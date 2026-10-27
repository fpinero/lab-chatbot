"""Manage isolated, loopback-only FastAPI/Vite development processes on macOS/Linux."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import get_origin

ROOT = Path(__file__).resolve().parents[1]


class DevError(Exception):
    pass


def process_signature(pid):
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart=,command="],
            capture_output=True,
            check=False,
            timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or not result.stdout.strip():
        return None
    return hashlib.sha256(result.stdout.strip()).hexdigest()


def owns_process(record):
    pid = record.get("pid")
    signature = record.get("signature")
    return (
        isinstance(pid, int)
        and pid > 1
        and isinstance(signature, str)
        and bool(signature)
        and process_signature(pid) == signature
    )


def stop_process(record):
    if not owns_process(record):
        return False
    pid = record["pid"]
    try:
        if os.getpgid(pid) != pid:
            raise DevError("The recorded process group changed; refusing to stop it.")
        os.killpg(pid, signal.SIGTERM)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and owns_process(record):
            time.sleep(0.1)
        if owns_process(record):
            os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return True


def frontend_environment(node, backend_port):
    # Backend credentials and Vite-exposed variables must not enter the frontend process.
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OPENROUTER_", "AUTH_", "ACCESS_", "VITE_"))
    }
    environment["PATH"] = str(node.parent) + os.pathsep + environment.get("PATH", "")
    environment["LAB_BROWSER_API_PORT"] = str(backend_port)
    return environment


def private_file(path, mode="a"):
    if path.is_symlink():
        raise DevError("Development state and logs must not be symlinks.")
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | (os.O_APPEND if mode == "a" else os.O_TRUNC),
        0o600,
    )
    os.chmod(path, 0o600)
    return os.fdopen(descriptor, mode)


@contextmanager
def state_lock(directory):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise DevError("Development state must use a regular private directory.")
    os.chmod(directory, 0o700)
    with private_file(directory / "operation.lock") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise DevError(
                "Another start/stop operation is in progress. Try again after it finishes."
            ) from None
        yield


def load_state(directory):
    path = directory / "state.json"
    if not path.exists():
        return None
    if path.is_symlink():
        raise DevError("Refusing a symlinked development state file.")
    try:
        state = json.loads(path.read_text())
    except (ValueError, OSError):
        raise DevError(
            "Development state is unreadable; no processes were stopped."
        ) from None
    if not isinstance(state, dict) or state.get("root") != str(ROOT):
        raise DevError(
            "Development state belongs to another checkout; refusing to use it."
        )
    records = state.get("processes")
    if not isinstance(records, list) or any(
        not isinstance(item, dict) for item in records
    ):
        raise DevError("Development state is invalid; no processes were stopped.")
    return state


def save_state(directory, state):
    temporary = directory / "state.tmp"
    with private_file(temporary, "w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
    temporary.replace(directory / "state.json")


def stop_state(directory, state):
    if state:
        for record in reversed(state.get("processes", [])):
            stop_process(record)
        (directory / "state.json").unlink(missing_ok=True)


def url_ready(url):
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=1) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def port_busy(port):
    with socket.socket() as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def print_running(state, directory, already=False):
    print(
        "Development services already running."
        if already
        else "Development services ready."
    )
    print(f"Web:     http://127.0.0.1:{state['frontend_port']}")
    print(f"Backend: http://127.0.0.1:{state['backend_port']}")
    print(f"Provider: {state['provider_mode']}")
    print(f"Logs: {directory / 'backend.log'} and {directory / 'frontend.log'}")
    print(f"Stop: {ROOT / 'stop-dev.sh'}")


def backend_environment(filename, port):
    from dotenv import dotenv_values

    sys.path.insert(0, str(ROOT / "backend"))
    from app.config import Settings

    environment = dict(os.environ)
    if filename.exists():
        environment.update(
            {
                key: value
                for key, value in dotenv_values(filename, interpolate=False).items()
                if value is not None
            }
        )
    elif filename != ROOT / ".env.local":
        raise DevError("The requested development environment file does not exist.")
    if environment.get("APP_ENV", "development") not in {"development", "test"}:
        raise DevError("Development scripts refuse production configuration.")
    environment["APP_ENV"] = "development"
    environment["APP_ORIGIN"] = f"http://127.0.0.1:{port}"
    if (
        not environment.get("AUTH_PASSWORD_HASH")
        and not environment.get("AUTH_PASSWORD_HASH_FILE")
        and (ROOT / "private/owner.hash").is_file()
    ):
        environment["AUTH_PASSWORD_HASH_FILE"] = str(ROOT / "private/owner.hash")
    try:
        arguments = {}
        for name, field in Settings.model_fields.items():
            if name.upper() in environment:
                value = environment[name.upper()]
                arguments[name] = (
                    json.loads(value) if get_origin(field.annotation) is list else value
                )
        settings = Settings(**arguments)
    except (ValueError, OSError):
        raise DevError(
            "Development configuration is invalid. Check .env.local and the owner hash without printing credentials."
        ) from None
    if (
        settings.provider_mode == "openrouter"
        and not settings.openrouter_api_key.get_secret_value()
    ):
        raise DevError("Live mode requires a configured private OpenRouter key.")
    return environment, settings.provider_mode


def node_version(path):
    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        return result.stdout.strip().removeprefix("v") if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def select_node(directory, no_install):
    pinned = (ROOT / ".nvmrc").read_text().strip().removeprefix("v")
    explicit = os.environ.get("DEV_NODE_BIN")
    if explicit:
        binary = Path(explicit).expanduser().resolve()
        if node_version(binary) != pinned:
            raise DevError(f"DEV_NODE_BIN must point to Node {pinned}.")
        return binary
    local = ROOT / "private/tools/node-runtime/node_modules/node/bin/node"
    candidates = [local, Path(shutil.which("node") or "/nonexistent")]
    for pattern in [
        f".nvm/versions/node/v{pinned}/bin/node",
        f".volta/tools/image/node/{pinned}/bin/node",
        f".local/share/fnm/node-versions/v{pinned}/installation/bin/node",
        f"Library/Application Support/fnm/node-versions/v{pinned}/installation/bin/node",
    ]:
        candidates.append(Path.home() / pattern)
    candidates.extend(
        [
            Path("/opt/homebrew/opt/node@24/bin/node"),
            Path("/usr/local/opt/node@24/bin/node"),
        ]
    )
    for binary in candidates:
        if binary.is_file() and node_version(binary) == pinned:
            return binary.resolve()
    npm = shutil.which("npm")
    if no_install or not npm:
        raise DevError(
            f"Node {pinned} is required. Install it or set DEV_NODE_BIN; automatic preparation needs npm."
        )
    print(
        f"Preparing private Node {pinned} once; system Node is unchanged...", flush=True
    )
    with private_file(directory / "setup.log") as log:
        try:
            result = subprocess.run(
                [
                    npm,
                    "install",
                    "--prefix",
                    str(ROOT / "private/tools/node-runtime"),
                    "--no-save",
                    "--no-package-lock",
                    f"node@{pinned}",
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                env=frontend_environment(
                    Path(shutil.which("node") or "/usr/bin/node"), 8000
                ),
                check=False,
                timeout=180,
            )
        except (OSError, subprocess.TimeoutExpired):
            raise DevError(
                "Node preparation failed; inspect the private setup.log."
            ) from None
    if result.returncode or node_version(local) != pinned:
        raise DevError("Node preparation failed; inspect the private setup.log.")
    return local.resolve()


def launch(arguments, cwd, environment, log_path):
    with private_file(log_path) as log:
        return subprocess.Popen(
            arguments,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )


def wait_for(process, url, label):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise DevError(f"{label} exited during startup. Inspect its private log.")
        if url_ready(url):
            return
        time.sleep(0.2)
    raise DevError(f"{label} did not become ready. Inspect its private log.")


def start(args, directory):
    state = load_state(directory)
    if (
        state
        and all(owns_process(item) for item in state.get("processes", []))
        and len(state.get("processes", [])) == 2
    ):
        if (
            args.backend_port != state["backend_port"]
            or args.frontend_port != state["frontend_port"]
            or str(args.env_file) != state["env_file"]
        ):
            raise DevError(
                "Managed services use another configuration. Stop them before changing ports or the environment file."
            )
        if url_ready(
            f"http://127.0.0.1:{state['backend_port']}/api/health/ready"
        ) and url_ready(f"http://127.0.0.1:{state['frontend_port']}/"):
            print_running(state, directory, already=True)
            return
    stop_state(directory, state)
    for port in [args.backend_port, args.frontend_port]:
        if port_busy(port):
            raise DevError(
                f"Port {port} is already in use by an unmanaged process. It was left untouched; stop its launcher or choose another development port."
            )
    environment, provider_mode = backend_environment(args.env_file, args.frontend_port)
    node = select_node(directory, args.no_install)
    vite = ROOT / "frontend/node_modules/vite/bin/vite.js"
    if not vite.is_file():
        raise DevError("Prepare frontend dependencies first: npm --prefix frontend ci")
    state = {
        "root": str(ROOT),
        "env_file": str(args.env_file),
        "backend_port": args.backend_port,
        "frontend_port": args.frontend_port,
        "provider_mode": provider_mode,
        "processes": [],
    }
    processes = []
    try:
        backend = launch(
            [
                str(ROOT / "backend/.venv/bin/python"),
                "-m",
                "uvicorn",
                "app.main:create_app",
                "--factory",
                "--app-dir",
                str(ROOT / "backend"),
                "--host",
                "127.0.0.1",
                "--port",
                str(args.backend_port),
                "--reload",
                "--reload-dir",
                str(ROOT / "backend/app"),
                "--reload-dir",
                str(ROOT / "backend/migrations"),
                "--no-proxy-headers",
                "--no-access-log",
                "--log-level",
                "warning",
                "--timeout-graceful-shutdown",
                "10",
            ],
            ROOT,
            environment,
            directory / "backend.log",
        )
        processes.append(backend)
        state["processes"].append(
            {
                "name": "backend",
                "pid": backend.pid,
                "signature": process_signature(backend.pid),
            }
        )
        save_state(directory, state)
        wait_for(
            backend, f"http://127.0.0.1:{args.backend_port}/api/health/ready", "Backend"
        )
        frontend = launch(
            [
                str(node),
                str(vite),
                "--host",
                "127.0.0.1",
                "--port",
                str(args.frontend_port),
                "--strictPort",
            ],
            ROOT / "frontend",
            frontend_environment(node, args.backend_port),
            directory / "frontend.log",
        )
        processes.append(frontend)
        state["processes"].append(
            {
                "name": "frontend",
                "pid": frontend.pid,
                "signature": process_signature(frontend.pid),
            }
        )
        save_state(directory, state)
        wait_for(frontend, f"http://127.0.0.1:{args.frontend_port}/", "Frontend")
        for record in state["processes"]:
            record["signature"] = process_signature(record["pid"])
        save_state(directory, state)
    except (OSError, DevError, KeyboardInterrupt):
        for process in reversed(processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=15)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
        (directory / "state.json").unlink(missing_ok=True)
        raise DevError(
            "Startup did not complete; only newly launched services were stopped. Inspect the private logs."
        ) from None
    print_running(state, directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "stop"])
    parser.add_argument(
        "--env-file",
        type=Path,
        default=Path(os.environ.get("DEV_ENV_FILE", ROOT / ".env.local")),
    )
    parser.add_argument(
        "--backend-port",
        type=int,
        default=int(os.environ.get("DEV_BACKEND_PORT", "8000")),
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=int(os.environ.get("DEV_FRONTEND_PORT", "5173")),
    )
    parser.add_argument("--no-install", action="store_true")
    args = parser.parse_args()
    args.env_file = args.env_file.expanduser().resolve()
    if args.backend_port == args.frontend_port or any(
        not 1 <= port <= 65535 for port in [args.backend_port, args.frontend_port]
    ):
        raise DevError("Choose two distinct ports between 1 and 65535.")
    os.chdir(ROOT)
    directory = (
        Path(os.environ.get("DEV_STATE_DIR", ROOT / "private/dev"))
        .expanduser()
        .absolute()
    )
    with state_lock(directory):
        if args.command == "start":
            start(args, directory)
        else:
            state = load_state(directory)
            stop_state(directory, state)
            print(
                "Managed development services stopped. Data and logs preserved."
                if state
                else "No managed development services are running."
            )


if __name__ == "__main__":
    try:
        main()
    except DevError as error:
        raise SystemExit(str(error)) from None

"""Install isolated deployment tools locally, never change the system client or cluster."""

import argparse
import hashlib
import os
import platform
import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KUBECTL_VERSION = "v1.25.16"
KUBECONFORM_VERSION = "v0.7.0"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    system = {"Darwin": "darwin", "Linux": "linux"}.get(platform.system())
    architecture = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "amd64"}.get(
        platform.machine()
    )
    if not system or not architecture:
        raise SystemExit("This installer supports macOS/Linux ARM64 and AMD64.")
    url = f"https://dl.k8s.io/release/{KUBECTL_VERSION}/bin/{system}/{architecture}/kubectl"
    if not args.execute:
        print(
            f"Plan: install kubectl {KUBECTL_VERSION} and kubeconform {KUBECONFORM_VERSION} under ignored private/tools. No cluster access."
        )
        return
    directory = ROOT / "private/tools"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with urllib.request.urlopen(url + ".sha256", timeout=30) as response:
        expected = response.read(256).decode().strip()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise SystemExit("Official kubectl checksum is invalid.")
    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read(100 * 1024 * 1024)
    if hashlib.sha256(content).hexdigest() != expected:
        raise SystemExit("Official kubectl checksum verification failed.")
    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
        handle.write(content)
        candidate = Path(handle.name)
    candidate.chmod(0o700)
    os.replace(candidate, directory / "kubectl")
    if not shutil.which("go"):
        raise SystemExit(
            "Verified kubectl installed. Install Go to build the pinned kubeconform tool."
        )
    environment = dict(
        os.environ,
        GOBIN=str(directory),
        GOCACHE=str(directory / "go-cache"),
        GOMODCACHE=str(directory / "go-mod"),
        GOSUMDB="sum.golang.org",
        GOPROXY="https://proxy.golang.org,direct",
    )
    subprocess.run(
        [
            "go",
            "install",
            f"github.com/yannh/kubeconform/cmd/kubeconform@{KUBECONFORM_VERSION}",
        ],
        env=environment,
        check=True,
    )
    print(
        "Isolated deployment tools installed. System kubectl and Kubernetes resources unchanged."
    )


if __name__ == "__main__":
    main()

"""Read-only release planning and explicitly executed, scoped release phases."""

from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import yaml
from argon2 import Type, extract_parameters
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
KINDS = {
    "Namespace",
    "ServiceAccount",
    "ConfigMap",
    "PersistentVolumeClaim",
    "Service",
    "Deployment",
    "Ingress",
}


class ReleaseError(Exception):
    pass


class ToolError(ReleaseError):
    def __init__(self, category="failed"):
        self.category = category
        super().__init__(
            f"External tool {category}; no fallback to local production state is allowed."
        )


def run(arguments, *, data=None, check=True, timeout=60):
    """Never echo command input, credential files, or raw authentication errors."""
    try:
        result = subprocess.run(
            arguments,
            check=False,
            input=data,
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise ToolError("unavailable or timed out") from None
    if check and result.returncode:
        message = result.stderr.lower()
        category = next(
            (
                value
                for marker, value in [
                    ("forbidden", "forbidden"),
                    ("unauthorized", "unauthorized"),
                    ("conflict", "conflict"),
                    ("alreadyexists", "already exists"),
                ]
                if marker in message
            ),
            "failed",
        )
        raise ToolError(category)
    return result


def fingerprint():
    names = run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
    ).stdout.split("\0")
    digest = hashlib.sha256()
    for name in sorted(set(names) - {""}):
        path = ROOT / name
        if path.is_symlink():
            raise ReleaseError("Release sources must not contain symlinks.")
        digest.update(name.encode() + b"\0")
        digest.update(
            str(path.stat().st_mode & 0o111).encode() if path.exists() else b"deleted"
        )
        digest.update(path.read_bytes() if path.is_file() else b"")
    return digest.hexdigest()


def write_record(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


@dataclass(frozen=True)
class Config:
    context: str
    namespace: str
    deployment: str
    container: str
    repository: str
    platform: str
    origin: str
    kubectl: str
    kubeconform: str
    key_file: Path
    hash_file: Path
    release_ready: bool = False
    origin_verified: bool = False
    pull_secret: str = ""

    @classmethod
    def load(cls, filename):
        values = dotenv_values(filename, interpolate=False)

        def value(key):
            result = values.get(key)
            if not result or "$" in result or "`" in result:
                raise ReleaseError(
                    f"Configure {key} in the private release environment."
                )
            return result

        config = cls(
            context=value("KUBE_CONTEXT"),
            namespace=value("NAMESPACE"),
            deployment=value("DEPLOYMENT"),
            container=value("CONTAINER"),
            repository=value("IMAGE_REPO"),
            platform=value("PLATFORM"),
            origin=value("APP_ORIGIN"),
            kubectl=value("KUBECTL"),
            kubeconform=values.get("KUBECONFORM") or "kubeconform",
            key_file=ROOT / value("OPENROUTER_KEY_FILE"),
            hash_file=ROOT / value("OWNER_HASH_FILE"),
            release_ready=values.get("RELEASE_READY") == "true",
            origin_verified=values.get("ORIGIN_TLS_VERIFIED") == "true",
            pull_secret=values.get("IMAGE_PULL_SECRET") or "",
        )
        if not all(
            re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", item)
            for item in [config.namespace, config.deployment, config.container]
        ):
            raise ReleaseError("Invalid Kubernetes target name.")
        if (
            not re.fullmatch(r"[A-Za-z0-9._:/-]+", config.context)
            or not re.fullmatch(
                r"[a-z0-9][a-z0-9.:/_-]+/[a-z0-9._/-]+", config.repository
            )
            or "@" in config.repository
        ):
            raise ReleaseError("Invalid explicit context or image repository.")
        if config.platform not in {"linux/arm64", "linux/amd64"}:
            raise ReleaseError("Choose one explicit supported Linux architecture.")
        if not re.fullmatch(r"https://[a-z0-9.-]+", config.origin):
            raise ReleaseError("APP_ORIGIN must be an exact HTTPS origin.")
        if config.pull_secret and not re.fullmatch(
            r"[a-z0-9][a-z0-9.-]{0,252}", config.pull_secret
        ):
            raise ReleaseError("Invalid image pull Secret name.")
        return config

    def kube(
        self, *arguments, data=None, check=True, request_timeout="20s", timeout=60
    ):
        return run(
            [
                self.kubectl,
                "--context",
                self.context,
                f"--request-timeout={request_timeout}",
                *arguments,
            ],
            data=data,
            check=check,
            timeout=timeout,
        )

    def get(self, kind, name):
        response = self.kube(
            "-n", self.namespace, "get", kind, name, "--ignore-not-found", "-o", "json"
        )
        return json.loads(response.stdout) if response.stdout.strip() else None


def image_tag(image, repository):
    tagged = image.split("@", 1)[0]
    if not tagged.startswith(repository + ":"):
        raise ReleaseError(
            "Production does not use the configured image repository and tag."
        )
    tag = tagged[len(repository) + 1 :]
    if not re.fullmatch(r"v?(?:0|[1-9][0-9]*)", tag):
        raise ReleaseError(
            "Production must use an unambiguous integer tag, optionally prefixed with v."
        )
    return tag


def baseline(config):
    deployment = config.get("deployment", config.deployment)
    if deployment is None:
        return {
            "image": None,
            "resource_version": None,
            "spec_hash": None,
            "next_tag": "1",
        }
    containers = deployment["spec"]["template"]["spec"]["containers"]
    matches = [item for item in containers if item["name"] == config.container]
    if len(matches) != 1:
        raise ReleaseError("The explicit production container could not be identified.")
    image = matches[0]["image"]
    tag = image_tag(image, config.repository)
    prefix = "v" if tag.startswith("v") else ""
    return {
        "image": image,
        "resource_version": deployment["metadata"]["resourceVersion"],
        "spec_hash": hashlib.sha256(
            json.dumps(deployment["spec"], sort_keys=True).encode()
        ).hexdigest(),
        "next_tag": prefix + str(int(tag.removeprefix("v")) + 1),
    }


def render(config, tag="1", digest=None):
    if not re.fullmatch(r"v?(?:0|[1-9][0-9]*)", tag):
        raise ReleaseError("Use an integer image tag.")
    if digest is not None and not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ReleaseError("Invalid immutable image digest.")
    text = config.kube("kustomize", str(ROOT / "k8s")).stdout
    objects = list(yaml.safe_load_all(text))
    for obj in objects:
        if not isinstance(obj, dict) or obj.get("kind") not in KINDS:
            raise ReleaseError(
                "Only the application's non-secret resource kinds may be rendered."
            )
        metadata = obj["metadata"]
        if obj["kind"] == "Namespace":
            metadata["name"] = config.namespace
        else:
            metadata["namespace"] = config.namespace
        if (
            obj["kind"] in {"Deployment", "Service", "Ingress", "ServiceAccount"}
            and metadata["name"] != "labchatbot"
        ):
            raise ReleaseError("Unexpected base resource name.")
        if config.deployment != "labchatbot" or config.container != "app":
            raise ReleaseError(
                "This manifest set targets Deployment labchatbot and container app."
            )
        if obj["kind"] == "Deployment":
            image = f"{config.repository}:{tag}" + (f"@{digest}" if digest else "")
            obj["spec"]["template"]["spec"]["containers"][0]["image"] = image
            if config.pull_secret:
                obj["spec"]["template"]["spec"]["imagePullSecrets"] = [
                    {"name": config.pull_secret}
                ]
            metadata.setdefault("annotations", {})["kubernetes.io/change-cause"] = (
                f"release {tag}"
            )
            metadata["annotations"]["labchatbot/source-fingerprint"] = fingerprint()
        elif obj["kind"] == "ConfigMap":
            obj["data"]["APP_ORIGIN"] = config.origin
        elif obj["kind"] == "Ingress":
            obj["spec"]["rules"][0]["host"] = config.origin.removeprefix("https://")
    return objects


def validate(config, objects, server=False):
    document = yaml.safe_dump_all(objects, sort_keys=False)
    run(
        [
            config.kubeconform,
            "-strict",
            "-summary",
            "-kubernetes-version",
            "1.25.6",
            "-",
        ],
        data=document,
    )
    if server:
        compatible_client(config)
        if config.get("namespace", config.namespace) is None:
            raise ReleaseError(
                "Server dry-run of namespaced resources requires the staged namespace bootstrap first."
            )
        config.kube(
            "apply",
            "--dry-run=server",
            "--server-side",
            "--field-manager=labchatbot-release",
            "-f",
            "-",
            data=document,
        )
    return {
        "valid_resources": len(objects),
        "schema_version": "1.25.6",
        "server_dry_run": server,
    }


def compatible_client(config):
    versions = json.loads(config.kube("version", "-o", "json").stdout)

    def minor(name):
        match = re.match(r"v1\.(\d+)\.", versions[name]["gitVersion"])
        if not match:
            raise ReleaseError(
                "Cannot establish Kubernetes client/server compatibility."
            )
        return int(match[1])

    if abs(minor("clientVersion") - minor("serverVersion")) > 1:
        raise ReleaseError(
            "Use kubectl within one minor version of the configured server."
        )


def registry(image):
    response = run(
        [
            "docker",
            "buildx",
            "imagetools",
            "inspect",
            image,
            "--format",
            "{{json .Manifest}}",
        ],
        check=False,
    )
    if response.returncode:
        message = response.stderr.lower()
        denied = any(
            item in message
            for item in ["unauthorized", "denied", "forbidden", "credential"]
        )
        if not denied and (
            "manifest unknown" in message
            or "no such manifest" in message
            or f"{image.lower()}: not found" in message
        ):
            return None
        raise ReleaseError(
            "Registry existence could not be established; check credentials or connectivity."
        )
    result = json.loads(response.stdout)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", result.get("digest", "")):
        raise ReleaseError("Registry did not return a trustworthy manifest digest.")
    return result


def receipt_path(config, tag):
    return ARTIFACTS / "releases" / f"{config.namespace}-{tag}.json"


def verify_remote(config, saved):
    reference = f"{saved['image']}@{saved['digest']}"
    raw = json.loads(
        run(
            [
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                reference,
                "--format",
                "{{json .Image}}",
            ]
        ).stdout
    )
    platform = f"{raw.get('os')}/{raw.get('architecture')}"
    labels = raw.get("config", {}).get("Labels", {})
    if (
        platform != config.platform
        or labels.get("com.labchatbot.source-fingerprint") != saved["fingerprint"]
    ):
        raise ReleaseError(
            "Registry image configuration does not match the recorded source and architecture."
        )


def local_gate(config):
    if not config.release_ready:
        raise ReleaseError(
            "RELEASE_READY=false: finish local verification and staged release review first."
        )
    if run(["git", "status", "--porcelain", "--untracked-files=normal"]).stdout.strip():
        raise ReleaseError(
            "Commit the reviewed public source before publishing or deploying."
        )
    if run(["git", "branch", "--show-current"]).stdout.strip() != "main":
        raise ReleaseError(
            "Production publication/deployment must use verified integrated main."
        )
    path = ARTIFACTS / "preparation-verification.json"
    if (
        not path.is_file()
        or json.loads(path.read_text()).get("fingerprint") != fingerprint()
    ):
        raise ReleaseError(
            "Run k8s/scripts/verify-preparation.sh for this exact source tree first."
        )


class Lease:
    """Renew a namespaced Kubernetes Lease using resourceVersion compare-and-swap."""

    def __init__(self, config):
        self.config = config
        self.holder = "labchatbot-" + uuid4().hex
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.thread = None
        self.name = "labchatbot-release"

    def save(self, current, holder, duration=90):
        now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        metadata = {"name": self.name, "namespace": self.config.namespace}
        if current:
            metadata["resourceVersion"] = current["metadata"]["resourceVersion"]
        obj = {
            "apiVersion": "coordination.k8s.io/v1",
            "kind": "Lease",
            "metadata": metadata,
            "spec": {
                "holderIdentity": holder,
                "leaseDurationSeconds": duration,
                "renewTime": now,
            },
        }
        self.config.kube(
            "create" if current is None else "replace", "-f", "-", data=json.dumps(obj)
        )

    def check(self):
        if self.lost.is_set():
            raise ReleaseError(
                "Release lock was lost. No subsequent publication or rollout is permitted."
            )

    def renew(self):
        while not self.stop.wait(20):
            try:
                current = self.config.get("lease", self.name)
                if not current or current["spec"].get("holderIdentity") != self.holder:
                    raise ReleaseError("Release lock ownership changed.")
                self.save(current, self.holder)
            except ReleaseError:
                self.lost.set()
                return

    def __enter__(self):
        current = self.config.get("lease", self.name)
        if current and current["spec"].get("holderIdentity"):
            stamp = current["spec"].get("renewTime") or current["spec"].get(
                "acquireTime"
            )
            if not stamp:
                raise ReleaseError(
                    "Existing release lock has no safe expiry information."
                )
            expiry = datetime.fromisoformat(stamp) + timedelta(
                seconds=current["spec"]["leaseDurationSeconds"]
            )
            if expiry > datetime.now(UTC):
                raise ReleaseError("Another machine holds the release lock.")
        self.save(current, self.holder)
        self.thread = threading.Thread(target=self.renew, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *unused):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=25)
        try:
            current = self.config.get("lease", self.name)
            if current and current["spec"].get("holderIdentity") == self.holder:
                self.save(current, "", 1)
        except ReleaseError:
            pass


def ensure_baseline(config, expected):
    if baseline(config) != expected:
        raise ReleaseError(
            "Production changed since planning. Recompute the release; do not overwrite it."
        )


def publish(config, plan, lock):
    tag = plan["next_tag"]
    image = f"{config.repository}:{tag}"
    existing = registry(image)
    fp = fingerprint()
    path = receipt_path(config, tag)
    if existing:
        saved = json.loads(path.read_text()) if path.is_file() else {}
        if saved.get("fingerprint") != fp or saved.get("digest") != existing["digest"]:
            raise ReleaseError(
                "The next immutable tag already exists for unverified/different source. It will not be overwritten or skipped."
            )
        verify_remote(config, saved)
        return saved
    revision = run(["git", "rev-parse", "HEAD"]).stdout.strip()
    run(
        [
            "docker",
            "buildx",
            "build",
            "--platform",
            config.platform,
            "--provenance=false",
            "--load",
            "-t",
            image,
            "--build-arg",
            f"SOURCE_REVISION={revision}",
            "--build-arg",
            f"SOURCE_FINGERPRINT={fp}",
            ".",
        ],
        timeout=1800,
    )
    run([sys.executable, str(ROOT / "scripts/smoke-image.py"), image], timeout=300)
    inspected = json.loads(
        run(["docker", "image", "inspect", image, "--format", "{{json .}}"]).stdout
    )
    if (
        f"{inspected.get('Os')}/{inspected.get('Architecture')}" != config.platform
        or inspected.get("Config", {})
        .get("Labels", {})
        .get("com.labchatbot.source-fingerprint")
        != fp
    ):
        raise ReleaseError(
            "The local image changed or has an unexpected architecture/source label."
        )
    if fingerprint() != fp:
        raise ReleaseError("Source changed during image verification.")
    lock.check()
    ensure_baseline(config, plan)
    if registry(image) is not None:
        raise ReleaseError(
            "The immutable tag appeared during build; publication aborted."
        )
    run(["docker", "push", image], timeout=900)
    lock.check()
    descriptor = registry(image)
    if descriptor is None:
        raise ReleaseError("Published image cannot be verified in the registry.")
    saved = {
        "tag": tag,
        "image": image,
        "digest": descriptor["digest"],
        "fingerprint": fp,
        "revision": revision,
        "platform": config.platform,
        "baseline": plan,
        "published_at": datetime.now(UTC).isoformat(),
    }
    verify_remote(config, saved)
    write_record(path, saved)
    return saved


def deploy(config, plan, saved, with_infra, lock, rollback=False):
    if not config.origin_verified:
        raise ReleaseError(
            "Verify origin TLS during the staged deployment before setting ORIGIN_TLS_VERIFIED=true."
        )
    if saved.get("fingerprint") != fingerprint() and not rollback:
        raise ReleaseError("Published image does not match the verified source tree.")
    if not rollback and saved.get("baseline") != plan:
        raise ReleaseError(
            "Production changed after publication. Review the saved baseline before deployment."
        )
    descriptor = registry(saved["image"])
    if (
        not descriptor
        or descriptor["digest"] != saved["digest"]
        or saved["platform"] != config.platform
    ):
        raise ReleaseError("Published digest or target architecture changed.")
    verify_remote(config, saved)
    if not config.kube(
        "-n",
        config.namespace,
        "get",
        "secret",
        "labchatbot-secrets",
        "-o",
        "jsonpath={.metadata.name}",
    ).stdout:
        raise ReleaseError(
            "Prepare the application Secret in the explicit namespace first."
        )
    objects = render(config, saved["tag"], saved["digest"])
    deployment = next(item for item in objects if item["kind"] == "Deployment")
    if plan["image"] is None and not with_infra:
        raise ReleaseError(
            "First deployment requires --with-infra after namespace and Secret preparation."
        )
    if rollback:
        current = config.get("deployment", config.deployment)
        if not current:
            raise ReleaseError("There is no production Deployment to roll back.")
        deployment = copy.deepcopy(current)
        deployment.pop("status", None)
        deployment["spec"]["template"]["spec"]["containers"] = [
            {**item, "image": f"{saved['image']}@{saved['digest']}"}
            if item["name"] == config.container
            else item
            for item in deployment["spec"]["template"]["spec"]["containers"]
        ]
        deployment["metadata"].setdefault("annotations", {})[
            "kubernetes.io/change-cause"
        ] = f"rollback to {saved['tag']}"
    selected = objects if with_infra and not rollback else [deployment]
    validate(config, selected, server=True)
    diff = config.kube(
        "diff", "-f", "-", data=yaml.safe_dump_all(selected), check=False
    )
    if diff.returncode not in {0, 1}:
        raise ReleaseError("Server-side deployment diff failed.")
    write_record(
        ARTIFACTS / "releases" / f"{config.namespace}-{saved['tag']}-desired.json",
        {"items": selected, "baseline": plan},
    )
    lock.check()
    ensure_baseline(config, plan)
    if with_infra and not rollback:
        for obj in objects:
            if obj["kind"] != "Deployment":
                config.kube(
                    "apply",
                    "--server-side",
                    "--field-manager=labchatbot-release",
                    "-f",
                    "-",
                    data=json.dumps(obj),
                )
    lock.check()
    ensure_baseline(config, plan)
    if plan["resource_version"]:
        deployment["metadata"]["resourceVersion"] = plan["resource_version"]
    config.kube(
        "replace" if plan["image"] else "create", "-f", "-", data=json.dumps(deployment)
    )
    config.kube(
        "-n",
        config.namespace,
        "rollout",
        "status",
        f"deployment/{config.deployment}",
        "--timeout=300s",
        request_timeout="310s",
        timeout=330,
    )
    lock.check()
    after = baseline(config)
    if after["image"] != f"{saved['image']}@{saved['digest']}":
        raise ReleaseError("Rollout did not retain the exact intended image digest.")
    write_record(
        ROOT / "k8s/release-state.local.json",
        {
            **saved,
            "deployed_at": datetime.now(UTC).isoformat(),
            "previous_image": plan["image"],
        },
    )
    health_check(config)


def health_check(config):
    with httpx.Client(timeout=15, follow_redirects=False, trust_env=False) as client:
        results = {}
        for path, expected in [
            ("/", 200),
            ("/api/health/live", 200),
            ("/api/health/ready", 200),
            ("/api/images/jobs", 401),
        ]:
            try:
                response = client.get(config.origin + path)
            except httpx.HTTPError:
                raise ReleaseError(
                    "Public HTTPS verification failed. Inspect DNS, Cloudflare and origin TLS before another deployment."
                ) from None
            results[path] = response.status_code
            if response.status_code != expected:
                raise ReleaseError(
                    f"Public check {path} returned {response.status_code}; expected {expected}. Review the live state before retrying."
                )
    return {
        "public_statuses": results,
        "owner_sign_in_and_authenticated_read": "manual verification required",
        "paid_requests": 0,
    }


def change_paths(before, after, prefix=""):
    if isinstance(before, dict) and isinstance(after, dict):
        paths = []
        for key in sorted(before.keys() | after.keys()):
            path = f"{prefix}/{key}"
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(change_paths(before[key], after[key], path))
        return paths
    return [prefix] if before != after else []


def diff_summary(config, objects):
    validate(config, objects, server=True)
    response = config.kube(
        "diff",
        "--server-side",
        "--field-manager=labchatbot-release",
        "-f",
        "-",
        data=yaml.safe_dump_all(objects),
        check=False,
    )
    if response.returncode not in {0, 1}:
        raise ReleaseError("Server-side diff failed.")
    summary = []
    for desired in objects:
        current = config.get(desired["kind"], desired["metadata"]["name"])

        def comparable(value):
            if value is None:
                return {}
            return {key: value[key] for key in ["spec", "data"] if key in value}

        summary.append(
            {
                "kind": desired["kind"],
                "name": desired["metadata"]["name"],
                "action": "create" if current is None else "review",
                "changed_field_paths": change_paths(
                    comparable(current), comparable(desired)
                )[:100],
            }
        )
    return {
        "changes": response.returncode == 1,
        "resources": summary,
        "values_redacted": True,
        "executed": False,
    }


def secret_summary(config):
    for path in [config.key_file, config.hash_file]:
        if not path.is_file() or path.is_symlink() or path.stat().st_mode & 0o077:
            raise ReleaseError(
                "Private credential files must exist, be regular files and have mode 0600."
            )
    parameters = extract_parameters(config.hash_file.read_text().strip())
    if (
        parameters.type != Type.ID
        or parameters.memory_cost < 65536
        or parameters.time_cost < 3
        or not config.key_file.read_text().strip()
    ):
        raise ReleaseError(
            "Private credentials must include a strong owner hash and a nonempty provider key."
        )
    return {
        "secret": "labchatbot-secrets",
        "namespace": config.namespace,
        "keys": ["openrouter.key", "owner.hash"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="plan",
        choices=[
            "plan",
            "render",
            "validate",
            "bootstrap",
            "secrets",
            "publish",
            "deploy",
            "release",
            "rollback",
            "health",
            "diff",
        ],
    )
    parser.add_argument("--env-file", type=Path, default=ROOT / "k8s/.env")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--with-infra", action="store_true")
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--tag")
    parser.add_argument("--ack-schema-compatible", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.tag and not re.fullmatch(r"v?(?:0|[1-9][0-9]*)", args.tag):
        raise ReleaseError("Use an integer image tag.")
    config = Config.load(args.env_file)
    if args.command == "health":
        print(json.dumps(health_check(config)))
        return
    if args.execute and args.command not in {"plan", "render", "validate"}:
        print(
            json.dumps(
                {
                    "requested_phase": args.command,
                    "context": config.context,
                    "namespace": config.namespace,
                    "deployment": config.deployment,
                    "container": config.container,
                    "origin": config.origin,
                }
            ),
            flush=True,
        )
    if args.command in {"render", "validate", "diff"}:
        objects = render(config, args.tag or "1")
        if args.command == "render":
            text = yaml.safe_dump_all(objects, sort_keys=False)
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text)
            else:
                print(text)
        elif args.command == "validate":
            print(json.dumps(validate(config, objects, args.server)))
        else:
            print(json.dumps(diff_summary(config, objects), indent=2))
        return
    if args.command == "secrets":
        summary = secret_summary(config)
        if args.execute:
            compatible_client(config)
            if config.get("namespace", config.namespace) is None:
                raise ReleaseError("Bootstrap the explicit namespace first.")
            obj = {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": summary["secret"], "namespace": config.namespace},
                "type": "Opaque",
                "data": {
                    "openrouter.key": base64.b64encode(
                        config.key_file.read_bytes()
                    ).decode(),
                    "owner.hash": base64.b64encode(
                        config.hash_file.read_bytes()
                    ).decode(),
                },
            }
            config.kube(
                "apply",
                "--server-side",
                "--field-manager=labchatbot-secrets",
                "-f",
                "-",
                data=json.dumps(obj),
            )
        print(json.dumps({**summary, "executed": args.execute}))
        return
    if args.command == "bootstrap":
        if args.execute:
            compatible_client(config)
            if config.get("namespace", config.namespace) is None:
                config.kube(
                    "create",
                    "-f",
                    "-",
                    data=json.dumps(
                        {
                            "apiVersion": "v1",
                            "kind": "Namespace",
                            "metadata": {"name": config.namespace},
                        }
                    ),
                )
        print(
            json.dumps(
                {
                    "context": config.context,
                    "namespace": config.namespace,
                    "executed": args.execute,
                }
            )
        )
        return
    plan = baseline(config)
    if not args.execute or args.command == "plan":
        print(
            json.dumps(
                {
                    "context": config.context,
                    "namespace": config.namespace,
                    "deployment": config.deployment,
                    "container": config.container,
                    "image_repository": config.repository,
                    "platform": config.platform,
                    "origin": config.origin,
                    "baseline": plan,
                    "fingerprint": fingerprint(),
                    "release_ready": config.release_ready,
                    "origin_tls_verified": config.origin_verified,
                    "requested_phase": args.command,
                    "executed": False,
                },
                indent=2,
            )
        )
        return
    compatible_client(config)
    local_gate(config)
    if config.get("namespace", config.namespace) is None:
        raise ReleaseError(
            "Bootstrap the namespace in its own reviewed step before acquiring a release Lease."
        )
    nodes = json.loads(config.kube("get", "nodes", "-o", "json").stdout)["items"]
    if not nodes or any(
        item["status"]["nodeInfo"]["architecture"] != config.platform.split("/")[1]
        for item in nodes
    ):
        raise ReleaseError(
            "Target node architecture does not match the selected image platform."
        )
    with Lease(config) as lock:
        ensure_baseline(config, plan)
        tag = args.tag if args.command == "rollback" else plan["next_tag"]
        if args.command == "rollback" and (not args.ack_schema_compatible or not tag):
            raise ReleaseError(
                "Rollback requires an explicit recorded tag and --ack-schema-compatible after backup review."
            )
        path = receipt_path(config, tag or "")
        saved = (
            publish(config, plan, lock)
            if args.command in {"publish", "release"}
            else json.loads(path.read_text())
            if path.is_file()
            else None
        )
        if saved is None:
            raise ReleaseError(
                "A verified publication receipt for this target tag is required."
            )
        if args.command in {"deploy", "release", "rollback"}:
            deploy(
                config,
                plan,
                saved,
                args.with_infra,
                lock,
                rollback=args.command == "rollback",
            )
        print(
            json.dumps(
                {
                    "phase": args.command,
                    "image": saved["image"],
                    "digest": saved["digest"],
                    "executed": True,
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except (ReleaseError, ValueError, KeyError, OSError):
        # Messages from our controlled errors contain no secret data or provider bodies.
        error = sys.exc_info()[1]
        print(
            str(error)
            if isinstance(error, ReleaseError)
            else "Release input or local evidence is invalid.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

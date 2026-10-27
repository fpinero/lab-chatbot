# Kubernetes deployment preparation

This directory manages a single-owner application on the existing K3s, Traefik and Cloudflare stack. Local verification, publication and deployment are separate phases. All write phases require an explicit `--execute`. Production releases use verified integrated main; source preparation alone does not publish or deploy anything.

The target namespace, Deployment and Service are `labchatbot`, the application container is `app`, and the public origin is `https://labchatbot.nivelepsilon.com`. Commands run from the repository root and always pass the configured Kubernetes context explicitly. No script changes the current system context or installs shared infrastructure.

## Files and private configuration

`namespace.yaml`, `serviceaccount.yaml`, `pvc.yaml`, `configmap.yaml`, `service.yaml`, `deployment.yaml` and `ingress.yaml` form the Kustomize resource set. `secret-template.yaml.example` is documentation only and is deliberately excluded. The application Service exposes port 80 internally and targets container port 8000. FastAPI serves the compiled frontend and API in one image; Nginx is unnecessary.

Copy the non-secret release settings from `k8s/.env.example` or use the local setup helper:

```sh
uv sync --project backend --locked
backend/.venv/bin/python scripts/configure-deploy.py
backend/.venv/bin/python scripts/configure-deploy.py --write
```

The helper reads the existing excluded `.env.local` and owner hash privately, then creates these ignored local files without printing credentials:

| File | Purpose |
| --- | --- |
| `k8s/.env` | Explicit context, namespace, repository, origin and private file references |
| `private/deploy/openrouter.key` | Existing restricted OpenRouter key |
| `private/deploy/owner.hash` | Existing strong Argon2id owner hash |
| `private/deploy/backup.key` | Random 32-byte backup encryption key |

Files use mode 0600 and the credential directory uses mode 0700. Existing files are preserved, never silently rotated. `.env` files are parsed as data, not sourced as shell programs. The root `.env.local` and running local application are not changed. References, private notes, credentials and data are excluded from Git and the Docker context. The image uses explicit public-source COPY instructions.

`SPEND_CONTROL=provider` keeps the existing OpenRouter key budget shared across every modality. The manifests do not allocate a monetary amount per request, day or modality. `TRUSTED_PROXY_NETWORKS=[]` deliberately trusts no forwarded client identity until actual proxy peers are verified.

`RELEASE_READY=false` prevents production publication/deployment until local evidence and the intended integrated release are reviewed. `ORIGIN_TLS_VERIFIED=false` separately prevents rollout until the intended origin mode and connectivity are reviewed. Neither flag is provider spending authorization. New environments keep both false until their respective evidence exists; the template is not a record of the deployed environment.

## Isolated deployment tools

The inspected server is K3s 1.25.6. A system kubectl 1.36 can answer reads but is outside the supported client/server skew for deployments. The local installer leaves it unchanged and prepares kubectl 1.25.16 plus kubeconform 0.7.0 under ignored `private/tools`:

```sh
backend/.venv/bin/python scripts/install-deploy-tools.py
backend/.venv/bin/python scripts/install-deploy-tools.py --execute
```

The installer verifies the official kubectl SHA-256 download and builds pinned kubeconform through the Go module checksum database. It requires Go. The generated private environment uses those isolated executables. Re-evaluate these pins when the cluster is upgraded. This tooling does not upgrade K3s or Traefik. See the [Kubernetes version skew policy](https://kubernetes.io/releases/version-skew-policy/).

## Safe inspection and local verification

These commands do not publish images or persist cluster resources:

```sh
k8s/scripts/plan-release.sh
k8s/scripts/render.sh --output artifacts/labchatbot-rendered.yaml
k8s/scripts/validate.sh
k8s/scripts/bootstrap-namespace.sh
k8s/scripts/prepare-secrets.sh
k8s/scripts/release-image.sh
k8s/scripts/deploy-k8s.sh
k8s/scripts/release-and-deploy.sh
k8s/scripts/rollback.sh
```

Planning reads the live named Deployment using `--ignore-not-found`. Only confirmed absence selects the first tag, `1`. Forbidden, timeout and unavailable-cluster results abort. Existing production integer tags increment by one, with an optional existing `v` prefix. Registry ports are parsed correctly. Arbitrary semver, ambiguous references, digest-only production references and `latest` are rejected.

Rendering uses Kustomize and produces non-secret manifests. Validation checks strict Kubernetes 1.25.6 schemas. Server dry-run is a later read-only validation step after the real namespace has been bootstrapped; an ephemeral namespace dry-run does not make namespaced resources exist:

```sh
k8s/scripts/validate.sh --server
k8s/scripts/diff.sh
```

The diff helper returns changed field paths without printing live values, so an accidentally inline credential cannot enter the terminal log. Review the rendered non-secret desired manifest alongside that summary.

Run the full local preparation gate with the pinned Node/uv tools on PATH:

```sh
k8s/scripts/verify-preparation.sh
```

It runs backend/frontend/browser checks, deployment and encrypted-backup regressions, shell syntax, schema validation, Compose validation, an actual ARM64 Docker build and a disposable container smoke check. Browser fixtures use isolated loopback ports 28000/25173, leaving the owner's normal local services alone. Container checks use synthetic credentials, no network, non-root UID 10001, read-only root and disposable volumes. They verify guarded routes, mock text/image history, authenticated media and persistence after restart, then production startup without generation. No paid provider request is made.

Evidence is stored in ignored `artifacts/preparation-verification.json` with the exact public-source fingerprint and local image ID. Source changes invalidate the gate. A production publish or deployment also requires a clean, reviewed, integrated `main`; preparation on a feature branch cannot publish. No release workflow runs automatically from a main merge.

## Container and persistence

The Docker image pins Node/Python/uv and installs locked production dependencies. One Uvicorn worker runs as UID/GID 10001. Root is read-only, capabilities are dropped, privilege escalation is disabled and the service-account token is not mounted. Only `/data` and bounded `/tmp` are writable. Initial resources are 100m CPU/256 MiB requested and 1 CPU/2 GiB limited; validate resource usage with representative document/media work during staged deployment.

The Deployment has one replica and `Recreate` strategy. Updates incur a short maintenance interruption. The static-web example's assumption that a previous pod always remains serving during a failed rollout does not apply here. Validate image availability before changing the Deployment.

The PVC requests 10 GiB using the inspected `local-path` class, and application storage is capped at 5 GiB. Local-path storage is tied to one node and is not replicated. The request is not a verified filesystem quota. Node loss needs recovery from an external backup. The storage class has Delete reclaim policy: never delete the production namespace or PVC as a deployment or rollback operation. These scripts do not contain such operations.

Compose is a separate local, mock-only container workflow on `127.0.0.1:8080` with a named volume. It mounts only the owner hash and never the real provider key:

```sh
docker compose up --build -d
docker compose down
```

Do not use `down --volumes` for retained data. Kubernetes preparation does not run Compose automatically.

## Traefik, Cloudflare and caching

The Ingress preserves the supplied working pattern: `ingressClassName: traefik`, entrypoints `web,websecure`, `router.tls: "true"`, one `/` Prefix route and no certificate issuer or `spec.tls` Secret reference. Existing Traefik and Cloudflare configuration is reused, not changed. No cert-manager, additional controller or redundant HTTPS redirect middleware is installed.

The owner confirmed Cloudflare Full mode, a proxied DNS record pointing to `141.145.211.128`, and Traefik's default self-signed origin certificate, matching the existing mouse-desktop pattern. The first deployment preserves this configuration without installing Cert Manager or changing shared Traefik/Cloudflare settings. HTTPS encrypts the origin connection in this mode, while Full does not validate the origin certificate's issuer or hostname. This is not a Full (strict) verification. See [Cloudflare Full](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full/).

For this environment, `ORIGIN_TLS_VERIFIED=true` records the explicitly confirmed Full-mode configuration and successful origin/edge checks. It does not claim public-CA trust or hostname validation at the origin. Public HTTPS checks retain normal browser/client certificate validation. A direct-origin diagnostic against the self-signed endpoint must be clearly identified and must not send owner credentials. A future Full (strict) configuration needs a valid matching certificate, which can be installed without Cert Manager. Do not change SSL modes or disable public HTTPS verification merely to make checks pass. See [Traefik 2.9 Ingress annotations](https://doc.traefik.io/traefik/v2.9/routing/providers/kubernetes-ingress/) and [Cloudflare Full (strict)](https://developers.cloudflare.com/ssl/origin-configuration/ssl-modes/full-strict/).

The supplied Nginx example serves a static site; its fallback/cache locations are not copied into this authenticated application. FastAPI keeps private API, SSE and media responses `no-store`. Confirm that Cloudflare cache rules do not override this. The frontend uses an SPA fallback while unknown `/api` routes remain guarded JSON errors. Test real uploads and SSE through the edge; any scoped timeout/buffering adjustment must affect only this application.

## Staged deployment

Use separate phases for a first deployment and inspect each result before continuing. These phases were exercised for version 1 on 2026-10-27; always plan from the current live Deployment rather than assuming the first tag is still available.

1. Review the read-only plan, origin TLS, registry access and intended application release. Keep unrelated shared infrastructure untouched.
2. Create the namespace in its own explicit step:

   ```sh
   k8s/scripts/bootstrap-namespace.sh --execute
   ```

3. Install the prepared private Secret without printing values:

   ```sh
   k8s/scripts/prepare-secrets.sh --execute
   ```

   For a private registry, prepare a namespace-local image pull Secret through a private credential file and set `IMAGE_PULL_SECRET` in `k8s/.env`. Registry credentials remain in the local Docker credential store or private files, never the repository. Other applications' Secrets are not copied.

4. Integrate the reviewed source, run the exact-source verification gate, verify Docker registry login privately and set `RELEASE_READY=true`. Publish the next immutable tag:

   ```sh
   k8s/scripts/release-image.sh --execute
   ```

5. Inspect the planned tag, receipt and rendered resources. Complete server dry-run, origin TLS and diff review, then deploy infrastructure plus application on the first rollout:

   ```sh
   k8s/scripts/deploy-k8s.sh --execute --with-infra
   ```

   Subsequent application releases omit `--with-infra`, leaving Service, Ingress, PVC and ConfigMap unchanged. An intentional infrastructure/configuration update uses that flag after review. A combined `release-and-deploy.sh --execute` is available later, but the separate steps are preferable for the first deployment.

6. Check public HTTPS, readiness, unauthorized-read denial, normal owner sign-in and an authenticated read. The public checks are read-only; owner sign-in is a separate manual verification, not inferred from a healthy pod. No paid generation is included. Verify restart persistence and mobile behavior before calling the deployment complete.

Publishing/deploying acquires a renewable, namespaced Kubernetes Lease, including cross-machine exclusion. It fails if the lock cannot be obtained or renewed. The live baseline and source fingerprint are rechecked, existing tags are never overwritten/skipped, and a previously published tag can be reused only with a matching local receipt, digest and remote source/platform labels. Rollout uses the pinned digest. Existing Deployments use resourceVersion compare-and-swap; the first Deployment is created atomically. Rendering and a private desired-state record happen before the one Deployment write, avoiding a stale-image intermediate revision.

The YAML files are reusable templates, not an authoritative record of what is currently deployed. Production is the version source. Ignored publication receipts, rendered desired-state artifacts and `k8s/release-state.local.json` record exact tag/digest/source and the previous image. Record successful integration/release metadata in the public append-only log without private data. A failed public check does not automatically roll back, retry a generation or increment another tag.

Version 1 deployed main revision `c7d42b2d92eeaabc94e24047f5f79c3abe7ed543` at immutable digest `sha256:8caa54eaf576c5fa7aeb637fdc3cd4eb3b529c9023ed08a74dc7230307a97f37`. Public and direct-origin protected reads returned 401/no-store, normal owner sign-in and authenticated catalog/budget reads worked, and a real pod replacement retained the PVC, SQLite integrity, owner session and a temporary private file. A 412 by 915 browser viewport showed no horizontal overflow and kept the 44-pixel Send button visible. Physical Android keyboard behavior, representative media recovery and real later-release rollback remain separate checks.

## Backups and rollback

Use a maintenance window and stop every application writer before snapshotting SQLite together with its referenced files. `scripts/backup-data.py` uses the SQLite backup API, verifies integrity, archives the data/files/checksums and encrypts the archive with authenticated AES-256-GCM. It never copies only an active WAL database file. Keep the random backup key separately and securely backed up; losing it makes the encrypted archive unrecoverable.

Examples run locally against an offline data directory; corresponding in-cluster maintenance/volume mounts must be reviewed during staged operation:

```sh
backend/.venv/bin/python scripts/backup-data.py backup \
  --data-dir data --archive backups/offline-snapshot.enc \
  --key-file private/deploy/backup.key --offline --execute

backend/.venv/bin/python scripts/backup-data.py restore \
  --archive backups/offline-snapshot.enc --target backups/isolated-restore \
  --key-file private/deploy/backup.key --execute
```

Without `--execute`, both commands only print a plan. Backups never overwrite an archive, restoration only accepts a new target directory, and authentication is verified before archive extraction. Existing application data is never replaced automatically. Test the restored application on an isolated volume before treating a backup as usable.

Rollback requires a previously recorded immutable publication tag and explicit confirmation that database/schema compatibility and backup recovery were checked:

```sh
k8s/scripts/rollback.sh --tag 1 --ack-schema-compatible --execute
```

It preserves the current Deployment configuration and changes only the selected container image and release annotation using compare-and-swap. It never restores/deletes a PVC, downgrades migrations automatically or assumes a failed Recreate rollout leaves an old pod running. If schema compatibility is uncertain, stop and prepare a separate recovery operation.

## Diagnosis

| Symptom | Check |
| --- | --- |
| Traefik 404 | Explicit context/namespace, Ingress class, hostname, route and entrypoints |
| Traefik 502 | Service selector/port, ready endpoints and application startup |
| Cloudflare 525/526 | Origin HTTPS listener and certificate requirements for the actual SSL mode |
| ImagePullBackOff | Exact immutable tag/digest, registry authentication and namespace-local pull Secret |
| Exec format error | Image platform must match the scheduled ARM64 node |
| Pending PVC | local-path provisioner, first consumer and node/storage availability |
| Upload rejection | Application byte/count limits and application-scoped edge limits |
| Stalled SSE | Edge cache/buffering/idle timeout; inspect durable run state before any retry |
| Lease conflict | Another release holds the lock; inspect expiry/holder, never delete blindly |
| Verification gate failure | Re-run local checks for the exact current source and inspect explicit release flags |

Public health is not evidence that credentials, authenticated access, backups or every model/provider are verified. Keep deployment status and remaining checks explicit.

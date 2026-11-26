# Library Management System: DevOps Platform

A small library application (books, members, loans) with the full path from commit to
production: CI/CD, containers, Kubernetes, Terraform, monitoring, logging, security,
canary releases and backups.

> **Status:** the application tests and a set of offline checks have run. The container
> image, Terraform, the Kubernetes deployment and the CI pipeline have **not** been run yet.
> Expect to fix a few things on the first run.

## Layout

| Path | Contents |
|---|---|
| `app/`, `tests/` | Flask API, web page, PostgreSQL schema, tests |
| `Dockerfile`, `docker-compose.yml` | Container image and local development |
| `.github/` | CI/CD pipeline, manual rollback, Dependabot |
| `infra/terraform/` | kind cluster, namespaces, secrets, Argo Rollouts |
| `k8s/base`, `k8s/overlays` | Application manifests, staging and production |
| `k8s/observability` | Prometheus, Grafana, Loki, Alloy |
| `scripts/` | Deploy, smoke test, backup, restore, drills |

## Prerequisites

Docker, [kind](https://kind.sigs.k8s.io/), kubectl, Terraform 1.9 or newer, Python 3.13,
curl, make, bash. About 4 CPUs and 8 GB of memory is a comfortable size (an estimate).

## 1. Run locally with Docker Compose

```bash
cp .env.example .env        # edit both values; use letters and digits only for the password
docker compose up --build   # http://localhost:8000
```

## 2. Run the tests

```bash
docker run -d --name testdb -p 5432:5432 -e POSTGRES_USER=library \
  -e POSTGRES_PASSWORD=library -e POSTGRES_DB=library_test postgres:17-alpine
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
make test lint
```

## 3. Run the whole platform on Kubernetes

Stop Compose first. Ports 8080 and 3000 must be free.

```bash
make up        # Terraform: cluster, namespaces, secrets, Argo Rollouts
make deploy    # build the image, load it, deploy app and monitoring
make smoke
```

| What | Where |
|---|---|
| Library | http://localhost:8080 |
| Grafana (user `admin`) | http://localhost:3000 |
| Prometheus and alerts | `kubectl -n observability port-forward svc/prometheus 9090` |

```bash
terraform -chdir=infra/terraform output -raw api_key            # for the librarian desk
terraform -chdir=infra/terraform output -raw grafana_password
```

Recovery drills:

```bash
make drill-rollback   # releases a broken version; it should be aborted automatically
make drill-restore    # writes a row, backs up, deletes it, restores it
make down             # remove the cluster (this deletes the data and backups)
```

## 4. Push to GitHub

```bash
cd library-devops-platform
git init -b main
git add .
git update-index --chmod=+x scripts/*.sh   # keeps scripts executable, also from Windows
git commit -m "Library management DevOps platform"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

The push starts the pipeline:

```
test + security  ->  build + image scan  ->  e2e on a throwaway cluster  ->  publish to GHCR
                                                                         ->  production (opt-in)
```

Recommended repository settings: protect `main`, require pull requests and passing checks.

## 5. Production deployment (opt-in)

The production job needs a Kubernetes cluster reachable from GitHub, with a network plugin
that enforces NetworkPolicy and a default StorageClass. Terraform here creates only the
local cluster, so prepare an existing one once:

```bash
for ns in library observability argo-rollouts; do kubectl create namespace $ns; done
kubectl label ns library observability pod-security.kubernetes.io/enforce=restricted
kubectl apply -n argo-rollouts \
  -f https://github.com/argoproj/argo-rollouts/releases/download/v1.10.1/install.yaml

DB=$(openssl rand -hex 24)
kubectl -n library create secret generic library-secrets \
  --from-literal=POSTGRES_PASSWORD=$DB \
  --from-literal=DATABASE_URL=postgresql://library:$DB@postgres:5432/library \
  --from-literal=API_KEY=$(openssl rand -hex 24)
kubectl -n observability create secret generic grafana-admin \
  --from-literal=password=$(openssl rand -hex 16)
```

Then in GitHub:

1. Create the environment `production` and add required reviewers.
2. Add the secret `KUBE_CONFIG` (use a limited service account, not a cluster admin).
3. Add the repository variable `DEPLOY_PRODUCTION` = `true`.
4. Make the GHCR package public, or add an image pull secret to the cluster.

Add TLS and an ingress or gateway in front of `service/library` before real users reach it.

**Rollback:** a failed canary reverts by itself. To go back to an older version, run the
`rollback` workflow with that version's commit SHA.

## API

Protected routes need the header `X-API-Key`.

| Method and path | Key | Purpose |
|---|---|---|
| `GET /api/books?q=` | no | Search the catalogue |
| `POST /api/books` | yes | `{isbn, title, author, copies}` |
| `GET`, `POST /api/members` | yes | `{name, email}` |
| `GET`, `POST /api/loans` | yes | `{book_id, member_id}` |
| `POST /api/loans/<id>/return` | yes | Return a book |
| `GET /healthz`, `GET /readyz` | no | Liveness and readiness |

## Known limits

- One PostgreSQL instance, so no database high availability.
- Backups stay inside the cluster. Copy them off-site for real use.
- Alerts appear in Prometheus but are not sent anywhere (no Alertmanager).
- A single shared API key, not individual librarian accounts.
- A canary with no traffic passes the error check.
- Rollback restores the application, not the database. Keep schema changes additive.
- Commit `infra/terraform/.terraform.lock.hcl` after your first `terraform init`.

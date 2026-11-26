IMAGE ?= library-app:local

.PHONY: test lint validate dev up deploy smoke drill-rollback drill-restore backup down

test:            ## needs PostgreSQL, see README
	pytest --cov=app
lint:
	ruff check . && bandit -q -r app && pip-audit -r requirements.txt
validate:        ## offline checks
	shellcheck scripts/*.sh
	promtool test rules k8s/observability/alerts.test.yml
dev:             ## app + database with Docker Compose
	docker compose up --build
up:              ## create the cluster and platform with Terraform
	terraform -chdir=infra/terraform init
	terraform -chdir=infra/terraform apply -auto-approve
	kind export kubeconfig --name library
deploy:          ## build, load into kind, deploy
	docker build -t $(IMAGE) --build-arg APP_VERSION=local-$$(date +%s) .
	kind load docker-image $(IMAGE) --name library
	./scripts/deploy.sh staging $(IMAGE)
smoke:
	./scripts/smoke-test.sh http://localhost:8080
drill-rollback:
	./scripts/drill-rollback.sh
drill-restore:
	./scripts/drill-restore.sh
backup:
	./scripts/backup.sh
down:
	terraform -chdir=infra/terraform destroy -auto-approve

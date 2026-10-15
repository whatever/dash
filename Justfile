set dotenv-load := false

mod docker 'Justfile.docker'

kube_context := "rancher-desktop"
namespace := "dash"
chart := "charts/dash"
rd_socket := env("HOME") / ".rd/docker.sock"
kubectl := "kubectl --context " + kube_context + " --namespace " + namespace

default:
    @just --list

build:
    @test -S {{rd_socket}} || { echo "start Rancher Desktop (dockerd runtime): {{rd_socket}} not found" >&2; exit 1; }
    DOCKER_HOST=unix://{{rd_socket}} docker build -t dash:local .

secrets:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p .local
    [ -f .local/id_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -C dash-agent -f .local/id_ed25519
    set -a
    [ -f .env ] && . ./.env
    set +a
    jq -n \
        --rawfile private .local/id_ed25519 \
        --rawfile public .local/id_ed25519.pub \
        'def v($k; d): (env[$k] // "") | if . == "" then d else . end;
        {secrets: {values: {
            "dash-bedrock": ({
            AWS_REGION: v("AWS_REGION"; "us-east-1"),
            AWS_DEFAULT_REGION: v("AWS_DEFAULT_REGION"; v("AWS_REGION"; "us-east-1")),
            AWS_ACCESS_KEY_ID: v("AWS_ACCESS_KEY_ID"; null),
            AWS_SECRET_ACCESS_KEY: v("AWS_SECRET_ACCESS_KEY"; null),
            AWS_SESSION_TOKEN: v("AWS_SESSION_TOKEN"; null)
        } | with_entries(select(.value != null))),
        "dash-agent-ssh": {PRIVATE_KEY: $private},
        "dash-sandbox-ssh": {PUBLIC_KEY: $public}
    }}}' > .local/secrets.json

up: build secrets
    helm upgrade \
        --install dash {{chart}} \
        --kube-context {{kube_context}} \
        --namespace {{namespace}} \
        --create-namespace \
        --values {{chart}}/values-local.yaml \
        --values .local/secrets.json \
        --wait --timeout 10m
    @echo "open http://dash.localhost"

reload: build
    {{kubectl}} rollout restart deploy/dash-api deploy/dash-worker
    {{kubectl}} rollout status deploy/dash-api deploy/dash-worker --timeout 5m

scrape:
    #!/usr/bin/env bash
    set -euo pipefail
    job=scrape-$(date +%s)
    {{kubectl}} create job --from=cronjob/dash-scrape "$job"
    {{kubectl}} logs --follow --pod-running-timeout=2m "job/$job"

down:
    helm uninstall dash --kube-context {{kube_context}} --namespace {{namespace}}

nuke:
    -helm uninstall dash --kube-context {{kube_context}} --namespace {{namespace}}
    kubectl --context {{kube_context}} delete namespace {{namespace}} --ignore-not-found

ps:
    {{kubectl}} get pods,pvc,ingress,cronjobs,jobs

[arg('follow', short='f', long='follow', value='--follow')]
logs app follow="":
    {{kubectl}} logs {{follow}} --all-containers --prefix deploy/{{app}}

browse:
    open http://dash.localhost

chart-lint:
    helm lint {{chart}}
    helm lint {{chart}} --values {{chart}}/values-local.yaml
    helm template dash {{chart}} --namespace {{namespace}} > /dev/null
    helm template dash {{chart}} --namespace {{namespace}} --values {{chart}}/values-local.yaml > /dev/null

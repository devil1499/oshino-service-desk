#!/usr/bin/env bash
set -euo pipefail
umask 077

release_dir=$(cd -- "$(dirname -- "$0")" && pwd)
deploy_dir=$(dirname "$(dirname "$release_dir")")
export SERVER_ENV_FILE="$deploy_dir/.env.server"
registry_user=$1
export BACKEND_IMAGE=$2
export FRONTEND_IMAGE=$3

if [[ ! -s "$SERVER_ENV_FILE" ]]; then
  printf 'Missing server configuration at %s\n' "$SERVER_ENV_FILE" >&2
  exit 1
fi

export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
docker login ghcr.io --username "$registry_user" --password-stdin >/dev/null

compose=(docker compose --env-file "$SERVER_ENV_FILE" -f "$release_dir/compose.yaml")
"${compose[@]}" config --quiet
"${compose[@]}" pull
"${compose[@]}" up -d --no-build --wait --wait-timeout 180
"${compose[@]}" exec -T frontend wget -q -O /dev/null http://127.0.0.1/
"${compose[@]}" exec -T frontend wget -q -O /dev/null http://127.0.0.1/api/health

printf 'BACKEND_IMAGE=%s\nFRONTEND_IMAGE=%s\n' "$BACKEND_IMAGE" "$FRONTEND_IMAGE" > "$release_dir/.images.env"
ln -sfn "$release_dir" "$deploy_dir/current"

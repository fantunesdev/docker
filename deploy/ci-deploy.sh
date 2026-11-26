#!/bin/sh
# Executado na VM por SSH. Recebe o token temporário GHCR pela entrada padrão.
set -eu
: "${DEPLOY_IMAGE:?Informe a imagem por digest}"
: "${DEPLOY_COMMIT:?Informe o SHA aprovado}"
: "${REGISTRY_USER:?Informe o usuário do registry}"
BASEDIR="${BASEDIR:-/docker/myfinance}"
DOCKER_CONFIG=$(mktemp -d)
export DOCKER_CONFIG
trap 'rm -rf "$DOCKER_CONFIG"' 0
trap 'exit 130' INT
trap 'exit 143' TERM
docker login ghcr.io -u "$REGISTRY_USER" --password-stdin
export BASEDIR DEPLOY_IMAGE DEPLOY_COMMIT
exec_status=0
"$BASEDIR/mfupdate" || exec_status=$?
exit "$exec_status"

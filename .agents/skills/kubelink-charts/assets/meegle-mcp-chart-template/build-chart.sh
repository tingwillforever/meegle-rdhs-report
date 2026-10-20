#!/usr/bin/env bash
set -euo pipefail

# Canonical meegle-mcp release flow. Replace only project-specific defaults.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${SCRIPT_DIR}"

OS_NAME=$(uname)
SERVICE_NAME="${SERVICE_NAME:-app}"
CHART_SOURCE_NAME="${CHART_SOURCE_NAME:-app}"
CHART_REPOSITORY="${CHART_REPOSITORY:-cbg-helm-local}"

for required_variable in PROJECT_VERSION BUILD_ID; do
  if [[ -z "${!required_variable:-}" ]]; then
    echo "error: ${required_variable} is not set" >&2
    exit 1
  fi
done

if [[ ! -d "./${CHART_SOURCE_NAME}" ]]; then
  echo "error: chart directory ./${CHART_SOURCE_NAME} does not exist" >&2
  exit 1
fi

VERSION="${PROJECT_VERSION}.${BUILD_ID}"
ENV="${ENV:-prod}"
ENV_VALUES_FILE="./${CHART_SOURCE_NAME}/values-${ENV}.yaml"
BUILD_DIR="${SERVICE_NAME}-${ENV}"

rm -rf "${BUILD_DIR}"
cp -R "${CHART_SOURCE_NAME}" "${BUILD_DIR}"

if [[ "${OS_NAME}" == "Darwin" ]]; then
  SED_INPLACE=(sed -i '')
else
  SED_INPLACE=(sed -i)
fi

"${SED_INPLACE[@]}" "s/^name: ${CHART_SOURCE_NAME}$/name: ${SERVICE_NAME}-${ENV}/" "${BUILD_DIR}/Chart.yaml"
"${SED_INPLACE[@]}" "s/^version: .*/version: ${VERSION}/" "${BUILD_DIR}/Chart.yaml"
"${SED_INPLACE[@]}" "s/^appVersion: .*/appVersion: \"${VERSION}\"/" "${BUILD_DIR}/Chart.yaml"
"${SED_INPLACE[@]}" -E "s/^([[:space:]]*tag:).*/\\1 \"${VERSION}\"/" "${BUILD_DIR}/values.yaml"

if [[ -f "${ENV_VALUES_FILE}" ]]; then
  "${SED_INPLACE[@]}" -E "s/^([[:space:]]*tag:).*/\\1 \"${VERSION}\"/" "${BUILD_DIR}/values-${ENV}.yaml"
  if [[ "${ENV}" == "prod" ]]; then
    cp "${BUILD_DIR}/values-${ENV}.yaml" "${BUILD_DIR}/values.yaml"
  fi
fi

helm lint "${BUILD_DIR}"

if ! helm push-artifactory "${BUILD_DIR}" "${CHART_REPOSITORY}" --skip-reindex; then
  echo "error: chart push failed" >&2
  exit 1
fi

echo "chart build and push completed: ${SERVICE_NAME}-${ENV} ${VERSION}"

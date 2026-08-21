#!/usr/bin/env bash
set -euo pipefail

# Build the versioned chart using the same release flow as meegle-mcp.
# The script is intentionally non-publishing by default; CI can set
# PUSH_CHART=true after the packaged chart has passed its release checks.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
SERVICE_NAME=${SERVICE_NAME:-meegle-rdhs-report}
ENV=${ENV:-prod}
PUSH_CHART=${PUSH_CHART:-false}
CHART_SOURCE="${SCRIPT_DIR}/rdhs-report"
BUILD_DIR="${SCRIPT_DIR}/${SERVICE_NAME}-${ENV}"
PACKAGE_DIR=${CHART_PACKAGE_DIR:-"${SCRIPT_DIR}/packages"}

: "${PROJECT_VERSION:?PROJECT_VERSION must be set, for example 1.0}"
: "${BUILD_ID:?BUILD_ID must be set, for example 42}"

VERSION="${PROJECT_VERSION}.${BUILD_ID}"
ENV_VALUES_FILE="${CHART_SOURCE}/values-${ENV}.yaml"
if [[ ! -f "${ENV_VALUES_FILE}" ]]; then
  ENV_VALUES_FILE="${CHART_SOURCE}/values-${ENV}.example.yaml"
fi

if [[ ! -d "${CHART_SOURCE}" ]]; then
  echo "Chart source does not exist: ${CHART_SOURCE}" >&2
  exit 1
fi

if [[ ! -f "${ENV_VALUES_FILE}" ]]; then
  echo "No environment values file found for ENV=${ENV}" >&2
  echo "Expected values-${ENV}.yaml or values-${ENV}.example.yaml under ${CHART_SOURCE}" >&2
  exit 1
fi

echo "Building ${SERVICE_NAME}-${ENV} ${VERSION} from ${REPO_ROOT}"
rm -rf "${BUILD_DIR}"
cp -R "${CHART_SOURCE}" "${BUILD_DIR}"

# Keep the source defaults as values.yaml and carry the selected environment
# file alongside it. Helm consumers can pass that file at install time, just
# as they do for the source chart.
ENV_VALUES_BASENAME=$(basename "${ENV_VALUES_FILE}")
cp "${ENV_VALUES_FILE}" "${BUILD_DIR}/${ENV_VALUES_BASENAME}"

# The source production values contain a placeholder immutable tag. Replace
# every image tag in the build copy with the release version for both images.
if command -v perl >/dev/null 2>&1; then
  for values_file in "${BUILD_DIR}/values.yaml" "${BUILD_DIR}/${ENV_VALUES_BASENAME}"; do
    perl -pi -e 's/^(\s+tag:)\s*.*$/$1 "'"${VERSION}"'"/' "${values_file}"
  done
else
  echo "perl is required to version image tags portably on macOS and Linux" >&2
  exit 1
fi

if command -v perl >/dev/null 2>&1; then
  perl -pi -e 's/^name:\s+.*/name: '"${SERVICE_NAME}"'-'"${ENV}"'/' "${BUILD_DIR}/Chart.yaml"
  perl -pi -e 's/^version:\s+.*/version: '"${VERSION}"'/' "${BUILD_DIR}/Chart.yaml"
  perl -pi -e 's/^appVersion:\s+.*/appVersion: "'"${VERSION}"'"/' "${BUILD_DIR}/Chart.yaml"
fi

helm lint "${BUILD_DIR}" -f "${BUILD_DIR}/${ENV_VALUES_BASENAME}"
mkdir -p "${PACKAGE_DIR}"
PACKAGE=$(helm package "${BUILD_DIR}" --destination "${PACKAGE_DIR}" | awk '{print $NF}')
echo "Packaged chart: ${PACKAGE}"

if [[ "${PUSH_CHART}" == "true" ]]; then
  if ! command -v helm >/dev/null 2>&1 || ! helm push-artifactory --help >/dev/null 2>&1; then
    echo "PUSH_CHART=true requires the helm push-artifactory plugin" >&2
    exit 1
  fi
  helm push-artifactory "${PACKAGE}" cbg-helm-local --skip-reindex
  echo "Published chart to cbg-helm-local: ${PACKAGE}"
else
  echo "Chart was not published (set PUSH_CHART=true to publish via helm push-artifactory)."
fi

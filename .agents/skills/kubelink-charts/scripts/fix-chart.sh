#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEMPLATE_DIR="${SCRIPT_DIR}/../assets/meegle-mcp-chart-template"
chart=""
values=""
confirmed=false
while (($#)); do
  case "$1" in
    --chart) chart=$2; shift 2 ;;
    --values) values=$2; shift 2 ;;
    --confirm) confirmed=true; shift ;;
    -h|--help)
      echo "Usage: fix-chart.sh --chart DIR [--values FILE] --confirm"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "${chart}" ]] || { echo "error: --chart is required" >&2; exit 2; }
[[ "${confirmed}" == true ]] || {
  echo "error: modification requires --confirm after a completed read-only audit" >&2
  exit 2
}
chart=$(cd "${chart}" && pwd)
if [[ -n "${values}" ]]; then
  values=$(cd "$(dirname "${values}")" && pwd)/$(basename "${values}")
else
  values="${chart}/values.yaml"
fi
[[ -f "${values}" ]] || { echo "error: values file does not exist: ${values}" >&2; exit 1; }

template_image_repository=$(sed -n '/^image:[[:space:]]*$/,/^[^[:space:]]/ { s/^[[:space:]]*repository:[[:space:]]*//p; }' "${TEMPLATE_DIR}/values.yaml" | head -1)
template_image_repository=${template_image_repository%\"}
template_image_repository=${template_image_repository#\"}
template_image_repository=${template_image_repository%\'}
template_image_repository=${template_image_repository#\'}
[[ "${template_image_repository}" == */* ]] || {
  echo "error: canonical template image.repository is missing or invalid" >&2
  exit 1
}
canonical_image_prefix="${template_image_repository%/*}/"

backup_root="${chart}/../.kubelink-charts-backup/$(date +%Y%m%d%H%M%S)"
mkdir -p "${backup_root}"
cp -R "${chart}" "${backup_root}/chart"
cp "${values}" "${backup_root}/values.yaml"

service_name=$(basename "${chart}")
for image_values in "${chart}/values.yaml" "${chart}/values-prod.yaml" "${chart}/values-prod.yaml.example"; do
  if [[ -f "${image_values}" ]]; then
    sed -i.bak -E "s#^(  repository: ).*#\1${canonical_image_prefix}${service_name}#" "${image_values}"
    rm -f "${image_values}.bak"
  fi
done

template_text=$(find "${chart}/templates" -maxdepth 1 -type f -print -exec cat {} \;)
if grep -qE '\.Values\.(secrets|imagePullSecrets)' <<<"${template_text}" && ! grep -qE '^secrets:' "${values}"; then
  cat >>"${values}" <<'EOF'

# Added by kubelink-charts: optional Secret mode is disabled by default.
secrets:
  create: false
EOF
fi
if ! grep -qE '^imagePullSecrets:' "${values}"; then
  cat >>"${values}" <<'EOF'

# Added by kubelink-charts: set the private registry pull Secret when needed.
imagePullSecrets: []
EOF
fi

# Keep the configuration closure in sync after explicit confirmation. Secret
# values are copied only into the selected production values file; the default
# values.yaml remains secret-free.
project_root=$(cd "${chart}/../.." && pwd)
inventory_file=$(mktemp)
trap 'rm -f "${inventory_file}"' EXIT
python3 "${SCRIPT_DIR}/inventory-config.py" "${project_root}" --include-secret-values --output "${inventory_file}"
python3 "${SCRIPT_DIR}/populate_values.py" --values "${chart}/values.yaml" --inventory "${inventory_file}"
production_values="${values}"
if [[ "${production_values}" == "${chart}/values.yaml" && -f "${chart}/values-prod.yaml" ]]; then
  production_values="${chart}/values-prod.yaml"
fi
if [[ "${production_values}" != "${chart}/values.yaml" && -f "${production_values}" ]]; then
  python3 "${SCRIPT_DIR}/populate_values.py" --values "${production_values}" --inventory "${inventory_file}" --include-secret-values
fi

echo "safe chart fixes applied"
echo "backup: ${backup_root}"
echo "review diff; no git commit or push performed"

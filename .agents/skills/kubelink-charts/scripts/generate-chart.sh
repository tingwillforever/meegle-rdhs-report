#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TEMPLATE_DIR="${SCRIPT_DIR}/../assets/meegle-mcp-chart-template"
inventory_file=$(mktemp)
trap 'rm -f "${inventory_file}"' EXIT

project_root=""
output=""
service_name=""
image_repository=""
confirmed=false
force=false

usage() {
  cat <<'EOF'
Usage: generate-chart.sh --project-root DIR --output DIR [options]

Options:
  --service-name NAME       Chart/service name; defaults to project directory name
  --image-repository IMAGE  Known image repository to put in values files
  --confirm                 Confirm generation after a completed read-only audit
  --force                   Replace an existing output directory
EOF
}

while (($#)); do
  case "$1" in
    --project-root) project_root=$2; shift 2 ;;
    --output) output=$2; shift 2 ;;
    --service-name) service_name=$2; shift 2 ;;
    --image-repository) image_repository=$2; shift 2 ;;
    --confirm) confirmed=true; shift ;;
    --force) force=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "${project_root}" && -n "${output}" ]] || { usage >&2; exit 2; }
[[ "${confirmed}" == true ]] || {
  echo "error: generation requires --confirm after a completed read-only audit" >&2
  exit 2
}
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
if [[ -n "${image_repository}" && "${image_repository}" != "${canonical_image_prefix}"* ]]; then
  echo "error: image repository must use canonical prefix ${canonical_image_prefix}" >&2
  exit 1
fi
project_root=$(cd "${project_root}" && pwd)
if [[ -z "${service_name}" ]]; then
  service_name=$(basename "${project_root}" | tr '[:upper:]_' '[:lower:]-' | sed -E 's/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//')
fi
[[ -n "${service_name}" ]] || { echo "error: cannot derive service name" >&2; exit 1; }

if [[ -e "${output}" ]]; then
  if [[ "${force}" != true ]]; then
    echo "error: output exists; pass --force to replace it: ${output}" >&2
    exit 1
  fi
  rm -rf "${output}"
fi

mkdir -p "$(dirname "${output}")"
cp -R "${TEMPLATE_DIR}" "${output}"

find "${output}" -type f -print0 | xargs -0 sed -i.bak \
  -e "s/define \"app\./define \"${service_name}./g" \
  -e "s/include \"app\./include \"${service_name}./g"
find "${output}" -name '*.bak' -delete

sed -i.bak "s/^name: app$/name: ${service_name}/" "${output}/Chart.yaml"
sed -i.bak -E "s#^(  repository: ).*#\1${canonical_image_prefix}${service_name}#" "${output}/values.yaml"
sed -i.bak -E "s#^(  repository: ).*#\1${canonical_image_prefix}${service_name}#" "${output}/values-prod.yaml.example"
sed -i.bak "s#path: /app#path: /${service_name}#" "${output}/values-prod.yaml.example"
rm -f "${output}/Chart.yaml.bak" "${output}/values.yaml.bak" "${output}/values-prod.yaml.example.bak"

if [[ -n "${image_repository}" ]]; then
  sed -i.bak "0,/repository:.*/s#repository:.*#repository: ${image_repository}#" "${output}/values.yaml"
  sed -i.bak "0,/repository:.*/s#repository:.*#repository: ${image_repository}#" "${output}/values-prod.yaml.example"
  rm -f "${output}/values.yaml.bak" "${output}/values-prod.yaml.example.bak"
fi

if [[ ! -f "${output}/values-prod.yaml" ]]; then
  cp "${output}/values-prod.yaml.example" "${output}/values-prod.yaml"
fi

python3 "${SCRIPT_DIR}/inventory-config.py" "${project_root}" --include-secret-values --output "${inventory_file}"
python3 "${SCRIPT_DIR}/populate_values.py" --values "${output}/values.yaml" --inventory "${inventory_file}"
python3 "${SCRIPT_DIR}/populate_values.py" --values "${output}/values-prod.yaml" --inventory "${inventory_file}" --include-secret-values

dockerfile=$(find "${project_root}" -maxdepth 1 -name 'Dockerfile*' -type f -print -quit)
if [[ -n "${dockerfile}" ]]; then
  detected_port=$(sed -nE 's/^EXPOSE[[:space:]]+([0-9]+).*$/\1/p' "${dockerfile}" | head -1)
  if [[ -n "${detected_port}" ]]; then
    sed -i.bak -E "s/^  port: [0-9]+/  port: ${detected_port}/; s/^  targetPort: [0-9]+/  targetPort: ${detected_port}/" "${output}/values.yaml"
    sed -i.bak -E "s/^  port: [0-9]+/  port: ${detected_port}/; s/^  targetPort: [0-9]+/  targetPort: ${detected_port}/" "${output}/values-prod.yaml"
    rm -f "${output}/values.yaml.bak" "${output}/values-prod.yaml.bak"
  fi
fi

chmod +x "${output}/build-chart.sh"
echo "generated Chart scaffold: ${output}"
echo "next: configure values.yaml and values-prod.yaml, then run audit-chart.sh"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
fixture=$(mktemp -d)
trap 'rm -rf "${fixture}"' EXIT

mkdir -p "${fixture}/charts/demo"
cp -R "${SKILL_ROOT}/assets/meegle-mcp-chart-template/." "${fixture}/charts/demo/"
cp "${fixture}/charts/demo/values.yaml" "${fixture}/charts/demo/values-prod.yaml"
sed -i.bak -E 's#^(  repository: ).*#\1registry.example.invalid/team/demo#' "${fixture}/charts/demo/values.yaml" "${fixture}/charts/demo/values-prod.yaml"
rm -f "${fixture}/charts/demo/values.yaml.bak" "${fixture}/charts/demo/values-prod.yaml.bak"
printf '%s\n' 'OPENAI_API_KEY=fixture-secret-value' > "${fixture}/.env.local"

if "${SKILL_ROOT}/scripts/fix-chart.sh" --chart "${fixture}/charts/demo" >/dev/null 2>&1; then
  echo "fix-chart.sh must reject modification without --confirm" >&2
  exit 1
fi
[[ ! -d "${fixture}/charts/.kubelink-charts-backup" ]]

if "${SKILL_ROOT}/scripts/generate-chart.sh" \
  --project-root "${fixture}" \
  --output "${fixture}/charts/generated" >/dev/null 2>&1; then
  echo "generate-chart.sh must reject generation without --confirm" >&2
  exit 1
fi
[[ ! -e "${fixture}/charts/generated" ]]

if "${SKILL_ROOT}/scripts/generate-chart.sh" \
  --project-root "${fixture}" \
  --output "${fixture}/charts/noncanonical" \
  --image-repository registry.example.invalid/team/demo \
  --confirm >/dev/null 2>&1; then
  echo "generate-chart.sh must reject a non-canonical image prefix" >&2
  exit 1
fi
[[ ! -e "${fixture}/charts/noncanonical" ]]

"${SKILL_ROOT}/scripts/fix-chart.sh" \
  --chart "${fixture}/charts/demo" \
  --confirm >/dev/null
[[ -d "${fixture}/charts/.kubelink-charts-backup" ]]
grep -q 'artifacts.iflytek.com/cbg-docker-repo/cbbywkf/demo' "${fixture}/charts/demo/values.yaml"
grep -q 'artifacts.iflytek.com/cbg-docker-repo/cbbywkf/demo' "${fixture}/charts/demo/values-prod.yaml"
grep -q 'OPENAI_API_KEY: "fixture-secret-value"' "${fixture}/charts/demo/values-prod.yaml"
! grep -q 'fixture-secret-value' "${fixture}/charts/demo/values.yaml"

"${SKILL_ROOT}/scripts/generate-chart.sh" \
  --project-root "${fixture}" \
  --output "${fixture}/charts/generated" \
  --service-name demo-generated \
  --confirm >/dev/null
[[ -f "${fixture}/charts/generated/Chart.yaml" ]]
grep -q 'artifacts.iflytek.com/cbg-docker-repo/cbbywkf/demo-generated' "${fixture}/charts/generated/values.yaml"
grep -q 'OPENAI_API_KEY: "fixture-secret-value"' "${fixture}/charts/generated/values-prod.yaml"
! grep -q 'fixture-secret-value' "${fixture}/charts/generated/values.yaml"

echo "change gate checks passed"

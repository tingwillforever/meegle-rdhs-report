#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
TEMPLATE_DIR="${SKILL_ROOT}/assets/meegle-mcp-chart-template"
fixture=$(mktemp -d)
trap 'rm -rf "${fixture}"' EXIT

mkdir -p "${fixture}/charts/demo"
cp -R "${TEMPLATE_DIR}/." "${fixture}/charts/demo/"
cat >"${fixture}/Dockerfile" <<'EOF'
FROM node:22
ENV IMAGE_DEFAULT=stable
EOF
cat >"${fixture}/.env" <<'EOF'
APP_REQUIRED=from-local-config
APP_TOKEN=local-secret-value
EOF
python3 - "${fixture}/charts/demo/values.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
p.write_text(p.read_text().replace("env:\n", 'env:\n  APP_REQUIRED: "from-values"\n  APP_TOKEN: "placeholder-token"\n', 1))
PY
cp "${fixture}/charts/demo/values.yaml" "${fixture}/charts/demo/values-prod.yaml"
python3 - "${fixture}/charts/demo/values-prod.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
p.write_text("\n".join(line for line in p.read_text().splitlines() if "APP_REQUIRED" not in line) + "\n")
PY

inventory=$(python3 "${SKILL_ROOT}/scripts/inventory-config.py" "${fixture}")
grep -q '"APP_REQUIRED"' <<<"${inventory}"
grep -q '"APP_TOKEN"' <<<"${inventory}"
! grep -q 'local-secret-value' <<<"${inventory}"

if "${SKILL_ROOT}/scripts/audit-chart.sh" \
  --project-root "${fixture}" \
  --chart charts/demo \
  --values charts/demo/values-prod.yaml \
  --kube-version 1.15.12 \
  --strict; then
  echo "expected strict audit to detect missing production configuration" >&2
  exit 1
fi

python3 - "${fixture}/charts/demo/values-prod.yaml" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
p.write_text(p.read_text().replace("env:\n", 'env:\n  APP_REQUIRED: "from-values"\n', 1))
PY
"${SKILL_ROOT}/scripts/audit-chart.sh" \
  --project-root "${fixture}" \
  --chart charts/demo \
  --values charts/demo/values-prod.yaml \
  --kube-version 1.15.12 >/dev/null

echo "config closure checks passed"

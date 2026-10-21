#!/usr/bin/env bash
# 把 rdhs skill 事实源单向同步到公开分发渠道，并校验本机软链方向。
#
# 用法：
#   ./scripts/sync-rdhs-skill.sh --dry-run
#   ./scripts/sync-rdhs-skill.sh
#
# 事实源：本仓 .agents/skills/meegle-rdhs-diagnosis
# 分发渠道：$RDP_SKILL_CHANNEL/skills/meegle-rdhs-diagnosis（默认 ~/Develop/meegle-skills）
#
# 这条链路只属于应用层；基础设施 skill（meegle-cli / meegle-mcp）由 meegle-infra
# 自己的 sync-public-skill.sh 负责，两边互不调用。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${REPO_ROOT}/.agents/skills/meegle-rdhs-diagnosis"
CHANNEL="${RDP_SKILL_CHANNEL:-${HOME}/Develop/meegle-skills}"
DEST="${CHANNEL}/skills/meegle-rdhs-diagnosis"
LINK="${HOME}/.agents/skills/meegle-rdhs-diagnosis"

DRY=()
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY=(--dry-run)
elif [[ $# -gt 0 ]]; then
  echo "Unknown option: $1" >&2
  exit 2
fi

[[ -f "${SRC}/SKILL.md" ]] || { echo "FAIL source missing: ${SRC}/SKILL.md" >&2; exit 1; }
[[ -d "${CHANNEL}/skills" ]] || { echo "FAIL channel layout missing: ${CHANNEL}/skills" >&2; exit 1; }

# --delete-excluded 让被排除的 __pycache__ / .DS_Store 也从渠道侧清掉，避免把字节码发布出去。
rsync -a --delete --delete-excluded \
  --exclude '__pycache__' --exclude '.DS_Store' \
  "${DRY[@]+${DRY[@]}}" "${SRC}/" "${DEST}/"

if [[ ! -L "${LINK}" ]]; then
  echo "FAIL runtime link missing or not a symlink: ${LINK}" >&2
  exit 1
fi

ACTUAL="$(readlink "${LINK}")"
if [[ "${ACTUAL}" != "${SRC}" ]]; then
  echo "FAIL runtime link points at ${ACTUAL}" >&2
  echo "     expected ${SRC}" >&2
  exit 1
fi

echo "rdhs skill in sync: ${SRC} -> ${DEST}${DRY:+ (dry run, nothing written)}"

#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mode="${1:-weekly}"

if [[ "$mode" != "monthly" && "$mode" != "weekly" ]]; then
  echo "Usage: $0 [monthly|weekly]" >&2
  exit 2
fi

env_file="${RDHS_SYNC_ENV:-$site_root/.env.sync}"
if [[ -f "$env_file" ]]; then
  set -a
  source "$env_file"
  set +a
fi

select_python() {
  local candidate resolved
  if [[ -n "${RDHS_PYTHON_BIN:-}" ]]; then
    printf '%s\n' "$RDHS_PYTHON_BIN"
    return 0
  fi

  for candidate in \
    "/opt/homebrew/bin/python3" \
    "/opt/homebrew/opt/python@3.14/bin/python3.14" \
    python3 \
    "$HOME/.local/bin/python3.13" \
    "$HOME/.local/bin/python3.12"; do
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    if [[ -n "$resolved" ]] && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  command -v python3
}

python_bin="$(select_python)"

# 1. 抓取数据并导出快照 JSON 到 data/snapshots/
echo "==> [1/2] 正在运行 RDHS $mode 数据同步..."
mkdir -p "$site_root/data/snapshots"
"$python_bin" "$site_root/scripts/sync-rdhs-to-pages.py" --mode "$mode"

# 2. 自动打包并发布至 GitHub Pages
echo "==> [2/2] 正在自动编译并发布至 GitHub Pages..."
if [[ "${RDHS_NO_DEPLOY:-0}" != "1" ]]; then
  bash "$site_root/scripts/deploy-to-github-pages.sh"
else
  echo "==> RDHS_NO_DEPLOY=1, 跳过自动发布。"
fi

echo "==> RDHS $mode 任务全流程执行完成。"

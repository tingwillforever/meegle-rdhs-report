#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cadence="${1:-monthly}"
if [[ "$cadence" != "monthly" ]]; then
  echo "cadence must be monthly" >&2
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
    candidate="$RDHS_PYTHON_BIN"
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      printf '%s\n' "$candidate"
      return 0
    fi
    echo "RDHS_PYTHON_BIN must point to Python 3.10 or newer" >&2
    return 1
  fi

  for candidate in \
    "$HOME/.local/bin/python3.13" \
    "$HOME/.local/bin/python3.12" \
    "$HOME/.local/bin/python3.11" \
    python3; do
    resolved="$(command -v "$candidate" 2>/dev/null || true)"
    if [[ -n "$resolved" ]] && "$resolved" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      printf '%s\n' "$resolved"
      return 0
    fi
  done
  echo "Python 3.10 or newer is required for RDHS synchronization" >&2
  return 1
}

python_bin="$(select_python)"

# 1. 导出快照到本地 data/snapshots
echo "==> Running RDHS monthly sync and exporting to data/snapshots..."
mkdir -p "$site_root/data/snapshots"

sync_args=(
  "$site_root/scripts/sync-rdhs-snapshot.py"
  --cadence "$cadence"
  --export-dir "$site_root/data/snapshots"
)

# 保留旧内网上传兼容（若提供了凭据则继续上传，实现双轨支持）
if [[ -n "${RDHS_SITE_URL:-}" && -n "${RDHS_INGEST_TOKEN:-}" ]]; then
  sync_args+=(--site-url "$RDHS_SITE_URL" --token "$RDHS_INGEST_TOKEN")
else
  sync_args+=(--no-upload)
fi

"$python_bin" "${sync_args[@]}"

# 2. 如果检测到新快照文件，自动 commit 并推送
cd "$site_root"
if [[ -n "$(git status -s data/snapshots/)" ]]; then
  echo "==> Detected new or updated snapshot files in data/snapshots/:"
  git status -s data/snapshots/
  
  if [[ "${RDHS_NO_GIT_PUSH:-0}" != "1" ]]; then
    git add data/snapshots/
    current_month="$(date +%Y-%m)"
    git commit -m "chore(data): auto-sync monthly snapshot for $current_month"
    echo "==> Pushing to git remote..."
    git push origin "$(git branch --show-current)" || {
      echo "WARN: git push failed or credentials required. Please push manually." >&2
    }
  else
    echo "==> RDHS_NO_GIT_PUSH is enabled. Skipped git commit & push."
  fi
else
  echo "==> No changes in data/snapshots/. Snapshots are already up to date."
fi

echo "==> Monthly sync job finished successfully."

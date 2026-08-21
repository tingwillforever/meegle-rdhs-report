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
elif [[ -z "${RDHS_SITE_URL:-}" || -z "${RDHS_INGEST_TOKEN:-}" ]]; then
  echo "RDHS sync environment not found: $env_file" >&2
  exit 1
fi
: "${RDHS_SITE_URL:?RDHS_SITE_URL is required}"
: "${RDHS_INGEST_TOKEN:?RDHS_INGEST_TOKEN is required}"

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
exec "$python_bin" "$site_root/scripts/sync-rdhs-snapshot.py" --cadence "$cadence"

#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cadence="${1:-}"
if [[ "$cadence" != "weekly" && "$cadence" != "monthly" ]]; then
  echo "cadence must be weekly or monthly" >&2
  exit 2
fi

env_file="${RDHS_SYNC_ENV:-$site_root/.env.sync}"
if [[ ! -f "$env_file" ]]; then
  echo "RDHS sync environment not found: $env_file" >&2
  exit 1
fi

set -a
source "$env_file"
set +a
: "${RDHS_SITE_URL:?RDHS_SITE_URL is required}"
: "${RDHS_INGEST_TOKEN:?RDHS_INGEST_TOKEN is required}"

python_bin="${RDHS_PYTHON_BIN:-$(command -v python3)}"
exec "$python_bin" "$site_root/scripts/sync-rdhs-snapshot.py" --cadence "$cadence"

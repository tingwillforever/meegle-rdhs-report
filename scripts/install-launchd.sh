#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${RDHS_PYTHON_BIN:-$(command -v python3)}"
launch_agents="$HOME/Library/LaunchAgents"
mkdir -p "$launch_agents"

write_plist() {
  local label="$1"
  local cadence="$2"
  local weekday="$3"
  local day="$4"
  local target="$launch_agents/$label.plist"
  cat >"$target" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
    <string>$python_bin</string>
    <string>$site_root/scripts/sync-rdhs-snapshot.py</string>
    <string>--cadence</string><string>$cadence</string>
  </array>
  <key>WorkingDirectory</key><string>$site_root</string>
  <key>StartCalendarInterval</key><dict>
    ${weekday:+<key>Weekday</key><integer>$weekday</integer>}
    ${day:+<key>Day</key><integer>$day</integer>}
    <key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>$site_root/runtime/sync.log</string>
  <key>StandardErrorPath</key><string>$site_root/runtime/sync-error.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$target"
}

mkdir -p "$site_root/runtime"
write_plist "com.rdhs.operations.weekly" "weekly" "2" ""
write_plist "com.rdhs.operations.monthly" "monthly" "" "1"
echo "RDHS weekly and monthly synchronization jobs installed."


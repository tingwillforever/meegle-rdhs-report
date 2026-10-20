#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
launch_agents="$HOME/Library/LaunchAgents"
mkdir -p "$launch_agents" "$site_root/runtime"

write_plist() {
  local label="$1"
  local day="$2"
  local target="$launch_agents/$label.plist"
  cat >"$target" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array>
    <string>/bin/bash</string>
    <string>$site_root/scripts/run-sync-job.sh</string>
    <string>monthly</string>
  </array>
  <key>WorkingDirectory</key><string>$site_root</string>
  <key>StartCalendarInterval</key><dict>
    ${day:+<key>Day</key><integer>$day</integer>}
    <key>Hour</key><integer>9</integer><key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>$site_root/runtime/sync-monthly.log</string>
  <key>StandardErrorPath</key><string>$site_root/runtime/sync-monthly-error.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$target"
}

write_plist "com.rdhs.operations.monthly" "1"
echo "RDHS monthly synchronization job installed."

#!/bin/bash
# Install (or reinstall) a macOS launchd job that runs scripts/run_paper.sh at 08:15 and 18:15 local time.
# If the Mac is asleep at a scheduled time, launchd runs the job once when it wakes.
# Uninstall: launchctl bootout gui/$(id -u)/com.tempmarkets.paper && rm ~/Library/LaunchAgents/com.tempmarkets.paper.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL=com.tempmarkets.paper
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
chmod +x "$REPO/scripts/run_paper.sh"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$REPO/scripts/run_paper.sh</string></array>
  <key>StartCalendarInterval</key>
  <array>
    <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>15</integer></dict>
    <dict><key>Hour</key><integer>18</integer><key>Minute</key><integer>15</integer></dict>
  </array>
  <key>StandardOutPath</key><string>$REPO/data/paper_launchd.log</string>
  <key>StandardErrorPath</key><string>$REPO/data/paper_launchd.log</string>
</dict>
</plist>
EOF
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed $LABEL -> $PLIST"
launchctl print "gui/$(id -u)/$LABEL" | grep -E "state|path" | head -5

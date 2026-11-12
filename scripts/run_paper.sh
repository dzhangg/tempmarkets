#!/bin/bash
# One paper-log cycle: snapshot live books + forecast, then settle resolved paper trades.
# READ-ONLY: GET requests only; appends to paper_log/. Invoked by launchd (see install_schedule.sh).
set -u
cd "$(dirname "$0")/.." || exit 1
LOG=data/paper_job.log
mkdir -p data
{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S %Z') ==="
  .venv/bin/python -W ignore scripts/paper_snapshot.py
  .venv/bin/python -W ignore scripts/paper_settle.py
  echo "exit: $?"
} >> "$LOG" 2>&1

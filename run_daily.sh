#!/usr/bin/env bash
# Daily runner. Point cron or Task Scheduler at this file.
# No API key needed - the default source is free and keyless.
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p logs
STAMP="$(date +%Y-%m-%d)"
python3 run.py >> "logs/run-$STAMP.log" 2>&1
echo "finished $(date)" >> "logs/run-$STAMP.log"

# Uncomment to auto-open the report on a desktop machine:
# xdg-open "out/leads-$STAMP.html" 2>/dev/null || open "out/leads-$STAMP.html"

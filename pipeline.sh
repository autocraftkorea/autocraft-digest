#!/bin/bash
set -e

BASE="/Users/syedjafferhussain/autocraft"
VENV="$BASE/venv/bin/python3"
LOG="$BASE/pipeline.log"
DATE=$(date "+%Y-%m-%d %H:%M:%S")

echo "==============================" >> "$LOG"
echo "Pipeline started: $DATE" >> "$LOG"

cd "$BASE"

# Load credentials
source ~/.zshrc

echo "Step 1/4: Normalising auction data..." >> "$LOG"
$VENV "$BASE/normalize.py" >> "$LOG" 2>&1

echo "Step 2/4: Running match engine..." >> "$LOG"
$VENV "$BASE/match.py" >> "$LOG" 2>&1

echo "Step 3/4: Rendering digest..." >> "$LOG"
$VENV "$BASE/digest.py" >> "$LOG" 2>&1

echo "Step 4/4: Publishing and sending email..." >> "$LOG"
$VENV "$BASE/send.py" >> "$LOG" 2>&1

echo "Pipeline completed: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "==============================" >> "$LOG"
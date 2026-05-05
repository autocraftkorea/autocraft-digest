#!/bin/zsh
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

echo "Step 1/6: Fetching K-Car listing IDs..." >> "$LOG"
set +e
$VENV "$BASE/fetch_kcar_ids.py" >> "$LOG" 2>&1
KCAR_IDS_RC=$?
set -e
if [ $KCAR_IDS_RC -ne 0 ]; then
    echo "  fetch_kcar_ids.py exited with $KCAR_IDS_RC — continuing with fallback URLs" >> "$LOG"
fi

echo "Step 2/6: Fetching Autohub listing IDs..." >> "$LOG"
set +e
$VENV "$BASE/fetch_autohub_ids.py" >> "$LOG" 2>&1
AUTOHUB_IDS_RC=$?
set -e
if [ $AUTOHUB_IDS_RC -ne 0 ]; then
    echo "  fetch_autohub_ids.py exited with $AUTOHUB_IDS_RC — continuing with fallback URLs" >> "$LOG"
fi

echo "Step 3/6: Normalising auction data..." >> "$LOG"
$VENV "$BASE/normalize.py" >> "$LOG" 2>&1

echo "Step 4/6: Running match engine..." >> "$LOG"
$VENV "$BASE/match.py" >> "$LOG" 2>&1

echo "Step 5/6: Rendering digest..." >> "$LOG"
$VENV "$BASE/digest.py" >> "$LOG" 2>&1

echo "Step 6/6: Publishing and sending email..." >> "$LOG"
$VENV "$BASE/send.py" >> "$LOG" 2>&1

echo "Pipeline completed: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "==============================" >> "$LOG"
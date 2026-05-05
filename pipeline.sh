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

echo "Step 1/5: Fetching K-Car CAR_ID/AUC_CD mappings..." >> "$LOG"
set +e
$VENV "$BASE/fetch_kcar_ids.py" >> "$LOG" 2>&1
KCAR_IDS_RC=$?
set -e
if [ $KCAR_IDS_RC -ne 0 ]; then
    echo "  fetch_kcar_ids.py exited with $KCAR_IDS_RC — continuing with fallback URLs" >> "$LOG"
fi

echo "Step 2/5: Normalising auction data..." >> "$LOG"
$VENV "$BASE/normalize.py" >> "$LOG" 2>&1

echo "Step 3/5: Running match engine..." >> "$LOG"
$VENV "$BASE/match.py" >> "$LOG" 2>&1

echo "Step 4/5: Rendering digest..." >> "$LOG"
$VENV "$BASE/digest.py" >> "$LOG" 2>&1

echo "Step 5/5: Publishing and sending email..." >> "$LOG"
$VENV "$BASE/send.py" >> "$LOG" 2>&1

echo "Pipeline completed: $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
echo "==============================" >> "$LOG"
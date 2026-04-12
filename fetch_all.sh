#!/usr/bin/env bash
# fetch_all.sh — Run both auction scrapers then hand off to pipeline.sh
#
# Designed to be called from cron BEFORE pipeline.sh, or inserted at the
# top of your existing pipeline.sh.
#
# Cron example (Mon/Wed 20:30 UTC — 30 min before pipeline at 21:00):
#   30 20 * * 1,3 /bin/zsh -lc 'cd ~/autocraft && bash fetch_all.sh >> logs/fetch_all.log 2>&1'

set -euo pipefail

AUTOCRAFT="$HOME/autocraft"
VENV="$AUTOCRAFT/venv"
SCRIPTS="$AUTOCRAFT"          # adjust if scripts live in a subdirectory
LOG_DIR="$AUTOCRAFT/logs"
TODAY=$(date +%Y-%m-%d)

mkdir -p "$LOG_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# ── Activate venv ────────────────────────────────────────────────────────────
if [[ ! -f "$VENV/bin/activate" ]]; then
    log "ERROR: venv not found at $VENV"
    exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
log "Activated venv: $VENV"

# ── Install / verify Playwright is available ─────────────────────────────────
if ! python -c "import playwright" 2>/dev/null; then
    log "Installing playwright…"
    pip install playwright --quiet
    playwright install chromium
fi

# ── K-Car ────────────────────────────────────────────────────────────────────
log "=== Fetching K-Car (kcarauction.com) ==="
if python "$SCRIPTS/fetch_kcar.py" --date "$TODAY"; then
    log "✓ K-Car download complete"
    KCAR_OK=1
else
    log "✗ K-Car download FAILED (exit $?)"
    KCAR_OK=0
fi

# ── Autohub ───────────────────────────────────────────────────────────────────
log "=== Fetching Autohub (sellcarauction.co.kr) ==="
if python "$SCRIPTS/fetch_autohub.py" --date "$TODAY"; then
    log "✓ Autohub download complete"
    AUTOHUB_OK=1
else
    log "✗ Autohub download FAILED (exit $?)"
    AUTOHUB_OK=0
fi

# ── Gate: abort pipeline if both sources failed ───────────────────────────────
if [[ "$KCAR_OK" -eq 0 && "$AUTOHUB_OK" -eq 0 ]]; then
    log "ERROR: Both sources failed — aborting pipeline."
    exit 1
fi

if [[ "$KCAR_OK" -eq 0 ]]; then
    log "WARNING: K-Car failed but Autohub succeeded — pipeline will run with partial data."
fi

if [[ "$AUTOHUB_OK" -eq 0 ]]; then
    log "WARNING: Autohub failed but K-Car succeeded — pipeline will run with partial data."
fi

log "=== Handing off to pipeline.sh ==="
exec bash "$AUTOCRAFT/pipeline.sh"

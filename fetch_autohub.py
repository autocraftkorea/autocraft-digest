#!/usr/bin/env python3
"""
fetch_autohub.py — Download weekly Excel export from sellcarauction.co.kr
Source filename pattern: 출품리스트_YYYY-MM-DD.xlsx
Saves to:               ~/autocraft/data/autohub_YYYY-MM-DD.xlsx

Usage:
    python fetch_autohub.py [--date YYYY-MM-DD] [--headless/--no-headless]

Credentials (required in environment):
    AUTOHUB_USERNAME
    AUTOHUB_PASSWORD
"""

import os
import sys
import re
import time
import shutil
import logging
import argparse
import tempfile
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

# ── Config ────────────────────────────────────────────────────────────────────
LOGIN_URL   = "https://www.sellcarauction.co.kr/member/login"
LIST_URL    = "https://www.sellcarauction.co.kr/auction/list"
DATA_DIR    = Path.home() / "autocraft" / "data"
LOG_DIR     = Path.home() / "autocraft" / "logs"
TIMEOUT_MS  = 30_000
NAV_TIMEOUT = 60_000

# Expected source filename pattern  (날짜 부분은 무시하고 prefix 만 매칭)
FILENAME_PREFIX = "출품리스트"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "fetch_autohub.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser(description="Download Autohub auction Excel")
    p.add_argument("--date", default=str(date.today()),
                   help="Export date label YYYY-MM-DD (default: today)")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction,
                   default=True, help="Run browser headless (default: True)")
    p.add_argument("--retries", type=int, default=3,
                   help="Number of download attempts (default: 3)")
    return p.parse_args()


def get_credentials():
    username = os.environ.get("AUTOHUB_USERNAME")
    password = os.environ.get("AUTOHUB_PASSWORD")
    if not username or not password:
        log.error("AUTOHUB_USERNAME / AUTOHUB_PASSWORD not set. Add to ~/.zshrc and re-source.")
        sys.exit(1)
    return username, password


def run(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    username, password = get_credentials()
    target_path = DATA_DIR / f"autohub_{args.date}.xlsx"

    if target_path.exists():
        log.info("Output already exists: %s — skipping download.", target_path)
        return str(target_path)

    with tempfile.TemporaryDirectory() as tmp_dir:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=args.headless,
                args=["--lang=ko-KR"],
            )
            context = browser.new_context(
                accept_downloads=True,
                locale="ko-KR",
                timezone_id="Asia/Seoul",
                
                viewport={"width": 1280, "height": 900},
            )
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            page.set_default_navigation_timeout(NAV_TIMEOUT)

            try:
                # ── Login ──────────────────────────────────────────────────
                log.info("Navigating to login page…")
                page.goto(LOGIN_URL, wait_until="domcontentloaded")

                # Username
                for sel in ['input[name="userId"]', 'input[name="loginId"]',
                            'input[type="text"]', '#userId', '#id']:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(username)
                        log.debug("Filled username via: %s", sel)
                        break
                else:
                    raise RuntimeError("Could not locate username field")

                # Password
                for sel in ['input[name="userPwd"]', 'input[name="password"]',
                            'input[type="password"]', '#userPwd', '#pw']:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.fill(password)
                        log.debug("Filled password via: %s", sel)
                        break
                else:
                    raise RuntimeError("Could not locate password field")

                # Submit
                for sel in ['button[type="submit"]', 'input[type="submit"]',
                            'a.btn-login', '.login-btn', 'button:has-text("로그인")']:
                    if page.locator(sel).count() > 0:
                        page.locator(sel).first.click()
                        log.debug("Clicked login via: %s", sel)
                        break
                else:
                    page.keyboard.press("Enter")

                page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)

                if "login" in page.url.lower():
                    raise RuntimeError(
                        "Still on login page — check AUTOHUB credentials or site structure."
                    )
                log.info("Login succeeded. Current URL: %s", page.url)

                # ── Navigate to list / export page ─────────────────────────
                log.info("Opening auction list page…")
                page.goto(LIST_URL, wait_until="domcontentloaded")

                # Try to find the Excel download button
                excel_selectors = [
                    f'a:has-text("{FILENAME_PREFIX}")',
                    'button:has-text("엑셀")', 'a:has-text("엑셀")',
                    'button:has-text("Excel")', 'a:has-text("Excel")',
                    'button:has-text("다운로드")', 'a:has-text("다운로드")',
                    '[onclick*="excel"]', '[onclick*="xlsx"]',
                    'a[href*=".xlsx"]', 'a[href*="download"]',
                    'img[alt*="엑셀"]', 'img[src*="excel"]',
                ]

                export_el = None
                for sel in excel_selectors:
                    el = page.locator(sel)
                    if el.count() > 0:
                        export_el = el.first
                        log.info("Found export element via: %s", sel)
                        break

                # Fallback: intercept network request for .xlsx
                if export_el is None:
                    log.warning(
                        "Could not find Excel button with standard selectors. "
                        "Attempting XHR/fetch intercept fallback…"
                    )
                    export_el = _intercept_fallback(page, tmp_dir, args.date, target_path)
                    if export_el is None:
                        page.screenshot(path=str(LOG_DIR / "autohub_debug.png"))
                        raise RuntimeError(
                            "Could not find Excel export button or intercept download. "
                            "Screenshot saved to logs/autohub_debug.png. "
                            "Inspect the page and update excel_selectors."
                        )
                    return export_el   # intercept path already saved the file

                # ── Download ───────────────────────────────────────────────
                log.info("Triggering Excel download…")
                with page.expect_download(timeout=60_000) as dl_info:
                    export_el.click()
                download = dl_info.value

                suggested = download.suggested_filename
                log.info("Download started: %s", suggested)

                # Validate it looks like the expected file
                if not re.search(FILENAME_PREFIX, suggested):
                    log.warning(
                        "Downloaded filename '%s' doesn't match expected prefix '%s'. "
                        "Saving anyway.", suggested, FILENAME_PREFIX
                    )

                tmp_file = Path(tmp_dir) / suggested
                download.save_as(str(tmp_file))
                shutil.move(str(tmp_file), str(target_path))
                log.info("✓ Saved: %s", target_path)
                return str(target_path)

            except PWTimeout as e:
                page.screenshot(path=str(LOG_DIR / "autohub_timeout.png"))
                log.error("Playwright timeout: %s (screenshot saved)", e)
                raise
            finally:
                context.close()
                browser.close()


def _intercept_fallback(page, tmp_dir: str, date_label: str, target_path: Path):
    """
    Fallback: watch network traffic for an .xlsx response while clicking
    anything that looks like it might trigger a download.
    Returns the saved path string if successful, None otherwise.
    """
    captured = {}

    def handle_response(response):
        ct = response.headers.get("content-type", "")
        cd = response.headers.get("content-disposition", "")
        if "spreadsheet" in ct or "xlsx" in ct or "출품리스트" in cd or ".xlsx" in cd:
            captured["url"] = response.url
            captured["headers"] = response.headers

    page.on("response", handle_response)

    # Click any download-looking element
    for sel in ['button', 'a']:
        els = page.locator(sel).all()
        for el in els:
            text = (el.inner_text() or "").strip()
            if any(kw in text for kw in ["엑셀", "다운로드", "Excel", "CSV", "출품"]):
                try:
                    with page.expect_download(timeout=15_000) as dl:
                        el.click()
                    dl_val = dl.value
                    tmp_file = Path(tmp_dir) / dl_val.suggested_filename
                    dl_val.save_as(str(tmp_file))
                    import shutil as _sh
                    _sh.move(str(tmp_file), str(target_path))
                    log.info("✓ Fallback download saved: %s", target_path)
                    return str(target_path)
                except Exception:
                    continue

    if captured.get("url"):
        log.warning("Intercepted XHR to %s but couldn't trigger browser download.", captured["url"])
    return None


def main():
    args = parse_args()
    for attempt in range(1, args.retries + 1):
        try:
            path = run(args)
            log.info("Done → %s", path)
            return
        except Exception as e:
            log.warning("Attempt %d/%d failed: %s", attempt, args.retries, e)
            if attempt < args.retries:
                wait = 15 * attempt
                log.info("Retrying in %ds…", wait)
                time.sleep(wait)
            else:
                log.error("All %d attempts failed. Exiting.", args.retries)
                sys.exit(1)


if __name__ == "__main__":
    main()

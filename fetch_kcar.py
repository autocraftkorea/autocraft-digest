#!/usr/bin/env python3
"""
fetch_kcar.py — Download weekly Excel export from kcarauction.com
Saves to: ~/autocraft/data/kcar_YYYY-MM-DD.xlsx
"""

import os
import sys
import time
import shutil
import logging
import argparse
import tempfile
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LOGIN_URL  = "https://www.kcarauction.com/kcar/user/user_login.do"
EXPORT_URL = "https://www.kcarauction.com/kcar/auction/weekly_auction/colAuction.do?PAGE_TYPE=wCfm&LANE_TYPE=A#1"
DATA_DIR   = Path.home() / "autocraft" / "data"
LOG_DIR    = Path.home() / "autocraft" / "logs"
TIMEOUT_MS  = 30_000
NAV_TIMEOUT = 60_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_DIR / "fetch_kcar.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=str(date.today()))
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--retries", type=int, default=3)
    return p.parse_args()


def get_credentials():
    username = os.environ.get("KCAR_USERNAME")
    password = os.environ.get("KCAR_PASSWORD")
    if not username or not password:
        log.error("KCAR_USERNAME / KCAR_PASSWORD not set.")
        sys.exit(1)
    return username, password


def run(args):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    username, password = get_credentials()
    target_path = DATA_DIR / f"kcar_{args.date}.xlsx"

    if target_path.exists():
        log.info("Already exists: %s — skipping.", target_path)
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
                # Login
                log.info("Navigating to login page...")
                page.goto(LOGIN_URL, wait_until="domcontentloaded")
                page.locator("#user_id").fill(username)
                page.locator("#user_pw").fill(password)
                page.keyboard.press("Enter")
                page.wait_for_load_state("networkidle", timeout=NAV_TIMEOUT)
                log.info("Login submitted. URL: %s", page.url)

                # Dismiss popups
                time.sleep(3)
                for sel in ['button:has-text("동의안함")', 'button:has-text("닫기")', 'button:has-text("확인")', 'button:has-text("동의")']:
                    for btn in page.locator(sel).all():
                        try:
                            btn.click()
                            time.sleep(1)
                        except Exception:
                            pass

                # Navigate to export page
                log.info("Opening export page...")
                page.goto(EXPORT_URL, wait_until="domcontentloaded")
                time.sleep(3)

                # Find download button
                export_el = None
                for sel in ['a[href*="excel_download"]', 'a:has-text("엑셀다운로드")']:
                    if page.locator(sel).count() > 0:
                        export_el = page.locator(sel).first
                        log.info("Found export button via: %s", sel)
                        break

                if export_el is None:
                    page.screenshot(path=str(LOG_DIR / "kcar_debug.png"))
                    raise RuntimeError("Could not find export button. Screenshot saved.")

                # Download
                log.info("Triggering download...")
                with page.expect_download(timeout=60_000) as dl_info:
                    export_el.click()
                download = dl_info.value
                suggested = download.suggested_filename
                log.info("Downloading: %s", suggested)

                tmp_file = Path(tmp_dir) / suggested
                download.save_as(str(tmp_file))
                shutil.move(str(tmp_file), str(target_path))
                log.info("Saved: %s", target_path)
                return str(target_path)

            except PWTimeout as e:
                page.screenshot(path=str(LOG_DIR / "kcar_timeout.png"))
                log.error("Timeout: %s", e)
                raise
            finally:
                context.close()
                browser.close()


def main():
    args = parse_args()
    for attempt in range(1, args.retries + 1):
        try:
            path = run(args)
            log.info("Done: %s", path)
            return
        except Exception as e:
            log.warning("Attempt %d/%d failed: %s", attempt, args.retries, e)
            if attempt < args.retries:
                wait = 15 * attempt
                log.info("Retrying in %ds...", wait)
                time.sleep(wait)
            else:
                log.error("All attempts failed.")
                sys.exit(1)


if __name__ == "__main__":
    main()

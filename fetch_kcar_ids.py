#!/usr/bin/env python3
"""
fetch_kcar_ids.py — Scrape per-vehicle CAR_ID and AUC_CD from the K-Car
weekly auction list page, so the digest's "View listing" links point to the
real detail page instead of a synthesised URL.

Output: ~/autocraft/data/kcar_ids_YYYYMMDD.json
        keyed by "<LANE>:<LOT>", e.g. {"A:1202": {"car_id":"CA20374300","auc_cd":"AC20260411"}}

Date used in filename:
  - --date YYYY-MM-DD if passed, else the latest KCAR_<date>_*.csv in data/.
  - If no CSV exists yet, today's date.
"""

import os
import re
import sys
import json
import time
import logging
import argparse
from datetime import date
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

LOGIN_URL = "https://www.kcarauction.com/kcar/user/user_login.do"
LIST_URL_TPL = (
    "https://www.kcarauction.com/kcar/auction/weekly_auction/colAuction.do"
    "?PAGE_TYPE=wCfm&LANE_TYPE={lane}"
)
DATA_DIR = Path.home() / "autocraft" / "data"
LOG_DIR = Path.home() / "autocraft" / "logs"
LANES = ("A", "B")

# Cart-icon ids appear as `ai_AC..._CA...` (table view) and `lai_AC..._CA...` (list view).
ID_PATTERN = re.compile(r"l?ai_(AC\d+)_(CA\d+)")
# Lot number text: "출품번호 1001(A)"
LOT_PATTERN = re.compile(r"출품번호\s*(\d+)\(([A-Z])\)")
# Page-size selector accepts 18, 36, or 72.
PAGE_SIZE = "72"
MAX_PAGES = 30

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None,
                   help="Auction date (YYYY-MM-DD). Defaults to latest KCAR CSV in data/, "
                        "or today if no CSV present.")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--debug-html", action="store_true",
                   help="Save the rendered list HTML to logs/ for inspection.")
    return p.parse_args()


def resolve_date(arg_date):
    if arg_date:
        return arg_date.replace("-", "")
    if DATA_DIR.exists():
        dates = []
        for f in DATA_DIR.iterdir():
            if not f.name.startswith("KCAR_") or not f.name.endswith(".csv"):
                continue
            for tok in f.name.replace(".csv", "").split("_"):
                if tok.isdigit() and len(tok) == 8:
                    dates.append(tok)
                    break
        if dates:
            return max(dates)
    return date.today().strftime("%Y%m%d")


def get_credentials():
    user = os.environ.get("KCAR_USERNAME")
    pw = os.environ.get("KCAR_PASSWORD")
    if not user or not pw:
        log.error("KCAR_USERNAME / KCAR_PASSWORD not set in environment.")
        sys.exit(1)
    return user, pw


def login(page, user, pw):
    log.info("Logging in...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.locator("#user_id").fill(user)
    page.locator("#user_pw").fill(pw)
    page.keyboard.press("Enter")
    page.wait_for_load_state("networkidle", timeout=60_000)
    if "login" in page.url.lower():
        raise RuntimeError("Login failed — still on login page.")
    time.sleep(2)
    for sel in (
        'button:has-text("동의안함")',
        'button:has-text("닫기")',
        'button:has-text("확인")',
        'button:has-text("동의")',
    ):
        for btn in page.locator(sel).all():
            try:
                btn.click(timeout=1500)
                time.sleep(0.5)
            except Exception:
                pass


def extract_from_html(html):
    """
    Pair each unique (AUC_CD, CAR_ID) with the nearest "출품번호 NNNN(L)"
    occurrence in the document. Returns dict keyed by "<LANE>:<LOT>".
    """
    id_first_pos = {}
    for m in ID_PATTERN.finditer(html):
        key = (m.group(1), m.group(2))
        if key not in id_first_pos:
            id_first_pos[key] = m.start()
    lots = [(m.start(), m.group(1), m.group(2)) for m in LOT_PATTERN.finditer(html)]
    mapping = {}
    if not lots:
        return mapping
    for (auc_cd, car_id), pos in id_first_pos.items():
        nearest = min(lots, key=lambda l: abs(l[0] - pos))
        _, lot, lane = nearest
        mapping[f"{lane}:{lot}"] = {"car_id": car_id, "auc_cd": auc_cd}
    return mapping


def scrape_lane(page, lane, debug_html=False):
    url = LIST_URL_TPL.format(lane=lane)
    log.info("Lane %s: loading %s", lane, url)
    page.goto(url, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=60_000)
    # Wait for the cart-icon link to be attached (it's styled-hidden, so don't require visibility).
    try:
        page.wait_for_selector('[id^="ai_AC"], [id^="lai_AC"]', state="attached", timeout=20_000)
    except Exception:
        log.warning("Lane %s: cart icons did not appear within 20s", lane)
    time.sleep(2)

    # Bump page size to 72 (max) by setting the underlying select value via JS.
    # The visible element is a custom dropdown, so select_option/click can fail
    # on visibility checks — set the value directly and trigger the onchange.
    try:
        page.evaluate(
            f"""() => {{
                const sel = document.getElementById('page_cnt');
                if (!sel) return false;
                sel.value = '{PAGE_SIZE}';
                if (typeof getAuctionCarList === 'function') {{
                    getAuctionCarList(1, '', 'weekly');
                }} else {{
                    sel.dispatchEvent(new Event('change'));
                }}
                return true;
            }}"""
        )
        time.sleep(3)
        page.wait_for_load_state("networkidle", timeout=30_000)
    except Exception as e:
        log.warning("Lane %s: could not set page size to %s (%s) — falling back to default page size",
                    lane, PAGE_SIZE, type(e).__name__)

    if debug_html:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / f"kcar_list_lane_{lane}_p1.html").write_text(
            page.content(), encoding="utf-8"
        )

    mapping = {}
    seen_ids_per_page = []
    for page_num in range(1, MAX_PAGES + 1):
        if page_num > 1:
            try:
                page.evaluate(f"go_page({page_num}, 'weekly')")
            except Exception as e:
                log.warning("Lane %s: go_page(%d) failed: %s", lane, page_num, e)
                break
            time.sleep(2)
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except Exception:
                pass

        html = page.content()
        page_mapping = extract_from_html(html)
        ids_this_page = frozenset(
            (v["auc_cd"], v["car_id"]) for v in page_mapping.values()
        )
        log.info("Lane %s page %d: %d mappings", lane, page_num, len(page_mapping))

        if not page_mapping:
            log.info("Lane %s: empty page — stopping at %d", lane, page_num)
            break
        if seen_ids_per_page and ids_this_page == seen_ids_per_page[-1]:
            log.info("Lane %s: page %d duplicates page %d — stopping",
                     lane, page_num, page_num - 1)
            break

        seen_ids_per_page.append(ids_this_page)
        mapping.update(page_mapping)

        if debug_html and page_num <= 3:
            (LOG_DIR / f"kcar_list_lane_{lane}_p{page_num}.html").write_text(
                html, encoding="utf-8"
            )

    log.info("Lane %s: total %d unique lot mappings across %d pages",
             lane, len(mapping), len(seen_ids_per_page))
    return mapping


def main():
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    user, pw = get_credentials()
    date_token = resolve_date(args.date)
    out_path = DATA_DIR / f"kcar_ids_{date_token}.json"
    log.info("Output: %s", out_path)

    all_mapping = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, args=["--lang=ko-KR"])
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(60_000)
        try:
            login(page, user, pw)
            for lane in LANES:
                try:
                    all_mapping.update(scrape_lane(page, lane, debug_html=args.debug_html))
                except PWTimeout as e:
                    log.error("Lane %s timed out: %s", lane, e)
        finally:
            context.close()
            browser.close()

    if not all_mapping:
        log.error("No mappings extracted. Re-run with --debug-html to inspect the page.")
        sys.exit(2)

    out_path.write_text(
        json.dumps(all_mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info("Saved %d mappings to %s", len(all_mapping), out_path)


if __name__ == "__main__":
    main()

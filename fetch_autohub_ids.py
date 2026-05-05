#!/usr/bin/env python3
"""
fetch_autohub_ids.py — Scrape per-vehicle entryId / perfId / carId / evalDate
from sellcarauction.co.kr's auction listing, so the digest's "View listing"
links point to real Autohub detail pages.

The site is a React SPA — IDs are not in the rendered DOM. Approach:
  1. Log in.
  2. Navigate to /auction/list?page=N for each page.
  3. Intercept all JSON responses and extract any dict that has
     entryId + carId + perfId, paired with the row's lot number ("entryNo")
     and lane ("laneCode" / "lane").
  4. Save data/autohub_ids_<YYYYMMDD>.json keyed by "<LANE>:<LOT>".
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

LOGIN_URL = "https://www.sellcarauction.co.kr/login?lang=ko"
LIST_URL_TPL = (
    "https://www.sellcarauction.co.kr/auction/list"
    "?lang=ko&page={page}&sortBy=entryNo"
)
DATA_DIR = Path.home() / "autocraft" / "data"
LOG_DIR = Path.home() / "autocraft" / "logs"
MAX_PAGES = 120  # 1824 vehicles / ~20 per page = 92 pages; cap higher.

# Login form selector candidates (try in order).
ID_SELECTORS = (
    'input[placeholder*="아이디"]',
    'input[name="userId"]', 'input[name="loginId"]', 'input[name="memberId"]',
    'input[name="id"]', '#userId', '#loginId', '#user_id', '#memberId',
    'input[type="text"]:not([readonly])', 'input[type="email"]',
)
PW_SELECTORS = (
    'input[type="password"]',
    'input[placeholder*="비밀번호"]',
    'input[name="password"]', 'input[name="userPw"]', 'input[name="pwd"]',
    '#password', '#userPw', '#user_pw',
)
SUBMIT_SELECTORS = (
    'form button[type="submit"]',
    'button[type="submit"]',
    'form button:has-text("로그인")',
    'input[type="submit"]',
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None,
                   help="Auction date (YYYY-MM-DD). Defaults to latest 출품리스트_*.xlsx in data/, or today.")
    p.add_argument("--headless", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--max-pages", type=int, default=MAX_PAGES)
    p.add_argument("--debug-json", action="store_true",
                   help="Dump the first response containing entryId to logs/.")
    p.add_argument("--debug-html", action="store_true",
                   help="Dump login + list page HTML to logs/.")
    return p.parse_args()


def resolve_date(arg_date):
    if arg_date:
        return arg_date.replace("-", "")
    if DATA_DIR.exists():
        candidates = []
        for f in DATA_DIR.iterdir():
            m = re.search(r"(\d{4})-(\d{2})-(\d{2})", f.name)
            if m and "출품" in f.name:
                candidates.append(m.group(1) + m.group(2) + m.group(3))
        if candidates:
            return max(candidates)
    return date.today().strftime("%Y%m%d")


def get_credentials():
    user = os.environ.get("AUTOHUB_USERNAME")
    pw = os.environ.get("AUTOHUB_PASSWORD")
    if not user or not pw:
        log.error("AUTOHUB_USERNAME / AUTOHUB_PASSWORD not set in environment.")
        sys.exit(1)
    return user, pw


def first_match(page, selectors):
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0:
                return loc, sel
        except Exception:
            pass
    return None, None


def login(page, user, pw, debug_html=False):
    log.info("Loading login page...")
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle", timeout=30_000)
    time.sleep(1)

    if debug_html:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "autohub_login.html").write_text(page.content(), encoding="utf-8")

    id_loc, id_sel = first_match(page, ID_SELECTORS)
    pw_loc, pw_sel = first_match(page, PW_SELECTORS)
    if id_loc is None or pw_loc is None:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / "autohub_login.html").write_text(page.content(), encoding="utf-8")
        raise RuntimeError(
            "Could not locate login form fields — saved HTML to "
            f"{LOG_DIR/'autohub_login.html'} for inspection."
        )
    log.info("Login form: id=%s, pw=%s", id_sel, pw_sel)
    id_loc.fill(user)
    pw_loc.fill(pw)

    submit_loc, submit_sel = first_match(page, SUBMIT_SELECTORS)
    if submit_loc:
        log.info("Submitting via: %s", submit_sel)
        submit_loc.click()
    else:
        log.info("No submit button found; pressing Enter")
        page.keyboard.press("Enter")

    try:
        page.wait_for_url(lambda u: "/login" not in u, timeout=30_000)
    except PWTimeout:
        if debug_html:
            (LOG_DIR / "autohub_login_after.html").write_text(
                page.content(), encoding="utf-8"
            )
        raise RuntimeError(
            "Login appears to have failed (still on /login). "
            "Re-run with --debug-html to inspect."
        )
    log.info("Login succeeded; current URL: %s", page.url)


# ---------- response parsing ----------

# Field-name candidates (matching the actual API on api.ahsellcar.co.kr).
LOT_KEYS = ("entryNo", "lotNo")
LANE_KEYS = ("aucLaneCode", "laneCode", "lane")
EVAL_KEYS = ("aucStartPlanDate", "evalDate", "aucDate")


def first_present(d, keys):
    for k in keys:
        v = d.get(k)
        if v not in (None, ""):
            return v
    return None


def normalize_lane(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    # "A 레인" -> "A"; "A_LANE" -> "A"; "A" -> "A"
    m = re.match(r"^\s*([A-Z])", s)
    return m.group(1) if m else s


def find_vehicles(obj, _depth=0):
    """Walk a JSON structure; yield dicts that have entryId + carId + perfId."""
    if _depth > 20:
        return
    if isinstance(obj, dict):
        if "entryId" in obj and "carId" in obj and "perfId" in obj:
            yield obj
        for v in obj.values():
            yield from find_vehicles(v, _depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            yield from find_vehicles(item, _depth + 1)


def make_response_handler(captured, debug_state):
    def on_response(response):
        try:
            ct = response.headers.get("content-type", "")
            if "json" not in ct.lower():
                return
            url = response.url
            # Cheap content sniff to skip irrelevant JSON
            text = response.text()
            if "entryId" not in text:
                return
            try:
                body = json.loads(text)
            except Exception:
                return

            if debug_state.get("dump_all"):
                LOG_DIR.mkdir(parents=True, exist_ok=True)
                idx = debug_state.setdefault("dump_idx", 0)
                debug_state["dump_idx"] = idx + 1
                # Sanitize URL into filename
                safe = re.sub(r"[^a-zA-Z0-9._-]", "_", url)[-80:]
                (LOG_DIR / f"autohub_api_{idx:03d}_{safe}.json").write_text(
                    json.dumps({"url": url, "body": body}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )

            for v in find_vehicles(body):
                entry_id = v.get("entryId")
                car_id = v.get("carId")
                perf_id = v.get("perfId")
                lot = first_present(v, LOT_KEYS)
                lane_raw = first_present(v, LANE_KEYS)
                eval_dt = first_present(v, EVAL_KEYS)
                if not (entry_id and car_id and perf_id and lot):
                    continue
                lane = normalize_lane(lane_raw) or "?"
                key = f"{lane}:{lot}"
                if key not in captured:
                    captured[key] = {
                        "entry_id": entry_id,
                        "perf_id": perf_id,
                        "car_id": car_id,
                        "eval_date": str(eval_dt) if eval_dt else None,
                    }
        except Exception as e:
            log.debug("response handler error: %s", e)
    return on_response


# ---------- main scrape ----------

def main():
    args = parse_args()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    user, pw = get_credentials()
    date_token = resolve_date(args.date)
    out_path = DATA_DIR / f"autohub_ids_{date_token}.json"
    log.info("Output: %s", out_path)

    captured = {}
    debug_state = {"dump_all": args.debug_json}

    with sync_playwright() as p:
        # Site's WAF blocks Playwright Chromium via TLS/JA3 fingerprinting.
        # Firefox has a different TLS stack and passes the check.
        browser = p.firefox.launch(headless=args.headless)
        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Sec-Ch-Ua": (
                    '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"'
                ),
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"macOS"',
            },
        )
        # Mask webdriver flag
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.set_default_navigation_timeout(60_000)
        page.on("response", make_response_handler(captured, debug_state))

        try:
            login(page, user, pw, debug_html=args.debug_html)
        except Exception as e:
            log.error("Login failed: %s", e)
            browser.close()
            sys.exit(2)

        # Settle after login redirect before first navigation.
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PWTimeout:
            pass
        time.sleep(2)

        prev_count = -1
        empty_pages = 0
        for page_num in range(1, args.max_pages + 1):
            url = LIST_URL_TPL.format(page=page_num)
            log.info("Page %d: %s", page_num, url)
            for attempt in range(3):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                    break
                except Exception as e:
                    msg = str(e)
                    if "NS_BINDING_ABORTED" in msg or "aborted" in msg.lower():
                        log.warning("Page %d goto attempt %d aborted; retrying", page_num, attempt + 1)
                        time.sleep(2)
                        continue
                    raise
            try:
                page.wait_for_load_state("networkidle", timeout=30_000)
            except PWTimeout:
                log.warning("Page %d networkidle timeout — continuing", page_num)
            time.sleep(2)

            if args.debug_html and page_num <= 2:
                (LOG_DIR / f"autohub_list_p{page_num}.html").write_text(
                    page.content(), encoding="utf-8"
                )

            new_count = len(captured)
            delta = new_count - prev_count if prev_count >= 0 else new_count
            log.info("Page %d: total mappings now %d (+%d)", page_num, new_count, delta)
            if new_count == prev_count:
                empty_pages += 1
                if empty_pages >= 2:
                    log.info("No new mappings for 2 consecutive pages — stopping at page %d", page_num)
                    break
            else:
                empty_pages = 0
            prev_count = new_count

        browser.close()

    if not captured:
        log.error("No mappings extracted. Re-run with --debug-json --debug-html to inspect.")
        sys.exit(2)

    out_path.write_text(
        json.dumps(captured, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("Saved %d mappings to %s", len(captured), out_path)


if __name__ == "__main__":
    main()

import json, os
from datetime import datetime

def load_json(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)

def fmt_price(p):
    return f"\u20a9{p:,}" if p else "TBD"

def score_color(s):
    return "#1a6b45" if s >= 0.75 else "#a05e10" if s >= 0.55 else "#c13a1e"

def score_bg(s):
    return "#e6f4ed" if s >= 0.75 else "#fdf0dc" if s >= 0.55 else "#fceaea"

def bar_color(p):
    return "#1a6b45" if p >= 0.75 else "#a05e10" if p >= 0.45 else "#c13a1e"

def flag_style(f):
    fl = f.lower()
    if any(x in fl for x in ["no accident", "grade:", "below target", "preferred colour"]):
        return "background:#e6f4ed;color:#085041;border:1px solid #1D9E75"
    if any(x in fl for x in ["above target", "below preferred", "rental", "unknown", "keyword", "near-miss"]):
        return "background:#fdf0dc;color:#633806;border:1px solid #BA7517"
    if any(x in fl for x in ["accident history", "flood", "lien"]):
        return "background:#fceaea;color:#A32D2D;border:1px solid #c13a1e"
    return "background:#f1efe8;color:#5f5e5a;border:1px solid #d3d1c7"

def clean_lane(v):
    s = str(v or "").replace("\ub808\uc778", "").replace(" ", "").strip()
    return f"Lane {s}" if s else "\u2014"

def src_label(v):
    return {"kcar": "K-Car", "autohub": "Autohub"}.get(str(v).lower(), str(v).upper())

def fmt_date(iso):
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return "\u2014"

def render(results, auction_date, total_vehicles):
    by_customer = {}
    for r in results:
        by_customer.setdefault(r["customer_name"], []).append(r)
    now = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    css = (
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f4f1eb;color:#0d0d0b;font-size:14px;line-height:1.5}"
        ".wrap{max-width:900px;margin:0 auto}"
        ".hdr{background:#0d0d0b;color:#f4f1eb;padding:28px 32px 22px}"
        ".hdr-brand{font-size:11px;letter-spacing:.15em;text-transform:uppercase;color:#888;font-family:monospace;margin-bottom:6px}"
        ".hdr-title{font-size:26px;font-weight:300;margin-bottom:8px}"
        ".hdr-title b{font-weight:600}"
        ".hdr-meta{font-family:monospace;font-size:11px;color:#aaa;margin-bottom:16px}"
        ".stats{display:flex;gap:28px;padding-top:16px;border-top:1px solid rgba(255,255,255,.1)}"
        ".sn{font-family:monospace;font-size:22px;color:#f4f1eb;display:block}"
        ".sl{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#777}"
        ".cust{background:#fff;margin-bottom:12px}"
        ".ch{padding:14px 24px;border-bottom:1px solid #e8e4dc;display:flex;align-items:center;gap:12px;flex-wrap:wrap}"
        ".cn{font-family:monospace;font-size:10px;background:#f4f1eb;padding:2px 8px;border-radius:2px;color:#888}"
        ".cname{font-size:16px;font-weight:500}"
        ".ccount{font-family:monospace;font-size:11px;color:#888;margin-left:auto}"
        ".vehicles{padding:12px 16px;display:flex;flex-direction:column;gap:10px}"
        ".card{border:1px solid #e0dcd4;border-radius:4px;overflow:hidden;background:#fff}"
        ".card:hover{box-shadow:0 2px 12px rgba(0,0,0,.08)}"
        ".card.strong{border-left:3px solid #1a6b45}"
        ".card.nearmiss{border-left:3px solid #a05e10}"
        ".card-body{display:grid;grid-template-columns:60px 1fr 152px}"
        ".rc{background:#f4f1eb;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:12px 0;border-right:1px solid #e0dcd4;gap:4px}"
        ".rn{font-family:monospace;font-size:20px;font-weight:600;line-height:1}"
        ".rl{font-family:monospace;font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:#aaa}"
        ".ring{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:monospace;font-size:11px;font-weight:600;margin-top:4px}"
        ".ic{padding:12px 14px}"
        ".vname{font-size:13px;font-weight:500;margin-bottom:2px;line-height:1.3}"
        ".vsub{font-family:monospace;font-size:10px;color:#aaa;margin-bottom:8px}"
        ".specs{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:8px}"
        ".slbl{font-family:monospace;font-size:9px;text-transform:uppercase;letter-spacing:.06em;color:#aaa;display:block}"
        ".sval{font-family:monospace;font-size:12px;font-weight:500}"
        ".flags{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}"
        ".flag{font-family:monospace;font-size:10px;padding:2px 7px;border-radius:2px}"
        ".sc{border-left:1px solid #e0dcd4;padding:12px 10px;display:flex;flex-direction:column;gap:4px;justify-content:center}"
        ".bdrow{margin-bottom:2px}"
        ".bdhead{display:flex;justify-content:space-between;margin-bottom:2px}"
        ".bdlbl{font-family:monospace;font-size:9px;text-transform:uppercase;letter-spacing:.05em;color:#aaa}"
        ".bdpct{font-family:monospace;font-size:9px;color:#aaa}"
        ".btrack{height:5px;background:#e8e4dc;border-radius:2px}"
        ".bfill{height:5px;border-radius:2px}"
        ".foot{border-top:1px solid #e8e4dc;padding:6px 14px;display:flex;align-items:center;gap:6px;background:#fafaf8;flex-wrap:wrap}"
        ".lotref{font-family:monospace;font-size:10px;color:#aaa}"
        ".lotref b{color:#0d0d0b}"
        ".vbtn{font-family:monospace;font-size:10px;color:#c13a1e;background:#f9ece8;border:1px solid #f5c4b3;padding:3px 10px;border-radius:2px;text-decoration:none;margin-left:auto}"
        ".ntag{font-family:monospace;font-size:10px;color:#a05e10;background:#fdf0dc;padding:2px 8px;border-radius:2px}"
        ".stag{font-family:monospace;font-size:10px;color:#085041;background:#e6f4ed;padding:2px 8px;border-radius:2px}"
        ".nodata{padding:16px 24px;font-family:monospace;font-size:12px;color:#aaa;font-style:italic}"
        ".divider{height:6px;background:#f4f1eb;border-top:1px solid #e0dcd4;border-bottom:1px solid #e0dcd4}"
        ".ftr{background:#0d0d0b;color:#666;padding:18px 32px;font-family:monospace;font-size:11px;line-height:1.9}"
        ".ftr b{color:#aaa}"
        # --- Filter bar styles ---
        "#filter-bar{display:flex;align-items:center;gap:8px;padding:10px 16px;background:#f4f1eb;border-bottom:1px solid #ddd;position:sticky;top:0;z-index:100}"
        ".filter-btn{font-family:monospace;font-size:11px;padding:4px 14px;border:1px solid #bbb;border-radius:20px;background:#fff;color:#555;cursor:pointer;transition:all .15s}"
        ".filter-btn:hover{background:#e8e4dc;color:#0d0d0b}"
        ".filter-btn.active{background:#1a6b45;border-color:#1a6b45;color:#fff;font-weight:600}"
        ".date-tag{font-family:monospace;font-size:10px;color:#aaa;margin-left:auto;white-space:nowrap}"
    )

    filter_js = (
        "<script>"
        "function filterPlatform(p){"
        "document.querySelectorAll('.filter-btn').forEach(function(b){b.classList.remove('active');});"
        "document.getElementById('btn-'+p).classList.add('active');"
        # Show/hide cards and track which customer sections have visible cards
        "var wrap=document.querySelector('.wrap');"
        "document.querySelectorAll('.cust').forEach(function(section){"
        "var hasVisible=false;"
        "section.querySelectorAll('.card').forEach(function(c){"
        "var show=p==='all'||c.dataset.platform===p;"
        "c.style.display=show?'':'none';"
        "if(show)hasVisible=true;"
        "});"
        "section.style.display=hasVisible?'':'none';"
        "});"
        # Hide/show dividers: a divider should show only if the section after it is visible
        # and it is not the first visible section
        "var firstVisible=null;"
        "wrap.querySelectorAll('.cust').forEach(function(s){"
        "if(s.style.display!=='none'&&!firstVisible)firstVisible=s;"
        "});"
        "wrap.querySelectorAll('.divider').forEach(function(d){"
        "var next=d.nextElementSibling;"
        "while(next&&!next.classList.contains('cust'))next=next.nextElementSibling;"
        "d.style.display=(next&&next.style.display!=='none'&&next!==firstVisible)?'':'none';"
        "});}"
        "</script>"
    )

    parts = []
    parts.append(
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>Autocraft Korea \u2014 Auction Digest {auction_date}</title>"
        f"<style>{css}</style>"
        f"{filter_js}"
        "</head><body>"
        "<div id=\"filter-bar\">"
        "<button id=\"btn-all\" class=\"filter-btn active\" onclick=\"filterPlatform('all')\">All</button>"
        "<button id=\"btn-kcar\" class=\"filter-btn\" onclick=\"filterPlatform('kcar')\">K-Car</button>"
        "<button id=\"btn-autohub\" class=\"filter-btn\" onclick=\"filterPlatform('autohub')\">Autohub</button>"
        "</div>"
        "<div class=\"wrap\">"
        "<div class=\"hdr\">"
        "<div class=\"hdr-brand\">Autocraft Korea \u2014 Auction Intelligence</div>"
        "<div class=\"hdr-title\">Weekly auction <b>buyer digest</b></div>"
        f"<div class=\"hdr-meta\">Generated: {now} &nbsp;|&nbsp; Auction date: {auction_date}</div>"
        "<div class=\"stats\">"
        f"<div><span class=\"sn\">{total_vehicles:,}</span><span class=\"sl\">Vehicles scanned</span></div>"
        f"<div><span class=\"sn\">{len(by_customer)}</span><span class=\"sl\">Profiles matched</span></div>"
        f"<div><span class=\"sn\">{len(results)}</span><span class=\"sl\">Matches surfaced</span></div>"
        "<div><span class=\"sn\">13:00 KST</span><span class=\"sl\">Auction starts</span></div>"
        "</div></div>"
    )

    for ci, (customer, matches) in enumerate(by_customer.items()):
        if ci > 0:
            parts.append('<div class="divider"></div>')
        strong = sum(1 for m in matches if not m["is_near_miss"])
        near   = sum(1 for m in matches if m["is_near_miss"])
        ctxt   = f"{len(matches)} match{'es' if len(matches) != 1 else ''}"
        if near:
            ctxt += f" &middot; {near} near-miss"

        parts.append(
            f'<div class="cust"><div class="ch">'
            f'<span class="cn">Customer {ci+1:02d}</span>'
            f'<span class="cname">{customer}</span>'
            f'<span class="ccount">{ctxt}</span>'
            f'</div><div class="vehicles">'
        )

        if not matches:
            parts.append('<div class="nodata">No matches found for this profile in this auction.</div>')
        else:
            for rank, m in enumerate(matches, 1):
                sc    = m["match_score"]
                bd    = m["score_breakdown"]
                nm    = m["is_near_miss"]
                src   = src_label(m.get("source_platform", ""))
                # --- CHANGE 1: capture raw platform key for data-platform attribute ---
                platform_key = str(m.get("source_platform", "")).lower()
                lot   = m.get("lot_number", "")
                lane  = clean_lane(m.get("auction_lane"))
                park  = m.get("parking_location") or "\u2014"
                url   = m.get("listing_url", "#")
                name  = str(m.get("full_vehicle_name") or "")
                year  = m.get("model_year", "\u2014")
                mil   = f"{m['mileage_km']:,} km" if m.get("mileage_km") else "\u2014"
                price = fmt_price(m.get("starting_price_krw"))
                gp    = m.get("platform_grade", "\u2014")
                gn    = m.get("normalised_grade", "\u2014")
                fuel  = str(m.get("fuel_type") or "\u2014").capitalize()
                tr    = str(m.get("transmission") or "\u2014").capitalize()
                us    = str(m.get("usage_type") or "\u2014").capitalize()
                cc    = "nearmiss" if nm else "strong"
                rb    = score_bg(sc)
                rc    = score_color(sc)
                tag   = '<span class="ntag">near-miss</span>' if nm else '<span class="stag">strong match</span>'
                # --- CHANGE 2: format ingested_at as human-readable date ---
                data_as_of = fmt_date(m.get("ingested_at", ""))

                card = (
                    # CHANGE 1: data-platform attribute added to card div
                    f'<div class="card {cc}" data-platform="{platform_key}"><div class="card-body">'
                    f'<div class="rc"><div class="rn">{rank}</div><div class="rl">rank</div>'
                    f'<div class="ring" style="background:{rb};color:{rc};border:1.5px solid {rc}80">{sc}</div></div>'
                    f'<div class="ic">'
                    f'<div class="vname">{name}</div>'
                    f'<div class="vsub">{src} &middot; Lot {lot} &middot; {lane} &middot; Parking: {park}</div>'
                    f'<div class="specs">'
                    f'<div><span class="slbl">Year</span><span class="sval">{year}</span></div>'
                    f'<div><span class="slbl">Mileage</span><span class="sval">{mil}</span></div>'
                    f'<div><span class="slbl">Starting Price</span><span class="sval">{price}</span></div>'
                    f'<div><span class="slbl">Grade</span><span class="sval">{gp} &rarr; {gn}/10</span></div>'
                    f'<div><span class="slbl">Fuel</span><span class="sval">{fuel}</span></div>'
                    f'<div><span class="slbl">Transmission</span><span class="sval">{tr}</span></div>'
                    f'<div><span class="slbl">Usage</span><span class="sval">{us}</span></div>'
                    f'</div><div class="flags">'
                )
                parts.append(card)

                for flag in m.get("flags", []):
                    parts.append(f'<span class="flag" style="{flag_style(flag)}">{flag}</span>')

                parts.append('</div></div><div class="sc">')

                for dim, lbl in [("grade", "Grade"), ("mileage", "Mileage"), ("price", "Price"), ("year", "Year"), ("accident", "Accident")]:
                    pct = bd.get(dim, 0)
                    bc  = bar_color(pct)
                    parts.append(
                        f'<div class="bdrow"><div class="bdhead">'
                        f'<span class="bdlbl">{lbl}</span><span class="bdpct">{int(pct*100)}%</span>'
                        f'</div><div class="btrack"><div class="bfill" style="width:{int(pct*100)}%;background:{bc}"></div></div></div>'
                    )

                parts.append(
                    f'</div></div>'
                    f'<div class="foot">'
                    f'<span class="lotref">{src} &middot; <b>Lot {lot}</b> &middot; {lane} &middot; Parking: {park}</span>'
                    # CHANGE 2: "Data as of" label before the view button
                    f'<span class="date-tag">Data as of: {data_as_of}</span>'
                    f'<a class="vbtn" href="{url}">View listing &rarr;</a>{tag}'
                    f'</div></div>'
                )

        parts.append('</div></div>')

    parts.append(
        "<div class=\"ftr\">"
        "<b>Autocraft Korea \u2014 Auction Intelligence System</b><br>"
        f"Generated: {now} &nbsp;|&nbsp; Auction date: {auction_date}<br>"
        "Sources: K-Car Weekly Auction &nbsp;|&nbsp; Autohub Listing<br>"
        f"Total vehicles scanned: {total_vehicles:,} &nbsp;|&nbsp; Total matches: {len(results)}<br><br>"
        "<b>Grade mapping:</b> K-Car: A1=9, A2=8, A3=7, B1=6, B2=5 &nbsp;|&nbsp; Autohub: AA=10, AB=9, AC/BA=8, AD/BB=7, BC/CA=6<br>"
        "<b>Score thresholds:</b> &ge;0.75 strong match &nbsp;|&nbsp; 0.55&ndash;0.74 near-miss<br><br>"
        "This digest is generated automatically. All bid decisions remain with the buyer. "
        "Verify listing details on platform before bidding."
        "</div></div></body></html>"
    )

    return "".join(parts)


if __name__ == "__main__":
    base    = os.path.dirname(os.path.abspath(__file__))
    results = load_json(os.path.join(base, "match_results.json"))
    normalised = load_json(os.path.join(base, "normalised_vehicles.json"))
    total_vehicles = len(normalised)
    html    = render(results, datetime.now().strftime("%Y-%m-%d"), total_vehicles)
    out     = os.path.join(base, "digest.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Done — {out}")
    print(f"Customers: {len(set(r['customer_name'] for r in results))} | Matches: {len(results)}")

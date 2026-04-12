import os
import smtplib
import json
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

GMAIL_USER   = os.environ.get("AUTOCRAFT_GMAIL_USER")
GMAIL_PASS   = os.environ.get("AUTOCRAFT_GMAIL_PASS")
SENDER_NAME  = "Autocraft Korea"
SENDER_EMAIL = GMAIL_USER
DIGEST_URL   = "https://autocraftkorea.github.io/autocraft-digest/digest.html"

BUYERS = [
    {
        "name":      "Jaffer",
        "email":     "jaffer.h1220@gmail.com",
        "customers": [
            "Autohaus Chile",
            "Autohaus Chile (Premium)",
            "Wazanoon Ghana",
            "Dominican Republic (LPG)",
            "Dominican Republic (Honda)",
        ]
    }
]

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def publish_to_github():
    base = os.path.dirname(os.path.abspath(__file__))
    try:
        subprocess.run(["git", "-C", base, "add", "digest.html"], check=True)
        subprocess.run(["git", "-C", base, "commit", "-m", f"Digest update {datetime.now().strftime('%Y-%m-%d')}"], check=True)
        subprocess.run(["git", "-C", base, "push", "origin", "main"], check=True)
        print("  Digest published to GitHub Pages")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ERROR publishing to GitHub: {e}")
        return False

def build_email(buyer, results, auction_date):
    total   = len(results)
    strong  = sum(1 for r in results if not r["is_near_miss"])
    near    = sum(1 for r in results if r["is_near_miss"])

    # Build per-customer summary lines
    by_customer = {}
    for r in results:
        by_customer.setdefault(r["customer_name"], []).append(r)

    rows = ""
    for customer, matches in by_customer.items():
        cs = sum(1 for m in matches if not m["is_near_miss"])
        cn = sum(1 for m in matches if m["is_near_miss"])
        top = matches[0]
        price = f"₩{top['starting_price_krw']:,}" if top.get("starting_price_krw") else "TBD"
        top_name = str(top.get("full_vehicle_name") or "")[:50]
        rows += f"""
        <tr>
          <td style="padding:10px 14px;border-bottom:1px solid #e8e4dc;font-size:13px;font-weight:500">{customer}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e8e4dc;font-family:monospace;font-size:12px;text-align:center;color:#1a6b45;font-weight:600">{cs}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e8e4dc;font-family:monospace;font-size:12px;text-align:center;color:#a05e10">{cn}</td>
          <td style="padding:10px 14px;border-bottom:1px solid #e8e4dc;font-family:monospace;font-size:11px;color:#888">{top_name}<br><span style="color:#0d0d0b;font-weight:500">{top.get("platform_grade","")} &rarr; {top.get("normalised_grade","")}/10 &nbsp;|&nbsp; {top.get("mileage_km",""):,} km &nbsp;|&nbsp; {price}</span></td>
        </tr>"""

    subject = f"Autocraft Korea — Auction Digest {auction_date} ({strong} strong matches)"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f1eb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif">
<div style="max-width:620px;margin:32px auto;background:#fff;border:1px solid #e0dcd4">

  <!-- Header -->
  <div style="background:#0d0d0b;padding:24px 32px">
    <div style="font-family:monospace;font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:#888;margin-bottom:6px">Autocraft Korea</div>
    <div style="font-size:22px;font-weight:300;color:#f4f1eb">Auction <b style="font-weight:600">digest ready</b></div>
    <div style="font-family:monospace;font-size:11px;color:#aaa;margin-top:6px">{auction_date} &nbsp;|&nbsp; {total} matches across {len(by_customer)} profiles</div>
  </div>

  <!-- Stats bar -->
  <div style="display:flex;border-bottom:1px solid #e8e4dc">
    <div style="flex:1;padding:16px;text-align:center;border-right:1px solid #e8e4dc">
      <div style="font-family:monospace;font-size:24px;font-weight:600;color:#1a6b45">{strong}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-top:2px">Strong matches</div>
    </div>
    <div style="flex:1;padding:16px;text-align:center;border-right:1px solid #e8e4dc">
      <div style="font-family:monospace;font-size:24px;font-weight:600;color:#a05e10">{near}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-top:2px">Near misses</div>
    </div>
    <div style="flex:1;padding:16px;text-align:center">
      <div style="font-family:monospace;font-size:24px;font-weight:600;color:#0d0d0b">{len(by_customer)}</div>
      <div style="font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:#888;margin-top:2px">Profiles</div>
    </div>
  </div>

  <!-- Customer summary table -->
  <div style="padding:20px 24px 0">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:.1em;color:#aaa;margin-bottom:10px">Summary by customer</div>
    <table style="width:100%;border-collapse:collapse;border:1px solid #e8e4dc">
      <thead>
        <tr style="background:#f9f8f5">
          <th style="padding:8px 14px;text-align:left;font-family:monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#aaa;border-bottom:1px solid #e8e4dc">Customer</th>
          <th style="padding:8px 14px;text-align:center;font-family:monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#aaa;border-bottom:1px solid #e8e4dc">Strong</th>
          <th style="padding:8px 14px;text-align:center;font-family:monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#aaa;border-bottom:1px solid #e8e4dc">Near-miss</th>
          <th style="padding:8px 14px;text-align:left;font-family:monospace;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:#aaa;border-bottom:1px solid #e8e4dc">Top match</th>
        </tr>
      </thead>
      <tbody>{rows}</tbody>
    </table>
  </div>

  <!-- CTA -->
  <div style="padding:28px 24px;text-align:center">
    <a href="{DIGEST_URL}" style="display:inline-block;background:#0d0d0b;color:#f4f1eb;font-family:monospace;font-size:13px;padding:14px 36px;text-decoration:none;letter-spacing:.05em">
      View full digest &rarr;
    </a>
    <div style="font-family:monospace;font-size:10px;color:#aaa;margin-top:12px">{DIGEST_URL}</div>
  </div>

  <!-- Footer -->
  <div style="border-top:1px solid #e8e4dc;padding:14px 24px;background:#f9f8f5">
    <div style="font-family:monospace;font-size:10px;color:#aaa;line-height:1.8">
      <b style="color:#888">Autocraft Korea</b> &mdash; Auction Intelligence System<br>
      Sources: K-Car Weekly Auction &nbsp;|&nbsp; Autohub Listing<br>
      This digest is generated automatically. Verify all details on platform before bidding.
    </div>
  </div>

</div>
</body></html>"""

    plain = f"""Autocraft Korea — Auction Digest {auction_date}

{strong} strong matches | {near} near-misses | {len(by_customer)} profiles

View full digest:
{DIGEST_URL}

— Autocraft Korea
"""
    return subject, html, plain

def send_digest(buyer, subject, html, plain, dry_run=False):
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]       = buyer["email"]
    msg["Reply-To"] = SENDER_EMAIL
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))
    if dry_run:
        print(f"  [DRY RUN] Would send to: {buyer['email']}")
        print(f"  Subject: {subject}")
        return True
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(SENDER_EMAIL, [buyer["email"]], msg.as_string())
        print(f"  Sent to: {buyer['email']}")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-publish", action="store_true", help="Skip GitHub push")
    args = parser.parse_args()

    if not GMAIL_USER or not GMAIL_PASS:
        print("ERROR: credentials not set. Run: source ~/.zshrc")
        exit(1)

    base         = os.path.dirname(os.path.abspath(__file__))
    results      = load_json(os.path.join(base, "match_results.json"))
    auction_date = datetime.now().strftime("%Y-%m-%d")

    print(f"\nAutocraft Korea — Digest Sender")
    print(f"{'='*45}")
    print(f"Auction date  : {auction_date}")
    print(f"Total matches : {len(results)}")
    print(f"Strong matches: {sum(1 for r in results if not r['is_near_miss'])}")
    print(f"Mode          : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*45}\n")

    # Step 1: publish digest to GitHub Pages
    if not args.dry_run and not args.skip_publish:
        print("Publishing digest to GitHub Pages...")
        publish_to_github()
    else:
        print("  [skipping GitHub publish]")

    # Step 2: send notification emails
    print("\nSending notification emails...")
    success = 0
    for buyer in BUYERS:
        print(f"Buyer: {buyer['name']} <{buyer['email']}>")
        subject, html, plain = build_email(buyer, results, auction_date)
        if send_digest(buyer, subject, html, plain, dry_run=args.dry_run):
            success += 1

    print(f"\n{'='*45}")
    print(f"Done — {success}/{len(BUYERS)} buyer(s) {'would be ' if args.dry_run else ''}notified")
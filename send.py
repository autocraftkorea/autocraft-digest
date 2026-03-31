import os
import smtplib
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

GMAIL_USER   = os.environ.get("AUTOCRAFT_GMAIL_USER")
GMAIL_PASS   = os.environ.get("AUTOCRAFT_GMAIL_PASS")
SENDER_NAME  = "Autocraft Korea"
SENDER_EMAIL = GMAIL_USER

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

def load_file(path):
    with open(path, encoding="utf-8") as f:
        return f.read()

def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def build_subject(results, auction_date):
    total  = len(results)
    strong = sum(1 for r in results if not r["is_near_miss"])
    return f"Autocraft Korea — Auction Digest {auction_date} ({strong} strong matches, {total} total)"

def send_digest(buyer, html_body, subject, dry_run=False):
    msg = MIMEMultipart("alternative")
    msg["Subject"]  = subject
    msg["From"]     = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"]       = buyer["email"]
    msg["Reply-To"] = SENDER_EMAIL
    plain = f"Autocraft Korea — Auction Digest\n{subject}\n\nPlease open in an HTML-capable email client.\n\n— Autocraft Korea"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    if dry_run:
        print(f"  [DRY RUN] Would send to: {buyer['email']}")
        print(f"  Subject: {subject}")
        print(f"  HTML size: {len(html_body):,} bytes")
        return True
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(SENDER_EMAIL, [buyer["email"]], msg.as_string())
        print(f"  Sent to: {buyer['email']}")
        return True
    except Exception as e:
        print(f"  ERROR sending to {buyer['email']}: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not GMAIL_USER or not GMAIL_PASS:
        print("ERROR: credentials not set. Run: source ~/.zshrc")
        exit(1)

    base         = os.path.dirname(os.path.abspath(__file__))
    results      = load_json(os.path.join(base, "match_results.json"))
    html_body    = load_file(os.path.join(base, "digest.html"))
    auction_date = datetime.now().strftime("%Y-%m-%d")
    subject      = build_subject(results, auction_date)

    print(f"\nAutocraft Korea — Digest Sender")
    print(f"{'='*45}")
    print(f"Auction date  : {auction_date}")
    print(f"Total matches : {len(results)}")
    print(f"Strong matches: {sum(1 for r in results if not r['is_near_miss'])}")
    print(f"Mode          : {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"{'='*45}\n")

    success = 0
    for buyer in BUYERS:
        print(f"Buyer: {buyer['name']} <{buyer['email']}>")
        if send_digest(buyer, html_body, subject, dry_run=args.dry_run):
            success += 1

    print(f"\n{'='*45}")
    print(f"Done — {success}/{len(BUYERS)} buyer(s) {'would be ' if args.dry_run else ''}notified")
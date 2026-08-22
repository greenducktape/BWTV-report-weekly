#!/usr/bin/env python3
"""
Schickt eine kurze Benachrichtigung, dass der Report aktualisiert wurde.

Aufruf:
    python3 scripts/notify.py --dry-run   # Nachricht nur anzeigen
    python3 scripts/notify.py             # Nachricht senden

Chanty hat keine eigene API und keine eingehenden Webhooks. Der Weg fuehrt
deshalb ueber einen Zapier-"Catch Hook": dieses Skript schickt ein JSON an die
Zapier-URL, Zapier legt daraus per "Create a New Public Message" eine Nachricht
in Chanty an. Genauso funktioniert jeder andere Dienst, der eine Webhook-URL
entgegennimmt (Make, n8n, Slack).

Die Webhook-URL ist ein Geheimnis und steht NICHT im Repository. Sie wird
gesucht in dieser Reihenfolge:
    1. Umgebungsvariable REPORT_WEBHOOK_URL
    2. Datei .secrets/webhook_url  (per .gitignore ausgeschlossen)

Das Skript liest denselben Datenspeicher wie das Dashboard - es rechnet nichts
neu und kann daher nie etwas anderes melden, als auf der Seite steht.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

from build_site import (  # noqa: E402  (Pfad muss vorher gesetzt sein)
    build_months, build_headline, de_num, MONTHS_DE,
)

SECRET_FILE = BASE / ".secrets" / "webhook_url"
TIMEOUT = 20


def webhook_url():
    from_env = os.environ.get("REPORT_WEBHOOK_URL", "").strip()
    if from_env:
        return from_env, "Umgebungsvariable REPORT_WEBHOOK_URL"
    if SECRET_FILE.exists():
        value = SECRET_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value, str(SECRET_FILE.relative_to(BASE))
    return None, None


def de_date(d):
    return "%02d.%02d.%d" % (d.day, d.month, d.year)


def day_range(a, b):
    if a.month == b.month and a.year == b.year:
        return "%02d.–%02d. %s" % (a.day, b.day, MONTHS_DE[b.month - 1])
    return "%s – %s" % (de_date(a), de_date(b))


def build_message(cfg):
    store = json.loads((BASE / "data" / "metricool_daily.json").read_text(encoding="utf-8"))
    days = store["days"]
    last_data = date.fromisoformat(max(days))
    months = build_months(days, last_data)
    current = next(m for m in months if m["key"] == last_data.strftime("%Y-%m"))
    verdict = build_headline(current, months)

    cur, prev = current["total"], current["prevTotal"]
    start = date.fromisoformat(current["start"])
    end = date.fromisoformat(current["end"])

    def delta(c, p):
        if not p:
            return ""
        d = (c - p) / abs(p) * 100
        return " (%s%s %%)" % ("+" if d >= 0 else "−", de_num(abs(d), 1))

    nets = []
    for key, meta in cfg["networks"].items():
        block = current.get(key, {})
        if block.get("followers") is not None:
            nets.append("%s %s Follower" % (meta["label"], de_num(block["followers"])))

    url = cfg.get("publish", {}).get("publicUrl", "")
    emoji = cfg.get("notify", {}).get("emoji", "")
    name = cfg["brand"].get("footer", "")

    lines = [
        "%s %s Social-Media-Report ist aktualisiert – Stand %s" % (emoji, name, de_date(last_data)),
        "",
        verdict["title"] + ".",
        "%s %s: %s Aufrufe%s aus %s Beiträgen." % (
            MONTHS_DE[end.month - 1], end.year, de_num(cur["views"]),
            delta(cur["views"], prev["views"]), de_num(cur["posts"])),
    ]
    if nets:
        lines.append(" · ".join(nets) + ".")
    if url:
        lines += ["", url]

    text = "\n".join(lines)
    return text, {
        "text": text,
        "title": "%s Social-Media-Report – Stand %s" % (name, de_date(last_data)),
        "headline": verdict["title"],
        "url": url,
        "dataDate": last_data.isoformat(),
        "period": day_range(start, end),
        "views": cur["views"],
        "posts": cur["posts"],
        "interactions": cur["interactions"],
        "viewsPerPost": cur["viewsPerPost"],
    }


def main():
    ap = argparse.ArgumentParser(description="Benachrichtigung zum Report senden")
    ap.add_argument("--dry-run", action="store_true", help="Nachricht nur anzeigen")
    ap.add_argument("--url", help="Webhook-URL überschreiben (nur für Tests)")
    args = ap.parse_args()

    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    text, payload = build_message(cfg)

    print("--- Nachricht ---")
    print(text)
    print("-----------------")

    if args.dry_run:
        print("\n--dry-run: nichts gesendet.")
        return

    if not cfg.get("notify", {}).get("enabled", True):
        print("\nBenachrichtigung ist in config.json deaktiviert (notify.enabled=false).")
        return

    url, origin = (args.url, "Parameter --url") if args.url else webhook_url()
    if not url:
        print(
            "\nKeine Webhook-URL hinterlegt – es wurde nichts gesendet.\n"
            "  Entweder:  export REPORT_WEBHOOK_URL='https://hooks.zapier.com/...'\n"
            "  oder:      echo 'https://hooks.zapier.com/...' > .secrets/webhook_url\n"
            "Die Datei .secrets/ ist per .gitignore vom Repository ausgeschlossen.",
            file=sys.stderr,
        )
        raise SystemExit(2)

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "bwtv-report-notify/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            print("\nGesendet (Quelle der URL: %s) – HTTP %s" % (origin, resp.status))
            answer = resp.read(400).decode("utf-8", "replace").strip()
            if answer:
                print("Antwort: " + answer)
    except urllib.error.HTTPError as err:
        raise SystemExit("Webhook antwortete mit HTTP %s: %s"
                         % (err.code, err.read(400).decode("utf-8", "replace").strip()))
    except urllib.error.URLError as err:
        raise SystemExit("Webhook nicht erreichbar: %s" % err.reason)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Fortschrittsuebersicht: aggregiert den Datenspeicher zu Wochen- und Monatswerten
und zeigt die Entwicklung als Tabelle im Terminal.

Aufruf:
    python3 scripts/progress.py              # Wochen
    python3 scripts/progress.py --monthly    # Monate (Metricool)
    python3 scripts/progress.py --meta       # Monate aus den Meta-Exporten (Maerz-Juli)
    python3 scripts/progress.py --csv out.csv

Additivitaet: Aufrufe/Interaktionen/Profilaufrufe/Beitraege werden summiert.
Die Reichweite wird als Summe der Tageswerte ausgegeben (keine Unique-Zahl).
Der Followerstand ist der letzte Wert der Periode.
"""

import argparse
import csv
import json
from collections import OrderedDict
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"


def load_days():
    path = DATA / "metricool_daily.json"
    if not path.exists():
        raise SystemExit(f"Datenspeicher fehlt: {path}")
    return json.loads(path.read_text(encoding="utf-8"))["days"]


def de_int(value) -> str:
    if value is None:
        return "-"
    return f"{int(round(value)):,}".replace(",", ".")


def period_key(day: date, monthly: bool) -> str:
    if monthly:
        return f"{day.year}-{day.month:02d}"
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def build(days: dict, monthly: bool):
    buckets = OrderedDict()
    for iso_date in sorted(days):
        day = date.fromisoformat(iso_date)
        key = period_key(day, monthly)
        bucket = buckets.setdefault(key, {
            "days": 0,
            "fbViews": 0, "fbInteractions": 0, "fbProfileViews": 0, "fbPosts": 0,
            "fbFollowers": None,
            "igViews": 0, "igReach": 0, "igInteractions": 0, "igPosts": 0,
            "igAccountsEngaged": 0, "igFollowers": None,
        })
        bucket["days"] += 1
        entry = days[iso_date]

        fb = entry.get("facebook") or {}
        bucket["fbViews"] += fb.get("views", 0)
        bucket["fbInteractions"] += fb.get("interactions", 0)
        bucket["fbProfileViews"] += fb.get("profileViews", 0)
        bucket["fbPosts"] += fb.get("posts", 0)
        if fb.get("followers") is not None:
            bucket["fbFollowers"] = fb["followers"]

        ig = entry.get("instagram") or {}
        bucket["igViews"] += ig.get("views", 0)
        bucket["igReach"] += ig.get("reach", 0)
        bucket["igInteractions"] += ig.get("interactions", 0)
        bucket["igPosts"] += ig.get("posts", 0)
        bucket["igAccountsEngaged"] += ig.get("accountsEngaged", 0)
        if ig.get("followers") is not None:
            bucket["igFollowers"] = ig["followers"]
    return buckets


def meta_months():
    path = DATA / "history_meta.json"
    if not path.exists():
        raise SystemExit(f"Historie fehlt: {path}\nZuerst backfill_meta_history.py ausfuehren.")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for key in sorted(payload["months"]):
        month = payload["months"][key]
        fb = month["monthTotals"]["facebook"]
        ig = month["monthTotals"]["instagram"]
        rows.append({
            "period": key + (" *" if month.get("partial") else ""),
            "days": month["days"],
            "fbViews": fb["views"], "fbInteractions": fb["interactions"],
            "fbNewFollowers": fb["newFollowers"],
            "igViews": ig["views"], "igReach": ig["reach"],
            "igInteractions": ig["interactions"], "igNewFollowers": ig["newFollowers"],
        })
    return rows


def pct(current, previous):
    if previous in (None, 0) or current is None:
        return ""
    value = (current - previous) / abs(previous) * 100
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.0f}%".replace(".", ",")


def print_table(headers, rows, aligns=None):
    aligns = aligns or [">"] * len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    line = "  ".join(f"{h:{'<' if i == 0 else '>'}{widths[i]}}" for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(
            f"{str(cell):{'<' if i == 0 else '>'}{widths[i]}}"
            for i, cell in enumerate(row)
        ))


def main() -> None:
    parser = argparse.ArgumentParser(description="BWTV Fortschrittsuebersicht")
    parser.add_argument("--monthly", action="store_true", help="Monate statt Wochen")
    parser.add_argument("--meta", action="store_true", help="Monatswerte aus den Meta-Exporten")
    parser.add_argument("--csv", help="Ergebnis zusaetzlich als CSV speichern")
    args = parser.parse_args()

    if args.meta:
        rows = meta_months()
        print("Monatswerte aus der Meta Business Suite (Maerz-Juli 2026)")
        print("Quelle: manuelle Insights-Exporte. IG-Reichweite hier ist Metas")
        print("deduplizierter Zeitraumwert (echte Unique-Reichweite).")
        print("* = unvollstaendiger Monat\n")
        table = []
        prev = None
        for row in rows:
            table.append([
                row["period"], row["days"],
                de_int(row["fbViews"]), pct(row["fbViews"], prev["fbViews"] if prev else None),
                de_int(row["fbInteractions"]), de_int(row["fbNewFollowers"]),
                de_int(row["igViews"]), pct(row["igViews"], prev["igViews"] if prev else None),
                de_int(row["igReach"]), de_int(row["igInteractions"]),
                de_int(row["igNewFollowers"]),
            ])
            prev = row
        print_table(
            ["Monat", "Tage", "FB Aufr.", "±", "FB Int.", "FB +Fol.",
             "IG Aufr.", "±", "IG Reich.", "IG Int.", "IG +Fol."],
            table,
        )
        print("\nHinweis: IG '+Fol.' im Juli (1.823) enthaelt den Einmal-Sprung vom 18.07.")
        return

    buckets = build(load_days(), args.monthly)
    if not buckets:
        raise SystemExit("Keine Daten im Speicher.")

    label = "Monat" if args.monthly else "KW"
    print(f"Fortschritt je {label} — Quelle Metricool (Brand 6061560)")
    print("IG-Reichweite = Summe der Tageswerte, keine eindeutige Personenzahl.\n")

    table = []
    prev = None
    for key, bucket in buckets.items():
        table.append([
            key, bucket["days"],
            de_int(bucket["fbViews"]), pct(bucket["fbViews"], prev["fbViews"] if prev else None),
            de_int(bucket["fbInteractions"]), de_int(bucket["fbPosts"]),
            de_int(bucket["fbFollowers"]),
            de_int(bucket["igViews"]), pct(bucket["igViews"], prev["igViews"] if prev else None),
            de_int(bucket["igReach"]), de_int(bucket["igInteractions"]),
            de_int(bucket["igPosts"]), de_int(bucket["igFollowers"]),
        ])
        prev = bucket

    headers = [label, "Tage", "FB Aufr.", "±", "FB Int.", "FB Bei.", "FB Fol.",
               "IG Aufr.", "±", "IG Reich.", "IG Int.", "IG Bei.", "IG Fol."]
    print_table(headers, table)

    incomplete = [k for k, b in buckets.items() if b["days"] < (28 if args.monthly else 7)]
    if incomplete:
        print(f"\nUnvollstaendige Perioden (weniger Tage im Speicher): {', '.join(incomplete)}")

    if args.csv:
        out = Path(args.csv)
        if not out.is_absolute():
            out = BASE / out
        with out.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow(headers)
            writer.writerows(table)
        print(f"\nCSV geschrieben: {out}")


if __name__ == "__main__":
    main()

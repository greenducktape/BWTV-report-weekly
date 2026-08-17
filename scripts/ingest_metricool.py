#!/usr/bin/env python3
"""
Nimmt die Rohantwort der Metricool-MCP-Abfragen und schreibt sie tagesgenau in
den Datenspeicher (data/metricool_daily.json).

Aufruf:
    python3 scripts/ingest_metricool.py payload.json

Erwartetes Payload-Format (so, wie die MCP-Tools antworten):
{
  "facebook": {
    "metrics": ["FBEV49", "FBEV03", ...],        # Reihenfolge wie angefragt
    "rows":    [["67.0", "5.0", ..., "20260701"], ...]
  },
  "instagram": {
    "metrics": ["IGEV05", "IGEV06", ...],
    "rows":    [["2037.0", "668.0", ..., "20260701"], ...]
  }
}

Metricool liefert pro Zeile die Werte in der angefragten Metrik-Reihenfolge und
das Datum (JJJJMMTT) als letzte Spalte. Fehlende Werte kommen als null - das
bedeutet "an diesem Tag kein Wert" und wird als 0 gespeichert, ausser bei
Bestandsmetriken (Follower), wo null echtes "unbekannt" heisst.
"""

import json
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STORE = DATA_DIR / "metricool_daily.json"

# Metricool-Feld-ID -> interner Name.
FIELD_MAP = {
    # --- Facebook -------------------------------------------------------
    "FBEV49": ("facebook", "views"),          # Page Media View = "Aufrufe"
    "FBEV03": ("facebook", "profileViews"),   # Page Views = "Aufrufe auf Facebook"
    "FBEV47": ("facebook", "newFollowers"),   # Page Followers Acquired
    "FBEV48": ("facebook", "lostFollowers"),
    "FBEV17": ("facebook", "followers"),      # Bestand
    "FBEV33": ("facebook", "posts"),
    "FBEV34": ("facebook", "interactions"),   # Page Posts Interactions (Posts+Reels)
    "FBEV11": ("facebook", "reachPerPost"),   # Tages-Durchschnitt je Beitrag
    "FBEV16": ("facebook", "postClicks"),
    # --- Instagram ------------------------------------------------------
    "IGEV05": ("instagram", "views"),
    "IGEV06": ("instagram", "reach"),         # Tageswert, NICHT ueber Zeitraum dedupliziert
    "IGEV38": ("instagram", "interactions"),  # Account Posts Interactions (Posts+Reels)
    "IGEV03": ("instagram", "newFollowers"),  # Netto-Saldo pro Tag
    "IGEV01": ("instagram", "followers"),     # Bestand
    "IGEV37": ("instagram", "posts"),
    "IGEV42": ("instagram", "accountsEngaged"),
    "IGEV16": ("instagram", "stories"),
    "IGEV22": ("instagram", "reels"),
}

# Bestandsmetriken: null bedeutet "unbekannt", nicht 0.
STOCK_METRICS = {"followers"}


def to_number(raw):
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    return int(value) if value.is_integer() else round(value, 4)


def parse_block(block, network_hint):
    """Wandelt {'metrics': [...], 'rows': [...]} in {datum: {feld: wert}} um."""
    metrics = block["metrics"]
    per_day = {}
    for row in block["rows"]:
        if len(row) != len(metrics) + 1:
            raise SystemExit(
                f"Zeile hat {len(row)} Spalten, erwartet {len(metrics) + 1} "
                f"({len(metrics)} Metriken + Datum): {row}"
            )
        raw_date = str(row[-1])
        if len(raw_date) != 8 or not raw_date.isdigit():
            raise SystemExit(f"Unerwartetes Datumsformat in letzter Spalte: {raw_date!r}")
        date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"

        values = {}
        for field_id, raw in zip(metrics, row[:-1]):
            mapped = FIELD_MAP.get(field_id)
            if mapped is None:
                continue
            network, name = mapped
            if network != network_hint:
                continue
            number = to_number(raw)
            if number is None and name not in STOCK_METRICS:
                number = 0
            if number is not None:
                values[name] = number
        per_day[date] = values
    return per_day


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if STORE.exists():
        store = json.loads(STORE.read_text(encoding="utf-8"))
    else:
        store = {
            "source": "metricool",
            "brandId": 6061560,
            "brand": "BWTV - Baden-Wuerttemberg Triathlon-Verband",
            "note": (
                "Tageswerte aus der Metricool-API. 'reach' ist ein Tageswert und darf "
                "nur als 'Summe Tageswerte' aggregiert werden, nicht als Unique-Reichweite. "
                "Interaktionen zaehlen nach Metricool-Definition (Beitraege des Zeitraums) "
                "und liegen daher unter den Werten der Meta Business Suite."
            ),
            "days": {},
        }

    days = store.setdefault("days", {})
    touched, created = set(), 0
    for network in ("facebook", "instagram"):
        block = payload.get(network)
        if not block:
            continue
        for date, values in parse_block(block, network).items():
            if date not in days:
                days[date] = {}
                created += 1
            days[date].setdefault(network, {}).update(values)
            touched.add(date)

    store["days"] = dict(sorted(days.items()))
    STORE.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")

    span = f"{min(touched)} bis {max(touched)}" if touched else "keine"
    print(f"{STORE.name}: {len(touched)} Tage aktualisiert ({created} neu), Zeitraum {span}")
    print(f"Speicher enthaelt jetzt {len(store['days'])} Tage.")


if __name__ == "__main__":
    main()

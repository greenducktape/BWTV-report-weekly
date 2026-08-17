#!/usr/bin/env python3
"""
Baut das BWTV-Social-Media-Dashboard als eigenstaendige index.html.

Aufruf:
    python3 scripts/build_site.py
    python3 scripts/build_site.py --out site/index.html --today 2026-08-17

Aufbau der Seite:
  1. Aktueller Monat (Monat-bis-heute) gegen denselben Zeitraum des Vormonats
  2. Entwicklung als Diagramm - umschaltbar Woche/Monat, je Netzwerk ein
     eigenes Panel mit eigener Skala (nie zwei y-Achsen in einem Chart)
  3. Monatsarchiv - jeder abgeschlossene Monat einzeln abrufbar

Alle Daten werden als JSON in die Seite eingebettet; die Datei laeuft ohne
Server, ohne externe Skripte und ohne Netzwerkzugriff.
"""

import argparse
import base64
import json
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
ASSETS = BASE / "assets"

MONTHS_DE = ["Januar", "Februar", "März", "April", "Mai", "Juni",
             "Juli", "August", "September", "Oktober", "November", "Dezember"]
MONTHS_DE_SHORT = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
                   "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]

FB_COLOR = "#0866ff"
IG_COLOR = "#d6246e"
BWTV_CYAN = "#00adeb"
BWTV_ORANGE = "#f18d5a"

SUMMED = ("views", "reach", "interactions", "profileViews", "newFollowers",
          "posts", "accountsEngaged")


# ---------------------------------------------------------------------------

def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def aggregate(days: dict, network: str, start: date, end: date) -> dict:
    out = {key: 0 for key in SUMMED}
    out["daysWithData"] = 0
    first_stock = last_stock = None
    for day in daterange(start, end):
        entry = days.get(day.isoformat())
        if not entry:
            continue
        block = entry.get(network)
        if not block:
            continue
        out["daysWithData"] += 1
        for key in SUMMED:
            value = block.get(key)
            if value is not None:
                out[key] += value
        stock = block.get("followers")
        if stock is not None:
            if first_stock is None:
                first_stock = stock
            last_stock = stock
    out["followers"] = last_stock
    out["followersStart"] = first_stock
    out["followersDelta"] = (None if first_stock is None or last_stock is None
                             else last_stock - first_stock)
    return out


def month_span(year: int, month: int):
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def prev_month(year: int, month: int):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def build_months(days: dict, last_data: date):
    keys = sorted({d[:7] for d in days})
    out = []
    for key in keys:
        year, month = int(key[:4]), int(key[5:7])
        start, end = month_span(year, month)
        effective_end = min(end, last_data)
        complete = end <= last_data
        py, pm = prev_month(year, month)
        p_start, p_end = month_span(py, pm)
        # Vergleichsfenster gleicher Laenge im Vormonat
        length = (effective_end - start).days
        p_effective_end = min(p_start + timedelta(days=length), p_end)
        out.append({
            "key": key,
            "label": f"{MONTHS_DE[month - 1]} {year}",
            "labelShort": f"{MONTHS_DE_SHORT[month - 1]} {str(year)[2:]}",
            "start": start.isoformat(),
            "end": effective_end.isoformat(),
            "complete": complete,
            "prevKey": f"{py}-{pm:02d}",
            "prevStart": p_start.isoformat(),
            "prevEnd": p_effective_end.isoformat(),
            "facebook": aggregate(days, "facebook", start, effective_end),
            "instagram": aggregate(days, "instagram", start, effective_end),
            "prevFacebook": aggregate(days, "facebook", p_start, p_effective_end),
            "prevInstagram": aggregate(days, "instagram", p_start, p_effective_end),
        })
    return out


def build_weeks(days: dict, last_data: date):
    seen = {}
    for iso_date in days:
        day = date.fromisoformat(iso_date)
        iso = day.isocalendar()
        seen.setdefault((iso.year, iso.week), 0)
        seen[(iso.year, iso.week)] += 1
    out = []
    for (year, week) in sorted(seen):
        monday = date.fromisocalendar(year, week, 1)
        sunday = monday + timedelta(days=6)
        effective_end = min(sunday, last_data)
        out.append({
            "key": f"{year}-W{week:02d}",
            "label": f"KW {week}",
            "labelShort": f"{week}",
            "start": monday.isoformat(),
            "end": effective_end.isoformat(),
            "complete": seen[(year, week)] >= 7,
            "days": seen[(year, week)],
            "facebook": aggregate(days, "facebook", monday, effective_end),
            "instagram": aggregate(days, "instagram", monday, effective_end),
        })
    return out


def logo_data_uri(name: str) -> str:
    path = ASSETS / name
    if not path.exists():
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def de_date(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


# ---------------------------------------------------------------------------

def render(payload: dict) -> str:
    data_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    logo = logo_data_uri("bwtv-liga-white.svg")
    logo_html = (f'<img class="logo" src="{logo}" alt="BWTV Triathlonliga">'
                 if logo else '<span class="logo logo--text">BWTV</span>')

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BWTV Social Media Dashboard</title>
<meta name="description" content="Social-Media-Performance des Baden-Württemberg Triathlon-Verbands auf Facebook und Instagram – monatlich und wöchentlich.">
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  :root {{
    --ink: #16121f;
    --ink-soft: #5b5470;
    --ink-faint: #8b849c;
    --surface: #ffffff;
    --surface-alt: #f5f4f8;
    --line: #e6e3ee;
    --line-soft: #f0eef5;
    --good-bg: #e6f6e9;  --good-fg: #1c7a33;
    --bad-bg:  #fdeaf0;  --bad-fg:  #c2185b;
    --flat-bg: #eeecf3;  --flat-fg: #5b5470;
    --fb: {FB_COLOR};
    --ig: {IG_COLOR};
    --cyan: {BWTV_CYAN};
    --orange: {BWTV_ORANGE};
  }}
  body {{
    margin: 0; background: #eceaf2; color: var(--ink);
    font: 400 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    padding: 26px 16px 46px;
  }}
  .sheet {{
    max-width: 1240px; margin: 0 auto; background: var(--surface);
    border-radius: 22px; overflow: hidden;
    box-shadow: 0 18px 48px rgba(22,18,31,.13);
  }}

  /* ---------- Kopf ---------- */
  .masthead {{
    background: linear-gradient(102deg, #17102b 0%, #241634 52%, #2f1a3a 100%);
    color: #fff; padding: 26px 34px 24px;
    display: flex; flex-wrap: wrap; gap: 20px;
    align-items: center; justify-content: space-between;
  }}
  .brand {{ display: flex; align-items: center; gap: 18px; min-width: 0; }}
  .logo {{ height: 54px; width: auto; flex: none; }}
  .logo--text {{ font-weight: 800; font-size: 26px; letter-spacing: .06em; }}
  .brand__text h1 {{ margin: 0; font-size: clamp(21px,2.5vw,29px); font-weight: 800; letter-spacing: -.015em; }}
  .brand__text p {{ margin: 3px 0 0; font-size: 14px; color: #c9c1dd; }}
  .stand {{ text-align: right; flex: none; }}
  .stand__eyebrow {{
    margin: 0; font-size: 10.5px; font-weight: 700; letter-spacing: .17em;
    text-transform: uppercase; color: #a99fc4;
  }}
  .stand__main {{ margin: 4px 0 0; font-size: clamp(18px,2.1vw,25px); font-weight: 800; }}
  .stand__sub {{ margin: 3px 0 0; font-size: 12.5px; color: #b3aac9; }}
  .rule {{ display: flex; height: 6px; }}
  .rule i {{ flex: 1; }}

  /* ---------- Sektionen ---------- */
  .content {{ padding: 0 34px 30px; }}
  section.block {{ padding-top: 30px; }}
  section.block + section.block {{
    margin-top: 30px; border-top: 1px solid var(--line);
  }}
  .block__head {{ margin-bottom: 16px; }}
  .block__kicker {{
    margin: 0; font-size: 11px; font-weight: 700; letter-spacing: .15em;
    text-transform: uppercase; color: var(--ink-faint);
  }}
  .block__title {{ margin: 5px 0 0; font-size: 22px; font-weight: 800; letter-spacing: -.01em; }}
  .block__sub {{ margin: 5px 0 0; font-size: 14px; color: var(--ink-soft); }}

  .callout {{
    border-left: 4px solid var(--cyan);
    background: linear-gradient(96deg, rgba(214,36,110,.07), rgba(0,173,235,.07));
    border-radius: 0 12px 12px 0; padding: 14px 18px;
    font-size: 14px; color: #3c3550; margin-bottom: 20px;
  }}
  .callout strong {{ color: var(--ink); }}

  /* ---------- Karten ---------- */
  .cards {{ display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(390px,1fr)); }}
  .card {{
    background: var(--surface-alt); border: 1px solid var(--line);
    border-radius: 16px; padding: 20px 22px 8px;
  }}
  .card__head {{ display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 6px; }}
  .card__icon {{
    width: 34px; height: 34px; border-radius: 10px; flex: none;
    background: var(--accent); display: grid; place-items: center;
  }}
  .card__icon svg {{ width: 21px; height: 21px; display: block; }}
  .card__title {{ margin: 0; font-size: 21px; font-weight: 800; color: var(--accent); letter-spacing: -.01em; }}
  .follower-pill {{
    margin-left: auto; flex: none; background: #fff; border: 1px solid var(--line);
    border-radius: 999px; padding: 6px 13px; font-size: 12.5px; font-weight: 700; color: var(--ink-soft);
  }}
  .follower-pill em {{ font-style: normal; font-weight: 500; color: var(--ink-faint); }}
  .follower-pill--good {{ color: var(--good-fg); border-color: #bfe6c8; }}
  .follower-pill--bad  {{ color: var(--bad-fg);  border-color: #f6ccdb; }}

  table.metrics {{ width: 100%; border-collapse: collapse; }}
  .metrics thead th {{
    font-size: 10.5px; font-weight: 700; letter-spacing: .13em; text-transform: uppercase;
    color: var(--ink-faint); text-align: left; padding: 12px 8px 9px; border-bottom: 1px solid var(--line);
  }}
  .metrics tbody th {{
    text-align: left; font-size: 14.5px; font-weight: 700; padding: 13px 8px;
    border-bottom: 1px solid var(--line);
  }}
  .metrics tbody tr:last-child th, .metrics tbody tr:last-child td {{ border-bottom: 0; }}
  .metrics td {{ padding: 13px 8px; border-bottom: 1px solid var(--line); font-variant-numeric: tabular-nums; }}
  .num {{ text-align: right; font-size: 15px; color: var(--ink-soft); }}
  .num--current {{ font-weight: 800; font-size: 16.5px; color: var(--ink); }}
  .delta {{ text-align: right; white-space: nowrap; }}
  .metric-note {{
    display: block; font-size: 11.5px; font-weight: 400; color: var(--ink-faint);
    margin-top: 2px; max-width: 30ch;
  }}
  .pill {{
    display: inline-block; border-radius: 999px; padding: 4px 10px;
    font-size: 12.5px; font-weight: 800; font-variant-numeric: tabular-nums;
  }}
  .pill--good {{ background: var(--good-bg); color: var(--good-fg); }}
  .pill--bad  {{ background: var(--bad-bg);  color: var(--bad-fg); }}
  .pill--flat {{ background: var(--flat-bg); color: var(--flat-fg); }}

  /* ---------- Steuerung ---------- */
  .controls {{ display: flex; flex-wrap: wrap; gap: 10px 22px; align-items: flex-end; margin-bottom: 18px; }}
  .control__label {{
    display: block; font-size: 10.5px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: var(--ink-faint); margin-bottom: 6px;
  }}
  .segmented {{
    display: inline-flex; background: var(--surface-alt); border: 1px solid var(--line);
    border-radius: 10px; padding: 3px; gap: 2px;
  }}
  .segmented button {{
    appearance: none; border: 0; background: transparent; cursor: pointer;
    font: 600 13.5px/1 inherit; color: var(--ink-soft);
    padding: 8px 14px; border-radius: 8px; white-space: nowrap;
  }}
  .segmented button:hover {{ color: var(--ink); }}
  .segmented button[aria-pressed="true"] {{ background: #fff; color: var(--ink); box-shadow: 0 1px 3px rgba(22,18,31,.12); font-weight: 700; }}
  .segmented button:focus-visible {{ outline: 2px solid var(--cyan); outline-offset: 1px; }}

  /* ---------- Diagramme ---------- */
  .charts {{ display: grid; gap: 20px; grid-template-columns: repeat(auto-fit, minmax(400px,1fr)); }}
  .panel {{
    background: var(--surface-alt); border: 1px solid var(--line);
    border-radius: 16px; padding: 18px 20px 14px; min-width: 0;
  }}
  .panel__head {{ display: flex; align-items: baseline; gap: 9px; margin-bottom: 2px; }}
  .panel__dot {{ width: 10px; height: 10px; border-radius: 3px; background: var(--accent); flex: none; }}
  .panel__title {{ margin: 0; font-size: 15px; font-weight: 800; }}
  .panel__value {{ margin: 2px 0 0; font-size: 27px; font-weight: 800; letter-spacing: -.02em; font-variant-numeric: tabular-nums; }}
  .panel__meta {{ margin: 1px 0 10px; font-size: 12.5px; color: var(--ink-faint); }}
  .chart {{ position: relative; }}
  .chart svg {{ display: block; width: 100%; height: auto; overflow: visible; }}
  .bar {{ transition: opacity .12s; }}
  .bar--partial {{ opacity: .42; }}
  .chart-empty {{
    padding: 26px 4px; font-size: 13.5px; color: var(--ink-faint);
    border: 1px dashed var(--line); border-radius: 12px; text-align: center;
  }}
  .tip {{
    position: absolute; pointer-events: none; z-index: 5;
    background: #17102b; color: #fff; border-radius: 9px;
    padding: 8px 11px; font-size: 12.5px; line-height: 1.45;
    box-shadow: 0 6px 18px rgba(22,18,31,.28);
    opacity: 0; transform: translate(-50%, -100%); transition: opacity .1s;
    white-space: nowrap;
  }}
  .tip[data-show="1"] {{ opacity: 1; }}
  .tip b {{ font-variant-numeric: tabular-nums; }}
  .tip i {{ font-style: normal; color: #b3aac9; }}

  details.tablewrap {{ margin-top: 14px; }}
  details.tablewrap summary {{
    cursor: pointer; font-size: 12.5px; font-weight: 700; color: var(--ink-soft);
    padding: 6px 0;
  }}
  details.tablewrap summary:focus-visible {{ outline: 2px solid var(--cyan); outline-offset: 2px; }}
  .scroller {{ overflow-x: auto; margin-top: 8px; }}
  table.raw {{ border-collapse: collapse; font-size: 13px; min-width: 100%; }}
  table.raw th, table.raw td {{
    padding: 7px 11px; text-align: right; white-space: nowrap;
    border-bottom: 1px solid var(--line-soft); font-variant-numeric: tabular-nums;
  }}
  table.raw th:first-child, table.raw td:first-child {{ text-align: left; }}
  table.raw thead th {{
    font-size: 10.5px; letter-spacing: .1em; text-transform: uppercase;
    color: var(--ink-faint); border-bottom: 1px solid var(--line);
  }}
  table.raw tbody tr.partial td, table.raw tbody tr.partial th {{ color: var(--ink-faint); }}

  .hint {{ margin: 14px 0 0; font-size: 12.5px; color: var(--ink-faint); }}
  .hint code {{
    background: var(--surface-alt); border: 1px solid var(--line);
    border-radius: 5px; padding: 1px 5px; font-size: 12px;
  }}

  .sheet__foot {{
    border-top: 1px solid var(--line); padding: 15px 34px 17px;
    display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between;
    font-size: 12px; color: var(--ink-faint);
  }}
  .sheet__foot b {{ color: var(--ink-soft); }}
  noscript p {{
    margin: 0 0 18px; padding: 13px 16px; border-radius: 10px;
    background: var(--bad-bg); color: var(--bad-fg); font-size: 14px;
  }}

  @media (max-width: 760px) {{
    body {{ padding: 12px 9px 30px; }}
    .masthead, .content, .sheet__foot {{ padding-left: 18px; padding-right: 18px; }}
    .stand {{ text-align: left; }}
    .cards, .charts {{ grid-template-columns: 1fr; }}
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .sheet {{ box-shadow: none; border-radius: 0; max-width: none; }}
    .controls, details.tablewrap {{ display: none; }}
  }}
</style>
</head>
<body>
<main class="sheet">
  <header class="masthead">
    <div class="brand">
      {logo_html}
      <div class="brand__text">
        <h1>Social Media Dashboard</h1>
        <p>Facebook &amp; Instagram · Baden-Württemberg Triathlon-Verband</p>
      </div>
    </div>
    <div class="stand">
      <p class="stand__eyebrow">Datenstand</p>
      <p class="stand__main" id="standMain">–</p>
      <p class="stand__sub" id="standSub">–</p>
    </div>
  </header>
  <div class="rule">
    <i style="background:var(--ig)"></i>
    <i style="background:var(--cyan)"></i>
    <i style="background:var(--orange)"></i>
  </div>

  <div class="content">
    <noscript><p>Für die Filter und Diagramme wird JavaScript benötigt. Die Zahlen des aktuellen Monats stehen auch im Monatsarchiv der Rohdatentabelle.</p></noscript>

    <!-- 1. Aktueller Monat -->
    <section class="block" id="current">
      <div class="block__head">
        <p class="block__kicker">Wöchentlicher Report</p>
        <h2 class="block__title" id="currentTitle">Aktueller Monat</h2>
        <p class="block__sub" id="currentSub"></p>
      </div>
      <p class="callout" id="currentFraming"></p>
      <div class="cards" id="currentCards"></div>
    </section>

    <!-- 2. Entwicklung -->
    <section class="block" id="evolution">
      <div class="block__head">
        <p class="block__kicker">Entwicklung</p>
        <h2 class="block__title">Verlauf über die Zeit</h2>
        <p class="block__sub">Facebook und Instagram in getrennten Panels – die Größenordnungen
          unterscheiden sich um mehr als das Zehnfache, eine gemeinsame Skala würde Facebook unsichtbar machen.</p>
      </div>
      <div class="controls">
        <div>
          <span class="control__label" id="lblGran">Zeitraster</span>
          <div class="segmented" role="group" aria-labelledby="lblGran" id="granControl">
            <button type="button" data-gran="weekly" aria-pressed="false">Wöchentlich</button>
            <button type="button" data-gran="monthly" aria-pressed="true">Monatlich</button>
          </div>
        </div>
        <div>
          <span class="control__label" id="lblMetric">Kennzahl</span>
          <div class="segmented" role="group" aria-labelledby="lblMetric" id="metricControl"></div>
        </div>
      </div>
      <div class="charts" id="charts"></div>
      <details class="tablewrap">
        <summary>Zahlen als Tabelle anzeigen</summary>
        <div class="scroller" id="evolutionTable"></div>
      </details>
      <p class="hint" id="evolutionHint"></p>
    </section>

    <!-- 3. Monatsarchiv -->
    <section class="block" id="archive">
      <div class="block__head">
        <p class="block__kicker">Monatsarchiv</p>
        <h2 class="block__title">Einzelne Monate</h2>
        <p class="block__sub">Jeder Monat im Vergleich zum Vormonat – gleiche Zeitraumlänge.</p>
      </div>
      <div class="controls">
        <div>
          <span class="control__label" id="lblMonth">Monat</span>
          <div class="segmented" role="group" aria-labelledby="lblMonth" id="monthControl"></div>
        </div>
      </div>
      <p class="callout" id="archiveFraming"></p>
      <div class="cards" id="archiveCards"></div>
    </section>
  </div>

  <footer class="sheet__foot">
    <span>Quelle: Metricool (Brand <span id="brandId"></span>) · erzeugt <span id="builtAt"></span></span>
    <span><b>BWTV</b> — Baden-Württemberg Triathlon-Verband</span>
  </footer>
</main>

<script type="application/json" id="payload">{data_json}</script>
<script>
(function () {{
  "use strict";
  var D = JSON.parse(document.getElementById("payload").textContent);

  var MONTHS = ["Januar","Februar","März","April","Mai","Juni","Juli","August",
                "September","Oktober","November","Dezember"];
  var COLORS = {{ facebook: "{FB_COLOR}", instagram: "{IG_COLOR}" }};
  var NAMES  = {{ facebook: "Facebook", instagram: "Instagram" }};

  // ---- Formatierung ----------------------------------------------------
  function nf(v) {{
    if (v === null || v === undefined) return "–";
    return Math.round(v).toLocaleString("de-DE");
  }}
  function pf(v) {{
    if (v === null || v === undefined) return "–";
    return v.toLocaleString("de-DE", {{ minimumFractionDigits: 1, maximumFractionDigits: 1 }}) + " %";
  }}
  function sf(v) {{
    if (v === null || v === undefined) return "–";
    return (v > 0 ? "+" : "") + Math.round(v).toLocaleString("de-DE");
  }}
  function parseISO(s) {{
    var p = s.split("-");
    return new Date(+p[0], +p[1] - 1, +p[2]);
  }}
  function dmy(s) {{
    var d = parseISO(s);
    return String(d.getDate()).padStart(2, "0") + "." +
           String(d.getMonth() + 1).padStart(2, "0") + "." + d.getFullYear();
  }}
  function rangeLabel(a, b) {{
    var x = parseISO(a), y = parseISO(b);
    var dd = function (d) {{ return String(d.getDate()).padStart(2, "0"); }};
    if (x.getMonth() === y.getMonth() && x.getFullYear() === y.getFullYear())
      return dd(x) + ".–" + dd(y) + ". " + MONTHS[y.getMonth()] + " " + y.getFullYear();
    if (x.getFullYear() === y.getFullYear())
      return dd(x) + ". " + MONTHS[x.getMonth()] + " – " + dd(y) + ". " + MONTHS[y.getMonth()] + " " + y.getFullYear();
    return dmy(a) + " – " + dmy(b);
  }}
  function esc(s) {{
    return String(s).replace(/[&<>"']/g, function (c) {{
      return {{ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }}[c];
    }});
  }}

  function change(cur, prev) {{
    if (cur === null || cur === undefined || prev === null || prev === undefined) return null;
    if (prev === 0) return null;
    return (cur - prev) / Math.abs(prev) * 100;
  }}

  // ---- Karten ----------------------------------------------------------
  var ICONS = {{
    facebook: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#fff" d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.8-.1-1.7-.15-2.5-.15-2.5 0-4.2 1.5-4.2 4.3v2.15H7.3V13h2.25v8h3.95Z"/></svg>',
    instagram: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="#fff" stroke-width="2"/><circle cx="17.1" cy="6.9" r="1.35" fill="#fff"/></svg>'
  }};

  var ROWS = {{
    facebook: [
      {{ label: "Aufrufe", key: "views", dir: "up" }},
      {{ label: "Interaktionen", key: "interactions", dir: "up" }},
      {{ label: "Profilaufrufe", key: "profileViews", dir: "up" }},
      {{ label: "Beiträge", key: "posts", dir: "neutral" }},
      {{ label: "Neue Follower", key: "newFollowers", dir: "up" }}
    ],
    instagram: [
      {{ label: "Aufrufe", key: "views", dir: "up" }},
      {{ label: "Reichweite", key: "reach", dir: "up",
        note: "Summe der Tageswerte – keine eindeutige Personenzahl" }},
      {{ label: "Interaktionen", key: "interactions", dir: "up" }},
      {{ label: "Aktive Konten", key: "accountsEngaged", dir: "up",
        note: "Konten, die mit dem Content interagiert haben" }},
      {{ label: "Beiträge", key: "posts", dir: "neutral" }}
    ]
  }};

  function pill(cur, prev, dir) {{
    var c = change(cur, prev);
    if (c === null) {{
      if (cur === null || prev === null || cur === prev) return '<span class="pill pill--flat">–</span>';
      var rising0 = cur > prev;
      var tone0 = dir === "neutral" ? "flat" : ((rising0 === (dir === "up")) ? "good" : "bad");
      return '<span class="pill pill--' + tone0 + '">' + (rising0 ? "▲" : "▼") + " " + sf(cur - prev) + "</span>";
    }}
    if (Math.abs(c) < 0.05) return '<span class="pill pill--flat">±0,0 %</span>';
    var rising = c > 0;
    var tone = dir === "neutral" ? "flat" : ((rising === (dir === "up")) ? "good" : "bad");
    return '<span class="pill pill--' + tone + '">' + (rising ? "▲" : "▼") + " " + pf(Math.abs(c)) + "</span>";
  }}

  function card(network, cur, prev, labelCur, labelPrev) {{
    var rows = ROWS[network].map(function (r) {{
      var note = r.note ? '<span class="metric-note">' + esc(r.note) + "</span>" : "";
      return "<tr><th scope=\\"row\\">" + esc(r.label) + note + "</th>" +
             '<td class="num">' + nf(prev[r.key]) + "</td>" +
             '<td class="num num--current">' + nf(cur[r.key]) + "</td>" +
             '<td class="delta">' + pill(cur[r.key], prev[r.key], r.dir) + "</td></tr>";
    }}).join("");

    var d = cur.followersDelta, fp;
    if (d === null || d === undefined) {{
      fp = '<span class="follower-pill">Followerstand ' + nf(cur.followers) + "</span>";
    }} else {{
      var tone = d > 0 ? "good" : (d < 0 ? "bad" : "flat");
      fp = '<span class="follower-pill follower-pill--' + tone + '">' + sf(d) +
           " Follower <em>· " + nf(cur.followers) + " gesamt</em></span>";
    }}

    return '<section class="card" style="--accent:' + COLORS[network] + '">' +
      '<header class="card__head"><span class="card__icon">' + ICONS[network] + "</span>" +
      '<h3 class="card__title">' + NAMES[network] + "</h3>" + fp + "</header>" +
      '<table class="metrics"><thead><tr><th scope="col">Kennzahl</th>' +
      '<th scope="col" class="num">' + esc(labelPrev) + "</th>" +
      '<th scope="col" class="num">' + esc(labelCur) + "</th>" +
      '<th scope="col" class="delta">Veränd.</th></tr></thead><tbody>' +
      rows + "</tbody></table></section>";
  }}

  // ---- Diagramm --------------------------------------------------------
  var METRICS = [
    {{ key: "views", label: "Aufrufe", networks: ["facebook", "instagram"], stock: false }},
    {{ key: "interactions", label: "Interaktionen", networks: ["facebook", "instagram"], stock: false }},
    {{ key: "posts", label: "Beiträge", networks: ["facebook", "instagram"], stock: false }},
    {{ key: "followers", label: "Follower", networks: ["facebook", "instagram"], stock: true }},
    {{ key: "reach", label: "Reichweite", networks: ["instagram"], stock: false,
       missing: "Metricool liefert für Facebook-Seiten keine vergleichbare Reichweite – nur einen Durchschnitt je Beitrag." }},
    {{ key: "profileViews", label: "Profilaufrufe", networks: ["facebook"], stock: false,
       missing: "Die Instagram-Profilaufrufe hat Meta abgekündigt; Metricool liefert dafür keinen belastbaren Wert mehr." }}
  ];

  var state = {{ gran: "monthly", metric: "views", month: null }};

  function periods() {{ return state.gran === "weekly" ? D.weeks : D.months; }}

  function niceMax(v) {{
    if (v <= 0) return 1;
    var mag = Math.pow(10, Math.floor(Math.log10(v)));
    var n = v / mag;
    var step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10;
    return step * mag;
  }}

  function chartSVG(network, metric) {{
    var list = periods();
    var pts = list.map(function (p) {{
      return {{
        label: p.labelShort, full: p.label, start: p.start, end: p.end,
        complete: p.complete,
        value: metric.stock ? p[network].followers : p[network][metric.key]
      }};
    }});
    var withData = pts.filter(function (p) {{ return p.value !== null && p.value !== undefined; }});
    if (!withData.length) return null;

    // Bestandsmetriken erst ab dem ersten bekannten Wert zeigen.
    if (metric.stock) {{
      var firstIdx = pts.findIndex(function (p) {{ return p.value !== null && p.value !== undefined; }});
      pts = pts.slice(firstIdx);
    }}

    var W = 560, H = 210, padL = 52, padR = 10, padT = 12, padB = 30;
    var innerW = W - padL - padR, innerH = H - padT - padB;
    var maxV = niceMax(Math.max.apply(null, withData.map(function (p) {{ return p.value; }})));
    var minV = 0;
    if (metric.stock) {{
      var vals = withData.map(function (p) {{ return p.value; }});
      var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
      var pad = Math.max(1, (hi - lo) * 0.18);
      minV = Math.max(0, Math.floor((lo - pad) / 100) * 100);
      maxV = Math.ceil((hi + pad) / 100) * 100;
    }}
    var span = maxV - minV || 1;
    var y = function (v) {{ return padT + innerH - ((v - minV) / span) * innerH; }};

    var n = pts.length;
    var slot = innerW / n;
    var barW = Math.max(3, Math.min(30, slot - 2)); // 2px Abstand zwischen Balken
    var ticks = [minV, minV + span / 2, maxV];

    var parts = [];
    parts.push('<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-label="' +
               esc(NAMES[network] + " – " + metric.label + " je " +
                   (state.gran === "weekly" ? "Kalenderwoche" : "Monat")) + '">');

    ticks.forEach(function (t) {{
      parts.push('<line x1="' + padL + '" y1="' + y(t).toFixed(1) + '" x2="' + (W - padR) +
                 '" y2="' + y(t).toFixed(1) + '" stroke="#e6e3ee" stroke-width="1"/>');
      parts.push('<text x="' + (padL - 8) + '" y="' + (y(t) + 4).toFixed(1) +
                 '" text-anchor="end" font-size="10.5" fill="#8b849c">' +
                 (t >= 10000 ? Math.round(t / 1000) + "k" : nf(t)) + "</text>");
    }});

    var labelEvery = Math.ceil(n / 9);
    pts.forEach(function (p, i) {{
      var cx = padL + slot * i + slot / 2;
      if (p.value !== null && p.value !== undefined) {{
        if (metric.stock) {{
          parts.push('<circle class="bar' + (p.complete ? "" : " bar--partial") +
                     '" cx="' + cx.toFixed(1) + '" cy="' + y(p.value).toFixed(1) +
                     '" r="4.5" fill="' + COLORS[network] + '" stroke="#f5f4f8" stroke-width="2"' +
                     ' data-i="' + i + '"/>');
        }} else {{
          var h = Math.max(1, padT + innerH - y(p.value));
          parts.push('<rect class="bar' + (p.complete ? "" : " bar--partial") +
                     '" x="' + (cx - barW / 2).toFixed(1) + '" y="' + y(p.value).toFixed(1) +
                     '" width="' + barW.toFixed(1) + '" height="' + h.toFixed(1) +
                     '" rx="' + Math.min(4, barW / 2).toFixed(1) + '" fill="' + COLORS[network] +
                     '" data-i="' + i + '"/>');
        }}
      }}
      if (i % labelEvery === 0 || i === n - 1) {{
        parts.push('<text x="' + cx.toFixed(1) + '" y="' + (H - 10) +
                   '" text-anchor="middle" font-size="10.5" fill="#8b849c">' + esc(p.label) + "</text>");
      }}
      // unsichtbares, groesseres Trefferfeld
      parts.push('<rect x="' + (padL + slot * i).toFixed(1) + '" y="' + padT +
                 '" width="' + slot.toFixed(1) + '" height="' + innerH +
                 '" fill="transparent" data-i="' + i + '" class="hit"/>');
    }});

    if (metric.stock) {{
      var line = pts.filter(function (p) {{ return p.value !== null && p.value !== undefined; }})
        .map(function (p) {{
          var i = pts.indexOf(p);
          return (padL + slot * i + slot / 2).toFixed(1) + "," + y(p.value).toFixed(1);
        }}).join(" ");
      parts.splice(1 + ticks.length * 2, 0,
        '<polyline points="' + line + '" fill="none" stroke="' + COLORS[network] +
        '" stroke-width="2" stroke-linejoin="round"/>');
    }}

    parts.push('<line x1="' + padL + '" y1="' + (padT + innerH) + '" x2="' + (W - padR) +
               '" y2="' + (padT + innerH) + '" stroke="#d5d1e0" stroke-width="1"/>');
    parts.push("</svg>");
    return {{ svg: parts.join(""), pts: pts, total: withData.reduce(function (a, p) {{ return a + p.value; }}, 0) }};
  }}

  function renderCharts() {{
    var metric = METRICS.filter(function (m) {{ return m.key === state.metric; }})[0];
    var host = document.getElementById("charts");
    host.innerHTML = "";

    ["facebook", "instagram"].forEach(function (network) {{
      var panel = document.createElement("section");
      panel.className = "panel";
      panel.style.setProperty("--accent", COLORS[network]);

      if (metric.networks.indexOf(network) === -1) {{
        panel.innerHTML = '<div class="panel__head"><span class="panel__dot"></span>' +
          '<h3 class="panel__title">' + NAMES[network] + "</h3></div>" +
          '<p class="panel__meta">' + esc(metric.label) + " – nicht verfügbar</p>" +
          '<div class="chart-empty">' + esc(metric.missing || "Für dieses Netzwerk liegt diese Kennzahl nicht vor.") + "</div>";
        host.appendChild(panel);
        return;
      }}

      var built = chartSVG(network, metric);
      if (!built) {{
        panel.innerHTML = '<div class="panel__head"><span class="panel__dot"></span>' +
          '<h3 class="panel__title">' + NAMES[network] + "</h3></div>" +
          '<div class="chart-empty">Keine Daten für diese Kennzahl.</div>';
        host.appendChild(panel);
        return;
      }}

      var last = built.pts[built.pts.length - 1];
      var headline = metric.stock ? nf(last.value) : nf(built.total);
      var meta = metric.stock
        ? "Stand " + dmy(last.end) + " · Verlauf je " + (state.gran === "weekly" ? "Kalenderwoche" : "Monat")
        : "Summe über alle dargestellten " + (state.gran === "weekly" ? "Wochen" : "Monate");

      panel.innerHTML = '<div class="panel__head"><span class="panel__dot"></span>' +
        '<h3 class="panel__title">' + NAMES[network] + " · " + esc(metric.label) + "</h3></div>" +
        '<p class="panel__value">' + headline + "</p>" +
        '<p class="panel__meta">' + esc(meta) + "</p>" +
        '<div class="chart">' + built.svg + '<div class="tip" role="status"></div></div>';
      host.appendChild(panel);

      // Hover
      var chart = panel.querySelector(".chart");
      var tip = panel.querySelector(".tip");
      var svg = panel.querySelector("svg");
      svg.addEventListener("mousemove", function (ev) {{
        var target = ev.target.closest("[data-i]");
        if (!target) {{ tip.dataset.show = "0"; return; }}
        var p = built.pts[+target.dataset.i];
        if (!p || p.value === null || p.value === undefined) {{ tip.dataset.show = "0"; return; }}
        var box = chart.getBoundingClientRect();
        tip.innerHTML = "<b>" + nf(p.value) + "</b> " + esc(metric.label) +
          "<br><i>" + esc(p.full) + " · " + rangeLabel(p.start, p.end) +
          (p.complete ? "" : " · unvollständig") + "</i>";
        tip.style.left = (ev.clientX - box.left) + "px";
        tip.style.top = (ev.clientY - box.top - 12) + "px";
        tip.dataset.show = "1";
      }});
      svg.addEventListener("mouseleave", function () {{ tip.dataset.show = "0"; }});
    }});

    renderEvolutionTable();
    var partial = periods().filter(function (p) {{ return !p.complete; }});
    document.getElementById("evolutionHint").innerHTML =
      "Balken mit geringerer Deckkraft kennzeichnen unvollständige Zeiträume" +
      (partial.length ? " (" + partial.map(function (p) {{ return esc(p.label); }}).join(", ") + ")" : "") +
      ". Die Instagram-Reichweite ist die Summe der Tageswerte und damit keine eindeutige Personenzahl.";
  }}

  function renderEvolutionTable() {{
    var list = periods();
    var head = "<tr><th>Zeitraum</th><th>FB Aufrufe</th><th>FB Interakt.</th><th>FB Beiträge</th>" +
               "<th>FB Follower</th><th>IG Aufrufe</th><th>IG Reichweite</th><th>IG Interakt.</th>" +
               "<th>IG Beiträge</th><th>IG Follower</th></tr>";
    var body = list.slice().reverse().map(function (p) {{
      return '<tr class="' + (p.complete ? "" : "partial") + '"><th scope="row">' + esc(p.label) +
        (p.complete ? "" : " *") + "</th>" +
        "<td>" + nf(p.facebook.views) + "</td><td>" + nf(p.facebook.interactions) + "</td>" +
        "<td>" + nf(p.facebook.posts) + "</td><td>" + nf(p.facebook.followers) + "</td>" +
        "<td>" + nf(p.instagram.views) + "</td><td>" + nf(p.instagram.reach) + "</td>" +
        "<td>" + nf(p.instagram.interactions) + "</td><td>" + nf(p.instagram.posts) + "</td>" +
        "<td>" + nf(p.instagram.followers) + "</td></tr>";
    }}).join("");
    document.getElementById("evolutionTable").innerHTML =
      '<table class="raw"><thead>' + head + "</thead><tbody>" + body + "</tbody></table>";
  }}

  // ---- Aktueller Monat -------------------------------------------------
  function renderCurrent() {{
    var m = D.current;
    document.getElementById("currentTitle").textContent = m.label;
    document.getElementById("currentSub").textContent =
      "Monat bis " + dmy(m.end) + " · " + m.dayCount + " Tage";
    document.getElementById("currentFraming").innerHTML =
      "<strong>Einordnung:</strong> " + rangeLabel(m.start, m.end) +
      " gegen denselben Zeitraum im Vormonat (" + rangeLabel(m.prevStart, m.prevEnd) +
      ") – gleiche Zeitraumlänge, gleiche Zeitraumposition, berechnet aus den Tagesrohwerten.";
    document.getElementById("currentCards").innerHTML =
      card("facebook", m.facebook, m.prevFacebook, "Aktuell", "Vormonat") +
      card("instagram", m.instagram, m.prevInstagram, "Aktuell", "Vormonat");
  }}

  // ---- Archiv ----------------------------------------------------------
  function renderArchive() {{
    var m = D.months.filter(function (x) {{ return x.key === state.month; }})[0];
    if (!m) return;
    document.getElementById("archiveFraming").innerHTML =
      "<strong>" + esc(m.label) + ":</strong> " + rangeLabel(m.start, m.end) +
      " gegen " + rangeLabel(m.prevStart, m.prevEnd) +
      (m.complete ? "" : " · der Monat läuft noch, die Werte sind noch nicht vollständig") + ".";
    document.getElementById("archiveCards").innerHTML =
      card("facebook", m.facebook, m.prevFacebook, m.labelShort, "Vormonat") +
      card("instagram", m.instagram, m.prevInstagram, m.labelShort, "Vormonat");
    Array.prototype.forEach.call(document.querySelectorAll("#monthControl button"), function (b) {{
      b.setAttribute("aria-pressed", b.dataset.month === state.month ? "true" : "false");
    }});
  }}

  // ---- Steuerung -------------------------------------------------------
  function buildControls() {{
    var mc = document.getElementById("metricControl");
    mc.innerHTML = METRICS.map(function (m) {{
      return '<button type="button" data-metric="' + m.key + '" aria-pressed="' +
        (m.key === state.metric) + '">' + esc(m.label) + "</button>";
    }}).join("");
    mc.addEventListener("click", function (ev) {{
      var b = ev.target.closest("button[data-metric]");
      if (!b) return;
      state.metric = b.dataset.metric;
      Array.prototype.forEach.call(mc.querySelectorAll("button"), function (x) {{
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      }});
      renderCharts();
    }});

    var gc = document.getElementById("granControl");
    gc.addEventListener("click", function (ev) {{
      var b = ev.target.closest("button[data-gran]");
      if (!b) return;
      state.gran = b.dataset.gran;
      Array.prototype.forEach.call(gc.querySelectorAll("button"), function (x) {{
        x.setAttribute("aria-pressed", x === b ? "true" : "false");
      }});
      renderCharts();
    }});

    var monthsDesc = D.months.slice().reverse();
    var moc = document.getElementById("monthControl");
    moc.innerHTML = monthsDesc.map(function (m) {{
      return '<button type="button" data-month="' + m.key + '">' + esc(m.label) + "</button>";
    }}).join("");
    moc.addEventListener("click", function (ev) {{
      var b = ev.target.closest("button[data-month]");
      if (!b) return;
      state.month = b.dataset.month;
      renderArchive();
    }});
    // Voreinstellung: der neueste abgeschlossene Monat. Der laufende Monat
    // steht schon oben im aktuellen Report, hier waere er eine Dopplung.
    var newestComplete = monthsDesc.filter(function (m) {{ return m.complete; }})[0];
    state.month = (newestComplete || monthsDesc[0]).key;
    window.__bwtv = state;
  }}

  // ---- Start -----------------------------------------------------------
  document.getElementById("standMain").textContent = dmy(D.meta.lastData);
  document.getElementById("standSub").textContent =
    D.meta.dayCount + " Tage erfasst · ab " + dmy(D.meta.firstData);
  document.getElementById("brandId").textContent = D.meta.brandId;
  document.getElementById("builtAt").textContent = dmy(D.meta.builtAt);

  buildControls();
  renderCurrent();
  renderCharts();
  renderArchive();
}})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Baut das BWTV-Dashboard")
    parser.add_argument("--out", default="index.html", help="Zielpfad (Standard: index.html)")
    parser.add_argument("--today", help="Referenzdatum JJJJ-MM-TT (nur fuer Tests)")
    args = parser.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()

    store_path = DATA / "metricool_daily.json"
    if not store_path.exists():
        raise SystemExit(f"Datenspeicher fehlt: {store_path}")
    store = json.loads(store_path.read_text(encoding="utf-8"))
    days = store["days"]
    if not days:
        raise SystemExit("Datenspeicher ist leer.")

    first_data = date.fromisoformat(min(days))
    last_data = date.fromisoformat(max(days))

    months = build_months(days, last_data)
    weeks = build_weeks(days, last_data)

    # Aktueller Monat = Monat des letzten Datentags, bis zu diesem Tag.
    current = next(m for m in months if m["key"] == last_data.strftime("%Y-%m"))
    current = dict(current)
    current["dayCount"] = (date.fromisoformat(current["end"])
                           - date.fromisoformat(current["start"])).days + 1

    payload = {
        "meta": {
            "brandId": store.get("brandId", 6061560),
            "firstData": first_data.isoformat(),
            "lastData": last_data.isoformat(),
            "dayCount": len(days),
            "builtAt": today.isoformat(),
        },
        "current": current,
        "months": months,
        "weeks": weeks,
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = BASE / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(payload), encoding="utf-8")

    size_kb = out.stat().st_size / 1024
    print(f"Dashboard geschrieben: {out}  ({size_kb:.0f} kB)")
    print(f"Datenstand: {de_date(last_data)} · {len(days)} Tage · "
          f"{len(months)} Monate · {len(weeks)} Wochen")
    print(f"Aktueller Monat: {current['label']} "
          f"({current['start']} bis {current['end']}, {current['dayCount']} Tage)")
    print(f"  FB Aufrufe {current['facebook']['views']:>8,}  "
          f"(Vormonat {current['prevFacebook']['views']:,})".replace(",", "."))
    print(f"  IG Aufrufe {current['instagram']['views']:>8,}  "
          f"(Vormonat {current['prevInstagram']['views']:,})".replace(",", "."))


if __name__ == "__main__":
    main()

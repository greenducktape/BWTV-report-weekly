#!/usr/bin/env python3
"""
Baut das Social-Media-Dashboard als eigenstaendige index.html.

Aufruf:
    python3 scripts/build_site.py
    python3 scripts/build_site.py --out index.html --today 2026-08-18

Marke, Farben und Logo kommen aus config.json - fuer einen anderen Kunden nur
diese Datei anpassen, die Skripte bleiben unveraendert.

Aufbau der Seite:
  1. Kernaussage    - was die Zahlen in einem Satz sagen
  2. Hero-Kennzahlen- die vier Zahlen, auf die es ankommt, mit Sparkline
  3. Effizienz      - Wirkung je Beitrag, unabhaengig von der Menge
  4. Verlauf        - Monat/Woche umschaltbar, je Netzwerk eigenes Panel
  5. Details        - vollstaendige Tabelle je Netzwerk
  6. Monatsarchiv   - jeder Monat einzeln gegen den Vormonat
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

SUMMED = ("views", "reach", "interactions", "profileViews", "newFollowers",
          "posts", "accountsEngaged")


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------

def daterange(start, end):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def aggregate(days, network, start, end):
    out = {k: 0 for k in SUMMED}
    out["daysWithData"] = 0
    first = last = None
    for day in daterange(start, end):
        entry = days.get(day.isoformat())
        if not entry:
            continue
        block = entry.get(network)
        if not block:
            continue
        out["daysWithData"] += 1
        for k in SUMMED:
            v = block.get(k)
            if v is not None:
                out[k] += v
        stock = block.get("followers")
        if stock is not None:
            if first is None:
                first = stock
            last = stock
    out["followers"] = last
    out["followersStart"] = first
    out["followersDelta"] = None if first is None or last is None else last - first
    # Wirkung je Beitrag: trennt Menge von Qualitaet.
    out["viewsPerPost"] = round(out["views"] / out["posts"], 1) if out["posts"] else None
    out["interactionsPerPost"] = round(out["interactions"] / out["posts"], 1) if out["posts"] else None
    return out


def month_span(year, month):
    start = date(year, month, 1)
    end = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    return start, end


def prev_month(year, month):
    return (year - 1, 12) if month == 1 else (year, month - 1)


def combine(a, b):
    """Netzwerke zusammenfassen. Nur additive Groessen werden summiert."""
    out = {}
    for k in ("views", "interactions", "posts"):
        out[k] = a.get(k, 0) + b.get(k, 0)
    fa, fb = a.get("followers"), b.get("followers")
    out["followers"] = None if fa is None and fb is None else (fa or 0) + (fb or 0)
    da, db = a.get("followersDelta"), b.get("followersDelta")
    out["followersDelta"] = None if da is None and db is None else (da or 0) + (db or 0)
    out["viewsPerPost"] = round(out["views"] / out["posts"], 1) if out["posts"] else None
    return out


def build_months(days, last_data):
    out = []
    for key in sorted({d[:7] for d in days}):
        year, month = int(key[:4]), int(key[5:7])
        start, end = month_span(year, month)
        eff_end = min(end, last_data)
        py, pm = prev_month(year, month)
        p_start, p_end = month_span(py, pm)
        length = (eff_end - start).days
        p_eff_end = min(p_start + timedelta(days=length), p_end)
        fb = aggregate(days, "facebook", start, eff_end)
        ig = aggregate(days, "instagram", start, eff_end)
        pfb = aggregate(days, "facebook", p_start, p_eff_end)
        pig = aggregate(days, "instagram", p_start, p_eff_end)
        out.append({
            "key": key,
            "label": MONTHS_DE[month - 1] + " " + str(year),
            "labelShort": MONTHS_DE_SHORT[month - 1] + " " + str(year)[2:],
            "start": start.isoformat(), "end": eff_end.isoformat(),
            "complete": end <= last_data,
            "dayCount": (eff_end - start).days + 1,
            "prevKey": "%d-%02d" % (py, pm),
            "prevStart": p_start.isoformat(), "prevEnd": p_eff_end.isoformat(),
            "facebook": fb, "instagram": ig,
            "prevFacebook": pfb, "prevInstagram": pig,
            "total": combine(fb, ig), "prevTotal": combine(pfb, pig),
        })
    return out


def build_weeks(days, last_data):
    seen = {}
    for iso in days:
        d = date.fromisoformat(iso)
        c = d.isocalendar()
        seen[(c.year, c.week)] = seen.get((c.year, c.week), 0) + 1
    out = []
    for (year, week) in sorted(seen):
        monday = date.fromisocalendar(year, week, 1)
        eff_end = min(monday + timedelta(days=6), last_data)
        fb = aggregate(days, "facebook", monday, eff_end)
        ig = aggregate(days, "instagram", monday, eff_end)
        out.append({
            "key": "%d-W%02d" % (year, week),
            "label": "KW %d" % week,
            "labelShort": str(week),
            "start": monday.isoformat(), "end": eff_end.isoformat(),
            "complete": seen[(year, week)] >= 7,
            "dayCount": seen[(year, week)],
            "facebook": fb, "instagram": ig, "total": combine(fb, ig),
        })
    return out


# --------------------------------------------------------------------------
# Kernaussage
# --------------------------------------------------------------------------

def pct(cur, prev):
    if cur is None or prev in (None, 0):
        return None
    return (cur - prev) / abs(prev) * 100.0


def de_num(v, digits=0):
    if v is None:
        return "–"
    s = ("{:,.%df}" % digits).format(v)
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def de_pct(v):
    if v is None:
        return "–"
    return de_num(abs(v), 1) + " %"


def word(v, up="gestiegen", down="gesunken", flat="stabil geblieben"):
    if v is None:
        return flat
    if abs(v) < 3:
        return flat
    return up if v > 0 else down


def build_headline(current, months):
    """Erzeugt Kernaussage und Belege aus den Zahlen des laufenden Zeitraums."""
    cur, prev = current["total"], current["prevTotal"]
    dv = pct(cur["views"], prev["views"])
    dp = pct(cur["posts"], prev["posts"])
    dvp = pct(cur["viewsPerPost"], prev["viewsPerPost"])

    # Verdikt: trennt Menge (Output) von Wirkung (je Beitrag).
    if dv is None:
        title = "Vergleich mit dem Vormonat noch nicht möglich"
    elif dv < -3 and dp is not None and dp < -3 and (dvp is None or dvp > -10):
        title = "Weniger Reichweite, weil weniger veröffentlicht wurde"
    elif dv < -3 and (dvp is not None and dvp < -10):
        title = "Weniger Reichweite – und jeder Beitrag wirkt schwächer"
    elif dv > 3 and dvp is not None and dvp > 3:
        title = "Mehr Reichweite bei stärkerer Wirkung je Beitrag"
    elif dv > 3:
        title = "Mehr Reichweite, getragen von höherem Output"
    else:
        title = "Reichweite auf dem Niveau des Vormonats"

    points = []
    points.append(
        "<strong>Aufrufe</strong> " + word(dv) + ": " + de_num(prev["views"]) +
        " → <strong>" + de_num(cur["views"]) + "</strong>" +
        ("" if dv is None else " (" + ("+" if dv > 0 else "−") + de_pct(dv) + ")") + "."
    )
    points.append(
        "<strong>Beiträge</strong> " + word(dp, "erhöht", "reduziert", "unverändert") + ": " +
        de_num(prev["posts"]) + " → <strong>" + de_num(cur["posts"]) + "</strong>."
    )
    if cur["viewsPerPost"] is not None and prev["viewsPerPost"] is not None:
        points.append(
            "<strong>Aufrufe je Beitrag</strong> " + word(dvp) + ": " +
            de_num(prev["viewsPerPost"]) + " → <strong>" + de_num(cur["viewsPerPost"]) +
            "</strong>. Diese Zahl zeigt die Wirkung eines einzelnen Beitrags, " +
            "unabhängig davon, wie viel veröffentlicht wurde."
        )

    # Langfristige Einordnung der Wirkung je Beitrag.
    done = [m for m in months if m["complete"] and m["instagram"]["viewsPerPost"]]
    if len(done) >= 3:
        best = max(done, key=lambda m: m["instagram"]["viewsPerPost"])
        newest = done[-1]
        if best["key"] != newest["key"] and best["instagram"]["viewsPerPost"] > 0:
            drop = pct(newest["instagram"]["viewsPerPost"], best["instagram"]["viewsPerPost"])
            if drop is not None and drop < -25:
                points.append(
                    "<strong>Im Jahresverlauf:</strong> Instagram erreichte im " + best["label"] +
                    " noch " + de_num(best["instagram"]["viewsPerPost"]) +
                    " Aufrufe je Beitrag, im " + newest["label"] + " sind es " +
                    de_num(newest["instagram"]["viewsPerPost"]) + ". Damals trugen wenige, sehr " +
                    "starke Reels die Reichweite; inzwischen wird deutlich mehr veröffentlicht, " +
                    "der einzelne Beitrag wirkt aber schwächer."
                )
    return {"title": title, "points": points}


# --------------------------------------------------------------------------
# Rendern
# --------------------------------------------------------------------------

def data_uri(rel):
    p = BASE / rel
    if not p.exists():
        return ""
    return "data:image/svg+xml;base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def de_date(d):
    return "%02d.%02d.%d" % (d.day, d.month, d.year)


TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TITLE%%</title>
<meta name="description" content="%%SUBTITLE%%">
<style>
  *, *::before, *::after { box-sizing: border-box; }
  :root {
    --ink:#16121f; --ink-soft:#5b5470; --ink-faint:#8b849c;
    --surface:#fff; --surface-alt:#f5f4f8; --line:#e6e3ee; --line-soft:#f0eef5;
    --good-bg:#e6f6e9; --good-fg:#1c7a33;
    --bad-bg:#fdeaf0;  --bad-fg:#c2185b;
    --flat-bg:#eeecf3; --flat-fg:#5b5470;
%%THEMEVARS%%
  }
  body{margin:0;background:#eceaf2;color:var(--ink);
    font:400 16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
    -webkit-font-smoothing:antialiased;padding:26px 16px 46px;}
  .sheet{max-width:1240px;margin:0 auto;background:var(--surface);border-radius:22px;
    overflow:hidden;box-shadow:0 18px 48px rgba(22,18,31,.13);}

  /* Kopf */
  .masthead{background:linear-gradient(102deg,var(--h1) 0%,var(--h2) 52%,var(--h3) 100%);
    color:#fff;padding:26px 34px 24px;display:flex;flex-wrap:wrap;gap:20px;
    align-items:center;justify-content:space-between;}
  .brand{display:flex;align-items:center;gap:18px;min-width:0;}
  .logo{height:54px;width:auto;flex:none;}
  .logo--text{font-weight:800;font-size:26px;letter-spacing:.06em;}
  .brand__text h1{margin:0;font-size:clamp(21px,2.5vw,29px);font-weight:800;letter-spacing:-.015em;}
  .brand__text p{margin:3px 0 0;font-size:14px;color:#c9c1dd;}
  .stand{text-align:right;flex:none;}
  .stand__eyebrow{margin:0;font-size:10.5px;font-weight:700;letter-spacing:.17em;
    text-transform:uppercase;color:#a99fc4;}
  .stand__main{margin:4px 0 0;font-size:clamp(18px,2.1vw,25px);font-weight:800;}
  .stand__sub{margin:3px 0 0;font-size:12.5px;color:#b3aac9;}
  .rule{display:flex;height:6px;}
  .rule i{flex:1;}

  .content{padding:0 34px 30px;}
  section.block{padding-top:30px;}
  section.block+section.block{margin-top:30px;border-top:1px solid var(--line);}
  .block__kicker{margin:0;font-size:11px;font-weight:700;letter-spacing:.15em;
    text-transform:uppercase;color:var(--ink-faint);}
  .block__title{margin:5px 0 0;font-size:22px;font-weight:800;letter-spacing:-.01em;}
  .block__sub{margin:5px 0 0;font-size:14px;color:var(--ink-soft);max-width:78ch;}
  .block__head{margin-bottom:16px;}

  /* Kernaussage */
  .verdict{border:1px solid var(--line);border-radius:16px;overflow:hidden;}
  .verdict__top{padding:20px 24px 18px;
    background:linear-gradient(96deg,rgba(214,36,110,.07),rgba(0,173,235,.07));
    border-bottom:1px solid var(--line);}
  .verdict__eyebrow{margin:0 0 5px;font-size:10.5px;font-weight:700;letter-spacing:.15em;
    text-transform:uppercase;color:var(--ink-faint);}
  .verdict__title{margin:0;font-size:clamp(19px,2.2vw,25px);font-weight:800;letter-spacing:-.02em;line-height:1.25;}
  .verdict__period{margin:8px 0 0;font-size:13.5px;color:var(--ink-soft);}
  .verdict ul{margin:0;padding:16px 24px 18px 40px;}
  .verdict li{margin-bottom:9px;font-size:14.5px;color:#3c3550;}
  .verdict li:last-child{margin-bottom:0;}
  .verdict strong{color:var(--ink);}

  /* Hero-Kacheln */
  .kpis{display:grid;gap:16px;margin-top:20px;
    grid-template-columns:repeat(auto-fit,minmax(232px,1fr));}
  .kpi{background:var(--surface-alt);border:1px solid var(--line);border-radius:16px;padding:17px 19px 15px;}
  .kpi__label{margin:0;font-size:10.5px;font-weight:700;letter-spacing:.13em;
    text-transform:uppercase;color:var(--ink-faint);}
  .kpi__value{margin:7px 0 0;font-size:31px;font-weight:800;letter-spacing:-.025em;
    font-variant-numeric:tabular-nums;line-height:1.05;}
  .kpi__row{display:flex;align-items:center;gap:9px;margin-top:8px;flex-wrap:wrap;}
  .kpi__split{margin:9px 0 0;font-size:12px;color:var(--ink-faint);
    font-variant-numeric:tabular-nums;display:flex;gap:11px;flex-wrap:wrap;}
  .kpi__split span{display:inline-flex;align-items:center;gap:5px;}
  .kpi__split i{width:8px;height:8px;border-radius:2.5px;display:inline-block;}
  .kpi__note{margin:7px 0 0;font-size:11px;line-height:1.35;color:var(--ink-faint);}
  .spark{display:block;margin-top:11px;width:100%;height:34px;overflow:visible;}

  /* Effizienz */
  .eff{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));}
  .effcard{background:var(--surface-alt);border:1px solid var(--line);border-radius:16px;padding:18px 20px 16px;}
  .effcard__head{display:flex;align-items:center;gap:9px;margin-bottom:14px;}
  .effcard__dot{width:10px;height:10px;border-radius:3px;background:var(--accent);flex:none;}
  .effcard__title{margin:0;font-size:15px;font-weight:800;}
  .effrow{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
    padding:11px 0;border-bottom:1px solid var(--line);}
  .effrow:last-child{border-bottom:0;padding-bottom:0;}
  .effrow__label{font-size:13.5px;color:var(--ink-soft);}
  .effrow__right{display:flex;align-items:baseline;gap:10px;}
  .effrow__value{font-size:21px;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.02em;}

  /* Karten */
  .cards{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));}
  .card{background:var(--surface-alt);border:1px solid var(--line);border-radius:16px;padding:20px 22px 8px;}
  .card__head{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:6px;}
  .card__icon{width:34px;height:34px;border-radius:10px;flex:none;background:var(--accent);
    display:grid;place-items:center;}
  .card__icon svg{width:21px;height:21px;display:block;}
  .card__title{margin:0;font-size:21px;font-weight:800;color:var(--accent);letter-spacing:-.01em;}
  .follower-pill{margin-left:auto;flex:none;background:#fff;border:1px solid var(--line);
    border-radius:999px;padding:6px 13px;font-size:12.5px;font-weight:700;color:var(--ink-soft);}
  .follower-pill em{font-style:normal;font-weight:500;color:var(--ink-faint);}
  .follower-pill--good{color:var(--good-fg);border-color:#bfe6c8;}
  .follower-pill--bad{color:var(--bad-fg);border-color:#f6ccdb;}

  table.metrics{width:100%;border-collapse:collapse;}
  .metrics thead th{font-size:10.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;
    color:var(--ink-faint);text-align:left;padding:12px 8px 9px;border-bottom:1px solid var(--line);}
  .metrics tbody th{text-align:left;font-size:14.5px;font-weight:700;padding:13px 8px;
    border-bottom:1px solid var(--line);}
  .metrics tbody tr:last-child th,.metrics tbody tr:last-child td{border-bottom:0;}
  .metrics td{padding:13px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums;}
  .num{text-align:right;font-size:15px;color:var(--ink-soft);}
  .num--current{font-weight:800;font-size:16.5px;color:var(--ink);}
  .delta{text-align:right;white-space:nowrap;}
  .metric-note{display:block;font-size:11.5px;font-weight:400;color:var(--ink-faint);
    margin-top:2px;max-width:30ch;}
  .pill{display:inline-block;border-radius:999px;padding:4px 10px;font-size:12.5px;
    font-weight:800;font-variant-numeric:tabular-nums;}
  .pill--good{background:var(--good-bg);color:var(--good-fg);}
  .pill--bad{background:var(--bad-bg);color:var(--bad-fg);}
  .pill--flat{background:var(--flat-bg);color:var(--flat-fg);}
  .pill--sm{padding:3px 8px;font-size:11.5px;}

  /* Steuerung */
  .controls{display:flex;flex-wrap:wrap;gap:10px 22px;align-items:flex-end;margin-bottom:18px;}
  .control__label{display:block;font-size:10.5px;font-weight:700;letter-spacing:.13em;
    text-transform:uppercase;color:var(--ink-faint);margin-bottom:6px;}
  .segmented{display:inline-flex;background:var(--surface-alt);border:1px solid var(--line);
    border-radius:10px;padding:3px;gap:2px;flex-wrap:wrap;}
  .segmented button{appearance:none;border:0;background:transparent;cursor:pointer;
    font:600 13.5px/1 inherit;color:var(--ink-soft);padding:8px 14px;border-radius:8px;white-space:nowrap;}
  .segmented button:hover{color:var(--ink);}
  .segmented button[aria-pressed="true"]{background:#fff;color:var(--ink);
    box-shadow:0 1px 3px rgba(22,18,31,.12);font-weight:700;}
  .segmented button:focus-visible{outline:2px solid var(--accent);outline-offset:1px;}

  /* Diagramme */
  .charts{display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));}
  .panel{background:var(--surface-alt);border:1px solid var(--line);border-radius:16px;
    padding:18px 20px 14px;min-width:0;}
  .panel__head{display:flex;align-items:baseline;gap:9px;margin-bottom:2px;}
  .panel__dot{width:10px;height:10px;border-radius:3px;background:var(--accent);flex:none;}
  .panel__title{margin:0;font-size:15px;font-weight:800;}
  .panel__value{margin:2px 0 0;font-size:27px;font-weight:800;letter-spacing:-.02em;
    font-variant-numeric:tabular-nums;}
  .panel__meta{margin:1px 0 10px;font-size:12.5px;color:var(--ink-faint);}
  .chart{position:relative;}
  .chart svg{display:block;width:100%;height:auto;overflow:visible;}
  .bar--partial{opacity:.42;}
  .chart-empty{padding:26px 4px;font-size:13.5px;color:var(--ink-faint);
    border:1px dashed var(--line);border-radius:12px;text-align:center;}
  .tip{position:absolute;pointer-events:none;z-index:5;background:#17102b;color:#fff;
    border-radius:9px;padding:8px 11px;font-size:12.5px;line-height:1.45;
    box-shadow:0 6px 18px rgba(22,18,31,.28);opacity:0;transform:translate(-50%,-100%);
    transition:opacity .1s;white-space:nowrap;}
  .tip[data-show="1"]{opacity:1;}
  .tip b{font-variant-numeric:tabular-nums;}
  .tip i{font-style:normal;color:#b3aac9;}

  details.tablewrap{margin-top:14px;}
  details.tablewrap summary{cursor:pointer;font-size:12.5px;font-weight:700;
    color:var(--ink-soft);padding:6px 0;}
  details.tablewrap summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
  .scroller{overflow-x:auto;margin-top:8px;}
  table.raw{border-collapse:collapse;font-size:13px;min-width:100%;}
  table.raw th,table.raw td{padding:7px 11px;text-align:right;white-space:nowrap;
    border-bottom:1px solid var(--line-soft);font-variant-numeric:tabular-nums;}
  table.raw th:first-child,table.raw td:first-child{text-align:left;}
  table.raw thead th{font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;
    color:var(--ink-faint);border-bottom:1px solid var(--line);}
  table.raw tbody tr.partial td,table.raw tbody tr.partial th{color:var(--ink-faint);}

  .hint{margin:14px 0 0;font-size:12.5px;color:var(--ink-faint);max-width:88ch;}
  .callout{border-left:4px solid var(--accent);
    background:linear-gradient(96deg,rgba(214,36,110,.07),rgba(0,173,235,.07));
    border-radius:0 12px 12px 0;padding:14px 18px;font-size:14px;color:#3c3550;margin-bottom:20px;}
  .callout strong{color:var(--ink);}

  .sheet__foot{border-top:1px solid var(--line);padding:15px 34px 17px;display:flex;
    flex-wrap:wrap;gap:8px;justify-content:space-between;font-size:12px;color:var(--ink-faint);}
  .sheet__foot b{color:var(--ink-soft);}
  noscript p{margin:0 0 18px;padding:13px 16px;border-radius:10px;background:var(--bad-bg);
    color:var(--bad-fg);font-size:14px;}

  @media (max-width:760px){
    body{padding:12px 9px 30px;}
    .masthead,.content,.sheet__foot{padding-left:18px;padding-right:18px;}
    .stand{text-align:left;}
    .cards,.charts,.eff{grid-template-columns:1fr;}
  }
  @media print{
    body{background:#fff;padding:0;}
    .sheet{box-shadow:none;border-radius:0;max-width:none;}
    .controls,details.tablewrap{display:none;}
  }
</style>
</head>
<body>
<main class="sheet">
  <header class="masthead">
    <div class="brand">
      %%LOGO%%
      <div class="brand__text">
        <h1>%%BRANDNAME%%</h1>
        <p>%%SUBTITLE%%</p>
      </div>
    </div>
    <div class="stand">
      <p class="stand__eyebrow">Datenstand</p>
      <p class="stand__main" id="standMain">–</p>
      <p class="stand__sub" id="standSub">–</p>
    </div>
  </header>
  <div class="rule">%%RULE%%</div>

  <div class="content">
    <noscript><p>Für Filter und Diagramme wird JavaScript benötigt.</p></noscript>

    <section class="block" id="summary">
      <div class="block__head">
        <p class="block__kicker">Aktueller Report</p>
        <h2 class="block__title" id="sumTitle">Laufender Monat</h2>
        <p class="block__sub" id="sumSub"></p>
      </div>
      <div class="verdict" id="verdict"></div>
      <div class="kpis" id="kpis"></div>
    </section>

    <section class="block" id="efficiency">
      <div class="block__head">
        <p class="block__kicker">Wirkung</p>
        <h2 class="block__title">Was ein einzelner Beitrag bringt</h2>
        <p class="block__sub">Summen hängen davon ab, wie viel veröffentlicht wurde. Diese Werte
          zeigen die Wirkung je Beitrag – damit lässt sich erkennen, ob Inhalte besser oder
          schlechter funktionieren, unabhängig von der Menge.</p>
      </div>
      <div class="eff" id="effCards"></div>
    </section>

    <section class="block" id="evolution">
      <div class="block__head">
        <p class="block__kicker">Entwicklung</p>
        <h2 class="block__title">Verlauf über die Zeit</h2>
        <p class="block__sub">Facebook und Instagram in getrennten Panels mit eigener Skala – die
          Größenordnungen unterscheiden sich um mehr als das Zehnfache.</p>
      </div>
      <div class="controls">
        <div>
          <span class="control__label" id="lblGran">Zeitraster</span>
          <div class="segmented" role="group" aria-labelledby="lblGran" id="granControl">
            <button type="button" data-gran="monthly" aria-pressed="true">Monatlich</button>
            <button type="button" data-gran="weekly" aria-pressed="false">Wöchentlich</button>
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

    <section class="block" id="detail">
      <div class="block__head">
        <p class="block__kicker">Details</p>
        <h2 class="block__title">Alle Kennzahlen im Vergleich</h2>
        <p class="block__sub" id="detailSub"></p>
      </div>
      <div class="cards" id="detailCards"></div>
    </section>

    <section class="block" id="archive">
      <div class="block__head">
        <p class="block__kicker">Monatsarchiv</p>
        <h2 class="block__title">Einzelne Monate</h2>
        <p class="block__sub">Jeder Monat gegen den Vormonat – gleiche Zeitraumlänge.</p>
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
    <span>Quelle: %%SOURCENAME%% (Brand <span id="brandId"></span>) · erzeugt <span id="builtAt"></span></span>
    <span><b>%%FOOTER%%</b> — %%FOOTERLONG%%</span>
  </footer>
</main>

<script type="application/json" id="payload">%%DATA%%</script>
<script>
(function(){
"use strict";
var D=JSON.parse(document.getElementById("payload").textContent);
var NET=D.config.networks, ORDER=Object.keys(NET);
var MONTHS=["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"];

function nf(v,d){if(v===null||v===undefined)return "–";
  return Number(v).toLocaleString("de-DE",{minimumFractionDigits:d||0,maximumFractionDigits:d||0});}
function pf(v){if(v===null||v===undefined)return "–";
  return Number(v).toLocaleString("de-DE",{minimumFractionDigits:1,maximumFractionDigits:1})+" %";}
function sf(v){if(v===null||v===undefined)return "–";
  return (v>0?"+":"")+Number(v).toLocaleString("de-DE");}
function iso(s){var p=s.split("-");return new Date(+p[0],+p[1]-1,+p[2]);}
function dmy(s){var d=iso(s);return String(d.getDate()).padStart(2,"0")+"."+String(d.getMonth()+1).padStart(2,"0")+"."+d.getFullYear();}
function rng(a,b){var x=iso(a),y=iso(b),dd=function(d){return String(d.getDate()).padStart(2,"0");};
  if(x.getMonth()===y.getMonth()&&x.getFullYear()===y.getFullYear())
    return dd(x)+".–"+dd(y)+". "+MONTHS[y.getMonth()]+" "+y.getFullYear();
  if(x.getFullYear()===y.getFullYear())
    return dd(x)+". "+MONTHS[x.getMonth()]+" – "+dd(y)+". "+MONTHS[y.getMonth()]+" "+y.getFullYear();
  return dmy(a)+" – "+dmy(b);}
function esc(s){return String(s).replace(/[&<>"']/g,function(c){
  return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function chg(c,p){if(c===null||c===undefined||p===null||p===undefined||p===0)return null;
  return (c-p)/Math.abs(p)*100;}

function pill(cur,prev,dir,small){
  var c=chg(cur,prev),cls=small?" pill--sm":"";
  if(c===null){
    if(cur===null||prev===null||cur===prev)return '<span class="pill pill--flat'+cls+'">–</span>';
    var r0=cur>prev,t0=dir==="neutral"?"flat":((r0===(dir==="up"))?"good":"bad");
    return '<span class="pill pill--'+t0+cls+'">'+(r0?"▲":"▼")+" "+sf(cur-prev)+"</span>";}
  if(Math.abs(c)<0.05)return '<span class="pill pill--flat'+cls+'">±0,0 %</span>';
  var r=c>0,t=dir==="neutral"?"flat":((r===(dir==="up"))?"good":"bad");
  return '<span class="pill pill--'+t+cls+'">'+(r?"▲":"▼")+" "+pf(Math.abs(c))+"</span>";}

/* ---------- Sparkline ---------- */
function spark(vals,color){
  var W=200,H=34,n=vals.length;
  if(!n)return "";
  var clean=vals.filter(function(v){return v!==null&&v!==undefined;});
  if(!clean.length)return "";
  var max=Math.max.apply(null,clean),min=Math.min.apply(null,clean);
  var lo=Math.min(0,min),span=(max-lo)||1;
  var slot=W/n,bw=Math.max(3,Math.min(22,slot-3));
  var out='<svg class="spark" viewBox="0 0 '+W+" "+H+'" preserveAspectRatio="none" aria-hidden="true">';
  vals.forEach(function(v,i){
    if(v===null||v===undefined)return;
    var h=Math.max(2,(v-lo)/span*(H-3));
    var x=slot*i+(slot-bw)/2;
    out+='<rect x="'+x.toFixed(1)+'" y="'+(H-h).toFixed(1)+'" width="'+bw.toFixed(1)+
      '" height="'+h.toFixed(1)+'" rx="2" fill="'+color+'" opacity="'+(i===n-1?"1":"0.28")+'"/>';});
  return out+"</svg>";}

/* ---------- Kernaussage + KPIs ---------- */
function renderSummary(){
  var m=D.current;
  document.getElementById("sumTitle").textContent=m.label;
  document.getElementById("sumSub").textContent="Monat bis "+dmy(m.end)+" · "+m.dayCount+" Tage erfasst";
  var v=D.verdict;
  document.getElementById("verdict").innerHTML=
    '<div class="verdict__top"><p class="verdict__eyebrow">Kernaussage</p>'+
    '<p class="verdict__title">'+esc(v.title)+"</p>"+
    '<p class="verdict__period">'+rng(m.start,m.end)+" gegen "+rng(m.prevStart,m.prevEnd)+
    " · gleiche Zeitraumlänge und -position</p></div><ul>"+
    v.points.map(function(p){return "<li>"+p+"</li>";}).join("")+"</ul>";

  var hist=D.months.slice(-6);
  var tiles=[
    {label:"Aufrufe",key:"views",dir:"up",split:true},
    {label:"Interaktionen",key:"interactions",dir:"up",split:true},
    {label:"Follower (beide Kanäle)",key:"followers",dir:"up",stock:true,split:true,
     note:"Summe beider Kanäle – wer beiden folgt, ist doppelt gezählt"},
    {label:"Veröffentlichte Beiträge",key:"posts",dir:"neutral",split:true}
  ];
  document.getElementById("kpis").innerHTML=tiles.map(function(t){
    var cur=m.total[t.key],prev=m.prevTotal[t.key];
    var fd=m.total.followersDelta;
    var deltaHtml=t.stock
      ? '<span class="pill pill--'+(fd>0?"good":(fd<0?"bad":"flat"))+' pill--sm">'+
        (fd>0?"▲ ":(fd<0?"▼ ":""))+nf(Math.abs(fd))+"</span>"
      : pill(cur,prev,t.dir,true);
    var series=hist.map(function(x){return t.stock?x.total.followers:x.total[t.key];});
    var split=ORDER.map(function(nk){
      var val=t.stock?m[nk].followers:m[nk][t.key];
      return '<span><i style="background:'+NET[nk].color+'"></i>'+NET[nk].label.slice(0,2)+" "+nf(val)+"</span>";}).join("");
    return '<article class="kpi"><p class="kpi__label">'+esc(t.label)+"</p>"+
      '<p class="kpi__value">'+nf(cur)+"</p>"+
      '<div class="kpi__row">'+deltaHtml+
      '<span style="font-size:12px;color:var(--ink-faint)">vs. Vormonat</span></div>'+
      '<div class="kpi__split">'+split+"</div>"+
      (t.note?'<p class="kpi__note">'+esc(t.note)+"</p>":"")+
      spark(series,D.config.theme.accent)+"</article>";}).join("");
}

/* ---------- Effizienz ---------- */
function renderEfficiency(){
  var m=D.current;
  document.getElementById("effCards").innerHTML=ORDER.map(function(nk){
    var c=m[nk],p=m["prev"+nk.charAt(0).toUpperCase()+nk.slice(1)];
    var hist=D.months.slice(-6).map(function(x){return x[nk].viewsPerPost;});
    var rows=[
      {l:"Aufrufe je Beitrag",c:c.viewsPerPost,p:p.viewsPerPost},
      {l:"Interaktionen je Beitrag",c:c.interactionsPerPost,p:p.interactionsPerPost},
      {l:"Beiträge im Zeitraum",c:c.posts,p:p.posts,neutral:true}
    ].map(function(r){
      return '<div class="effrow"><span class="effrow__label">'+esc(r.l)+"</span>"+
        '<span class="effrow__right"><span class="effrow__value">'+nf(r.c)+"</span>"+
        pill(r.c,r.p,r.neutral?"neutral":"up",true)+"</span></div>";}).join("");
    return '<article class="effcard" style="--accent:'+NET[nk].color+'">'+
      '<div class="effcard__head"><span class="effcard__dot"></span>'+
      '<h3 class="effcard__title">'+esc(NET[nk].label)+"</h3></div>"+rows+
      spark(hist,NET[nk].color)+
      '<p style="margin:8px 0 0;font-size:11.5px;color:var(--ink-faint)">Balken: Aufrufe je Beitrag, letzte 6 Monate</p>'+
      "</article>";}).join("");
}

/* ---------- Detailkarten ---------- */
var ICONS={
 facebook:'<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#fff" d="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.8-.1-1.7-.15-2.5-.15-2.5 0-4.2 1.5-4.2 4.3v2.15H7.3V13h2.25v8h3.95Z"/></svg>',
 instagram:'<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2" fill="none" stroke="#fff" stroke-width="2"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="#fff" stroke-width="2"/><circle cx="17.1" cy="6.9" r="1.35" fill="#fff"/></svg>'};
var ROWS={
 facebook:[{l:"Aufrufe",k:"views",d:"up"},{l:"Interaktionen",k:"interactions",d:"up"},
   {l:"Profilaufrufe",k:"profileViews",d:"up"},{l:"Beiträge",k:"posts",d:"neutral"},
   {l:"Aufrufe je Beitrag",k:"viewsPerPost",d:"up"},{l:"Neue Follower",k:"newFollowers",d:"up"}],
 instagram:[{l:"Aufrufe",k:"views",d:"up"},
   {l:"Reichweite",k:"reach",d:"up",n:"Summe der Tageswerte – keine eindeutige Personenzahl"},
   {l:"Interaktionen",k:"interactions",d:"up"},
   {l:"Aktive Konten",k:"accountsEngaged",d:"up",n:"Konten, die mit dem Content interagiert haben"},
   {l:"Beiträge",k:"posts",d:"neutral"},{l:"Aufrufe je Beitrag",k:"viewsPerPost",d:"up"}]};

function card(nk,cur,prev,lc,lp){
  var rows=ROWS[nk].map(function(r){
    var note=r.n?'<span class="metric-note">'+esc(r.n)+"</span>":"";
    var dec=r.k==="viewsPerPost"?0:0;
    return '<tr><th scope="row">'+esc(r.l)+note+"</th>"+
      '<td class="num">'+nf(prev[r.k],dec)+"</td>"+
      '<td class="num num--current">'+nf(cur[r.k],dec)+"</td>"+
      '<td class="delta">'+pill(cur[r.k],prev[r.k],r.d)+"</td></tr>";}).join("");
  var d=cur.followersDelta,fp;
  if(d===null||d===undefined){fp='<span class="follower-pill">Followerstand '+nf(cur.followers)+"</span>";}
  else{var t=d>0?"good":(d<0?"bad":"flat");
    fp='<span class="follower-pill follower-pill--'+t+'">'+sf(d)+" Follower <em>· "+nf(cur.followers)+" gesamt</em></span>";}
  return '<section class="card" style="--accent:'+NET[nk].color+'">'+
    '<header class="card__head"><span class="card__icon">'+ICONS[nk]+"</span>"+
    '<h3 class="card__title">'+esc(NET[nk].label)+"</h3>"+fp+"</header>"+
    '<table class="metrics"><thead><tr><th scope="col">Kennzahl</th>'+
    '<th scope="col" class="num">'+esc(lp)+"</th>"+
    '<th scope="col" class="num">'+esc(lc)+"</th>"+
    '<th scope="col" class="delta">Veränd.</th></tr></thead><tbody>'+rows+"</tbody></table></section>";}

function renderDetail(){
  var m=D.current;
  document.getElementById("detailSub").textContent=
    rng(m.start,m.end)+" gegen "+rng(m.prevStart,m.prevEnd)+".";
  document.getElementById("detailCards").innerHTML=
    ORDER.map(function(nk){
      return card(nk,m[nk],m["prev"+nk.charAt(0).toUpperCase()+nk.slice(1)],"Aktuell","Vormonat");}).join("");}

/* ---------- Diagramme ---------- */
var METRICS=[
 {key:"views",label:"Aufrufe",nets:ORDER},
 {key:"viewsPerPost",label:"Aufrufe je Beitrag",nets:ORDER,dec:0},
 {key:"interactions",label:"Interaktionen",nets:ORDER},
 {key:"posts",label:"Beiträge",nets:ORDER},
 {key:"followers",label:"Follower",nets:ORDER,stock:true},
 {key:"reach",label:"Reichweite",nets:["instagram"],
  missing:"Metricool liefert für Facebook-Seiten keine vergleichbare Reichweite."},
 {key:"profileViews",label:"Profilaufrufe",nets:["facebook"],
  missing:"Instagram-Profilaufrufe hat Meta abgekündigt – kein belastbarer Wert mehr."}];
var state={gran:"monthly",metric:"views",month:null};
function periods(){return state.gran==="weekly"?D.weeks:D.months;}
function niceMax(v){if(v<=0)return 1;
  var mag=Math.pow(10,Math.floor(Math.log10(v))),n=v/mag;
  var s=n<=1?1:n<=2?2:n<=2.5?2.5:n<=5?5:10;return s*mag;}
function shortNum(v){return v>=10000?Math.round(v/1000)+"k":nf(v);}

function chartSVG(nk,metric){
  var list=periods();
  var pts=list.map(function(p){return {label:p.labelShort,full:p.label,start:p.start,end:p.end,
    complete:p.complete,value:p[nk][metric.key]};});
  var wd=pts.filter(function(p){return p.value!==null&&p.value!==undefined;});
  if(!wd.length)return null;
  if(metric.stock){var fi=pts.findIndex(function(p){return p.value!==null&&p.value!==undefined;});pts=pts.slice(fi);}
  var W=560,H=220,padL=54,padR=10,padT=18,padB=30;
  var iw=W-padL-padR,ih=H-padT-padB;
  var minV=0,maxV=niceMax(Math.max.apply(null,wd.map(function(p){return p.value;})));
  if(metric.stock){var vs=wd.map(function(p){return p.value;});
    var lo=Math.min.apply(null,vs),hi=Math.max.apply(null,vs),pad=Math.max(1,(hi-lo)*0.18);
    minV=Math.max(0,Math.floor((lo-pad)/100)*100);maxV=Math.ceil((hi+pad)/100)*100;}
  var span=maxV-minV||1,y=function(v){return padT+ih-((v-minV)/span)*ih;};
  var n=pts.length,slot=iw/n,bw=Math.max(3,Math.min(34,slot-2));
  var ticks=[minV,minV+span/2,maxV],o=[];
  o.push('<svg viewBox="0 0 '+W+" "+H+'" role="img" aria-label="'+
    esc(NET[nk].label+" – "+metric.label+" je "+(state.gran==="weekly"?"Kalenderwoche":"Monat"))+'">');
  ticks.forEach(function(t){
    o.push('<line x1="'+padL+'" y1="'+y(t).toFixed(1)+'" x2="'+(W-padR)+'" y2="'+y(t).toFixed(1)+
      '" stroke="#e6e3ee" stroke-width="1"/>');
    o.push('<text x="'+(padL-8)+'" y="'+(y(t)+4).toFixed(1)+
      '" text-anchor="end" font-size="10.5" fill="#8b849c">'+shortNum(t)+"</text>");});
  var showVal=n<=8&&!metric.stock;
  pts.forEach(function(p,i){
    var cx=padL+slot*i+slot/2;
    if(p.value!==null&&p.value!==undefined){
      if(metric.stock){
        o.push('<circle class="bar'+(p.complete?"":" bar--partial")+'" cx="'+cx.toFixed(1)+
          '" cy="'+y(p.value).toFixed(1)+'" r="4.5" fill="'+NET[nk].color+
          '" stroke="#f5f4f8" stroke-width="2" data-i="'+i+'"/>');
      }else{
        var h=Math.max(1,padT+ih-y(p.value));
        o.push('<rect class="bar'+(p.complete?"":" bar--partial")+'" x="'+(cx-bw/2).toFixed(1)+
          '" y="'+y(p.value).toFixed(1)+'" width="'+bw.toFixed(1)+'" height="'+h.toFixed(1)+
          '" rx="'+Math.min(4,bw/2).toFixed(1)+'" fill="'+NET[nk].color+'" data-i="'+i+'"/>');
        if(showVal)o.push('<text x="'+cx.toFixed(1)+'" y="'+(y(p.value)-6).toFixed(1)+
          '" text-anchor="middle" font-size="11" font-weight="700" fill="#5b5470">'+shortNum(p.value)+"</text>");}}
    if(i%Math.ceil(n/9)===0||i===n-1)
      o.push('<text x="'+cx.toFixed(1)+'" y="'+(H-10)+'" text-anchor="middle" font-size="10.5" fill="#8b849c">'+
        esc(p.label)+"</text>");
    o.push('<rect x="'+(padL+slot*i).toFixed(1)+'" y="'+padT+'" width="'+slot.toFixed(1)+
      '" height="'+ih+'" fill="transparent" data-i="'+i+'"/>');});
  if(metric.stock){
    var line=pts.filter(function(p){return p.value!==null&&p.value!==undefined;}).map(function(p){
      var i=pts.indexOf(p);return (padL+slot*i+slot/2).toFixed(1)+","+y(p.value).toFixed(1);}).join(" ");
    o.splice(1+ticks.length*2,0,'<polyline points="'+line+'" fill="none" stroke="'+NET[nk].color+
      '" stroke-width="2" stroke-linejoin="round"/>');}
  o.push('<line x1="'+padL+'" y1="'+(padT+ih)+'" x2="'+(W-padR)+'" y2="'+(padT+ih)+
    '" stroke="#d5d1e0" stroke-width="1"/>');
  o.push("</svg>");
  return {svg:o.join(""),pts:pts,total:wd.reduce(function(a,p){return a+p.value;},0),avg:wd.reduce(function(a,p){return a+p.value;},0)/wd.length};}

function renderCharts(){
  var metric=METRICS.filter(function(m){return m.key===state.metric;})[0];
  var host=document.getElementById("charts");host.innerHTML="";
  ORDER.forEach(function(nk){
    var panel=document.createElement("section");
    panel.className="panel";panel.style.setProperty("--accent",NET[nk].color);
    if(metric.nets.indexOf(nk)===-1){
      panel.innerHTML='<div class="panel__head"><span class="panel__dot"></span><h3 class="panel__title">'+
        esc(NET[nk].label)+'</h3></div><p class="panel__meta">'+esc(metric.label)+
        ' – nicht verfügbar</p><div class="chart-empty">'+esc(metric.missing||"Kennzahl liegt nicht vor.")+"</div>";
      host.appendChild(panel);return;}
    var b=chartSVG(nk,metric);
    if(!b){panel.innerHTML='<div class="panel__head"><span class="panel__dot"></span><h3 class="panel__title">'+
      esc(NET[nk].label)+'</h3></div><div class="chart-empty">Keine Daten.</div>';host.appendChild(panel);return;}
    var last=b.pts[b.pts.length-1];
    var isAvg=metric.stock||metric.key==="viewsPerPost";
    var headline=metric.stock?nf(last.value):(metric.key==="viewsPerPost"?nf(b.avg):nf(b.total));
    var meta=metric.stock?("Stand "+dmy(last.end))
      :(metric.key==="viewsPerPost"?"Durchschnitt über alle dargestellten Zeiträume"
      :"Summe über alle dargestellten "+(state.gran==="weekly"?"Wochen":"Monate"));
    panel.innerHTML='<div class="panel__head"><span class="panel__dot"></span><h3 class="panel__title">'+
      esc(NET[nk].label)+" · "+esc(metric.label)+'</h3></div><p class="panel__value">'+headline+
      '</p><p class="panel__meta">'+esc(meta)+'</p><div class="chart">'+b.svg+'<div class="tip" role="status"></div></div>';
    host.appendChild(panel);
    var chart=panel.querySelector(".chart"),tip=panel.querySelector(".tip"),svg=panel.querySelector("svg");
    svg.addEventListener("mousemove",function(ev){
      var t=ev.target.closest("[data-i]");
      if(!t){tip.dataset.show="0";return;}
      var p=b.pts[+t.dataset.i];
      if(!p||p.value===null||p.value===undefined){tip.dataset.show="0";return;}
      var box=chart.getBoundingClientRect();
      tip.innerHTML="<b>"+nf(p.value)+"</b> "+esc(metric.label)+"<br><i>"+esc(p.full)+" · "+
        rng(p.start,p.end)+(p.complete?"":" · unvollständig")+"</i>";
      tip.style.left=(ev.clientX-box.left)+"px";tip.style.top=(ev.clientY-box.top-12)+"px";
      tip.dataset.show="1";});
    svg.addEventListener("mouseleave",function(){tip.dataset.show="0";});});
  renderEvoTable();
  var part=periods().filter(function(p){return !p.complete;});
  document.getElementById("evolutionHint").innerHTML=
    "Blassere Balken kennzeichnen unvollständige Zeiträume"+
    (part.length?" ("+part.map(function(p){return esc(p.label);}).join(", ")+")":"")+
    ". Die Instagram-Reichweite ist die Summe der Tageswerte und damit keine eindeutige Personenzahl.";}

function renderEvoTable(){
  var list=periods();
  var head="<tr><th>Zeitraum</th><th>FB Aufrufe</th><th>FB Aufr./Beitr.</th><th>FB Beiträge</th>"+
    "<th>FB Follower</th><th>IG Aufrufe</th><th>IG Aufr./Beitr.</th><th>IG Reichweite</th>"+
    "<th>IG Beiträge</th><th>IG Follower</th></tr>";
  var body=list.slice().reverse().map(function(p){
    return '<tr class="'+(p.complete?"":"partial")+'"><th scope="row">'+esc(p.label)+(p.complete?"":" *")+"</th>"+
      "<td>"+nf(p.facebook.views)+"</td><td>"+nf(p.facebook.viewsPerPost)+"</td>"+
      "<td>"+nf(p.facebook.posts)+"</td><td>"+nf(p.facebook.followers)+"</td>"+
      "<td>"+nf(p.instagram.views)+"</td><td>"+nf(p.instagram.viewsPerPost)+"</td>"+
      "<td>"+nf(p.instagram.reach)+"</td><td>"+nf(p.instagram.posts)+"</td>"+
      "<td>"+nf(p.instagram.followers)+"</td></tr>";}).join("");
  document.getElementById("evolutionTable").innerHTML=
    '<table class="raw"><thead>'+head+"</thead><tbody>"+body+"</tbody></table>";}

/* ---------- Archiv ---------- */
function renderArchive(){
  var m=D.months.filter(function(x){return x.key===state.month;})[0];
  if(!m)return;
  document.getElementById("archiveFraming").innerHTML="<strong>"+esc(m.label)+":</strong> "+
    rng(m.start,m.end)+" gegen "+rng(m.prevStart,m.prevEnd)+
    (m.complete?"":" · der Monat läuft noch")+".";
  document.getElementById("archiveCards").innerHTML=ORDER.map(function(nk){
    return card(nk,m[nk],m["prev"+nk.charAt(0).toUpperCase()+nk.slice(1)],m.labelShort,"Vormonat");}).join("");
  Array.prototype.forEach.call(document.querySelectorAll("#monthControl button"),function(b){
    b.setAttribute("aria-pressed",b.dataset.month===state.month?"true":"false");});}

/* ---------- Steuerung ---------- */
function controls(){
  var mc=document.getElementById("metricControl");
  mc.innerHTML=METRICS.map(function(m){
    return '<button type="button" data-metric="'+m.key+'" aria-pressed="'+(m.key===state.metric)+'">'+
      esc(m.label)+"</button>";}).join("");
  mc.addEventListener("click",function(ev){
    var b=ev.target.closest("button[data-metric]");if(!b)return;
    state.metric=b.dataset.metric;
    Array.prototype.forEach.call(mc.querySelectorAll("button"),function(x){
      x.setAttribute("aria-pressed",x===b?"true":"false");});
    renderCharts();});
  var gc=document.getElementById("granControl");
  gc.addEventListener("click",function(ev){
    var b=ev.target.closest("button[data-gran]");if(!b)return;
    state.gran=b.dataset.gran;
    Array.prototype.forEach.call(gc.querySelectorAll("button"),function(x){
      x.setAttribute("aria-pressed",x===b?"true":"false");});
    renderCharts();});
  var desc=D.months.slice().reverse();
  var moc=document.getElementById("monthControl");
  moc.innerHTML=desc.map(function(m){
    return '<button type="button" data-month="'+m.key+'">'+esc(m.label)+"</button>";}).join("");
  moc.addEventListener("click",function(ev){
    var b=ev.target.closest("button[data-month]");if(!b)return;
    state.month=b.dataset.month;renderArchive();});
  var nc=desc.filter(function(m){return m.complete;})[0];
  state.month=(nc||desc[0]).key;
  window.__dash=state;}

document.getElementById("standMain").textContent=dmy(D.meta.lastData);
document.getElementById("standSub").textContent=D.meta.dayCount+" Tage erfasst · ab "+dmy(D.meta.firstData);
document.getElementById("brandId").textContent=D.meta.brandId;
document.getElementById("builtAt").textContent=dmy(D.meta.builtAt);
controls();renderSummary();renderEfficiency();renderCharts();renderDetail();renderArchive();
})();
</script>
</body>
</html>
"""


def render(payload, cfg):
    theme = cfg["theme"]
    brand = cfg["brand"]
    logo_uri = data_uri(brand.get("logo", "")) if brand.get("logo") else ""
    logo_html = ('<img class="logo" src="%s" alt="%s">' % (logo_uri, brand.get("footer", ""))
                 if logo_uri else
                 '<span class="logo logo--text">%s</span>' % brand.get("logoFallback", ""))
    rule = "".join('<i style="background:%s"></i>' % c for c in theme["rule"])
    theme_vars = "\n".join([
        "    --h1:%s; --h2:%s; --h3:%s;" % (theme["headerFrom"], theme["headerVia"], theme["headerTo"]),
        "    --accent:%s;" % theme["accent"],
    ])
    html = TEMPLATE
    for token, value in [
        ("%%TITLE%%", brand["name"]),
        ("%%SUBTITLE%%", brand["subtitle"]),
        ("%%BRANDNAME%%", brand["name"]),
        ("%%LOGO%%", logo_html),
        ("%%RULE%%", rule),
        ("%%THEMEVARS%%", theme_vars),
        ("%%FOOTERLONG%%", brand["footerLong"]),
        ("%%FOOTER%%", brand["footer"]),
        ("%%SOURCENAME%%", cfg["source"]["name"]),
        ("%%DATA%%", json.dumps(payload, ensure_ascii=False, separators=(",", ":"))),
    ]:
        html = html.replace(token, value)
    return html


def main():
    ap = argparse.ArgumentParser(description="Baut das Social-Media-Dashboard")
    ap.add_argument("--out", default="index.html")
    ap.add_argument("--today")
    args = ap.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))

    store = json.loads((DATA / "metricool_daily.json").read_text(encoding="utf-8"))
    days = store["days"]
    if not days:
        raise SystemExit("Datenspeicher ist leer.")

    first_data = date.fromisoformat(min(days))
    last_data = date.fromisoformat(max(days))
    months = build_months(days, last_data)
    weeks = build_weeks(days, last_data)
    current = next(m for m in months if m["key"] == last_data.strftime("%Y-%m"))

    payload = {
        "config": {"networks": cfg["networks"], "theme": cfg["theme"]},
        "meta": {
            "brandId": cfg["source"]["brandId"],
            "firstData": first_data.isoformat(),
            "lastData": last_data.isoformat(),
            "dayCount": len(days),
            "builtAt": today.isoformat(),
        },
        "verdict": build_headline(current, months),
        "current": current,
        "months": months,
        "weeks": weeks,
    }

    out = Path(args.out)
    if not out.is_absolute():
        out = BASE / out
    out.write_text(render(payload, cfg), encoding="utf-8")

    print("Dashboard geschrieben: %s (%.0f kB)" % (out, out.stat().st_size / 1024))
    print("Datenstand: %s · %d Tage · %d Monate · %d Wochen"
          % (de_date(last_data), len(days), len(months), len(weeks)))
    print("Kernaussage: " + payload["verdict"]["title"])
    t, p = current["total"], current["prevTotal"]
    print("  Aufrufe   %8s (Vormonat %s)" % (de_num(t["views"]), de_num(p["views"])))
    print("  Beiträge  %8s (Vormonat %s)" % (de_num(t["posts"]), de_num(p["posts"])))
    print("  Aufr./Beitrag %4s (Vormonat %s)" % (de_num(t["viewsPerPost"]), de_num(p["viewsPerPost"])))


if __name__ == "__main__":
    main()

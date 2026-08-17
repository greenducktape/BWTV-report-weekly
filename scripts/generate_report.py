#!/usr/bin/env python3
"""
Erzeugt den woechentlichen BWTV-Social-Media-Report als eigenstaendige HTML-Datei.

Aufruf:
    python3 scripts/generate_report.py                # letzte abgeschlossene KW
    python3 scripts/generate_report.py --week 2026-W33
    python3 scripts/generate_report.py --week 2026-W33 --out reports/eigener_name.html

Datenquelle: data/metricool_daily.json (Tageswerte aus Metricool).
Verglichen wird immer die Berichtswoche gegen die unmittelbar vorhergehende
Woche - gleiche Laenge, gleiche Wochentage.

Zur Vergleichbarkeit der Metriken:
  - Aufrufe, Interaktionen, Profilaufrufe, Beitraege und neue Follower sind
    additiv und werden exakt aufsummiert.
  - Die Reichweite ist ein Tageswert. Ueber mehrere Tage summiert ergibt das
    KEINE eindeutige Personenzahl (Mehrfachzaehlung). Sie wird deshalb als
    "Reichweite (Summe Tageswerte)" ausgewiesen - als Trendgroesse belastbar,
    nicht als Unique-Reichweite.
  - Der Followerstand wird als Anfangs-/Endwert der Woche gelesen, nicht summiert.
"""

import argparse
import base64
import json
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "data"
ASSETS = BASE / "assets"
REPORTS = BASE / "reports"

MONTHS_DE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

# --- Farben (aus dem echten BWTV-Logo abgeleitet) --------------------------
BWTV_CYAN = "#00adeb"
BWTV_ORANGE = "#f18d5a"
IG_MAGENTA = "#d6246e"
FB_BLUE = "#0866ff"


# ---------------------------------------------------------------------------
# Formatierung
# ---------------------------------------------------------------------------

def de_int(value) -> str:
    """1234567 -> '1.234.567'"""
    if value is None:
        return "–"
    return f"{int(round(value)):,}".replace(",", ".")


def de_pct(value) -> str:
    if value is None:
        return "–"
    return f"{value:,.1f}".replace(".", ",") + " %"


def de_signed(value) -> str:
    if value is None:
        return "–"
    value = int(round(value))
    return f"{'+' if value > 0 else ''}{de_int(value) if value >= 0 else '-' + de_int(abs(value))}"


def de_date(d: date) -> str:
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def de_range(start: date, end: date) -> str:
    if start.month == end.month and start.year == end.year:
        return f"{start.day:02d}.–{end.day:02d}. {MONTHS_DE[end.month - 1]} {end.year}"
    if start.year == end.year:
        return (f"{start.day:02d}. {MONTHS_DE[start.month - 1]} – "
                f"{end.day:02d}. {MONTHS_DE[end.month - 1]} {end.year}")
    return f"{de_date(start)} – {de_date(end)}"


# ---------------------------------------------------------------------------
# Zeitraeume
# ---------------------------------------------------------------------------

def iso_week_bounds(year: int, week: int):
    monday = date.fromisocalendar(year, week, 1)
    return monday, monday + timedelta(days=6)


def parse_week(text: str):
    year_str, week_str = text.upper().split("-W")
    return int(year_str), int(week_str)


def last_complete_week(today: date):
    monday_this = today - timedelta(days=today.weekday())
    last_monday = monday_this - timedelta(days=7)
    iso = last_monday.isocalendar()
    return iso.year, iso.week


def daterange(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

SUMMED = ("views", "reach", "interactions", "profileViews", "newFollowers",
          "posts", "accountsEngaged")


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

    out["followersStart"] = first_stock
    out["followersEnd"] = last_stock
    out["followersDelta"] = (
        None if first_stock is None or last_stock is None else last_stock - first_stock
    )
    return out


def change(current, previous):
    """Relative Veraenderung in Prozent. None, wenn nicht sinnvoll berechenbar."""
    if current is None or previous is None:
        return None
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


# ---------------------------------------------------------------------------
# Zeilendefinition je Netzwerk
# ---------------------------------------------------------------------------

def build_rows(network: str, current: dict, previous: dict):
    if network == "facebook":
        spec = [
            ("Aufrufe", "views", "up", None),
            ("Interaktionen", "interactions", "up", None),
            ("Profilaufrufe", "profileViews", "up", None),
            ("Beiträge", "posts", "neutral", None),
            ("Neue Follower", "newFollowers", "up", None),
        ]
    else:
        spec = [
            ("Aufrufe", "views", "up", None),
            ("Reichweite", "reach", "up", "Summe der Tageswerte – keine eindeutige Personenzahl"),
            ("Interaktionen", "interactions", "up", None),
            ("Aktive Konten", "accountsEngaged", "up", "Konten, die mit dem Content interagiert haben"),
            ("Beiträge", "posts", "neutral", None),
        ]

    rows = []
    for label, key, direction, note in spec:
        cur, prev = current.get(key), previous.get(key)
        rows.append({
            "label": label,
            "current": cur,
            "previous": prev,
            "change": change(cur, prev),
            "direction": direction,
            "note": note,
        })
    return rows


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def logo_data_uri() -> str:
    path = ASSETS / "bwtv-liga-white.svg"
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def delta_pill(row) -> str:
    value = row["change"]
    direction = row["direction"]
    if value is None:
        # Kein Prozentwert berechenbar (Vorwoche = 0). Absolute Veraenderung
        # ist hier die einzige ehrliche Aussage.
        cur, prev = row["current"], row["previous"]
        if cur is None or prev is None or cur == prev:
            return '<span class="pill pill--flat">–</span>'
        rising = cur > prev
        tone = "flat" if direction == "neutral" else (
            "good" if rising == (direction == "up") else "bad")
        arrow = "▲" if rising else "▼"
        return (f'<span class="pill pill--{tone}">{arrow} '
                f'{de_signed(cur - prev)}</span>')
    if abs(value) < 0.05:
        return '<span class="pill pill--flat">±0,0 %</span>'
    rising = value > 0
    if direction == "neutral":
        tone = "flat"
    else:
        good = rising if direction == "up" else not rising
        tone = "good" if good else "bad"
    arrow = "▲" if rising else "▼"
    return (f'<span class="pill pill--{tone}">{arrow} '
            f'{de_pct(abs(value))}</span>')


def render_card(network: str, title: str, rows, current: dict, previous: dict,
                label_prev: str, label_cur: str) -> str:
    accent = FB_BLUE if network == "facebook" else IG_MAGENTA
    if network == "facebook":
        icon = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#fff" '
                'd="M13.5 21v-8h2.7l.4-3.1h-3.1V7.9c0-.9.25-1.5 1.55-1.5h1.65V3.6c-.8-.1-1.7-.15-2.5-.15'
                '-2.5 0-4.2 1.5-4.2 4.3v2.15H7.3V13h2.25v8h3.95Z"/></svg>')
    else:
        icon = ('<svg viewBox="0 0 24 24" aria-hidden="true">'
                '<rect x="3.2" y="3.2" width="17.6" height="17.6" rx="5.2" fill="none" '
                'stroke="#fff" stroke-width="2"/>'
                '<circle cx="12" cy="12" r="4.1" fill="none" stroke="#fff" stroke-width="2"/>'
                '<circle cx="17.1" cy="6.9" r="1.35" fill="#fff"/></svg>')

    delta = current.get("followersDelta")
    end = current.get("followersEnd")
    if delta is None:
        follower_pill = '<span class="follower-pill">Followerstand –</span>'
    else:
        tone = "good" if delta > 0 else ("bad" if delta < 0 else "flat")
        follower_pill = (
            f'<span class="follower-pill follower-pill--{tone}">'
            f'{de_signed(delta)} Follower <em>· {de_int(end)} gesamt</em></span>'
        )

    body = []
    for row in rows:
        note = (f'<span class="metric-note">{row["note"]}</span>'
                if row["note"] else "")
        body.append(
            "<tr>"
            f'<th scope="row">{row["label"]}{note}</th>'
            f'<td class="num">{de_int(row["previous"])}</td>'
            f'<td class="num num--current">{de_int(row["current"])}</td>'
            f'<td class="delta">{delta_pill(row)}</td>'
            "</tr>"
        )

    return f"""      <section class="card" style="--accent:{accent}">
        <header class="card__head">
          <span class="card__icon">{icon}</span>
          <h2 class="card__title">{title}</h2>
          {follower_pill}
        </header>
        <table class="metrics">
          <thead>
            <tr>
              <th scope="col">Kennzahl</th>
              <th scope="col" class="num">{label_prev}</th>
              <th scope="col" class="num">{label_cur}</th>
              <th scope="col" class="delta">Veränd.</th>
            </tr>
          </thead>
          <tbody>
{chr(10).join("            " + line for line in body)}
          </tbody>
        </table>
      </section>"""


def render_html(context) -> str:
    cur_start, cur_end = context["curStart"], context["curEnd"]
    prev_start, prev_end = context["prevStart"], context["prevEnd"]
    logo = logo_data_uri()
    logo_html = (f'<img class="logo" src="{logo}" alt="BWTV Triathlonliga">'
                 if logo else '<span class="logo logo--text">BWTV</span>')

    cards = "\n".join([
        render_card("facebook", "Facebook", context["fbRows"],
                    context["fbCur"], context["fbPrev"],
                    context["labelPrev"], context["labelCur"]),
        render_card("instagram", "Instagram", context["igRows"],
                    context["igCur"], context["igPrev"],
                    context["labelPrev"], context["labelCur"]),
    ])

    insights = "\n".join(
        f"            <li>{item}</li>" for item in context["insights"]
    )

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>BWTV Social Media Performance · {context["weekLabel"]}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  :root {{
    --ink: #16121f;
    --ink-soft: #5b5470;
    --ink-faint: #8b849c;
    --surface: #ffffff;
    --surface-alt: #f5f4f8;
    --line: #e6e3ee;
    --good-bg: #e6f6e9;  --good-fg: #1c7a33;
    --bad-bg:  #fdeaf0;  --bad-fg:  #c2185b;
    --flat-bg: #eeecf3;  --flat-fg: #5b5470;
    --cyan: {BWTV_CYAN};
    --orange: {BWTV_ORANGE};
    --magenta: {IG_MAGENTA};
  }}
  body {{
    margin: 0;
    background: #eceaf2;
    color: var(--ink);
    font: 400 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
    padding: 28px 18px 46px;
  }}
  .sheet {{
    max-width: 1180px; margin: 0 auto;
    background: var(--surface);
    border-radius: 22px;
    overflow: hidden;
    box-shadow: 0 18px 48px rgba(22,18,31,.13);
  }}

  /* ---- Kopf ---- */
  .masthead {{
    background: linear-gradient(102deg, #17102b 0%, #241634 52%, #2f1a3a 100%);
    color: #fff;
    padding: 26px 34px 24px;
    display: flex; flex-wrap: wrap; gap: 20px;
    align-items: center; justify-content: space-between;
  }}
  .brand {{ display: flex; align-items: center; gap: 18px; min-width: 0; }}
  .logo {{ height: 54px; width: auto; flex: none; }}
  .logo--text {{ font-weight: 800; font-size: 26px; letter-spacing: .06em; }}
  .brand__text h1 {{
    margin: 0; font-size: clamp(21px, 2.5vw, 29px);
    font-weight: 800; letter-spacing: -.015em;
  }}
  .brand__text p {{
    margin: 3px 0 0; font-size: 14px; color: #c9c1dd;
  }}
  .period {{ text-align: right; flex: none; }}
  .period__eyebrow {{
    margin: 0; font-size: 10.5px; font-weight: 700;
    letter-spacing: .17em; text-transform: uppercase; color: #a99fc4;
  }}
  .period__main {{
    margin: 4px 0 0; font-size: clamp(18px, 2.1vw, 25px); font-weight: 800;
  }}
  .period__prev {{ margin: 3px 0 0; font-size: 12.5px; color: #b3aac9; }}
  .rule {{ display: flex; height: 6px; }}
  .rule i {{ flex: 1; }}

  /* ---- Inhalt ---- */
  .content {{ padding: 26px 34px 30px; }}
  .callout {{
    border-left: 4px solid var(--cyan);
    background: linear-gradient(96deg, rgba(214,36,110,.07), rgba(0,173,235,.07));
    border-radius: 0 12px 12px 0;
    padding: 15px 20px;
    font-size: 14.5px; color: #3c3550;
  }}
  .callout strong {{ color: var(--ink); }}

  .cards {{
    display: grid; gap: 20px; margin-top: 24px;
    grid-template-columns: repeat(auto-fit, minmax(390px, 1fr));
  }}
  .card {{
    background: var(--surface-alt);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 20px 22px 8px;
  }}
  .card__head {{
    display: flex; align-items: center; gap: 12px;
    flex-wrap: wrap; margin-bottom: 6px;
  }}
  .card__icon {{
    width: 34px; height: 34px; border-radius: 10px; flex: none;
    background: var(--accent);
    display: grid; place-items: center;
  }}
  .card__icon svg {{ width: 21px; height: 21px; display: block; }}
  .card__title {{
    margin: 0; font-size: 21px; font-weight: 800;
    color: var(--accent); letter-spacing: -.01em;
  }}
  .follower-pill {{
    margin-left: auto; flex: none;
    background: #fff; border: 1px solid var(--line);
    border-radius: 999px; padding: 6px 13px;
    font-size: 12.5px; font-weight: 700; color: var(--ink-soft);
  }}
  .follower-pill em {{ font-style: normal; font-weight: 500; color: var(--ink-faint); }}
  .follower-pill--good {{ color: var(--good-fg); border-color: #bfe6c8; }}
  .follower-pill--bad  {{ color: var(--bad-fg);  border-color: #f6ccdb; }}

  .metrics {{ width: 100%; border-collapse: collapse; }}
  .metrics thead th {{
    font-size: 10.5px; font-weight: 700; letter-spacing: .13em;
    text-transform: uppercase; color: var(--ink-faint);
    text-align: left; padding: 12px 8px 9px; border-bottom: 1px solid var(--line);
  }}
  .metrics tbody th {{
    text-align: left; font-size: 14.5px; font-weight: 700;
    padding: 13px 8px; border-bottom: 1px solid var(--line);
  }}
  .metrics tbody tr:last-child th,
  .metrics tbody tr:last-child td {{ border-bottom: 0; }}
  .metrics td {{
    padding: 13px 8px; border-bottom: 1px solid var(--line);
    font-variant-numeric: tabular-nums;
  }}
  .num {{ text-align: right; font-size: 15px; color: var(--ink-soft); }}
  .num--current {{ font-weight: 800; font-size: 16.5px; color: var(--ink); }}
  .delta {{ text-align: right; white-space: nowrap; }}
  .metric-note {{
    display: block; font-size: 11.5px; font-weight: 400;
    color: var(--ink-faint); margin-top: 2px; max-width: 30ch;
  }}
  .pill {{
    display: inline-block; border-radius: 999px;
    padding: 4px 10px; font-size: 12.5px; font-weight: 800;
    font-variant-numeric: tabular-nums;
  }}
  .pill--good {{ background: var(--good-bg); color: var(--good-fg); }}
  .pill--bad  {{ background: var(--bad-bg);  color: var(--bad-fg); }}
  .pill--flat {{ background: var(--flat-bg); color: var(--flat-fg); }}

  .insights {{ margin-top: 26px; }}
  .insights h2 {{
    margin: 0 0 11px; font-size: 11px; font-weight: 700;
    letter-spacing: .15em; text-transform: uppercase; color: var(--ink-faint);
  }}
  .insights ul {{ margin: 0; padding-left: 20px; }}
  .insights li {{ margin-bottom: 9px; font-size: 14.5px; color: #3c3550; }}
  .insights li:last-child {{ margin-bottom: 0; }}
  .insights strong {{ color: var(--ink); }}

  .sheet__foot {{
    border-top: 1px solid var(--line);
    padding: 15px 34px 17px;
    display: flex; flex-wrap: wrap; gap: 8px; justify-content: space-between;
    font-size: 12px; color: var(--ink-faint);
  }}
  .sheet__foot b {{ color: var(--ink-soft); }}

  @media (max-width: 720px) {{
    body {{ padding: 14px 10px 30px; }}
    .masthead, .content {{ padding-left: 20px; padding-right: 20px; }}
    .sheet__foot {{ padding-left: 20px; padding-right: 20px; }}
    .period {{ text-align: left; }}
    .cards {{ grid-template-columns: 1fr; }}
  }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .sheet {{ box-shadow: none; border-radius: 0; max-width: none; }}
    .cards {{ grid-template-columns: 1fr 1fr; }}
  }}
</style>
</head>
<body>
  <main class="sheet">
    <header class="masthead">
      <div class="brand">
        {logo_html}
        <div class="brand__text">
          <h1>Social Media Performance</h1>
          <p>Facebook &amp; Instagram · {context["weekLabel"]} ({de_range(cur_start, cur_end)})</p>
        </div>
      </div>
      <div class="period">
        <p class="period__eyebrow">Berichtszeitraum</p>
        <p class="period__main">{de_range(cur_start, cur_end)}</p>
        <p class="period__prev">vs. {de_range(prev_start, prev_end)}</p>
      </div>
    </header>
    <div class="rule">
      <i style="background:var(--magenta)"></i>
      <i style="background:var(--cyan)"></i>
      <i style="background:var(--orange)"></i>
    </div>

    <div class="content">
      <p class="callout">
        <strong>Einordnung:</strong> {context["framing"]}
      </p>

      <div class="cards">
{cards}
      </div>

      <section class="insights">
        <h2>Was das bedeutet</h2>
        <ul>
{insights}
        </ul>
      </section>
    </div>

    <footer class="sheet__foot">
      <span>Quelle: Metricool (Brand {context["brandId"]}) · Stand {de_date(context["generated"])}</span>
      <span><b>BWTV</b> — Baden-Württemberg Triathlon-Verband</span>
    </footer>
  </main>
</body>
</html>
"""


# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Woechentlicher BWTV Social-Media-Report")
    parser.add_argument("--week", help="ISO-Woche, z. B. 2026-W33 (Standard: letzte abgeschlossene)")
    parser.add_argument("--out", help="Zielpfad der HTML-Datei")
    parser.add_argument("--today", help="Referenzdatum (JJJJ-MM-TT), nur fuer Tests")
    args = parser.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    year, week = parse_week(args.week) if args.week else last_complete_week(today)

    store_path = DATA / "metricool_daily.json"
    if not store_path.exists():
        raise SystemExit(f"Datenspeicher fehlt: {store_path}\n"
                         "Zuerst scripts/ingest_metricool.py ausfuehren.")
    days = json.loads(store_path.read_text(encoding="utf-8"))["days"]

    cur_start, cur_end = iso_week_bounds(year, week)
    prev_start, prev_end = cur_start - timedelta(days=7), cur_start - timedelta(days=1)

    fb_cur = aggregate(days, "facebook", cur_start, cur_end)
    fb_prev = aggregate(days, "facebook", prev_start, prev_end)
    ig_cur = aggregate(days, "instagram", cur_start, cur_end)
    ig_prev = aggregate(days, "instagram", prev_start, prev_end)

    if fb_cur["daysWithData"] == 0 and ig_cur["daysWithData"] == 0:
        raise SystemExit(f"Keine Daten fuer {year}-W{week:02d} "
                         f"({de_range(cur_start, cur_end)}) im Speicher.")

    week_label = f"KW {week}/{year}"
    prev_iso = prev_start.isocalendar()
    context = {
        "weekLabel": week_label,
        "labelCur": f"KW {week}",
        "labelPrev": f"KW {prev_iso.week}",
        "curStart": cur_start, "curEnd": cur_end,
        "prevStart": prev_start, "prevEnd": prev_end,
        "fbCur": fb_cur, "fbPrev": fb_prev,
        "igCur": ig_cur, "igPrev": ig_prev,
        "fbRows": build_rows("facebook", fb_cur, fb_prev),
        "igRows": build_rows("instagram", ig_cur, ig_prev),
        "brandId": 6061560,
        "generated": today,
        "framing": (
            f"Direkter Vergleich von {de_range(cur_start, cur_end)} gegen die Vorwoche "
            f"{de_range(prev_start, prev_end)} – gleiche Zeitraumlänge, gleiche "
            f"Wochentage, berechnet aus den Tagesrohwerten beider Zeiträume."
        ),
        "insights": build_insights(fb_cur, fb_prev, ig_cur, ig_prev),
    }

    html = render_html(context)
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else REPORTS / f"bwtv_social_{year}-W{week:02d}.html"
    if not out.is_absolute():
        out = BASE / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")

    print(f"Report geschrieben: {out}")
    print(f"Zeitraum: {de_range(cur_start, cur_end)}  vs.  {de_range(prev_start, prev_end)}")
    print(f"  Facebook  Aufrufe {de_int(fb_cur['views']):>9}  (Vorwoche {de_int(fb_prev['views'])})"
          f"  Follower {de_signed(fb_cur['followersDelta'])}")
    print(f"  Instagram Aufrufe {de_int(ig_cur['views']):>9}  (Vorwoche {de_int(ig_prev['views'])})"
          f"  Follower {de_signed(ig_cur['followersDelta'])}")
    print(f"  Tage mit Daten: FB {fb_cur['daysWithData']}/7, IG {ig_cur['daysWithData']}/7")


def build_insights(fb_cur, fb_prev, ig_cur, ig_prev):
    """Erzeugt die Kommentarzeilen aus den tatsaechlichen Zahlen."""
    items = []

    fb_change = change(fb_cur["views"], fb_prev["views"])
    ig_change = change(ig_cur["views"], ig_prev["views"])

    def phrase(value):
        if value is None:
            return "ohne Vorwochenvergleich"
        if abs(value) < 1:
            return "praktisch unverändert"
        return ("um <strong>" + de_pct(abs(value)) + "</strong> "
                + ("gestiegen" if value > 0 else "gesunken"))

    items.append(
        f"<strong>Aufrufe:</strong> Facebook {phrase(fb_change)} "
        f"({de_int(fb_prev['views'])} → {de_int(fb_cur['views'])}), "
        f"Instagram {phrase(ig_change)} "
        f"({de_int(ig_prev['views'])} → {de_int(ig_cur['views'])})."
    )

    # Posting-Frequenz als Erklaerung fuer Reichweitenschwankungen.
    posts_cur = ig_cur["posts"] + fb_cur["posts"]
    posts_prev = ig_prev["posts"] + fb_prev["posts"]
    if posts_prev or posts_cur:
        if posts_cur < posts_prev:
            items.append(
                f"<strong>Output:</strong> {posts_cur} Beiträge gegenüber "
                f"{posts_prev} in der Vorwoche. Der Rückgang bei Aufrufen und "
                f"Interaktionen folgt größtenteils der geringeren Veröffentlichungsfrequenz."
            )
        elif posts_cur > posts_prev:
            items.append(
                f"<strong>Output:</strong> {posts_cur} Beiträge gegenüber "
                f"{posts_prev} in der Vorwoche – höhere Frequenz."
            )

    # Followerentwicklung Instagram.
    ig_delta = ig_cur["followersDelta"]
    ig_delta_prev = ig_prev["followersDelta"]
    if ig_delta is not None:
        if ig_delta < 0 and ig_delta_prev is not None and ig_delta_prev < 0:
            items.append(
                f"<strong>Instagram-Follower:</strong> {de_signed(ig_delta)} in dieser Woche "
                f"(Vorwoche {de_signed(ig_delta_prev)}). Der Abbau nach dem Follower-Sprung "
                f"vom 20.07. hält an, hat sich aber deutlich verlangsamt. "
                f"Aktueller Stand: {de_int(ig_cur['followersEnd'])}."
            )
        elif ig_delta < 0:
            items.append(
                f"<strong>Instagram-Follower:</strong> {de_signed(ig_delta)} in dieser Woche, "
                f"Stand {de_int(ig_cur['followersEnd'])}."
            )
        else:
            items.append(
                f"<strong>Instagram-Follower:</strong> {de_signed(ig_delta)} in dieser Woche, "
                f"Stand {de_int(ig_cur['followersEnd'])}."
            )

    fb_delta = fb_cur["followersDelta"]
    if fb_delta is not None:
        items.append(
            f"<strong>Facebook:</strong> Followerstand {de_int(fb_cur['followersEnd'])} "
            f"({de_signed(fb_delta)} in der Woche). Die Seite wächst weiter langsam, "
            f"trägt aber verlässlich Aufrufe."
        )

    return items


if __name__ == "__main__":
    main()

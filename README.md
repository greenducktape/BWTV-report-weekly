# BWTV Social Media Dashboard

Wöchentlich aktualisiertes Social-Media-Reporting für Facebook und Instagram des
**Baden-Württemberg Triathlon-Verbands**. Die Daten kommen aus Metricool, werden
tagesgenau gespeichert und als eine eigenständige `index.html` ausgegeben.

Die Seite ist eine einzelne HTML-Datei ohne externe Skripte, Fonts oder
Netzwerkzugriffe — sie funktioniert auch offline.

## Aufbau der Seite

1. **Kernaussage** — was die Zahlen in einem Satz sagen, mit den Belegen darunter.
   Der Text wird aus den Daten erzeugt und trennt bewusst *Menge* (wie viel wurde
   veröffentlicht) von *Wirkung* (was ein einzelner Beitrag bringt).
2. **Hero-Kennzahlen** — Aufrufe, Interaktionen, Follower und Beiträge mit
   Veränderung zum Vormonat, Aufteilung je Kanal und Sparkline der letzten 6 Monate.
3. **Wirkung je Beitrag** — Aufrufe und Interaktionen je Beitrag. Die wichtigste
   Ergänzung: Summen hängen davon ab, wie viel gepostet wurde. Erst diese Werte
   zeigen, ob Inhalte besser oder schlechter funktionieren.
4. **Verlauf** — umschaltbar zwischen Kalenderwochen und Monaten, für Aufrufe,
   Aufrufe je Beitrag, Interaktionen, Beiträge, Follower, Reichweite und
   Profilaufrufe. Facebook und Instagram in getrennten Panels mit eigener Skala.
5. **Details** — vollständige Kennzahlentabelle je Kanal.
6. **Monatsarchiv** — jeder Monat einzeln abrufbar, jeweils gegen den Vormonat.

Der laufende Monat wird immer gegen **denselben Zeitraum des Vormonats** gestellt
(gleiche Länge, gleiche Position), nicht gegen den vollen Vormonat — sonst
vergleicht man einen halben Monat mit einem ganzen.

## Verzeichnisse

```
├── index.html                  Das Dashboard (generiert – nicht manuell bearbeiten)
├── config.json                 Marke, Farben, Logo, Kanäle  ← für neue Kunden anpassen
├── vercel.json                 Deploy-Konfiguration (statisch, kein Build)
├── data/
│   ├── metricool_daily.json    Tageswerte aus Metricool – die laufende Quelle
│   └── history_meta.json       Tagesreihen März–Juli 2026 aus den Meta-Exporten
├── reports/                    Wochenreports als einzelne HTML-Dateien
├── assets/                     BWTV-Logos (SVG)
└── scripts/
    ├── ingest_metricool.py     Metricool-Rohantwort → Datenspeicher
    ├── build_site.py           Datenspeicher → index.html
    ├── generate_report.py      Datenspeicher → Wochenreport (einzelne KW)
    ├── progress.py             Wochen-/Monatsübersicht im Terminal
    ├── publish.py              Bauen, committen, nach main pushen
    └── backfill_meta_history.py   Historie aus den Meta-Exporten (einmalig)
```

## Wöchentlicher Ablauf

Läuft automatisch **montags um 9:05** über die geplante Aufgabe
`bwtv-wochenreport`: Daten holen → einlesen → Dashboard bauen → nach `main`
pushen. Vercel deployt den neuen Stand automatisch.

Manuell:

```bash
# 1. Daten aus Metricool holen (Brand 6061560) und als Payload ablegen
python3 scripts/ingest_metricool.py /pfad/zur/payload.json

# 2. Bauen, committen, veröffentlichen
python3 scripts/publish.py

# Nur bauen und Änderungen ansehen
python3 scripts/publish.py --dry-run
```

Fortschritt im Terminal:

```bash
python3 scripts/progress.py             # je Kalenderwoche
python3 scripts/progress.py --monthly   # je Monat
python3 scripts/progress.py --meta      # Meta-Exporte März–Juli
```

## Für einen anderen Kunden verwenden

Die Skripte enthalten nichts Kundenspezifisches. Für ein neues Dashboard reicht:

1. `config.json` anpassen — Name, Untertitel, Footer, Farben, Kanalfarben und die
   Metricool-Brand-ID.
2. Logo nach `assets/` legen und in `config.json` unter `brand.logo` eintragen
   (relativer Pfad, wird als Data-URI eingebettet). Ohne Logo wird
   `brand.logoFallback` als Schriftzug gesetzt.
3. `data/metricool_daily.json` leeren und mit den Daten der neuen Brand füllen.
4. `python3 scripts/build_site.py`

Die Kernaussage, die Kennzahlen und alle Diagramme passen sich automatisch an.
Getestet mit einer abweichenden Marke und Farbpalette.

## Kennzahlen

| Anzeige | Metricool | Bedeutung |
|---|---|---|
| FB Aufrufe | `FBEV49` | Page Media View — entspricht Metas „Aufrufe" |
| FB Profilaufrufe | `FBEV03` | Page Views |
| FB Interaktionen | `FBEV34` | Page Posts Interactions (Posts + Reels) |
| FB Beiträge | `FBEV33` | Posts + Reels |
| FB Neue Follower | `FBEV47` | Followers Acquired |
| FB Followerstand | `FBEV17` | Bestand |
| IG Aufrufe | `IGEV05` | Views |
| IG Reichweite | `IGEV06` | Tageswert (siehe unten) |
| IG Interaktionen | `IGEV38` | Account Posts Interactions (Posts + Reels) |
| IG Aktive Konten | `IGEV42` | Accounts Engaged |
| IG Beiträge | `IGEV37` | Posts + Reels |
| IG Followerstand | `IGEV01` | Bestand |

## Was sich summieren lässt und was nicht

Das Mapping ist gegen die Meta-Business-Suite-Exporte geprüft.

**Additiv — exakt über jeden Zeitraum summierbar.** Gegenprobe für
01.–17. Juli gegen 01.–17. Juni 2026: FB Aufrufe 15.550 / 11.453,
FB Interaktionen 71 / 46, FB Profilaufrufe 240 / 239, IG Interaktionen
3.709 / 2.176, IG Profilaufrufe 1.111 — alle Werte exakt reproduziert.
Auf Monatsebene stimmen die Facebook-Aufrufe (11.105 / 13.710 / 23.948 /
24.951) und die Instagram-Aufrufe (93.650 / 226.535 / 391.315 / 214.418)
mit den Meta-Exporten überein.

**Reichweite und „Betrachter" sind nicht additiv.** Meta dedupliziert diese über
den Zeitraum (eindeutige Personen), Metricool liefert Tageswerte:

| | Summe Tageswerte | Meta-Zeitraumwert |
|---|---|---|
| IG Reichweite 01.–17.06. | 34.321 | 18.568 |
| FB Betrachter 01.–17.06. | 5.257 | 2.778 |

Im Dashboard steht deshalb ausdrücklich **„Summe der Tageswerte"**. Als
Trendgröße ist der Wert belastbar, solange er immer gleich berechnet wird — eine
Personenzahl ist er nicht.

**Interaktionen zählen Metricool und Meta unterschiedlich.** Metricool zählt
beitragsbezogen (nur Beiträge des Zeitraums), Meta zählt alle Interaktionen im
Zeitraum unabhängig vom Beitragsdatum. Die Metricool-Werte liegen daher
systematisch niedriger. Innerhalb dieser Reihe ist das konsistent — die beiden
Quellen dürfen aber nicht direkt gegeneinander gestellt werden.

**Followerstand wird nicht summiert**, sondern als Anfangs- gegen Endwert der
Periode gelesen.

**Facebook hat keine vergleichbare Reichweite** und Instagram keine belastbaren
Profilaufrufe mehr (von Meta abgekündigt). Das Dashboard weist diese Lücken
sichtbar aus, statt sie mit Ersatzwerten zu füllen.

## Bekannte Auffälligkeit: Instagram-Follower Juli 2026

Am 20.07.2026 sprang der Instagram-Followerstand von 2.952 auf 4.980 (+2.028;
die Meta-Exporte verbuchen denselben Effekt am 18.07. mit +1.704). Seitdem baut
das Konto diese Follower kontinuierlich ab — Stand 16.08.2026: 4.192.

Das war kein organisches Wachstum. Der Rückgang ist als Normalisierung zu lesen,
nicht als Verlust echter Reichweite. Aussagen zum Followerwachstum sind für den
Zeitraum ab dem 20.07. nur eingeschränkt belastbar.

## Datenumfang

Erfasst ab **01.03.2026**. Der Followerstand liegt bei Instagram erst ab
19.06.2026 vor, bei Facebook ab 01.03.2026 — davor liefert Metricool keine
Bestandswerte. Diagramme beginnen entsprechend später, statt Nullwerte zu
erfinden.

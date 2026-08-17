#!/usr/bin/env python3
"""
Veroeffentlicht den aktuellen Stand des Dashboards: baut index.html neu,
committet die Aenderungen und schiebt sie nach main.

Aufruf:
    python3 scripts/publish.py               # bauen, committen, pushen
    python3 scripts/publish.py --dry-run     # nur bauen und Status zeigen
    python3 scripts/publish.py --no-push     # bauen und committen, nicht pushen

Der Push geht an das Remote 'origin' (Branch main). Wenn es keine Aenderungen
gibt, wird kein leerer Commit erzeugt.
"""

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def run(args, check=True, capture=True):
    result = subprocess.run(
        args, cwd=BASE, check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
        text=True,
    )
    if check and result.returncode != 0:
        sys.stdout.write(result.stdout or "")
        raise SystemExit(f"Abbruch: '{' '.join(args)}' endete mit Code {result.returncode}")
    return (result.stdout or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard bauen und veroeffentlichen")
    parser.add_argument("--dry-run", action="store_true", help="nur bauen, nichts committen")
    parser.add_argument("--no-push", action="store_true", help="committen, aber nicht pushen")
    parser.add_argument("--message", help="eigene Commit-Nachricht")
    args = parser.parse_args()

    if not (BASE / ".git").exists():
        raise SystemExit(f"Kein Git-Repository in {BASE}. Zuerst 'git init' und Remote setzen.")

    print("1/4  Dashboard bauen …")
    print(run([sys.executable, "scripts/build_site.py"]))

    print("\n2/4  Änderungen prüfen …")
    status = run(["git", "status", "--porcelain"])
    if not status:
        print("Keine Änderungen — nichts zu veröffentlichen.")
        return
    print(status)

    if args.dry_run:
        print("\n--dry-run: kein Commit, kein Push.")
        return

    print("\n3/4  Commit …")
    run(["git", "add", "-A"])
    message = args.message or f"Dashboard-Update {date.today().isoformat()}"
    print(run(["git", "commit", "-m", message]))

    if args.no_push:
        print("\n--no-push: Commit erstellt, nicht gepusht.")
        return

    print("\n4/4  Push nach origin/main …")
    print(run(["git", "push", "origin", "main"]))
    print("\nFertig. Vercel deployt den neuen Stand automatisch, "
          "sobald der Push auf main ankommt.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""
normalize_all_yaml.py

Orchestrateur qui :
  - lance les normalizers (cards, items, crafts)
  - collecte leurs erreurs / warnings
  - génère un HTML global de validation
  - ouvre ce HTML automatiquement sur Windows

Les normalizers doivent pouvoir être lancés avec :

    python normalize_xxx.py --json

et renvoyer une structure :

{
  "script": "normalize_items_yaml.py",
  "errors": [...],
  "warnings": [...],
  "infos": [...]
}
"""

from __future__ import annotations
import subprocess
import sys
from pathlib import Path
import yaml
import webbrowser
import datetime


THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[2]
REPORT_PATH = PROJECT_ROOT / "app" / "data" / "validation_report.html"


# ---------------------------------------------------------------------------
# Lancer un normalizer et récupérer sa sortie JSON/YAML
# ---------------------------------------------------------------------------

def run_normalizer(script_rel_path: str) -> dict:
    """
    Lance un normalizer via subprocess, en mode JSON/YAML.

    Chaque normalizer doit pouvoir être lancé avec :

        python normalize_xxx.py --json

    et écrire sur stdout un dict de la forme :

        {
           "script": "normalize_items_yaml.py",
           "errors": [...],
           "warnings": [...],
           "infos": [...]
        }
    """
    script_abs = PROJECT_ROOT / script_rel_path

    if not script_abs.exists():
        return {
            "script": script_rel_path,
            "errors": [f"Script not found: {script_abs}"],
            "warnings": [],
            "infos": []
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(script_abs), "--json"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True
        )
    except Exception as e:
        return {
            "script": script_rel_path,
            "errors": [f"Failed to execute: {e}"],
            "warnings": [],
            "infos": []
        }

    if proc.returncode != 0:
        return {
            "script": script_rel_path,
            "errors": [f"Exited with code {proc.returncode}", proc.stdout, proc.stderr],
            "warnings": [],
            "infos": []
        }

    try:
        # On accepte du JSON ou du YAML (JSON est un sous-ensemble valide)
        result = yaml.safe_load(proc.stdout)
        if not isinstance(result, dict):
            raise ValueError("Normalizer output is not a dict")
        # On s’assure que les clefs de base existent
        result.setdefault("script", script_rel_path)
        result.setdefault("errors", [])
        result.setdefault("warnings", [])
        result.setdefault("infos", [])
        return result
    except Exception:
        return {
            "script": script_rel_path,
            "errors": ["Invalid JSON/YAML output from normalizer", proc.stdout],
            "warnings": [],
            "infos": []
        }


# ---------------------------------------------------------------------------
# Génération du HTML
# ---------------------------------------------------------------------------

def make_html_report(results: list[dict]) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html: list[str] = []
    html.append(
        """
<!DOCTYPE html>
<html lang='fr'>
<head>
<meta charset='UTF-8'>
<title>LodyLand — YAML Validation Report</title>
<style>
body {
  background: #0b1020;
  color: #e5e7eb;
  font-family: system-ui, sans-serif;
  padding: 20px;
}
h1 { color: #38bdf8; }
h2 { margin-top: 35px; color: #93c5fd; }

.section {
  margin: 20px 0;
  padding: 20px;
  background: #131a2e;
  border: 1px solid #232b3f;
  border-radius: 8px;
}

.error { color: #f87171; }
.warn  { color: #fbbf24; }
.info  { color: #34d399; }

.status-ok {
  color: #34d399;
  font-weight: 600;
  margin-left: 8px;
}
.status-warn {
  color: #fbbf24;
  font-weight: 600;
  margin-left: 8px;
}
.status-error {
  color: #f87171;
  font-weight: 600;
  margin-left: 8px;
}

ul {
  padding-left: 20px;
}

pre {
  white-space: pre-wrap;
  background: #020617;
  border: 1px solid #1f2937;
  padding: 10px;
  border-radius: 5px;
}
</style>
</head>
<body>
<h1>YAML Validation Report</h1>
<p>Généré le : """
        + timestamp
        + """</p>
"""
    )

    # Pour chaque normalizer (cards, items, crafts)
    for result in results:
        script_label = result.get("script", "normalizer")
        errors = result.get("errors") or []
        warnings = result.get("warnings") or []
        infos = result.get("infos") or []

        has_errors = len(errors) > 0
        has_warnings = len(warnings) > 0
        all_ok = not has_errors and not has_warnings

        html.append("<div class='section'>")

        # Titre + statut
        if has_errors:
            status_span = "<span class='status-error'>❌ Erreurs</span>"
        elif has_warnings:
            status_span = "<span class='status-warn'>⚠ Avertissements</span>"
        else:
            status_span = "<span class='status-ok'>✓ OK</span>"

        html.append(f"<h2>{script_label}{status_span}</h2>")

        # Erreurs détaillées
        if has_errors:
            html.append("<h3 class='error'>❌ Errors</h3><ul>")
            for err in errors:
                html.append(f"<li class='error'>{err}</li>")
            html.append("</ul>")

        # Warnings détaillés
        if has_warnings:
            html.append("<h3 class='warn'>⚠ Warnings</h3><ul>")
            for w in warnings:
                html.append(f"<li class='warn'>{w}</li>")
            html.append("</ul>")

        # Infos :
        # - Si tout est OK (pas d’erreurs ni warnings) → on se contente d’un petit résumé “OK”
        # - Si erreurs / warnings présents → on peut afficher les infos (logs) si utiles
        if all_ok:
            html.append("<p class='info'>Tout est valide pour ce normalizer.</p>")
        elif infos:
            html.append("<h3 class='info'>✔ Infos</h3><ul>")
            for info in infos:
                html.append(f"<li class='info'>{info}</li>")
            html.append("</ul>")

        html.append("</div>")

    html.append("</body></html>")

    REPORT_PATH.write_text("\n".join(html), encoding="utf-8")
    print(f"[normalize_all] HTML report written to: {REPORT_PATH}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def run_all_normalizers(report_mode: bool = False) -> None:
    scripts = [
        "app/data/cards/normalize_cards_yaml.py",
        "app/data/items/normalize_items_yaml.py",
        "app/data/crafts/normalize_crafts_yaml.py",
        "app/data/lands/normalize_lands_yaml.py",
    ]

    results: list[dict] = []

    for scr in scripts:
        print(f"[normalize_all] Running: {scr}")
        r = run_normalizer(scr)
        results.append(r)

    make_html_report(results)

    # Ouvre le navigateur seulement si report_mode=True
    if report_mode:
        try:
            webbrowser.open(REPORT_PATH.as_uri())
            print("[normalize_all] Report opened in browser.")
        except Exception:
            print("[normalize_all] Could not open report automatically.")
    else:
        print("[normalize_all] Report generated (no auto-open).")


if __name__ == "__main__":
    run_all_normalizers()

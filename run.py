# run.py

import sys
from app import create_app
from app.data.normalize_all_yaml import run_all_normalizers

if __name__ == "__main__":
    # Argument optionnel : --report
    report_mode = "--report" in sys.argv

    # Exécuter les normalizers AVANT de lancer Flask
    run_all_normalizers(report_mode=report_mode)

    # Lancer l'app Flask
    app = create_app()
    app.run(debug=True)

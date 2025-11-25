# =============================================================================
# File: run.py
# Purpose: Entry point for development. Starts the minimal Flask app.
# =============================================================================
# run.py
from app.data.normalize_all_yaml import run_all_normalizers
from app import create_app

run_all_normalizers()

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)


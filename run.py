# =============================================================================
# File: run.py
# Purpose: Entry point for development. Starts the minimal Flask app.
# =============================================================================
# run.py
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)


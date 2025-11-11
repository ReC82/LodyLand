# =============================================================================
# File: run.py
# Purpose: Entry point for development. Starts the minimal Flask app.
# =============================================================================
from app import create_app

app = create_app()

if __name__ == "__main__":
    print("[BOOT] Flask minimal app starting on http://127.0.0.1:8000")
    app.run(host="127.0.0.1", port=8000, debug=True)

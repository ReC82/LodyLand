# run.py

import sys
from app import create_app
from app.data.normalize_all_yaml import run_all_normalizers

# Create the Flask app at module level so Gunicorn can import it
app = create_app()


if __name__ == "__main__":
    """
    Dev entrypoint:
    - Optionally run YAML normalizers (with --report)
    - Run the built-in Flask dev server
    """
    # Optional CLI argument: --report
    report_mode = "--report" in sys.argv

    # Run normalizers BEFORE starting Flask dev server
    run_all_normalizers(report_mode=report_mode)

    # Start Flask dev server (for local/dev usage only)
    app.run(host="0.0.0.0", port=5000, debug=True)

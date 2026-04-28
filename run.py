# run.py

import sys
from app import create_app
from app.data.normalize_all_yaml import run_all_normalizers

# Create the Flask app at module level so Gunicorn can import it
app = create_app()


if __name__ == "__main__":
    """
    Dev entrypoint:
    - Optionally run YAML normalizers (with --normalize or --report)
    - Run the built-in Flask dev server

    Flags:
      --normalize  Rebuild all generated YAML files from their sources
      --report     Same as --normalize but also opens an HTML report
    """
    normalize = "--normalize" in sys.argv or "--report" in sys.argv
    report_mode = "--report" in sys.argv

    if normalize:
        # Only rebuild YAML files when explicitly requested.
        # Do NOT run automatically on every restart — admin edits to lands.yml,
        # crafts.yml, etc. would be silently overwritten.
        run_all_normalizers(report_mode=report_mode)

    # Start Flask dev server (for local/dev usage only)
    app.run(host="0.0.0.0", port=5000, debug=True)

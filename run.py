"""
'What Did I Miss?' - AI Chat Log Summarizer Application Entry Point
"""
import os
from dotenv import load_dotenv
from app import create_app

load_dotenv()

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "True").lower() in ("true", "1", "t")
    print(f"Starting 'What Did I Miss?' server on http://localhost:{port} (Debug: {debug})...")
    app.run(host="0.0.0.0", port=port, debug=debug)

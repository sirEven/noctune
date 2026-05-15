#!/usr/bin/env python3
"""Start uvicorn with stderr logging to file for debugging."""
import os, sys, logging

# Configure logging so we can see errors
logging.basicConfig(level=logging.INFO)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import uvicorn
from pathlib import Path
from noctune.main import create_app

app = create_app(config_path=Path("~/.noctune/config.yaml"))
print(f"Created app with {len(app.routes)} routes")
sys.stdout.flush()

uvicorn.run(app, host="127.0.0.1", port=8001)
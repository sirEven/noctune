"""Dev server runner for Noctune backend — stays alive for background mode."""
import signal
import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from noctune.main import create_app
import uvicorn

# Ignore SIGTERM so background mode doesn't kill us
signal.signal(signal.SIGTERM, signal.SIG_IGN)

if __name__ == "__main__":
    config_path = Path(__file__).parent / "config.example.yaml"
    app = create_app(config_path=config_path)
    print("Noctune backend starting on http://0.0.0.0:8001", flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8001)
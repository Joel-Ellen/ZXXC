import sys
from pathlib import Path

import uvicorn


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from frontend.server import app


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8800, log_level="info")

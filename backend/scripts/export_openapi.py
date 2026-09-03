"""Write the broker's OpenAPI document for frontend contract generation."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.main import app

payload = json.dumps(app.openapi(), ensure_ascii=False)
if len(sys.argv) > 1:
    Path(sys.argv[1]).write_text(payload, encoding="utf-8")
else:
    sys.stdout.write(payload)

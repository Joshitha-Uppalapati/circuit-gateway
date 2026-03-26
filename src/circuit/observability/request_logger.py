import json
import os
from datetime import datetime

LOG_FILE = "src/circuit/logs/requests.jsonl"


def log_request(data: dict):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

    with open(LOG_FILE, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.utcnow().isoformat(),
            **data
        }) + "\n")
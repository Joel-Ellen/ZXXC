"""Apply resource-v4 metadata retention windows."""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.database.resource_generation_repo import ResourceGenerationRepo


def main() -> int:
    result = ResourceGenerationRepo(
        allow_memory_fallback=False
    ).purge_expired_metadata()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

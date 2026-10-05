"""Index only docs/assistant_kb_manifest.json into the assistant knowledge base."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.assistant import knowledge  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(knowledge.reindex(), ensure_ascii=False))

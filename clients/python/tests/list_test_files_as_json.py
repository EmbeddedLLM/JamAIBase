import json
from pathlib import Path

tests_dir = Path(__file__).parent.resolve()

files = []
i = 0
for d in tests_dir.iterdir():
    if not d.is_dir():
        continue
    if d.name in ["__pycache__", "_loader_check"]:
        continue
    for f in d.iterdir():
        if not f.is_file():
            continue
        files.append(
            {"uri": str(f.relative_to(tests_dir.parent)), "document_id": str(i), "access_level": 0}
        )
        i += 1

with open("files.json", "w", encoding="utf-8") as f:
    json.dump({"files": files}, f, ensure_ascii=False)

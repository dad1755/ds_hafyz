#!/usr/bin/env bash
# S9 hygiene evidence, run in the built image:
#   1. what the two new modules import and which methods they call (no training, no artifact I/O);
#   2. the repository's own secret-pattern sweep over the tree.
set -uo pipefail
cd /home/ec-user/non_prod/hafyz_ds

echo "\$ docker run --rm -i -v \"\$PWD:/app:z\" -w /app aihubcampus-web:s9 python - <<PY"
docker run --rm -i -v "$PWD:/app:z" -w /app aihubcampus-web:s9 python - <<'PY'
import ast
from pathlib import Path

for name in ("src/data_manager.py", "src/pages_datasets.py"):
    tree = ast.parse(Path(name).read_text(encoding="utf-8"))
    imports = sorted(
        {
            node.module if isinstance(node, ast.ImportFrom) else alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in (node.names if isinstance(node, ast.Import) else [node])
        }
    )
    methods = sorted(
        {
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        }
    )
    print(name)
    print("  imports:", ", ".join(imports))
    print("  methods called:", ", ".join(methods))
    for forbidden in ("fit", "predict", "dump", "load", "to_pickle"):
        print(f"  calls .{forbidden}(...): {forbidden in methods}")
PY

echo
echo "\$ python3 scripts/check_no_secrets.py   # on the host, where the operator's .env is readable"
python3 scripts/check_no_secrets.py
echo "exit=$?"

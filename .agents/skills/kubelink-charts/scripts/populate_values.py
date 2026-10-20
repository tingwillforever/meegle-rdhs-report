#!/usr/bin/env python3
"""Merge discovered configuration names/defaults into a values env map."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


SKIP_KINDS = {"build", "shell", "config", "dev-only", "docker-arg"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--values", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument(
        "--include-secret-values",
        action="store_true",
        help="copy discovered secret values into this explicitly selected production values file",
    )
    args = parser.parse_args()
    values_path = Path(args.values)
    text = values_path.read_text(encoding="utf-8")
    inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    existing = set(re.findall(r"^\s{2}([A-Z][A-Z0-9_]*)\s*:", text, re.M))
    additions: list[str] = []
    skipped_secrets: list[str] = []
    copied_secrets: list[str] = []
    unresolved: list[str] = []
    for item in inventory.get("variables", []):
        name = item["name"]
        if name in existing or item.get("kind") in SKIP_KINDS:
            continue
        if item.get("kind") == "secret":
            if not args.include_secret_values:
                skipped_secrets.append(name)
                continue
            if item.get("default") in (None, "", "<redacted>"):
                value = ""
                unresolved.append(name)
                skipped_secrets.append(name)
            else:
                value = item["default"]
                copied_secrets.append(name)
        else:
            value = item.get("default")
        if value in (None, "", "<redacted>"):
            value = ""
            if name not in unresolved:
                unresolved.append(name)
        additions.append(f'  {name}: {json.dumps(str(value), ensure_ascii=False)}')
    if additions:
        marker = "env:\n"
        if marker not in text:
            raise SystemExit(f"values file has no env map: {values_path}")
        text = text.replace(marker, marker + "\n".join(additions) + "\n", 1)
        values_path.write_text(text, encoding="utf-8")
    print(json.dumps({
        "values": str(values_path),
        "added": [line.strip().split(":", 1)[0] for line in additions],
        "unresolved": unresolved,
        "secrets_copied": copied_secrets,
        "secrets_not_copied": skipped_secrets,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

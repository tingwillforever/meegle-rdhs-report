#!/usr/bin/env python3
"""Inventory runtime configuration with an explicit production-secret mode.

The default scanner records names and sources, not credentials. The
``--include-secret-values`` mode is reserved for the confirmed modification
phase that materializes production values. Dynamic variable construction is
reported with inferred confidence so it cannot be mistaken for a complete
static inventory.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


EXCLUDED_PARTS = {
    ".git", ".agents", ".codex", ".superpowers", "node_modules", "dist", "build",
    ".next", ".venv", "__pycache__", "output", "coverage", ".cache", "vendor",
    ".turbo", ".pytest_cache", "charts",
}
SYSTEM_NAMES = {
    "PATH", "HOME", "PWD", "OLDPWD", "SHLVL", "SHELL", "USER", "LOGNAME",
    "HOSTNAME", "TERM", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "CI",
}
SECRET_PARTS = ("PASSWORD", "PASSWD", "TOKEN", "SECRET", "PRIVATE_KEY", "API_KEY", "CREDENTIAL")
KIND_PRIORITY = {
    "secret": 100,
    "manifest": 90,
    "node": 80,
    "python": 80,
    "go": 80,
    "env-file": 75,
    "docker-env": 60,
    "docker-arg": 20,
    "build": 10,
    "config": 10,
    "dev-only": 5,
}
NAME = r"[A-Z][A-Z0-9_]{2,}"


def is_secret(name: str) -> bool:
    upper = name.upper()
    return any(part in upper for part in SECRET_PARTS)


def is_system(name: str) -> bool:
    return name in SYSTEM_NAMES or name.startswith(("KUBERNETES_", "K8S_"))


def redact(name: str, value: str | None, include_secret_values: bool = False) -> str | None:
    if value is None:
        return None
    return value if include_secret_values or not is_secret(name) else "<redacted>"


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts):
            continue
        if path.stat().st_size > 2_000_000:
            continue
        try:
            if b"\x00" in path.read_bytes()[:4096]:
                continue
        except OSError:
            continue
        yield path


def add(found: dict[str, dict[str, Any]], name: str, path: Path, line_no: int,
        kind: str, default: str | None = None, confidence: str = "confirmed",
        include_secret_values: bool = False):
    if is_system(name):
        return
    entry = found.setdefault(name, {
        "name": name,
        "sources": [],
        "kind": "secret" if is_secret(name) else kind,
        "default": None,
        "confidence": confidence,
        "values_path": f"env.{name}",
    })
    if KIND_PRIORITY.get(kind, 0) > KIND_PRIORITY.get(entry["kind"], 0):
        entry["kind"] = "secret" if is_secret(name) else kind
    if confidence == "confirmed":
        entry["confidence"] = "confirmed"
    source = {"file": str(path), "line": line_no, "kind": kind}
    if source not in entry["sources"]:
        entry["sources"].append(source)
    if default is not None and (
        entry["default"] is None or (include_secret_values and entry["default"] == "<redacted>")
    ):
        entry["default"] = redact(name, default, include_secret_values)


def scan_file(path: Path, root: Path, found: dict[str, dict[str, Any]], include_secret_values: bool = False):
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return
    relative = path.relative_to(root)
    name_text = path.name.lower()
    dev_only = any(token in str(relative).lower() for token in ("vite.config", "wrangler", ".dev.", "test", "playwright"))
    for line_no, line in enumerate(lines, 1):
        stripped = line.strip()

        if path.name.startswith("Dockerfile"):
            match = re.match(r"(?:ENV|ARG)\s+([A-Z][A-Z0-9_]*)(?:=(.*))?$", stripped)
            if match:
                kind = "docker-arg" if stripped.startswith("ARG ") else "docker-env"
                default = match.group(2)
                if default is not None:
                    default = default.rstrip().rstrip("\\").rstrip()
                add(found, match.group(1), relative, line_no, kind, default, include_secret_values=include_secret_values)

        if path.name.startswith(".env") or name_text.endswith(".env") or ".env." in name_text:
            match = re.match(r"(?:export\s+)?(" + NAME + r")\s*=\s*(.*)$", stripped)
            if match and not stripped.startswith("#"):
                value = match.group(2).strip().strip("'\"")
                add(found, match.group(1), relative, line_no, "env-file", value, include_secret_values=include_secret_values)

        for pattern, kind, group, default_group in [
            (r"process\.env\.([A-Z][A-Z0-9_]*)", "node", 1, None),
            (r"process\.env\[['\"](" + NAME + r")[\"']\]", "node", 1, None),
            (r"process\.env\.([A-Z][A-Z0-9_]*)\s*(?:\|\||\?\?)\s*[\"']([^\"']*)[\"']", "node", 1, 2),
            (r"(?:os\.getenv|os\.environ\.get)\(\s*['\"](" + NAME + r")[\"']\s*(?:,\s*['\"]([^'\"]*)['\"])?", "python", 1, 2),
            (r"os\.environ\[['\"](" + NAME + r")[\"']\]", "python", 1, None),
            (r"os\.Getenv\(\s*['\"](" + NAME + r")[\"']", "go", 1, None),
        ]:
            for match in re.finditer(pattern, line):
                default = match.group(default_group) if default_group else None
                add(
                    found,
                    match.group(group),
                    relative,
                    line_no,
                    "dev-only" if dev_only else kind,
                    default,
                    include_secret_values=include_secret_values,
                )

        # Kubernetes/Compose environment blocks and shell assignments.
        for match in re.finditer(r"(?:^|[-\s])name:\s*([A-Z][A-Z0-9_]*)\b", line):
            add(found, match.group(1), relative, line_no, "manifest", include_secret_values=include_secret_values)
        for match in re.finditer(r"(?:^|\s)([A-Z][A-Z0-9_]*)\s*[:=]\s*[^=]", line):
            if path.suffix in {".yaml", ".yml", ".toml"}:
                add(found, match.group(1), relative, line_no, "config", include_secret_values=include_secret_values)
        if path.suffix in {".sh", ".bash"} or path.name.startswith("Dockerfile"):
            for match in re.finditer(r"\$\{(" + NAME + r")(?:[:-][^}]*)?\}|\$(" + NAME + r")", line):
                variable = match.group(1) or match.group(2)
                add(
                    found,
                    variable,
                    relative,
                    line_no,
                    "build",
                    confidence="inferred",
                    include_secret_values=include_secret_values,
                )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project_root", nargs="?", default=".")
    parser.add_argument("--output", help="write JSON to this path instead of stdout")
    parser.add_argument(
        "--include-secret-values",
        action="store_true",
        help="include discovered secret values for explicit production-values generation",
    )
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    found: dict[str, dict[str, Any]] = {}
    for path in iter_files(root):
        scan_file(path, root, found, args.include_secret_values)
    variables = []
    for name in sorted(found):
        item = found[name]
        item["sources"].sort(key=lambda source: (source["file"], source["line"]))
        item["status"] = "discovered"
        variables.append(item)
    payload = {"project_root": str(root), "variables": variables}
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

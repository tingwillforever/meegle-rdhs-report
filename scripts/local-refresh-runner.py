#!/usr/bin/env python3
"""Local webhook runner for the RDHS current-month refresh button."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from typing import Any
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = SITE_ROOT / "runtime" / "local-refresh-runs"
DEFAULT_PORT = 8765


def _current_month_key() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m")


def _today_key() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _select_python() -> str:
    configured = os.environ.get("RDHS_PYTHON_BIN", "")
    candidates = [
        configured,
        str(Path.home() / ".local" / "bin" / "python3.13"),
        str(Path.home() / ".local" / "bin" / "python3.12"),
        str(Path.home() / ".local" / "bin" / "python3.11"),
        "python3.13",
        "python3.12",
        "python3.11",
        "python3",
    ]
    for candidate in [item for item in candidates if item]:
        resolved = candidate if Path(candidate).exists() else shutil.which(candidate)
        if not resolved:
            continue
        completed = subprocess.run(
            [
                resolved,
                "-c",
                "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode == 0:
            return resolved
    raise RuntimeError("Python 3.10 or newer is required for RDHS synchronization")


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class RefreshRunner:
    def __init__(self, *, output_root: Path, timeout: int) -> None:
        self.output_root = output_root
        self.timeout = timeout
        self.lock = threading.Lock()

    def run(self, period_key: str) -> dict[str, Any]:
        if period_key != _current_month_key():
            raise ValueError("历史月份使用月初固化快照，不支持实时刷新")
        site_url = os.environ.get("RDHS_SITE_URL", "http://localhost:3000")
        ingest_token = os.environ.get("RDHS_INGEST_TOKEN", "")
        if not ingest_token:
            raise RuntimeError("RDHS_INGEST_TOKEN is required for local refresh")

        command = [
            _select_python(),
            str(SITE_ROOT / "scripts" / "sync-rdhs-snapshot.py"),
            "--current-month-cache",
            "--as-of",
            _today_key(),
            "--output-root",
            str(self.output_root),
        ]
        environment = dict(os.environ)
        environment["RDHS_SITE_URL"] = site_url
        environment["RDHS_INGEST_TOKEN"] = ingest_token
        environment["PATH"] = f"{Path.home() / '.local' / 'bin'}:{environment.get('PATH', '')}"
        completed = subprocess.run(
            command,
            cwd=SITE_ROOT,
            env=environment,
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(detail or "RDHS current-month refresh failed")

        result: dict[str, Any] = {}
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if lines:
            try:
                parsed = json.loads(lines[-1])
                if isinstance(parsed, dict):
                    result = parsed
            except json.JSONDecodeError:
                result = {"stdout": lines[-1]}
        return {
            "status": "updated",
            "message": "已更新当月缓存",
            "periodKey": period_key,
            **result,
        }


def _handler_factory(runner: RefreshRunner, runner_token: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path != "/health":
                _json_response(self, 404, {"error": "not found"})
                return
            _json_response(self, 200, {"status": "ok"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/rdhs/refresh":
                _json_response(self, 404, {"error": "not found"})
                return
            if runner_token and self.headers.get("Authorization") != f"Bearer {runner_token}":
                _json_response(self, 401, {"error": "unauthorized"})
                return

            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                if not isinstance(payload, dict):
                    raise ValueError("request body must be a JSON object")
                period_key = str(payload.get("periodKey") or _current_month_key())
                if not runner.lock.acquire(blocking=False):
                    _json_response(self, 409, {"error": "已有刷新任务正在执行"})
                    return
                try:
                    result = runner.run(period_key)
                finally:
                    runner.lock.release()
                _json_response(self, 200, result)
            except Exception as error:  # noqa: BLE001
                _json_response(self, 500, {"error": str(error)})

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    return Handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local RDHS refresh webhook")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--env-file", type=Path, default=SITE_ROOT / ".dev.vars")
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--timeout", type=int, default=600)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    _load_env_file(args.env_file)
    runner = RefreshRunner(output_root=args.output_root, timeout=args.timeout)
    handler = _handler_factory(runner, os.environ.get("RDHS_REFRESH_WEBHOOK_TOKEN", ""))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"RDHS local refresh runner listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

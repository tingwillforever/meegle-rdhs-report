"""周期性产研过程效能报告入口。"""

from __future__ import annotations

import argparse
from datetime import date
from datetime import datetime
import json
from pathlib import Path
from typing import Sequence

import yaml

from impl.periodic_report_runtime import run_periodic_report


TOPIC_ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = TOPIC_ROOT / "config" / "periodic_report.yaml"


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("日期必须使用 YYYY-MM-DD 格式") from exc


def _load_json_file(path: Path | None) -> dict[str, object] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"快照文件不是 JSON 对象：{path}")
    return payload


def _load_config(path: Path) -> dict[str, object]:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    report_config = config.get("periodic_report") if isinstance(config, dict) else None
    if not isinstance(report_config, dict):
        raise ValueError(f"配置缺少 periodic_report：{path}")
    for key in ("project_key", "current_chart_id", "previous_chart_id"):
        if not isinstance(report_config.get(key), str) or not report_config[key]:
            raise ValueError(f"配置缺少 {key}：{path}")
    return report_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="生成并发布周期性产研过程效能报告")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--mode",
        choices=("weekly", "monthly-baseline", "trial"),
        default="weekly",
    )
    parser.add_argument("--as-of", type=_parse_date, default=date.today())
    parser.add_argument("--current-raw", type=Path)
    parser.add_argument("--previous-raw", type=Path)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--no-publish", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _load_config(args.config)
    configured_output_root = Path(str(config.get("output_root", "reports/periodic")))
    output_root = args.output_root or (
        configured_output_root
        if configured_output_root.is_absolute()
        else TOPIC_ROOT / configured_output_root
    )
    result = run_periodic_report(
        mode=args.mode,
        as_of=args.as_of,
        output_root=output_root,
        project_key=str(config["project_key"]),
        current_chart_id=str(config["current_chart_id"]),
        previous_chart_id=str(config["previous_chart_id"]),
        current_payload=_load_json_file(args.current_raw),
        previous_payload=_load_json_file(args.previous_raw),
        publish=not args.no_publish,
    )
    print(
        json.dumps(
            {
                "run_dir": str(result.run_dir),
                "report_data_path": str(result.report_data_path),
                "audit_manifest_path": str(result.audit_manifest_path),
                "publication_url": result.publication_url,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

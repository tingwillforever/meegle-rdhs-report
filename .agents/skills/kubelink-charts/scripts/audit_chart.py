#!/usr/bin/env python3
"""Read-only Helm/values/config closure audit used by kubelink-charts."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


OPTIONAL_ROOTS = {
    "secrets", "podAnnotations", "podLabels", "pdb", "networkPolicy", "autoscaling",
    "nameOverride", "fullnameOverride", "imagePullSecrets",
}
BUILD_NAMES = {"PROJECT_VERSION", "BUILD_ID", "SERVICE_NAME", "ENV", "VERSION", "CHART_SOURCE_NAME"}
NON_RUNTIME_KINDS = {"build", "shell", "config", "docker-arg", "dev-only"}


def template_image_prefix() -> str | None:
    template_values = Path(__file__).resolve().parent.parent / "assets" / "meegle-mcp-chart-template" / "values.yaml"
    in_image = False
    for line in read(template_values).splitlines():
        if re.match(r"^image:\s*$", line):
            in_image = True
            continue
        if in_image and re.match(r"^[^\s]", line):
            break
        if in_image:
            match = re.match(r"^\s+repository:\s*[\"']?([^\"'#\s]+)", line)
            if match and "/" in match.group(1):
                return match.group(1).rsplit("/", 1)[0] + "/"
    return None


def run(command: list[str], cwd: Path) -> tuple[int, str, str]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def top_level_keys(text: str) -> set[str]:
    return {match.group(1) for match in re.finditer(r"^([A-Za-z][A-Za-z0-9_-]*):(?:\s|$)", text, re.M)}


def has_named_value(text: str, name: str) -> bool:
    return bool(re.search(rf"^\s+{re.escape(name)}:\s*", text, re.M)) or bool(
        re.search(rf"^\s*-?\s*name:\s*{re.escape(name)}\s*$", text, re.M)
    )


def template_roots(template_text: str) -> set[str]:
    return {match.group(1).split(".")[0] for match in re.finditer(r"\.Values\.([A-Za-z0-9_.-]+)", template_text)}


def template_has_root_default(template_text: str, root: str) -> bool:
    for match in re.finditer(rf"\.Values\.{re.escape(root)}", template_text):
        nearby = template_text[max(0, match.start() - 100): match.end() + 120]
        if "default" in nearby or "required" in nearby or "with .Values." + root in nearby:
            return True
    return False


def add(findings: list[dict[str, Any]], code: str, severity: str, message: str, path: str | None = None):
    item = {"code": code, "severity": severity, "message": message}
    if path:
        item["path"] = path
    findings.append(item)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--chart", required=True)
    parser.add_argument("--values")
    parser.add_argument("--env", default="prod")
    parser.add_argument("--kube-version")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--output", default=".kubelinks-chart-report.json")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    chart = (project_root / args.chart).resolve() if not Path(args.chart).is_absolute() else Path(args.chart).resolve()
    values = None
    if args.values:
        values = (project_root / args.values).resolve() if not Path(args.values).is_absolute() else Path(args.values).resolve()
    elif (chart / f"values-{args.env}.yaml").exists():
        values = chart / f"values-{args.env}.yaml"
    default_values = chart / "values.yaml"
    findings: list[dict[str, Any]] = []

    if not chart.is_dir():
        add(findings, "CHART_MISSING", "error", f"Chart directory does not exist: {chart}")
    if not default_values.exists():
        add(findings, "VALUES_MISSING", "error", f"values.yaml does not exist: {default_values}")
    chart_yaml = chart / "Chart.yaml"
    chart_text = read(chart_yaml)
    for field in ("apiVersion", "name", "version", "appVersion"):
        if not re.search(rf"^{field}:\s*\S+", chart_text, re.M):
            add(findings, "CHART_METADATA_MISSING", "error", f"Chart.yaml missing {field}", str(chart_yaml))
    if chart_text and not re.search(r"^apiVersion:\s*v2\s*$", chart_text, re.M):
        add(findings, "CHART_API_VERSION", "error", "Chart.yaml must use apiVersion v2", str(chart_yaml))

    values_text = read(values or default_values)
    default_text = read(default_values)
    all_template_text = "\n".join(read(path) for path in chart.glob("templates/*") if path.is_file())
    roots = template_roots(all_template_text)
    default_roots = top_level_keys(default_text)
    selected_roots = top_level_keys(values_text)
    for root in sorted(roots - default_roots):
        severity = "warning" if root in OPTIONAL_ROOTS or template_has_root_default(all_template_text, root) else "error"
        add(findings, "MISSING_IN_VALUES", severity, f"Template references .Values.{root}, but values.yaml does not define it", str(default_values))
    for root in sorted((default_roots - roots) - {"nameOverride", "fullnameOverride"}):
        add(findings, "UNUSED_VALUE", "warning", f"values.yaml key {root} is not referenced by a template", str(default_values))
    if values and values != default_values:
        for root in sorted((roots & default_roots) - selected_roots):
            severity = "warning" if root in OPTIONAL_ROOTS or template_has_root_default(all_template_text, root) else "error"
            add(findings, "MISSING_IN_PRODUCTION", severity, f"Production values omit required top-level key {root}", str(values))

    inventory_script = Path(__file__).with_name("inventory-config.py")
    with tempfile.NamedTemporaryFile(prefix="kubelink-inventory-", suffix=".json") as handle:
        inventory_result = subprocess.run([sys.executable, str(inventory_script), str(project_root), "--output", handle.name], text=True, capture_output=True, check=False)
        if inventory_result.returncode != 0:
            add(findings, "CONFIG_INVENTORY_FAILED", "error", inventory_result.stderr.strip() or "configuration inventory failed")
            inventory: dict[str, Any] = {"variables": []}
        else:
            inventory = json.loads(Path(handle.name).read_text(encoding="utf-8"))
    for item in inventory.get("variables", []):
        name = item["name"]
        if name in BUILD_NAMES or item.get("kind") in NON_RUNTIME_KINDS or item.get("kind") == "system":
            continue
        has_safe_default = item.get("default") not in (None, "", "<redacted>")
        if not has_named_value(default_text, name) and not has_named_value(all_template_text, name):
            severity = "error" if args.strict and not has_safe_default and item.get("kind") in {"node", "python", "go", "manifest", "env-file"} else "warning"
            add(findings, "MISSING_IN_VALUES", severity, f"Local configuration {name} has no values entry", "; ".join(source["file"] for source in item.get("sources", [])))
        if values and values != default_values and not has_named_value(values_text, name) and not has_named_value(all_template_text, name):
            managed_by_chart = has_named_value(default_text, name)
            severity = "error" if args.strict and managed_by_chart and item.get("kind") in {"node", "python", "go", "manifest", "env-file"} else "warning"
            add(findings, "MISSING_IN_PRODUCTION", severity, f"Production values/workload omit local configuration {name}", "; ".join(source["file"] for source in item.get("sources", [])))

    image_match = re.search(r"^\s*repository:\s*([^#\s]+)", values_text, re.M)
    tag_match = re.search(r"^\s*tag:\s*[\"']?([^\"'\s#]+)", values_text, re.M)
    canonical_image_prefix = template_image_prefix()
    if not canonical_image_prefix:
        add(findings, "CANONICAL_IMAGE_PREFIX_MISSING", "error", "canonical template image.repository is missing or invalid")
    if not image_match or not image_match.group(1):
        add(findings, "IMAGE_REPOSITORY_MISSING", "error", "image.repository is empty")
    elif "example.invalid" in image_match.group(1) or "registry.example" in image_match.group(1):
        add(findings, "IMAGE_REPOSITORY_PLACEHOLDER", "warning", f"image.repository is a template placeholder: {image_match.group(1)}")
    if canonical_image_prefix and image_match and image_match.group(1) and not image_match.group(1).startswith(canonical_image_prefix):
        severity = "error" if args.strict else "warning"
        add(
            findings,
            "IMAGE_REPOSITORY_PREFIX_MISMATCH",
            severity,
            f"image.repository must use canonical prefix {canonical_image_prefix}: {image_match.group(1)}",
        )
    if not tag_match or not tag_match.group(1):
        add(findings, "IMAGE_TAG_MISSING", "error", "image.tag is empty")
    elif tag_match.group(1) == "latest":
        add(findings, "MUTABLE_IMAGE_TAG", "error", "production image must not use latest")

    if "imagePullSecrets" not in values_text:
        add(findings, "IMAGE_PULL_SECRET_MISSING", "warning", "imagePullSecrets is not configured")
    if "livenessProbe:" not in all_template_text or "readinessProbe:" not in all_template_text:
        add(findings, "PROBE_MISSING", "warning", "livenessProbe/readinessProbe are not both present")
    if "resources:" not in all_template_text:
        add(findings, "RESOURCES_MISSING", "warning", "resources are not rendered")
    if "securityContext:" not in all_template_text:
        add(findings, "SECURITY_CONTEXT_MISSING", "warning", "securityContext is not rendered")
    if re.search(r"(PASSWORD|TOKEN|SECRET|PRIVATE_KEY)\s*:\s*[\"']?[A-Za-z0-9+/=_-]{8,}", values_text, re.I):
        add(findings, "PLAINTEXT_SECRET", "warning", "values file appears to contain a plaintext credential")

    build_scripts = list(project_root.glob("charts/build-chart*.sh"))
    if not build_scripts:
        build_scripts = list(chart.parent.glob("build-chart*.sh"))
    if build_scripts:
        build_text = read(build_scripts[0])
        code, _, stderr = run(["bash", "-n", str(build_scripts[0])], project_root)
        if code != 0:
            add(findings, "BUILD_SYNTAX_FAILED", "error", stderr.strip() or "bash -n failed", str(build_scripts[0]))
        if "helm lint" not in build_text:
            add(findings, "BUILD_LINT_MISSING", "error", "build script does not run helm lint", str(build_scripts[0]))
        if "helm push-artifactory" not in build_text:
            add(findings, "BUILD_PUSH_MISSING", "warning", "build script does not use helm push-artifactory", str(build_scripts[0]))
        if "push failed" not in build_text.lower() and "exit 1" not in build_text:
            add(findings, "BUILD_PUSH_STATUS_UNKNOWN", "error", "build script does not clearly fail when chart push fails", str(build_scripts[0]))
    else:
        add(findings, "BUILD_SCRIPT_MISSING", "warning", "no charts/build-chart*.sh found")

    if chart.is_dir() and default_values.exists():
        code, _, stderr = run(["helm", "lint", str(chart), "-f", str(values)] if values else ["helm", "lint", str(chart)], project_root)
        if code != 0:
            add(findings, "HELM_LINT_FAILED", "error", stderr.strip() or "helm lint failed")
        render_command = ["helm", "template", "kubelink-audit", str(chart)]
        if values:
            render_command += ["-f", str(values)]
        code, _, stderr = run(render_command, project_root)
        if code != 0:
            add(findings, "HELM_RENDER_FAILED", "error", stderr.strip() or "helm template failed")
        versions = [args.kube_version] if args.kube_version else []
        if "1.15.12" not in versions:
            versions.append("1.15.12")
        for version in versions:
            command = ["helm", "template", "kubelink-compat", str(chart), "--kube-version", version]
            if values:
                command += ["-f", str(values)]
            code, _, stderr = run(command, project_root)
            if code != 0:
                add(findings, "KUBE_RENDER_FAILED", "error", f"Kubernetes {version}: {stderr.strip() or 'helm template failed'}")

    errors = [item for item in findings if item["severity"] == "error"]
    warnings = [item for item in findings if item["severity"] == "warning"]
    if errors:
        status = "blocked"
    elif values and not any(item["code"] in {"MISSING_IN_VALUES", "MISSING_IN_PRODUCTION", "UNRESOLVED_VALUE"} and item["severity"] == "warning" for item in findings):
        status = "deployment-ready"
    else:
        status = "renderable"
    payload = {
        "status": status,
        "project_root": str(project_root),
        "chart": str(chart),
        "values": str(values) if values else None,
        "errors": errors,
        "warnings": warnings,
        "findings": findings,
    }
    output = Path(args.output)
    if not output.is_absolute():
        output = project_root / output
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"kubelink-charts status: {status}")
    print(f"errors: {len(errors)}, warnings: {len(warnings)}")
    for item in findings:
        print(f"[{item['severity']}] {item['code']}: {item['message']}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

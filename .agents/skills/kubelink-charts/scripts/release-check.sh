#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_root="."
chart=""
values=""
env_name="prod"
kube_version=""
push=false

while (($#)); do
  case "$1" in
    --project-root) project_root=$2; shift 2 ;;
    --chart) chart=$2; shift 2 ;;
    --values) values=$2; shift 2 ;;
    --env) env_name=$2; shift 2 ;;
    --kube-version) kube_version=$2; shift 2 ;;
    --push) push=true; shift ;;
    -h|--help)
      echo "Usage: release-check.sh --chart DIR [--values FILE] [--env NAME] [--kube-version VERSION] [--push]"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done
[[ -n "${chart}" ]] || { echo "error: --chart is required" >&2; exit 2; }

audit_args=(--project-root "${project_root}" --chart "${chart}" --env "${env_name}" --strict)
[[ -n "${values}" ]] && audit_args+=(--values "${values}")
[[ -n "${kube_version}" ]] && audit_args+=(--kube-version "${kube_version}")
"${SCRIPT_DIR}/audit-chart.sh" "${audit_args[@]}"

if [[ "${push}" == true ]]; then
  if [[ "${chart}" = /* ]]; then
    chart_dir="${chart}"
  else
    chart_dir="${project_root}/${chart}"
  fi
  build_script="$(cd "${chart_dir}/.." && pwd)/build-chart.sh"
  if [[ ! -x "${build_script}" ]]; then
    echo "error: executable build-chart.sh not found beside chart" >&2
    exit 1
  fi
  : "${PROJECT_VERSION:?PROJECT_VERSION is required for --push}"
  : "${BUILD_ID:?BUILD_ID is required for --push}"
  SERVICE_NAME="${SERVICE_NAME:-$(basename "${chart_dir}")}" \
    CHART_SOURCE_NAME="${CHART_SOURCE_NAME:-$(basename "${chart_dir}")}" \
    ENV="${env_name}" "${build_script}"
fi

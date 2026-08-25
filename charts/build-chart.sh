#!/bin/bash
set -e

# Build and publish the RDHS Helm chart using the meegle-mcp release flow.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "${SCRIPT_DIR}"

OS_NAME=$(uname)
SERVICE_NAME="${SERVICE_NAME:-meegle-rdhs-report}"
CHART_SOURCE_NAME="${CHART_SOURCE_NAME:-rdhs-report}"

if [[ -z "${PROJECT_VERSION:-}" ]]; then
    echo "❌ 错误: PROJECT_VERSION 环境变量未设置"
    exit 1
fi

if [[ -z "${BUILD_ID:-}" ]]; then
    echo "❌ 错误: BUILD_ID 环境变量未设置"
    exit 1
fi

if [[ ! -d "./${CHART_SOURCE_NAME}" ]]; then
    echo "❌ 错误: Chart 目录 ./${CHART_SOURCE_NAME} 不存在"
    echo "💡 当前工作目录: $(pwd)"
    exit 1
fi

VERSION=${PROJECT_VERSION}.${BUILD_ID}
ENV="${ENV:-prod}"

echo "=========================================="
echo "📋 构建环境变量信息"
echo "=========================================="
echo "  PROJECT_VERSION: ${PROJECT_VERSION}"
echo "  BUILD_ID: ${BUILD_ID}"
echo "  SERVICE_NAME: ${SERVICE_NAME}"
echo "  ENV: ${ENV}"
echo "  VERSION: ${VERSION}"
echo "  操作系统: ${OS_NAME}"
echo "  工作目录: $(pwd)"
echo "=========================================="

ENV_VALUES_FILE="./${CHART_SOURCE_NAME}/values-${ENV}.yaml"
if [[ ! -f "${ENV_VALUES_FILE}" ]]; then
    echo "⚠️  警告: 环境配置文件 ${ENV_VALUES_FILE} 不存在"
    echo "💡 将使用默认 values.yaml"
    ENV_VALUES_FILE=""
else
    echo "  ✓ 发现环境配置文件: values-${ENV}.yaml"
fi

BUILD_DIR="${SERVICE_NAME}-${ENV}"
rm -rf "${BUILD_DIR}"
cp -rf "${CHART_SOURCE_NAME}" "${BUILD_DIR}"

echo "  ✓ 已创建构建目录: ${BUILD_DIR}"

if [[ $OS_NAME != "Darwin" ]]; then
    sed -i "s/^name: ${CHART_SOURCE_NAME}$/name: ${SERVICE_NAME}-${ENV}/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "s/^version: .*/version: ${VERSION}/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "s/^appVersion: .*/appVersion: \"${VERSION}\"/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "s/^\([[:space:]]*tag:\).*/\1 \"${VERSION}\"/g" "./${BUILD_DIR}/values.yaml"
    if [[ -n "${ENV_VALUES_FILE}" ]]; then
        sed -i "s/^\([[:space:]]*tag:\).*/\1 \"${VERSION}\"/g" "./${BUILD_DIR}/values-${ENV}.yaml"
    fi
else
    sed -i "" "s/^name: ${CHART_SOURCE_NAME}$/name: ${SERVICE_NAME}-${ENV}/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "" "s/^version: .*/version: ${VERSION}/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "" "s/^appVersion: .*/appVersion: \"${VERSION}\"/g" "./${BUILD_DIR}/Chart.yaml"
    sed -i "" "s/^\([[:space:]]*tag:\).*/\1 \"${VERSION}\"/g" "./${BUILD_DIR}/values.yaml"
    if [[ -n "${ENV_VALUES_FILE}" ]]; then
        sed -i "" "s/^\([[:space:]]*tag:\).*/\1 \"${VERSION}\"/g" "./${BUILD_DIR}/values-${ENV}.yaml"
    fi
fi

if [[ -n "${ENV_VALUES_FILE}" && "${ENV}" == "prod" ]]; then
    echo "  🔧 应用生产环境配置到 values.yaml..."
    cp "./${BUILD_DIR}/values-${ENV}.yaml" "./${BUILD_DIR}/values.yaml"
    echo "  ✓ 已使用 values-${ENV}.yaml 覆盖 values.yaml"
fi

echo "  🔍 验证 Chart..."
helm lint "${BUILD_DIR}" || {
    echo "  ❌ Chart 验证失败"
    exit 1
}

echo "  📤 推送 chart 到内网仓库..."
PUSH_SUCCESS=false
if helm push-artifactory "${BUILD_DIR}" cbg-helm-local --skip-reindex; then
    PUSH_SUCCESS=true
    echo "  ✓ Chart 已成功推送到仓库"
else
    echo "  ⚠️  推送失败，但构建目录已创建: ${BUILD_DIR}"
    echo "  💡 可以手动执行: helm push-artifactory ${BUILD_DIR} cbg-helm-local"
fi

echo ""
if [[ "${PUSH_SUCCESS}" == "true" ]]; then
    echo "✅ Chart 构建并推送完成！"
else
    echo "✅ Chart 构建完成（推送失败）"
fi
echo "  📦 Chart 名称: ${SERVICE_NAME}-${ENV}"
echo "  📌 Chart 版本: ${VERSION}"

if [[ "${PUSH_SUCCESS}" == "false" ]]; then
    exit 1
fi

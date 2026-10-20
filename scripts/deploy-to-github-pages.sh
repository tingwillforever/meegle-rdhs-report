#!/usr/bin/env bash
set -euo pipefail

site_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "==> 1. 正在构建纯静态站点 (base path: /cbg-rdhs-reports)..."
cd "$site_root"
RDHS_BASE_PATH="/cbg-rdhs-reports" npm run build:pages

echo "==> 2. 同步产物至 GitHub Pages 仓库 (tingwillforever/cbg-rdhs-reports)..."
tmp_repo="/tmp/cbg-rdhs-reports"
rm -rf "$tmp_repo"
git clone https://github.com/tingwillforever/cbg-rdhs-reports.git "$tmp_repo"

cp -R "$site_root/dist/static/"* "$tmp_repo/"
cd "$tmp_repo"
touch .nojekyll

if [[ -n "$(git status -s)" ]]; then
  echo "==> 3. 正在提交并推送到 GitHub Pages main 分支..."
  git add -A
  git -c core.hooksPath=/dev/null commit -m "feat: update unified Bento dashboard & streamlined workbench $(date +%Y-%m-%d)"
  git push origin main
  echo "==> 🎉 部署成功！在线访问地址: https://tingwillforever.github.io/cbg-rdhs-reports/"
else
  echo "==> 没有检测到变更，GitHub Pages 已是最新版本。"
fi

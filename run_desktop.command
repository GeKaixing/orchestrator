#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

printf '%s\n' '============================================'
printf '%s\n' ' 达人招商编排客户端 - macOS 启动器'
printf '%s\n' '============================================'

printf '%s\n' '[1/3] 检查 Python 依赖 (uv sync) ...'
if ! command -v uv >/dev/null 2>&1; then
  printf '%s\n' '[错误] 未找到 uv, 请先安装: https://docs.astral.sh/uv/'
  exit 1
fi
uv sync

printf '%s\n' '[2/3] 检查前端依赖 ...'
if [ ! -d desktop/node_modules ]; then
  printf '%s\n' '  首次安装前端依赖 (需数分钟) ...'
  (
    cd desktop
    npm install
    node node_modules/electron/install.js
  )
fi

printf '%s\n' '[3/3] 启动客户端 ...'
(
  cd desktop
  npm run dev
)

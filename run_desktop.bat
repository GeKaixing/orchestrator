@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  达人招商编排客户端 - 启动器
echo ============================================

echo [1/3] 检查 Python 依赖 (uv sync) ...
where uv >nul 2>&1 || (
  echo [错误] 未找到 uv, 请先安装: https://docs.astral.sh/uv/
  pause & exit /b 1
)
uv sync
if errorlevel 1 (
  echo [错误] uv sync 失败, 请检查网络.
  pause & exit /b 1
)

echo [2/3] 检查前端依赖 ...
if not exist desktop\node_modules (
  echo   首次安装前端依赖 (需数分钟) ...
  pushd desktop
  call npm install
  if errorlevel 1 ( echo [错误] npm install 失败 & pause & exit /b 1 )
  call node node_modules\electron\install.js
  popd
)

echo [3/3] 启动客户端 ...
pushd desktop
call npm run dev
popd

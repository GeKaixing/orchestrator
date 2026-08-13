#!/usr/bin/env python3
"""打包四个项目为可分发包 (源码包 + 一键初始化脚本).

把 orchestrator / wxshop-cli / wechat-friend-add 三个 Python 项目 + rag (LangGraph Server,
Docker 栈, 可选组件) 的「已跟踪文件当前工作区内容」拷进同一个目录, 并生成 setup.bat /
setup-rag.bat / start-all.bat / README.txt, 供拷到别的机器一键初始化运行.

注意:
  - 不打包 .venv / node_modules / Chromium / Docker 镜像 (不可随机器迁移),
    由目标机的 setup.bat / setup-rag.bat 重建。
  - rag 是可选组件 (AI 自动回复才需要): 用独立的 setup-rag.bat 装, 依赖 Docker Desktop。
  - 登录态 / 密钥默认不打进包; 需要时用 --with-secrets (敏感, 只应发给可信的人)。

用法:
  python tools/build_bundle.py                 # 生成 dist/recruit-bundle/
  python tools/build_bundle.py --zip           # 额外打成 dist/recruit-bundle.zip
  python tools/build_bundle.py --with-secrets  # 顺带打包 wxshop 登录态 + wechat .env
  python tools/build_bundle.py --out OTHER     # 自定义输出目录
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ORCH_DIR = Path(__file__).resolve().parents[1]  # <repo>/tools/build_bundle.py -> repo 根
sys.path.insert(0, str(ORCH_DIR))

from recruit import paths  # noqa: E402  # 复用同级目录解析 (wxshop-cli / wechat-friend-add)

REPOS = [
    ("orchestrator", ORCH_DIR),
    ("wxshop-cli", paths.WXSHOP_DIR),
    ("wechat-friend-add", paths.WECHAT_FRIEND_DIR),
    ("rag", paths.RAG_DIR),
]

DEFAULT_OUT = ORCH_DIR / "dist" / "recruit-bundle"

WARN = "-" * 60


def _rmtree_retry(path: Path, attempts: int = 3) -> None:
    """Windows 下新建文件可能被安全软件短暂占用, rmtree 失败时重试几次."""
    import time

    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(0.5)


def _git_archive(repo: Path, dest: Path) -> None:
    """把仓库「已跟踪文件的当前工作区内容」拷到 dest.

    用 `git ls-files` 逐文件复制 (而非 git archive HEAD), 这样未提交的修改也会进包,
    排除未跟踪文件 (venv/.env/登录态等)。
    """
    proc = subprocess.run(["git", "-C", str(repo), "ls-files", "-z"], capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git ls-files {repo.name} 失败")
    for rel in proc.stdout.decode("utf-8", "replace").split("\0"):
        if not rel:
            continue
        src = repo / rel
        if not src.is_file():
            continue
        dst = dest / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _warn_untracked(repo: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    untracked = [ln[3:] for ln in proc.stdout.splitlines() if ln.startswith("??")]
    if untracked:
        print(f"[提示] {repo.name} 有未跟踪文件 (不会进包):")
        for ln in untracked[:12]:
            print(f"        {ln}")


def _copy_secrets(out: Path) -> None:
    """把 wxshop 登录态 + wechat .env 拷进包内 secrets/ (敏感!)."""
    print(WARN)
    print("!! 正在打包敏感数据:")
    print("!!   - 微信小店登录态 cookies  (~/.wxshop/weixin_store_state.json)")
    print("!!   - 店铺 API 密钥          (~/.wxshop/api_config.json)")
    print("!!   - wechat VISION_API_KEY   (wechat-friend-add/.env)")
    print("!! 只应发给可信的人或自己的机器, 切勿公开分发。")
    print(WARN)
    src_wxshop = Path.home() / ".wxshop"
    dst = out / "secrets" / ".wxshop"
    for name in ("weixin_store_state.json", "api_config.json"):
        s = src_wxshop / name
        if s.exists():
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(s, dst / name)
            print(f"  + secrets/.wxshop/{name}")
        else:
            print(f"  - 缺 ~/.wxshop/{name}, 跳过")
    env_src = paths.WECHAT_FRIEND_DIR / ".env"
    if env_src.exists():
        out.joinpath("secrets").mkdir(parents=True, exist_ok=True)
        shutil.copy2(env_src, out / "secrets" / ".env.wechat")
        print("  + secrets/.env.wechat")
    else:
        print("  - 缺 wechat-friend-add/.env, 跳过 (setup 会由 .env.example 生成)")


def _write(out: Path, name: str, content: str) -> None:
    p = out / name
    p.write_bytes(content.replace("\n", "\r\n").encode("utf-8"))
    print(f"  + {name}")


# ── 生成脚本模板 (写盘时转 CRLF) ─────────────────────────────

SETUP_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ROOT=%CD%"

echo ============================================================
echo   达人招商编排 (recruit-bundle) 一键初始化
echo   本包含三个项目源码, 需要联网拉依赖 (uv / Chromium / 可选 Electron)
echo ============================================================
echo.

rem ---- 1. 定位/安装 uv ----
echo [1/7] 检查 uv ...
set "UV_EXE="
where uv >nul 2>&1 && set "UV_EXE=uv"
if not defined UV_EXE (
  if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
)
if not defined UV_EXE (
  echo   未找到 uv, 正在通过官方脚本安装 ...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV_EXE=%USERPROFILE%\.local\bin\uv.exe"
)
if not defined UV_EXE (
  echo [错误] uv 安装失败, 请手动安装后重试: https://docs.astral.sh/uv/
  pause & exit /b 1
)
echo   uv: %UV_EXE%
echo.

rem ---- 2. orchestrator ----
echo [2/7] orchestrator: uv sync ...
pushd "%ROOT%\orchestrator"
"%UV_EXE%" sync
if errorlevel 1 ( echo [错误] orchestrator uv sync 失败 & pause & exit /b 1 )
popd

rem ---- 3. wxshop-cli ----
echo [3/7] wxshop-cli: uv sync + Chromium (~150MB, 仅首次) ...
pushd "%ROOT%\wxshop-cli"
"%UV_EXE%" sync
if errorlevel 1 ( echo [错误] wxshop uv sync 失败 & pause & exit /b 1 )
"%UV_EXE%" run playwright install chromium
popd

rem ---- 4. wechat-friend-add ----
echo [4/7] wechat-friend-add: uv sync ...
pushd "%ROOT%\wechat-friend-add"
"%UV_EXE%" sync
if errorlevel 1 ( echo [错误] wechat uv sync 失败 & pause & exit /b 1 )
popd

rem ---- 5. 登录态 / 密钥 ----
echo [5/7] 登录态 / 密钥 ...
if exist "%ROOT%\secrets\.wxshop\weixin_store_state.json" (
  if not exist "%USERPROFILE%\.wxshop\" mkdir "%USERPROFILE%\.wxshop"
  copy /y "%ROOT%\secrets\.wxshop\weixin_store_state.json" "%USERPROFILE%\.wxshop\" >nul
  echo   已导入 wxshop 登录态
) else (
  echo   (未随包带 wxshop 登录态, 之后可运行 wxshop login 扫码生成)
)
if exist "%ROOT%\secrets\.env.wechat" (
  copy /y "%ROOT%\secrets\.env.wechat" "%ROOT%\wechat-friend-add\.env" >nul
  echo   已导入 wechat .env
) else (
  if not exist "%ROOT%\wechat-friend-add\.env" (
    if exist "%ROOT%\wechat-friend-add\.env.example" (
      copy /y "%ROOT%\wechat-friend-add\.env.example" "%ROOT%\wechat-friend-add\.env" >nul
      echo   已由 .env.example 生成 .env, 请填入 VISION_API_KEY (发固定文案可不填)
    )
  )
)

rem ---- 6. 校验 ----
echo [6/7] 校验 ...
pushd "%ROOT%\orchestrator"
".venv\Scripts\python.exe" -c "from recruit import paths; print('  orchestrator 路径 OK:', paths.WXSHOP_DIR)" >nul 2>&1 && (echo   orchestrator venv OK) || (echo   [警告] orchestrator venv 异常, 请重跑 setup.bat)
popd
pushd "%ROOT%\wxshop-cli"
".venv\Scripts\python.exe" -m wxshop persist verify >nul 2>&1 && (echo   wxshop 登录态有效) || (echo   wxshop 未登录: cd wxshop-cli 后运行 uv run wxshop login 扫码)
popd
"%ROOT%\wechat-friend-add\.venv\Scripts\cua-driver.exe" --version >nul 2>&1 && (echo   cua-driver OK) || (echo   [警告] cua-driver 校验失败)

rem ---- 7. Electron 前端 (可选) ----
echo [7/7] Electron 前端依赖 (可选, 失败不影响轻量客户端) ...
if exist "%ROOT%\orchestrator\desktop\package.json" (
  if not exist "%ROOT%\orchestrator\desktop\node_modules" (
    pushd "%ROOT%\orchestrator\desktop"
    call npm install
    if errorlevel 1 ( echo   [警告] npm install 失败, 将使用轻量客户端 ) else ( call node node_modules\electron\install.js )
    popd
  ) else (
    echo   已存在 node_modules, 跳过
  )
)

echo.
echo ============================================================
echo   初始化完成!
echo   - 启动完整面板: start-all.bat  (Electron, 自动拉起后端)
echo   - 或轻量客户端:  start-client.bat  (需先手动开 start-backend.bat)
echo   - wxshop 未登录时: 先运行 wxshop login 扫码
echo   - 需要 AI 自动回复: 另跑 setup-rag.bat (可选, 需 Docker Desktop)
echo ============================================================
pause
"""

SETUP_RAG_BAT = r"""@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0rag"

echo ============================================================
echo   RAG 服务一键部署 (可选组件) — LangGraph + Milvus + Redis + MySQL
echo   前置: Docker Desktop 已启动 (否则无法拉镜像/起容器)
echo ============================================================
echo.

rem ---- 1. Docker 检查 ----
echo [1/5] 检查 Docker ...
docker info >nul 2>&1
if errorlevel 1 (
  echo [错误] Docker Desktop 未运行或未安装, 请先启动 Docker Desktop 再重试
  pause & exit /b 1
)
echo   Docker OK
echo.

rem ---- 2. .env ----
echo [2/5] 配置 .env ...
if not exist ".env" (
  if exist ".env.example" copy /y ".env.example" ".env" >nul
)
echo   [重要] 请确认 .env 已填 LLM_API_KEY (否则 LLM 回复全失败)
findstr /b /i "APP_IMAGE=" .env >nul 2>&1
if errorlevel 1 (
  echo   未设 APP_IMAGE, 追加 CI 镜像 ghcr.io/pnj-star/rag:latest
  echo APP_IMAGE=ghcr.io/pnj-star/rag:latest>> .env
)
echo.

rem ---- 3. 知识库 ----
echo [3/5] 准备知识库 (data/milvus_knowledge.json) ...
if not exist "data" mkdir "data"
if not exist "data\milvus_knowledge.json" (
  if exist "backup\mushroom_knowledge_backup.json" (
    copy /y "backup\mushroom_knowledge_backup.json" "data\milvus_knowledge.json" >nul
    echo   已从 backup/ 复制知识库
  ) else (
    echo   [警告] 缺 backup/mushroom_knowledge_backup.json, 之后需手动导入知识库
  )
)
echo.

rem ---- 4. 拉镜像 + 启动 ----
echo [4/5] 拉取镜像并启动 (首次需下载数 GB) ...
docker compose pull app
if errorlevel 1 ( echo [错误] docker compose pull 失败 (网络/镜像名?) & pause & exit /b 1 )
docker compose up -d
if errorlevel 1 ( echo [错误] docker compose up 失败 & pause & exit /b 1 )
echo   等待服务就绪 (约 30s, 可再 docker compose ps 查看) ...
timeout /t 30 /nobreak >nul
docker compose ps
echo.

rem ---- 5. 导入知识库 + 验证 ----
echo [5/5] 导入知识库到 Milvus ...
docker compose run --rm --entrypoint python -v "%CD%\data:/app/data" app scripts/milvus_data.py import -i /app/data/milvus_knowledge.json
if errorlevel 1 ( echo [错误] 知识库导入失败 & pause & exit /b 1 )

echo.
echo ============================================================
echo   RAG 服务部署完成!
echo   - 验证: http://localhost:2024/ok  (应返回 ok)
echo   - 文档: http://localhost:2024/redoc
echo   - 停止: cd rag 后 docker compose down
echo   - 改 LLM_API_KEY 后: cd rag 后 docker compose up -d 重启
echo ============================================================
pause
"""

START_ALL_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%CD%\orchestrator\desktop\node_modules" (
  echo 启动 Electron 面板 (其主进程会自动拉起后端, 等待窗口出现) ...
  cd /d "%CD%\orchestrator\desktop"
  call npm run dev
) else (
  echo Electron 未安装, 使用轻量客户端 (后端窗口会一并打开) ...
  start "recruit-backend" cmd /k "%CD%\start-backend.bat"
  timeout /t 3 /nobreak >nul
  call "%CD%\start-client.bat"
)
"""

START_BACKEND_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0orchestrator"
if exist ".venv\Scripts\python.exe" (
  echo 后端启动中, 地址 http://127.0.0.1:8765
  .venv\Scripts\python.exe -m backend
) else (
  echo [错误] 未找到 orchestrator\.venv, 请先运行 setup.bat
  pause
)
"""

START_CLIENT_BAT = r"""@echo off
chcp 65001 >nul
cd /d "%~dp0orchestrator"
if exist ".venv\Scripts\python.exe" (
  .venv\Scripts\python.exe -m client
) else (
  echo [错误] 未找到 orchestrator\.venv, 请先运行 setup.bat
  pause
)
"""

README_TXT = """达人招商编排 (recruit-bundle) — 可分发包
================================================

本包把四个项目合到一起, 拷到别的 Windows 机器即可运行:
  - orchestrator/     达人招商全流程编排 (LangGraph 后端 + 前端面板)
  - wxshop-cli/       微信小店 CLI (Playwright, 扫描达人/提取联系方式/IM 招商)
  - wechat-friend-add/ 微信桌面端加好友/发消息 (固定坐标自动化)
  - rag/              RAG 智能问答服务 (LangGraph Server + Milvus/Redis/MySQL, Docker 栈)
                      【可选】只发固定招商文案不需要它; 需要 AI 自动回复才装

为什么不是「自带 venv」?
  Python 虚拟环境、Playwright Chromium、Docker 镜像都指向本机/本用户的绝对路径, 无法随
  目录搬家。因此本包只含源码, 由 setup.bat / setup-rag.bat 在目标机上一键重建。

首次使用
  1. 双击 setup.bat
     - 自动安装 uv -> 重建三个 Python 项目的 .venv -> 下载 Chromium -> 导入登录态/密钥
     - 需要联网 (装依赖 + Chromium ~150MB + 可选 Electron npm)
  2. 双击 start-all.bat 启动完整面板 (Electron, 自动拉起后端 :8765)
     若 Electron 未装成功, 会回退到轻量客户端 (先开后端窗口再开客户端窗口)

AI 自动回复 (可选) — 部署 RAG 服务
  1. 启动 Docker Desktop
  2. 双击 setup-rag.bat
     - 复制 .env.example -> .env (填 LLM_API_KEY), 拉 CI 镜像 ghcr.io/pnj-star/rag:latest
       并 docker compose up -d, 再导入知识库
     - 首次需下载数 GB 镜像, 依赖网络
  3. 验证 http://localhost:2024/ok 返回 ok
  之后微信自动回复会走该 RAG 服务; 关闭用 cd rag && docker compose down

登录态 / 密钥
  - wxshop 小店登录态: 默认 ~/.wxshop/weixin_store_state.json。
    若包内带 secrets/ (构建时用了 --with-secrets), setup 会自动导入;
    否则在 wxshop-cli 下运行 `uv run wxshop login` 扫码生成。
  - 微信桌面端需先打开并登录微信。
  - RAG 需要 .env 的 LLM_API_KEY (rag 目录内); rag 的 .env 不在 secrets 里, 需目标机自己填。
  - secrets/ 内含 cookies 与 API 密钥, 属于敏感数据, 请勿公开分发。

常见问题
  - setup 报 uv 找不到: 重开终端或按提示手动安装 https://docs.astral.sh/uv/
  - rag 起不来: 确认 Docker Desktop 已启动、.env 的 LLM_API_KEY 已填
  - 微信窗口必须是 1920x1080 最大化 (坐标点击的前提)。
  - 其它细节见各子项目 README / AGENT.md / CLAUDE.md。
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="把三个项目打成可分发包")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="输出目录 (默认 dist/recruit-bundle)")
    ap.add_argument("--with-secrets", action="store_true", help="打包登录态/密钥 (敏感)")
    ap.add_argument("--zip", action="store_true", help="额外打成 zip")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的非空输出目录")
    args = ap.parse_args()

    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass

    out = Path(args.out).resolve()
    if out.exists() and any(out.iterdir()) and not args.force:
        print(f"[错误] {out} 已存在且非空, 加 --force 覆盖")
        return 1

    print(f"输出目录: {out}")
    for name, repo in REPOS:
        if not (repo / ".git").exists():
            print(f"[错误] {name} 不是 git 仓库: {repo}")
            return 1
        _warn_untracked(repo)

    if out.exists():
        _rmtree_retry(out)
    out.mkdir(parents=True)

    for name, repo in REPOS:
        print(f"归档 {name} <- {repo}")
        _git_archive(repo, out / name)

    _write(out, "setup.bat", SETUP_BAT)
    _write(out, "setup-rag.bat", SETUP_RAG_BAT)
    _write(out, "start-all.bat", START_ALL_BAT)
    _write(out, "start-backend.bat", START_BACKEND_BAT)
    _write(out, "start-client.bat", START_CLIENT_BAT)
    _write(out, "README.txt", README_TXT)

    if args.with_secrets:
        _copy_secrets(out)

    print(f"\n完成: {out}")
    print("下一步: 把该目录拷到目标机器, 先跑 setup.bat, 再跑 start-all.bat。")

    if args.zip:
        zf = out.with_name(out.name + ".zip")
        zf.unlink(missing_ok=True)
        with zipfile.ZipFile(zf, "w", zipfile.ZIP_DEFLATED) as z:
            for p in out.rglob("*"):
                z.write(p, p.relative_to(out.parent))
        print(f"已打包: {zf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

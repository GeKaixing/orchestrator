# AGENT.md — orchestrator (达人招商自动化编排)

> 本文件给**在此仓库工作的 AI 编码代理**看：告诉你这个仓库是什么、东西在哪、怎么跑、改东西时有哪些坑。
> 给人类读者的业务说明请看 `PROJECT_README.md`。

---

## 0. 一句话定位

`orchestrator` 是一个**把多个现成 CLI 工具串成流水线的「达人招商」编排系统**：
微信小店达人广场爬达人 → 提取联系方式 → 自动加微信好友 / 在小店 IM 发招商文案 →
达人回消息时用 RAG 自动应答。Python 编排核心 (LangGraph) + FastAPI 后端 + Electron/React 桌面端。

**你改代码时主要动的是 `recruit/` 和 `backend/`。`agents/` 下的子项目是外部 git 仓库的 clone，不要在里面改业务（见 §7 坑位）。**

---

## 1. 仓库布局（三层 + 外部子项目）

```
orchestrator/
├─ recruit/                 ← 编排核心（你主要改这里）
│  ├─ __main__.py / cli.py  ← 入口: python -m recruit
│  ├─ graph.py              ← LangGraph 主图 + 每联系人子图
│  ├─ state.py              ← RecruitState / ContactState (TypedDict + reducer)
│  ├─ config.py             ← RecruitConfig（stage/limit/text…）
│  ├─ paths.py              ← 所有路径常量 + 依赖项目解析（重点读 §3）
│  ├─ agents/               ← Agent 协议层
│  │  ├─ base.py            ← BaseAgent / AgentResult（接口契约）
│  │  ├─ registry.py        ← 名字 → agent 实例（wechat/shop/rag/openwiki）
│  │  ├─ client.py          ← 调用入口: worker 优先，失败回落直调
│  │  ├─ worker.py          ← 常驻 TCP worker 进程
│  │  └─ {wechat,shop,rag,openwiki}.py  ← 四个 agent 适配实现
│  ├─ nodes/                ← 各阶段节点（scan/contacts/recruit/im/invite/reply/report/preflight）
│  └─ services/             ← 持久化/账号/底层驱动（db/followup/accounts/wxshop/wechat/openwiki/runner/store）
├─ backend/                 ← FastAPI 服务（127.0.0.1:8765）
│  ├─ app.py                ← 全部 REST 路由；lifespan 里 start_all() 拉起 worker
│  ├─ agent_manager.py      ← 托管 worker 进程 + 3s 健康轮询 + 自动重启
│  └─ {runs,configs,files,preflight,updates,wxshop_debug,agent_store}.py
├─ desktop/                 ← Electron + React + TS 正式桌面 GUI（不在此仓库编译，见 §2）
├─ agents/                  ← 依赖的外部子项目（git clone，非本仓库代码）
│  ├─ wxshop-cli/           ← 微信小店 CLI（Playwright 驱动）
│  ├─ wechat-friend-add/    ← 微信桌面端加好友/发消息（cua-driver 驱动 UI）
│  ├─ openwiki/             ← 本地知识脑（Personal 模式，RAG 用）
│  └─ wiki/                 ← 旧知识库结构（已部分弃用）
├─ tools/build_bundle.py    ← 把项目打包成离线 dist/recruit-bundle/
├─ recruit_orchestrator.py  ← ⚠️ 旧版手写编排（单进程、不经 LangGraph/backend）。兼容保留，非主线。
├─ PROJECT_README.md        ← 业务/架构人类说明
└─ pyproject.toml           ← Python 依赖（langgraph/fastapi/cua-driver…）
```

数据文件（运行时生成，在仓库根 `orchestrator/`）：`talents.jsonl`、`contacts.jsonl`、
`recruit_state.json`、`recruit_report.md`、`recruit.db`、`达人跟进表`(在 wxshop-cli 里，见 §3)。

---

## 2. 怎么跑

### 2.1 编排核心（CLI，首选）
```bash
python -m recruit --stage all --limit 10          # 全流程
python -m recruit --stage scan --cat 美妆 --max-pages 2
python -m recruit --stage im    --text "招商文案"
python -m recruit --stage reply                  # IM 自动回复（需 rag 服务）
python -m recruit --contacts contacts.jsonl      # 跳过 wxshop，直接用现成 contacts
```
`--stage` 取值：`scan | add | send | im | invite | reply | all`（legacy `recruit_orchestrator.py` 仅支持 scan/add/send/im/reply/all）。

### 2.2 后端 + 桌面
```bash
python -m backend            # FastAPI，127.0.0.1:8765，自动拉起 worker
cd desktop && npm run dev     # Electron GUI（run_desktop.bat 亦可）
```
后端启动（`app.py` lifespan）→ `agent_manager.start_all()` 拉起 `wechat/shop/openwiki` worker
（**默认跳过 rag**，见 §7），后台线程每 3s 健康轮询、连续 3 次失败自动重启。

### 2.3 依赖 / 环境
- Python ≥ 3.11，依赖见 `pyproject.toml`，用 `uv` 安装（`uv sync` / `uv run`）。
- `agents/` 子项目各自有独立 `.venv`；`recruit_orchestrator.py` 通过 `_venv_python()` 找
  `<proj>/.venv/Scripts/python.exe`（Windows）或 `.venv/bin/python`。
- 环境变量：
  - `RECRUIT_AGENT_LOCAL=1`：强制进程内直调 agent（跳过 worker，测试/独立 CLI 用）。
  - `RECRUIT_SKIP_AGENTS=rag`（默认）：逗号分隔，控制后端启动时不拉起哪些 worker（设空 `RECRUIT_SKIP_AGENTS=` 则全拉起）。

---

## 3. 路径解析（必读，最容易踩坑）

所有外部依赖路径在 `recruit/paths.py` 的 `_sibling(name)` 解析，**回退顺序固定**：
```
orchestrator/agents/<name>   →  orchestrator 同级目录  →  ~/Desktop/<name>
```
即：依赖子项目默认放在 `orchestrator/agents/` 下（当前布局）；旧布局在同级的 `wxshop-cli/`
等；再不行回退到 `~/Desktop/`。改动路径逻辑时务必保证三处回退都还在，否则 runtime 找不到 venv。

关键常量：
- `WORK_DIR = PROJECT_ROOT`（= orchestrator 根，数据文件都在这）
- `WXSHOP_DIR / WECHAT_FRIEND_DIR / RAG_DIR / OPENWIKI_DIR / WIKI_DIR` 都来自 `_sibling`
- `FOLLOWUP_DB = WXSHOP_DIR / "达人跟进表.db"`（48 列跟进表，**由 wxshop-cli 维护**，orchestrator 直接读写）
- `STAGES_DONE = {"sent", "im_sent", "added"}`：命中即跳过（见 §5）

---

## 4. 架构要点（改代码前先懂）

### 4.1 LangGraph 编排（`graph.py` + `state.py`）
- 主图：`START → preflight → (按 stage 路由) → scan / load_contacts / im_recruit / invite / reply → build_todo → fan_out(每联系人 Send 子图) → join → report → END`。
- 每联系人子图：`add → (route_after_add: 成功且需 send 则 send) → done`。
- 状态 `RecruitState` / `ContactState` 用 TypedDict；`results` 通道带 `merge_results` reducer，各 `Send` 分支结果逐条并入（**不要直接覆盖 results**）。
- `graph.invoke(..., config={"recursion_limit": 200})` — 改图结构时注意别让并发分支突破递归上限。
- `RecruitConfig.needs_text()`：stage 为 `all/send/im/invite` 时必须传 `--text` 或 `.env` 的 `RECRUIT_TEXT`，否则 CLI 直接退出 1。

### 4.2 Agent Worker 模型（`agents/` + `backend/agent_manager.py`）
- **调用入口统一是 `client.call(name, action, **params)`**：
  1. 先查 `db` 的 `agents` 表拿 running worker 的 `port`，走 TCP 调用；
  2. worker 不存在/不可达/异常 → 回落 `registry.get(name).run(...)`（进程内直调同名 adapter）。
- **worker 协议**（`worker.py`，newline-delimited JSON over `127.0.0.1` TCP）：
  - 请求：`{"id":1,"method":"health"}` 或 `{"id":1,"method":"call","action":"...","params":{...}}`
  - 响应：`{"id":1,"ok":true,"result":{...}}` / `{"id":1,"ok":false,"error":"..."}`
  - `call` 用 `_call_lock` **串行**（天然序列化微信 UI 动作，避免并发点 UI 出错）；`health` 不抢锁即时响应（长任务不堵死健康检查）。
  - worker 启动后 **stdout 只打印一行 `PORT <n>`** 供 Manager 捕获；日志走 stderr。
- **新增一个 agent**：在 `agents/` 写一个继承 `BaseAgent` 的类（`name` 属性 + `health()` + `run(action, **params)`），在 `registry.py` 注册，并在 `agent_manager.AGENT_NAMES` 加入（若需后端托管）。

### 4.3 Agent 接口契约（`agents/base.py`）
- `AgentResult = {"success": bool, "data": dict, "error": str|None}`，用 `ok()/fail()` 构造。
- `BaseAgent.health()` 返回 `{ok, detail, checked_at}`：`ok=False` 表示**依赖不可用（降级）**，不是崩溃——preflight 据此判断能否继续。
- `run(action, **params)` 根据 `action` 字符串分发到具体能力。

---

## 5. 阶段 / 跳过逻辑（改流程必看）

`STAGES_DONE = {"sent", "im_sent", "added"}` 是断点续跑的核心：
- 某人状态 `stage` 落在集合里 → `build_todo` 直接跳过，**不再重发**。
- 改流程/重测时想重跑某人，要么改 `recruit_state.json` 里其 `stage`，要么换条件让 `load_contacts` 不命中。
- `fan_out` 用 `Send("process_contact")` 实现每联系人并发分支；子图 `add` 成功后 `route_after_add` 决定要不要 `send`。
- `invite`：IM 里发 5 条邀约 → 写联系方式进跟进表 → 微信加好友（只加不发文案，等对方通过）。
- `reply`：扫描已招商 IM 房间，达人新消息 → rag 作答 → im-chat 回复（按 `msgId` 去重，状态记 `replied_msg_ids`）。

---

## 6. 常见改动任务 → 改哪

| 想做的事 | 改哪里 |
|---|---|
| 新增一个编排阶段（如 `followup`） | `graph.py`（`route_preflight`/`build_graph` 加节点+边）+ `state.py`（如需新字段）+ 新增 `nodes/<x>.py` |
| 调整某阶段行为（加好友/发消息/扫描） | 对应 `recruit/nodes/*.py` |
| 新增一个外部能力（新 agent） | `recruit/agents/<x>.py`(继承 BaseAgent) + `registry.py` + `agent_manager.AGENT_NAMES` |
| 改持久化/跟进表字段 | `recruit/services/db.py`、`followup.py`（注意 `达人跟进表.db` 是 wxshop-cli 的 48 列表） |
| 改多账号轮换 | `recruit/services/accounts.py`（`settings` 表 `current_account`） |
| 改后端 API | `backend/app.py`（及 `runs/configs/files/...` 等模块） |
| 改路径/依赖位置 | `recruit/paths.py`（务必保留三处回退） |
| 改招商文案缺省来源 | `.env` 的 `RECRUIT_TEXT` 或 `recruit/config.py` 的 `resolve_text()` |
| 加 CLI 参数 | `recruit/cli.py` 的 `_build_parser()` |

---

## 7. 坑位 / 雷区（务必注意）

1. **`agents/` 是外部仓库的 clone，不是本仓库代码。** 这里的 `wxshop-cli`/`wechat-friend-add`/`openwiki` 是独立 git 项目，业务改动应回各自仓库；在本仓库里只把它们当「已安装依赖」调用，不要大改其源码（除非明确要 vendoring）。agent 适配层（`recruit/agents/{wechat,shop,rag,openwiki}.py`）才是本仓库该改的。
2. **wxshop 登录态约 1 天有效**（`storage_state`）。跑 `scan`/`contact`/`im` 前先确认登录态有效（`wxshop persist verify`），失效会整段失败。
3. **小店官方 IM 的 `im-send` HTTP 接口已失效（404）**，只能走 `im-chat` UI 路径（打开 IM 页 → 填 textarea → Enter）。判断成功靠 stdout 含 `"ok": true`。
4. **`rag` 默认不随后端启动**（`RECRUIT_SKIP_AGENTS=rag`）。`reply` 阶段强依赖 `localhost:2024` 的 rag 服务；只发固定文案可不依赖 rag。
5. **`health` 与 `call` 行为不同**：worker 的 `health` 即时响应不排队，`call` 串行。长任务（如 `openwiki` 问答几十秒）期间 `health` 仍该秒回——若你实现 worker 动作时把重活放进 `health` 会堵死健康检查。
6. **状态跳过是幂等护栏**：误把某人标成 `sent`/`added` 会导致永远不重发。调试时检查 `recruit_state.json`。
7. **`RecruitConfig` 校验**：`all/send/im/invite` 缺文案直接退出，别在改 CLI 时把 `needs_text()` 逻辑弄丢。
8. **`recruit_orchestrator.py`（根目录旧版）与新 `python -m recruit` 并存**：旧版是手写 subprocess 编排、不经 LangGraph/backend、自己维护一份 `STAGES_DONE={"sent","im_sent"}`。改流程时确认你改的是「主线 `recruit/`」还是「旧版单文件」，二者不共享状态机。
9. **Windows 路径**：子进程用 `taskkill /T /F` 杀 worker 进程树；日志落 `logs/agents/<name>.log`（避免管道缓冲阻塞 worker）。

---

## 8. 调试技巧

- 单测某个 worker：`python -m recruit.agents.worker <name> --selftest`（`--port 0` 随机端口，`--port N` 指定）。
- 看 agent 健康：`python -m recruit.agents.client` 导出的 `health_all()`，或后端 `/api/agents`。
- 后端日志：worker 日志在 `logs/agents/*.log`；backend 自身 stdout/stderr。
- 断点续跑：直接改 `recruit_state.json` 里对应 wxid 的 `stage` 为 `pending` 即可重跑该人。
- 打包离线版：`python tools/build_bundle.py` → `dist/recruit-bundle/`（含 `recruit-bundle.zip`）。

---

## 9. 约定小结

- 代码注释用中文，标识符用英文；文档尽量与 `PROJECT_README.md` 风格一致。
- 新增 agent/节点遵循既有 `BaseAgent` / `TypedDict` 契约，不要另起一套返回格式。
- 任何「调用外部进程/UI 自动化」都走 `client.call()` → worker（或 RECRUIT_AGENT_LOCAL 直调），不要自己在节点里裸 subprocess 调 wxshop/wechat。
- 改图后留意 `recursion_limit=200`；`fan_out` 并发分支数受此限制。

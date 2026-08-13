"""配置模型 — 由 cli 解析参数后构造, 注入 LangGraph state."""

from __future__ import annotations

from pydantic import BaseModel, Field

from .paths import WECHAT_FRIEND_DIR


def resolve_text(args_text: str) -> str:
    """文案来源: --text 优先, 否则读 wechat-friend-add/.env 的 RECRUIT_TEXT."""
    if args_text.strip():
        return args_text.strip()
    env = _load_env()
    return env.get("RECRUIT_TEXT", "").strip()


def _load_env() -> dict:
    env: dict[str, str] = {}
    path = WECHAT_FRIEND_DIR / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


class RecruitConfig(BaseModel):
    """一次编排运行的参数 (对应原脚本 CLI 参数)."""

    stage: str = Field(default="all", description="all/scan/add/send/im")
    contacts: str = Field(default="", description="现成 contacts.jsonl, 跳过 wxshop 扫描")
    cat: str = Field(default="", description="daren-scan 达人类目筛选")
    max_pages: int = Field(default=1, description="daren-scan 页数")
    limit: int = Field(default=10, description="本轮最多处理 N 个 wxid")
    text: str = Field(default="", description="招商文案 (缺省读 .env 的 RECRUIT_TEXT)")
    watch: bool = Field(default=False, description="是否要求持续自动回复 (仅提示)")
    retry: int = Field(default=1, description="每个动作失败后额外重试次数")

    @property
    def contacts_path(self) -> str:
        return self.contacts

    def actions_for(self) -> list[str]:
        """由 stage 推导联系人子图要执行的动作."""
        if self.stage == "add":
            return ["add"]
        if self.stage == "send":
            return ["send"]
        return ["add", "send"]

    def needs_text(self) -> bool:
        return self.stage in ("all", "send", "im")

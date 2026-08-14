"""LangGraph 主图 + 每联系人子图组装.

主图路由:
  START → preflight
    preflight ─(error)→ END
    preflight ─(stage=im)→ im_recruit → report → END
    preflight ─(stage=all/scan)→ scan → load_contacts
    preflight ─(else)→ load_contacts
  load_contacts ─(error)→ END; ─(ok)→ build_todo
  build_todo → fan_out: 每人一个 Send("process_contact") 分支, 或直达 report
  process_contact(子图) → join → report → END
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from .state import ContactState, RecruitState
from .nodes.contacts import build_todo, fan_out, join, load_contacts
from .nodes.im import im_recruit
from .nodes.invite import invite
from .nodes.preflight import preflight
from .nodes.recruit import add, done, route_after_add, send
from .nodes.reply import reply
from .nodes.report import report
from .nodes.scan import scan


def build_contact_graph() -> StateGraph:
    """每联系人子图: add → (成功且需 send) → send → done."""
    g = StateGraph(ContactState)
    g.add_node("add", add)
    g.add_node("send", send)
    g.add_node("done", done)
    g.add_edge(START, "add")
    g.add_conditional_edges("add", route_after_add, {"send": "send", "done": "done"})
    g.add_edge("send", "done")
    g.add_edge("done", END)
    return g.compile()


def route_preflight(state: RecruitState) -> str:
    if state.get("error"):
        return "end"
    stage = state["config"].stage
    if stage == "im":
        return "im"
    if stage == "invite":
        return "invite"
    if stage == "reply":
        return "reply"
    if stage in ("all", "scan"):
        return "scan"
    return "load"


def route_error(state: RecruitState) -> str:
    return "end" if state.get("error") else "next"


def route_after_scan(state: RecruitState) -> str:
    """scan 后路由: error→end; 无联系方式(但画像已存跟进表)→直接报告; 否则→load_contacts."""
    if state.get("error"):
        return "end"
    if state.get("no_contacts"):
        return "report"
    return "load"


def build_graph() -> StateGraph:
    g = StateGraph(RecruitState)
    g.add_node("preflight", preflight)
    g.add_node("scan", scan)
    g.add_node("load_contacts", load_contacts)
    g.add_node("build_todo", build_todo)
    g.add_node("process_contact", build_contact_graph())
    g.add_node("join", join)
    g.add_node("im_recruit", im_recruit)
    g.add_node("invite", invite)
    g.add_node("reply", reply)
    g.add_node("report", report)

    g.add_edge(START, "preflight")
    g.add_conditional_edges(
        "preflight", route_preflight,
        {"end": END, "im": "im_recruit", "invite": "invite", "reply": "reply",
         "scan": "scan", "load": "load_contacts"},
    )
    g.add_conditional_edges(
        "scan", route_after_scan, {"end": END, "report": "report", "load": "load_contacts"})
    g.add_conditional_edges("load_contacts", route_error, {"end": END, "next": "build_todo"})
    g.add_conditional_edges(
        "build_todo", fan_out,
        {"process_contact": "process_contact", "report": "report"},
    )
    g.add_edge("process_contact", "join")
    g.add_edge("join", "report")
    g.add_conditional_edges("im_recruit", route_error, {"end": END, "next": "report"})
    g.add_conditional_edges("invite", route_error, {"end": END, "next": "report"})
    g.add_conditional_edges("reply", route_error, {"end": END, "next": "report"})
    g.add_edge("report", END)
    return g.compile()

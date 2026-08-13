"""Agent 协议层 — 统一 agent 接口: 每个 agent 暴露 health() + run(action, **params).

Agent 不知道 LangGraph; orchestrator 通过 recruit.agents.client 调用.
"""

import { useCallback, useState } from 'react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { AgentStatus, AgentStatusName } from '../types'

const AGENTS: AgentStatusName[] = ['wechat', 'shop', 'rag']
const AGENT_LABEL: Record<AgentStatusName, string> = {
  wechat: '微信 Agent',
  shop: '小店 Agent',
  rag: 'RAG Agent'
}
const STATE_LABEL: Record<string, string> = {
  running: '运行中',
  degraded: '降级',
  error: '异常',
  stopped: '已停止',
  starting: '启动中'
}
const STATE_COLOR: Record<string, string> = {
  running: '#3ddc84',
  degraded: '#ffb84d',
  error: '#ff6b6b',
  stopped: '#9aa0a6',
  starting: '#ffb84d'
}
const DOT_CLASS: Record<string, string> = {
  running: 'green',
  degraded: 'yellow',
  error: 'red',
  stopped: '',
  starting: 'yellow'
}

export default function AgentsPanel(): JSX.Element {
  const [agents, setAgents] = useState<AgentStatus[]>([])
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setAgents(await api<AgentStatus[]>('/api/agents'))
    } catch (e) {
      console.error(e)
    }
  }, [])

  usePolling(load, 2000, true)

  const act = async (name: AgentStatusName, action: string): Promise<void> => {
    setBusy(`${name}:${action}`)
    try {
      await api(`/api/agents/${name}/${action}`, { method: 'POST' })
      await load()
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="agents-panel">
      <div className="agents-cards">
        {AGENTS.map((name) => {
          const a = agents.find((x) => x.name === name)
          const state = a?.status ?? 'stopped'
          return (
            <div key={name} className="agent-card">
              <div className="agent-card-head">
                <span className={`dot ${DOT_CLASS[state] ?? ''}`}>●</span>
                <span className="agent-name">{AGENT_LABEL[name]}</span>
              </div>
              <div className="agent-state" style={{ color: STATE_COLOR[state] }}>
                {STATE_LABEL[state]}
              </div>
              <div className="agent-meta">
                {state === 'running' && a?.pid ? `pid ${a.pid}` : ''}
                {state === 'running' && a?.port ? ` · :${a.port}` : ''}
              </div>
              <div className="agent-detail muted" title={a?.detail}>
                {a?.detail || '(未启动)'}
              </div>
              <div className="agent-last muted">检查 {a?.last_health || '—'}</div>
              <div className="agent-actions">
                {state === 'running' ? (
                  <>
                    <button
                      className="btn sm ghost"
                      disabled={busy !== null}
                      onClick={() => void act(name, 'restart')}
                    >
                      重启
                    </button>
                    <button
                      className="btn sm ghost"
                      disabled={busy !== null}
                      onClick={() => void act(name, 'stop')}
                    >
                      停止
                    </button>
                  </>
                ) : (
                  <button
                    className="btn sm primary"
                    disabled={busy !== null}
                    onClick={() => void act(name, 'start')}
                  >
                    启动
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

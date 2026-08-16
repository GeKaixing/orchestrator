import { useCallback, useState } from 'react'
import { Loader2, Play, RotateCw, Square } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { AgentStatus, AgentStatusName } from '../types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { cn } from '@/lib/utils'

const AGENTS: AgentStatusName[] = ['wechat', 'shop', 'rag', 'openwiki']
const AGENT_LABEL: Record<AgentStatusName, string> = {
  wechat: '微信 Agent',
  shop: '微信小店 Agent',
  rag: 'RAG Agent',
  openwiki: 'OpenWiki Agent'
}
const STATE_LABEL: Record<string, string> = {
  running: '运行中',
  degraded: '降级',
  error: '异常',
  stopped: '已停止',
  starting: '启动中'
}
const STATE_COLOR: Record<string, string> = {
  running: '#16a34a',
  degraded: '#d97706',
  error: '#dc2626',
  stopped: '#8a94a6',
  starting: '#d97706'
}
const DOT_CLASS: Record<string, string> = {
  running: 'bg-green-500',
  degraded: 'bg-yellow-500',
  error: 'bg-red-500',
  stopped: 'bg-muted-foreground/60',
  starting: 'bg-yellow-500'
}

export default function AgentsPanel({ stacked = false }: { stacked?: boolean }): JSX.Element {
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
    <div className={cn('grid grid-cols-1 gap-3', !stacked && 'sm:grid-cols-3')}>
      {AGENTS.map((name) => {
        const a = agents.find((x) => x.name === name)
        const state = a?.status ?? 'stopped'
        return (
          <Card key={name} className="gap-2 py-4">
            <CardContent className="flex flex-col gap-1.5 px-4">
              <div className="flex items-center gap-2">
                <span className={cn('size-2.5 rounded-full', DOT_CLASS[state] ?? 'bg-muted-foreground/60')} />
                <span className="text-sm font-semibold">{AGENT_LABEL[name]}</span>
              </div>
              <div className="text-lg font-bold" style={{ color: STATE_COLOR[state] }}>
                {STATE_LABEL[state]}
              </div>
              <div className="mono text-[11px] text-muted-foreground">
                {state === 'running' && a?.pid ? `pid ${a.pid}` : ''}
                {state === 'running' && a?.port ? ` · :${a.port}` : ''}
              </div>
              <div className="truncate text-[11px] text-muted-foreground" title={a?.detail}>
                {a?.detail || '(未启动)'}
              </div>
              <div className="text-[11px] text-muted-foreground">检查 {a?.last_health || '—'}</div>
              <div className="mt-1 flex gap-1.5">
                {state === 'running' ? (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={busy !== null}
                      onClick={() => void act(name, 'restart')}
                    >
                      {busy === `${name}:restart` ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <RotateCw className="size-3.5" />
                      )}
                      {busy === `${name}:restart` ? '重启中' : '重启'}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={busy !== null}
                      onClick={() => void act(name, 'stop')}
                    >
                      <Square className="size-3.5" />
                      停止
                    </Button>
                  </>
                ) : (
                  <Button
                    size="sm"
                    disabled={busy !== null}
                    onClick={() => void act(name, 'start')}
                  >
                    <Play className="size-3.5" />
                    启动
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}

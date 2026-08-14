import { useCallback, useState } from 'react'
import { Activity, Loader2, Play, RotateCw, Square, Store } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { AgentStatus } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import WxshopCli from './WxshopCli'

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
const STATE_BADGE: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  running: 'default',
  degraded: 'secondary',
  error: 'destructive',
  stopped: 'outline',
  starting: 'secondary'
}

export default function Shop(): JSX.Element {
  const [agent, setAgent] = useState<AgentStatus | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [live, setLive] = useState<{ ok: boolean; detail?: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await api<AgentStatus[]>('/api/agents')
      setAgent(list.find((x) => x.name === 'shop') ?? null)
    } catch (e) {
      console.error(e)
    }
  }, [])

  usePolling(load, 2000, true)

  const act = async (action: string): Promise<void> => {
    setBusy(action)
    try {
      await api(`/api/agents/shop/${action}`, { method: 'POST' })
      await load()
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(null)
    }
  }

  const runHealth = async (): Promise<void> => {
    setBusy('health')
    try {
      setLive(await api<{ ok: boolean; detail?: string }>('/api/agents/shop/health'))
    } catch (e) {
      setLive({ ok: false, detail: String(e) })
    } finally {
      setBusy(null)
    }
  }

  const state = agent?.status ?? 'stopped'
  const running = state === 'running'

  return (
    <div className="flex h-full gap-4">
      <div className="flex min-h-0 flex-1 flex-col gap-4">
        <WxshopCli />
      </div>

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <Store className="size-5 text-primary" />
              微信小店 Agent
            </CardTitle>
            <CardDescription>微信小店(优选联盟)达人招商采集服务（worker 进程）</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4 px-6">
            <div className="flex items-center gap-3">
              <Badge variant={STATE_BADGE[state] ?? 'outline'}>{STATE_LABEL[state] ?? state}</Badge>
              <span className="text-lg font-bold" style={{ color: STATE_COLOR[state] ?? '#8a94a6' }}>
                {STATE_LABEL[state] ?? state}
              </span>
            </div>

            <div className="mono grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <span>pid {agent?.pid ?? '—'}</span>
              <span>port {agent?.port ?? '—'}</span>
              <span className="col-span-2 truncate" title={agent?.detail}>
                {agent?.detail || '(未启动)'}
              </span>
              <span className="col-span-2">最近健康检查 {agent?.last_health || '—'}</span>
            </div>

            <div className="flex flex-wrap gap-2">
              {running ? (
                <>
                  <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void act('restart')}>
                    {busy === 'restart' ? <Loader2 className="size-4 animate-spin" /> : <RotateCw className="size-4" />}
                    {busy === 'restart' ? '重启中' : '重启'}
                  </Button>
                  <Button size="sm" variant="ghost" disabled={busy !== null} onClick={() => void act('stop')}>
                    <Square className="size-4" />
                    停止
                  </Button>
                </>
              ) : (
                <Button size="sm" disabled={busy !== null} onClick={() => void act('start')}>
                  <Play className="size-4" />
                  启动
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => void runHealth()}>
                {busy === 'health' ? <Loader2 className="size-4 animate-spin" /> : <Activity className="size-4" />}
                {busy === 'health' ? '检查中' : '健康检查'}
              </Button>
            </div>

            {live && (
              <div
                className={cn(
                  'rounded-md border px-3 py-2 text-xs',
                  live.ok ? 'border-green-300 bg-green-50 text-green-800' : 'border-red-300 bg-red-50 text-red-800'
                )}
              >
                {live.ok ? '健康 ✓' : '异常 ✗'} · {live.detail || '—'}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">服务说明</CardTitle>
          </CardHeader>
          <CardContent className="px-6 text-xs leading-relaxed text-muted-foreground">
            <p>
              shop agent 对接微信小店(优选联盟)后台，负责达人招商采集：扫描达人与商品（
              <code className="mono">scan</code>）、回填群房间号（<code className="mono">backfill_room_ids</code>）、
              提取联系人（<code className="mono">contact</code>）、群聊触达（<code className="mono">im_chat</code>）。
            </p>
            <p className="mt-2">
              健康检查会验证 wxshop 登录态是否有效；登录态失效时状态显示「降级」。任务控制页的采集/触达任务由
              本 agent 执行，启动后 agent_manager 每 3s 做健康轮询，连续失败会自动重启。
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

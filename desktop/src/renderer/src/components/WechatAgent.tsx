import { useCallback, useState } from 'react'
import { Activity, Check, Copy, Loader2, MessageCircle, Play, RotateCw, Square } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { AgentStatus } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

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

const CLI_CMDS: { desc: string; cmd: string }[] = [
  {
    desc: '一键初始化环境（装依赖 · 生成 .env · 校验 cua-driver）',
    cmd: 'powershell -ExecutionPolicy Bypass -File setup.ps1'
  },
  { desc: '添加微信好友', cmd: 'uv run python scripts/add_friend.py --wxid <微信号>' },
  { desc: '给联系人发送固定文案', cmd: 'uv run python scripts/send_message.py --wxid <微信号> --text "文案内容"' },
  { desc: 'AI 自动回复对方最新消息', cmd: 'uv run python scripts/send_message.py --wxid <微信号>' },
  { desc: '发送后持续监听对方新消息并自动回复', cmd: 'uv run python scripts/send_message.py --wxid <微信号> --watch' }
]

function CmdRow({ cmd }: { cmd: string }): JSX.Element {
  const [copied, setCopied] = useState(false)

  const copy = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(cmd)
      setCopied(true)
      setTimeout(() => setCopied(false), 1200)
    } catch {
      // 忽略剪贴板不可用
    }
  }

  return (
    <div className="flex items-center gap-2">
      <code
        className="mono min-w-0 flex-1 truncate rounded-md border bg-muted/40 px-2.5 py-1.5 text-xs"
        title={cmd}
      >
        {cmd}
      </code>
      <Button size="sm" variant="ghost" title="复制到剪贴板" onClick={() => void copy()}>
        {copied ? <Check className="size-3.5 text-green-600" /> : <Copy className="size-3.5" />}
      </Button>
    </div>
  )
}

export default function WechatAgent(): JSX.Element {
  const [agent, setAgent] = useState<AgentStatus | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [live, setLive] = useState<{ ok: boolean; detail?: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await api<AgentStatus[]>('/api/agents')
      setAgent(list.find((x) => x.name === 'wechat') ?? null)
    } catch (e) {
      console.error(e)
    }
  }, [])

  usePolling(load, 2000, true)

  const act = async (action: string): Promise<void> => {
    setBusy(action)
    try {
      await api(`/api/agents/wechat/${action}`, { method: 'POST' })
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
      setLive(await api<{ ok: boolean; detail?: string }>('/api/agents/wechat/health'))
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
        <Card className="flex min-h-0 flex-1 flex-col">
          <CardHeader className="pb-2">
            <CardTitle className="text-base">调试 CLI 命令</CardTitle>
            <CardDescription>
              工作目录{' '}
              <code className="mono">agents\wechat-friend-add</code>，可直接在终端运行（桌面端 agent 也调用同一项目）
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-2.5 px-6">
            {CLI_CMDS.map((c) => (
              <div key={c.cmd} className="flex flex-col gap-1">
                <span className="text-xs text-muted-foreground">{c.desc}</span>
                <CmdRow cmd={c.cmd} />
              </div>
            ))}
            <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
              排障产物：<code className="mono">logs/</code> 日志 · <code className="mono">screenshots/</code>{' '}
              截图 · <code className="mono">session/&lt;wxid&gt;.md</code> 会话记录
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <MessageCircle className="size-5 text-primary" />
              微信 Agent
            </CardTitle>
            <CardDescription>微信桌面端自动化 worker：达人加好友、发送文案</CardDescription>
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
            <CardTitle className="text-base">说明</CardTitle>
          </CardHeader>
          <CardContent className="px-6 text-xs leading-relaxed text-muted-foreground">
            <p>
              微信 Agent 负责驱动本机微信桌面端：向达人发送好友申请、发送招商文案。需要本机已登录运行微信桌面端，
              健康检查会报告微信桌面端是否在运行。
            </p>
            <p className="mt-2">
              agent 由后端 agent_manager 托管，启动后每 3s 做健康轮询，连续失败会自动重启。也可在「监控面板」
              的 Agent 区域统一管理 wechat / shop / rag。
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

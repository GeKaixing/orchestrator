import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, BrainCircuit, Loader2, MessageCircle, Play, RotateCcw, RotateCw, SendHorizontal, Square } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { AgentStatus } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import Markdown from '@/components/ui/markdown'

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

interface ChatMsg {
  role: 'user' | 'assistant' | 'error'
  text: string
}

const SUGGESTIONS = [
  '这款产品的佣金比例是多少？',
  '有哪些主打畅销品？',
  '发货时效和售后政策是怎样的？',
  '新人达人有扶持政策吗？'
]

function RagChat({ online }: { online: boolean }): JSX.Element {
  const [messages, setMessages] = useState<ChatMsg[]>([])
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const threadIdRef = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, asking])

  const send = async (): Promise<void> => {
    const q = input.trim()
    if (!q || asking) return
    setMessages((m) => [...m, { role: 'user', text: q }])
    setInput('')
    setAsking(true)
    try {
      const res = await api<{ reply: string; thread_id: string }>('/api/agents/rag/ask', {
        method: 'POST',
        body: { question: q, thread_id: threadIdRef.current }
      })
      threadIdRef.current = res.thread_id
      setMessages((m) => [...m, { role: 'assistant', text: res.reply }])
    } catch (e) {
      setMessages((m) => [...m, { role: 'error', text: String(e) }])
    } finally {
      setAsking(false)
    }
  }

  const reset = (): void => {
    threadIdRef.current = null
    setMessages([])
  }

  return (
    <Card className="flex min-h-0 flex-1 flex-col">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <MessageCircle className="size-4 text-primary" />
            知识库问答
            <Badge variant={online ? 'default' : 'outline'} className="gap-1">
              <span
                className={cn(
                  'size-1.5 rounded-full',
                  online ? 'bg-green-400' : 'bg-muted-foreground/70'
                )}
              />
              {online ? '在线' : '离线'}
            </Badge>
          </CardTitle>
          <Button
            size="sm"
            variant="ghost"
            onClick={reset}
            disabled={asking || messages.length === 0}
          >
            <RotateCcw className="size-3.5" />
            新对话
          </Button>
        </div>
        <CardDescription>
          向 RAG 知识库提问，回复基于检索内容生成，同一对话自动保持记忆（多轮）
        </CardDescription>
      </CardHeader>
      <CardContent className="flex min-h-0 flex-1 flex-col gap-3 px-6">
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
          <div className="flex flex-col gap-3 py-1">
            {messages.length === 0 && (
              <div className="flex flex-col items-center gap-4 py-10 text-center">
                <div className="text-xs text-muted-foreground">向 RAG 知识库提问，试试：</div>
                <div className="flex flex-wrap justify-center gap-2">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setInput(s)}
                      className="rounded-full border border-border bg-muted/50 px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn('flex', m.role === 'user' ? 'justify-end' : 'justify-start')}>
                <div
                  className={cn(
                    'max-w-[80%] rounded-lg px-3 py-2 text-[13px] leading-relaxed',
                    m.role === 'user'
                      ? 'bg-primary text-primary-foreground'
                      : m.role === 'assistant'
                        ? 'bg-muted'
                        : 'border border-red-200 bg-red-50 text-red-800'
                  )}
                >
                  {m.role === 'assistant' ? (
                    <Markdown content={m.text} />
                  ) : (
                    <span className="whitespace-pre-wrap">{m.text}</span>
                  )}
                </div>
              </div>
            ))}
            {asking && (
              <div className="flex justify-start">
                <div className="rounded-lg bg-muted px-3 py-2 text-[13px] text-muted-foreground">
                  思考中…
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-end gap-2">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
            placeholder="输入问题，Enter 发送，Shift+Enter 换行"
            className="min-h-9 max-h-32 flex-1 resize-y text-sm"
            rows={1}
            disabled={asking}
          />
          <Button size="sm" disabled={asking || input.trim() === ''} onClick={() => void send()}>
            <SendHorizontal className="size-4" />
            {asking ? '发送中…' : '发送'}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

export default function Rag(): JSX.Element {
  const [agent, setAgent] = useState<AgentStatus | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [live, setLive] = useState<{ ok: boolean; detail?: string } | null>(null)

  const load = useCallback(async () => {
    try {
      const list = await api<AgentStatus[]>('/api/agents')
      setAgent(list.find((x) => x.name === 'rag') ?? null)
    } catch (e) {
      console.error(e)
    }
  }, [])

  usePolling(load, 2000, true)

  const act = async (action: string): Promise<void> => {
    setBusy(action)
    try {
      await api(`/api/agents/rag/${action}`, { method: 'POST' })
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
      setLive(await api<{ ok: boolean; detail?: string }>('/api/agents/rag/health'))
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
      <RagChat online={running} />

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2">
              <BrainCircuit className="size-5 text-primary" />
              RAG 知识库服务
            </CardTitle>
            <CardDescription>基于向量检索的问答服务（worker 进程 · 默认健康地址 localhost:2024）</CardDescription>
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
            <CardTitle className="text-base">部署说明</CardTitle>
          </CardHeader>
          <CardContent className="px-6 text-xs leading-relaxed text-muted-foreground">
            <p>
              后端启动时默认<strong>不自动拉起</strong> RAG 服务（通过环境变量{' '}
              <code className="mono">RECRUIT_SKIP_AGENTS=rag</code> 跳过，因为 rag 服务尚未部署）。RAG 的 worker
              健康地址为 <code className="mono">localhost:2024</code>。
            </p>
            <p className="mt-2">
              部署好 RAG 服务后可在此手动「启动」；或把 <code className="mono">RECRUIT_SKIP_AGENTS</code> 置空，让 RAG
              随后端自动启动。启动后由 agent_manager 每 3s 做健康轮询，连续失败会自动重启。
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { MessageSquareReply, Play, Square } from 'lucide-react'
import { api } from '../api'
import type { Run, Settings } from '../types'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'

const STAGES = ['all', 'scan', 'add', 'send', 'im', 'invite']
const STAGE_NAME: Record<string, string> = {
  all: '全流程 (扫描→加好友→发送)',
  scan: '仅扫描提取联系方式',
  add: '仅加好友',
  send: '仅发送招商文案',
  im: '小店官方 IM 招商',
  invite: 'IM 5条邀约 → 微信复邀'
}

interface Props {
  run: Run | null
  settings: Settings
  onRunStarted: (run: Run) => void
}

export default function Controls({ run, settings, onRunStarted }: Props): JSX.Element {
  const [form, setForm] = useState<Settings>(settings)
  const [msg, setMsg] = useState('')

  // 仅挂载时用 settings 初始化; App 每 3s 轮询 settings 会传新对象,
  // 若依赖 settings 会把用户正在编辑的 stage/文案重置回默认值
  useEffect(() => {
    setForm(settings)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const set = <K extends keyof Settings>(key: K, value: Settings[K]): void =>
    setForm((f) => ({ ...f, [key]: value }))

  const start = async (): Promise<void> => {
    setMsg('')
    const stage = form.stage
    const text = form.text.trim()
    if (['all', 'send', 'im', 'invite'].includes(stage) && !text) {
      setMsg('该阶段需要招商文案: 请在下方填写或到「设置」保存')
      return
    }
    try {
      const run = await api<Run>('/api/runs', {
        method: 'POST',
        body: {
          type: 'recruit',
          stage,
          limit: Number(form.limit) || 10,
          max_pages: Number(form.max_pages) || 1,
          cat: form.cat.trim(),
          contacts: form.contacts.trim(),
          text
        }
      })
      onRunStarted(run)
      setMsg(`已启动任务 #${run.id} (${stage})`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const reply = async (): Promise<void> => {
    setMsg('')
    try {
      const run = await api<Run>('/api/runs', { method: 'POST', body: { type: 'reply' } })
      onRunStarted(run)
      setMsg(`已启动自动回复一轮 #${run.id}`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const stop = async (): Promise<void> => {
    if (!run) return
    try {
      await api(`/api/runs/${run.id}/stop`, { method: 'POST' })
      setMsg(`已请求停止任务 #${run.id}`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const running = !!run && ['pending', 'running', 'stopping'].includes(run.status)

  return (
    <div className="grid h-full grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <Card className="gap-4 py-5">
        <CardContent className="flex flex-col gap-4 px-5">
          <h2 className="text-[15px] font-semibold">任务参数</h2>

          <div className="flex flex-col gap-2">
            <Label>阶段</Label>
            <Select value={form.stage} onValueChange={(v) => set('stage', v)}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {STAGES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s} — {STAGE_NAME[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label>本轮处理数 limit</Label>
              <Input
                type="number"
                value={form.limit}
                onChange={(e) => set('limit', Number(e.target.value))}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>扫描页数 max-pages</Label>
              <Input
                type="number"
                value={form.max_pages}
                onChange={(e) => set('max_pages', Number(e.target.value))}
              />
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <Label>达人类目 cat（可空）</Label>
            <Input value={form.cat} onChange={(e) => set('cat', e.target.value)} />
          </div>

          <div className="flex flex-col gap-2">
            <Label>现成 contacts 文件（可空）</Label>
            <Input value={form.contacts} onChange={(e) => set('contacts', e.target.value)} />
          </div>

          <div className="flex flex-col gap-2">
            <Label>招商文案</Label>
            <Textarea
              value={form.text}
              onChange={(e) => set('text', e.target.value)}
              rows={8}
              className="resize-y"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="gap-4 py-5">
        <CardContent className="flex flex-col gap-3 px-5">
          <h2 className="text-[15px] font-semibold">操作</h2>
          <Button disabled={running} onClick={() => void start()}>
            <Play className="size-4" />
            启动任务
          </Button>
          <Button variant="destructive" disabled={!running} onClick={() => void stop()}>
            <Square className="size-4" />
            停止任务
          </Button>
          <Button disabled={running} onClick={() => void reply()}>
            <MessageSquareReply className="size-4" />
            自动回复一轮 (IM)
          </Button>

          <div className="mt-1 flex items-center gap-2 text-[13px]">
            <span
              className={cn(
                'size-2 rounded-full',
                run?.status === 'running' ? 'bg-green-500' : 'bg-muted-foreground/60'
              )}
            />
            <span>{runStatusText(run)}</span>
          </div>
          {msg && <div className="text-xs text-primary">{msg}</div>}
          <p className="text-xs leading-relaxed text-muted-foreground">
            all/send/im/invite 需填写招商文案; scan 只扫描提取联系方式。文案多行 = 多条消息
            (invite 用前 5 条)。启动后任务在后台子进程运行，可在「日志」查看输出。
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

function runStatusText(run: Run | null): string {
  if (!run) return '空闲'
  if (run.status === 'running') return `运行中 #${run.id} (${run.stage})`
  if (run.status === 'stopping') return `停止中 #${run.id}`
  if (run.status === 'finished') return `空闲 (#${run.id} 已完成)`
  if (run.status === 'failed') return `失败 #${run.id} (退出码 ${run.exit_code})`
  if (run.status === 'stopped') return `已停止 #${run.id}`
  return `空闲`
}

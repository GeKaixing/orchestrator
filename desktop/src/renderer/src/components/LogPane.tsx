import { useEffect, useRef, useState } from 'react'
import { ChevronDown, ChevronUp, Eraser } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { LogEntry, Run } from '../types'
import { Button } from '@/components/ui/button'

const MAX_LOGS = 2000

interface Props {
  run: Run | null
  collapsed: boolean
  onToggle: () => void
}

export default function LogPane({ run, collapsed, onToggle }: Props): JSX.Element {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [cursor, setCursor] = useState(0)
  const boxRef = useRef<HTMLPreElement>(null)

  // run 切换时重置
  useEffect(() => {
    setLogs([])
    setCursor(0)
  }, [run?.id])

  const active = !!run && ['pending', 'running', 'stopping'].includes(run.status)

  usePolling(() => {
    if (!run) return
    void api<{ logs: LogEntry[]; next: number }>(`/api/runs/${run.id}/logs?after=${cursor}`)
      .then((r) => {
        if (r.logs.length > 0) {
          setLogs((prev) => [...prev, ...r.logs].slice(-MAX_LOGS))
          setCursor(r.next)
        }
      })
      .catch(() => {})
  }, 1000, active)

  // 任务进入终态时补拉一次尾部日志
  useEffect(() => {
    if (run && ['finished', 'failed', 'stopped'].includes(run.status)) {
      void api<{ logs: LogEntry[]; next: number }>(`/api/runs/${run.id}/logs?after=${cursor}`)
        .then((r) => {
          if (r.logs.length > 0) {
            setLogs((prev) => [...prev, ...r.logs].slice(-MAX_LOGS))
            setCursor(r.next)
          }
        })
        .catch(() => {})
    }
  }, [run?.id, run?.status]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight
  }, [logs])

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-center gap-2 border-b px-3 py-1.5">
        <Button variant="ghost" size="sm" onClick={onToggle} className="-ml-1 px-1.5" title={collapsed ? '展开日志' : '收起日志'}>
          {collapsed ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
        </Button>
        <span className="text-xs font-semibold">日志 {run ? `· 运行 #${run.id} (${run.stage})` : ''}</span>
        <div className="flex-1" />
        <Button variant="ghost" size="sm" onClick={() => setLogs([])}>
          <Eraser className="size-3.5" />
          清空
        </Button>
      </div>
      {!collapsed && (
        <pre
          ref={boxRef}
          className="mono min-h-0 flex-1 overflow-auto px-3 py-2 text-[11px] leading-relaxed whitespace-pre-wrap break-all text-muted-foreground"
        >
          {logs.length === 0
            ? '(等待日志…启动任务后在此实时显示编排输出)'
            : logs.map((l) => `${l.ts} ${l.message}`).join('\n')}
        </pre>
      )}
    </div>
  )
}

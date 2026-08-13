import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import type { LogEntry, Run } from '../types'

const MAX_LOGS = 2000

interface Props {
  run: Run | null
}

export default function LogPane({ run }: Props): JSX.Element {
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
    <div className="logpane">
      <div className="logpane-head">
        <span className="logpane-title">日志 {run ? `· 运行 #${run.id} (${run.stage})` : ''}</span>
        <span className="spacer" />
        <button className="btn ghost sm" onClick={() => setLogs([])}>
          清空
        </button>
      </div>
      <pre ref={boxRef} className="logbox">
        {logs.length === 0
          ? '(等待日志…启动任务后在此实时显示编排输出)'
          : logs.map((l) => `${l.ts} ${l.message}`).join('\n')}
      </pre>
    </div>
  )
}

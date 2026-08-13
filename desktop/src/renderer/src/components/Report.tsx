import { useCallback, useState } from 'react'
import { api } from '../api'
import { usePolling } from '../usePolling'

export default function Report(): JSX.Element {
  const [text, setText] = useState('')

  const load = useCallback(async () => {
    try {
      const r = await api<{ text: string }>('/api/report')
      setText(r.text)
    } catch (e) {
      setText(String(e))
    }
  }, [])

  usePolling(load, 8000, true)

  return (
    <div className="view">
      <div className="toolbar">
        <span className="muted">报告文件: recruit_report.md</span>
        <span className="spacer" />
        <button className="btn ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <pre className="report-box">{text}</pre>
    </div>
  )
}

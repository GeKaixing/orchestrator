import { useCallback, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import { Button } from '@/components/ui/button'

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
    <div className="flex h-full flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">报告文件: recruit_report.md</span>
        <div className="flex-1" />
        <Button variant="outline" size="sm" onClick={() => void load()}>
          <RefreshCw className="size-4" />
          刷新
        </Button>
      </div>
      <pre className="mono min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">
        {text}
      </pre>
    </div>
  )
}

import { useCallback, useState } from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import AgentsPanel from './AgentsPanel'
import type { Daren, Preflight, Stats } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '@/components/ui/table'

const STAGES = ['pending', 'added', 'sent', 'im_sent', 'failed']
const STAGE_LABEL: Record<string, string> = {
  pending: '待处理',
  added: '已加好友',
  sent: '已发文案',
  im_sent: 'IM已发',
  failed: '失败'
}
const STAGE_COLOR: Record<string, string> = {
  pending: '#8a94a6',
  added: '#4a6fe0',
  sent: '#16a34a',
  im_sent: '#7c5ce0',
  failed: '#dc2626'
}

const CARD_DEFS: { key: keyof Stats; label: string; color: string }[] = [
  { key: 'total', label: '达人总数', color: '#2563eb' },
  { key: 'pending', label: '待处理', color: '#8a94a6' },
  { key: 'added', label: '已加好友', color: '#4a6fe0' },
  { key: 'sent', label: '已发文案', color: '#16a34a' },
  { key: 'im_sent', label: 'IM已发', color: '#7c5ce0' },
  { key: 'failed', label: '失败', color: '#dc2626' }
]

export default function Dashboard(): JSX.Element {
  const [stats, setStats] = useState<Stats | null>(null)
  const [darens, setDarens] = useState<Daren[]>([])
  const [filter, setFilter] = useState('全部')
  const [auto, setAuto] = useState(true)
  const [preflight, setPreflight] = useState<Preflight | null>(null)

  const load = useCallback(async () => {
    try {
      const path = filter === '全部' ? '/api/darens' : `/api/darens?stage=${filter}`
      const [s, d] = await Promise.all([api<Stats>('/api/stats'), api<Daren[]>(path)])
      setStats(s)
      setDarens(d)
    } catch (e) {
      console.error(e)
    }
  }, [filter])

  usePolling(load, 1500, auto)

  const runPreflight = async (): Promise<void> => {
    try {
      setPreflight(await api<Preflight>('/api/preflight'))
    } catch (e) {
      console.error(e)
    }
  }

  const s = stats ?? { total: 0, pending: 0, added: 0, sent: 0, im_sent: 0, failed: 0, by_stage: {} }

  return (
    <div className="flex h-full gap-4">
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
          {CARD_DEFS.map((c) => (
            <Card key={c.key} className="py-4 text-center">
              <CardContent className="px-2">
                <div className="text-xs text-muted-foreground">{c.label}</div>
                <div className="mt-1 text-2xl font-bold" style={{ color: c.color }}>
                  {String(s[c.key] ?? 0)}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">环境自检:</span>
          <Button variant="outline" size="sm" onClick={() => void runPreflight()}>
            <ShieldCheck className="size-4" />
            检查微信 / wxshop / rag
          </Button>
          {preflight && (
            <span className="text-xs text-muted-foreground">
              微信 {preflight.wechat ? '✅' : '❌'} · wxshop {preflight.wxshop ? '✅' : '❌'} · rag{' '}
              {preflight.rag ? '✅' : '❌'}
            </span>
          )}
          <div className="flex-1" />
          <Label className="gap-2 text-xs text-muted-foreground">
            阶段:
          </Label>
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="h-8 w-[120px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="全部">全部</SelectItem>
              {STAGES.map((st) => (
                <SelectItem key={st} value={st}>
                  {STAGE_LABEL[st]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Label className="gap-2 text-xs text-muted-foreground">
            <Checkbox
              checked={auto}
              onCheckedChange={(v) => setAuto(v === true)}
              className="size-4"
            />
            自动刷新
          </Label>
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-4" />
            刷新
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>微信号</TableHead>
                <TableHead>昵称</TableHead>
                <TableHead>阶段</TableHead>
                <TableHead>更新时间</TableHead>
                <TableHead className="max-w-[360px] whitespace-normal">备注</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {darens.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                    (暂无数据)
                  </TableCell>
                </TableRow>
              )}
              {darens.map((d) => (
                <TableRow key={d.wxid}>
                  <TableCell className="mono">{d.wxid}</TableCell>
                  <TableCell>{d.nickname}</TableCell>
                  <TableCell>
                    <Badge
                      variant="outline"
                      className="font-semibold"
                      style={{ color: STAGE_COLOR[d.stage] ?? '#9aa0a6' }}
                    >
                      {STAGE_LABEL[d.stage] ?? d.stage}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{d.updated}</TableCell>
                  <TableCell className="max-w-[360px] whitespace-normal text-muted-foreground">
                    {d.reason}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <AgentsPanel stacked />
      </div>
    </div>
  )
}

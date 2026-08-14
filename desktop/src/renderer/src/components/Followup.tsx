import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Search } from 'lucide-react'
import { api } from '../api'
import type { FollowupData, FollowupRow } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
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
import { cn } from '@/lib/utils'

const COLS: { key: keyof FollowupRow; label: string; mono?: boolean }[] = [
  { key: '达人昵称', label: '昵称' },
  { key: '微信号', label: '微信号', mono: true },
  { key: '手机号', label: '手机号', mono: true },
  { key: '跟进状态', label: '状态' },
  { key: '达人评分', label: '评分' },
  { key: '带货销售额', label: '带货销售额' },
  { key: '粉丝数', label: '粉丝数' },
  { key: '采集时间', label: '采集时间' },
  { key: '登记时间', label: '登记时间' },
  { key: '备注原因', label: '备注' }
]

const STATUS_COLOR: Record<string, string> = {
  已加好友: '#16a34a',
  已邀约: '#2563eb',
  'IM邀约中': '#7c5ce0',
  添加失败: '#dc2626'
}

// 脏数据可能把单格塞进超长无断行文本 (如 微信号 列混入整行数据), 而单元格 nowrap
// 会把这列撑到数千 px, 把其余列挤出可视区. 给每列设上限宽 + 省略号, 悬停 title 看全文.
const CELL_MAX_W: Partial<Record<keyof FollowupRow, string>> = {
  达人昵称: 'max-w-[150px]',
  微信号: 'max-w-[170px]',
  手机号: 'max-w-[130px]',
  带货销售额: 'max-w-[120px]',
  粉丝数: 'max-w-[110px]',
  采集时间: 'max-w-[130px]',
  登记时间: 'max-w-[130px]',
  备注原因: 'max-w-[200px]'
}

// Radix Select 不允许空字符串作为 item value, 用哨兵值代替 "全部状态"
const ALL_STATUS = '__all__'

export default function Followup(): JSX.Element {
  const [data, setData] = useState<FollowupData | null>(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    setBusy(true)
    try {
      const params = new URLSearchParams()
      if (q.trim()) params.set('q', q.trim())
      if (status) params.set('status', status)
      setData(await api<FollowupData>(`/api/followup?${params.toString()}`))
    } catch (e) {
      console.error(e)
    } finally {
      setBusy(false)
    }
  }, [q, status])

  // 搜索防抖
  useEffect(() => {
    const t = setTimeout(() => void load(), q ? 400 : 0)
    return () => clearTimeout(t)
  }, [load, q])

  const stats = data?.stats ?? {}
  const rows = data?.rows ?? []

  return (
    <div className="flex h-full gap-4">
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              className="w-[260px] pl-8"
              placeholder="搜索昵称 / 微信号 / 手机号…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <Select value={status === '' ? ALL_STATUS : status} onValueChange={(v) => setStatus(v === ALL_STATUS ? '' : v)}>
            <SelectTrigger className="h-8 w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_STATUS}>全部状态</SelectItem>
              {Object.keys(stats)
                .sort()
                .map((s) => (
                  <SelectItem key={s} value={s}>
                    {s} ({stats[s]})
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <span className="text-xs text-muted-foreground">
            共 {data?.total ?? 0} 位 · 显示 {rows.length}
          </span>
          <div className="flex-1" />
          <Button variant="outline" size="sm" disabled={busy} onClick={() => void load()}>
            <RefreshCw className="size-4" />
            刷新
          </Button>
        </div>

        <div className="min-h-0 flex-1 overflow-auto rounded-lg border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                {COLS.map((c) => (
                  <TableHead key={c.key}>{c.label}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={COLS.length} className="h-24 text-center text-muted-foreground">
                    (暂无匹配)
                  </TableCell>
                </TableRow>
              )}
              {rows.map((r, i) => (
                <TableRow key={`${r.达人昵称}-${i}`}>
                  {COLS.map((c) => {
                    const v = r[c.key]
                    if (c.key === '跟进状态' && v) {
                      return (
                        <TableCell key={c.key}>
                          <Badge
                            variant="outline"
                            className="font-semibold"
                            style={{ color: STATUS_COLOR[v] ?? '#9aa0a6' }}
                          >
                            {v}
                          </Badge>
                        </TableCell>
                      )
                    }
                    return (
                      <TableCell key={c.key} className={c.mono ? 'mono' : ''}>
                        {typeof v === 'string' && v.length > 16 ? (
                          <span
                            className={cn('block truncate', CELL_MAX_W[c.key])}
                            title={v}
                          >
                            {v}
                          </span>
                        ) : (
                          fmt(v)
                        )}
                      </TableCell>
                    )
                  })}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">跟进状态分布</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-1.5 px-6">
            {Object.keys(stats).length === 0 && (
              <span className="text-xs text-muted-foreground">(暂无数据)</span>
            )}
            {Object.entries(stats)
              .sort((a, b) => b[1] - a[1])
              .map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-[13px]">
                  <span className="flex items-center gap-2">
                    <span
                      className="size-2 rounded-full"
                      style={{ backgroundColor: STATUS_COLOR[k] ?? '#9aa0a6' }}
                    />
                    {k}
                  </span>
                  <span className="font-semibold">{v}</span>
                </div>
              ))}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v)
}

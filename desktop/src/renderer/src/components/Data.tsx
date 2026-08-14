import { useCallback, useEffect, useState } from 'react'
import { Braces, RefreshCw, Table2 } from 'lucide-react'
import { api } from '../api'
import type { FilePayload } from '../types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
import { cn } from '@/lib/utils'

const FILES = ['contacts', 'talents', 'state']

// 达人等级徽章配色 (S+ > S > A > B)
const LEVEL_COLOR: Record<string, string> = {
  'S+': '#dc2626',
  S: '#d97706',
  A: '#2563eb',
  B: '#6b7280'
}

// state 阶段徽章 (与 Dashboard 一致)
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

type Col = { key: string; label: string; mono?: boolean; badge?: boolean }

function colsFor(name: string, rows: Record<string, unknown>[]): Col[] {
  if (name === 'state') {
    return [
      { key: 'nickname', label: '昵称' },
      { key: 'stage', label: '阶段', badge: true },
      { key: 'updated', label: '更新时间' },
      { key: 'reason', label: '备注' }
    ]
  }
  const hasContact = rows.some(
    (r) => (r['微信号'] ?? '') !== '' || (r['手机号'] ?? '') !== ''
  )
  const cols: Col[] = [{ key: 'nickname', label: '昵称' }]
  if (hasContact) {
    cols.push(
      { key: '微信号', label: '微信号', mono: true },
      { key: '手机号', label: '手机号', mono: true }
    )
  }
  cols.push(
    { key: 'score', label: '评分', mono: true },
    { key: 'gmv', label: '带货销售额' },
    { key: 'fans', label: '粉丝数' },
    { key: '达人销售额等级', label: '销售额等级', badge: true },
    { key: '达人评分等级', label: '评分等级', badge: true },
    { key: '类目', label: '类目' },
    { key: 'invoice', label: '开票', badge: true }
  )
  return cols
}

function cellText(r: Record<string, unknown>, key: string): string {
  if (key === '类目') {
    return [r['类目1'], r['类目2'], r['类目3']].filter(Boolean).join(' / ')
  }
  const v = r[key]
  if (v === null || v === undefined) return ''
  return String(v)
}

export default function Data(): JSX.Element {
  const [name, setName] = useState('contacts')
  const [data, setData] = useState<FilePayload | null>(null)
  const [view, setView] = useState<'table' | 'raw'>('table')

  const load = useCallback(async () => {
    try {
      setData(await api<FilePayload>(`/api/files?name=${name}`))
    } catch (e) {
      setData({ name, count: 0, rows: [], text: String(e) })
    }
  }, [name])

  useEffect(() => {
    void load()
  }, [load])

  const rows = data?.rows ?? []
  const cols = rows.length > 0 ? colsFor(name, rows) : []

  return (
    <div className="flex h-full gap-4">
      <div className="flex min-h-0 flex-1 flex-col gap-3">
        <div className="flex items-center gap-2">
          <div className="flex-1" />
          {rows.length > 0 && (
            <div className="flex items-center rounded-md border bg-muted p-0.5">
              <Button
                variant={view === 'table' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setView('table')}
              >
                <Table2 className="size-3.5" />
                表格
              </Button>
              <Button
                variant={view === 'raw' ? 'secondary' : 'ghost'}
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => setView('raw')}
              >
                <Braces className="size-3.5" />
                原始
              </Button>
            </div>
          )}
          <Button variant="outline" size="sm" onClick={() => void load()}>
            <RefreshCw className="size-4" />
            刷新
          </Button>
        </div>

        {!data ? (
          <pre className="mono min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">
            (加载中…)
          </pre>
        ) : view === 'raw' ? (
          <pre className="mono min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">
            {data.text}
          </pre>
        ) : rows.length === 0 ? (
          <pre className="mono min-h-0 flex-1 overflow-auto rounded-lg border bg-card p-3 text-xs leading-relaxed whitespace-pre-wrap break-all">
            (该文件无结构化数据，可切「原始」查看原文)
          </pre>
        ) : (
          <div className="min-h-0 flex-1 overflow-auto rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  {cols.map((c) => (
                    <TableHead key={c.key}>{c.label}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={i}>
                    {cols.map((c) => {
                      const s = cellText(r, c.key)
                      if (c.badge) {
                        if (c.key === 'invoice') {
                          return (
                            <TableCell key={c.key}>
                              {s === '是' ? (
                                <Badge
                                  variant="outline"
                                  className="font-semibold"
                                  style={{ color: '#16a34a' }}
                                >
                                  是
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </TableCell>
                          )
                        }
                        if (c.key === 'stage') {
                          return (
                            <TableCell key={c.key}>
                              {s ? (
                                <Badge
                                  variant="outline"
                                  className="font-semibold"
                                  style={{ color: STAGE_COLOR[s] ?? '#9aa0a6' }}
                                >
                                  {STAGE_LABEL[s] ?? s}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">—</span>
                              )}
                            </TableCell>
                          )
                        }
                        return (
                          <TableCell key={c.key}>
                            {s ? (
                              <Badge
                                variant="outline"
                                className="font-semibold"
                                style={{ color: LEVEL_COLOR[s] ?? '#9aa0a6' }}
                              >
                                {s}
                              </Badge>
                            ) : (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </TableCell>
                        )
                      }
                      return (
                        <TableCell
                          key={c.key}
                          className={cn('max-w-[260px] whitespace-normal', c.mono && 'mono')}
                        >
                          {s || <span className="text-muted-foreground">—</span>}
                        </TableCell>
                      )
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className="flex w-80 shrink-0 flex-col gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">数据文件</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-3 px-6">
            <div className="flex flex-col gap-2">
              <Label className="text-xs text-muted-foreground">选择文件</Label>
              <Select value={name} onValueChange={setName}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FILES.map((f) => (
                    <SelectItem key={f} value={f}>
                      {f}.jsonl
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {data && <span className="text-xs text-muted-foreground">{data.count} 条记录</span>}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

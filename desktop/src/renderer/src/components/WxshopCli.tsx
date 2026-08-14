import { useState } from 'react'
import { Play, TerminalSquare } from 'lucide-react'
import { api } from '../api'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

interface CliResult {
  ok: boolean
  exit_code: number | null
  stdout: string
  stderr: string
  error?: string
}

const GROUPS: { group: string; items: { cmd: string; hint: string }[] }[] = [
  {
    group: '登录/账号',
    items: [
      { cmd: 'doctor', hint: '健康检查(登录态+API密钥)' },
      { cmd: 'login', hint: '扫码登录(弹出 Chromium)' },
      { cmd: 'persist status', hint: '持久化登录态状态' },
      { cmd: 'persist verify', hint: '断言登录态有效' },
      { cmd: 'account list', hint: '列出全部账号' },
      { cmd: 'config --show', hint: '查看 API 密钥' }
    ]
  },
  {
    group: '店铺信息',
    items: [
      { cmd: 'shop-info', hint: '店铺基本信息' },
      { cmd: 'shop-link', hint: '店铺 H5 链接' },
      { cmd: 'shop-taglink', hint: '店铺口令' },
      { cmd: 'favorites', hint: '收藏人数' },
      { cmd: 'compass --ds 20260813', hint: '电商数据概览(罗盘)' },
      { cmd: 'home', hint: '店铺概览' }
    ]
  },
  {
    group: '达人招商',
    items: [
      { cmd: 'daren-list --limit 10', hint: '带货者列表' },
      { cmd: 'daren-scan --max-pages 5', hint: '批量扫描(预览)' },
      { cmd: 'daren-scan --contact --out talents.jsonl', hint: '只爬有联系方式' },
      { cmd: 'daren-scan --db', hint: '扫描并 upsert 进 达人跟进表.db' },
      { cmd: 'daren-filters', hint: '带货者广场筛选维度' },
      { cmd: 'daren-detail --url <详情URL>', hint: '带货者详情' },
      { cmd: 'daren-contact --room-id <roomId>', hint: '提取联系方式' },
      { cmd: 'daren-contact --in talents.jsonl --out contacts.jsonl', hint: '批量提取联系方式' },
      { cmd: 'grade --sales "￥20万-30万" --avg-order "￥1000" --score 4.8', hint: '达人等级计算' }
    ]
  },
  {
    group: '商品/订单',
    items: [
      { cmd: 'goods-list --limit 10', hint: '商品列表' },
      { cmd: 'order-list --limit 10', hint: '订单列表' },
      { cmd: 'order-detail --order-id <id>', hint: '订单详情' },
      { cmd: 'aftersale-list --limit 10', hint: '售后订单' },
      { cmd: 'transaction-stats', hint: '交易统计概览' }
    ]
  },
  {
    group: '机构/联盟',
    items: [
      { cmd: 'agency-list --limit 10', hint: '机构广场' },
      { cmd: 'league-list --limit 10', hint: '联盟带货计划' },
      { cmd: 'coop-export --type promoter', hint: '合作导出(promoter|agency)' },
      { cmd: 'coop-manage --talents-only', hint: '爬合作管理页' }
    ]
  },
  {
    group: 'IM 触达',
    items: [
      { cmd: 'im-send --room-id <id> --message "你好"', hint: '发 IM 消息' },
      { cmd: 'im-chat --room-id <id> --message "你好"', hint: 'IM 页 UI 聊天' },
      { cmd: 'im-messages --room-id <id>', hint: '读 IM 房间消息' }
    ]
  }
]

function tokenize(s: string): string[] {
  const out: string[] = []
  let cur = ''
  let quote: string | null = null
  for (let i = 0; i < s.length; i++) {
    const ch = s[i]
    if (quote) {
      if (ch === quote) quote = null
      else cur += ch
      continue
    }
    if (ch === '"' || ch === "'") {
      quote = ch
      continue
    }
    if (/\s/.test(ch)) {
      if (cur) {
        out.push(cur)
        cur = ''
      }
      continue
    }
    cur += ch
  }
  if (cur) out.push(cur)
  return out
}

function pretty(text: string): string {
  const t = text.trim()
  if (t && (t.startsWith('{') || t.startsWith('['))) {
    try {
      return JSON.stringify(JSON.parse(t), null, 2)
    } catch {
      return t
    }
  }
  return t
}

export default function WxshopCli(): JSX.Element {
  const [cmd, setCmd] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<CliResult | null>(null)

  const run = async (): Promise<void> => {
    const argv = tokenize(cmd)
    if (argv.length === 0) return
    setRunning(true)
    setResult(null)
    try {
      const res = await api<CliResult>('/api/wxshop/run', {
        method: 'POST',
        body: { argv, timeout: 600 }
      })
      setResult(res)
    } catch (e) {
      setResult({ ok: false, exit_code: null, stdout: '', stderr: '', error: String(e) })
    } finally {
      setRunning(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <TerminalSquare className="size-4 text-primary" />
          CLI 调试
        </CardTitle>
        <CardDescription>
          直接调用 wxshop-cli 任意命令（经后端 <code className="mono">uv run wxshop</code>），结果 JSON 输出到 stdout
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4 px-6">
        {GROUPS.map((g) => (
          <div key={g.group}>
            <div className="mb-1.5 text-xs font-semibold text-muted-foreground">{g.group}</div>
            <div className="flex flex-wrap gap-1.5">
              {g.items.map((it) => (
                <button
                  key={it.cmd}
                  type="button"
                  title={it.hint}
                  className="rounded border border-border bg-muted/50 px-2 py-1 text-[11px] font-mono text-muted-foreground transition-colors hover:border-primary hover:text-primary"
                  onClick={() => setCmd(it.cmd)}
                >
                  {it.cmd}
                </button>
              ))}
            </div>
          </div>
        ))}

        <div className="flex flex-col gap-2">
          <label className="text-xs font-semibold text-muted-foreground">命令</label>
          <div className="flex items-center gap-2">
            <input
              value={cmd}
              onChange={(e) => setCmd(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !running) void run()
              }}
              placeholder='如 daren-list --limit 5  或  用上方命令按钮填充，点上方命令可带参'
              className="mono h-9 flex-1 rounded-md border border-input bg-background px-3 text-xs outline-none focus:border-primary"
              spellCheck={false}
            />
            <Button size="sm" disabled={running || cmd.trim() === ''} onClick={() => void run()}>
              <Play className="size-3.5" />
              {running ? '运行中…' : '运行'}
            </Button>
          </div>
          <p className="text-[11px] text-muted-foreground">
            路径请用正斜杠；多账号加 <code className="mono">--account 店铺名</code>；登录态在{' '}
            <code className="mono">agents/wxshop-cli/.wxshop/</code>，过期先跑 <code className="mono">login</code>
          </p>
        </div>

        {running && (
          <div className="text-xs text-muted-foreground">
            正在运行… 长命令(如 daren-scan 爬取)可能需要数十秒
          </div>
        )}

        {result && (
          <div
            className={cn(
              'flex flex-col gap-1.5 overflow-hidden rounded-md border',
              result.ok
                ? 'border-green-300 bg-green-50'
                : result.error
                  ? 'border-red-300 bg-red-50'
                  : 'border-amber-300 bg-amber-50'
            )}
          >
            <div className="flex items-center gap-2 border-b border-current/10 px-3 py-1.5 text-xs">
              <span
                className={cn(
                  'font-semibold',
                  result.ok ? 'text-green-800' : result.error ? 'text-red-800' : 'text-amber-800'
                )}
              >
                {result.ok ? '成功' : result.error ? '出错' : '失败'}
              </span>
              {result.exit_code !== null && (
                <span className="font-mono text-muted-foreground">exit {result.exit_code}</span>
              )}
            </div>
            {result.error && (
              <pre className="max-h-64 overflow-auto whitespace-pre-wrap px-3 pb-2 text-xs text-red-800">
                {result.error}
              </pre>
            )}
            {result.stdout && (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap px-3 pb-2 font-mono text-[11px] text-foreground">
                {pretty(result.stdout)}
              </pre>
            )}
            {result.stderr && (
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap px-3 pb-2 font-mono text-[11px] text-amber-800">
                {result.stderr}
              </pre>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

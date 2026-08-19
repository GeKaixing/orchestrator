import { useEffect, useState } from 'react'
import {
  Bot,
  Download,
  Loader2,
  Package,
  RefreshCw,
  SlidersHorizontal,
  Trash2
} from 'lucide-react'
import { api } from '../api'
import type { AgentStoreItem, Settings, UpdateCheck } from '../types'
import { Badge } from '@/components/ui/badge'
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
  all: '全流程',
  scan: '仅扫描',
  add: '仅加好友',
  send: '仅发送',
  im: 'IM 招商',
  invite: 'IM邀约复邀'
}

type SectionKey = 'general' | 'agents' | 'download' | 'update'

const SECTIONS: { key: SectionKey; label: string; icon: typeof Bot }[] = [
  { key: 'general', label: '默认设置', icon: SlidersHorizontal },
  { key: 'agents', label: '子 Agent 配置', icon: Bot },
  { key: 'download', label: '子 Agent 下载', icon: Package },
  { key: 'update', label: '版本与更新', icon: RefreshCw }
]

interface Props {
  settings: Settings
  onSaved: (s: Settings) => void
}

export default function SettingsView({ settings, onSaved }: Props): JSX.Element {
  const [form, setForm] = useState<Settings>(settings)
  const [msg, setMsg] = useState('')
  const [store, setStore] = useState<AgentStoreItem[]>([])
  const [busyKey, setBusyKey] = useState<string | null>(null)
  const [storeMsg, setStoreMsg] = useState('')
  const [refreshingStore, setRefreshingStore] = useState(false)
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null)
  const [update, setUpdate] = useState<UpdateCheck | null>(null)
  const [updateMsg, setUpdateMsg] = useState('')
  const [checking, setChecking] = useState(false)
  const [agentConfigs, setAgentConfigs] = useState<Record<string, { path: string; text: string }>>({})
  const [configMsg, setConfigMsg] = useState('')
  const [refreshingConfigs, setRefreshingConfigs] = useState(false)
  const [active, setActive] = useState<SectionKey>('general')

  const doCheck = async (force = false): Promise<void> => {
    setChecking(true)
    setUpdateMsg('')
    try {
      const r = await api<UpdateCheck>(force ? '/api/update-check?force=1' : '/api/update-check')
      setUpdate(r)
      setUpdateMsg(r.error || '')
    } catch (e) {
      setUpdateMsg(String(e))
    } finally {
      setChecking(false)
    }
  }

  useEffect(() => {
    void doCheck()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 仅挂载时用 settings 初始化; App 每 3s 轮询 settings 不应覆盖正在编辑的表单
  useEffect(() => {
    setForm(settings)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const loadStore = async (): Promise<void> => {
    try {
      setStore(await api<AgentStoreItem[]>('/api/agent-store'))
    } catch (e) {
      setStoreMsg(String(e))
    }
  }

  const refreshStore = async (): Promise<void> => {
    setRefreshingStore(true)
    try {
      await loadStore()
    } finally {
      setRefreshingStore(false)
    }
  }

  // 下载区与表单独立, 挂载时拉一次即可 (操作后有刷新按钮逻辑)
  useEffect(() => {
    void loadStore()
  }, [])
  const loadConfigs = async (): Promise<void> => {
    try {
      setAgentConfigs(await api<Record<string, { path: string; text: string }>>('/api/agent-configs'))
    } catch (e) {
      setConfigMsg(String(e))
    }
  }

  const refreshConfigs = async (): Promise<void> => {
    setRefreshingConfigs(true)
    try {
      await loadConfigs()
    } finally {
      setRefreshingConfigs(false)
    }
  }

  useEffect(() => { void loadConfigs() }, [])
  const saveAgentConfig = async (key: string): Promise<void> => {
    try { await api(`/api/agent-configs/${key}`, { method: 'PUT', body: { text: agentConfigs[key]?.text || '' } }); setConfigMsg(`${key} 配置已保存`) } catch (e) { setConfigMsg(String(e)) }
  }

  const storeAct = async (key: string, action: 'install' | 'update' | 'remove'): Promise<void> => {
    setBusyKey(`${key}:${action}`)
    setStoreMsg('')
    try {
      await api(`/api/agent-store/${key}/${action}`, { method: 'POST' })
      await loadStore()
    } catch (e) {
      setStoreMsg(String(e))
    } finally {
      setBusyKey(null)
      setConfirmRemove(null)
    }
  }

  const set = <K extends keyof Settings>(key: K, value: Settings[K]): void =>
    setForm((f) => ({ ...f, [key]: value }))

  const save = async (): Promise<void> => {
    setMsg('')
    const clean: Settings = {
      stage: form.stage,
      limit: Number(form.limit) || 10,
      max_pages: Number(form.max_pages) || 1,
      cat: form.cat.trim(),
      contacts: form.contacts.trim(),
      text: form.text.trim()
    }
    try {
      await api('/api/settings', { method: 'PUT', body: clean })
      onSaved(clean)
      setMsg('已保存')
    } catch (e) {
      setMsg(String(e))
    }
  }

  return (
    <Card className="h-full gap-0 overflow-hidden py-0">
      <CardContent className="flex h-full min-h-0 p-0">
        {/* 左侧分区导航 */}
        <nav className="flex w-[200px] shrink-0 flex-col gap-1 border-r border-border p-3">
          {SECTIONS.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.key}
                type="button"
                onClick={() => setActive(s.key)}
                className={cn(
                  'flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-[13px] transition-colors',
                  active === s.key
                    ? 'bg-secondary font-semibold text-primary'
                    : 'text-muted-foreground hover:bg-secondary/50'
                )}
              >
                <Icon className="size-4 shrink-0" />
                <span className="truncate">{s.label}</span>
              </button>
            )
          })}
        </nav>

        {/* 右侧内容面板 */}
        <div className="min-w-0 flex-1 overflow-auto p-5">
          {active === 'general' && (
            <div className="flex max-w-[560px] flex-col gap-4">
              <h2 className="text-[15px] font-semibold">
                客户端默认设置（保存后「工作流」自动预填）
              </h2>

              <div className="flex flex-col gap-2">
                <Label>默认阶段</Label>
                <Select value={form.stage} onValueChange={(v) => set('stage', v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STAGES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {STAGE_NAME[s]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="flex flex-col gap-2">
                  <Label>默认 limit</Label>
                  <Input type="number" value={form.limit} onChange={(e) => set('limit', Number(e.target.value))} />
                </div>
                <div className="flex flex-col gap-2">
                  <Label>默认 max-pages</Label>
                  <Input type="number" value={form.max_pages} onChange={(e) => set('max_pages', Number(e.target.value))} />
                </div>
              </div>

              <div className="flex flex-col gap-2">
                <Label>默认类目 cat</Label>
                <Input value={form.cat} onChange={(e) => set('cat', e.target.value)} />
              </div>

              <div className="flex flex-col gap-2">
                <Label>默认 contacts 文件</Label>
                <Input value={form.contacts} onChange={(e) => set('contacts', e.target.value)} />
              </div>

              <div className="flex flex-col gap-2">
                <Label>招商文案 (多行 = 多条消息, invite 用前 5 条)</Label>
                <Textarea
                  value={form.text}
                  onChange={(e) => set('text', e.target.value)}
                  rows={8}
                  className="resize-y"
                />
              </div>

              <div className="flex items-center gap-3">
                <Button onClick={() => void save()}>保存设置</Button>
                {msg && <span className="text-xs text-primary">{msg}</span>}
              </div>
            </div>
          )}

          {active === 'agents' && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-[15px] font-semibold">子 Agent 配置</h2>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={refreshingConfigs}
                  onClick={() => void refreshConfigs()}
                >
                  {refreshingConfigs ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3.5" />
                  )}
                  刷新
                </Button>
              </div>
              {Object.entries(agentConfigs).map(([key, cfg]) => (
                <div key={key} className="flex flex-col gap-2 rounded-md border border-border p-3">
                  <div className="flex items-center justify-between"><Label>{key}</Label><Button size="sm" onClick={() => void saveAgentConfig(key)} disabled={key === 'rag'}>保存</Button></div>
                  <div className="text-[11px] text-muted-foreground">{cfg.path}</div>
                  <Textarea value={cfg.text} onChange={(e) => setAgentConfigs((s) => ({ ...s, [key]: { ...cfg, text: e.target.value } }))} rows={4} className="font-mono text-xs" />
                </div>
              ))}
              {configMsg && <span className="text-xs text-muted-foreground">{configMsg}</span>}
            </div>
          )}

          {active === 'download' && (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <h2 className="text-[15px] font-semibold">子 Agent 下载</h2>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={refreshingStore}
                  onClick={() => void refreshStore()}
                >
                  {refreshingStore ? (
                    <Loader2 className="size-3.5 animate-spin" />
                  ) : (
                    <RefreshCw className="size-3.5" />
                  )}
                  刷新
                </Button>
              </div>
              <p className="-mt-1 text-xs text-muted-foreground">
                未安装的依赖项目（微信 / 微信小店）可一键克隆到 agents/ 目录
              </p>

              <div className="flex flex-col gap-2">
                {store.map((a) => {
                  const busy = busyKey !== null
                  const installing = busyKey === `${a.key}:install`
                  const updating = busyKey === `${a.key}:update`
                  const removing = busyKey === `${a.key}:remove`
                  const isConfirming = confirmRemove === a.key
                  return (
                    <div
                      key={a.key}
                      className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
                    >
                      <div className="flex min-w-0 flex-col gap-1">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-semibold">{a.name}</span>
                          {a.installed ? (
                            a.git ? (
                              <Badge variant={a.ready ? 'outline' : 'destructive'}>
                                {a.ready ? '已安装' : '需安装依赖'}{a.branch ? ` · ${a.branch}` : ''}
                                {a.head ? ` @${a.head}` : ''}
                              </Badge>
                            ) : (
                              <Badge variant="destructive">已存在（非 git）</Badge>
                            )
                          ) : (
                            <Badge variant="secondary">未安装</Badge>
                          )}
                        </div>
                        <div className="text-xs text-muted-foreground">{a.description}</div>
                        <div className="mono text-[11px] text-muted-foreground">{a.repo}</div>
                      </div>

                      <div className="flex shrink-0 items-center gap-1.5">
                        {!a.installed && (
                          <Button size="sm" disabled={busy} onClick={() => void storeAct(a.key, 'install')}>
                            {installing ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
                            {installing ? '下载中' : '下载'}
                          </Button>
                        )}
                        {a.installed && a.git && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={busy}
                            onClick={() => void storeAct(a.key, 'update')}
                          >
                            {updating ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
                            {updating ? '处理中' : a.ready ? '更新' : '安装依赖'}
                          </Button>
                        )}
                        {a.installed && (
                          <Button
                            size="sm"
                            variant={isConfirming ? 'destructive' : 'ghost'}
                            disabled={busy}
                            onClick={() => {
                              if (isConfirming) void storeAct(a.key, 'remove')
                              else setConfirmRemove(a.key)
                            }}
                          >
                            {removing ? <Loader2 className="size-3.5 animate-spin" /> : <Trash2 className="size-3.5" />}
                            {removing ? '移除中' : isConfirming ? '确认移除?' : '移除'}
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
                {store.length === 0 && !storeMsg && (
                  <div className="text-xs text-muted-foreground">加载中…</div>
                )}
              </div>

              {storeMsg && <span className="text-xs text-destructive">{storeMsg}</span>}
            </div>
          )}

          {active === 'update' && (
            <div className="flex max-w-[560px] flex-col gap-3">
              <h2 className="text-[15px] font-semibold">版本与更新</h2>
              <div className="flex items-center justify-between gap-3 rounded-md border border-border p-3">
                <div className="flex min-w-0 flex-col gap-1">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="shrink-0">当前版本</span>
                    <span className="mono text-xs text-muted-foreground">
                      {update ? `v${update.current_version}` : '…'}
                    </span>
                    {update?.has_update && <Badge variant="outline">有新版本</Badge>}
                  </div>
                  {update?.has_update && (
                    <div className="text-xs text-muted-foreground">
                      发现新版本 v{update.latest_version}（来自 GitHub Releases）
                    </div>
                  )}
                  {update && !update.has_update && !update.error && (
                    <div className="text-xs text-muted-foreground">已是最新版本</div>
                  )}
                  {updateMsg && <span className="text-xs text-destructive">{updateMsg}</span>}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {update?.has_update && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void window.api.openExternal(update.release_url)}
                    >
                      <Download className="size-3.5" />
                      去下载
                    </Button>
                  )}
                  <Button size="sm" disabled={checking} onClick={() => void doCheck(true)}>
                    {checking ? (
                      <Loader2 className="size-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="size-3.5" />
                    )}
                    检查更新
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

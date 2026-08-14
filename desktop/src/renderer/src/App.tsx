import { useEffect, useState } from 'react'
import {
  BookOpen,
  BrainCircuit,
  Database,
  Download,
  FileText,
  LayoutDashboard,
  ListChecks,
  MessageCircle,
  PlayCircle,
  Settings as SettingsIcon,
  Store,
  X
} from 'lucide-react'
import { api } from './api'
import { usePolling } from './usePolling'
import type { Run, Settings, UpdateCheck } from './types'
import { Button } from '@/components/ui/button'
import { TooltipProvider } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import Controls from './components/Controls'
import Dashboard from './components/Dashboard'
import Data from './components/Data'
import Followup from './components/Followup'
import LogPane from './components/LogPane'
import Rag from './components/Rag'
import Report from './components/Report'
import SettingsView from './components/Settings'
import Shop from './components/Shop'
import WechatAgent from './components/WechatAgent'
import Wiki from './components/Wiki'

const NAV = [
  { key: 'dashboard', label: '监控面板', icon: LayoutDashboard },
  { key: 'followup', label: '跟进表', icon: ListChecks },
  { key: 'controls', label: '任务控制', icon: PlayCircle },
  { key: 'rag', label: 'RAG', icon: BrainCircuit },
  { key: 'wiki', label: '知识库', icon: BookOpen },
  { key: 'wechat', label: '微信', icon: MessageCircle },
  { key: 'shop', label: '微信小店', icon: Store },
  { key: 'report', label: '报告', icon: FileText },
  { key: 'data', label: '数据', icon: Database },
  { key: 'settings', label: '设置', icon: SettingsIcon }
]

function toSettings(s: Record<string, string>): Settings {
  return {
    stage: s.stage || 'all',
    limit: Number(s.limit) || 10,
    max_pages: Number(s.max_pages) || 1,
    cat: s.cat || '',
    contacts: s.contacts || '',
    text: s.text || ''
  }
}

export default function App(): JSX.Element {
  const [nav, setNav] = useState('dashboard')
  const [run, setRun] = useState<Run | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [logCollapsed, setLogCollapsed] = useState(false)
  const [update, setUpdate] = useState<UpdateCheck | null>(null)
  const [updateDismissed, setUpdateDismissed] = useState(false)

  useEffect(() => {
    void api<UpdateCheck>('/api/update-check')
      .then(setUpdate)
      .catch(() => {})
  }, [])

  usePolling(() => {
    void api<Run[]>('/api/runs?limit=1')
      .then((list) => {
        if (list.length > 0) setRun(list[0])
      })
      .catch(() => {})
    void api<Record<string, string>>('/api/settings')
      .then((s) => setSettings(toSettings(s)))
      .catch(() => {})
  }, 3000, true)

  return (
    <TooltipProvider>
      <div
        className={cn(
          'grid h-screen grid-cols-[208px_minmax(0,1fr)] bg-background text-foreground',
          logCollapsed ? 'grid-rows-[minmax(0,1fr)_auto]' : 'grid-rows-[minmax(0,1fr)_220px]'
        )}
      >
        <aside className="col-start-1 row-span-2 flex flex-col gap-1 border-r border-border bg-sidebar p-3">
          <div className="flex items-center gap-2 px-2 pb-3">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-sm font-bold text-primary-foreground">
              达
            </span>
            <h1 className="text-[15px] font-semibold text-primary">达人招商编排</h1>
          </div>
          {NAV.map((n) => {
            const Icon = n.icon
            return (
              <Button
                key={n.key}
                variant={nav === n.key ? 'secondary' : 'ghost'}
                className={cn(
                  'w-full justify-start gap-2 text-[13px]',
                  nav === n.key && 'font-semibold text-primary'
                )}
                onClick={() => setNav(n.key)}
              >
                <Icon className="size-4" />
                {n.label}
              </Button>
            )
          })}
          <div className="mt-auto flex items-center gap-2 px-2 py-2 text-xs text-muted-foreground">
            <span className={cn('size-2 rounded-full', dotColor(run))} />
            <span className="truncate">{sidebarStatus(run)}</span>
          </div>
        </aside>
        <main className="col-start-2 row-start-1 min-w-0 overflow-auto p-4">
          {update?.has_update && !updateDismissed && (
            <div className="mb-3 flex items-center justify-between gap-3 rounded-md border border-primary/40 bg-primary/10 px-3 py-2">
              <div className="flex min-w-0 items-center gap-2 text-[13px]">
                <span className="shrink-0 font-semibold text-primary">
                  发现新版本 v{update.latest_version}
                </span>
                <span className="truncate text-muted-foreground">
                  当前 v{update.current_version}，建议更新
                </span>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button size="sm" onClick={() => void window.api.openExternal(update.release_url)}>
                  <Download className="size-3.5" />
                  查看更新
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label="关闭"
                  onClick={() => setUpdateDismissed(true)}
                >
                  <X className="size-3.5" />
                </Button>
              </div>
            </div>
          )}
          {nav === 'dashboard' && <Dashboard />}
          {nav === 'followup' && <Followup />}
          {nav === 'controls' && settings && (
            <Controls run={run} settings={settings} onRunStarted={(r) => setRun(r)} />
          )}
          {nav === 'rag' && <Rag />}
          {nav === 'wiki' && <Wiki />}
          {nav === 'wechat' && <WechatAgent />}
          {nav === 'shop' && <Shop />}
          {nav === 'report' && <Report />}
          {nav === 'data' && <Data />}
          {nav === 'settings' && settings && (
            <SettingsView settings={settings} onSaved={setSettings} />
          )}
        </main>
        <div className="col-start-2 row-start-2 min-h-0">
          <LogPane run={run} collapsed={logCollapsed} onToggle={() => setLogCollapsed((c) => !c)} />
        </div>
      </div>
    </TooltipProvider>
  )
}

function dotColor(run: Run | null): string {
  if (!run) return 'bg-muted-foreground/60'
  if (run.status === 'running') return 'bg-green-500'
  if (run.status === 'stopping') return 'bg-yellow-500'
  if (run.status === 'failed') return 'bg-red-500'
  return 'bg-muted-foreground/60'
}

function sidebarStatus(run: Run | null): string {
  if (!run) return '空闲'
  if (run.status === 'running') return `运行中 #${run.id}`
  if (run.status === 'stopping') return '停止中…'
  if (run.status === 'finished') return '空闲 (上次完成)'
  if (run.status === 'failed') return `失败 #${run.id}`
  if (run.status === 'stopped') return `已停止 #${run.id}`
  return '空闲'
}

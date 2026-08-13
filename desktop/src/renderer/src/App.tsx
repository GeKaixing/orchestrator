import { useState } from 'react'
import { api } from './api'
import { usePolling } from './usePolling'
import type { Run, Settings } from './types'
import Controls from './components/Controls'
import Dashboard from './components/Dashboard'
import Data from './components/Data'
import Followup from './components/Followup'
import LogPane from './components/LogPane'
import Report from './components/Report'
import SettingsView from './components/Settings'

const NAV = [
  { key: 'dashboard', label: '监控面板' },
  { key: 'followup', label: '跟进表' },
  { key: 'controls', label: '任务控制' },
  { key: 'report', label: '报告' },
  { key: 'data', label: '数据' },
  { key: 'settings', label: '设置' }
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
    <div className="app">
      <aside className="sidebar">
        <h1 className="brand">达人招商编排</h1>
        {NAV.map((n) => (
          <button
            key={n.key}
            className={`nav-btn ${nav === n.key ? 'active' : ''}`}
            onClick={() => setNav(n.key)}
          >
            {n.label}
          </button>
        ))}
        <div className="run-badge">
          <span className={`dot ${run?.status === 'running' ? 'green' : ''}`}>●</span>
          <span>{sidebarStatus(run)}</span>
        </div>
      </aside>
      <main className="content">
        {nav === 'dashboard' && <Dashboard />}
        {nav === 'followup' && <Followup />}
        {nav === 'controls' && settings && (
          <Controls run={run} settings={settings} onRunStarted={(r) => setRun(r)} />
        )}
        {nav === 'report' && <Report />}
        {nav === 'data' && <Data />}
        {nav === 'settings' && settings && <SettingsView settings={settings} onSaved={setSettings} />}
      </main>
      <LogPane run={run} />
    </div>
  )
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

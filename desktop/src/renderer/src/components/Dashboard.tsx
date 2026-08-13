import { useCallback, useState } from 'react'
import { api } from '../api'
import { usePolling } from '../usePolling'
import AgentsPanel from './AgentsPanel'
import type { Daren, Preflight, Stats } from '../types'

const STAGES = ['pending', 'added', 'sent', 'im_sent', 'failed']
const STAGE_LABEL: Record<string, string> = {
  pending: '待处理',
  added: '已加好友',
  sent: '已发文案',
  im_sent: 'IM已发',
  failed: '失败'
}
const STAGE_COLOR: Record<string, string> = {
  pending: '#9aa0a6',
  added: '#7c9ff2',
  sent: '#3ddc84',
  im_sent: '#2ec5c5',
  failed: '#ff6b6b'
}

const CARD_DEFS: { key: keyof Stats; label: string; color: string }[] = [
  { key: 'total', label: '达人总数', color: '#4aa3ff' },
  { key: 'pending', label: '待处理', color: '#9aa0a6' },
  { key: 'added', label: '已加好友', color: '#7c9ff2' },
  { key: 'sent', label: '已发文案', color: '#3ddc84' },
  { key: 'im_sent', label: 'IM已发', color: '#2ec5c5' },
  { key: 'failed', label: '失败', color: '#ff6b6b' }
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
    <div className="view">
      <div className="cards">
        {CARD_DEFS.map((c) => (
          <div key={c.key} className="card">
            <div className="card-label">{c.label}</div>
            <div className="card-value" style={{ color: c.color }}>
              {String(s[c.key] ?? 0)}
            </div>
          </div>
        ))}
      </div>

      <AgentsPanel />

      <div className="toolbar">
        <span className="muted">环境自检:</span>
        <button className="btn ghost" onClick={() => void runPreflight()}>
          检查微信 / wxshop / rag
        </button>
        {preflight && (
          <span className="muted">
            微信 {preflight.wechat ? '✅' : '❌'} · wxshop {preflight.wxshop ? '✅' : '❌'} · rag {preflight.rag ? '✅' : '❌'}
          </span>
        )}
        <span className="spacer" />
        <label className="muted">
          阶段:
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option>全部</option>
            {STAGES.map((st) => (
              <option key={st} value={st}>
                {STAGE_LABEL[st]}
              </option>
            ))}
          </select>
        </label>
        <label className="muted">
          <input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> 自动刷新
        </label>
        <button className="btn ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>

      <div className="table-wrap">
        <table className="daren-table">
          <thead>
            <tr>
              <th>微信号</th>
              <th>昵称</th>
              <th>阶段</th>
              <th>更新时间</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {darens.length === 0 && (
              <tr>
                <td colSpan={5} className="empty">
                  (暂无数据)
                </td>
              </tr>
            )}
            {darens.map((d) => (
              <tr key={d.wxid}>
                <td className="mono">{d.wxid}</td>
                <td>{d.nickname}</td>
                <td>
                  <span className="stage-chip" style={{ color: STAGE_COLOR[d.stage] ?? '#9aa0a6' }}>
                    {STAGE_LABEL[d.stage] ?? d.stage}
                  </span>
                </td>
                <td className="muted">{d.updated}</td>
                <td className="muted">{d.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

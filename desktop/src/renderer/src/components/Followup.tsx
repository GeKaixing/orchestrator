import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { FollowupData, FollowupRow } from '../types'

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
  已加好友: '#3ddc84',
  已邀约: '#2ec5c5',
  'IM邀约中': '#7c9ff2',
  添加失败: '#ff6b6b'
}

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
  const statusKeys = ['', ...Object.keys(stats).sort()]
  const rows = data?.rows ?? []

  return (
    <div className="view">
      <div className="toolbar">
        <input
          className="search"
          placeholder="搜索昵称 / 微信号 / 手机号…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          {statusKeys.map((s) => (
            <option key={s} value={s}>
              {s === '' ? '全部状态' : `${s} (${stats[s]})`}
            </option>
          ))}
        </select>
        <span className="muted">共 {data?.total ?? 0} 位 · 显示 {rows.length}</span>
        <span className="spacer" />
        <button className="btn ghost" disabled={busy} onClick={() => void load()}>
          刷新
        </button>
      </div>
      <div className="table-wrap">
        <table className="daren-table">
          <thead>
            <tr>
              {COLS.map((c) => (
                <th key={c.key}>{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLS.length} className="empty">
                  (暂无匹配)
                </td>
              </tr>
            )}
            {rows.map((r, i) => (
              <tr key={`${r.达人昵称}-${i}`}>
                {COLS.map((c) => {
                  const v = r[c.key]
                  if (c.key === '跟进状态' && v) {
                    return (
                      <td key={c.key}>
                        <span className="stage-chip" style={{ color: STATUS_COLOR[v] ?? '#9aa0a6' }}>
                          {v}
                        </span>
                      </td>
                    )
                  }
                  return <td key={c.key} className={c.mono ? 'mono' : ''}>{fmt(v)}</td>
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(2)
  return String(v)
}

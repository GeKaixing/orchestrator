import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Settings } from '../types'

const STAGES = ['all', 'scan', 'add', 'send', 'im']
const STAGE_NAME: Record<string, string> = {
  all: '全流程',
  scan: '仅扫描',
  add: '仅加好友',
  send: '仅发送',
  im: 'IM 招商'
}

interface Props {
  settings: Settings
  onSaved: (s: Settings) => void
}

export default function SettingsView({ settings, onSaved }: Props): JSX.Element {
  const [form, setForm] = useState<Settings>(settings)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    setForm(settings)
  }, [settings])

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
    <div className="view settings">
      <h2 className="section-title">客户端默认设置（保存后「任务控制」自动预填）</h2>

      <label className="field">
        <span>默认阶段</span>
        <select value={form.stage} onChange={(e) => set('stage', e.target.value)}>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {s} — {STAGE_NAME[s]}
            </option>
          ))}
        </select>
      </label>

      <div className="field-row">
        <label className="field">
          <span>默认 limit</span>
          <input type="number" value={form.limit} onChange={(e) => set('limit', Number(e.target.value))} />
        </label>
        <label className="field">
          <span>默认 max-pages</span>
          <input type="number" value={form.max_pages} onChange={(e) => set('max_pages', Number(e.target.value))} />
        </label>
      </div>

      <label className="field">
        <span>默认类目 cat</span>
        <input value={form.cat} onChange={(e) => set('cat', e.target.value)} />
      </label>

      <label className="field">
        <span>默认 contacts 文件</span>
        <input value={form.contacts} onChange={(e) => set('contacts', e.target.value)} />
      </label>

      <label className="field">
        <span>招商文案 (RECRUIT_TEXT)</span>
        <textarea value={form.text} onChange={(e) => set('text', e.target.value)} rows={8} />
      </label>

      <div className="settings-actions">
        <button className="btn primary" onClick={() => void save()}>
          保存设置
        </button>
        {msg && <span className="msg">{msg}</span>}
      </div>
    </div>
  )
}

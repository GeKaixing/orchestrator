import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Run, Settings } from '../types'

const STAGES = ['all', 'scan', 'add', 'send', 'im', 'invite']
const STAGE_NAME: Record<string, string> = {
  all: '全流程 (扫描→加好友→发送)',
  scan: '仅扫描提取联系方式',
  add: '仅加好友',
  send: '仅发送招商文案',
  im: '小店官方 IM 招商',
  invite: 'IM 5条邀约 → 微信复邀'
}

interface Props {
  run: Run | null
  settings: Settings
  onRunStarted: (run: Run) => void
}

export default function Controls({ run, settings, onRunStarted }: Props): JSX.Element {
  const [form, setForm] = useState<Settings>(settings)
  const [msg, setMsg] = useState('')

  // 仅挂载时用 settings 初始化; App 每 3s 轮询 settings 会传新对象,
  // 若依赖 settings 会把用户正在编辑的 stage/文案重置回默认值
  useEffect(() => {
    setForm(settings)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const set = <K extends keyof Settings>(key: K, value: Settings[K]): void =>
    setForm((f) => ({ ...f, [key]: value }))

  const start = async (): Promise<void> => {
    setMsg('')
    const stage = form.stage
    const text = form.text.trim()
    if (['all', 'send', 'im', 'invite'].includes(stage) && !text) {
      setMsg('该阶段需要招商文案: 请在下方填写或到「设置」保存')
      return
    }
    try {
      const run = await api<Run>('/api/runs', {
        method: 'POST',
        body: {
          type: 'recruit',
          stage,
          limit: Number(form.limit) || 10,
          max_pages: Number(form.max_pages) || 1,
          cat: form.cat.trim(),
          contacts: form.contacts.trim(),
          text
        }
      })
      onRunStarted(run)
      setMsg(`已启动任务 #${run.id} (${stage})`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const reply = async (): Promise<void> => {
    setMsg('')
    try {
      const run = await api<Run>('/api/runs', { method: 'POST', body: { type: 'reply' } })
      onRunStarted(run)
      setMsg(`已启动自动回复一轮 #${run.id}`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const stop = async (): Promise<void> => {
    if (!run) return
    try {
      await api(`/api/runs/${run.id}/stop`, { method: 'POST' })
      setMsg(`已请求停止任务 #${run.id}`)
    } catch (e) {
      setMsg(String(e))
    }
  }

  const running = !!run && ['pending', 'running', 'stopping'].includes(run.status)

  return (
    <div className="view controls">
      <div className="controls-form">
        <h2 className="section-title">任务参数</h2>

        <label className="field">
          <span>阶段</span>
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
            <span>本轮处理数 limit</span>
            <input
              type="number"
              value={form.limit}
              onChange={(e) => set('limit', Number(e.target.value))}
            />
          </label>
          <label className="field">
            <span>扫描页数 max-pages</span>
            <input
              type="number"
              value={form.max_pages}
              onChange={(e) => set('max_pages', Number(e.target.value))}
            />
          </label>
        </div>

        <label className="field">
          <span>达人类目 cat（可空）</span>
          <input value={form.cat} onChange={(e) => set('cat', e.target.value)} />
        </label>

        <label className="field">
          <span>现成 contacts 文件（可空）</span>
          <input value={form.contacts} onChange={(e) => set('contacts', e.target.value)} />
        </label>

        <label className="field">
          <span>招商文案</span>
          <textarea value={form.text} onChange={(e) => set('text', e.target.value)} rows={8} />
        </label>
      </div>

      <div className="controls-actions">
        <button className="btn primary" disabled={running} onClick={() => void start()}>
          启动任务
        </button>
        <button className="btn danger" disabled={!running} onClick={() => void stop()}>
          停止任务
        </button>
        <button className="btn teal" disabled={running} onClick={() => void reply()}>
          自动回复一轮 (IM)
        </button>

        <div className="run-status">
          <span className={`dot ${run && run.status === 'running' ? 'green' : ''}`}>●</span>
          <span>{runStatusText(run)}</span>
        </div>
        {msg && <div className="msg">{msg}</div>}
        <p className="hint">
          all/send/im/invite 需填写招商文案; scan 只扫描提取联系方式。文案多行 = 多条消息 (invite 用前 5 条)。启动后任务在后台子进程运行，可在「日志」查看输出。
        </p>
      </div>
    </div>
  )
}

function runStatusText(run: Run | null): string {
  if (!run) return '空闲'
  if (run.status === 'running') return `运行中 #${run.id} (${run.stage})`
  if (run.status === 'stopping') return `停止中 #${run.id}`
  if (run.status === 'finished') return `空闲 (#${run.id} 已完成)`
  if (run.status === 'failed') return `失败 #${run.id} (退出码 ${run.exit_code})`
  if (run.status === 'stopped') return `已停止 #${run.id}`
  return `空闲`
}

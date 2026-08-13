import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import type { FilePayload } from '../types'

const FILES = ['contacts', 'talents', 'state']

export default function Data(): JSX.Element {
  const [name, setName] = useState('contacts')
  const [data, setData] = useState<FilePayload | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await api<FilePayload>(`/api/files?name=${name}`))
    } catch (e) {
      setData({ name, count: 0, text: String(e) })
    }
  }, [name])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="view">
      <div className="toolbar">
        <label className="muted">
          文件:
          <select value={name} onChange={(e) => setName(e.target.value)}>
            {FILES.map((f) => (
              <option key={f} value={f}>
                {f}.jsonl
              </option>
            ))}
          </select>
        </label>
        {data && <span className="muted">{data.count} 条记录</span>}
        <span className="spacer" />
        <button className="btn ghost" onClick={() => void load()}>
          刷新
        </button>
      </div>
      <pre className="data-box">{data?.text ?? '(加载中…)'}</pre>
    </div>
  )
}

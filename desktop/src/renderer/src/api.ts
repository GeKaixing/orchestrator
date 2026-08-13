const BASE = 'http://127.0.0.1:8765'

export async function api<T = unknown>(
  path: string,
  options?: { method?: string; body?: unknown }
): Promise<T> {
  const res = await fetch(BASE + path, {
    method: options?.method ?? 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: options?.body !== undefined ? JSON.stringify(options.body) : undefined
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => '')
    throw new Error(`${path} -> HTTP ${res.status} ${detail.slice(0, 200)}`)
  }
  return (await res.json()) as T
}

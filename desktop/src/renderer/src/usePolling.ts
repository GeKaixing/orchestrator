import { useEffect, useRef } from 'react'

/** 轮询: active 时立即执行一次, 然后按 intervalMs 周期性执行. */
export function usePolling(fn: () => void, intervalMs: number, active: boolean): void {
  const saved = useRef(fn)
  saved.current = fn
  useEffect(() => {
    if (!active) return
    saved.current()
    const id = setInterval(() => saved.current(), intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, active])
}

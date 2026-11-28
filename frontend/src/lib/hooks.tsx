import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { getAuth, getCached, pendingActions, replayQueue, type Auth } from '../api/client'
import type { Config } from '../api/types'

// ------------------------------------------------------------------ data loading
export interface Loaded<T> {
  data: T | null
  error: string | null
  loading: boolean
  savedAt: string | null // when showing an offline copy
  reload: () => void
}

/** Load a GET endpoint, with the offline copy as a fallback. `path = null` skips loading. */
export function useLoad<T>(path: string | null): Loaded<T> {
  const [state, setState] = useState<Omit<Loaded<T>, 'reload'>>({
    data: null,
    error: null,
    loading: !!path,
    savedAt: null,
  })
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!path) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    getCached<T>(path)
      .then((r) => alive && setState({ data: r.data, savedAt: r.savedAt, error: null, loading: false }))
      .catch((e) => alive && setState((s) => ({ ...s, error: errorText(e), loading: false })))
    return () => {
      alive = false
    }
  }, [path, tick])
  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { ...state, reload }
}

export function errorText(e: unknown): string {
  if (e instanceof TypeError) return 'No connection to the server. Check your network and try again.'
  return e instanceof Error ? e.message : String(e)
}

// ------------------------------------------------------------------ config (days, slots, app name)
const ConfigContext = createContext<Loaded<Config> | null>(null)

export function ConfigProvider({ children }: { children: ReactNode }) {
  const cfg = useLoad<Config>('/public/config')
  useEffect(() => {
    if (cfg.data?.app_name) document.title = cfg.data.app_name
  }, [cfg.data?.app_name])
  return <ConfigContext.Provider value={cfg}>{children}</ConfigContext.Provider>
}

export function useConfig() {
  const ctx = useContext(ConfigContext)
  if (!ctx) throw new Error('ConfigProvider missing')
  return ctx
}

// ------------------------------------------------------------------ auth
export function useAuth(): Auth | null {
  const [auth, set] = useState(getAuth)
  useEffect(() => {
    const on = () => set(getAuth())
    window.addEventListener('auth-changed', on)
    window.addEventListener('storage', on)
    return () => {
      window.removeEventListener('auth-changed', on)
      window.removeEventListener('storage', on)
    }
  }, [])
  return auth
}

// ------------------------------------------------------------------ toasts
interface Toast {
  id: number
  text: string
  bad?: boolean
}
const ToastContext = createContext<(text: string, bad?: boolean) => void>(() => {})

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const next = useRef(1)
  const push = useCallback((text: string, bad = false) => {
    const id = next.current++
    setToasts((t) => [...t, { id, text, bad }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), bad ? 7000 : 4500)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={'toast' + (t.bad ? ' bad' : '')}>
            <span>{t.text}</span>
            <button
              className="btn btn-ghost btn-sm"
              style={{ color: 'inherit', minHeight: 0, padding: 0 }}
              onClick={() => setToasts((all) => all.filter((x) => x.id !== t.id))}
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export const useToast = () => useContext(ToastContext)

// ------------------------------------------------------------------ connection + offline queue
/** Online status, number of queued actions, and automatic replay when the signal returns. */
export function useNetwork() {
  const toast = useToast()
  const [online, setOnline] = useState(navigator.onLine)
  const [pending, setPending] = useState(pendingActions().length)
  useEffect(() => {
    const sync = () => setPending(pendingActions().length)
    const replay = async () => {
      const results = await replayQueue()
      for (const r of results) toast(r.ok ? `Sent: ${r.action.label}` : `${r.action.label}: ${r.message}`, !r.ok)
      if (results.length) window.dispatchEvent(new Event('data-changed'))
    }
    const goOnline = () => {
      setOnline(true)
      replay()
    }
    const goOffline = () => setOnline(false)
    window.addEventListener('online', goOnline)
    window.addEventListener('offline', goOffline)
    window.addEventListener('queue-changed', sync)
    if (navigator.onLine && pendingActions().length) replay()
    const timer = setInterval(() => {
      if (navigator.onLine && pendingActions().length) replay()
    }, 20000)
    return () => {
      window.removeEventListener('online', goOnline)
      window.removeEventListener('offline', goOffline)
      window.removeEventListener('queue-changed', sync)
      clearInterval(timer)
    }
  }, [toast])
  return { online, pending }
}

/** Re-run `fn` when queued actions were replayed (so lists refresh). */
export function useOnDataChanged(fn: () => void) {
  useEffect(() => {
    window.addEventListener('data-changed', fn)
    return () => window.removeEventListener('data-changed', fn)
  }, [fn])
}

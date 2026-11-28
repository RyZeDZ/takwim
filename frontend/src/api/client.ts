// The only place that talks to the backend.
//  - GET responses are cached in localStorage, so the last timetable stays visible offline.
//  - Professor actions (absence, extra session) made offline are queued and replayed when the
//    connection returns. The backend endpoints are idempotent, so a replay never duplicates.

export const API_URL = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

const TOKEN_KEY = 'auth'
const CACHE_PREFIX = 'cache:'
const QUEUE_KEY = 'pending-actions'

export type Role = 'admin' | 'prof'
export interface Auth {
  token: string
  role: Role
  username: string
  professor_id: number | null
}

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : detailMessage(detail) || `Error ${status}`)
    this.status = status
    this.detail = detail
  }
}

function detailMessage(detail: unknown): string {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{loc, msg}]
    return detail.map((d) => (d && typeof d === 'object' && 'msg' in d ? String(d.msg) : String(d))).join('; ')
  }
  if (typeof detail === 'object' && 'message' in detail) {
    const d = detail as { message: string; errors?: string[] }
    return d.errors?.length ? `${d.message}: ${d.errors.join('; ')}` : d.message
  }
  return ''
}

// ------------------------------------------------------------------ auth
export function getAuth(): Auth | null {
  try {
    return JSON.parse(localStorage.getItem(TOKEN_KEY) || 'null')
  } catch {
    return null
  }
}

export function setAuth(auth: Auth | null) {
  if (auth) localStorage.setItem(TOKEN_KEY, JSON.stringify(auth))
  else localStorage.removeItem(TOKEN_KEY)
  window.dispatchEvent(new Event('auth-changed'))
}

// ------------------------------------------------------------------ requests
type Body = object | FormData | undefined

async function request<T>(method: string, path: string, body?: Body): Promise<T> {
  const headers: Record<string, string> = {}
  const auth = getAuth()
  if (auth) headers.Authorization = `Bearer ${auth.token}`
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  const res = await fetch(API_URL + path, { method, headers, body: payload })
  if (res.status === 401 && auth) {
    setAuth(null) // the login expired: log in again
  }
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    data = text
  }
  if (!res.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? (data as { detail: unknown }).detail : data
    throw new ApiError(res.status, detail)
  }
  return data as T
}

/** True when the request failed because there is no connection (not because the server said no). */
export function isNetworkError(e: unknown) {
  return e instanceof TypeError || (e instanceof Error && e.name === 'TypeError')
}

export interface Cached<T> {
  data: T
  savedAt: string | null // set when the data comes from the offline cache
}

/** GET with an offline fallback: returns the last saved copy when the network is down. */
export async function getCached<T>(path: string): Promise<Cached<T>> {
  const key = CACHE_PREFIX + (getAuth()?.username ?? 'public') + ':' + path
  try {
    const data = await request<T>('GET', path)
    try {
      localStorage.setItem(key, JSON.stringify({ data, at: new Date().toISOString() }))
    } catch {
      /* storage full: the app still works online */
    }
    return { data, savedAt: null }
  } catch (e) {
    const saved = localStorage.getItem(key)
    if (isNetworkError(e) && saved) {
      const { data, at } = JSON.parse(saved)
      return { data, savedAt: at }
    }
    throw e
  }
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: Body) => request<T>('POST', path, body),
  put: <T>(path: string, body?: Body) => request<T>('PUT', path, body),
  patch: <T>(path: string, body?: Body) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

// ------------------------------------------------------------------ offline queue
export interface QueuedAction {
  id: string
  method: 'POST' | 'DELETE'
  path: string
  body?: Record<string, unknown>
  label: string // shown to the user, e.g. "Absence: Algorithms 1, Sun 30 Nov"
  queuedAt: string
}

export interface ReplayResult {
  action: QueuedAction
  ok: boolean
  message: string
}

export function pendingActions(): QueuedAction[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveQueue(q: QueuedAction[]) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify(q))
  window.dispatchEvent(new Event('queue-changed'))
}

/**
 * Send a professor action now, or queue it if there is no connection.
 * Returns {queued: true} when it was saved for later.
 */
export async function sendOrQueue<T>(
  method: 'POST' | 'DELETE',
  path: string,
  body: Record<string, unknown> | undefined,
  label: string,
): Promise<{ queued: true } | { queued: false; data: T }> {
  try {
    const data = await request<T>(method, path, body)
    return { queued: false, data }
  } catch (e) {
    if (!isNetworkError(e)) throw e
    const q = pendingActions()
    q.push({ id: crypto.randomUUID(), method, path, body, label, queuedAt: new Date().toISOString() })
    saveQueue(q)
    return { queued: true }
  }
}

let replaying = false

/** Replay queued actions in order. Stops at the first network failure (still offline). */
export async function replayQueue(): Promise<ReplayResult[]> {
  if (replaying) return []
  replaying = true
  const results: ReplayResult[] = []
  try {
    let q = pendingActions()
    while (q.length) {
      const action = q[0]
      try {
        await request(action.method, action.path, action.body)
        results.push({ action, ok: true, message: 'sent' })
      } catch (e) {
        if (isNetworkError(e)) break
        results.push({ action, ok: false, message: e instanceof Error ? e.message : 'refused' })
      }
      q = pendingActions().filter((a) => a.id !== action.id)
      saveQueue(q)
    }
  } finally {
    replaying = false
  }
  return results
}

// ------------------------------------------------------------------ files
export function exportUrl(format: 'pdf' | 'excel', scope: 'group' | 'prof' | 'room', ids?: number[]) {
  const q = new URLSearchParams({ scope })
  if (ids?.length) q.set('ids', ids.join(','))
  return `${API_URL}/export/${format}?${q}`
}

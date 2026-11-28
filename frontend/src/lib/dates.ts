// Dates travel as "YYYY-MM-DD" strings (the backend's format). Computed in UTC so that
// adding days never shifts because of the browser's timezone.
import { locale, t } from './i18n'

export function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function shortDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString(locale(), { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

export function longDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString(locale(), { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

export function weekLabel(dates: string[]): string {
  if (!dates.length) return ''
  return `${shortDate(dates[0])} – ${shortDate(dates[dates.length - 1])}`
}

export function timeAgo(isoDateTime: string): string {
  const mins = Math.round((Date.now() - new Date(isoDateTime).getTime()) / 60000)
  if (mins < 1) return t('just now')
  if (mins < 60) return t('{n} min ago', { n: mins })
  const h = Math.round(mins / 60)
  if (h < 48) return t('{n} h ago', { n: h })
  return t('{n} days ago', { n: Math.round(h / 24) })
}

/** "08:00-09:30" -> "08:00" */
export const slotStart = (slot: string) => slot.split('-')[0]

/** "08:00" -> minutes since midnight */
export const minutes = (hhmm: string) => Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3, 5))

/** Minutes since midnight now, on this device. */
export function nowMinutes(): number {
  const d = new Date()
  return d.getHours() * 60 + d.getMinutes()
}

/** "in 25 min", "in 1 h 10" */
export function inTime(mins: number): string {
  if (mins < 60) return t('in {n} min', { n: mins })
  const h = Math.floor(mins / 60)
  const m = mins % 60
  return m ? t('in {h} h {m}', { h, m: String(m).padStart(2, '0') }) : t('in {h} h', { h })
}

/** Keep a time or a range left-to-right inside Arabic text ("08:00-09:30", not "09:30-08:00"). */
export const ltr = (s: string) => `\u2066${s}\u2069`

/** Backend day names ("Sunday") in the interface language. */
export const dayName = (d: string) => t(d)

export const KIND_LABEL: Record<string, string> = { lecture: 'Lecture', td: 'TD', tp: 'TP', extra: 'Extra' }
export const kindLabel = (k: string) => t(KIND_LABEL[k] ?? k)

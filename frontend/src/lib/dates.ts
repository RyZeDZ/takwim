// Dates travel as "YYYY-MM-DD" strings (the backend's format). Computed in UTC so that
// adding days never shifts because of the browser's timezone.

export function addDays(iso: string, n: number): string {
  const d = new Date(iso + 'T00:00:00Z')
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function shortDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

export function longDate(iso: string): string {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

export function weekLabel(dates: string[]): string {
  if (!dates.length) return ''
  return `${shortDate(dates[0])} – ${shortDate(dates[dates.length - 1])}`
}

export function timeAgo(isoDateTime: string): string {
  const mins = Math.round((Date.now() - new Date(isoDateTime).getTime()) / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins} min ago`
  const h = Math.round(mins / 60)
  if (h < 48) return `${h} h ago`
  return `${Math.round(h / 24)} days ago`
}

/** "08:00-09:30" -> "08:00" */
export const slotStart = (slot: string) => slot.split('-')[0]

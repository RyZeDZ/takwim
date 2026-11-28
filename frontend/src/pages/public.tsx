import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, exportUrl, setAuth, type Auth } from '../api/client'
import type { FreeRoom, GroupNode, LevelGroups, Week } from '../api/types'
import { PageHead } from '../components/Layout'
import { Dialog, Empty, ErrorBox, GridSkeleton, Icon, ListSkeleton, SavedCopyNote } from '../components/ui'
import { TodayCard, WeekGrid, WeekNav } from '../components/WeekGrid'
import { dayName, longDate, ltr, minutes, nowMinutes } from '../lib/dates'
import { errorText, useConfig, useLoad } from '../lib/hooks'
import { t } from '../lib/i18n'

const MY_GROUP = 'my-group'

export const ROOM_TYPE: Record<string, string> = { amphi: 'Lecture hall', td: 'Classroom', lab: 'Computer lab' }
export const roomType = (type: string) => t(ROOM_TYPE[type] ?? type)

// ------------------------------------------------------------------ pick a group
export function Home() {
  const groups = useLoad<LevelGroups[]>('/public/groups')
  const cfg = useConfig()
  const [query, setQuery] = useState('')
  const mine = (() => {
    try {
      return JSON.parse(localStorage.getItem(MY_GROUP) || 'null') as { id: number; name: string } | null
    } catch {
      return null
    }
  })()
  useEffect(() => {
    document.title = t(cfg.data?.app_name ?? 'Timetables')
  }, [cfg.data?.app_name])

  const q = query.trim().toLowerCase()
  const levels = (groups.data ?? [])
    .map((lv) => ({
      ...lv,
      sections: lv.sections
        .map((sec) => ({ sec, list: flatGroups(sec).filter((g) => !q || `${lv.level} ${g.name}`.toLowerCase().includes(q)) }))
        .filter((x) => x.list.length),
    }))
    .filter((lv) => lv.sections.length)

  return (
    <>
      <div className="hero">
        <span className="hero-kicker">{t('For students, no account needed')}</span>
        <h1>{t('Your class timetable, always up to date')}</h1>
        <p>
          {t(
            "Pick your group to see this week's classes. Cancelled classes and new sessions show up as soon as a professor declares them, and the last timetable you opened stays available without a connection.",
          )}
        </p>
        <div className="row">
          {mine && (
            <Link to={`/g/${mine.id}`} className="btn btn-primary btn-lg">
              <Icon name="calendar" /> {t('Open {group}', { group: mine.name })}
            </Link>
          )}
          <Link to="/free-rooms" className="btn btn-lg">
            <Icon name="door" /> {t('Find a free room')}
          </Link>
        </div>
      </div>
      <SavedCopyNote savedAt={groups.savedAt} />
      {groups.error && <ErrorBox error={groups.error} onRetry={groups.reload} />}
      {groups.data && groups.data.length === 0 && (
        <Empty icon="calendar" title={t('No timetable published yet')}>
          <p>{t("The department hasn't generated this semester's timetable. Check again soon.")}</p>
        </Empty>
      )}
      {(groups.loading || !!groups.data?.length) && (
        <div className="search-box">
          <Icon name="search" />
          <input
            className="input"
            type="search"
            placeholder={t('Find your group, e.g. L2 G3')}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label={t('Find your group')}
          />
        </div>
      )}
      {groups.loading && !groups.data && (
        <div className="levels">
          {[0, 1, 2].map((i) => (
            <div key={i} className="panel">
              <ListSkeleton rows={3} />
            </div>
          ))}
        </div>
      )}
      {groups.data && q && levels.length === 0 && <p className="muted">{t('No group matches "{q}".', { q: query })}</p>}
      <div className="levels">
        {levels.map((lv) => (
          <section key={lv.level} className="panel level-card" aria-label={lv.level}>
            <h2>{lv.level}</h2>
            <div className="stack-sm">
              {lv.sections.map(({ sec, list }) => (
                <div key={sec.id} className="stack-sm" style={{ gap: 8 }}>
                  {lv.sections.length > 1 && <span className="small muted">{sec.name}</span>}
                  <div className="group-links">
                    {list.map((g) => (
                      <Link
                        key={g.id}
                        to={`/g/${g.id}`}
                        className={'group-link' + (g.kind === 'section' ? ' section' : '') + (mine?.id === g.id ? ' mine' : '')}
                        title={t('{group} · {n} students', { group: g.name, n: g.size })}
                      >
                        {g.kind === 'section' ? t('Whole section') : shortName(g.name)}
                      </Link>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
      {cfg.data && (
        <p className="small muted" style={{ marginTop: 32 }}>
          {t('Week: {days} · {n} time slots from {start} to {end}', {
            days: cfg.data.days.map(dayName).join(', '),
            n: cfg.data.slots.length,
            start: ltr(cfg.data.slots[0]?.split('-')[0] ?? ''),
            end: ltr(cfg.data.slots[cfg.data.slots.length - 1]?.split('-')[1] ?? ''),
          })}
        </p>
      )}
    </>
  )
}

function flatGroups(node: GroupNode): GroupNode[] {
  const out: GroupNode[] = []
  const walk = (n: GroupNode) => {
    if (n.kind !== 'section') out.push(n)
    n.children.forEach(walk)
  }
  walk(node)
  return out.length ? out : [node]
}

/** "L1 CS - G3" -> "G3" (the level is already the card title). */
const shortName = (name: string) => name.split(' - ').slice(1).join(' - ') || name

// ------------------------------------------------------------------ a group's week
export function GroupWeek() {
  const { id } = useParams()
  const cfg = useConfig()
  const [params, setParams] = useSearchParams()
  const date = params.get('date') || cfg.data?.display_date || cfg.data?.today || ''
  const week = useLoad<Week>(date ? `/public/groups/${id}/week?date=${date}` : null)
  const groups = useLoad<LevelGroups[]>('/public/groups')
  const [share, setShare] = useState(false)
  const [copied, setCopied] = useState(false)

  const name = findGroupName(groups.data, Number(id))
  useEffect(() => {
    if (name) localStorage.setItem(MY_GROUP, JSON.stringify({ id: Number(id), name }))
  }, [id, name])
  const url = window.location.origin + `/g/${id}`
  const changes = week.data?.entries.filter((e) => e.status !== 'normal') ?? []
  const cancelled = changes.filter((c) => c.status === 'cancelled').length
  const added = changes.filter((c) => c.status === 'new').length

  const shareNow = async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: name ?? t('Group timetable'), text: t('Our timetable, always up to date'), url })
        return
      } catch {
        /* closed, or not allowed: show the QR code instead */
      }
    }
    setShare(true)
  }

  return (
    <div className="stack">
      <PageHead title={name ?? t('Group timetable')} intro={t("This week's classes. Cancelled classes and new sessions are marked as soon as they are declared.")}>
        <a className="btn" href={exportUrl('pdf', 'group', [Number(id)])} download>
          <Icon name="download" /> PDF
        </a>
        <a className="btn" href={exportUrl('excel', 'group', [Number(id)])} download>
          <Icon name="download" /> Excel
        </a>
        <button className="btn btn-primary" onClick={shareNow}>
          <Icon name="share" /> {t('Share')}
        </button>
      </PageHead>
      <SavedCopyNote savedAt={week.savedAt} />
      {week.data && cfg.data && <TodayCard week={week.data} today={cfg.data.today} />}
      <div className="row-between">
        <WeekNav week={week.data} date={date} thisWeek={cfg.data?.display_date ?? cfg.data?.today ?? ''} onChange={(d) => setParams({ date: d })} />
        {changes.length > 0 && (
          <span className="row small">
            {cancelled > 0 && <span className="badge badge-cancelled">{t('{n} cancelled', { n: cancelled })}</span>}
            {added > 0 && <span className="badge badge-new">{t('{n} new', { n: added })}</span>}
            <span className="muted">{t('this week')}</span>
          </span>
        )}
      </div>
      {week.error && <ErrorBox error={week.error} onRetry={week.reload} />}
      {week.loading && !week.data && <GridSkeleton days={cfg.data?.days.length} slots={cfg.data?.slots.length} />}
      {week.data && week.data.entries.length === 0 && (
        <Empty icon="calendar" title={t('No classes this week')}>
          <p>{t('Try the next week, or check again later.')}</p>
        </Empty>
      )}
      {week.data && cfg.data && week.data.entries.length > 0 && <WeekGrid week={week.data} today={cfg.data.today} show={['professor', 'room']} />}
      <Dialog open={share} onClose={() => setShare(false)} title={t('Share this timetable')}>
        <p className="muted">{t('Students scan this code or open the link. No account needed.')}</p>
        <QRCodeSVG value={url} size={200} className="qr" />
        <div className="row">
          <input className="input" readOnly value={url} style={{ flex: 1 }} onFocus={(e) => e.target.select()} />
          <button className="btn" onClick={() => navigator.clipboard?.writeText(url).then(() => setCopied(true))}>
            <Icon name={copied ? 'check' : 'share'} /> {copied ? t('Copied') : t('Copy')}
          </button>
        </div>
      </Dialog>
    </div>
  )
}

function findGroupName(levels: LevelGroups[] | null, id: number): string | null {
  const walk = (n: GroupNode): string | null => (n.id === id ? n.name : n.children.map(walk).find(Boolean) ?? null)
  for (const lv of levels ?? [])
    for (const s of lv.sections) {
      const hit = walk(s)
      if (hit) return hit
    }
  return null
}

// ------------------------------------------------------------------ free rooms (to study in)
/** The slot happening now, or the next one today (0 before the first, the last after the end). */
function currentSlot(slots: string[]): number {
  const now = nowMinutes()
  const i = slots.findIndex((s) => now < minutes(s.split('-')[1] ?? '00:00'))
  return i === -1 ? Math.max(0, slots.length - 1) : i
}

export function FreeRooms() {
  const cfg = useConfig()
  const [date, setDate] = useState('')
  const [slot, setSlot] = useState<number | null>(null)
  const d = date || cfg.data?.today || ''
  const s = slot ?? (cfg.data ? currentSlot(cfg.data.slots) : 0)
  const rooms = useLoad<FreeRoom[]>(d && cfg.data ? `/public/free-rooms?date=${d}&slot=${s}` : null)
  const freed = rooms.data?.filter((r) => r.freed_by_absence).length ?? 0

  return (
    <div className="stack">
      <PageHead title={t('Free rooms')} intro={t('Rooms with no class at a given time: useful to study, or to find a room for a meeting.')} />
      <div className="panel form-grid">
        <label className="field">
          {t('Date')}
          <input className="input" type="date" value={d} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field">
          {t('Time')}
          <select className="select" value={s} onChange={(e) => setSlot(Number(e.target.value))}>
            {cfg.data?.slots.map((sl, i) => (
              <option key={sl} value={i}>
                {sl}
              </option>
            ))}
          </select>
        </label>
      </div>
      {rooms.error && <ErrorBox error={rooms.error} onRetry={rooms.reload} />}
      {rooms.loading && (
        <div className="panel">
          <ListSkeleton />
        </div>
      )}
      {rooms.data && !rooms.loading && (
        <div className="panel panel-tight">
          <div className="panel-head">
            <h2>{t('{n} free room(s)', { n: rooms.data.length })}</h2>
            <span className="small muted">
              {longDate(d)} · {ltr(cfg.data?.slots[s] ?? '')}
              {freed > 0 && ` · ${t('{n} freed by an absence', { n: freed })}`}
            </span>
          </div>
          {rooms.data.length === 0 ? (
            <p className="muted small" style={{ padding: '0 24px 20px' }}>
              {t('Every room is taken at that time. Try another slot.')}
            </p>
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Room')}</th>
                    <th>{t('Type')}</th>
                    <th>{t('Seats')}</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {rooms.data.map((r) => (
                    <tr key={r.id}>
                      <td>
                        <strong>{r.name}</strong>
                      </td>
                      <td>{roomType(r.type)}</td>
                      <td className="num">{r.capacity}</td>
                      <td>{r.freed_by_absence && <span className="badge badge-freed">{t('Freed by an absence')}</span>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ login
export function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    document.title = t('Staff login')
  }, [])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const auth = await api.post<Auth>('/auth/login', { username: username.trim(), password })
      setAuth(auth)
      navigate(auth.role === 'admin' ? '/admin' : '/prof')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="panel login-card stack" onSubmit={submit}>
      <div className="stack-sm">
        <h1>{t('Staff login')}</h1>
        <p className="muted small">{t("For professors and the department's administration. Students don't need an account.")}</p>
      </div>
      <label className="field">
        {t('Username')}
        <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
      </label>
      <label className="field">
        {t('Password')}
        <span className="input-with-btn">
          <input
            className="input"
            type={show ? 'text' : 'password'}
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <button type="button" className="btn btn-ghost icon-btn" onClick={() => setShow(!show)} aria-label={show ? t('Hide password') : t('Show password')} aria-pressed={show}>
            <Icon name="eye" />
          </button>
        </span>
      </label>
      {error && <ErrorBox error={error} />}
      <button className="btn btn-primary btn-lg" disabled={busy}>
        {busy ? <span className="spinner" /> : null} {t('Log in')}
      </button>
      <p className="tiny muted">{t('Professors get their login from the department. Lost it? The administrator can reset it.')}</p>
    </form>
  )
}

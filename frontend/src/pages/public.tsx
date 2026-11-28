import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { QRCodeSVG } from 'qrcode.react'
import { api, exportUrl, setAuth, type Auth } from '../api/client'
import type { FreeRoom, GroupNode, LevelGroups, Week } from '../api/types'
import { PageHead } from '../components/Layout'
import { Dialog, ErrorBox, Icon, Loading, SavedCopyNote } from '../components/ui'
import { WeekGrid, WeekNav } from '../components/WeekGrid'
import { longDate } from '../lib/dates'
import { errorText, useConfig, useLoad } from '../lib/hooks'

const MY_GROUP = 'my-group'

// ------------------------------------------------------------------ pick a group
export function Home() {
  const groups = useLoad<LevelGroups[]>('/public/groups')
  const cfg = useConfig()
  const mine = (() => {
    try {
      return JSON.parse(localStorage.getItem(MY_GROUP) || 'null') as { id: number; name: string } | null
    } catch {
      return null
    }
  })()

  return (
    <>
      <div className="hero">
        <h1>Your class timetable, always up to date</h1>
        <p>
          Pick your group to see this week's classes. Cancelled classes and new sessions show up as soon as a
          professor declares them, and the last timetable you opened stays available without a connection.
        </p>
        {mine && (
          <Link to={`/g/${mine.id}`} className="btn btn-primary btn-lg" style={{ alignSelf: 'start' }}>
            <Icon name="calendar" /> Open {mine.name}
          </Link>
        )}
      </div>
      <SavedCopyNote savedAt={groups.savedAt} />
      {groups.loading && !groups.data && <Loading />}
      {groups.error && <ErrorBox error={groups.error} onRetry={groups.reload} />}
      {groups.data && groups.data.length === 0 && (
        <div className="panel empty">
          <h2>No timetable published yet</h2>
          <p>The department hasn't generated this semester's timetable. Check again soon.</p>
        </div>
      )}
      <div className="levels">
        {groups.data?.map((lv) => (
          <section key={lv.level} className="panel level-card" aria-label={lv.level}>
            <h2>{lv.level}</h2>
            <div className="stack-sm">
              {lv.sections.map((sec) => (
                <div key={sec.id} className="stack-sm" style={{ gap: 8 }}>
                  {lv.sections.length > 1 && <span className="small muted">{sec.name}</span>}
                  <div className="group-links">
                    {flatGroups(sec).map((g) => (
                      <Link
                        key={g.id}
                        to={`/g/${g.id}`}
                        className={'group-link' + (g.kind === 'section' ? ' section' : '')}
                        title={`${g.name} · ${g.size} students`}
                      >
                        {g.kind === 'section' ? 'Whole section' : shortName(g.name)}
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
          Week: {cfg.data.days.join(', ')} · {cfg.data.slots.length} time slots from {cfg.data.slots[0]?.split('-')[0]} to{' '}
          {cfg.data.slots[cfg.data.slots.length - 1]?.split('-')[1]}
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

  const name = findGroupName(groups.data, Number(id))
  useEffect(() => {
    if (name) localStorage.setItem(MY_GROUP, JSON.stringify({ id: Number(id), name }))
  }, [id, name])
  const url = window.location.origin + `/g/${id}`
  const changes = week.data?.entries.filter((e) => e.status !== 'normal') ?? []

  return (
    <div className="stack">
      <PageHead title={name ?? 'Group timetable'} intro="This week's classes. Cancelled classes and new sessions are marked as soon as they are declared.">
        <a className="btn" href={exportUrl('pdf', 'group', [Number(id)])} download>
          <Icon name="download" /> PDF
        </a>
        <a className="btn" href={exportUrl('excel', 'group', [Number(id)])} download>
          <Icon name="download" /> Excel
        </a>
        <button className="btn" onClick={() => setShare(true)}>
          <Icon name="share" /> Share
        </button>
      </PageHead>
      <SavedCopyNote savedAt={week.savedAt} />
      <div className="row-between">
        <WeekNav week={week.data} date={date} thisWeek={cfg.data?.display_date ?? cfg.data?.today ?? ''} onChange={(d) => setParams({ date: d })} />
        {changes.length > 0 && (
          <span className="small muted">
            {changes.filter((c) => c.status === 'cancelled').length} cancelled ·{' '}
            {changes.filter((c) => c.status === 'new').length} new this week
          </span>
        )}
      </div>
      {week.error && <ErrorBox error={week.error} onRetry={week.reload} />}
      {week.loading && !week.data && <Loading />}
      {week.data && cfg.data && <WeekGrid week={week.data} today={cfg.data.today} show={['professor', 'room']} />}
      <Dialog open={share} onClose={() => setShare(false)} title="Share this timetable">
        <p className="muted">Students scan this code or open the link. No account needed.</p>
        <QRCodeSVG value={url} size={200} className="qr" />
        <div className="row">
          <input className="input" readOnly value={url} style={{ flex: 1 }} onFocus={(e) => e.target.select()} />
          <button className="btn" onClick={() => navigator.clipboard?.writeText(url)}>
            Copy
          </button>
        </div>
      </Dialog>
    </div>
  )
}

function findGroupName(levels: LevelGroups[] | null, id: number): string | null {
  const walk = (n: GroupNode): string | null => (n.id === id ? n.name : n.children.map(walk).find(Boolean) ?? null)
  for (const lv of levels ?? []) for (const s of lv.sections) {
    const hit = walk(s)
    if (hit) return hit
  }
  return null
}

// ------------------------------------------------------------------ free rooms (to study in)
export function FreeRooms() {
  const cfg = useConfig()
  const [date, setDate] = useState('')
  const [slot, setSlot] = useState(0)
  const d = date || cfg.data?.today || ''
  const rooms = useLoad<FreeRoom[]>(d ? `/public/free-rooms?date=${d}&slot=${slot}` : null)

  return (
    <div className="stack">
      <PageHead title="Free rooms" intro="Rooms with no class at a given time: useful to study, or to find a room for a meeting." />
      <div className="panel form-grid">
        <label className="field">
          Date
          <input className="input" type="date" value={d} onChange={(e) => setDate(e.target.value)} />
        </label>
        <label className="field">
          Time
          <select className="select" value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
            {cfg.data?.slots.map((s, i) => (
              <option key={s} value={i}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>
      {rooms.error && <ErrorBox error={rooms.error} onRetry={rooms.reload} />}
      {rooms.loading && <Loading />}
      {rooms.data && (
        <div className="panel panel-tight">
          <div className="panel-head">
            <h2>
              {rooms.data.length} free room{rooms.data.length === 1 ? '' : 's'}
            </h2>
            <span className="small muted">{longDate(d)}</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Room</th>
                  <th>Type</th>
                  <th>Seats</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {rooms.data.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <strong>{r.name}</strong>
                    </td>
                    <td>{ROOM_TYPE[r.type] ?? r.type}</td>
                    <td className="num">{r.capacity}</td>
                    <td>{r.freed_by_absence && <span className="badge badge-freed">Freed by an absence</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

export const ROOM_TYPE: Record<string, string> = { amphi: 'Lecture hall', td: 'Classroom', lab: 'Computer lab' }

// ------------------------------------------------------------------ login
export function Login() {
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

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
        <h1>Staff login</h1>
        <p className="muted small">For professors and the department's administration. Students don't need an account.</p>
      </div>
      <label className="field">
        Username
        <input className="input" autoComplete="username" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
      </label>
      <label className="field">
        Password
        <input
          className="input"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </label>
      {error && <ErrorBox error={error} />}
      <button className="btn btn-primary btn-lg" disabled={busy}>
        {busy ? <span className="spinner" /> : null} Log in
      </button>
      <p className="tiny muted">Professors get their login from the department. Lost it? The administrator can reset it.</p>
    </form>
  )
}

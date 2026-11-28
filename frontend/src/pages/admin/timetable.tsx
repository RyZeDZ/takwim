import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError, exportUrl } from '../../api/client'
import type { Credential, GenerateResult, LevelGroups, GroupNode, Professor, Room, Stats, Week, WeekEntry } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { CredentialsTable, Dialog, ErrorBox, Icon, Loading, Stat } from '../../components/ui'
import { WeekGrid, WeekNav } from '../../components/WeekGrid'
import { longDate, shortDate } from '../../lib/dates'
import { errorText, useConfig, useLoad, useToast } from '../../lib/hooks'

const LAST_RUN = 'last-generation'

function lastRun(): GenerateResult | null {
  try {
    return JSON.parse(localStorage.getItem(LAST_RUN) || 'null')
  } catch {
    return null
  }
}

// ------------------------------------------------------------------ the Generate button + its summary
export function GeneratePanel({ onDone }: { onDone?: () => void }) {
  const toast = useToast()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(lastRun)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await api.post<GenerateResult>('/admin/timetable/generate')
      setResult(r)
      localStorage.setItem(LAST_RUN, JSON.stringify(r))
      toast(r.saved ? `Timetable saved: ${r.placed} sessions, 0 clashes` : 'Not saved: see the problems below', !r.saved)
      onDone?.()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="panel stack-sm" aria-label="Generate the timetable">
      <div className="row-between">
        <div>
          <h2>Generate the timetable</h2>
          <p className="muted small" style={{ maxWidth: '60ch', marginTop: 4 }}>
            Builds the groups from headcounts and places every session with no clash. Running it again keeps sessions where
            they are and only moves what has to change.
          </p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={run} disabled={running}>
          {running ? <span className="spinner" /> : <Icon name="sparkle" />}
          {running ? 'Generating…' : 'Generate'}
        </button>
      </div>
      {running && (
        <div className="stack-sm" role="status">
          <div className="progress indeterminate">
            <div />
          </div>
          <span className="small muted">The solver is searching for the timetable with the fewest gaps. This takes a few seconds.</span>
        </div>
      )}
      {error && <ErrorBox error={error} />}
      {result && !running && <GenerateSummary r={result} />}
    </section>
  )
}

export function GenerateSummary({ r }: { r: GenerateResult }) {
  return (
    <div className="stack-sm">
      {r.saved ? (
        <div className="callout callout-ok">
          Saved. {r.placed} of {r.requirements} weekly sessions placed with 0 clashes in {r.seconds.toFixed(1)} s
          {r.sessions_moved != null && `, ${r.sessions_moved} session${r.sessions_moved === 1 ? '' : 's'} moved`}.
        </div>
      ) : (
        <div className="callout callout-bad">
          Not saved: the result breaks a rule, so the current timetable was kept.
          {r.conflicts.length > 0 && (
            <ul>
              {r.conflicts.slice(0, 8).map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      {r.warning && <div className="callout callout-warn">{r.warning}</div>}
      <div className="stats">
        <Stat label="Sessions placed" value={`${r.placed}/${r.requirements}`} />
        <Stat label="Clashes" value={r.conflicts.length} />
        <Stat label="Time" value={`${r.seconds.toFixed(1)} s`} note={r.solver === 'ai.solver' ? 'AI solver (CP-SAT)' : 'Built-in solver'} />
        <Stat label="Gaps per group" value={r.gaps_per_group_per_week ?? '–'} note="empty slots between classes, per week" />
        <Stat label="Sessions moved" value={r.sessions_moved ?? '–'} note="compared with the previous timetable" />
      </div>
      {r.groups_rebuilt_for.length > 0 && (
        <p className="small muted">Groups rebuilt for: {r.groups_rebuilt_for.join(', ')}.</p>
      )}
      {r.unscheduled.length > 0 && (
        <div className="callout callout-warn">
          <div>
            {r.unscheduled.length} session{r.unscheduled.length === 1 ? '' : 's'} could not be placed:
            <ul>
              {r.unscheduled.slice(0, 10).map((u) => (
                <li key={u.requirement_id}>
                  {u.module} ({u.kind.toUpperCase()}, {u.group}): {u.reason}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {r.absences_dropped.length > 0 && (
        <div className="callout callout-warn">
          <div>
            Absences that no longer match a session:
            <ul>
              {r.absences_dropped.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {r.claims_to_review.length > 0 && (
        <div className="callout callout-warn">
          <div>
            Extra sessions to review:
            <ul>
              {r.claims_to_review.map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ dashboard
export function Dashboard() {
  const stats = useLoad<Stats>('/admin/stats')
  const toast = useToast()
  const [creds, setCreds] = useState<Credential[] | null>(null)
  const [seeding, setSeeding] = useState(false)
  const s = stats.data
  const empty = s && s.levels === 0 && s.rooms_active === 0 && s.professors === 0

  const seed = async () => {
    setSeeding(true)
    try {
      const r = await api.post<{ credentials: Credential[]; professors: number }>('/admin/demo/seed')
      setCreds(r.credentials)
      toast(`Demo department loaded: ${r.professors} professors`)
      stats.reload()
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setSeeding(false)
    }
  }

  return (
    <div className="stack">
      <PageHead title="Dashboard" intro="The department at a glance." />
      {stats.loading && !s && <Loading />}
      {stats.error && <ErrorBox error={stats.error} onRetry={stats.reload} />}
      {empty && (
        <section className="panel empty">
          <h2>Start by adding the department's data</h2>
          <p style={{ maxWidth: '55ch' }}>
            Import the files you already have (levels with headcounts, rooms, modules, professors), in Excel, CSV or PDF.
            Or load a synthetic department to try everything out.
          </p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <Link to="/admin/import" className="btn btn-primary">
              <Icon name="upload" /> Import files
            </Link>
            <button className="btn" onClick={seed} disabled={seeding}>
              {seeding && <span className="spinner" />} Load demo department
            </button>
          </div>
        </section>
      )}
      {s && !empty && (
        <>
          <div className="stats">
            <Stat label="Sessions per week" value={s.sessions_per_week} />
            <Stat label="Levels" value={s.levels} note={`${s.modules} modules`} />
            <Stat label="Professors" value={s.professors} note={`${s.professors_with_availability} filled their availability`} />
            <Stat label="Rooms open" value={s.rooms_active} note={`${s.room_occupancy_percent}% occupied`} />
            <Stat label="Upcoming absences" value={s.upcoming_absences} note={`${s.absences} in total`} />
            <Stat label="Extra sessions" value={s.extra_sessions} note={`${s.freed_rooms_reused} in freed rooms`} />
          </div>
          <GeneratePanel onDone={stats.reload} />
        </>
      )}
      <Dialog open={!!creds} onClose={() => setCreds(null)} title="Professor logins" wide>
        {creds && <CredentialsTable rows={creds} />}
      </Dialog>
    </div>
  )
}

// ------------------------------------------------------------------ timetable views
type Scope = 'group' | 'prof' | 'room'

export function Timetable() {
  const cfg = useConfig()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const scope = (params.get('scope') as Scope) || 'group'
  const id = params.get('id') || ''
  const date = params.get('date') || cfg.data?.display_date || ''
  const groups = useLoad<LevelGroups[]>('/public/groups')
  const profs = useLoad<Professor[]>('/admin/professors')
  const rooms = useLoad<Room[]>('/admin/rooms')
  const week = useLoad<Week>(id && date ? `/admin/week?scope=${scope}&id=${id}&date=${date}` : null)
  const [picked, setPicked] = useState<WeekEntry | null>(null)
  const [check, setCheck] = useState<{ ok: boolean; conflicts: string[] } | null>(null)

  const choices = useMemo(() => {
    if (scope === 'prof') return (profs.data ?? []).map((p) => ({ id: p.id, name: p.name }))
    if (scope === 'room') return (rooms.data ?? []).map((r) => ({ id: r.id, name: r.name + (r.active ? '' : ' (closed)') }))
    const out: { id: number; name: string; section?: boolean }[] = []
    const walk = (n: GroupNode) => (
      out.push({ id: n.id, name: n.kind === 'section' ? `${n.name} (whole section)` : n.name, section: n.kind === 'section' }),
      n.children.forEach(walk)
    )
    groups.data?.forEach((lv) => lv.sections.forEach(walk))
    return out
  }, [scope, groups.data, profs.data, rooms.data])

  const set = (patch: Record<string, string>) => setParams({ scope, id, date, ...patch })
  useEffect(() => {
    const first = choices.find((c) => !('section' in c && c.section)) ?? choices[0]
    if (!id && first) setParams({ scope, id: String(first.id), date }, { replace: true })
  }, [id, choices, scope, date, setParams])

  const runCheck = async () => {
    try {
      setCheck(await api.get('/admin/timetable/check'))
    } catch (e) {
      toast(errorText(e), true)
    }
  }

  return (
    <div className="stack">
      <PageHead title="Timetable" intro="Generate, check and browse the timetable by group, professor or room.">
        <button className="btn" onClick={runCheck}>
          Check for clashes
        </button>
      </PageHead>
      <GeneratePanel onDone={() => week.reload()} />
      {check && (
        <div className={'callout ' + (check.ok ? 'callout-ok' : 'callout-bad')} role="status">
          {check.ok ? 'Checked: the saved timetable follows every rule (0 clashes).' : (
            <div>
              {check.conflicts.length} problem(s):
              <ul>
                {check.conflicts.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
      <section className="stack-sm">
        <div className="tabs" role="tablist">
          {(['group', 'prof', 'room'] as Scope[]).map((s) => (
            <button key={s} role="tab" aria-selected={scope === s} className={'tab' + (scope === s ? ' on' : '')} onClick={() => setParams({ scope: s, date })}>
              By {s === 'prof' ? 'professor' : s}
            </button>
          ))}
        </div>
        <div className="row-between">
          <div className="row">
            <select className="select" value={id} onChange={(e) => set({ id: e.target.value })} aria-label="Show the timetable of">
              {choices.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <WeekNav week={week.data} date={date} thisWeek={cfg.data?.display_date ?? ''} onChange={(d) => set({ date: d })} />
          </div>
          {id && (
            <div className="row">
              <a className="btn btn-sm" href={exportUrl('pdf', scope, [Number(id)])} download>
                <Icon name="download" /> PDF
              </a>
              <a className="btn btn-sm" href={exportUrl('excel', scope, [Number(id)])} download>
                <Icon name="download" /> Excel
              </a>
              <a className="btn btn-sm" href={exportUrl('excel', scope)} download>
                All {scope === 'prof' ? 'professors' : scope + 's'} (Excel)
              </a>
            </div>
          )}
        </div>
        {week.error && <ErrorBox error={week.error} onRetry={week.reload} />}
        {week.loading && !week.data && <Loading />}
        {choices.length === 0 && !groups.loading && <div className="callout callout-info">Nothing to show yet: generate the timetable first.</div>}
        {week.data && cfg.data && (
          <WeekGrid
            week={week.data}
            today={cfg.data.today}
            show={
              scope === 'group'
                ? choices.find((c) => String(c.id) === id && 'section' in c && c.section)
                  ? ['group', 'professor', 'room']
                  : ['professor', 'room']
                : scope === 'prof'
                  ? ['group', 'room']
                  : ['group', 'professor']
            }
            onEntry={(e) => e.session_id && setPicked(e)}
          />
        )}
      </section>
      <SessionDialog entry={picked} rooms={rooms.data ?? []} onClose={() => setPicked(null)} onChanged={() => week.reload()} />
    </div>
  )
}

/** Admin actions on one session: move it (re-checked by the server) or mark the professor absent that day. */
function SessionDialog({
  entry,
  rooms,
  onClose,
  onChanged,
}: {
  entry: WeekEntry | null
  rooms: Room[]
  onClose: () => void
  onChanged: () => void
}) {
  const cfg = useConfig()
  const toast = useToast()
  const [day, setDay] = useState(0)
  const [slot, setSlot] = useState(0)
  const [room, setRoom] = useState('')
  const [problems, setProblems] = useState<string[] | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!entry) return
    setDay(entry.day)
    setSlot(entry.slot)
    setRoom(String(rooms.find((r) => r.name === entry.room)?.id ?? ''))
    setProblems(null)
  }, [entry, rooms])

  if (!entry || !cfg.data) return <Dialog open={false} onClose={onClose} title="">{null}</Dialog>

  const move = async () => {
    setBusy(true)
    setProblems(null)
    try {
      await api.patch(`/admin/sessions/${entry.session_id}`, { day, slot, room_id: room ? Number(room) : undefined })
      toast('Session moved')
      onChanged()
      onClose()
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) {
        setProblems((e.detail as { conflicts: string[] }).conflicts ?? [e.message])
      } else toast(errorText(e), true)
    } finally {
      setBusy(false)
    }
  }

  const absent = async () => {
    setBusy(true)
    try {
      await api.post('/me/absences', { session_id: entry.session_id, date: entry.date })
      toast(`Marked absent on ${shortDate(entry.date)}: ${entry.room} is free for that slot`)
      onChanged()
      onClose()
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open onClose={onClose} title={entry.module}>
      <dl className="kbd-list">
        <dt>Group</dt>
        <dd>{entry.group}</dd>
        <dt>Professor</dt>
        <dd>{entry.professor}</dd>
        <dt>Now</dt>
        <dd>
          {cfg.data.days[entry.day]} {entry.time}, {entry.room}
        </dd>
      </dl>
      <div className="form-grid">
        <label className="field">
          Day
          <select className="select" value={day} onChange={(e) => setDay(Number(e.target.value))}>
            {cfg.data.days.map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Time
          <select className="select" value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
            {cfg.data.slots.map((s, i) => (
              <option key={s} value={i}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Room
          <select className="select" value={room} onChange={(e) => setRoom(e.target.value)}>
            {rooms.filter((r) => r.active).map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} ({r.capacity})
              </option>
            ))}
          </select>
        </label>
      </div>
      {problems && (
        <div className="callout callout-bad">
          <div>
            Refused, this move would create a clash:
            <ul>
              {problems.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        </div>
      )}
      <div className="row-between">
        {entry.status === 'normal' && entry.date >= cfg.data.today ? (
          <button className="btn btn-danger" onClick={absent} disabled={busy}>
            Professor absent on {longDate(entry.date)}
          </button>
        ) : (
          <span />
        )}
        <button className="btn btn-primary" onClick={move} disabled={busy}>
          Move session
        </button>
      </div>
    </Dialog>
  )
}

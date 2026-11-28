import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError, exportUrl } from '../../api/client'
import type { Change, Credential, Fix, GenerateResult, GroupNode, LevelGroups, Professor, Room, Stats, Week, WeekEntry } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { CredentialsTable, Dialog, Empty, ErrorBox, GridSkeleton, Icon, ListSkeleton, Progress, Stat, useElapsed } from '../../components/ui'
import { WeekGrid, WeekNav } from '../../components/WeekGrid'
import { dayName, kindLabel, longDate, ltr, shortDate } from '../../lib/dates'
import { errorText, useConfig, useLoad, useToast } from '../../lib/hooks'
import { t } from '../../lib/i18n'
import { roomType } from '../public'

const LAST_RUN = 'last-generation'

function lastRun(): GenerateResult | null {
  try {
    return JSON.parse(localStorage.getItem(LAST_RUN) || 'null')
  } catch {
    return null
  }
}

// ------------------------------------------------------------------ the Generate button + its summary
const GEN_STEPS = ['Building the groups', 'Placing every session', 'Checking every rule and saving']

export function GeneratePanel({ onDone }: { onDone?: () => void }) {
  const toast = useToast()
  const cfg = useConfig()
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<GenerateResult | null>(lastRun)
  const [error, setError] = useState<string | null>(null)
  const elapsed = useElapsed(running)
  // The solver searches for its time limit, then the result is checked and saved.
  const total = (cfg.data?.solver_seconds ?? 10) + 1
  const value = Math.min(0.97, elapsed / total)
  const step = elapsed < 0.4 ? 0 : elapsed < total - 0.8 ? 1 : 2

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await api.post<GenerateResult>('/admin/timetable/generate')
      setResult(r)
      localStorage.setItem(LAST_RUN, JSON.stringify(r))
      toast(r.saved ? t('Timetable saved: {n} sessions, 0 clashes', { n: r.placed }) : t('Not saved: see the problems below'), !r.saved)
      onDone?.()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setRunning(false)
    }
  }

  return (
    <section className="panel stack-sm generate" aria-label={t('Generate the timetable')}>
      <div className="row-between">
        <div>
          <h2>{t('Generate the timetable')}</h2>
          <p className="muted small" style={{ maxWidth: '60ch', marginTop: 4 }}>
            {t(
              'Builds the groups from headcounts and places every session with no clash. Running it again keeps sessions where they are and only moves what has to change.',
            )}
          </p>
        </div>
        <button className="btn btn-primary btn-lg" onClick={run} disabled={running}>
          {running ? <span className="spinner" /> : <Icon name="sparkle" />}
          {running ? t('Generating…') : t('Generate')}
        </button>
      </div>
      {running && (
        <Progress
          value={value}
          steps={GEN_STEPS.map((s) => t(s))}
          current={step}
          note={t('The AI solver tries thousands of timetables and keeps the one with the fewest gaps. About {n} seconds.', {
            n: Math.round(total),
          })}
        />
      )}
      {error && <ErrorBox error={error} />}
      {result && !running && <GenerateSummary r={result} />}
    </section>
  )
}

/** A suggested fix for a session that could not be placed. */
function fixText(f: Fix | undefined, kind: string, module: string): string {
  const types = (f?.types ?? []).map(roomType).join(' / ')
  switch (f?.code) {
    case 'no_teacher':
      return t('No professor teaches {module} ({kind}). Add it to a professor in Professors, with {kind} ticked.', { module, kind: kindLabel(kind) })
    case 'no_room_type':
      return t('There is no open room of type {types}. Reopen or add one in Rooms, or allow another room type in Settings.', { types })
    case 'room_too_small':
      return t(
        'The group has {size} students but the biggest open room of type {types} has {biggest} seats. Add or reopen a bigger room, allow another room type in Settings, or lower the group size in Settings.',
        { size: f.size ?? '', biggest: f.biggest ?? '', types },
      )
    case 'profs_full':
      return t('Every professor who teaches it has reached their weekly maximum ({names}). Raise one maximum in Professors, or add a professor.', {
        names: (f.professors ?? []).join(', '),
      })
    case 'no_common_time':
      return t(
        'No time left when the professor ({names}), the group and a suitable room are all free. Free some "can\'t" slots in their availability, open another room, or add a working day or a time slot in Settings.',
        { names: (f.professors ?? []).join(', ') },
      )
    default:
      return ''
  }
}

const REASON: Record<Change['reason'], { label: string; icon: string }> = {
  room_closed: { label: 'Room closed', icon: 'door' },
  slot_removed: { label: 'Time slot removed', icon: 'clock' },
  prof_unavailable: { label: 'Professor not available any more', icon: 'users' },
  knock_on: { label: 'Moved to make room for these changes', icon: 'arrow' },
}

/** Every moved session: from where, to where, and why. */
function ChangesList({ changes }: { changes: Change[] }) {
  const cfg = useConfig()
  const [all, setAll] = useState(false)
  const place = (p: Change['from']) =>
    `${dayName(cfg.data?.days[p.day] ?? '?')} ${ltr(cfg.data?.slots[p.slot]?.split('-')[0] ?? '')}, ${p.room}`
  const shown = all ? changes : changes.slice(0, 12)
  const byReason = (Object.keys(REASON) as Change['reason'][]).map((r) => ({ r, items: shown.filter((c) => c.reason === r) })).filter((x) => x.items.length)
  return (
    <details className="changes" open={changes.length <= 12}>
      <summary>
        <Icon name="history" /> {t('What changed: {n} session(s) moved', { n: changes.length })}
      </summary>
      <div className="stack-sm" style={{ marginTop: 12 }}>
        {byReason.map(({ r, items }) => (
          <div key={r} className="stack-sm" style={{ gap: 6 }}>
            <span className="change-reason">
              <Icon name={REASON[r].icon} size={16} /> {t(REASON[r].label)}
            </span>
            <ul className="change-list">
              {items.map((c, i) => (
                <li key={i}>
                  <strong>{c.module}</strong>{' '}
                  <span className="muted">
                    · {kindLabel(c.kind)} · {c.group}
                  </span>
                  <span className="change-move">
                    <span className="from">{place(c.from)}</span>
                    <Icon name="arrow" size={14} flip />
                    <span className="to">{place(c.to)}</span>
                    {c.from.professor !== c.to.professor && (
                      <span className="muted">
                        {' '}
                        · {c.from.professor} → {c.to.professor}
                      </span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
        {changes.length > 12 && (
          <button className="btn btn-sm" style={{ alignSelf: 'start' }} onClick={() => setAll(!all)}>
            {all ? t('Show less') : t('Show all {n}', { n: changes.length })}
          </button>
        )}
      </div>
    </details>
  )
}

export function GenerateSummary({ r }: { r: GenerateResult }) {
  return (
    <div className="stack-sm">
      {r.saved ? (
        <div className="callout callout-ok">
          <Icon name="check" />
          <span>
            {t('Saved. {placed} of {total} weekly sessions placed with 0 clashes in {s} s.', {
              placed: r.placed,
              total: r.requirements,
              s: r.seconds.toFixed(1),
            })}{' '}
            {r.sessions_moved != null && t('{n} session(s) moved.', { n: r.sessions_moved })}
          </span>
        </div>
      ) : (
        <div className="callout callout-bad">
          <Icon name="alert" />
          <div>
            {t('Not saved: the result breaks a rule, so the current timetable was kept.')}
            {r.conflicts.length > 0 && (
              <ul>
                {r.conflicts.slice(0, 8).map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {r.warning && <div className="callout callout-warn">{r.warning}</div>}
      <div className="stats">
        <Stat label={t('Sessions placed')} value={`${r.placed}/${r.requirements}`} />
        <Stat label={t('Clashes')} value={r.conflicts.length} />
        <Stat label={t('Time')} value={`${r.seconds.toFixed(1)} s`} note={r.solver === 'ai.solver' ? t('AI solver (CP-SAT)') : t('Built-in solver')} />
        <Stat label={t('Gaps per group')} value={r.gaps_per_group_per_week ?? '–'} note={t('empty slots between classes, per week')} />
        <Stat label={t('Sessions moved')} value={r.sessions_moved ?? '–'} note={t('compared with the previous timetable')} />
      </div>
      {r.changes && r.changes.length > 0 && <ChangesList changes={r.changes} />}
      {r.groups_rebuilt_for.length > 0 && <p className="small muted">{t('Groups rebuilt for: {list}.', { list: r.groups_rebuilt_for.join(', ') })}</p>}
      {r.unscheduled.length > 0 && (
        <div className="callout callout-warn">
          <Icon name="alert" />
          <div className="stack-sm" style={{ gap: 8 }}>
            <strong>{t('{n} session(s) could not be placed:', { n: r.unscheduled.length })}</strong>
            <ul className="fix-list">
              {r.unscheduled.slice(0, 10).map((u) => (
                <li key={u.requirement_id}>
                  <strong>
                    {u.module} ({kindLabel(u.kind)}, {u.group})
                  </strong>
                  {u.fix ? (
                    <span className="fix">
                      <Icon name="wand" size={14} /> {fixText(u.fix, u.kind, u.module)}
                    </span>
                  ) : (
                    <span>: {t(u.reason)}</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
      {r.absences_dropped.length > 0 && (
        <div className="callout callout-warn">
          <div>
            {t('Absences that no longer match a session:')}
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
            {t('Extra sessions to review:')}
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
      toast(t('Demo department loaded: {n} professors', { n: r.professors }))
      stats.reload()
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setSeeding(false)
    }
  }

  return (
    <div className="stack">
      <PageHead title={t('Dashboard')} intro={t('The department at a glance.')} />
      {stats.loading && !s && (
        <div className="stats">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="stat">
              <ListSkeleton rows={2} />
            </div>
          ))}
        </div>
      )}
      {stats.error && <ErrorBox error={stats.error} onRetry={stats.reload} />}
      {empty && (
        <Empty icon="upload" title={t("Start by adding the department's data")}>
          <p style={{ maxWidth: '55ch' }}>
            {t(
              'Import the files you already have (levels with headcounts, rooms, modules, professors), in Excel, CSV or PDF. Or load a synthetic department to try everything out.',
            )}
          </p>
          <div className="row" style={{ justifyContent: 'center' }}>
            <Link to="/admin/import" className="btn btn-primary">
              <Icon name="upload" /> {t('Import files')}
            </Link>
            <button className="btn" onClick={seed} disabled={seeding}>
              {seeding && <span className="spinner" />} {t('Load demo department')}
            </button>
          </div>
        </Empty>
      )}
      {s && !empty && (
        <>
          <div className="stats">
            <Stat label={t('Sessions per week')} value={s.sessions_per_week} />
            <Stat label={t('Levels')} value={s.levels} note={t('{n} modules', { n: s.modules })} />
            <Stat label={t('Professors')} value={s.professors} note={t('{n} filled their availability', { n: s.professors_with_availability })} />
            <Stat label={t('Rooms open')} value={s.rooms_active} note={t('{n}% occupied', { n: s.room_occupancy_percent })} />
            <Stat label={t('Upcoming absences')} value={s.upcoming_absences} note={t('{n} in total', { n: s.absences })} />
            <Stat label={t('Extra sessions')} value={s.extra_sessions} note={t('{n} in freed rooms', { n: s.freed_rooms_reused })} />
          </div>
          <GeneratePanel onDone={stats.reload} />
        </>
      )}
      <Dialog open={!!creds} onClose={() => setCreds(null)} title={t('Professor logins')} wide>
        {creds && <CredentialsTable rows={creds} />}
      </Dialog>
    </div>
  )
}

// ------------------------------------------------------------------ timetable views
type Scope = 'group' | 'prof' | 'room'
const SCOPE_LABEL: Record<Scope, string> = { group: 'By group', prof: 'By professor', room: 'By room' }
const ALL_LABEL: Record<Scope, string> = { group: 'All groups (Excel)', prof: 'All professors (Excel)', room: 'All rooms (Excel)' }

export function Timetable() {
  const cfg = useConfig()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const scope = (params.get('scope') as Scope) || 'group'
  const id = params.get('id') || ''
  const date = params.get('date') || cfg.data?.display_date || cfg.data?.today || ''
  const groups = useLoad<LevelGroups[]>('/public/groups')
  const profs = useLoad<Professor[]>('/admin/professors')
  const rooms = useLoad<Room[]>('/admin/rooms')
  const week = useLoad<Week>(id && date ? `/admin/week?scope=${scope}&id=${id}&date=${date}` : null)
  const [picked, setPicked] = useState<WeekEntry | null>(null)
  const [check, setCheck] = useState<{ ok: boolean; conflicts: string[] } | null>(null)
  const [checking, setChecking] = useState(false)

  const choices = useMemo(() => {
    if (scope === 'prof') return (profs.data ?? []).map((p) => ({ id: p.id, name: p.name }))
    if (scope === 'room') return (rooms.data ?? []).map((r) => ({ id: r.id, name: r.name + (r.active ? '' : ` (${t('closed')})`) }))
    const out: { id: number; name: string; section?: boolean }[] = []
    const walk = (n: GroupNode) => (
      out.push({ id: n.id, name: n.kind === 'section' ? `${n.name} (${t('whole section')})` : n.name, section: n.kind === 'section' }),
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
    setChecking(true)
    try {
      setCheck(await api.get('/admin/timetable/check'))
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setChecking(false)
    }
  }

  return (
    <div className="stack">
      <PageHead title={t('Timetable')} intro={t('Generate, check and browse the timetable by group, professor or room.')}>
        <button className="btn" onClick={runCheck} disabled={checking}>
          {checking ? <span className="spinner" /> : <Icon name="check" />} {t('Check for clashes')}
        </button>
      </PageHead>
      <GeneratePanel onDone={() => week.reload()} />
      {check && (
        <div className={'callout ' + (check.ok ? 'callout-ok' : 'callout-bad')} role="status">
          <Icon name={check.ok ? 'check' : 'alert'} />
          {check.ok ? (
            t('Checked: the saved timetable follows every rule (0 clashes).')
          ) : (
            <div>
              {t('{n} problem(s):', { n: check.conflicts.length })}
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
              {t(SCOPE_LABEL[s])}
            </button>
          ))}
        </div>
        <div className="row-between">
          <div className="row">
            <select className="select" value={id} onChange={(e) => set({ id: e.target.value })} aria-label={t('Show the timetable of')}>
              {choices.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
            <WeekNav week={week.data} date={date} thisWeek={cfg.data?.display_date ?? cfg.data?.today ?? ''} onChange={(d) => set({ date: d })} />
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
                {t(ALL_LABEL[scope])}
              </a>
            </div>
          )}
        </div>
        {week.error && <ErrorBox error={week.error} onRetry={week.reload} />}
        {week.loading && !week.data && <GridSkeleton days={cfg.data?.days.length} slots={cfg.data?.slots.length} />}
        {choices.length === 0 && !groups.loading && (
          <Empty icon="calendar" title={t('Nothing to show yet')}>
            <p>{t('Generate the timetable first.')}</p>
          </Empty>
        )}
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

  if (!entry || !cfg.data)
    return (
      <Dialog open={false} onClose={onClose} title="">
        {null}
      </Dialog>
    )

  const move = async () => {
    setBusy(true)
    setProblems(null)
    try {
      await api.patch(`/admin/sessions/${entry.session_id}`, { day, slot, room_id: room ? Number(room) : undefined })
      toast(t('Session moved'))
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
      toast(t('Marked absent on {date}: {room} is free for that slot', { date: shortDate(entry.date), room: entry.room }))
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
        <dt>{t('Group')}</dt>
        <dd>{entry.group}</dd>
        <dt>{t('Professor')}</dt>
        <dd>{entry.professor}</dd>
        <dt>{t('Now')}</dt>
        <dd>
          {dayName(cfg.data.days[entry.day])} {ltr(entry.time)}, {entry.room}
        </dd>
      </dl>
      <div className="form-grid">
        <label className="field">
          {t('Day')}
          <select className="select" value={day} onChange={(e) => setDay(Number(e.target.value))}>
            {cfg.data.days.map((d, i) => (
              <option key={d} value={i}>
                {dayName(d)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t('Time')}
          <select className="select" value={slot} onChange={(e) => setSlot(Number(e.target.value))}>
            {cfg.data.slots.map((s, i) => (
              <option key={s} value={i}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {t('Room')}
          <select className="select" value={room} onChange={(e) => setRoom(e.target.value)}>
            {rooms
              .filter((r) => r.active)
              .map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name} ({r.capacity})
                </option>
              ))}
          </select>
        </label>
      </div>
      {problems && (
        <div className="callout callout-bad">
          <Icon name="alert" />
          <div>
            {t('Refused, this move would create a clash:')}
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
            {t('Professor absent on {date}', { date: longDate(entry.date) })}
          </button>
        ) : (
          <span />
        )}
        <button className="btn btn-primary" onClick={move} disabled={busy}>
          {busy && <span className="spinner" />} {t('Move session')}
        </button>
      </div>
    </Dialog>
  )
}

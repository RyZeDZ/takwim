import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, ApiError, sendOrQueue } from '../api/client'
import type { Absence, Availability, Claim, MyGroup, SlotOption, Week, WeekEntry } from '../api/types'
import { PageHead } from '../components/Layout'
import { Dialog, Empty, ErrorBox, GridSkeleton, Icon, ListSkeleton, Loading, Progress, SavedCopyNote } from '../components/ui'
import { TodayCard, WeekGrid, WeekNav } from '../components/WeekGrid'
import { addDays, dayName, kindLabel, longDate, ltr, shortDate } from '../lib/dates'
import { errorText, useConfig, useLoad, useOnDataChanged, useToast } from '../lib/hooks'
import { t } from '../lib/i18n'

// ------------------------------------------------------------------ my week
export function ProfWeek() {
  const cfg = useConfig()
  const toast = useToast()
  const [params, setParams] = useSearchParams()
  const date = params.get('date') || cfg.data?.display_date || cfg.data?.today || ''
  const week = useLoad<Week>(date ? `/me/week?date=${date}` : null)
  const absences = useLoad<Absence[]>('/me/absences')
  const [picked, setPicked] = useState<WeekEntry | null>(null)
  const [busy, setBusy] = useState(false)
  const { reload: reloadWeek } = week
  const { reload: reloadAbsences } = absences
  const refresh = useCallback(() => {
    reloadWeek()
    reloadAbsences()
  }, [reloadWeek, reloadAbsences])
  useOnDataChanged(refresh)
  const today = cfg.data?.today ?? ''

  const act = async (fn: () => Promise<string | null>) => {
    setBusy(true)
    try {
      const msg = await fn()
      if (msg) toast(msg)
      setPicked(null)
      refresh()
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setBusy(false)
    }
  }

  const declareAbsence = (e: WeekEntry) =>
    act(async () => {
      const r = await sendOrQueue<Absence>(
        'POST',
        '/me/absences',
        { session_id: e.session_id, date: e.date },
        t('Absence: {what}', { what: `${e.module}, ${shortDate(e.date)}` }),
      )
      return r.queued
        ? t('Saved. Your absence will be sent when the connection returns.')
        : t('Done. {group} will see "Cancelled", and {room} is free for others.', { group: e.group, room: r.data.room_freed })
    })

  const undoAbsence = (e: WeekEntry) =>
    act(async () => {
      const a = absences.data?.find((x) => x.session_id === e.session_id && x.date === e.date)
      if (!a) throw new Error(t('Absence not found: refresh the page and try again.'))
      await api.del(`/me/absences/${a.id}`)
      return t('Absence cancelled: the class is back on.')
    })

  const cancelClaim = (e: WeekEntry) =>
    act(async () => {
      await api.del(`/me/claims/${e.claim_id}`)
      return t('Extra session cancelled. The room is free again.')
    })

  return (
    <div className="stack">
      <PageHead title={t('My week')} intro={t('Tap a class to declare an absence for that day. The room is freed for others right away.')}>
        <Link to="/prof/extra" className="btn btn-primary">
          <Icon name="plus" /> {t('Extra session')}
        </Link>
      </PageHead>
      <SavedCopyNote savedAt={week.savedAt} />
      {week.data && <TodayCard week={week.data} today={today} />}
      <WeekNav week={week.data} date={date} thisWeek={cfg.data?.display_date ?? cfg.data?.today ?? ''} onChange={(d) => setParams({ date: d })} />
      {week.error && <ErrorBox error={week.error} onRetry={week.reload} />}
      {week.loading && !week.data && <GridSkeleton days={cfg.data?.days.length} slots={cfg.data?.slots.length} />}
      {week.data && week.data.entries.length === 0 && (
        <Empty icon="calendar" title={t('No classes this week')}>
          <p>{t("If the timetable hasn't been generated yet, check again later.")}</p>
        </Empty>
      )}
      {week.data && week.data.entries.length > 0 && <WeekGrid week={week.data} today={today} show={['group', 'room']} onEntry={setPicked} />}

      <Dialog open={!!picked} onClose={() => setPicked(null)} title={picked?.module ?? ''}>
        {picked && (
          <>
            <dl className="kbd-list">
              <dt>{t('When')}</dt>
              <dd>
                {longDate(picked.date)}, {ltr(picked.time)}
              </dd>
              <dt>{t('Group')}</dt>
              <dd>{picked.group}</dd>
              <dt>{t('Room')}</dt>
              <dd>{picked.room}</dd>
              <dt>{t('Status')}</dt>
              <dd>
                {picked.status === 'cancelled' && <span className="badge badge-cancelled">{t("Cancelled (you're absent)")}</span>}
                {picked.status === 'new' && <span className="badge badge-new">{t('Extra session you booked')}</span>}
                {picked.status === 'normal' && t('Regular class')}
              </dd>
            </dl>
            {picked.date < today ? (
              <p className="muted small">{t('This date has passed.')}</p>
            ) : picked.status === 'normal' ? (
              <div className="stack-sm">
                <p className="small muted">
                  {t('Students of {group} will see this class as cancelled, and {room} becomes available to other professors for that slot.', {
                    group: picked.group,
                    room: picked.room,
                  })}
                </p>
                <button className="btn btn-danger btn-lg" disabled={busy} onClick={() => declareAbsence(picked)}>
                  {busy && <span className="spinner" />} {t("I'll be absent on {date}", { date: shortDate(picked.date) })}
                </button>
              </div>
            ) : picked.status === 'cancelled' ? (
              <button className="btn btn-lg" disabled={busy} onClick={() => undoAbsence(picked)}>
                {t("I'll be there after all (undo)")}
              </button>
            ) : (
              <button className="btn btn-danger btn-lg" disabled={busy} onClick={() => cancelClaim(picked)}>
                {t('Cancel this extra session')}
              </button>
            )}
          </>
        )}
      </Dialog>
    </div>
  )
}

// ------------------------------------------------------------------ extra session
type Range = 'this' | 'next' | 'custom'
type Option = SlotOption & { otherRooms: number }

/** Options come ranked per (date, time, room): keep the best room of each time, at most 6 times. */
function bestPerSlot(options: SlotOption[]): Option[] {
  const out: Option[] = []
  for (const o of options) {
    const same = out.find((x) => x.date === o.date && x.slot === o.slot)
    if (same) same.otherRooms++
    else out.push({ ...o, otherRooms: 0 })
  }
  return out.slice(0, 6)
}

export function ProfExtra() {
  const cfg = useConfig()
  const toast = useToast()
  const groups = useLoad<MyGroup[]>('/me/groups')
  const [choice, setChoice] = useState('')
  const [range, setRange] = useState<Range>('this')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [options, setOptions] = useState<Option[] | null>(null)
  const [notice, setNotice] = useState<{ kind: 'warn' | 'ok'; text: string; list?: string[] } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const picked = groups.data?.find((g) => `${g.group_id}:${g.module_id}` === choice) ?? null
  useEffect(() => {
    if (!choice && groups.data?.length) setChoice(`${groups.data[0].group_id}:${groups.data[0].module_id}`)
  }, [groups.data, choice])

  const search = async () => {
    if (!picked || !cfg.data) return
    setBusy(true)
    setError(null)
    setNotice(null)
    const body: Record<string, unknown> = { group_id: picked.group_id, kind: picked.kind, limit: 50 }
    if (range === 'next') {
      // the week after the one shown by default
      const shown = cfg.data.display_date
      body.date_from = addDays(shown, 7)
      body.date_to = addDays(shown, 13)
    } else if (range === 'custom') {
      body.date_from = from
      if (to) body.date_to = to
    }
    try {
      const r = await api.post<{ options: SlotOption[] }>('/me/slots/search', body)
      setOptions(bestPerSlot(r.options))
    } catch (e) {
      setError(errorText(e))
      setOptions(null)
    } finally {
      setBusy(false)
    }
  }

  const claim = async (o: SlotOption) => {
    if (!picked) return
    setBusy(true)
    try {
      const r = await sendOrQueue<Claim>(
        'POST',
        '/me/claims',
        { group_id: picked.group_id, room_id: o.room.id, date: o.date, slot: o.slot, module_id: picked.module_id, kind: picked.kind },
        t('Extra session: {what}', { what: `${picked.group}, ${shortDate(o.date)} ${o.time}` }),
      )
      if (r.queued) {
        setNotice({
          kind: 'warn',
          text: t('Saved offline. It will be booked when the connection returns, if the slot is still free (first claim wins).'),
        })
      } else {
        setNotice({
          kind: 'ok',
          text: t('Booked: {group} on {date}, {time}, in {room}. Students now see it as a new session.', {
            group: r.data.group,
            date: longDate(r.data.date),
            time: r.data.time,
            room: r.data.room,
          }),
        })
        setOptions(null)
        toast(t('Extra session booked'))
      }
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && typeof e.detail === 'object' && e.detail) {
        const d = e.detail as { message: string; problems: string[]; alternatives: SlotOption[] }
        setNotice({ kind: 'warn', text: `${t(d.message)}. ${t('Here are the next best options.')}`, list: d.problems })
        setOptions(bestPerSlot(d.alternatives))
      } else {
        toast(errorText(e), true)
      }
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack">
      <PageHead
        title={t('Extra session')}
        intro={t("Find a time when you, your students and a room are all free. Rooms freed by a colleague's absence come first.")}
      />
      {groups.loading && (
        <div className="panel">
          <ListSkeleton rows={3} />
        </div>
      )}
      {groups.error && <ErrorBox error={groups.error} onRetry={groups.reload} />}
      {groups.data && groups.data.length === 0 && (
        <Empty icon="users" title={t('No group yet')}>
          <p>{t('You have no classes in the timetable yet, so there is no group to book for.')}</p>
        </Empty>
      )}
      {groups.data && groups.data.length > 0 && (
        <div className="panel stack-sm">
          <div className="form-grid">
            <label className="field" style={{ gridColumn: 'span 2' }}>
              {t('Group and module')}
              <select className="select" value={choice} onChange={(e) => (setChoice(e.target.value), setOptions(null))}>
                {groups.data.map((g) => (
                  <option key={`${g.group_id}:${g.module_id}`} value={`${g.group_id}:${g.module_id}`}>
                    {g.group} · {g.module} ({kindLabel(g.kind)}, {t('{n} students', { n: g.size })})
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              {t('When')}
              <select className="select" value={range} onChange={(e) => setRange(e.target.value as Range)}>
                <option value="this">{t('Coming days')}</option>
                <option value="next">{t('The week after')}</option>
                <option value="custom">{t('Choose dates')}</option>
              </select>
            </label>
            {range === 'custom' && (
              <>
                <label className="field">
                  {t('From')}
                  <input className="input" type="date" value={from} min={cfg.data?.today} onChange={(e) => setFrom(e.target.value)} />
                </label>
                <label className="field">
                  {t('To (optional)')}
                  <input className="input" type="date" value={to} min={from} onChange={(e) => setTo(e.target.value)} />
                </label>
              </>
            )}
          </div>
          <button
            className="btn btn-primary"
            style={{ alignSelf: 'start' }}
            onClick={search}
            disabled={busy || !picked || (range === 'custom' && !from)}
          >
            {busy ? <span className="spinner" /> : <Icon name="search" />} {t('Find free slots')}
          </button>
          {busy && !options && <Progress value={null} note={t('Checking every day, time and room…')} />}
        </div>
      )}
      {error && <ErrorBox error={error} />}
      {notice && (
        <div className={`callout callout-${notice.kind}`} role="status">
          <Icon name={notice.kind === 'ok' ? 'check' : 'alert'} />
          <div>
            {notice.text}
            {notice.list && (
              <ul>
                {notice.list.map((p) => (
                  <li key={p}>{t(p)}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
      {options && options.length === 0 && (
        <div className="callout callout-info">
          <Icon name="info" /> {t('No free slot in this period. Try next week or other dates.')}
        </div>
      )}
      {options && options.length > 0 && (
        <ol className="options" aria-label={t('Ranked options')}>
          {options.map((o, i) => (
            <li key={`${o.date}-${o.slot}-${o.room.id}`} className={'option' + (i === 0 ? ' best' : '')}>
              <span className="option-rank">{i + 1}</span>
              <div className="option-main">
                <div className="row">
                  <strong>
                    {dayName(o.day)} {shortDate(o.date)}, {ltr(o.time)}
                  </strong>
                  <span className="muted">
                    · {o.room.name} ({t('{n} seats', { n: o.room.capacity })})
                  </span>
                  {i === 0 && <span className="badge badge-neutral">{t('Best option')}</span>}
                  {o.freed_by_absence && <span className="badge badge-freed">{t('Freed room')}</span>}
                  {o.otherRooms > 0 && <span className="small muted">{t('+{n} other room(s) free', { n: o.otherRooms })}</span>}
                </div>
                {o.reasons.length > 0 && (
                  <ul className="reasons">
                    {o.reasons.map((r) => (
                      <li key={r}>{t(r)}</li>
                    ))}
                  </ul>
                )}
              </div>
              <button className={'btn' + (i === 0 ? ' btn-primary' : '')} disabled={busy} onClick={() => claim(o)}>
                {t('Book')}
              </button>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

// ------------------------------------------------------------------ availability grid
type Mark = 'free' | 'no' | 'avoid'
const NEXT: Record<Mark, Mark> = { free: 'no', no: 'avoid', avoid: 'free' }

/** The weekly grid of "I can't" / "I'd rather not" slots. Shared with the admin's professor editor. */
export function AvailabilityEditor({
  load,
  save,
  intro,
}: {
  load: () => Promise<Availability>
  save: (a: Availability) => Promise<Availability>
  intro?: string
}) {
  const cfg = useConfig()
  const toast = useToast()
  const [marks, setMarks] = useState<Record<string, Mark> | null>(null)
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    load()
      .then((a) => {
        const m: Record<string, Mark> = {}
        a.unavailable.forEach((x) => (m[`${x.day}:${x.slot}`] = 'no'))
        a.avoid.forEach((x) => (m[`${x.day}:${x.slot}`] = 'avoid'))
        setMarks(m)
      })
      .catch((e) => setError(errorText(e)))
  }, [load])

  const counts = useMemo(() => {
    const v = Object.values(marks ?? {})
    return { no: v.filter((x) => x === 'no').length, avoid: v.filter((x) => x === 'avoid').length }
  }, [marks])

  if (error) return <ErrorBox error={error} />
  if (!marks || !cfg.data) return <Loading />
  const { days, slots } = cfg.data

  const toggle = (k: string) => {
    setMarks((m) => ({ ...m, [k]: NEXT[m?.[k] ?? 'free'] }))
    setDirty(true)
  }
  /** Tap a day name: the whole day becomes "can't" (or free again if it already was). */
  const toggleDay = (di: number) => {
    const all = slots.every((_, si) => marks[`${di}:${si}`] === 'no')
    setMarks((m) => ({ ...m, ...Object.fromEntries(slots.map((_, si) => [`${di}:${si}`, all ? 'free' : 'no'])) }))
    setDirty(true)
  }
  const submit = async () => {
    setBusy(true)
    const pick = (want: Mark) =>
      Object.entries(marks)
        .filter(([, v]) => v === want)
        .map(([k]) => ({ day: Number(k.split(':')[0]), slot: Number(k.split(':')[1]) }))
    try {
      await save({ unavailable: pick('no'), avoid: pick('avoid') })
      setDirty(false)
      toast(t('Saved. It will be used the next time the timetable is generated.'))
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack-sm">
      {intro && <p className="muted">{intro}</p>}
      <div className="legend">
        <span>
          <i className="swatch" /> {t('Available')}
        </span>
        <span>
          <i className="swatch no" /> {t("I can't (never scheduled)")}
        </span>
        <span>
          <i className="swatch avoid" /> {t("I'd rather not (avoided when possible)")}
        </span>
      </div>
      <div className="table-wrap">
        <div className="avail" style={{ gridTemplateColumns: `88px repeat(${days.length}, 1fr)` }} role="grid">
          <span />
          {days.map((d, di) => (
            <button key={d} type="button" className="avail-head avail-day" onClick={() => toggleDay(di)} title={t('Tap to block the whole day')}>
              {dayName(d)}
            </button>
          ))}
          {slots.map((s, si) => (
            <div key={s} style={{ display: 'contents' }} role="row">
              <span className="avail-head" style={{ textAlign: 'start', alignSelf: 'center' }}>
                {s.replace('-', ' – ')}
              </span>
              {days.map((d, di) => {
                const k = `${di}:${si}`
                const m = marks[k] ?? 'free'
                const label = m === 'no' ? t("Can't") : m === 'avoid' ? t('Rather not') : ''
                return (
                  <button
                    key={k}
                    type="button"
                    className={`avail-cell ${m}`}
                    onClick={() => toggle(k)}
                    aria-label={`${dayName(d)} ${s}: ${label || t('Available')}`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <div className="row-between">
        <span className="small muted">
          {t('{no} slot(s) blocked · {avoid} to avoid. Tap a slot to change it, or a day name for the whole day.', counts)}
        </span>
        <button className="btn btn-primary" onClick={submit} disabled={busy || !dirty}>
          {busy && <span className="spinner" />} {dirty ? t('Save') : t('Saved')}
        </button>
      </div>
    </div>
  )
}

export function ProfAvailability() {
  const load = useCallback(() => api.get<Availability>('/me/availability'), [])
  const save = useCallback((a: Availability) => api.put<Availability>('/me/availability', a), [])
  return (
    <div className="stack">
      <PageHead
        title={t('My availability')}
        intro={t("Mark the slots you can't teach, and those you'd rather avoid. The timetable never puts you in a blocked slot.")}
      />
      <div className="panel">
        <AvailabilityEditor load={load} save={save} />
      </div>
    </div>
  )
}

// ------------------------------------------------------------------ my bookings
export function ProfBookings() {
  const toast = useToast()
  const absences = useLoad<Absence[]>('/me/absences')
  const claims = useLoad<Claim[]>('/me/claims')
  const cfg = useConfig()
  const { reload: reloadAbsences } = absences
  const { reload: reloadClaims } = claims
  const refresh = useCallback(() => {
    reloadAbsences()
    reloadClaims()
  }, [reloadAbsences, reloadClaims])
  useOnDataChanged(refresh)

  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try {
      await fn()
      toast(ok)
      refresh()
    } catch (e) {
      toast(errorText(e), true)
    }
  }

  return (
    <div className="stack">
      <PageHead title={t('My absences and extra sessions')} intro={t('Upcoming only. Undo an absence as long as nobody has booked the freed slot.')} />
      <section className="panel panel-tight">
        <div className="panel-head">
          <h2>{t('Absences')}</h2>
        </div>
        {absences.loading && !absences.data && <ListSkeleton rows={2} />}
        {absences.data?.length === 0 && <p className="muted small" style={{ padding: '0 24px 20px' }}>{t('No upcoming absence.')}</p>}
        {!!absences.data?.length && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Date')}</th>
                  <th>{t('Time')}</th>
                  <th>{t('Class')}</th>
                  <th>{t('Freed room')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {absences.data.map((a) => (
                  <tr key={a.id}>
                    <td>{longDate(a.date)}</td>
                    <td className="num">{cfg.data?.slots[a.slot]}</td>
                    <td>
                      {a.module} · {a.group}
                    </td>
                    <td>{a.room_freed}</td>
                    <td className="actions">
                      <button className="btn btn-sm" onClick={() => run(() => api.del(`/me/absences/${a.id}`), t('Absence cancelled'))}>
                        {t('Undo')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="panel panel-tight">
        <div className="panel-head">
          <h2>{t('Extra sessions')}</h2>
          <Link to="/prof/extra" className="btn btn-sm">
            <Icon name="plus" /> {t('New')}
          </Link>
        </div>
        {claims.loading && !claims.data && <ListSkeleton rows={2} />}
        {claims.data?.length === 0 && <p className="muted small" style={{ padding: '0 24px 20px' }}>{t('No upcoming extra session.')}</p>}
        {!!claims.data?.length && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Date')}</th>
                  <th>{t('Time')}</th>
                  <th>{t('Group')}</th>
                  <th>{t('Room')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {claims.data.map((c) => (
                  <tr key={c.id}>
                    <td>{longDate(c.date)}</td>
                    <td className="num">{c.time}</td>
                    <td>
                      {c.group}
                      {c.module ? ` · ${c.module}` : ''}
                    </td>
                    <td>{c.room}</td>
                    <td className="actions">
                      <button className="btn btn-sm btn-danger" onClick={() => run(() => api.del(`/me/claims/${c.id}`), t('Extra session cancelled'))}>
                        {t('Cancel')}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

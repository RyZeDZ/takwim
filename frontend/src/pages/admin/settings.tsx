import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { GenerateResult, Kind, LogRow, Room, Rules, SettingsResponse } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { ErrorBox, Loading } from '../../components/ui'
import { errorText, useConfig, useLoad, useToast } from '../../lib/hooks'
import { ROOM_TYPE } from '../public'
import { GenerateSummary } from './timetable'

const WEEKDAYS = ['saturday', 'sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday']
const KIND_LABEL: Record<Kind, string> = { lecture: 'Lectures', td: 'TD', tp: 'TP' }

const NUMBERS: { key: keyof Rules; label: string; hint: string }[] = [
  { key: 'max_sessions_per_day_per_group', label: 'Max sessions per day, per group', hint: 'Students never have more classes than this in one day.' },
  { key: 'max_sessions_per_day_per_professor', label: 'Max sessions per day, per professor', hint: 'A professor never teaches more than this in one day.' },
  { key: 'default_max_sessions_per_professor', label: 'Default max sessions per week, per professor', hint: 'Used when a professor has no personal maximum.' },
  { key: 'section_max_size', label: 'Max students per section', hint: 'A section attends lectures together.' },
  { key: 'td_group_size', label: 'Students per TD group', hint: 'Target size of a TD group.' },
  { key: 'tp_group_size', label: 'Students per TP subgroup', hint: 'Only used when TP subgroups are on.' },
]

export function Settings() {
  const cfg = useConfig()
  const toast = useToast()
  const [data, setData] = useState<SettingsResponse | null>(null)
  const [rules, setRules] = useState<Rules | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [outcome, setOutcome] = useState<{ changed: string[]; notes: string[]; regenerated: GenerateResult | null } | null>(null)

  useEffect(() => {
    api
      .get<SettingsResponse>('/admin/settings')
      .then((r) => {
        setData(r)
        setRules(r.rules)
      })
      .catch((e) => setError(errorText(e)))
  }, [])

  if (error) return <ErrorBox error={error} />
  if (!rules || !data) return <Loading />

  const changes = Object.fromEntries(
    Object.entries(rules).filter(([k, v]) => JSON.stringify(v) !== JSON.stringify(data.rules[k as keyof Rules])),
  )
  const reshaping = ['week_days', 'time_slots', 'section_max_size', 'td_group_size', 'tp_group_size', 'split_tp_groups', 'room_types_for'].some(
    (k) => k in changes,
  )

  const save = async () => {
    setBusy(true)
    setOutcome(null)
    try {
      const r = await api.put<{ rules: Rules; changed: string[]; notes: string[]; regenerated: GenerateResult | null }>('/admin/settings', changes)
      setData({ ...data, rules: r.rules })
      setRules(r.rules)
      setOutcome(r)
      cfg.reload()
      toast('Settings saved')
    } catch (e) {
      toast(errorText(e), true)
    } finally {
      setBusy(false)
    }
  }

  const days = WEEKDAYS.filter((d) => rules.week_days.includes(d))
  const firstDay = days[0] ?? 'sunday'
  // Keep days in calendar order starting from the chosen first day of the week.
  const orderFrom = (first: string, picked: string[]) => {
    const start = WEEKDAYS.indexOf(first)
    const cycle = [...WEEKDAYS.slice(start), ...WEEKDAYS.slice(0, start)]
    return cycle.filter((d) => picked.includes(d))
  }

  return (
    <div className="stack">
      <PageHead title="Settings" intro="The department's rules. Changing the week or the group sizes regenerates the timetable right away, moving as few sessions as possible.">
        <button className="btn btn-primary" disabled={busy || !Object.keys(changes).length} onClick={save}>
          {busy && <span className="spinner" />}
          {busy && reshaping ? 'Saving and regenerating…' : 'Save changes'}
        </button>
      </PageHead>
      {reshaping && !busy && (
        <div className="callout callout-info">Saving these changes will regenerate the timetable (it takes a few seconds).</div>
      )}
      {outcome && (
        <section className="panel stack-sm">
          <h2>Saved</h2>
          <p className="small muted">Changed: {outcome.changed.join(', ') || 'nothing'}</p>
          {outcome.notes.map((n) => (
            <div key={n} className="callout callout-warn">
              {n}
            </div>
          ))}
          {outcome.regenerated && <GenerateSummary r={outcome.regenerated} />}
        </section>
      )}

      <section className="panel stack-sm">
        <h2>Week</h2>
        <div className="form-grid">
          <label className="field">
            First day of the week
            <select
              className="select"
              value={firstDay}
              onChange={(e) => setRules({ ...rules, week_days: orderFrom(e.target.value, [...new Set([e.target.value, ...rules.week_days])]) })}
            >
              {WEEKDAYS.map((d) => (
                <option key={d} value={d}>
                  {cap(d)}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="row" role="group" aria-label="Working days">
          {orderFrom(firstDay, WEEKDAYS).map((d) => (
            <label key={d} className="check" style={{ marginRight: 12 }}>
              <input
                type="checkbox"
                checked={rules.week_days.includes(d)}
                disabled={d === firstDay}
                onChange={(e) =>
                  setRules({
                    ...rules,
                    week_days: orderFrom(firstDay, e.target.checked ? [...rules.week_days, d] : rules.week_days.filter((x) => x !== d)),
                  })
                }
              />
              {cap(d)}
            </label>
          ))}
        </div>
      </section>

      <section className="panel stack-sm">
        <h2>Time slots</h2>
        <p className="small muted">Format 08:00-09:30, in order, without overlaps.</p>
        <div className="stack-sm" style={{ gap: 8, maxWidth: 360 }}>
          {rules.time_slots.map((s, i) => (
            <div className="row" key={i}>
              <input
                className="input"
                style={{ flex: 1 }}
                value={s}
                aria-label={`Time slot ${i + 1}`}
                onChange={(e) => setRules({ ...rules, time_slots: rules.time_slots.map((x, j) => (j === i ? e.target.value : x)) })}
              />
              <button
                className="btn icon-btn btn-ghost"
                aria-label={`Remove slot ${s}`}
                disabled={rules.time_slots.length <= 1}
                onClick={() => setRules({ ...rules, time_slots: rules.time_slots.filter((_, j) => j !== i) })}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            className="btn btn-sm"
            style={{ alignSelf: 'start' }}
            onClick={() => setRules({ ...rules, time_slots: [...rules.time_slots, nextSlot(rules.time_slots)] })}
          >
            Add a slot
          </button>
        </div>
      </section>

      <section className="panel stack-sm">
        <h2>Limits and group sizes</h2>
        <div className="form-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
          {NUMBERS.map((n) => (
            <label key={n.key} className="field">
              {n.label}
              <input
                className="input"
                type="number"
                min={1}
                value={rules[n.key] as number}
                onChange={(e) => setRules({ ...rules, [n.key]: Number(e.target.value) })}
              />
              <span className="tiny muted" style={{ fontWeight: 400 }}>
                {n.hint}
              </span>
            </label>
          ))}
        </div>
        <label className="check">
          <input type="checkbox" checked={rules.split_tp_groups} onChange={(e) => setRules({ ...rules, split_tp_groups: e.target.checked })} />
          Split TD groups into smaller TP subgroups (off: the whole TD group goes to the lab)
        </label>
      </section>

      <section className="panel stack-sm">
        <h2>Which rooms for which classes</h2>
        <div className="table-wrap">
          <table className="table" style={{ maxWidth: 560 }}>
            <thead>
              <tr>
                <th></th>
                {(['amphi', 'td', 'lab'] as Room['type'][]).map((t) => (
                  <th key={t}>{ROOM_TYPE[t]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(['lecture', 'td', 'tp'] as Kind[]).map((k) => (
                <tr key={k}>
                  <td>
                    <strong>{KIND_LABEL[k]}</strong>
                  </td>
                  {(['amphi', 'td', 'lab'] as Room['type'][]).map((t) => {
                    const on = rules.room_types_for[k].includes(t)
                    return (
                      <td key={t}>
                        <input
                          type="checkbox"
                          style={{ width: 18, height: 18, accentColor: 'var(--blue)' }}
                          checked={on}
                          aria-label={`${KIND_LABEL[k]} in ${ROOM_TYPE[t]}`}
                          onChange={() =>
                            setRules({
                              ...rules,
                              room_types_for: {
                                ...rules.room_types_for,
                                [k]: on ? rules.room_types_for[k].filter((x) => x !== t) : [...rules.room_types_for[k], t],
                              },
                            })
                          }
                        />
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn" disabled={busy} onClick={() => setRules(data.defaults)}>
          Back to defaults
        </button>
        <button className="btn btn-primary" disabled={busy || !Object.keys(changes).length} onClick={save}>
          Save changes
        </button>
      </div>
    </div>
  )
}

const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

/** Suggest the slot that follows the last one, with the same length. */
function nextSlot(slots: string[]): string {
  const last = slots[slots.length - 1]
  const m = last?.match(/^(\d\d):(\d\d)-(\d\d):(\d\d)$/)
  if (!m) return '08:00-09:30'
  const start = +m[3] * 60 + +m[4]
  const len = start - (+m[1] * 60 + +m[2])
  const f = (t: number) => `${String(Math.floor(t / 60) % 24).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
  return `${f(start)}-${f(start + len)}`
}

// ------------------------------------------------------------------ activity log
export function Activity() {
  const logs = useLoad<LogRow[]>('/admin/logs?limit=200')
  return (
    <div className="stack">
      <PageHead title="Activity" intro="Every action, who did it and when: imports, generations, absences, bookings." />
      {logs.error && <ErrorBox error={logs.error} onRetry={logs.reload} />}
      {logs.loading && !logs.data && <Loading />}
      {logs.data && (
        <section className="panel panel-tight">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>Action</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {logs.data.map((l, i) => (
                  <tr key={i}>
                    <td className="num" style={{ whiteSpace: 'nowrap' }}>
                      {new Date(l.at + 'Z').toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' })}
                    </td>
                    <td>{l.user}</td>
                    <td>
                      <span className="badge badge-neutral">{l.action.replace('_', ' ')}</span>
                    </td>
                    <td className="small">{l.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {logs.data.length === 0 && <p className="muted small" style={{ padding: 20 }}>Nothing yet.</p>}
        </section>
      )}
    </div>
  )
}

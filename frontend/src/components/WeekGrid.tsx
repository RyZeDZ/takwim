import type { Week, WeekEntry } from '../api/types'
import { addDays, longDate, shortDate, weekLabel } from '../lib/dates'
import { Icon } from './ui'

const KIND_LABEL: Record<string, string> = { lecture: 'Lecture', td: 'TD', tp: 'TP', extra: 'Extra' }

type Field = 'group' | 'professor' | 'room'

interface Props {
  week: Week
  today: string
  show: Field[]
  onEntry?: (e: WeekEntry) => void
  onEmptyCell?: (date: string, slot: number) => void
}

/** Days × time slots, drawn from what the backend sends. On phones it becomes a day-by-day list. */
export function WeekGrid({ week, today, show, onEntry, onEmptyCell }: Props) {
  const at = (date: string, slot: number) => week.entries.filter((e) => e.date === date && e.slot === slot)
  const cols = `minmax(92px, auto) repeat(${week.dates.length}, minmax(130px, 1fr))`

  return (
    <>
      <div className="grid-wrap has-agenda">
        <div className="week-grid" style={{ gridTemplateColumns: cols }} role="table" aria-label="Week timetable">
          <div className="wg-head" style={{ borderLeft: 0 }} role="columnheader">
            Time
          </div>
          {week.dates.map((d, i) => (
            <div key={d} className={'wg-head' + (d === today ? ' today' : '')} role="columnheader">
              {week.days[i]}
              <small>
                {shortDate(d)}
                {d === today ? ' · today' : ''}
              </small>
            </div>
          ))}
          {week.slots.map((slot, s) => (
            <Row key={slot}>
              <div className="wg-time" role="rowheader">
                {slot.replace('-', ' – ')}
              </div>
              {week.dates.map((d) => {
                const items = at(d, s)
                const canTap = !items.length && onEmptyCell && d >= today
                return (
                  <div
                    key={d}
                    role="cell"
                    className={'wg-cell' + (d === today ? ' today' : '') + (canTap ? ' tappable' : '')}
                    onClick={canTap ? () => onEmptyCell!(d, s) : undefined}
                  >
                    {items.map((e) => (
                      <SessionCard key={(e.session_id ?? 'c' + e.claim_id) + e.date} e={e} show={show} onClick={onEntry} />
                    ))}
                  </div>
                )
              })}
            </Row>
          ))}
        </div>
      </div>

      <div className="agenda">
        {week.dates.map((d, i) => {
          const items = week.entries.filter((e) => e.date === d).sort((a, b) => a.slot - b.slot)
          return (
            <section key={d} className="agenda-day" aria-label={longDate(d)}>
              <h3>
                <span>
                  {week.days[i]} {d === today && <span className="badge badge-neutral">Today</span>}
                </span>
                <span className="small muted">{shortDate(d)}</span>
              </h3>
              {items.length === 0 && <p className="agenda-empty">No classes</p>}
              {items.map((e) => (
                <div className="agenda-item" key={(e.session_id ?? 'c' + e.claim_id) + e.date}>
                  <span className="time">{week.slots[e.slot]?.replace('-', '\n')}</span>
                  <SessionCard e={e} show={show} onClick={onEntry} />
                </div>
              ))}
            </section>
          )
        })}
      </div>
    </>
  )
}

function Row({ children }: { children: React.ReactNode }) {
  return <div style={{ display: 'contents' }} role="row">{children}</div>
}

function SessionCard({ e, show, onClick }: { e: WeekEntry; show: Field[]; onClick?: (e: WeekEntry) => void }) {
  const cls = `session k-${e.kind} s-${e.status}`
  const body = (
    <>
      <span className="row" style={{ gap: 6, justifyContent: 'space-between' }}>
        <strong>{e.module}</strong>
        {e.status === 'cancelled' && <span className="badge badge-cancelled">Cancelled</span>}
        {e.status === 'new' && <span className="badge badge-new">New session</span>}
      </span>
      <span className="meta">
        {KIND_LABEL[e.kind]}
        {show.includes('room') && ` · ${e.room}`}
      </span>
      {show.includes('group') && <span className="meta">{e.group}</span>}
      {show.includes('professor') && <span className="meta">{e.professor}</span>}
    </>
  )
  if (onClick)
    return (
      <button type="button" className={cls} onClick={(ev) => (ev.stopPropagation(), onClick(e))}>
        {body}
      </button>
    )
  return <div className={cls}>{body}</div>
}

/** Previous / this week / next week. */
export function WeekNav({
  week,
  date,
  thisWeek,
  onChange,
}: {
  week: Week | null
  date: string
  thisWeek: string // a date of the default week (display_date from /public/config)
  onChange: (date: string) => void
}) {
  return (
    <div className="week-nav">
      <button className="btn icon-btn" onClick={() => onChange(addDays(date, -7))} aria-label="Previous week">
        <Icon name="left" />
      </button>
      <span className="week-title">{week ? weekLabel(week.dates) : '…'}</span>
      <button className="btn icon-btn" onClick={() => onChange(addDays(date, 7))} aria-label="Next week">
        <Icon name="right" />
      </button>
      {week && thisWeek && !week.dates.includes(thisWeek) && (
        <button className="btn btn-sm" onClick={() => onChange(thisWeek)}>
          This week
        </button>
      )}
    </div>
  )
}

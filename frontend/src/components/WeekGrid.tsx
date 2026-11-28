import { useEffect, useRef, useState } from 'react'
import type { Week, WeekEntry } from '../api/types'
import { addDays, dayName, inTime, kindLabel, longDate, ltr, minutes, nowMinutes, shortDate, slotStart, weekLabel } from '../lib/dates'
import { t } from '../lib/i18n'
import { Icon } from './ui'

type Field = 'group' | 'professor' | 'room'

interface Props {
  week: Week
  today: string
  show: Field[]
  onEntry?: (e: WeekEntry) => void
  onEmptyCell?: (date: string, slot: number) => void
}

const entryKey = (e: WeekEntry) => (e.session_id ?? 'c' + e.claim_id) + e.date

/** Re-render every minute (for "now" and "in 25 min"). */
function useMinute() {
  const [, set] = useState(0)
  useEffect(() => {
    const id = setInterval(() => set((n) => n + 1), 60_000)
    return () => clearInterval(id)
  }, [])
}

/** The class happening now, or the next one today (or on the next day of the week). */
function nowAndNext(week: Week, today: string) {
  const live = week.entries.filter((e) => e.status !== 'cancelled').sort((a, b) => (a.date + a.slot).localeCompare(b.date + b.slot))
  const now = nowMinutes()
  const end = (e: WeekEntry) => minutes(week.slots[e.slot]?.split('-')[1] ?? '23:59')
  const start = (e: WeekEntry) => minutes(slotStart(week.slots[e.slot] ?? '00:00'))
  const todays = live.filter((e) => e.date === today)
  const current = todays.find((e) => start(e) <= now && now < end(e)) ?? null
  const next = todays.find((e) => start(e) > now) ?? live.find((e) => e.date > today) ?? null
  return { current, next, start }
}

/** "Now" / "Next" card above the week. */
export function TodayCard({ week, today }: { week: Week; today: string }) {
  useMinute()
  if (!week.dates.includes(today) && !week.dates.some((d) => d > today)) return null
  const { current, next, start } = nowAndNext(week, today)
  const cancelledToday = week.entries.filter((e) => e.date === today && e.status === 'cancelled')
  if (!current && !next && !cancelledToday.length) return null
  const where = (e: WeekEntry) => [kindLabel(e.kind), e.room].filter(Boolean).join(' · ')
  return (
    <section className="today-card" aria-label={t('Today')}>
      {current && (
        <div className="today-item now">
          <span className="today-tag">{t('Now')}</span>
          <strong>{current.module}</strong>
          <span className="muted">
            {where(current)} · {t('until {time}', { time: ltr(week.slots[current.slot]?.split('-')[1] ?? '') })}
          </span>
        </div>
      )}
      {next && (
        <div className="today-item">
          <span className="today-tag next">{t('Next')}</span>
          <strong>{next.module}</strong>
          <span className="muted">
            {where(next)} ·{' '}
            {next.date === today
              ? inTime(start(next) - nowMinutes())
              : `${next.date === addDays(today, 1) ? t('tomorrow') : dayName(week.days[week.dates.indexOf(next.date)] ?? '')} ${ltr(next.time)}`}
          </span>
        </div>
      )}
      {!current && !next && <div className="today-item muted">{t('No more classes this week.')}</div>}
      {cancelledToday.length > 0 && (
        <div className="today-item">
          <span className="badge badge-cancelled">{t('Cancelled')}</span>
          <span className="muted">
            {t('Today')}: {cancelledToday.map((e) => `${e.module} (${ltr(e.time)})`).join(', ')}
          </span>
        </div>
      )}
    </section>
  )
}

/** Days × time slots, drawn from what the backend sends. On phones it becomes a day-by-day list. */
export function WeekGrid({ week, today, show, onEntry, onEmptyCell }: Props) {
  useMinute()
  const at = (date: string, slot: number) => week.entries.filter((e) => e.date === date && e.slot === slot)
  const cols = `minmax(92px, auto) repeat(${week.dates.length}, minmax(130px, 1fr))`
  const { current, next } = nowAndNext(week, today)
  const highlight = current ?? (next?.date === today ? next : null)
  const hiKey = highlight ? entryKey(highlight) : ''

  // On phones, open the list on today.
  const todayRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const el = todayRef.current
    if (el && window.matchMedia('(max-width: 720px)').matches && el.getBoundingClientRect().top > window.innerHeight)
      el.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [week.week_start])

  return (
    <>
      <div className="grid-wrap has-agenda">
        <div className="week-grid" style={{ gridTemplateColumns: cols }} role="table" aria-label={t('Week timetable')}>
          <div className="wg-head wg-corner" role="columnheader">
            {t('Time')}
          </div>
          {week.dates.map((d, i) => (
            <div key={d} className={'wg-head' + (d === today ? ' today' : '')} role="columnheader">
              {dayName(week.days[i])}
              <small>
                {shortDate(d)}
                {d === today ? ` · ${t('today')}` : ''}
              </small>
            </div>
          ))}
          {week.slots.map((slot, s) => (
            <div key={slot} style={{ display: 'contents' }} role="row">
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
                      <SessionCard key={entryKey(e)} e={e} show={show} onClick={onEntry} highlight={entryKey(e) === hiKey} />
                    ))}
                  </div>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      <div className="agenda">
        {week.dates.map((d, i) => {
          const items = week.entries.filter((e) => e.date === d).sort((a, b) => a.slot - b.slot)
          return (
            <section key={d} className={'agenda-day' + (d === today ? ' is-today' : '')} aria-label={longDate(d)} ref={d === today ? todayRef : undefined}>
              <h3>
                <span>
                  {dayName(week.days[i])} {d === today && <span className="badge badge-neutral">{t('Today')}</span>}
                </span>
                <span className="small muted">{shortDate(d)}</span>
              </h3>
              {items.length === 0 && <p className="agenda-empty">{t('No classes')}</p>}
              {items.map((e) => (
                <div className="agenda-item" key={entryKey(e)}>
                  <span className="time">{week.slots[e.slot]?.replace('-', '\n')}</span>
                  <SessionCard e={e} show={show} onClick={onEntry} highlight={entryKey(e) === hiKey} />
                </div>
              ))}
            </section>
          )
        })}
      </div>
    </>
  )
}

function SessionCard({ e, show, onClick, highlight }: { e: WeekEntry; show: Field[]; onClick?: (e: WeekEntry) => void; highlight?: boolean }) {
  const cls = `session k-${e.kind} s-${e.status}` + (highlight ? ' is-next' : '')
  const body = (
    <>
      <span className="row" style={{ gap: 6, justifyContent: 'space-between' }}>
        <strong>{e.module}</strong>
        {e.status === 'cancelled' && <span className="badge badge-cancelled">{t('Cancelled')}</span>}
        {e.status === 'new' && <span className="badge badge-new">{t('New session')}</span>}
      </span>
      <span className="meta">
        {kindLabel(e.kind)}
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
      <button className="btn icon-btn" onClick={() => onChange(addDays(date, -7))} aria-label={t('Previous week')}>
        <Icon name="left" flip />
      </button>
      <span className="week-title">{week ? weekLabel(week.dates) : '…'}</span>
      <button className="btn icon-btn" onClick={() => onChange(addDays(date, 7))} aria-label={t('Next week')}>
        <Icon name="right" flip />
      </button>
      {week && thisWeek && !week.dates.includes(thisWeek) && (
        <button className="btn btn-sm" onClick={() => onChange(thisWeek)}>
          {t('This week')}
        </button>
      )}
    </div>
  )
}

import { useCallback, useMemo, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { Availability, Credential, Kind, Level, Module, Professor, Room, Teaching } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { CredentialsTable, Dialog, ErrorBox, Icon, ListSkeleton } from '../../components/ui'
import { errorText, useLoad, useToast } from '../../lib/hooks'
import { AvailabilityEditor } from '../prof'
import { roomType } from '../public'
import { t } from '../../lib/i18n'
import { kindLabel } from '../../lib/dates'

const KINDS: Kind[] = ['lecture', 'td', 'tp']

function useAction() {
  const toast = useToast()
  return async (fn: () => Promise<unknown>, ok?: string) => {
    try {
      await fn()
      if (ok) toast(ok)
      return true
    } catch (e) {
      toast(errorText(e), true)
      return false
    }
  }
}

// ------------------------------------------------------------------ rooms
export function Rooms() {
  const rooms = useLoad<Room[]>('/admin/rooms')
  const act = useAction()
  const [edit, setEdit] = useState<Partial<Room> | null>(null)
  const [query, setQuery] = useState('')
  const list = (rooms.data ?? []).filter((r) => r.name.toLowerCase().includes(query.toLowerCase()))
  const open = rooms.data?.filter((r) => r.active) ?? []

  const toggle = (r: Room) =>
    act(
      () => api.patch(`/admin/rooms/${r.id}`, { active: !r.active }),
      r.active ? t('{room} closed. Generate the timetable again to move its sessions.', { room: r.name }) : t('{room} reopened', { room: r.name }),
    ).then(rooms.reload)

  return (
    <div className="stack">
      <PageHead title={t('Rooms')} intro={t('Lecture halls, classrooms and labs. Close a room (repairs, exams) and regenerate: its sessions move elsewhere.')}>
        <button className="btn btn-primary" onClick={() => setEdit({ type: 'td', capacity: 40, active: true })}>
          <Icon name="plus" /> {t('Add room')}
        </button>
      </PageHead>
      {rooms.data && (
        <div className="stats">
          <div className="stat">
            <span className="stat-label">{t('Open rooms')}</span>
            <span className="stat-value">{open.length}</span>
            <span className="stat-note">{t('{n} closed', { n: rooms.data.length - open.length })}</span>
          </div>
          <div className="stat">
            <span className="stat-label">{t('Seats')}</span>
            <span className="stat-value">{open.reduce((n, r) => n + r.capacity, 0)}</span>
          </div>
          {(['amphi', 'td', 'lab'] as const).map((ty) => (
            <div className="stat" key={ty}>
              <span className="stat-label">{roomType(ty)}</span>
              <span className="stat-value">{open.filter((r) => r.type === ty).length}</span>
            </div>
          ))}
        </div>
      )}
      {rooms.error && <ErrorBox error={rooms.error} onRetry={rooms.reload} />}
      {rooms.loading && !rooms.data && <div className="panel"><ListSkeleton /></div>}
      {rooms.data && (
        <section className="panel panel-tight">
          <div className="panel-head">
            <input className="input" type="search" placeholder={t('Search rooms')} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t('Search rooms')} />
          </div>
          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Room')}</th>
                  <th>{t('Type')}</th>
                  <th>{t('Seats')}</th>
                  <th>{t('Status')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id} className={r.active ? '' : 'is-off'}>
                    <td>
                      <strong>{r.name}</strong>
                    </td>
                    <td>{roomType(r.type)}</td>
                    <td className="num">{r.capacity}</td>
                    <td>{r.active ? <span className="badge badge-new">{t('Open')}</span> : <span className="badge badge-closed">{t('Closed')}</span>}</td>
                    <td className="actions">
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <button className={'btn btn-sm' + (r.active ? ' btn-danger' : '')} onClick={() => toggle(r)}>
                          {r.active ? t('Close') : t('Reopen')}
                        </button>
                        <button className="btn btn-sm" onClick={() => setEdit(r)}>
                          {t('Edit')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <RoomDialog room={edit} onClose={() => setEdit(null)} onSaved={rooms.reload} />
    </div>
  )
}

function RoomDialog({ room, onClose, onSaved }: { room: Partial<Room> | null; onClose: () => void; onSaved: () => void }) {
  const act = useAction()
  const [form, setForm] = useState<Partial<Room>>({})
  const [key, setKey] = useState<unknown>(null)
  if (room !== key) {
    setKey(room)
    setForm(room ?? {})
  }
  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const body = { name: form.name, type: form.type, capacity: Number(form.capacity), active: form.active ?? true }
    const ok = await act(() => (room?.id ? api.patch(`/admin/rooms/${room.id}`, body) : api.post('/admin/rooms', body)), t('Room saved'))
    if (ok) {
      onSaved()
      onClose()
    }
  }
  const remove = async () => {
    if (!room?.id || !confirm(t('Delete {name}? Its sessions will be removed from the timetable.', { name: room.name ?? '' }))) return
    if (await act(() => api.del(`/admin/rooms/${room.id}`), t('Room deleted'))) {
      onSaved()
      onClose()
    }
  }
  return (
    <Dialog open={!!room} onClose={onClose} title={room?.id ? t('Edit {name}', { name: room.name ?? '' }) : t('Add a room')}>
      <form className="stack-sm" onSubmit={submit}>
        <label className="field">
          {t('Name')}
          <input className="input" value={form.name ?? ''} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
        </label>
        <div className="form-grid">
          <label className="field">
            {t('Type')}
            <select className="select" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as Room['type'] })}>
              {(['amphi', 'td', 'lab'] as const).map((ty) => (
                <option key={ty} value={ty}>
                  {roomType(ty)}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            {t('Seats')}
            <input className="input" type="number" min={1} value={form.capacity ?? ''} onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })} required />
          </label>
        </div>
        <div className="row-between">
          {room?.id ? (
            <button type="button" className="btn btn-danger" onClick={remove}>
              {t('Delete')}
            </button>
          ) : (
            <span />
          )}
          <button className="btn btn-primary">{t('Save')}</button>
        </div>
      </form>
    </Dialog>
  )
}

// ------------------------------------------------------------------ levels
export function Levels() {
  const levels = useLoad<Level[]>('/admin/levels')
  const modules = useLoad<Module[]>('/admin/modules')
  const act = useAction()
  const [edit, setEdit] = useState<Partial<Level> | null>(null)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!edit) return
    const body = { name: edit.name, headcount: Number(edit.headcount) }
    const ok = await act(() => (edit.id ? api.patch(`/admin/levels/${edit.id}`, body) : api.post('/admin/levels', body)), t('Level saved'))
    if (ok) {
      setEdit(null)
      levels.reload()
    }
  }
  const remove = async (lv: Level) => {
    if (!confirm(t('Delete {name}, its modules and its groups?', { name: lv.name }))) return
    if (await act(() => api.del(`/admin/levels/${lv.id}`), t('Level deleted'))) levels.reload()
  }

  return (
    <div className="stack">
      <PageHead title={t('Levels and specialities')} intro={t('Each level with its number of students. Groups are built from these headcounts when the timetable is generated.')}>
        <button className="btn btn-primary" onClick={() => setEdit({ headcount: 60 })}>
          <Icon name="plus" /> {t('Add level')}
        </button>
      </PageHead>
      {levels.error && <ErrorBox error={levels.error} onRetry={levels.reload} />}
      {levels.loading && !levels.data && <div className="panel"><ListSkeleton /></div>}
      {levels.data && (
        <section className="panel panel-tight">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Level')}</th>
                  <th>{t('Students')}</th>
                  <th>{t('Modules')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {levels.data.map((lv) => (
                  <tr key={lv.id}>
                    <td>
                      <strong>{lv.name}</strong>
                    </td>
                    <td className="num">{lv.headcount}</td>
                    <td className="num">{modules.data?.filter((m) => m.level_id === lv.id).length ?? '…'}</td>
                    <td className="actions">
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <Link className="btn btn-sm" to={`/admin/modules?level=${lv.id}`}>
                          {t('Modules')}
                        </Link>
                        <button className="btn btn-sm" onClick={() => setEdit(lv)}>
                          {t('Edit')}
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => remove(lv)}>
                          {t('Delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {levels.data.length === 0 && <p className="muted small" style={{ padding: 20 }}>{t('No levels yet. Add one or import a file.')}</p>}
        </section>
      )}
      <Dialog open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? t('Edit {name}', { name: edit.name ?? '' }) : t('Add a level')}>
        {edit && (
          <form className="stack-sm" onSubmit={save}>
            <label className="field">
              {t('Name (level and speciality)')}
              <input className="input" placeholder={t('e.g. L3 ISIL')} value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} required />
            </label>
            <label className="field">
              {t('Number of students')}
              <input className="input" type="number" min={1} value={edit.headcount ?? ''} onChange={(e) => setEdit({ ...edit, headcount: Number(e.target.value) })} required />
            </label>
            <button className="btn btn-primary" style={{ alignSelf: 'end' }}>
              {t('Save')}
            </button>
          </form>
        )}
      </Dialog>
    </div>
  )
}

// ------------------------------------------------------------------ modules
export function Modules() {
  const levels = useLoad<Level[]>('/admin/levels')
  const modules = useLoad<Module[]>('/admin/modules')
  const act = useAction()
  const [level, setLevel] = useState(() => new URLSearchParams(location.search).get('level') ?? '')
  const [edit, setEdit] = useState<Partial<Module> | null>(null)
  const levelName = (id: number) => levels.data?.find((l) => l.id === id)?.name ?? '?'
  const list = (modules.data ?? []).filter((m) => !level || String(m.level_id) === level)

  const save = async (e: FormEvent) => {
    e.preventDefault()
    if (!edit) return
    const body = {
      level_id: Number(edit.level_id),
      name: edit.name,
      lecture_per_week: Number(edit.lecture_per_week ?? 0),
      td_per_week: Number(edit.td_per_week ?? 0),
      tp_per_week: Number(edit.tp_per_week ?? 0),
    }
    const ok = await act(() => (edit.id ? api.patch(`/admin/modules/${edit.id}`, body) : api.post('/admin/modules', body)), t('Module saved'))
    if (ok) {
      setEdit(null)
      modules.reload()
    }
  }
  const remove = async (m: Module) => {
    if (!confirm(t('Delete {name}?', { name: m.name }))) return
    if (await act(() => api.del(`/admin/modules/${m.id}`), t('Module deleted'))) modules.reload()
  }

  return (
    <div className="stack">
      <PageHead title={t('Modules')} intro={t('Weekly load of each module, counted in sessions (one time slot each): lectures for the whole section, TD and TP per group.')}>
        <button
          className="btn btn-primary"
          disabled={!levels.data?.length}
          onClick={() => setEdit({ level_id: Number(level) || levels.data?.[0]?.id, lecture_per_week: 1, td_per_week: 1, tp_per_week: 0 })}
        >
          <Icon name="plus" /> {t('Add module')}
        </button>
      </PageHead>
      <div className="row">
        <select className="select" value={level} onChange={(e) => setLevel(e.target.value)} aria-label={t('Filter by level')}>
          <option value="">{t('All levels')}</option>
          {levels.data?.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </select>
        <span className="small muted">{t('{n} modules', { n: list.length })}</span>
      </div>
      {modules.error && <ErrorBox error={modules.error} onRetry={modules.reload} />}
      {modules.loading && !modules.data && <div className="panel"><ListSkeleton /></div>}
      {modules.data && (
        <section className="panel panel-tight">
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Module')}</th>
                  <th>{t('Level')}</th>
                  <th>{t('Lectures / week')}</th>
                  <th>{t('TD / week')}</th>
                  <th>{t('TP / week')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {list.map((m) => (
                  <tr key={m.id}>
                    <td>
                      <strong>{m.name}</strong>
                    </td>
                    <td>{levelName(m.level_id)}</td>
                    <td className="num">{m.lecture_per_week}</td>
                    <td className="num">{m.td_per_week}</td>
                    <td className="num">{m.tp_per_week}</td>
                    <td className="actions">
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <button className="btn btn-sm" onClick={() => setEdit(m)}>
                          {t('Edit')}
                        </button>
                        <button className="btn btn-sm btn-danger" onClick={() => remove(m)}>
                          {t('Delete')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <Dialog open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? t('Edit {name}', { name: edit.name ?? '' }) : t('Add a module')}>
        {edit && (
          <form className="stack-sm" onSubmit={save}>
            <label className="field">
              {t('Name')}
              <input className="input" value={edit.name ?? ''} onChange={(e) => setEdit({ ...edit, name: e.target.value })} required />
            </label>
            <label className="field">
              {t('Level')}
              <select className="select" value={edit.level_id} onChange={(e) => setEdit({ ...edit, level_id: Number(e.target.value) })}>
                {levels.data?.map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="form-grid">
              {(['lecture_per_week', 'td_per_week', 'tp_per_week'] as const).map((k) => (
                <label className="field" key={k}>
                  {k === 'lecture_per_week' ? t('Lectures per week') : k === 'td_per_week' ? t('TD per week') : t('TP per week')}
                  <input className="input" type="number" min={0} value={edit[k] ?? 0} onChange={(e) => setEdit({ ...edit, [k]: Number(e.target.value) })} />
                </label>
              ))}
            </div>
            <button className="btn btn-primary" style={{ alignSelf: 'end' }}>
              {t('Save')}
            </button>
          </form>
        )}
      </Dialog>
    </div>
  )
}

// ------------------------------------------------------------------ professors
export function Professors() {
  const profs = useLoad<Professor[]>('/admin/professors')
  const modules = useLoad<Module[]>('/admin/modules')
  const levels = useLoad<Level[]>('/admin/levels')
  const act = useAction()
  const [edit, setEdit] = useState<Partial<Professor> | null>(null)
  const [avail, setAvail] = useState<Professor | null>(null)
  const [creds, setCreds] = useState<Credential[] | null>(null)
  const [query, setQuery] = useState('')
  const moduleName = useCallback(
    (id: number) => {
      const m = modules.data?.find((x) => x.id === id)
      if (!m) return '?'
      return `${m.name} (${levels.data?.find((l) => l.id === m.level_id)?.name ?? ''})`
    },
    [modules.data, levels.data],
  )
  const list = (profs.data ?? []).filter((p) => p.name.toLowerCase().includes(query.toLowerCase()))

  const reset = async (p: Professor) => {
    if (!confirm(t('Give {name} a new password? The old one stops working.', { name: p.name }))) return
    await act(async () => {
      const r = await api.post<{ username: string; password: string }>(`/admin/professors/${p.id}/reset-password`)
      setCreds([{ name: p.name, ...r }])
    })
  }

  return (
    <div className="stack">
      <PageHead title={t('Professors')} intro={t('Who teaches what (in order of preference), their weekly maximum, and their availability.')}>
        <button className="btn btn-primary" onClick={() => setEdit({ teaches: [] })}>
          <Icon name="plus" /> {t('Add professor')}
        </button>
      </PageHead>
      {profs.error && <ErrorBox error={profs.error} onRetry={profs.reload} />}
      {profs.loading && !profs.data && <div className="panel"><ListSkeleton /></div>}
      {profs.data && (
        <section className="panel panel-tight">
          <div className="panel-head">
            <input className="input" type="search" placeholder={t('Search professors')} value={query} onChange={(e) => setQuery(e.target.value)} aria-label={t('Search professors')} />
            <span className="small muted">
              {t('{n} professors · {m} filled their availability', { n: profs.data.length, m: profs.data.filter((p) => p.availability_filled).length })}
            </span>
          </div>
          <div className="table-wrap" style={{ marginTop: 16 }}>
            <table className="table">
              <thead>
                <tr>
                  <th>{t('Name')}</th>
                  <th>{t('Login')}</th>
                  <th>{t('Max / week')}</th>
                  <th>{t('Teaches (1st choice first)')}</th>
                  <th>{t('Availability')}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {list.map((p) => (
                  <tr key={p.id}>
                    <td>
                      <strong>{p.name}</strong>
                    </td>
                    <td>
                      <span className="code">{p.username}</span>
                    </td>
                    <td className="num">{p.max_sessions}</td>
                    <td className="small">
                      {p.teaches.length === 0 && <span className="muted">{t('Nothing yet')}</span>}
                      {p.teaches.map((tc) => (
                        <div key={tc.module_id}>
                          {tc.rank}. {moduleName(tc.module_id)} · {tc.kinds.map((k) => kindLabel(k)).join(', ')}
                        </div>
                      ))}
                    </td>
                    <td>{p.availability_filled ? <span className="badge badge-new">{t('Filled')}</span> : <span className="badge badge-neutral">{t('Not yet')}</span>}</td>
                    <td className="actions">
                      <div className="row" style={{ justifyContent: 'flex-end' }}>
                        <button className="btn btn-sm" onClick={() => setEdit(p)}>
                          {t('Edit')}
                        </button>
                        <button className="btn btn-sm" onClick={() => setAvail(p)}>
                          {t('Availability')}
                        </button>
                        <button className="btn btn-sm" onClick={() => reset(p)}>
                          {t('New password')}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <ProfessorDialog
        prof={edit}
        modules={modules.data ?? []}
        moduleName={moduleName}
        onClose={() => setEdit(null)}
        onSaved={(c) => {
          profs.reload()
          if (c) setCreds(c)
        }}
      />
      <Dialog open={!!avail} onClose={() => setAvail(null)} title={t('Availability of {name}', { name: avail?.name ?? '' })} wide>
        {avail && <ProfAvailability prof={avail} onSaved={profs.reload} />}
      </Dialog>
      <Dialog open={!!creds} onClose={() => setCreds(null)} title={t('Login to give to the professor')} wide>
        {creds && <CredentialsTable rows={creds} />}
      </Dialog>
    </div>
  )
}

function ProfAvailability({ prof, onSaved }: { prof: Professor; onSaved: () => void }) {
  const load = useCallback(() => api.get<Availability>(`/admin/professors/${prof.id}/availability`), [prof.id])
  const save = useCallback(
    async (a: Availability) => {
      const r = await api.put<Availability>(`/admin/professors/${prof.id}/availability`, a)
      onSaved()
      return r
    },
    [prof.id, onSaved],
  )
  return <AvailabilityEditor load={load} save={save} intro={t("Fill the grid on the professor's behalf (for example from their paper form).")} />
}

function ProfessorDialog({
  prof,
  modules,
  moduleName,
  onClose,
  onSaved,
}: {
  prof: Partial<Professor> | null
  modules: Module[]
  moduleName: (id: number) => string
  onClose: () => void
  onSaved: (credentials?: Credential[]) => void
}) {
  const act = useAction()
  const [name, setName] = useState('')
  const [max, setMax] = useState('')
  const [teaches, setTeaches] = useState<Teaching[]>([])
  const [adding, setAdding] = useState('')
  const [key, setKey] = useState<unknown>(null)
  if (prof !== key) {
    setKey(prof)
    setName(prof?.name ?? '')
    setMax(prof?.max_sessions ? String(prof.max_sessions) : '')
    setTeaches([...(prof?.teaches ?? [])].sort((a, b) => a.rank - b.rank))
    setAdding('')
  }
  const available = useMemo(() => modules.filter((m) => !teaches.some((t) => t.module_id === m.id)), [modules, teaches])

  const move = (i: number, d: number) => {
    const next = [...teaches]
    const [x] = next.splice(i, 1)
    next.splice(i + d, 0, x)
    setTeaches(next)
  }
  const toggleKind = (i: number, k: Kind) =>
    setTeaches(teaches.map((t, j) => (j !== i ? t : { ...t, kinds: t.kinds.includes(k) ? t.kinds.filter((x) => x !== k) : [...t.kinds, k] })))

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const body = {
      name,
      max_sessions: max ? Number(max) : null,
      teaches: teaches.filter((t) => t.kinds.length).map((t, i) => ({ ...t, rank: i + 1 })),
    }
    await act(async () => {
      if (prof?.id) {
        await api.patch(`/admin/professors/${prof.id}`, body)
        onSaved()
      } else {
        const r = await api.post<Professor & { password: string }>('/admin/professors', body)
        onSaved([{ name: r.name, username: r.username ?? '', password: r.password }])
      }
      onClose()
    }, t('Professor saved'))
  }
  const remove = async () => {
    if (!prof?.id || !confirm(t('Delete {name}? Their sessions will be removed from the timetable.', { name: prof.name ?? '' }))) return
    if (await act(() => api.del(`/admin/professors/${prof.id}`), t('Professor deleted'))) {
      onSaved()
      onClose()
    }
  }

  return (
    <Dialog open={!!prof} onClose={onClose} title={prof?.id ? t('Edit {name}', { name: prof.name ?? '' }) : t('Add a professor')} wide>
      <form className="stack-sm" onSubmit={submit}>
        <div className="form-grid">
          <label className="field" style={{ gridColumn: 'span 2' }}>
            {t('Full name')}
            <input className="input" value={name} onChange={(e) => setName(e.target.value)} required />
          </label>
          <label className="field">
            {t('Max sessions per week')}
            <input className="input" type="number" min={1} placeholder={t('Department default')} value={max} onChange={(e) => setMax(e.target.value)} />
          </label>
        </div>
        <h3>{t('Teaches, in order of preference')}</h3>
        <p className="small muted">{t('The first module is their first choice. The timetable tries to give each professor their preferred modules.')}</p>
        {teaches.length === 0 && <p className="small muted">{t('No module yet.')}</p>}
        <ol className="options">
          {teaches.map((tc, i) => (
            <li key={tc.module_id} className="option" style={{ gridTemplateColumns: 'auto 1fr auto' }}>
              <span className="option-rank">{i + 1}</span>
              <div className="stack-sm" style={{ gap: 4 }}>
                <strong>{moduleName(tc.module_id)}</strong>
                <div className="row">
                  {KINDS.map((k) => (
                    <label key={k} className="check">
                      <input type="checkbox" checked={tc.kinds.includes(k)} onChange={() => toggleKind(i, k)} /> {kindLabel(k)}
                    </label>
                  ))}
                </div>
              </div>
              <div className="row" style={{ gap: 4 }}>
                <button type="button" className="btn btn-sm" disabled={i === 0} onClick={() => move(i, -1)} aria-label={t('Move up')}>
                  ↑
                </button>
                <button type="button" className="btn btn-sm" disabled={i === teaches.length - 1} onClick={() => move(i, 1)} aria-label={t('Move down')}>
                  ↓
                </button>
                <button type="button" className="btn btn-sm btn-danger" onClick={() => setTeaches(teaches.filter((_, j) => j !== i))} aria-label={t('Remove')}>
                  ✕
                </button>
              </div>
            </li>
          ))}
        </ol>
        <div className="row">
          <select className="select" value={adding} onChange={(e) => setAdding(e.target.value)} style={{ flex: 1 }} aria-label={t('Module to add')}>
            <option value="">{t('Add a module…')}</option>
            {available.map((m) => (
              <option key={m.id} value={m.id}>
                {moduleName(m.id)}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn"
            disabled={!adding}
            onClick={() => {
              setTeaches([...teaches, { module_id: Number(adding), kinds: ['lecture', 'td', 'tp'], rank: teaches.length + 1 }])
              setAdding('')
            }}
          >
            {t('Add')}
          </button>
        </div>
        <div className="row-between" style={{ marginTop: 8 }}>
          {prof?.id ? (
            <button type="button" className="btn btn-danger" onClick={remove}>
              {t('Delete')}
            </button>
          ) : (
            <span />
          )}
          <button className="btn btn-primary">{t('Save')}</button>
        </div>
      </form>
    </Dialog>
  )
}

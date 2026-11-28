import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { ImportField, ImportPreview, ImportResult } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { CredentialsTable, ErrorBox, Icon, Progress, useElapsed } from '../../components/ui'
import { errorText, useLoad, useToast } from '../../lib/hooks'
import { t } from '../../lib/i18n'

type ImportKind = 'levels' | 'rooms' | 'modules' | 'professors'

const KINDS: { kind: ImportKind; title: string; hint: string }[] = [
  { kind: 'levels', title: 'Levels', hint: 'Level / speciality and number of students' },
  { kind: 'rooms', title: 'Rooms', hint: 'Room name, type and number of seats' },
  { kind: 'modules', title: 'Modules', hint: 'Level, module, lectures / TD / TP per week' },
  { kind: 'professors', title: 'Professors', hint: 'Name, modules in order of preference (fiche de vœux), max load' },
]

/** Field names as the admin reads them. */
const FIELD_LABEL: Record<string, string> = {
  name: 'Name', type: 'Type', capacity: 'Seats', headcount: 'Students', year: 'Year', speciality: 'Speciality',
  level: 'Level', lecture: 'Lectures per week', td: 'TD per week', tp: 'TP per week', max_sessions: 'Max sessions per week',
  modules: 'Modules', kinds: 'Lecture / TD / TP', rank: 'Order of preference',
}
const fieldLabel = (f: string) => t(FIELD_LABEL[f] ?? f)
const READ_STEPS = ['Reading the file', 'Matching its columns', 'Preparing the preview']

const METHOD: Record<string, string> = {
  dictionary: 'known column name',
  llm: 'AI suggestion',
  admin: 'your choice',
}

export function Import() {
  const toast = useToast()
  const fields = useLoad<Record<ImportKind, Record<string, ImportField>>>('/admin/import/kinds')
  const [kind, setKind] = useState<ImportKind>('levels')
  const [file, setFile] = useState<File | null>(null)
  const [overrides, setOverrides] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [rows, setRows] = useState<Record<string, unknown>[]>([])
  const [result, setResult] = useState<ImportResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const step = result ? 3 : preview ? 2 : 1
  const elapsed = useElapsed(busy && step === 1)
  const readStep = elapsed < 0.6 ? 0 : elapsed < 2.5 ? 1 : 2

  const runPreview = async (f: File, ov: Record<string, string>) => {
    setBusy(true)
    setError(null)
    const form = new FormData()
    form.append('kind', kind)
    form.append('file', f)
    if (Object.keys(ov).length) form.append('column_overrides', JSON.stringify(ov))
    try {
      const p = await api.post<ImportPreview>('/admin/import/preview', form)
      setPreview(p)
      setRows(p.rows)
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const commit = async () => {
    setBusy(true)
    try {
      const cleaned = rows.map((r) =>
        kind === 'professors' && typeof r.modules === 'string'
          ? { ...r, modules: (r.modules as string).split(/[;,]/).map((s) => s.trim()).filter(Boolean) }
          : r,
      )
      const r = await api.post<ImportResult>('/admin/import/commit', { kind, rows: cleaned })
      setResult(r)
      toast(t('Imported: {created} new, {updated} updated', { created: r.created, updated: r.updated }))
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy(false)
    }
  }

  const restart = (k: ImportKind = kind) => {
    setKind(k)
    setFile(null)
    setPreview(null)
    setRows([])
    setResult(null)
    setOverrides({})
    setError(null)
  }

  const columns = preview ? Object.keys(fields.data?.[kind] ?? {}) : []
  const nextKind = KINDS[KINDS.findIndex((k) => k.kind === kind) + 1]?.kind

  return (
    <div className="stack">
      <PageHead
        title={t('Import files')}
        intro={t("Use the department's existing files as they are: Excel, CSV or PDF tables, in French, English or Arabic. Nothing is saved before you check the preview.")}
      />
      <ol className="steps" aria-label={t('Steps')}>
        {['Choose a file', 'Check the preview', 'Done'].map((s, i) => (
          <li key={s} className={step >= i + 1 ? 'on' : ''}>
            <span>{step > i + 1 ? <Icon name="check" size={14} /> : i + 1}</span>
            {t(s)}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <section className="panel stack-sm">
          <h2>{t('What does the file contain?')}</h2>
          <p className="small muted">{t('Import in this order: levels, then rooms, modules, and professors last (they refer to modules).')}</p>
          <div className="form-grid" role="radiogroup">
            {KINDS.map((k, i) => (
              <label key={k.kind} className={'option' + (kind === k.kind ? ' best' : '')} style={{ gridTemplateColumns: 'auto 1fr', cursor: 'pointer' }}>
                <input type="radio" name="kind" checked={kind === k.kind} onChange={() => restart(k.kind)} />
                <span>
                  <strong>
                    {i + 1}. {t(k.title)}
                  </strong>
                  <br />
                  <span className="small muted">{t(k.hint)}</span>
                </span>
              </label>
            ))}
          </div>
          <label className={'field dropzone' + (busy ? ' busy' : '')} style={{ marginTop: 8 }}>
            <span className="dropzone-text">
              <Icon name="upload" size={22} />
              <strong>{t('Choose or drop a file')}</strong>
              <span className="small muted">Excel, CSV, PDF · 10 MB max</span>
            </span>
            <input
              className="input"
              style={{ paddingTop: 7 }}
              type="file"
              accept=".xlsx,.xlsm,.xls,.csv,.txt,.pdf"
              onChange={(e) => {
                const f = e.target.files?.[0] ?? null
                setFile(f)
                if (f) runPreview(f, {})
              }}
            />
          </label>
          {busy && (
            <Progress
              value={null}
              steps={READ_STEPS.map((x) => t(x))}
              current={readStep}
              note={t('Unusual column names are read by a small AI model on the server. It can take a few seconds the first time.')}
            />
          )}
          {fields.data && (
            <p className="tiny muted">
              {t('Expected columns: {list}', {
                list: Object.entries(fields.data[kind])
                  .map(([f, sp]) => `${fieldLabel(f)}${sp.required ? ` (${t('required')})` : ''}`)
                  .join(', '),
              })}
            </p>
          )}
        </section>
      )}
      {error && <ErrorBox error={error} />}

      {step === 2 && preview && (
        <>
          <section className="panel stack-sm">
            <div className="row-between">
              <h2>{t('Detected columns in {file}', { file: preview.filename })}</h2>
              <button className="btn btn-sm" onClick={() => restart()}>
                {t('Choose another file')}
              </button>
            </div>
            <p className="small muted">{t('Each field of the app was matched to a column of your file. Fix any wrong match: the preview updates.')}</p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>{t('Field')}</th>
                    <th>{t('Column in your file')}</th>
                    <th>{t('How it was matched')}</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(fields.data?.[kind] ?? {}).map(([f, spec]) => {
                    const m = preview.mapping[f]
                    return (
                      <tr key={f}>
                        <td>
                          <strong>{fieldLabel(f)}</strong> {spec.required && <span className="tiny muted">{t('required')}</span>}
                        </td>
                        <td>
                          <select
                            className="select input-sm"
                            value={m?.column ?? ''}
                            onChange={(e) => {
                              const ov = { ...overrides, [f]: e.target.value }
                              setOverrides(ov)
                              if (file && e.target.value) runPreview(file, ov)
                            }}
                          >
                            <option value="">{t('(not in the file)')}</option>
                            {preview.columns.filter(Boolean).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="small">
                          {m ? (
                            <>
                              <span className={'badge ' + (m.method === 'llm' ? 'badge-ai' : 'badge-neutral')}>
                                {m.method === 'llm' && <Icon name="sparkle" size={12} />} {t(METHOD[m.method] ?? m.method)}
                              </span>
                              {m.confidence < 1 && <span className="muted"> · {t('{n}% sure', { n: Math.round(m.confidence * 100) })}</span>}
                            </>
                          ) : spec.required ? (
                            <span className="badge badge-cancelled">{t('Missing')}</span>
                          ) : (
                            <span className="muted">{t('optional')}</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {preview.unmapped_columns.length > 0 && <p className="tiny muted">{t('Ignored columns: {list}', { list: preview.unmapped_columns.join(', ') })}</p>}
          </section>

          {preview.warnings.length > 0 && (
            <div className="callout callout-warn">
              <div>
                {t('{n} line(s) to check:', { n: preview.warnings.length })}
                <ul>
                  {preview.warnings.slice(0, 8).map((w) => (
                    <li key={w}>{w}</li>
                  ))}
                </ul>
              </div>
            </div>
          )}

          <section className="panel panel-tight">
            <div className="panel-head">
              <h2>{t('{n} rows to import', { n: rows.length })}</h2>
              <span className="small muted">{t('Click a value to correct it before saving.')}</span>
            </div>
            <div className="table-wrap" style={{ maxHeight: 480, marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{fieldLabel(c)}</th>
                    ))}
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i}>
                      {columns.map((c) => (
                        <td key={c}>
                          <input
                            className="input input-sm"
                            style={{ width: '100%', minWidth: c === 'name' || c === 'modules' ? 180 : 70 }}
                            value={Array.isArray(r[c]) ? (r[c] as string[]).join(', ') : String(r[c] ?? '')}
                            onChange={(e) => setRows(rows.map((x, j) => (j === i ? { ...x, [c]: e.target.value } : x)))}
                            aria-label={t('{field}, row {n}', { field: fieldLabel(c), n: i + 1 })}
                          />
                        </td>
                      ))}
                      <td className="actions">
                        <button className="btn btn-sm btn-ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={t('Remove row {n}', { n: i + 1 })}>
                          ✕
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <div className="row-between">
            {!preview.ready && (
              <span className="small" style={{ color: 'var(--bad)' }}>
                {t('Required field(s) missing: {list}. Pick their column above.', { list: preview.missing_required.map(fieldLabel).join(', ') })}
              </span>
            )}
            <span />
            <button className="btn btn-primary btn-lg" disabled={busy || !preview.ready || !rows.length} onClick={commit}>
              {busy && <span className="spinner" />} {t('Save {n} rows', { n: rows.length })}
            </button>
          </div>
        </>
      )}

      {step === 3 && result && (
        <section className="panel stack-sm">
          <div className="callout callout-ok">
            <Icon name="check" />
            <span>
              {t('Saved: {created} new, {updated} updated, {skipped} skipped. Importing the same file again updates the data instead of duplicating it.', {
                created: result.created,
                updated: result.updated,
                skipped: result.skipped,
              })}
            </span>
          </div>
          {result.warnings.length > 0 && (
            <div className="callout callout-warn">
              <ul>
                {result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </div>
          )}
          {result.credentials.length > 0 && <CredentialsTable rows={result.credentials} />}
          <div className="row">
            {nextKind && (
              <button className="btn btn-primary" onClick={() => restart(nextKind)}>
                {t('Next: import {what}', { what: t(KINDS.find((k) => k.kind === nextKind)?.title ?? '').toLowerCase() })}
              </button>
            )}
            {!nextKind && (
              <Link to="/admin/timetable" className="btn btn-primary">
                <Icon name="sparkle" /> {t('Generate the timetable')}
              </Link>
            )}
            <button className="btn" onClick={() => restart()}>
              {t('Import another file of the same kind')}
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

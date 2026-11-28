import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { ImportField, ImportPreview, ImportResult } from '../../api/types'
import { PageHead } from '../../components/Layout'
import { CredentialsTable, ErrorBox, Icon, Loading } from '../../components/ui'
import { errorText, useLoad, useToast } from '../../lib/hooks'

type ImportKind = 'levels' | 'rooms' | 'modules' | 'professors'

const KINDS: { kind: ImportKind; title: string; hint: string }[] = [
  { kind: 'levels', title: 'Levels', hint: 'Level / speciality and number of students' },
  { kind: 'rooms', title: 'Rooms', hint: 'Room name, type and number of seats' },
  { kind: 'modules', title: 'Modules', hint: 'Level, module, lectures / TD / TP per week' },
  { kind: 'professors', title: 'Professors', hint: 'Name, modules in order of preference (fiche de vœux), max load' },
]

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
      toast(`Imported: ${r.created} new, ${r.updated} updated`)
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
        title="Import files"
        intro="Use the department's existing files as they are: Excel, CSV or PDF tables, in French, English or Arabic. Nothing is saved before you check the preview."
      />
      <ol className="steps" aria-label="Steps">
        {['Choose a file', 'Check the preview', 'Done'].map((s, i) => (
          <li key={s} className={step >= i + 1 ? 'on' : ''}>
            <span>{i + 1}</span>
            {s}
          </li>
        ))}
      </ol>

      {step === 1 && (
        <section className="panel stack-sm">
          <h2>What does the file contain?</h2>
          <p className="small muted">Import in this order: levels, then rooms, modules, and professors last (they refer to modules).</p>
          <div className="form-grid" role="radiogroup">
            {KINDS.map((k, i) => (
              <label key={k.kind} className={'option' + (kind === k.kind ? ' best' : '')} style={{ gridTemplateColumns: 'auto 1fr', cursor: 'pointer' }}>
                <input type="radio" name="kind" checked={kind === k.kind} onChange={() => restart(k.kind)} />
                <span>
                  <strong>
                    {i + 1}. {k.title}
                  </strong>
                  <br />
                  <span className="small muted">{k.hint}</span>
                </span>
              </label>
            ))}
          </div>
          <label className="field" style={{ marginTop: 8 }}>
            File (.xlsx, .csv, .pdf)
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
          {busy && <Loading text="Reading the file and matching its columns…" />}
          {fields.data && (
            <p className="tiny muted">
              Expected columns: {Object.entries(fields.data[kind]).map(([f, s]) => `${f}${s.required ? ' (required)' : ''}`).join(', ')}
            </p>
          )}
        </section>
      )}
      {error && <ErrorBox error={error} />}

      {step === 2 && preview && (
        <>
          <section className="panel stack-sm">
            <div className="row-between">
              <h2>Detected columns in {preview.filename}</h2>
              <button className="btn btn-sm" onClick={() => restart()}>
                Choose another file
              </button>
            </div>
            <p className="small muted">Each field of the app was matched to a column of your file. Fix any wrong match: the preview updates.</p>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Field</th>
                    <th>Column in your file</th>
                    <th>How it was matched</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(fields.data?.[kind] ?? {}).map(([f, spec]) => {
                    const m = preview.mapping[f]
                    return (
                      <tr key={f}>
                        <td>
                          <strong>{f}</strong> {spec.required && <span className="tiny muted">required</span>}
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
                            <option value="">(not in the file)</option>
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
                              {METHOD[m.method] ?? m.method}
                              {m.confidence < 1 && <span className="muted"> · {Math.round(m.confidence * 100)}% sure</span>}
                            </>
                          ) : spec.required ? (
                            <span className="badge badge-cancelled">Missing</span>
                          ) : (
                            <span className="muted">optional</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {preview.unmapped_columns.length > 0 && <p className="tiny muted">Ignored columns: {preview.unmapped_columns.join(', ')}</p>}
          </section>

          {preview.warnings.length > 0 && (
            <div className="callout callout-warn">
              <div>
                {preview.warnings.length} line(s) to check:
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
              <h2>{rows.length} rows to import</h2>
              <span className="small muted">Click a value to correct it before saving.</span>
            </div>
            <div className="table-wrap" style={{ maxHeight: 480, marginTop: 12 }}>
              <table className="table">
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <th key={c}>{c}</th>
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
                            aria-label={`${c}, row ${i + 1}`}
                          />
                        </td>
                      ))}
                      <td className="actions">
                        <button className="btn btn-sm btn-ghost" onClick={() => setRows(rows.filter((_, j) => j !== i))} aria-label={`Remove row ${i + 1}`}>
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
                Required field(s) missing: {preview.missing_required.join(', ')}. Pick their column above.
              </span>
            )}
            <span />
            <button className="btn btn-primary btn-lg" disabled={busy || !preview.ready || !rows.length} onClick={commit}>
              {busy && <span className="spinner" />} Save {rows.length} rows
            </button>
          </div>
        </>
      )}

      {step === 3 && result && (
        <section className="panel stack-sm">
          <div className="callout callout-ok">
            Saved: {result.created} new, {result.updated} updated{result.skipped ? `, ${result.skipped} skipped` : ''}. Importing the same file
            again updates the data instead of duplicating it.
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
                Next: import {nextKind}
              </button>
            )}
            {!nextKind && (
              <Link to="/admin/timetable" className="btn btn-primary">
                <Icon name="sparkle" /> Generate the timetable
              </Link>
            )}
            <button className="btn" onClick={() => restart()}>
              Import another {kind} file
            </button>
          </div>
        </section>
      )}
    </div>
  )
}

import { useEffect, useRef, type ReactNode } from 'react'
import { timeAgo } from '../lib/dates'

// ------------------------------------------------------------------ icons (stroke, 18px)
const paths: Record<string, ReactNode> = {
  calendar: (
    <>
      <rect x="3" y="4.5" width="18" height="16" rx="2" />
      <path d="M3 9.5h18M8 2.5v4M16 2.5v4" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </>
  ),
  door: (
    <>
      <path d="M5 21V4a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v17M3 21h18" />
      <circle cx="15" cy="12" r="1" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 13 9 5 9-5" />
    </>
  ),
  book: (
    <>
      <path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5Z" />
      <path d="M4 19a2 2 0 0 1 2-2h13" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0 1 13 0M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" />
    </>
  ),
  upload: (
    <>
      <path d="M12 16V4M7 9l5-5 5 5" />
      <path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.3 5.3l2.1 2.1M16.6 16.6l2.1 2.1M5.3 18.7l2.1-2.1M16.6 7.4l2.1-2.1" />
    </>
  ),
  history: (
    <>
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
      <path d="M3 3v5h5M12 7v5l3 2" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  sparkle: <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  left: <path d="m15 18-6-6 6-6" />,
  right: <path d="m9 18 6-6-6-6" />,
  download: (
    <>
      <path d="M12 4v12M7 11l5 5 5-5" />
      <path d="M4 20h16" />
    </>
  ),
  logout: (
    <>
      <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
      <path d="M10 17l-5-5 5-5M5 12h11" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  share: (
    <>
      <circle cx="18" cy="5" r="2.5" />
      <circle cx="6" cy="12" r="2.5" />
      <circle cx="18" cy="19" r="2.5" />
      <path d="m8.2 10.8 7.6-4.4M8.2 13.2l7.6 4.4" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.5" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
}

export function Icon({ name, size = 18 }: { name: keyof typeof paths | string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeLinecap="round">
        <rect x="3.5" y="5" width="17" height="15" rx="2" />
        <path d="M3.5 10h17M8.5 3v4M15.5 3v4" />
        <path d="M8 14h3M13 14h3M8 17h3" stroke="oklch(0.82 0.16 75)" />
      </svg>
    </span>
  )
}

// ------------------------------------------------------------------ states
export function Loading({ text = 'Loading…' }: { text?: string }) {
  return (
    <div className="loading" role="status">
      <span className="spinner" /> {text}
    </div>
  )
}

export function ErrorBox({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <div className="callout callout-bad" role="alert">
      <div className="stack-sm" style={{ gap: 8 }}>
        <span>{error}</span>
        {onRetry && (
          <button className="btn btn-sm" onClick={onRetry} style={{ alignSelf: 'start' }}>
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

/** Shown when the page displays the copy saved for offline use. */
export function SavedCopyNote({ savedAt }: { savedAt: string | null }) {
  if (!savedAt) return null
  return (
    <div className="callout callout-warn" role="status">
      Offline: showing the copy saved {timeAgo(savedAt)}. It updates as soon as the connection returns.
    </div>
  )
}

// ------------------------------------------------------------------ dialog
export function Dialog({
  open,
  onClose,
  title,
  children,
  wide = false,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  wide?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const d = ref.current
    if (!d) return
    if (open && !d.open) d.showModal()
    if (!open && d.open) d.close()
  }, [open])
  return (
    <dialog
      ref={ref}
      className={'dialog' + (wide ? ' dialog-wide' : '')}
      onClose={onClose}
      onClick={(e) => e.target === ref.current && onClose()}
      aria-label={title}
    >
      {open && (
        <div className="dialog-body">
          <div className="row-between">
            <h2>{title}</h2>
            <button className="btn btn-ghost icon-btn" onClick={onClose} aria-label="Close">
              ✕
            </button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  )
}

export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {note && <span className="stat-note">{note}</span>}
    </div>
  )
}

/** One-time passwords: shown once, with a copy button. */
export function CredentialsTable({ rows }: { rows: { name: string; username: string; password: string }[] }) {
  const text = rows.map((r) => `${r.name}\t${r.username}\t${r.password}`).join('\n')
  return (
    <div className="stack-sm">
      <div className="callout callout-warn">
        These passwords are shown only once. Copy them now and give each professor their own login.
      </div>
      <div className="table-wrap" style={{ maxHeight: 320 }}>
        <table className="table">
          <thead>
            <tr>
              <th>Professor</th>
              <th>Username</th>
              <th>Password</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.username}>
                <td>{r.name}</td>
                <td>
                  <span className="code">{r.username}</span>
                </td>
                <td>
                  <span className="code">{r.password}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="btn" style={{ alignSelf: 'start' }} onClick={() => navigator.clipboard?.writeText(text)}>
        Copy all
      </button>
    </div>
  )
}

import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, setAuth } from '../api/client'
import { useAuth, useConfig, useNetwork } from '../lib/hooks'
import { BrandMark, Icon } from './ui'

export interface NavItem {
  to: string
  label: string
  icon: string
  end?: boolean
}

export function Brand() {
  const cfg = useConfig()
  return (
    <Link to="/" className="brand">
      <BrandMark />
      <span>{cfg.data?.app_name ?? 'Timetables'}</span>
    </Link>
  )
}

/** Connection banner: offline, or actions waiting to be sent. */
export function NetBar() {
  const { online, pending } = useNetwork()
  if (online && !pending) return null
  return (
    <div className="netbar" role="status">
      {!online && 'No connection. Your saved timetable is still available. '}
      {pending > 0 &&
        `${pending} action${pending > 1 ? 's' : ''} waiting to be sent${online ? '…' : ' when the connection returns.'}`}
    </div>
  )
}

/** Sidebar layout for the admin and professor spaces. */
export function Shell({ sections }: { sections: { label: string; items: NavItem[] }[] }) {
  const auth = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [open, setOpen] = useState(false)
  useEffect(() => setOpen(false), [location.pathname])

  const logout = async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      /* already logged out or offline: forget the token anyway */
    }
    setAuth(null)
    navigate('/')
  }

  return (
    <div className="shell">
      <aside className={'sidebar' + (open ? ' open' : '')} aria-label="Main menu">
        <Brand />
        {sections.map((sec) => (
          <nav className="nav-group" key={sec.label} aria-label={sec.label}>
            <span className="nav-label">{sec.label}</span>
            {sec.items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.end} className="nav-link">
                <Icon name={it.icon} />
                {it.label}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="sidebar-foot">
          <div className="who">
            <strong>{auth?.username}</strong>
            <span>{auth?.role === 'admin' ? 'Administrator' : 'Professor'}</span>
          </div>
          <button className="nav-link btn-ghost" style={{ border: 0, background: 'none', cursor: 'pointer' }} onClick={logout}>
            <Icon name="logout" /> Log out
          </button>
        </div>
      </aside>
      <div style={{ minWidth: 0 }} onClick={() => open && setOpen(false)}>
        <header className="topbar">
          <Brand />
          <button
            className="btn icon-btn"
            aria-label="Open menu"
            aria-expanded={open}
            onClick={(e) => {
              e.stopPropagation()
              setOpen(true)
            }}
          >
            <Icon name="menu" />
          </button>
        </header>
        <NetBar />
        <main className="main">
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** Header-only layout for students (no account). */
export function PublicLayout({ children }: { children?: ReactNode }) {
  const auth = useAuth()
  return (
    <div className="public">
      <header className="public-head">
        <Brand />
        <nav className="row">
          <NavLink to="/free-rooms" className="btn btn-ghost btn-sm">
            Free rooms
          </NavLink>
          {auth ? (
            <Link to={auth.role === 'admin' ? '/admin' : '/prof'} className="btn btn-sm">
              My space
            </Link>
          ) : (
            <Link to="/login" className="btn btn-sm">
              Staff login
            </Link>
          )}
        </nav>
      </header>
      <NetBar />
      <main className="public-main">{children ?? <Outlet />}</main>
    </div>
  )
}

export function PageHead({ title, intro, children }: { title: string; intro?: ReactNode; children?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{title}</h1>
        {intro && <p>{intro}</p>}
      </div>
      {children && <div className="row">{children}</div>}
    </div>
  )
}

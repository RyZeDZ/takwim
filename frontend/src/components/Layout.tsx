import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, setAuth } from '../api/client'
import { useAuth, useConfig, useNetwork } from '../lib/hooks'
import { LANGS, t, usePrefs, type Theme } from '../lib/i18n'
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
      <span>{t(cfg.data?.app_name ?? 'Timetables')}</span>
    </Link>
  )
}

const THEME_NEXT: Record<Theme, Theme> = { auto: 'dark', dark: 'light', light: 'auto' }
const THEME_ICON: Record<Theme, string> = { auto: 'contrast', dark: 'moon', light: 'sun' }
const THEME_LABEL: Record<Theme, string> = { auto: 'Theme: like the device', dark: 'Theme: dark', light: 'Theme: light' }

/** Language menu and light / dark switch. */
export function PrefControls() {
  const { lang, setLang, theme, setTheme } = usePrefs()
  return (
    <div className="prefs">
      <label className="lang-pick" title={t('Language')}>
        <Icon name="globe" />
        <select value={lang} onChange={(e) => setLang(e.target.value as typeof lang)} aria-label={t('Language')}>
          {LANGS.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      </label>
      <button
        className="btn btn-ghost icon-btn"
        onClick={() => setTheme(THEME_NEXT[theme])}
        aria-label={t(THEME_LABEL[theme])}
        title={t(THEME_LABEL[theme])}
      >
        <Icon name={THEME_ICON[theme]} />
      </button>
    </div>
  )
}

/** Connection banner: offline, or actions waiting to be sent. */
export function NetBar() {
  const { online, pending } = useNetwork()
  if (online && !pending) return null
  return (
    <div className="netbar" role="status">
      {!online && t('No connection. Your saved timetable is still available.') + ' '}
      {pending > 0 &&
        (online
          ? t('{n} action(s) waiting to be sent…', { n: pending })
          : t('{n} action(s) waiting, sent when the connection returns.', { n: pending }))}
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
      <aside className={'sidebar' + (open ? ' open' : '')} aria-label={t('Main menu')}>
        <Brand />
        {sections.map((sec) => (
          <nav className="nav-group" key={sec.label} aria-label={t(sec.label)}>
            <span className="nav-label">{t(sec.label)}</span>
            {sec.items.map((it) => (
              <NavLink key={it.to} to={it.to} end={it.end} className="nav-link">
                <Icon name={it.icon} />
                {t(it.label)}
              </NavLink>
            ))}
          </nav>
        ))}
        <div className="sidebar-foot">
          <PrefControls />
          <div className="who">
            <strong>{auth?.username}</strong>
            <span>{auth?.role === 'admin' ? t('Administrator') : t('Professor')}</span>
          </div>
          <button className="nav-link btn-ghost" style={{ border: 0, background: 'none', cursor: 'pointer' }} onClick={logout}>
            <Icon name="logout" flip /> {t('Log out')}
          </button>
        </div>
      </aside>
      <div style={{ minWidth: 0 }} onClick={() => open && setOpen(false)}>
        <header className="topbar">
          <Brand />
          <button
            className="btn icon-btn"
            aria-label={t('Open menu')}
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
        <main className="main page-in" key={location.pathname}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}

/** Header-only layout for students (no account). */
export function PublicLayout({ children }: { children?: ReactNode }) {
  const auth = useAuth()
  const location = useLocation()
  return (
    <div className="public">
      <header className="public-head">
        <Brand />
        <nav className="row public-nav">
          <NavLink to="/free-rooms" className="btn btn-ghost btn-sm hide-narrow">
            {t('Free rooms')}
          </NavLink>
          {auth ? (
            <Link to={auth.role === 'admin' ? '/admin' : '/prof'} className="btn btn-sm" aria-label={t('My space')}>
              <Icon name="users" />
              <span className="hide-narrow">{t('My space')}</span>
            </Link>
          ) : (
            <Link to="/login" className="btn btn-sm" aria-label={t('Staff login')}>
              <Icon name="users" />
              <span className="hide-narrow">{t('Staff login')}</span>
            </Link>
          )}
          <PrefControls />
        </nav>
      </header>
      <NetBar />
      <InstallPrompt />
      <main className="public-main page-in" key={location.pathname}>
        {children ?? <Outlet />}
      </main>
      <footer className="public-foot">
        <NavLink to="/free-rooms">{t('Free rooms')}</NavLink>
        <span>·</span>
        <span>{t('Works offline once opened')}</span>
      </footer>
    </div>
  )
}

export function PageHead({ title, intro, children }: { title: string; intro?: ReactNode; children?: ReactNode }) {
  const cfg = useConfig()
  useEffect(() => {
    const app = t(cfg.data?.app_name ?? 'Timetables')
    document.title = title ? `${title} · ${app}` : app
  }, [title, cfg.data?.app_name])
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

// ------------------------------------------------------------------ "install the app" banner
interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: string }>
}
const INSTALL_KEY = 'install-dismissed'
let deferred: InstallEvent | null = null
window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  deferred = e as InstallEvent
  window.dispatchEvent(new Event('install-ready'))
})

/** Offers to install the app once a student has opened a group (Android: one tap; iPhone: how-to). */
function InstallPrompt() {
  const location = useLocation()
  const [ready, setReady] = useState(!!deferred)
  const [hidden, setHidden] = useState(() => localStorage.getItem(INSTALL_KEY) === '1')
  useEffect(() => {
    const on = () => setReady(true)
    window.addEventListener('install-ready', on)
    return () => window.removeEventListener('install-ready', on)
  }, [])
  const standalone = window.matchMedia('(display-mode: standalone)').matches
  const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
  if (hidden || standalone || !location.pathname.startsWith('/g/') || (!ready && !ios)) return null

  const close = () => {
    localStorage.setItem(INSTALL_KEY, '1')
    setHidden(true)
  }
  const install = async () => {
    if (!deferred) return
    await deferred.prompt()
    await deferred.userChoice
    deferred = null
    close()
  }
  return (
    <div className="install" role="region" aria-label={t('Install the app')}>
      <Icon name="phone" size={22} />
      <div className="install-text">
        <strong>{t('Keep your timetable on your phone')}</strong>
        <span>
          {ready
            ? t('Install it: it opens in one tap, even without a connection.')
            : t('In Safari, tap Share, then "Add to Home Screen".')}
        </span>
      </div>
      {ready && (
        <button className="btn btn-primary btn-sm" onClick={install}>
          {t('Install')}
        </button>
      )}
      <button className="btn btn-ghost btn-sm" onClick={close}>
        {t('Not now')}
      </button>
    </div>
  )
}

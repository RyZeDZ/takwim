// Interface language (English, French, Arabic) and colour theme.
//
// Texts are written in English in the code and wrapped in t('...'); lib/translations.ts gives the
// French and Arabic versions. A missing translation shows the English text, so nothing breaks.
// Placeholders: t('{n} rooms', { n: 3 }).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { AR, FR } from './translations'

export type Lang = 'en' | 'fr' | 'ar'
export const LANGS: { code: Lang; label: string }[] = [
  { code: 'fr', label: 'Français' },
  { code: 'ar', label: 'العربية' },
  { code: 'en', label: 'English' },
]
const DICTS: Record<Lang, Record<string, string>> = { en: {}, fr: FR, ar: AR }
const LANG_KEY = 'lang'

function initialLang(): Lang {
  const saved = localStorage.getItem(LANG_KEY)
  if (saved === 'en' || saved === 'fr' || saved === 'ar') return saved
  const nav = (navigator.language || 'en').slice(0, 2)
  return nav === 'fr' || nav === 'ar' ? nav : 'en'
}

let current: Lang = initialLang()

export function t(text: string, vars?: Record<string, string | number>): string {
  let out = DICTS[current][text] ?? text
  if (vars) for (const [k, v] of Object.entries(vars)) out = out.split(`{${k}}`).join(String(v))
  return out
}

/** Locale for dates and numbers. */
export const locale = () => ({ en: 'en-GB', fr: 'fr-FR', ar: 'ar-DZ' })[current]
export const getLang = () => current

function applyLang(lang: Lang) {
  document.documentElement.lang = lang
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
}

// ------------------------------------------------------------------ theme
export type Theme = 'auto' | 'light' | 'dark'
const THEME_KEY = 'theme'
const dark = window.matchMedia('(prefers-color-scheme: dark)')

function applyTheme(theme: Theme) {
  const on = theme === 'dark' || (theme === 'auto' && dark.matches)
  document.documentElement.dataset.theme = on ? 'dark' : 'light'
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', on ? '#111827' : '#001858')
}

// ------------------------------------------------------------------ provider
interface Prefs {
  lang: Lang
  setLang: (l: Lang) => void
  theme: Theme
  setTheme: (t: Theme) => void
}
const PrefsContext = createContext<Prefs | null>(null)

export function PrefsProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(current)
  const [theme, setThemeState] = useState<Theme>(() => (localStorage.getItem(THEME_KEY) as Theme) || 'auto')

  useEffect(() => applyLang(lang), [lang])
  useEffect(() => {
    applyTheme(theme)
    const on = () => applyTheme(theme)
    dark.addEventListener('change', on)
    return () => dark.removeEventListener('change', on)
  }, [theme])

  const setLang = useCallback((l: Lang) => {
    current = l
    localStorage.setItem(LANG_KEY, l)
    setLangState(l)
  }, [])
  const setTheme = useCallback((th: Theme) => {
    localStorage.setItem(THEME_KEY, th)
    setThemeState(th)
  }, [])

  // key={lang}: every text is drawn again in the new language.
  return (
    <PrefsContext.Provider value={{ lang, setLang, theme, setTheme }}>
      <div key={lang} style={{ display: 'contents' }}>
        {children}
      </div>
    </PrefsContext.Provider>
  )
}

export function usePrefs() {
  const ctx = useContext(PrefsContext)
  if (!ctx) throw new Error('PrefsProvider missing')
  return ctx
}

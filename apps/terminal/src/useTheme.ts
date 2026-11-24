import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem('politeia-theme')
    if (stored === 'dark' || stored === 'light') return stored
  } catch { /* Storage may be disabled; the switch still works. */ }
  return window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(initialTheme)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.documentElement.classList.toggle('bp6-dark', theme === 'dark')
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#08090b' : '#fafafa')
  }, [theme])
  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    try { localStorage.setItem('politeia-theme', next) } catch { /* Optional persistence. */ }
    setTheme(next)
  }
  return { theme, toggleTheme }
}

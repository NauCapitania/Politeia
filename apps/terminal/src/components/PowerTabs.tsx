import type { KeyboardEvent } from 'react'
import { POWERS, viewLabel } from '../platform'
import { useStore, type View } from '../store'

export function PowerTabs() {
  const { view, setView } = useStore()
  const power = POWERS.find((p) => p.views.includes(view))
  if (!power) return null
  function navigate(e: KeyboardEvent<HTMLDivElement>) {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
    const tabs = [...e.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')]
    const current = tabs.indexOf(e.target as HTMLButtonElement)
    if (current < 0) return
    e.preventDefault()
    const next = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (current + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length
    tabs[next].focus(); tabs[next].click()
  }
  return <div className="power-navigation">
    <div className="power-tabs" role="tablist" aria-label="Poderes da República" onKeyDown={navigate}>{POWERS.map((p) => <button key={p.id} role="tab" aria-controls="workspace-panel" tabIndex={power.id === p.id ? 0 : -1} aria-selected={power.id === p.id} onClick={() => setView(p.view)}>{p.label}</button>)}</div>
    {power.id === 'legislativo' && <div className="chamber-tabs" role="tablist" aria-label="Casas do Congresso" onKeyDown={navigate}>{(['congresso', 'senado', 'camara'] as View[]).map((v) => <button key={v} role="tab" aria-controls="workspace-panel" tabIndex={v === view ? 0 : -1} aria-selected={v === view} onClick={() => setView(v)}>{viewLabel(v)}</button>)}</div>}
  </div>
}

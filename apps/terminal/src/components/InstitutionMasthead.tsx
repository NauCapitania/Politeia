import './institution-masthead.css'

type Institution = 'congresso' | 'senado' | 'camara' | 'stf' | 'executivo'

const ART: Record<Institution, string> = {
  congresso: 'congresso', senado: 'congresso', camara: 'congresso',
  stf: 'stf-justica', executivo: 'executivo',
}

/** Decorative art supplied by the owner; institutional facts stay in the page. */
export function InstitutionMasthead({ kind, eyebrow, title, subtitle }: {
  kind: Institution; eyebrow: string; title: string; subtitle: string
}) {
  return <header className={`institution-masthead institution-masthead--${kind}`}>
    <div className="institution-masthead-copy">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </div>
    <div className="institution-masthead-art" aria-hidden="true">
      <img src={`/${ART[kind]}.webp`} alt="" width={kind === 'stf' ? 720 : 1600} height={kind === 'stf' ? 900 : 533} decoding="async" />
    </div>
  </header>
}

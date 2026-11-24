// Verifies the Cloudflare Access JWT so the agent stays private even if Access is misconfigured on a hostname.
type Jwk = JsonWebKey & { kid?: string }
type Claims = { aud?: string | string[]; exp?: number; nbf?: number; iss?: string; email?: string }

const certCache = new Map<string, { keys: Jwk[]; at: number }>()

function b64url(input: string) {
  const s = input.replace(/-/g, '+').replace(/_/g, '/')
  return Uint8Array.from(atob(s + '='.repeat((4 - (s.length % 4)) % 4)), (c) => c.charCodeAt(0))
}

async function certs(team: string, fetchImpl: typeof fetch): Promise<Jwk[]> {
  const cached = certCache.get(team)
  if (cached && Date.now() - cached.at < 3_600_000) return cached.keys
  const res = await fetchImpl(`https://${team}/cdn-cgi/access/certs`)
  if (!res.ok) throw new Error('certs')
  const { keys } = await res.json() as { keys: Jwk[] }
  certCache.set(team, { keys, at: Date.now() })
  return keys
}

export async function verifyAccess(
  token: string | null,
  opts: { team: string; aud: string; allowedEmails: string[] },
  fetchImpl: typeof fetch = fetch,
  now = Date.now() / 1000,
): Promise<string | null> {
  if (!token) return null
  const [h, p, s] = token.split('.')
  if (!h || !p || !s) return null
  try {
    const header = JSON.parse(new TextDecoder().decode(b64url(h))) as { alg?: string; kid?: string }
    if (header.alg !== 'RS256') return null
    const jwk = (await certs(opts.team, fetchImpl)).find((k) => k.kid === header.kid)
    if (!jwk) return null
    const key = await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify'])
    const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64url(s), new TextEncoder().encode(`${h}.${p}`))
    if (!ok) return null
    const claims = JSON.parse(new TextDecoder().decode(b64url(p))) as Claims
    const auds = Array.isArray(claims.aud) ? claims.aud : [claims.aud]
    if (!auds.includes(opts.aud) || claims.iss !== `https://${opts.team}`) return null
    if (!claims.exp || claims.exp < now || (claims.nbf && claims.nbf > now + 60)) return null
    const email = claims.email?.toLowerCase()
    if (!email || (opts.allowedEmails.length && !opts.allowedEmails.includes(email))) return null
    return email
  } catch {
    return null
  }
}

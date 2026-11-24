const HOSTS = new Set(["legis.senado.leg.br", "www12.senado.leg.br"]);
const HEADERS = [
  "content-encoding", "content-type", "deprecation", "etag", "last-modified",
  "link", "location", "retry-after", "sunset",
];

function authorized(header, secret) {
  if (!secret) return false;
  const expected = `Bearer ${secret}`;
  let difference = header.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) {
    difference |= expected.charCodeAt(i) ^ (header.charCodeAt(i) || 0);
  }
  return difference === 0;
}

export async function relay(request, env, fetchUpstream = fetch) {
  if (!authorized(request.headers.get("authorization") || "", env.SENADO_PROXY_SECRET)) {
    return new Response(null, { status: 401 });
  }
  if (request.method !== "GET") return new Response(null, { status: 405, headers: { Allow: "GET" } });
  let target;
  try {
    target = new URL(new URL(request.url).searchParams.get("url"));
  } catch {
    return new Response(null, { status: 400 });
  }
  if (target.protocol !== "https:" || !HOSTS.has(target.hostname) ||
      target.port || target.username || target.password || target.hash) {
    return new Response(null, { status: 403 });
  }

  try {
    const upstream = await fetchUpstream(target, {
      headers: { Accept: request.headers.get("accept") || "*/*" },
      redirect: "manual",
    });
    const headers = new Headers({ "Cache-Control": "no-store" });
    for (const name of HEADERS) {
      const value = upstream.headers.get(name);
      if (value !== null) headers.set(name, value);
    }
    return new Response(upstream.body, { status: upstream.status, headers });
  } catch {
    return new Response(null, { status: 502 });
  }
}

export default {
  fetch: (request, env) => relay(request, env),
};

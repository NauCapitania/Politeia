import assert from "node:assert/strict";
import { test } from "node:test";
import { relay } from "./worker.mjs";

const env = { SENADO_PROXY_SECRET: "test-only" };
const target = "https://legis.senado.leg.br/dadosabertos/votacao?dataInicio=2026-11-01";
const bearer = "Bearer test-only";

function request(url, auth = bearer, method = "GET") {
  return new Request(`https://relay.example/?url=${encodeURIComponent(url)}`, {
    method, headers: { Authorization: auth, Accept: "application/json" },
  });
}

test("forwards the authorized request but not its credential, preserving upstream metadata", async () => {
  const result = await relay(request(target), env, async (url, options) => {
    assert.equal(url.href, target);
    assert.deepEqual(options, { headers: { Accept: "application/json" }, redirect: "manual" });
    return new Response('{"ok":true}', { headers: { "Content-Type": "application/json", ETag: "1" } });
  });
  assert.equal(result.status, 200);
  assert.equal(result.headers.get("etag"), "1");
  assert.equal(result.headers.get("cache-control"), "no-store");
  assert.deepEqual(await result.json(), { ok: true });
});

test("rejects unauthorized requests, other methods and unapproved destinations", async () => {
  const forbiddenFetch = () => assert.fail("must not fetch");
  assert.equal((await relay(request(target, "Bearer wrong"), env, forbiddenFetch)).status, 401);
  assert.equal((await relay(request(target, bearer, "POST"), env, forbiddenFetch)).status, 405);
  for (const url of ["http://legis.senado.leg.br/", "https://legis.senado.leg.br.bad.example/",
                     "https://user@legis.senado.leg.br/", "https://www12.senado.leg.br:444/"]) {
    assert.equal((await relay(request(url), env, forbiddenFetch)).status, 403);
  }
});

test("returns redirects without following them", async () => {
  const url = "https://www12.senado.leg.br/noticias/rss";
  const result = await relay(request(url), env, async (_, options) => {
    assert.equal(options.redirect, "manual");
    return new Response(null, { status: 302, headers: { Location: "/noticias/rss/" } });
  });
  assert.equal(result.status, 302);
  assert.equal(result.headers.get("location"), "/noticias/rss/");
});

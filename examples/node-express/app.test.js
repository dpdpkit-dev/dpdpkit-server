import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { test } from "node:test";

import { createApp } from "./app.js";
import { DpdpkitClient, SIGNATURE_HEADER, verifySignature } from "./dpdpkit.js";

const SECRET = "whsec_test";

function sign(body, timestamp = Math.floor(Date.now() / 1000)) {
  const digest = createHmac("sha256", SECRET).update(`${timestamp}.${body}`).digest("hex");
  return `t=${timestamp},v1=${digest}`;
}

async function withApp(run) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init, body: JSON.parse(init.body) });
    return new Response(JSON.stringify({ token: "tok", expires_at: 1, recorded: true }), { status: 200 });
  };
  const erased = [];
  const app = createApp({
    dpdpkit: new DpdpkitClient({ baseUrl: "http://dpdpkit", apiKey: "dpk_x", fetchImpl }),
    webhookSecret: SECRET,
    handlers: { erase: async (...args) => erased.push(args), export: async () => {} },
    currentUser: (req) => (req.get("x-user") ? { id: req.get("x-user") } : null),
  });
  const server = app.listen(0);
  try {
    await run(`http://127.0.0.1:${server.address().port}`, calls, erased);
  } finally {
    server.close();
  }
}

test("verifySignature accepts a fresh signature and rejects tampering and stale ones", () => {
  const body = Buffer.from('{"a":1}');
  assert.equal(verifySignature(SECRET, body, sign(body)), true);
  assert.equal(verifySignature(SECRET, Buffer.from('{"a":2}'), sign(body)), false);
  assert.equal(verifySignature(SECRET, body, sign(body, 1000)), false);
  assert.equal(verifySignature(SECRET, body, "garbage"), false);
  assert.equal(verifySignature(SECRET, body, undefined), false);
});

test("privacy token needs a signed-in user and is minted with the API key", async () => {
  await withApp(async (base, calls) => {
    assert.equal((await fetch(`${base}/api/privacy-token`, { method: "POST" })).status, 401);
    const response = await fetch(`${base}/api/privacy-token`, { method: "POST", headers: { "x-user": "u1" } });
    assert.equal(response.status, 200);
    assert.equal(calls[0].url, "http://dpdpkit/v1/tokens");
    assert.equal(calls[0].init.headers.Authorization, "Bearer dpk_x");
    assert.equal(calls[0].body.subject, "u1");
  });
});

test("erasure.due runs the handler, then confirms with the event id", async () => {
  await withApp(async (base, calls, erased) => {
    const body = JSON.stringify({
      id: "ev_1",
      type: "erasure.due",
      data: { schedule_id: "sch_1", principal: "u1", purpose: "marketing" },
    });
    const response = await fetch(`${base}/dpdpkit/webhook`, {
      method: "POST",
      headers: { [SIGNATURE_HEADER]: sign(body), "Content-Type": "application/json" },
      body,
    });
    assert.equal(response.status, 204);
    assert.deepEqual(erased, [["u1", "marketing"]]);
    assert.deepEqual(calls[0].body, {
      event_type: "erasure.due",
      event_id: "ev_1",
      subject_id: "sch_1",
      status: "completed",
      message: "",
    });
  });
});

test("a webhook with a bad signature is rejected and nothing runs", async () => {
  await withApp(async (base, calls, erased) => {
    const response = await fetch(`${base}/dpdpkit/webhook`, {
      method: "POST",
      headers: { [SIGNATURE_HEADER]: "t=1,v1=00" },
      body: "{}",
    });
    assert.equal(response.status, 401);
    assert.equal(calls.length + erased.length, 0);
  });
});

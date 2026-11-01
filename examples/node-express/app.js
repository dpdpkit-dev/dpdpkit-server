import express from "express";

import { DpdpkitClient, SIGNATURE_HEADER, verifySignature } from "./dpdpkit.js";

// `handlers.erase(principal, purpose)` and `handlers.export(principal)` are where your app acts on its own data.
export function createApp({ dpdpkit, webhookSecret, handlers, currentUser }) {
  const app = express();

  // 1. Hand the browser a short-lived token for the consent widget. The API key never leaves this backend.
  app.post("/api/privacy-token", async (req, res) => {
    const user = currentUser(req);
    if (!user) return res.status(401).json({ error: "sign in first" });
    try {
      res.json(await dpdpkit.createUserToken(user.id));
    } catch (error) {
      console.error(error);
      res.status(502).json({ error: "privacy service unavailable" });
    }
  });

  // 2. Receive signed webhooks. The signature covers the exact bytes, so read the raw body, not parsed JSON.
  app.post("/dpdpkit/webhook", express.raw({ type: "*/*", limit: "256kb" }), async (req, res) => {
    if (!verifySignature(webhookSecret, req.body, req.get(SIGNATURE_HEADER))) {
      return res.status(401).json({ error: "bad signature" });
    }
    const event = JSON.parse(req.body.toString("utf8"));
    try {
      if (event.type === "erasure.due") {
        await handlers.erase(event.data.principal, event.data.purpose);
        await dpdpkit.confirm({ eventType: event.type, eventId: event.id, subjectId: event.data.schedule_id });
      } else if (event.type === "export.requested") {
        await handlers.export(event.data.principal);
        await dpdpkit.confirm({ eventType: event.type, eventId: event.id, subjectId: event.data.request_id });
      }
      // Other event types are ignored; answering 2xx tells the server not to retry them.
      res.status(204).end();
    } catch (error) {
      // A non-2xx answer makes the server retry with backoff, and dead-letter the event after the last attempt.
      console.error(error);
      res.status(500).json({ error: "handler failed" });
    }
  });

  return app;
}

export function createAppFromEnv(env = process.env) {
  const need = (name) => {
    if (!env[name]) throw new Error(`set ${name}`);
    return env[name];
  };
  return createApp({
    dpdpkit: new DpdpkitClient({ baseUrl: env.DPDPKIT_URL ?? "http://localhost:8000", apiKey: need("DPDPKIT_API_KEY") }),
    webhookSecret: need("APP_WEBHOOK_SECRET"),
    // Demo only: replace with your real session lookup.
    currentUser: (req) => (req.get("x-demo-user") ? { id: req.get("x-demo-user") } : null),
    handlers: {
      erase: async (principal, purpose) => console.log(`erase ${purpose} data of ${principal}`),
      export: async (principal) => console.log(`export data of ${principal}`),
    },
  });
}

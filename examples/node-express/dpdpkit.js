// Thin client for dpdpkit-server, using only Node's built-ins (Node 18+).
import { createHmac, timingSafeEqual } from "node:crypto";

export const SIGNATURE_HEADER = "x-dpdpkit-signature";

// Same scheme as dpdpkit.events.verify_signature: header "t=<unix>,v1=<hex hmac-sha256 of "<t>.<raw body>">".
export function verifySignature(secret, rawBody, header, { tolerance = 300, now = Date.now() / 1000 } = {}) {
  if (!Buffer.isBuffer(rawBody)) return false; // express.raw leaves {} when the request has no body
  const parts = Object.fromEntries(String(header ?? "").split(",").map((p) => p.split(/=(.*)/s).slice(0, 2)));
  const timestamp = Number(parts.t);
  if (!Number.isInteger(timestamp) || typeof parts.v1 !== "string") return false;
  if (Math.abs(now - timestamp) > tolerance) return false;
  const expected = createHmac("sha256", secret).update(`${timestamp}.`).update(rawBody).digest("hex");
  const given = Buffer.from(parts.v1);
  const wanted = Buffer.from(expected);
  return given.length === wanted.length && timingSafeEqual(given, wanted);
}

export class DpdpkitClient {
  constructor({ baseUrl, apiKey, fetchImpl = fetch }) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
    this.fetch = fetchImpl;
  }

  async #post(path, body) {
    const response = await this.fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new Error(`dpdpkit-server ${path} answered ${response.status}`);
    return response.json();
  }

  // A short-lived token for the consent widget, bound to one of your users.
  createUserToken(subject, { scope = "", ttlSeconds = 900 } = {}) {
    return this.#post("/v1/tokens", { subject, scope, ttl_seconds: ttlSeconds });
  }

  // Tell the server that you acted on an erasure.due or export.requested event. It records this in the ledger.
  confirm({ eventType, eventId, subjectId, status = "completed", message = "" }) {
    return this.#post("/v1/webhooks/confirmations", {
      event_type: eventType,
      event_id: eventId,
      subject_id: subjectId,
      status,
      message,
    });
  }
}

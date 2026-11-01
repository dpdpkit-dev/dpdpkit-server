# node-express example

An Express app (Node 18+) that uses dpdpkit-server over HTTP:

- `POST /api/privacy-token` mints a short-lived end-user token for the consent widget (`/v1/tokens`). The API key stays
  on the backend. The demo identifies the user by an `x-demo-user` header; replace `currentUser` with your session.
- `POST /dpdpkit/webhook` verifies `X-DPDPKit-Signature` over the raw body, acts on `erasure.due` and
  `export.requested` (the handlers only log here), then confirms with `POST /v1/webhooks/confirmations`.

`dpdpkit.js` is the whole client and has no dependencies; only `app.js` needs Express.

## Run it

From the repository root, start the server and Postgres (see `.env.example` for the secrets):

```sh
cp .env.example .env     # fill in POSTGRES_PASSWORD, DPDPKIT_SIGNING_KEY, DPDPKIT_API_KEY_HASHES, APP_WEBHOOK_SECRET
docker compose up -d
```

Then, with the API key whose hash you put in `.env` and the same webhook secret:

```sh
cd examples/node-express
npm install
DPDPKIT_API_KEY=dpk_... APP_WEBHOOK_SECRET=... npm start
curl -X POST localhost:3000/api/privacy-token -H 'x-demo-user: user-1'
```

`dpdpkit.example.yaml` points the `app` webhook at `http://host.docker.internal:3000/dpdpkit/webhook`, which is this
app running on your machine.

`npm test` runs the signature, token and confirmation tests with Node's test runner and a fake `fetch`.

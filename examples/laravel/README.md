# Laravel snippet

Use dpdpkit-server from a Laravel 10+ app (PHP 8.1+) with the built-in HTTP client. Two jobs, the same as in
[`../node-express`](../node-express): mint a short-lived end-user token for the consent widget, and receive the signed
`erasure.due` / `export.requested` webhooks and confirm them. This is a snippet to copy, not a package; it has not been
run against a live server.

## 1. Configuration

`config/services.php`:

```php
'dpdpkit' => [
    'url' => env('DPDPKIT_URL', 'http://localhost:8000'),
    'api_key' => env('DPDPKIT_API_KEY'),             // dpk_..., from `new-api-key`; backend only
    'webhook_secret' => env('DPDPKIT_WEBHOOK_SECRET'), // same value as APP_WEBHOOK_SECRET on the server
],
```

## 2. Client

`app/Services/Dpdpkit.php`:

```php
<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;

class Dpdpkit
{
    private function post(string $path, array $body): array
    {
        return Http::baseUrl(config('services.dpdpkit.url'))
            ->withToken(config('services.dpdpkit.api_key'))
            ->acceptJson()
            ->post($path, $body)
            ->throw()
            ->json();
    }

    /** A short-lived token for the consent widget, bound to one of your users. */
    public function userToken(string $subject, int $ttlSeconds = 900): array
    {
        return $this->post('/v1/tokens', ['subject' => $subject, 'ttl_seconds' => $ttlSeconds]);
    }

    /** Tell the server that you acted on an event; it records this in the ledger. */
    public function confirm(string $eventType, string $eventId, string $subjectId, string $status = 'completed', string $message = ''): array
    {
        return $this->post('/v1/webhooks/confirmations', [
            'event_type' => $eventType,
            'event_id' => $eventId,
            'subject_id' => $subjectId,
            'status' => $status,
            'message' => $message,
        ]);
    }

    /** Header format: `t=<unix>,v1=<hex hmac-sha256 of "<t>.<raw body>">`. */
    public static function verifySignature(string $secret, string $rawBody, ?string $header, int $tolerance = 300): bool
    {
        $parts = [];
        foreach (explode(',', (string) $header) as $part) {
            [$key, $value] = array_pad(explode('=', $part, 2), 2, null);
            $parts[$key] = $value;
        }
        if (! isset($parts['t'], $parts['v1']) || ! ctype_digit($parts['t'])) {
            return false;
        }
        if (abs(time() - (int) $parts['t']) > $tolerance) {
            return false;
        }

        return hash_equals(hash_hmac('sha256', $parts['t'].'.'.$rawBody, $secret), $parts['v1']);
    }
}
```

## 3. Routes and controller

`routes/web.php` (webhooks are server-to-server, so exempt them from CSRF; in Laravel 11 add
`$middleware->validateCsrfTokens(except: ['dpdpkit/webhook']);` in `bootstrap/app.php`, in Laravel 10 add the path to
`VerifyCsrfToken::$except`):

```php
use App\Http\Controllers\DpdpkitController;

Route::post('/api/privacy-token', [DpdpkitController::class, 'token'])->middleware('auth');
Route::post('/dpdpkit/webhook', [DpdpkitController::class, 'webhook']);
```

`app/Http/Controllers/DpdpkitController.php`:

```php
<?php

namespace App\Http\Controllers;

use App\Services\Dpdpkit;
use Illuminate\Http\Request;

class DpdpkitController extends Controller
{
    public function token(Request $request, Dpdpkit $dpdpkit)
    {
        return $dpdpkit->userToken((string) $request->user()->getAuthIdentifier());
    }

    public function webhook(Request $request, Dpdpkit $dpdpkit)
    {
        // The signature covers the exact bytes: use getContent(), not the parsed input.
        $raw = $request->getContent();
        if (! Dpdpkit::verifySignature(config('services.dpdpkit.webhook_secret'), $raw, $request->header('X-DPDPKit-Signature'))) {
            abort(401, 'bad signature');
        }

        $event = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        $data = $event['data'] ?? [];

        // Any exception here gives a 500, so the server retries with backoff and dead-letters after the last attempt.
        if ($event['type'] === 'erasure.due') {
            // Erase $data['purpose'] data of $data['principal'] in your own tables here.
            $dpdpkit->confirm($event['type'], $event['id'], $data['schedule_id']);
        } elseif ($event['type'] === 'export.requested') {
            // Build and deliver the export for $data['principal'] here.
            $dpdpkit->confirm($event['type'], $event['id'], $data['request_id']);
        }

        return response()->noContent();
    }
}
```

Confirmations are idempotent on the event id, so a retried webhook is safe. Do the real erasure and export in a queued
job if they take long, and call `confirm` from the job once it has finished.

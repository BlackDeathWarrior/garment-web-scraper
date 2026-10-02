# Support desk integration

Ethnic Threads can hand its customer support and its own failure reports to a support desk (a TMS deployment). Everything here is optional: with `SUPPORT_API_URL` unset the site behaves exactly as before, and the contact form keeps using Formspree.

## What it does

| In the app | What happens on the support desk |
| --- | --- |
| **Write to Us** (`/contact`) | A ticket is raised for the shopper. They get a reference and a link to follow it. |
| **Report a problem with this listing** (product window) | A ticket that carries the listing: id, title, store, price and when it was scraped. These facts come from the worker's own catalogue, never from the browser. |
| **My Requests** (`/requests`) | The shopper reads the replies, writes back and rates the answer. |
| **Chat** (bottom right) | The support desk's chat widget in the site's colours. It knows which listing the visitor has open. The signed-in admin is vouched for with a signed token. |
| **Scraper failures** | A run that fails, a store that returns nothing, a failed S3 upload, a full disk, a CAPTCHA or a stale catalogue is reported as an incident. Repeats share one ticket; a recovery resolves it. |
| **Admin: Support Desk panel** (home page) | Open incidents, the latest requests, and what the support desk reported back through its webhooks. |
| **AI tools** | The support desk's AI can read the scraper's status and log, look up a listing, check the catalogue's age, and (after a supervisor approves) start a scrape. |

The browser never holds an API key. It calls the worker (`/api/support/*`), and the worker calls the support desk.

## Settings

Put these in `.env` at the repository root (see `frontend/.env.example`). Each feature switches on when its own settings are present.

| Setting | For |
| --- | --- |
| `SUPPORT_API_URL` | Where the support desk is served. Without it, everything below is off. |
| `SUPPORT_API_KEY_WEB` | Shopper requests (a key with the ticket scope). |
| `SUPPORT_API_KEY_EVENTS` | Scraper incidents (a key with the incident scope). |
| `SUPPORT_WEBHOOK_SECRET` | Verifies webhooks sent to `/api/support/webhook`. |
| `SUPPORT_CHAT_IDENTITY_SECRET` | Signs the admin's identity for the chat. |
| `SUPPORT_TOOL_TOKEN` | What the support desk's AI must send to call `/api/support/tools/*`. |
| `SUPPORT_WIDGET_URL` | Where the chat widget is served from, when it is not `SUPPORT_API_URL`. |
| `SUPPORT_STALE_HOURS` | The catalogue counts as stale when its newest product is older than this (default 48). |

## Worker endpoints

| Route | Who calls it | Protected by |
| --- | --- | --- |
| `GET /api/support/config` | Storefront | Public; returns no secrets |
| `POST /api/support/tickets` | Storefront | Per-visitor limit |
| `GET /api/support/requests/{ref}`, `…/changes`, `POST …/messages`, `POST …/rating` | Storefront | The request's tracking token (`X-Request-Token`), or the admin's session |
| `POST /api/support/webhook` | Support desk | `X-TMS-Signature` (HMAC-SHA256), replays refused, duplicates stored once |
| `GET /api/support/tools/scrape-status`, `log-tail`, `catalog-status`, `products`, `products/{id}`; `POST /api/support/tools/rescrape` | Support desk's AI | `Authorization: Bearer <SUPPORT_TOOL_TOKEN>` |
| `GET /api/support/admin/overview`, `GET /api/support/identity` | Storefront, admin only | The session token from `/api/auth/login` |

`/api/auth/login` now returns a signed session token that expires after 12 hours, instead of a fixed string.

## Incidents the scraper reports

| Fingerprint | Raised when | Resolved when |
| --- | --- | --- |
| `scraper.run_failed` | A scrape process exits with an error (not when the admin stops it) | A run or a watch cycle succeeds |
| `scraper.spawn_failed` | The scrape process cannot be started | A run succeeds |
| `scraper.zero_products:<store>` | A store returns no products | That store returns products |
| `scraper.source_failed:<store>` | A store's scrape throws | That store returns products |
| `scraper.cycle_failed` | A watch cycle fails or finds nothing | A cycle succeeds |
| `scraper.s3_sync_failed` | The upload to S3 fails | An upload succeeds |
| `scraper.disk_critical` | Less than 5% of the disk is free | By hand |
| `scraper.captcha:amazon` | Amazon serves a CAPTCHA | Amazon returns products |
| `catalog.stale` | The newest product is older than `SUPPORT_STALE_HOURS` | A scrape refreshes the catalogue |

A support desk that is down never stops a scrape: reports time out after three seconds and are dropped.

## Running the worker without an automatic scrape

```bash
python -m scraper.worker --no-autostart --max-products 5
```

`--no-autostart` skips the continuous scrape that otherwise starts ten seconds after boot. Scrapes then run only when the admin, or the support desk with a supervisor's approval, asks for one.

## Tests

```bash
python -m pytest tests/support
```

```bash
cd frontend && npx vitest run src/__tests__/support.test.jsx
```

`scraper/support/tms_support.py` is the support desk's own Python client, copied in unchanged; `tests/support/signature-vectors.json` is the file its signatures are tested against.

# The shop and its support desk

Ethnic Threads is a demonstration shop: accounts, a cart, checkout, orders that move through a warehouse and a carrier, cancellations, returns and refunds. **Nothing in it is real commerce.** No card number or UPI id is ever asked for, no money moves and nothing is shipped; an order advances on a clock.

Its customer support runs on a support desk (a TMS deployment) through that desk's public integration API. The support side is optional: with `SUPPORT_API_URL` unset the shop works by itself, the help forms say support is not available, there is no chat, and nothing is reported anywhere.

The scraper that collected the catalogue is still in `scraper/` and is not part of the site any more. The shop sells the catalogue it left behind (`frontend/public/products.json`).

## Run it

```bash
pip install python-dotenv
python -m shop.server --step-seconds 20
```

```bash
cd frontend && npm install && npm run dev
```

The shop's server needs only Python's standard library (`python-dotenv` lets it read `.env`); it keeps accounts and orders in a SQLite file under `outputs/shop/`. It listens on port 8765 and the site on http://localhost:5173 (it reaches the server through the Vite proxy). `--step-seconds` is how long an order stays at each step; the admin can change it while the shop runs.

The admin signs in on the same sign-in page with `ADMIN_USERNAME` and `ADMIN_PASSWORD` from `.env`. Without `ADMIN_PASSWORD` there is no admin.

## What a shopper can do

| Page | What it does |
| --- | --- |
| Home | Browse, search and filter the catalogue; open a product, choose a size, add it to the cart or buy it now |
| Cart | Change quantities, remove items. The cart is kept in the browser and needs no account |
| Sign in, Create an account | Email and password. Checkout sends a visitor here and brings them back |
| Checkout | Delivery address (saved for next time), standard or express delivery, and how to pay: cash on delivery, UPI or card. Paying is one click and always simulated |
| Your orders | Every order with its status |
| An order | The five steps (placed, packed, shipped, out for delivery, delivered) with times, the carrier and tracking number, the expected date, items, payment and address. Cancel before it ships (what was paid is refunded at once); ask for a return within seven days of delivery; buy it again; get help with it |
| Help | The shopper's requests to support, each with its conversation, a reply box and, once solved, a rating |
| Contact | A form for visitors without an account. They follow the request by the link they are given |
| Chat (bottom right) | The support desk's chat, in the shop's colours |

## What the admin can do (Operations)

- See every order, move one to its next step, hold or release it, and approve a return (which refunds it).
- Change the simulation:

  | Switch | Effect in the shop | Reported to the support desk |
  | --- | --- | --- |
  | Payments are failing | Paying by UPI or card fails at checkout with "you have not been charged". Cash on delivery still works | Incident `shop.payments_failing` (critical), once per failed checkout. Recovery when the switch goes off |
  | The carrier is delayed | Orders that have shipped stop moving and their page says "delayed with the carrier" | Incident `shop.shipping_delayed` (error) when the first order is held up. Recovery when the switch goes off |
  | Seconds per step | How fast orders move | Nothing |

- Read what the support desk knows: open incidents, the latest tickets, and what the desk reported back through its webhooks. The admin can read a shopper's request and cannot reply to it or rate it.

## How the shop uses the support desk

| In the shop | On the support desk |
| --- | --- |
| **Get help with this order** | A ticket for the signed-in shopper, with the order number as its reference and the order's facts (status, carrier, tracking, items, total, payment) taken from the shop's own records, never from the browser |
| **Contact** | A ticket for a visitor. Reading it back needs the tracking token in the link |
| **Help** | The shopper's own tickets, listed by the shop's id for that shopper. No link or token is needed when signed in |
| **Chat** | A signed-in shopper is vouched for with a signed identity token, so the desk knows who is asking. A visitor who only types a name and an email is not vouched for |
| **Failed payments, carrier delays** | Incidents. Repeats are counted on one ticket; a recovery resolves it |
| **Webhooks from the desk** | Verified by signature, stored once, shown in the admin's activity feed, and used to refresh an open request page |
| **Tools for the desk's AI** | See below |

The browser never holds an API key. It calls the shop's server (`/api/support/*`), and the server calls the support desk.

### What the desk's AI may ask the shop

Every call carries `Authorization: Bearer <SUPPORT_TOOL_TOKEN>`. The order tools take the customer's email, which the desk fills in from the ticket (the AI cannot choose it), and answer only about that customer's orders.

| Route | What it does |
| --- | --- |
| `GET /api/support/tools/orders?customer_email=` | The customer's five most recent orders |
| `GET /api/support/tools/orders/{id}?customer_email=` | One order: status, carrier, tracking number, expected date, whether it is delayed |
| `POST /api/support/tools/orders/{id}/cancel` | Cancels it if it has not shipped, and refunds what was paid |
| `POST /api/support/tools/refunds` | Refunds a delivered order in full. The desk runs this only after a supervisor approves it. Asking twice refunds once |
| `GET /api/support/tools/shop-status` | Whether payments and the carrier are working, and how many orders are delayed |
| `GET /api/support/tools/products?query=`, `GET /api/support/tools/products/{id}` | Product search and lookup |

An order that is not that customer's is answered exactly like an order that does not exist.

## Settings

In `.env` at the repository root (see `frontend/.env.example`).

| Setting | For |
| --- | --- |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD` | The admin's sign-in |
| `SHOP_SESSION_SECRET` | Signs sessions. Without it one is made on first use and kept in the shop's database |
| `SHOP_STEP_SECONDS` | Seconds an order stays at each step (same as `--step-seconds`) |
| `SHOP_DB` | Where the database file is (default `outputs/shop/shop.db`) |
| `SUPPORT_API_URL` | Where the support desk is served. Without it, everything below is off |
| `SUPPORT_API_KEY_WEB` | Shoppers' requests (a key with the ticket scope) |
| `SUPPORT_API_KEY_EVENTS` | Incidents (a key with the incident scope) |
| `SUPPORT_WEBHOOK_SECRET` | Verifies webhooks sent to `/api/support/webhook` |
| `SUPPORT_CHAT_IDENTITY_SECRET` | Signs a shopper's identity for the chat |
| `SUPPORT_TOOL_TOKEN` | What the desk's AI must send to call `/api/support/tools/*` |
| `SUPPORT_WIDGET_URL` | Where the chat widget is served from, when it is not `SUPPORT_API_URL` |
| `SUPPORT_INTEGRATION` | The integration's identifier on the desk (default `ethnic-threads`) |

## The server's routes

| Route | Who | Protected by |
| --- | --- | --- |
| `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` | Anyone | Per-visitor limits. Passwords are stored as PBKDF2 hashes; a session is a signed token that expires |
| `GET /api/checkout/options`, `POST /api/checkout/quote` | Anyone | Prices always come from the shop's catalogue, never from the request |
| `POST /api/orders`, `GET /api/orders`, `GET /api/orders/{id}`, `POST /api/orders/{id}/cancel`, `POST /api/orders/{id}/return`, `GET /api/addresses` | Shopper | The session. Another shopper's order answers 404 |
| `GET /api/admin/orders`, `GET`/`PUT /api/admin/simulation`, `POST /api/admin/orders/{id}/advance`, `/hold`, `/release`, `/refund` | Admin | The admin's session |
| `GET /api/support/config` | Storefront | Public; returns no secrets |
| `POST /api/support/tickets` | Storefront | Per-visitor limit. An order request needs the shopper's session and their own order |
| `GET /api/support/requests`, `GET /api/support/requests/{ref}`, `…/changes`, `POST …/messages`, `POST …/rating` | Storefront | The shopper's session (their own requests only), or the request's tracking token for a guest |
| `GET /api/support/identity` | Storefront | The session (a shopper's or the admin's) |
| `POST /api/support/webhook` | Support desk | `X-TMS-Signature` (HMAC-SHA256), replays refused, duplicates stored once |
| `/api/support/tools/*` | Support desk's AI | `SUPPORT_TOOL_TOKEN` |
| `GET /api/support/admin/overview` | Storefront, admin only | The admin's session |

## Tests

```bash
python -m pytest tests/shop tests/support
```

```bash
cd frontend && npx vitest run
```

`scraper/support/tms_support.py` is the support desk's own Python client, copied in unchanged; `tests/support/signature-vectors.json` is the file its signatures are tested against. The shop reuses that client, the webhook receiver and the incident reporter from `scraper/support/`.

The end-to-end run that drives this site together with the support desk lives in the support desk's repository (`e2e/tests/garment`).

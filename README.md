# Procura AI

**Buy with clarity.** Procura AI turns a natural-language buying brief into catalogue-backed recommendations, explains the options, and prepares a purchase for the buyer to review. It brings personal shopping and business procurement into one guided flow.

> Hackathon prototype. Product, supplier, price, stock, and reliability information is seeded demo data and is not live availability. PayPal checkout uses Sandbox credentials.

## The problem

People and small teams spend time translating a need into product specifications, searching listings, comparing suppliers, checking bulk quantities against budgets, and then completing a purchase. Procura makes that work easier to review in one place.

## What works in this prototype

- Individual and Business procurement modes.
- Natural-language request parsing. Add an OpenAI-compatible API key for model-based structured extraction; without one, a built-in demo parser handles the curated examples.
- Seeded catalogue across electronics, apparel, and stationery with supplier listings, attributes, prices, minimum order quantities, and demo stock.
- Backend filtering for product constraints, stock, quantity, minimum order, and budget.
- Server-calculated purchase totals and persistent SQLite order drafts.
- Explicit purchase approval before checkout.
- PayPal Orders v2 Sandbox order creation and capture when credentials are configured. The server checks the completed capture, amount, currency, and local order reference before marking an order paid.
- Order history that persists in SQLite across refreshes and backend restarts.

## Run locally

Requires Python 3.10+ and pip.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn main:app --reload --env-file .env
```

Open [http://localhost:8000](http://localhost:8000). The database is created at `data/procura.db` and is seeded on first start. The catalogue and request parsing work without API credentials.

## Enable AI extraction

Edit `backend/.env` and set `LLM_API_KEY`. The default endpoint and model target OpenAI-compatible Chat Completions. Set `LLM_BASE_URL` and `LLM_MODEL` for another compatible provider. The key stays on the backend and is never sent to the browser. If the model request fails, the deterministic demo parser keeps the curated demo usable.

## Enable PayPal Sandbox checkout

1. Create a Sandbox REST app in the PayPal Developer Dashboard.
2. Put its Sandbox Client ID and Secret in `backend/.env` as `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`.
3. Keep `PAYPAL_BASE_URL=https://api-m.sandbox.paypal.com` and restart the backend.
4. Use a PayPal Sandbox buyer account to approve checkout.

The Client ID is public and used by the PayPal JavaScript SDK. The Secret remains server-side. A buyer approval alone does not mark an order paid; the backend captures and verifies it. This prototype pays the configured Sandbox merchant account and does not implement supplier payouts or split settlement.

## Demo walkthrough

1. Choose **For me** and try “Find me a laptop under $900 for programming, with at least 16 GB RAM and 512 GB storage.” Compare a recommended laptop and add it to the cart.
2. Return to procurement, choose **For my business**, and try “Find 100 black cotton T-shirts in sizes S to XL within a total budget of $500.” Review supplier prices and the purchase total.
3. Check the exact items and total, then approve. With PayPal Sandbox configured, complete checkout and show the verified paid order in **Orders**.

## Architecture

```text
Browser (HTML/CSS/JS + PayPal JS SDK)
       │ same-origin JSON API
FastAPI ── request extraction (LLM or demo parser)
   ├── deterministic catalogue, stock and budget rules
   ├── SQLite orders and payment records
   └── PayPal Orders v2 create → buyer approval → capture verification
```

The model interprets the user’s words. It does not supply product IDs, prices, stock, totals, or payment status. Backend catalogue records and payment responses remain authoritative.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Service and integration configuration |
| GET | `/api/products` | Search the seeded catalogue |
| POST | `/api/procurement/parse` | Extract requirements and return eligible listings |
| POST | `/api/orders` | Persist a server-priced purchase draft |
| GET | `/api/orders` | Read recent order history |
| POST | `/api/payments/create` | Create a PayPal order from a local draft |
| POST | `/api/payments/capture` | Capture and verify PayPal payment |

## Safety and demo limitations

- Never commit `.env`, Sandbox secrets, or API keys.
- The buyer reviews the items and total before checkout.
- The backend recalculates totals from catalogue prices and validates stock at draft creation.
- Demo stock is illustrative and does not reserve inventory.
- No real payment, shipment, supplier payout, production authentication, tax, or shipping calculation is implemented.

## Team workstreams

Project/AI integration · Frontend · Backend/database · PayPal Sandbox · Catalogue/procurement/QA/deployment. Use short-lived feature branches and integrate frequently.

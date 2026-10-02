# TFTW — Razorpay Payment Gateway Integration Guide

This document details the architecture, configuration, security mechanisms, API contracts, webhook processing, refund flow, and operational procedures for the **Too Fresh To Waste (TFTW)** Razorpay payment implementation.

---

## 1. Architectural Overview & Payment Flow

TFTW employs an **Official Server-Side Razorpay Payment Architecture** designed with zero-trust client pricing, HMAC-SHA256 signature verification, and idempotent webhook reconciliation.

### Conceptual Payment Flow

```text
CUSTOMER (Browser)                 TFTW BACKEND                        RAZORPAY GATEWAY
       │                                 │                                    │
       │─── 1. Select Food & Qty ───────>│                                    │
       │    POST /payments/create-order/ │                                    │
       │                                 │── 2. Read trusted DB price ────────│
       │                                 │   Atomic inventory lock            │
       │                                 │   Create PENDING Booking           │
       │                                 │                                    │
       │                                 │── 3. client.order.create() ───────>│
       │                                 │<── Returns razorpay_order_id ──────│
       │<── 4. Return Order Details ─────│                                    │
       │                                 │                                    │
       │─── 5. Open Razorpay Checkout ───────────────────────────────────────>│
       │       (UPI, Cards, NetBanking, Wallets)                              │
       │<── 6. Customer Completes Payment ────────────────────────────────────│
       │       Returns payment_id, order_id, signature                        │
       │                                 │                                    │
       │─── 7. POST /payments/verify/ ──>│                                    │
       │                                 │── 8. HMAC-SHA256 Verification ─────│
       │                                 │      (Secret Key Backend-Only)     │
       │                                 │   Order status -> CONFIRMED        │
       │                                 │   Payment status -> PAID           │
       │                                 │   Broadcast real-time event        │
       │<── 9. Confirmation & PIN ───────│                                    │
       │                                 │                                    │
       │                                 │<── 10. Webhook (payment.captured) ─│
       │                                 │    (Idempotent reconciliation)     │
```

---

## 2. Environment Variables & Credentials

Credentials must be configured in `backend/.env`.

| Variable | Description | Example (Test Mode) | Example (Live Mode) |
|---|---|---|---|
| `RAZORPAY_KEY_ID` | Public Key ID (provided to frontend checkout) | `rzp_test_xxxxxxxxxx` | `rzp_live_xxxxxxxxxx` |
| `RAZORPAY_KEY_SECRET` | Backend Secret Key (**NEVER EXPOSE**) | `xxxxxxxxxxxxxxxxxxxxxxxx` | `xxxxxxxxxxxxxxxxxxxxxxxx` |
| `RAZORPAY_WEBHOOK_SECRET` | Webhook verification secret | `whsec_xxxxxxxxxxxxxxxx` | `whsec_xxxxxxxxxxxxxxxx` |

> [!CAUTION]
> **CRITICAL SECURITY RULES**:
> 1. NEVER commit `.env`, `.env.local`, or secret-bearing files.
> 2. NEVER expose `RAZORPAY_KEY_SECRET` to JavaScript or client-side code.
> 3. NEVER log secret keys or full card credentials.
> 4. Keep `backend/.env.example` populated only with blank placeholders.

---

## 3. Backend Endpoints Summary

All payment endpoints are served under `/api/payments/`.

| Method | Endpoint | Auth Required | Description |
|---|---|---|---|
| `GET` | `/api/payments/config/` | Public | Returns `key_id`, `currency`, and `is_configured`. Never returns secret keys. |
| `POST` | `/api/payments/create-order/` | Authenticated | Calculates DB price, holds stock atomically, and creates Razorpay Order. |
| `POST` | `/api/payments/verify/` | Authenticated | Server-side HMAC-SHA256 signature verification. Confirms order to `PAID`. |
| `POST` | `/api/payments/failure/` | Authenticated | Records customer checkout dismissal or gateway failure; allows retry. |
| `POST` | `/api/payments/retry/` | Authenticated | Reuses or creates fresh Razorpay order for unpaid pending booking. |
| `POST` | `/api/payments/webhook/` | Public (Signed) | Asynchronous webhook listener. Verifies `X-Razorpay-Signature`. |
| `POST` | `/api/payments/refund/` | Admin Only | Calls Razorpay Refund API, updates status to `REFUNDED`, restores inventory. |
| `GET` | `/api/payments/admin/all/` | Admin Only | Full audit listing of payment transactions and status history. |

---

## 4. Zero-Trust Price Control

Client-supplied amounts are **NEVER trusted**.

1. The frontend sends only `{ "listing_id": 14, "quantity": 2 }`.
2. The server acquires a row lock on the `FoodListing` using `select_for_update()`.
3. The server retrieves the verified `discounted_price` from the database.
4. Server computes: `subtotal = discounted_price * quantity`, `amount_paise = int(total * 100)`.
5. The Razorpay Order is created using this server-computed paise amount.
6. The client cannot tamper with the price, tax, discount, or payment status.

---

## 5. Official Signature Verification

Payment authorization is verified server-side in `apps.payments.services.verify_razorpay_signature`:

```python
params = {
    'razorpay_order_id': razorpay_order_id,
    'razorpay_payment_id': razorpay_payment_id,
    'razorpay_signature': razorpay_signature,
}
client.utility.verify_payment_signature(params)
```

- If verification passes: Payment is marked `PAID`, Booking is marked `CONFIRMED`.
- If verification fails: Attempt is logged, `Payment.status` is set to `PAYMENT_FAILED`, and HTTP 400 is returned.

---

## 6. Webhooks & Idempotency

Razorpay webhooks provide reliable status reconciliation if a customer closes their browser or loses connectivity after completing payment:

- **Webhook URL**: `https://api.toofreshtowaste.in/api/payments/webhook/` (or ngrok URL for local development)
- **Secret**: Defined via `RAZORPAY_WEBHOOK_SECRET`
- **Header Checked**: `X-Razorpay-Signature`

### Supported Webhook Events

1. `payment.captured` / `order.paid`: Automatically transitions booking to `CONFIRMED` and `PAID` if not already confirmed by frontend callback.
2. `payment.failed`: Records failure details in `Payment` audit record.
3. `refund.processed`: Marks order `CANCELLED` and `REFUNDED`, and restores listing stock.

### Idempotency Guarantee
The table `payment_webhook_events` stores each event's `event_id` with a database unique constraint. If Razorpay redelivers an identical webhook, the server acknowledges it with HTTP 200 immediately without duplicate processing or double-updating inventory.

---

## 7. Database Payment States

```text
ORDER_CREATED
      ↓
PAYMENT_PENDING
      ↓
     PAID ──────────> REFUND_PENDING ──────────> REFUNDED
      │
      ├───> PAYMENT_FAILED ───> (Retry) ───> PAID
      └───> CANCELLED
```

### Models

- `marketplace.Booking`: Extended with `razorpay_order_id`, `razorpay_payment_id`, `payment_timestamp`, `refund_id`, `refund_status`, `refund_amount`, `refunded_at`.
- `payments.Payment`: Audit log capturing every payment attempt, error descriptions, and bank/channel methods (UPI, Card, NetBanking).
- `payments.PaymentWebhookEvent`: Idempotent ledger of all webhook deliveries.

---

## 8. Admin Refund Architecture

Refunds are restricted strictly to users with the `admin` role (`IsAdminRole`).

1. Admin views orders in `/admin-dashboard.html` or calls `POST /api/payments/refund/`.
2. Server validates that the payment exists, was `PAID`, and has not already been refunded.
3. Official Razorpay Refund API is called: `client.payment.refund(razorpay_payment_id, {'amount': amount_paise})`.
4. Upon confirmation from Razorpay:
   - `Booking.status` becomes `CANCELLED`.
   - `Booking.payment_status` becomes `REFUNDED`.
   - `Booking.refund_id` is recorded.
   - Available food stock on `FoodListing` is **atomically restored**.
   - Notifications are dispatched to customer and restaurant partner.

---

## 9. Switching from Test Mode to Live Mode

The system is 100% environment-driven and does not hardcode "test" flags in business logic.

To switch to **Razorpay Live Mode**:

1. Log into [Razorpay Dashboard](https://dashboard.razorpay.com/) and switch to **Live Mode**.
2. Complete KYC and business activation under **Settings -> Account & Settings**.
3. Generate Live API Keys under **Settings -> API Keys** (`rzp_live_...`).
4. Generate a Live Webhook Secret under **Settings -> Webhooks** with URL pointing to:
   `https://<your-production-domain>/api/payments/webhook/`
   Subscribe to events:
   - `payment.captured`
   - `order.paid`
   - `payment.failed`
   - `refund.processed`
5. Update your production `.env` (or hosting environment variables e.g., Render/AWS/Heroku):
   ```env
   RAZORPAY_KEY_ID=rzp_live_xxxxxxxxxxxxxxxx
   RAZORPAY_KEY_SECRET=your_live_secret_key_here
   RAZORPAY_WEBHOOK_SECRET=your_live_webhook_secret_here
   ```
6. Restart the backend ASGI / Daphne server.
7. Test a ₹1.00 live transaction and verify end-to-end confirmation and settlement.

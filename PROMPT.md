# Migration Prompt — OnePay Payment Gateway: Odoo 18/19 → Odoo 20

> **How to use this file:** Give this entire document to your coding agent as its task prompt, together with `docs/onepay-odoo20-investigation-report.md`. The agent executes the port on a new branch, then writes `docs/onepay-odoo20-migration-changelog.md` describing exactly what it changed. Do not merge until the smoke tests in Section 5 pass on a real Odoo 20 instance.

---

## 1. Role & objective

You are a senior Odoo developer. Port the **`payment_onepay`** module from Odoo 18/19 to **Odoo 20** (Python 3.12–3.14, PostgreSQL 16+). The investigation is already done — follow `docs/onepay-odoo20-investigation-report.md`, which rated this migration **Low difficulty**. Keep the port **minimal and surgical**: do not redesign the module, do not change the OnePay REST contract (`/v3/checkout/link/`, `/v3/transaction/status/`), and do not change the payment flow behavior. Only change what Odoo 20 requires.

## 2. Rules of engagement

- Work on a **conceptand-10** branch. Do not commit. I will reveiw and commit my self. Never commit to the main or dev branch or any other branch also.
- Make the **smallest change that is correct**. Preserve existing behavior, field names, and the OnePay API payloads exactly unless Odoo 20 forces a change.
- **Verify before you assume.** Several facts must be checked against the **actual installed Odoo 20 core source** (see Section 4, "Verify" items) — not from memory and not from this prompt alone. Where this prompt states an Odoo 20 fact, it is from the official Odoo 20 documentation, but still confirm it against the core module you are building on.
- Your best reference is a **known-good Odoo 20 core redirect-style provider** — read `addons/payment_demo`, `addons/payment_razorpay`, or `addons/payment_mollie` in your Odoo 20 source and mirror their controller + transaction patterns. Copy the shape, not fictional APIs.
- After each change group, note it in the changelog with the file and line touched.

## 3. Confirmed Odoo 20 facts (from official Odoo 20 docs — still confirm against your core build)

- **Payment transaction provider hooks (current in Odoo 20):** `_extract_reference(provider_code, payment_data)`, `_extract_amount_data(payment_data)`, `_apply_updates(payment_data)`, orchestrated by `_process(provider_code, payment_data)`; `_search_by_reference(provider_code, payment_data)` finds the transaction. `_apply_updates` must NOT be called directly — payment data goes through `_process()`.
- **Legacy hooks to remove:** `_get_tx_from_notification_data` and `_process_notification_data` are **not** the Odoo 20 API. Remove these overrides and the `hasattr` dispatch that selects between them.
- **`_get_specific_rendering_values(processing_values)`** still exists in Odoo 20 — keep the redirect builder.
- **Security:** `ir.model.access` + `ir.rule` are merged into a single `ir.access` model (operation = subset of `crud`, optional group, optional domain). This module ships none, so there is nothing to rewrite — only verify inherited access still works.
- **Typed config params:** string-based `get_param`/`set_param` are superseded by typed `get_str`/`get_int`/`get_bool`/`get_float` (and `set_*`).
- **Platform:** Python 3.12–3.14, PostgreSQL 16+.

## 4. Change groups (execute in order)

### Step 0 — Verify against live Odoo 20 core (blocking)
Before editing, confirm from the installed Odoo 20 source:
- (a) The transaction processing entry point and controller call pattern used by a core redirect provider (`_process(provider_code, payment_data)` and how the controller invokes it).
- (b) `payment.provider._setup_provider(code)` and `_ensure_payment_method_line(...)` still exist with the same signatures (the module `hasattr`-guards the latter — resolve this).
- (c) The `payment.method` model fields (name/code/sequence/active + any newly-required field).
- (d) The core `payment.payment_provider_form` still has pages named `credentials` and `configuration`.
- (e) The correct typed accessor for the base URL (`get_str("web.base.url", ...)` vs a record-level `get_base_url()` helper).
- (f) That `payment` and `account_payment` are still the correct dependency module names.
Record each answer in the changelog. If any differs from this prompt, follow the core source, not this prompt.

### Step 1 — Manifest & platform (report finding #11)
- `__manifest__.py`: set `version` to `"20.0.1.0.0"`.
- Add `"external_dependencies": {"python": ["requests"]}` (the module imports `requests` at `models/payment_transaction.py:6`).
- Confirm `depends = ["payment", "account_payment"]` are valid Odoo 20 module names (per Step 0f).

### Step 2 — Payment transaction API (report finding #13 — the main change)
In `models/payment_transaction.py`:
- **Remove** the legacy overrides `_get_tx_from_notification_data` (≈`:339`) and `_process_notification_data` (≈`:372`).
- **Keep and finalize** the Odoo 20 hooks already present: `_extract_reference` (`:379`), `_extract_amount_data` (`:389`), `_apply_updates` (`:402`) — ensure their signatures match Step 0a and that `_apply_updates` routes into your existing `_onepay_apply_payment_status` (`:413`).
- If transaction lookup logic is still needed beyond the core default, move it into an override of `_search_by_reference(provider_code, payment_data)` rather than the removed legacy method.
- **Keep** `_get_specific_rendering_values` (`:170`), the OnePay helpers, `_onepay_verify_status`, and `_onepay_apply_payment_status` unchanged in behavior.

### Step 3 — Controller (report finding #13)
In `controllers/main.py`:
- Replace the `hasattr`-based dispatch at `:39-48` (`_process` / `_handle_notification_data` / `_process_notification_data`) with the single Odoo 20 call confirmed in Step 0a — typically `request.env["payment.transaction"].sudo()._process("onepay", verified_data)`.
- Keep both routes (`/payment/onepay/webhook`, `/payment/onepay/return`), their `auth="public"`, `csrf=False`, and the `_onepay_verify_status` server-to-server confirmation exactly as they are. `request` usage in the controller is correct — leave it.

### Step 4 — Typed config parameter (report finding #3 / Section 5.3)
In `models/payment_transaction.py:186`, replace `ir.config_parameter.sudo().get_param("web.base.url", "")` with the Odoo 20 accessor confirmed in Step 0e (`get_str(...)` or the record `get_base_url()` helper).

### Step 5 — Domains (report finding #4 / Section 5.5)
In `models/payment_transaction.py:359,364`, convert the concatenated-list domains (`domain + [...]`) to Odoo 20 `Domain` objects (`from odoo.fields import Domain`; use `Domain.AND([...])` or `&`). Low risk — operators are hardcoded — but do it for forward compatibility.

### Step 6 — Provider wiring (report finding re: hasattr guards)
In `models/payment_provider.py`: once Step 0b confirms `_setup_provider` and `_ensure_payment_method_line` exist in Odoo 20, **remove the `hasattr` guard** (`:69`) and call them directly. Keep the `in provider._fields` guards in `_compute_feature_support_fields` only if a field may legitimately be absent; otherwise simplify.

### Step 7 — Views (report Section 5.1)
In `views/payment_provider_views.xml`: confirm the two XPaths (`//page[@name='credentials']` `:10`, `//page[@name='configuration']` `:28`) still resolve on the Odoo 20 core form (Step 0d). Adjust only if a page was renamed. No `attrs=`/`states=` exist, so nothing else to change here.

### Step 8 — Data & payment-method ownership (report finding #12)
In `data/payment_provider_data.xml`: confirm the `payment.method` (`:4`) and `payment.provider` (`:16`) seed records match the Odoo 20 schema (Step 0c). The module already ships its own `payment.method`, which Odoo 20 expects — keep it; adjust only fields that became required/renamed.

### Step 9 — Security (report finding #1)
No `ir.access` rows to write (the module ships none). Only add module-local `ir.access` rows **if** Step 0 testing shows the inherited models lack needed access for an ordinary portal/public user under Odoo 20's core `ir.access`.

## 5. Smoke tests (must pass before done)
On a clean Odoo 20 instance:
1. Module installs with no errors; provider appears under Accounting → Payment Providers.
2. Enter OnePay credentials, enable the provider; the form (credentials + configuration pages) renders.
3. **Success flow** (report Section 6.1): start a payment → redirect to OnePay `/v3/checkout/link/` → return → webhook → `_onepay_verify_status` → transaction reaches `done`. Confirm amount + currency matching still gate the result.
4. **Failure/cancel flow** (report Section 6.2): transaction reaches `error`, correct message shown, `/payment/status` displays the failure.
5. No deprecation warnings in the server log referencing this module.
6. If you added anything, run the module through `./odoo-bin upgrade_code --addons-path <path>` on a clean tree and review the diff.

## 6. Deliverables
- The `conceptand-10` branch without commit.
- `docs/onepay-odoo20-migration-changelog.md`: per change group, what changed (file:line), the Step 0 verification answers, and the smoke-test results.
- An **"Open decisions"** section flagging anything that needed a human call — in particular the webhook's lack of inbound signature verification (report Section 3.3 / Open question #3): note it, but do **not** change the trust model in this port unless instructed.

## 7. Done criteria
The module installs and runs on Odoo 20, both payment flows pass, the legacy `hasattr` version-hedging is gone, every Section 4 step is either done or explicitly marked "no change needed (verified)", and the changelog documents it. Behavior and the OnePay API contract are unchanged.
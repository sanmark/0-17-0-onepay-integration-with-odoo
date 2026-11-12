# OnePay Payment Gateway — Odoo 20 Migration Investigation Report

> Read-only investigation. No source files were modified. Branch investigated: `conceptand-10`.
> All locations cited as `path:LINE` relative to the repository root. Module root: `payment_onepay/`.

## 0. Summary

- **Module name:** `OnePay Payment Provider` (technical name `payment_onepay`).
- **Current version:** `19.0.1.0.0` (`payment_onepay/__manifest__.py:3`).
- **Odoo series supported:** Declared 19.0. The module uses Odoo 18/19-era payment-provider API (`_get_tx_from_notification_data`, `_process_notification_data`) plus newer 19 hooks (`_process`, `_extract_reference`, `_extract_amount_data`, `_apply_updates`). It contains runtime feature-detection branches (`hasattr(...)`) to straddle 18/19.
- **Overall migration difficulty: Low.** This is a small, self-contained redirect-style payment provider: 3 model files, 1 controller, 2 XML files, no JavaScript, no OWL components, no custom security files, and no SQL constraints or binary-field handling. The surface area that collides with Odoo 20 breaking changes is narrow and mostly mechanical. The two substantive risks are (a) the payment-provider/transaction API names that Odoo keeps renaming between releases, which must be re-verified against live Odoo 20 source, and (b) the already-present `hasattr`-based version branching, which should be resolved to the single correct Odoo 20 API rather than carried forward.
- **Top 5 highest-risk items:**
  1. **Payment API method names must be re-verified against Odoo 20 source** — the module already hedges with `hasattr(Transaction, "_process")` / `_handle_notification_data` (`controllers/main.py:39-48`) and overrides both legacy and new hooks. If Odoo 20 renamed or removed any of these, the webhook silently falls through. *(Section 4.2 / 4.3)*
  2. **`ir.config_parameter.get_param`** for `web.base.url` (`models/payment_transaction.py:186`) — superseded by typed accessors in Odoo 20 (Section 5.3).
  3. **Manifest `version` and undeclared external dependency `requests`** (`__manifest__.py:3`, `:17`) — version bump to `20.0.x` and `external_dependencies` should declare `requests` for Python 3.12–3.14 (Section 5.11).
  4. **Concatenated-list domains** in `_get_tx_from_notification_data` (`models/payment_transaction.py:359,364`) — recommended to move to `Domain` objects (Section 5.5). Low functional risk (operators are hardcoded, not user-supplied).
  5. **No `ir.access` / no access rules shipped** — the module ships no `ir.model.access.csv` and no `ir.rule`, so nothing must be rewritten, **but** confirm Odoo 20's core `payment` module still grants the access the inherited models need (Section 5.1 / 4.4).

---

## 1. Module inventory

### 1.1 Directory tree

```
payment_onepay/
├── __init__.py                         # imports models, controllers
├── __manifest__.py
├── controllers/
│   ├── __init__.py                     # imports main
│   └── main.py                         # OnePayController: webhook + return routes
├── data/
│   └── payment_provider_data.xml       # payment.method, redirect_form template, payment.provider seed
├── models/
│   ├── __init__.py                     # imports account_payment_method, payment_provider, payment_transaction
│   ├── account_payment_method.py       # account.payment.method (_get_payment_method_information)
│   ├── payment_provider.py             # payment.provider (_inherit)
│   └── payment_transaction.py          # payment.transaction (_inherit)
├── static/
│   └── description/
│       └── icon.png                    # provider logo (used for image_128)
└── views/
    └── payment_provider_views.xml      # provider form inheritance
```

Nothing non-standard in layout. **Notable absences** (all relevant to migration): no `security/` directory, no `ir.model.access.csv`, no `demo/`, no `static/src/` (no JS/CSS/OWL), no `tests/`, no `i18n/`, no hooks.

### 1.2 Manifest breakdown (`payment_onepay/__manifest__.py`)

| Key | Value |
|---|---|
| `name` | "OnePay Payment Provider" |
| `version` | `19.0.1.0.0` → **must become `20.0.x.y.z`** |
| `author` | "Sanmark Solutions" |
| `category` | "Accounting/Payment Providers" |
| `depends` | `["payment", "account_payment"]` |
| `data` | `data/payment_provider_data.xml`, `views/payment_provider_views.xml` |
| `installable` | `True` |
| `application` | `False` |
| `license` | `LGPL-3` |
| `external_dependencies` | **Not declared** — but `requests` is imported (`models/payment_transaction.py:6`). Recommend `{"python": ["requests"]}`. |
| `assets` | None declared (no frontend bundle). |
| `pre_init_hook` / `post_init_hook` / `uninstall_hook` | None. |
| `auto_install` | Not set (defaults to `False`). |

- **Declared Odoo series:** 19.0 (from `version`).
- **Version-conditional branches:** No `odoo.release.version_info` checks. Instead the module does **runtime API feature-detection** via `hasattr`: `controllers/main.py:39` (`_process`), `:43` (`_handle_notification_data`), and `models/payment_provider.py:69` (`_ensure_payment_method_line`). These are de-facto version branches and should be reduced to the single Odoo 20 API during the port.
- **Third-party Python packages imported anywhere:** `requests` (`models/payment_transaction.py:6`). Everything else is stdlib (`json`, `logging`, `hashlib`, `urllib.parse.quote_plus`) or `odoo.*`.

---

## 2. Models

| File | `_inherit` | Purpose |
|---|---|---|
| `models/account_payment_method.py` | `account.payment.method` | Registers the `onepay` method in `_get_payment_method_information` so `account.payment` can resolve it. |
| `models/payment_provider.py` | `payment.provider` | Adds the `onepay` provider code + credential fields; wires accounting payment method; declares feature support. |
| `models/payment_transaction.py` | `payment.transaction` | Builds the OnePay checkout link, verifies status, maps status → Odoo state. |

No new `_name` models are defined (all are `_inherit`). No `_sql_constraints`, no `ormcache`, no `read_group`, no `_table_query`, no `self._cr/_context/_uid`, no non-public `odoo.*` imports in any model.

### 2.1 `account.payment.method` (`models/account_payment_method.py`)

- `_get_payment_method_information` (`@api.model`, line 7) — adds `res["onepay"] = {"mode": "electronic", "type": ("bank",)}`.

### 2.2 `payment.provider` (`models/payment_provider.py`)

**Fields added:**

| Field | Type | Notes / location |
|---|---|---|
| `code` | Selection `selection_add=[("onepay","OnePay")]`, `ondelete={"onepay":"set default"}` | `:7` |
| `onepay_app_id` | Char, `required_if_provider="onepay"` | `:12` — credential |
| `onepay_app_token` | Char, `required_if_provider="onepay"`, `groups="base.group_system"` | `:17` — **secret** (API auth token) |
| `onepay_hash_salt` | Char, `required_if_provider="onepay"`, `groups="base.group_system"` | `:23` — **secret** (hash salt) |
| `onepay_api_base_url` | Char, default `https://api.onepay.lk`, `required_if_provider="onepay"` | `:29` — endpoint |

**Overridden / added methods:**

- `create` (`@api.model_create_multi`, `:36`) — after create, calls `_onepay_setup_account_payment_method()` for onepay providers.
- `write` (`:46`) — same post-write wiring.
- `_onepay_setup_account_payment_method` (`:55`) — calls `self.env["payment.provider"].sudo()._setup_provider("onepay")` and, **guarded by `hasattr(provider, "_ensure_payment_method_line")`** (`:69`), calls `_ensure_payment_method_line(allow_create=True)`. *(Verify `_setup_provider` and `_ensure_payment_method_line` exist/behave the same in Odoo 20.)*
- `_compute_feature_support_fields` (`:72`) — sets `support_tokenization=False`, `support_manual_capture=False`, `support_refund="none"`, `support_express_checkout=False`, each guarded by `in provider._fields`.
- `_get_default_payment_method_codes` (`:88`) — returns `["onepay"]`.
- `_get_supported_currencies` (`:96`) — returns LKR + USD currencies via `search`.
- `_onepay_get_api_base_url` (`:106`) / `_onepay_get_api_url` (`:110`) — URL helpers.

### 2.3 `payment.transaction` (`models/payment_transaction.py`)

**OnePay helpers:**
- `_onepay_generate_hash` (`:22`) — **SHA-256** over `app_id + currency + amount + hash_salt` (see Section 3.3).
- `_onepay_post` (`:36`) — `requests.post` to OnePay with `Authorization: <app_token>` header, 30s timeout; raises `ValidationError` on connection error or HTTP ≥ 400.
- `_onepay_get_nested_value` (`:71`) — tolerant key lookup including a nested `data` dict.
- `_onepay_get_partner_names` (`:87`), `_onepay_get_customer_phone` (`:98`), `_onepay_get_customer_email` (`:121`) — customer field extraction; phone/email required (raise if missing). Both guard transaction-level fields with `in self._fields`.
- `_onepay_is_success_status` (`:141`) — maps assorted truthy/string statuses to success.

**Overridden Odoo payment hooks:**
- `_get_specific_rendering_values` (`:170`) — **the redirect builder.** Validates credentials, builds the checkout payload, POSTs to `/v3/checkout/link/`, extracts `redirect_url` + transaction id, sets `provider_reference`, returns `{"api_url": redirect_url, "reference": ...}`.
- `_get_tx_from_notification_data` (`:339`) — resolves the tx from callback data (legacy 18/19 hook name).
- `_process_notification_data` (`:372`) — legacy processing hook → delegates to `_onepay_apply_payment_status`.
- `_extract_reference` (`:379`), `_extract_amount_data` (`:389`), `_apply_updates` (`:402`) — newer (Odoo 19) extraction hooks, also delegating to `_onepay_apply_payment_status`.
- `_onepay_verify_status` (`:259`) — server-to-server confirmation: POSTs `/v3/transaction/status/`, normalizes status/amount/currency/reference.
- `_onepay_apply_payment_status` (`:413`) — currency-match + amount-match guards, then `_set_done()` or `_set_error()`.

**ORM/pattern notes per Section 4.2:**
- `ir.config_parameter ... get_param` for `web.base.url` — `:186` (Section 5.3 finding).
- Manual domain-list concatenation — `:359`, `:364` (`domain + [...]`) (Section 5.5 finding).
- `request` referenced inside a model — **none found** (only in the controller).
- Binary fields with manual base64 (`b64encode`/`b64decode`/`len()` on binary) — **none found** in Python. (The only base64 is the XML image loader, Section 4.4.)
- `self._cr` / `self._context` / `self._uid` / `read_group` / `_table_query` — **none found**.
- `_sql_constraints` — **none found**.
- `ormcache` / `tools.ormcache` — **none found**.
- Imports from `odoo.osv` or deep `odoo.*` internals — **none found** (only `odoo.http`, `odoo.exceptions`, `odoo.tools.float_compare`, `odoo` top-level).

---

## 3. Controllers & OnePay flow

### 3.1 Route table (`controllers/main.py`)

| Route | Method | `type` | `auth` | `methods` | `csrf` | `website` | `sitemap` | Handler |
|---|---|---|---|---|---|---|---|---|
| `/payment/onepay/webhook` | server-to-server IPN | `http` | `public` | `POST` | `False` | — (default) | — | `onepay_webhook` (`:62`) |
| `/payment/onepay/return` | customer return | `http` | `public` | `GET,POST` | `False` | `True` | — | `onepay_return` (`:90`) |

Helper methods: `_json_response` (`:12`), `_get_json_payload` (`:22`), `_process_onepay_payload` (`:30`).

**Raw request access (Section 4.3 last bullet):**
- `request.httprequest.get_json(silent=True)` and `dict(request.params)` — `:23`, `:28`.
- `request.make_response(...)` — `:13`.
- `request.env[...]` — `:31`; `request.redirect(...)` — `:102`.
These all live in the controller (allowed); none are inside a model.

### 3.2 Redirect / return / IPN flow

- **Redirect / pay (build request to OnePay):** `payment.transaction._get_specific_rendering_values` (`models/payment_transaction.py:170`). The request is sent as a **JSON POST to OnePay's `/v3/checkout/link/` API** (`:219`) — *not* an HTML form of `vpc_*` fields. OnePay returns a `redirect_url`; Odoo's `redirect_form` QWeb template (`data/payment_provider_data.xml:11`) renders a bare `<form t-att-action="api_url" method="get" target="_self">` that forwards the browser to that URL. Payload keys sent (`:200-215`): `app_id`, `amount` (`"%.2f"`), `currency`, `hash`, `reference`, `customer_first_name`, `customer_last_name`, `customer_phone_number`, `customer_email`, `transaction_redirect_url`, `additionalData`.
- **Return URL (customer redirected back):** `/payment/onepay/return` → `onepay_return` (`:90`). It optionally processes any payload, then always `request.redirect("/payment/status")`. The return URL handed to OnePay is `<base_url>/payment/onepay/return?reference=<ref>` (`:210`).
- **IPN / webhook (server-to-server):** `/payment/onepay/webhook` → `onepay_webhook` (`:62`). Documented for the merchant to register in the OnePay portal (`views/payment_provider_views.xml:33`). Both webhook and return delegate to `_process_onepay_payload` (`:30`).

### 3.3 Signature & hash verification logic

- **Algorithm:** `hashlib.sha256(...).hexdigest()` — plain SHA-256, **not HMAC** (`models/payment_transaction.py:22-34`).
- **Hashed material / order:** concatenation of `onepay_app_id + currency_id.name + amount_string + onepay_hash_salt` (`:27-32`), UTF-8 encoded.
- **Secret used:** `onepay_hash_salt` (provider field, `group_system`-restricted).
- **Direction:** the hash is generated **outbound only** — it is sent as the `hash` field in the checkout-link request (`:204`). **There is no inbound signature verification** of the webhook/return payload. Instead, trust is established by an **independent server-to-server status call** (`_onepay_verify_status`, `/v3/transaction/status/`, `:279`) plus **amount and currency matching** (`_onepay_apply_payment_status`, `:420-446`). This is a valid design (callback is only a trigger), but note for the migration: **the webhook accepts any POST and relies entirely on the status API + amount/currency checks for integrity** — there is no HMAC on the callback itself.
- **`request` usage needing adjustment:** all `request` references are in the controller, which is the correct place; none are in model code (Section 5.6 = none found).

---

## 4. Data & security

### 4.1 Access rules

- **`ir.model.access.csv`: none found.** The module ships no access-rights CSV.
- **`ir.rule` records: none found.** No record rules.
- **Implication for Section 5.1:** there is nothing to rewrite into `ir.access`. All three models are `_inherit` of core `payment`/`account_payment` models, so they rely entirely on access defined by the core modules. **Action for the port:** confirm Odoo 20's core (now expressed as `ir.access`) still grants the needed access to `payment.provider`, `payment.transaction`, and `account.payment.method` for the relevant groups; no module-local change is expected.

### 4.2 Provider & payment-method data seeding (`data/payment_provider_data.xml`)

- **`payment.method` record** `payment_method_onepay` (`:4`): name "OnePay", code `onepay`, sequence 10, active. **The module already ships its own `payment.method` data** — good for Odoo 20's ownership expectation (Section 5.12).
- **`payment.provider` record** `payment_provider_onepay` (`:16`): name/code `onepay`, `state=disabled`, `redirect_form_view_id` → the local `redirect_form` template, `payment_method_ids` linked to the onepay method via `(6,0,[...])`, and `image_128` loaded from the icon.
- **`redirect_form` QWeb template** (`:11`) — see Section 5.

### 4.3 Config parameters

- **Read:** `ir.config_parameter.get_param("web.base.url", "")` — `models/payment_transaction.py:186` (Section 5.3 finding).
- **Written via XML `<function>` / `<record>`:** none found. No `ir.config_parameter` values are seeded by the module.

---

## 5. Views & frontend

### 5.1 View inheritance table (`views/payment_provider_views.xml`)

| View | Model | `inherit_id` | XPath targets | Deprecated syntax? |
|---|---|---|---|---|
| `payment_provider_form_onepay` (`:4`) | `payment.provider` | `payment.payment_provider_form` | `//page[@name='credentials']` (inside, `:10`); `//page[@name='configuration']` (inside, `:28`) | **No `attrs=` / `states=`.** Uses modern `invisible="code != 'onepay'"` and `required="code == 'onepay'"` attribute expressions. |

**Odoo 20 flag:** the two XPaths target `page[@name='credentials']` and `page[@name='configuration']` on the **core payment-provider form** (`payment.payment_provider_form`). These page names are stable across 17–19 but **must be confirmed against the Odoo 20 core view** — if a page was renamed/restructured, the XPath fails at install. Record both expressions for verification.

### 5.2 QWeb templates & asset bundles

- **`redirect_form`** (`data/payment_provider_data.xml:11`) — a minimal redirect form: `<form t-att-action="api_url" method="get" target="_self"></form>`. No `t-esc`, no fields, no bundle registration. Referenced by the provider's `redirect_form_view_id`.
- **Asset bundles:** none. The manifest declares no `assets`, and there is no `web.assets_frontend` / `payment.*` registration.

### 5.3 JS / OWL inventory + Owl-3 flags

- **No `.js` files exist** anywhere in the module (`find . -name '*.js'` → empty).
- No `odoo.define`, no ESM modules, no OWL components, no `static props`/`defaultProps`/`useState`/`useRef`/`useExternalListener`/`t-portal`/`t-model`.
- `t-esc` in QWeb — **none found.**
- **Section 5.2 (Owl 3): none found — zero frontend JS to migrate.**

---

## 6. End-to-end flow narrative

### 6.1 Success path

1. Customer chooses OnePay at checkout and confirms. Odoo creates/uses a `payment.transaction` with `provider_code = "onepay"`.
2. Odoo calls **`payment.transaction._get_specific_rendering_values`** (`models/payment_transaction.py:170`). It validates `onepay_app_id`/`onepay_app_token`/`onepay_hash_salt`, computes `amount_string = "%.2f"`, builds the SHA-256 `hash` (`_onepay_generate_hash`, `:22`), assembles the payload incl. `transaction_redirect_url = <base_url>/payment/onepay/return?reference=<ref>`, and **POSTs to OnePay `/v3/checkout/link/`** via `_onepay_post` (`:219`).
3. OnePay responds with a `redirect_url` (+ transaction id). Odoo stores the id in `provider_reference` (`:248`) and returns `{"api_url": redirect_url}`.
4. The **`redirect_form` template** (`data/payment_provider_data.xml:11`) auto-submits, sending the browser to OnePay's hosted page. Customer pays there.
5. OnePay calls back **`POST /payment/onepay/webhook`** → `onepay_webhook` (`controllers/main.py:62`) → `_process_onepay_payload` (`:30`):
   - `_get_tx_from_notification_data("onepay", payload)` (`models/payment_transaction.py:339`) resolves the tx by `provider_reference` or `reference`.
   - `tx._onepay_verify_status(payload)` (`:259`) **POSTs `/v3/transaction/status/`** to OnePay and normalizes `{reference, provider_reference, status, status_message, amount, currency}`.
   - Processing is dispatched by capability: `_process("onepay", verified_data)` if present (Odoo 19), else `_handle_notification_data`, else `tx._process_notification_data(verified_data)` (`controllers/main.py:39-48`).
   - These route into **`_onepay_apply_payment_status`** (`:413`): currency match → amount match (`float_compare`) → `_onepay_is_success_status` → **`_set_done()`** (`:455`).
   - If `state == "done"` and not yet post-processed, `_post_process()` is called (`controllers/main.py:50-51`).
6. Separately, the customer's browser returns to **`GET/POST /payment/onepay/return`** → `onepay_return` (`:90`), which may re-process the payload and then redirects to **`/payment/status`**, where Odoo shows the confirmed transaction.

### 6.2 Failure / cancel path

1–4. Same as success up to the hosted OnePay page.
5. On a failed/cancelled payment, OnePay's webhook (or the return) still triggers `_process_onepay_payload`. `_onepay_verify_status` queries the status API and returns a non-success `status`/`status_message`.
6. In `_onepay_apply_payment_status`:
   - **Currency mismatch** → `_set_error` with a currency-mismatch message (`:422`), return.
   - **Amount mismatch** (`float_compare != 0`) → `_set_error` (`:440`), return.
   - Otherwise, `_onepay_is_success_status` returns `False` → **`_set_error`** with "OnePay payment was not successful…" (`:457`).
7. `onepay_webhook` returns HTTP 400 JSON only if an **exception** is raised during processing (`controllers/main.py:70-76`); a cleanly-recorded failure still returns `{"status":"ok"}`. `onepay_return` swallows exceptions and redirects to `/payment/status`, which displays the error/cancel state to the customer.

---

## 7. Odoo 20 breaking-change findings

| # | Area (5.x) | File:Line | Current pattern | Required Odoo 20 change | Risk | Effort |
|---|---|---|---|---|---|---|
| 1 | 5.1 Security merge | `security/` (absent); no `ir.model.access.csv`, no `ir.rule` | Module ships no access rules | **None to rewrite.** Verify core `payment`/`account_payment` `ir.access` still grants needed access to the inherited models. | Low | Trivial (verify only) |
| 2 | 5.2 Owl 3 | — | No JS/OWL in module | **None found** — no action. | None | None |
| 3 | 5.3 Typed config params | `models/payment_transaction.py:186` | `ir.config_parameter.sudo().get_param("web.base.url", "")` | Use typed `get_str("web.base.url", "")` (or `get_base_url()` helper if available on the record). Behavior change: typed accessors are the new idiom. **Verify the exact API on Odoo 20.** | Low–Med | Small |
| 4 | 5.4 Binary → BinaryValue | — (Python) | No manual `b64encode/b64decode/len()` on binary | **None found.** (`image_128` is seeded via XML `type="base64" file=`, which is unchanged data-file loading, `data/payment_provider_data.xml:22`.) | None | None |
| 5 | 5.5 Domains → `Domain` | `models/payment_transaction.py:359,364` | `self.search(domain + [("...","=",...)], limit=1)` where `domain=[("provider_code","=","onepay")]` (`:356`) | Prefer `Domain` objects / `Domain.AND`. Operators are hardcoded (no user-supplied operators), so this is a style/forward-compat change, not a security fix. | Low | Small |
| 6 | 5.6 `request` in models | models: **none**; controller only (`controllers/main.py:5,13,23,28,31,102`) | `request` used in controller (allowed) | **None found in model code** — no change required. | None | None |
| 7 | 5.7 Imports | `models/payment_transaction.py:8-10`, `controllers/main.py:4-5` | `from odoo import _, models`; `from odoo.exceptions import ValidationError`; `from odoo.tools import float_compare`; `from odoo import http` / `odoo.http.request` | All public entry points — compliant. No `odoo.osv` / `odoo.orm.*` imports. **None found.** | None | None |
| 8 | 5.8 `_sql_constraints` | — | No `_sql_constraints` | **None found.** | None | None |
| 9 | 5.9 Deprecated ORM accessors | — | No `self._cr/_context/_uid`, no `read_group`, no `_table_query` | **None found.** | None | None |
| 10 | 5.10 RPC / external API | — | OnePay integration is plain HTTPS REST via `requests` (`/v3/checkout/link/`, `/v3/transaction/status/`); no `/xmlrpc`, `/jsonrpc`, or `db` service | **None found** — no Odoo-RPC dependency. | None | None |
| 11 | 5.11 Manifest & platform | `__manifest__.py:3` | `version = "19.0.1.0.0"`; `depends=["payment","account_payment"]`; no `external_dependencies` | Bump `version` → `20.0.1.0.0`; confirm `payment` & `account_payment` exist in Odoo 20 (they do, historically); add `external_dependencies={"python":["requests"]}`; confirm Python 3.12–3.14 / PostgreSQL 16+ (no code barriers seen). | Low | Small |
| 12 | 5.12 Payment-method data ownership | `data/payment_provider_data.xml:4` | Module ships its own `payment.method` (`code=onepay`) and links it on the provider (`:21`) | **Already compliant** — module carries its own method data. Verify the `payment.method` schema/fields (name/code/sequence/active + any newly-required field) against Odoo 20. | Low | Verify |
| 13 | API drift (not in 5.x, but critical) | `controllers/main.py:39-48`; `models/payment_transaction.py:339,372,379,389,402`; `models/payment_provider.py:63,69` | Overrides both legacy (`_get_tx_from_notification_data`, `_process_notification_data`) and newer (`_process`, `_extract_reference`, `_extract_amount_data`, `_apply_updates`) hooks; `hasattr` dispatch; `_setup_provider`/`_ensure_payment_method_line` guarded by `hasattr` | **Pin to the single Odoo 20 payment API.** Confirm which notification/processing hooks Odoo 20 actually calls, drop the dead branches, and confirm `_setup_provider` + `_ensure_payment_method_line` signatures. This is the main functional risk. | **Med** | Medium |

---

## 8. Migration plan outline

Ordered change groups (each depends on the previous being settled):

1. **Verify against live Odoo 20 source first (blocking research step).** Resolve, from the actual Odoo 20 `payment`/`account_payment` code: (a) the exact transaction notification/processing hook names and signatures (finding #13); (b) `payment.provider._setup_provider` and `_ensure_payment_method_line`; (c) the `payment.method` model fields; (d) the core `payment_provider_form` page names (`credentials`, `configuration`); (e) the typed-config accessor for `web.base.url`; (f) that `payment` + `account_payment` are the correct dependency names.
2. **Manifest & platform (Section 5.11, finding #11).** Bump `version` to `20.0.x`; add `external_dependencies` for `requests`; re-pin/confirm Python 3.12–3.14.
3. **Security (Section 5.1, finding #1).** No rewrite expected; just confirm inherited-model access under the new `ir.access` core. Only add module-local `ir.access` rows if a gap is found.
4. **Models (findings #3, #5, #13).** Replace `get_param` with the typed accessor; convert concatenated domains to `Domain`; collapse the `hasattr`-based hook branching to the confirmed Odoo 20 API. Depends on step 1.
5. **Controllers (finding #13).** Align `_process_onepay_payload` dispatch (`controllers/main.py:30-53`) with the single Odoo 20 processing hook; keep `request` usage as-is (controller-local). Depends on step 4.
6. **Views (Section 5.1 views, finding re XPath).** Re-confirm the two XPaths resolve on the Odoo 20 core form; adjust page targets only if renamed. No `attrs`/`states` to fix.
7. **Data (Section 5.12, finding #12).** Confirm `payment.method` and `payment.provider` seed records match the Odoo 20 schema; adjust fields if any became required/renamed.
8. **JS / OWL (Section 5.2).** Nothing to do — no frontend code.
9. **Install/smoke test** on an Odoo 20 instance: install module, enable provider, run success + failure flows (Section 6) end to end.

**Must be verified against live Odoo 20 source** (cannot be concluded from this module alone): items (a)–(f) in step 1 above, plus the exact typed-config API shape (`get_str` vs a record-level `get_base_url()` helper) and whether `_sql_constraints`/`get_param` are *removed* vs merely *deprecated* in the target 20.0 build.

---

## 9. Open questions

1. **Which processing hook does Odoo 20 actually invoke?** The code defensively overrides both the legacy (`_process_notification_data`, `_get_tx_from_notification_data`) and newer (`_process`, `_extract_reference`, `_extract_amount_data`, `_apply_updates`) APIs. I could not determine from this repo alone which set Odoo 20 calls; this must be checked against Odoo 20 core. *(controllers/main.py:39-48; models/payment_transaction.py:339-407)*
2. **`_setup_provider` / `_ensure_payment_method_line` availability.** `_ensure_payment_method_line` is already `hasattr`-guarded (`models/payment_provider.py:69`), implying uncertainty about its presence across versions. Confirm both exist with the same signatures in Odoo 20.
3. **Webhook has no inbound signature verification.** Integrity relies solely on the server-to-server status API plus amount/currency matching (Section 3.3). This is a design question more than a migration blocker, but worth a human decision on whether Odoo 20 hardening (or OnePay's own signed callbacks, if any) should be added during the port.
4. **`web.base.url` typed accessor.** Whether to switch to `get_str(...)` or to a record-level base-URL helper depends on the exact Odoo 20 API; not resolvable from this module. *(models/payment_transaction.py:186)*
5. **Core form page names.** The view XPaths assume `page[@name='credentials']` and `page[@name='configuration']` still exist on the Odoo 20 `payment_provider_form`. Unverifiable without the Odoo 20 core view. *(views/payment_provider_views.xml:10,28)*
6. **No tests exist.** There is no `tests/` directory, so there is no automated regression net for the port; consider adding at least a success/failure flow test during migration.
```

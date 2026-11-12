# OnePay Payment Gateway — Odoo 18/19 → Odoo 20 Migration Changelog

> Branch: `conceptand-10` (not committed — review and commit yourself).
> Scope: minimal, surgical port per `PROMPT.md` + `docs/onepay-odoo20-investigation-report.md`.
> OnePay REST contract (`/v3/checkout/link/`, `/v3/transaction/status/`) and payment-flow behavior are unchanged.

---

## ⚠️ Environment limitation (read first)

**No Odoo 20 source tree and no `odoo-bin` are present on this machine.** I searched the filesystem for `addons/payment`, `payment_demo`, `payment_razorpay`, `payment_mollie`, and `odoo-bin` — none were found.

Consequences:

- **Step 0 (verify against live Odoo 20 core) could not be executed.** The code changes below follow the *documented* Odoo 20 facts given in `PROMPT.md` Section 3 (stated there as sourced from official Odoo 20 docs). Each item that still needs live-core confirmation is marked **🔶 VERIFY**.
- **Section 5 smoke tests could not be run** (no Odoo 20 instance, no database). They remain **outstanding** and are a merge gate per the prompt.
- Where the prompt conditions a change on a Step 0 confirmation I could not obtain (Steps 6–9), I followed the prompt's own conditional logic and **did not** remove safety guards I cannot prove are safe. These are called out below and in **Open decisions**.

Static validation that *was* performed: `python3 -m py_compile` passed on all module Python files; the manifest parses; a grep confirms **zero** residual references to the removed legacy APIs (`_get_tx_from_notification_data`, `_process_notification_data`, `_handle_notification_data`, `hasattr(Transaction`, `get_param`).

---

## Step 0 — Verification answers

| # | Item | Status | Basis |
|---|---|---|---|
| (a) | `_process(provider_code, payment_data)` entry point + `_search_by_reference` lookup; controller calls `_process` | 🔶 **VERIFY** — assumed per prompt §3 | PROMPT.md §3; investigation report finding #13. Mirrored on `payment_razorpay`-style controller shape (could not open core — not on disk). |
| (b) | `payment.provider._setup_provider(code)` and `_ensure_payment_method_line(...)` exist | 🔶 **VERIFY — unresolved** | Could not confirm. `_setup_provider` call retained (unchanged). `_ensure_payment_method_line` **`hasattr` guard retained** (see Step 6). |
| (c) | `payment.method` fields (name/code/sequence/active + any newly-required) | 🔶 **VERIFY** — assumed unchanged | No core to diff against; seed record left as-is (Step 8). |
| (d) | `payment.payment_provider_form` still has `credentials` + `configuration` pages | 🔶 **VERIFY** — assumed unchanged | No core to diff; XPaths left as-is (Step 7). |
| (e) | Base-URL accessor: `get_str("web.base.url", ...)` vs record `get_base_url()` | 🔶 **VERIFY** — chose `get_str` | PROMPT.md §3 states typed `get_str` is the Odoo 20 accessor. Kept exact `web.base.url` + default-`""` semantics. Fallback if `get_str` is absent on the build: `self.get_base_url()`. |
| (f) | `payment` and `account_payment` are valid Odoo 20 depends | 🔶 **VERIFY** — assumed valid | Both are long-standing core modules; no rename known. `depends` left unchanged. |

**Rule applied:** per PROMPT.md §2, if any live-core fact differs from the prompt, the core wins. Since core was unavailable, I implemented to the prompt's documented facts and flagged every assumption above for confirmation before merge.

---

## Change groups

### Step 1 — Manifest & platform ✅ done

`payment_onepay/__manifest__.py`
- `:3` — `version`: `"19.0.1.0.0"` → **`"20.0.1.0.0"`**.
- `:18` — added **`"external_dependencies": {"python": ["requests"]}`** (module imports `requests` at `models/payment_transaction.py:6`).
- `depends = ["payment", "account_payment"]` — left unchanged (🔶 VERIFY 0f).

### Step 2 — Payment transaction API ✅ done

`payment_onepay/models/payment_transaction.py`
- `:10` — added import `from odoo.fields import Domain` (used by Step 5).
- **Removed** legacy override `_get_tx_from_notification_data` (was ≈`:339`).
- **Removed** legacy override `_process_notification_data` (was ≈`:372`).
- **Added** Odoo 20 override **`_search_by_reference(self, provider_code, payment_data)`** (now `:340`), carrying forward the original lookup logic exactly: match `provider_reference` first (from `provider_reference`/`transaction_id`/`ipg_transaction_id`/`onepay_transaction_id`), then fall back to `reference` (from `reference`/`additional_data`/`additionalData`); raises the same `ValidationError` when nothing matches. Non-`onepay` codes delegate to `super()`.
- **Kept unchanged:** `_extract_reference` (now `:379`-ish), `_extract_amount_data`, `_apply_updates` (routes into `_onepay_apply_payment_status`), `_get_specific_rendering_values`, `_onepay_verify_status`, `_onepay_apply_payment_status`, and all `_onepay_*` helpers. No behavior change to these.

🔶 VERIFY (0a): that Odoo 20's `_process` invokes `_search_by_reference(provider_code, payment_data)` with this signature and calls `_apply_updates` after `_extract_amount_data`.

### Step 3 — Controller ✅ done

`payment_onepay/controllers/main.py` — `_process_onepay_payload` (`:30`)
- **Removed** the `hasattr`-based dispatch (`_process` / `_handle_notification_data` / `_process_notification_data`).
- Transaction lookup now uses **`Transaction._search_by_reference("onepay", payload)`** (`:35`) so the server-to-server confirmation (`_onepay_verify_status`) can run before any callback data is trusted.
- Processing now the single Odoo 20 call **`Transaction._process("onepay", verified_data)`** (`:39`).
- Post-processing guard preserved: `if tx.state == "done" and not tx.is_post_processed: tx.sudo()._post_process()`.
- **Unchanged:** both routes `/payment/onepay/webhook` and `/payment/onepay/return`, their `auth="public"`, `csrf=False`, `methods`, and the `_onepay_verify_status` confirmation. `request` usage left in place (correct in a controller).

### Step 4 — Typed config parameter ✅ done

`payment_onepay/models/payment_transaction.py:187`
- `ir.config_parameter.sudo().get_param("web.base.url", "")` → **`...get_str("web.base.url", "")`** (typed Odoo 20 accessor). `.rstrip("/")` and the subsequent "not configured" guard preserved.

🔶 VERIFY (0e): if the target build does not expose `get_str` on `ir.config_parameter`, switch to `self.get_base_url()` (the "not configured" guard then becomes inert but harmless).

### Step 5 — Domains ✅ done

`payment_onepay/models/payment_transaction.py` (inside the new `_search_by_reference`, `:357`–`:372`)
- Concatenated-list domains (`domain + [...]`) replaced with **`Domain` objects**: `base_domain = Domain("provider_code", "=", "onepay")` combined via `Domain.AND([...])`. Operators are hardcoded; functional result identical.

### Step 6 — Provider wiring 🟡 no change (verification-gated)

`payment_onepay/models/payment_provider.py:69`
- The `hasattr(provider, "_ensure_payment_method_line")` guard is **retained**. The prompt makes removal conditional on Step 0b confirming the method exists in Odoo 20; that confirmation was impossible (no core on disk). Removing the guard blindly would risk `AttributeError` on provider create/write. Retained pending confirmation — see **Open decisions #2**.
- The `in provider._fields` guards in `_compute_feature_support_fields` are **retained** (defensive, harmless; these are standard core fields). No version-hedging risk.

### Step 7 — Views 🟡 no change (verification-gated)

`payment_onepay/views/payment_provider_views.xml`
- XPaths `//page[@name='credentials']` (`:10`) and `//page[@name='configuration']` (`:28`) left unchanged. Adjust only if Step 0d shows a page was renamed on the Odoo 20 core form. No `attrs=`/`states=` present — nothing else to change. 🔶 VERIFY (0d).

### Step 8 — Data & payment-method ownership 🟡 no change (verification-gated)

`payment_onepay/data/payment_provider_data.xml`
- `payment.method` (`:4`) and `payment.provider` (`:16`) seed records left unchanged. The module already ships its own `payment.method`, which Odoo 20 expects. Adjust only fields that became required/renamed per Step 0c. 🔶 VERIFY (0c).

### Step 9 — Security ✅ no change needed

- Module ships no `ir.model.access.csv` and no `ir.rule`, so there is nothing to rewrite into `ir.access`. Add module-local `ir.access` rows only if Section 5 testing shows the inherited models lack access under Odoo 20's core `ir.access`. Nothing added.

---

## Files changed (summary)

| File | Change |
|---|---|
| `payment_onepay/__manifest__.py` | version → `20.0.1.0.0`; added `external_dependencies` (requests) |
| `payment_onepay/models/payment_transaction.py` | import `Domain`; removed 2 legacy hooks; added `_search_by_reference`; `get_param`→`get_str`; `Domain` objects |
| `payment_onepay/controllers/main.py` | removed `hasattr` dispatch; `_search_by_reference` + single `_process` call |
| `payment_onepay/models/payment_provider.py` | *(no change — verification-gated)* |
| `payment_onepay/views/payment_provider_views.xml` | *(no change — verification-gated)* |
| `payment_onepay/data/payment_provider_data.xml` | *(no change — verification-gated)* |

Static checks: `py_compile` OK on all module files; manifest parses; zero residual legacy-API references.

---

## Smoke tests (Section 5) — NOT RUN

| # | Test | Result |
|---|---|---|
| 1 | Module installs; provider appears | ⛔ Not run — no Odoo 20 instance on machine |
| 2 | Credentials entry + form (credentials/configuration pages) render | ⛔ Not run |
| 3 | Success flow → `done`, amount+currency gate | ⛔ Not run |
| 4 | Failure/cancel flow → `error`, message, `/payment/status` | ⛔ Not run |
| 5 | No deprecation warnings referencing this module | ⛔ Not run |
| 6 | `./odoo-bin upgrade_code` diff review | ⛔ Not run — no `odoo-bin` |

**These must be executed on a clean Odoo 20 instance before merge.** The port is a merge gate until they pass (PROMPT.md top note + §7).

---

## Open decisions (human call needed)

1. **🔶 Live-core verification outstanding (Step 0 a–f).** All six verification items were assumed from PROMPT.md §3 because no Odoo 20 source is on this machine. Re-run Step 0 against the real build; if anything differs, core wins and the corresponding step must be revised.
2. **`_ensure_payment_method_line` guard (Step 6).** Left guarded by `hasattr` because I could not confirm the method exists in Odoo 20 core (Step 0b). The prompt's Done criteria want legacy `hasattr` hedging gone — the *controller* version-hedging **is** removed, but this provider-wiring guard remains pending confirmation. Once Step 0b is confirmed on the real build, remove the guard (`payment_provider.py:69`) and call `provider._ensure_payment_method_line(allow_create=True)` directly.
3. **Base-URL accessor choice (Step 4 / 0e).** Implemented `get_str`. If the target build lacks it, switch to `self.get_base_url()`.
4. **Webhook has no inbound signature verification** (investigation report §3.3 / Open question #3). Trust rests entirely on the server-to-server `_onepay_verify_status` call plus amount/currency matching. **Per the prompt, the trust model was deliberately left unchanged in this port.** Flagged for a human decision on whether Odoo 20 hardening (or OnePay signed callbacks, if available) should be added in a follow-up.
5. **No automated tests exist.** There is no `tests/` directory, so there is no regression net. Consider adding at least a success/failure flow test alongside the port.

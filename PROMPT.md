# Investigation Prompt — OnePay Payment Gateway Module: Odoo 18/19 → Odoo 20 Upgrade

> **How to use this file:** Give this entire document to your coding agent as its task prompt, run it against the local OnePay module source, and let it produce `onepay-odoo20-investigation-report.md` in the same `docs/` folder. Return that report here and the migration work will be planned and executed from it.

---

## 1. Role & objective

You are a senior Odoo developer performing a **read-only investigation** of an existing **OnePay payment gateway integration module** currently built for **Odoo 18 and 19**. The goal is to prepare a precise, exhaustive migration dossier so the module can be ported to **Odoo 20** (released September 2026; Python 3.12–3.14, PostgreSQL 16+).

You will **not** change any code in this pass. You will produce a single structured report that catalogs what the module does, how it is built, and every place it collides with an Odoo 20 breaking change — each finding tied to a concrete file and line range.

- Investigate the conceptand-10 branch

## 2. Rules of engagement

- **Do not modify, move, rename, or delete any source file.** This is investigation only.
- **Cite everything** as `path/to/file.py:LINE` or `:START–END`. A finding without a location is not useful.
- When you quote code, quote the **minimum** needed to show the pattern (a few lines), not whole files.
- Do not guess. If something is ambiguous or you cannot find it, say so explicitly under an **"Open questions"** heading rather than inventing an answer.
- Prefer facts from the actual source tree over assumptions about how OnePay modules "usually" work.
- If the module is split across several addon folders, investigate all of them and say how they relate.

## 3. What to produce

Write one Markdown file: **`docs/onepay-odoo20-investigation-report.md`**, following the report template in Section 6. It must be self-contained enough that a developer who has never seen this module could plan the Odoo 20 port from it alone.

---

## 4. Investigation tasks

Work through these in order. For each, record findings in the report.

### 4.1 Module inventory & manifest
- Locate the module root(s). List the full directory tree (folders + files), noting anything non-standard.
- Open `__manifest__.py`: record `name`, `version`, `depends`, `external_dependencies` (Python/bin), `data`, `assets`, `application`, `installable`, `license`, `auto_install`, and any `pre_init_hook` / `post_init_hook` / `uninstall_hook`.
- Record the declared Odoo series (from `version`) and confirm whether the code has any version-conditional branches (e.g. `if odoo.release.version_info...`).
- List every third-party Python package imported anywhere in the module.

### 4.2 Python models
- Enumerate every model class: file, `_name` / `_inherit`, and purpose.
- For the **payment provider** model (`_inherit = 'payment.provider'` or legacy `payment.acquirer`): list every field added, every credential/config field (API keys, merchant/access codes, secret hashes, endpoint URLs, environment/test flags), and every overridden method (`_get_supported_currencies`, `_compute_feature_support_fields`, `_get_default_payment_method_codes`, etc.).
- For the **payment transaction** model (`_inherit = 'payment.transaction'`): list overridden methods, especially `_get_specific_rendering_values`, `_get_tx_from_notification_data` (or legacy `_get_tx_from_feedback_data`), `_process_notification_data` (or legacy `_process_feedback_data`), `_send_payment_request`, and status-mapping logic.
- Note any use of: `ir.config_parameter` `get_param`/`set_param`; `self._cr`, `self._context`, `self._uid`; `read_group`; `request` referenced inside a model; `_sql_constraints`; Binary fields with manual base64 (`b64encode`/`b64decode`, `base64.*`, `len()` on binary); manual domain-list concatenation; `ormcache` / `tools.ormcache`; `_table_query`; imports from `odoo.osv` or deep `odoo.*` internals.

### 4.3 Controllers & routes (the OnePay flow — critical)
- Enumerate every controller and `@http.route`: path, `type` (`http`/`json`), `auth`, `methods`, `csrf`, `website`, `sitemap`.
- Identify and document in detail the OnePay redirect/return flow:
  - The **redirect/pay** route that builds the request to OnePay (which `vpc_*` / query parameters, in what order).
  - The **return URL** route the customer is redirected back to.
  - The **IPN / webhook** route OnePay calls server-to-server, if any.
- Document the **signature / secure-hash logic**: algorithm (HMAC-SHA256 vs legacy SHA256), which parameters are hashed, hashing order, the secret used, and where verification happens on return/IPN. Flag any use of `request` that would need adjusting.
- Note any controller that reads raw request body, headers, or query string directly.

### 4.4 Data files & security
- List all XML/CSV in `data/`, `security/`, `views/`, `demo/`.
- **Security:** record the exact contents of `ir.model.access.csv` and every `ir.rule` record. This is the single highest-impact migration area (see 5.1).
- **Provider data:** record how the `payment.provider` record is seeded (`data/payment_provider_data.xml`) and whether the module ships its own `payment.method` records (Odoo 20 expects each provider module to carry its own payment-method data).
- Note any `ir.config_parameter` values set via XML `<function>` or `<record>`.

### 4.5 Views
- List every view record and what it `inherit_id`s.
- Flag deprecated view syntax: `attrs="..."`, `states="..."` (removed since Odoo 17), and any XPath that targets a core element that may have moved/renamed in Odoo 20 (payment provider form, checkout templates). Record each XPath expression and its target.

### 4.6 Frontend — templates, JS/OWL, assets
- List QWeb templates (redirect form template, checkout fragments) and the assets bundles they are registered in (`web.assets_frontend`, `payment.*`, etc.).
- For every `.js` file: note whether it is legacy (`odoo.define`) or ESM, whether it uses OWL, and flag Owl-2 patterns that break under **Owl 3** (see 5.2): `static props` / `defaultProps`, `useState`, `useRef`, `useExternalListener`, `t-portal`, `t-model`, `t-esc`.
- Note any `t-esc` usage in QWeb templates and any JS that patches core payment-form components.

### 4.7 End-to-end payment flow narrative
Write a step-by-step trace of a full successful payment (customer clicks pay → redirect to OnePay → return → IPN → transaction set to `done`), naming the exact method/route at each hop. Then do the same for the failure/cancel path. This is what the migration will be validated against.

### 4.8 External & environment dependencies
- OnePay endpoint URLs (test vs production) and where they are configured.
- Any hardcoded credentials, URLs, or merchant IDs (flag as a finding, don't expose secret values in full).
- Python/runtime assumptions that matter for Python 3.12+ (e.g. packages that may need re-pinning).

---

## 5. Odoo 20 breaking-change checklist (what to flag)

For each item below, search the module and record **every** occurrence with a location and a one-line migration note. If an item has zero occurrences, state "none found" — absence is a useful result.

### 5.1 Security model merge — `ir.model.access` + `ir.rule` → `ir.access`
Odoo 20 replaces separate access-rights CSV and record-rule (`ir.rule`) records with a **single `ir.access` model**. Each row has a model, an `operation` (a subset of `crud`, e.g. `r`, `crud`), an optional group, and an optional domain. A row **with** a group grants; a row **without** a group restricts everyone; restrictions override grants, and there is no default operation. → Flag the current `ir.model.access.csv` and all `ir.rule` records for rewrite.

### 5.2 Owl 3 (frontend)
Owl 3 removes/renames: `static props`/`defaultProps` → `useProps(...)`; `useState` → `proxy`/`signal`/`computed`; `useRef("x")` → `signal.ref()`; `useExternalListener` → `useListener`; `t-portal`/`t-model` → `t-custom-portal` / signal-based `t-model`; `t-esc` reported removed. The compat layer rejects components still declaring `static props`/`defaultProps`, and the bundle no longer exports `useState`/`useRef`/`useExternalListener`. Failures surface at runtime → flag every match.

### 5.3 Typed config parameters
`ir.config_parameter` `get_param`/`set_param` (string-based) are superseded by typed `get_int`/`get_bool`/`get_float`/`get_str` and matching `set_*`. Behavior differs (stored `0` is now valid; invalid values log a warning). → Flag every `get_param`/`set_param` call.

### 5.4 Binary fields → `BinaryValue`
Binary field reads now return a lazy `BinaryValue` (use `.content`, `.to_base64()`, `.size`, `.mimetype`), and writes take `BinaryBytes(...)`. Manual `b64encode`/`b64decode`/`len()` on binary breaks. → Flag all manual base64 handling.

### 5.5 Domains → `Domain` objects
List concatenation to build domains is discouraged (and flagged as a security concern for user-supplied operators). Prefer `Domain` objects (`&`, `|`, `~`, `Domain.AND/OR`). → Flag concatenated-list domains, especially any built from request/user input.

### 5.6 `request` removed from model code
`request` is no longer available inside models; use `env.website` or pass values from the controller. → Flag any model method that references `request`.

### 5.7 Imports & module structure
The ORM now lives under `odoo/orm/`; do not import from `odoo.orm.*`. Use public entry points only (`odoo.api`, `odoo.fields` incl. `Domain`, `odoo.models`, `odoo.tools` incl. `SQL`). `odoo.osv` deprecated since 19.0. → Flag non-public imports.

### 5.8 `_sql_constraints` → constraint descriptors
`_sql_constraints` lists give way to class attributes `models.Constraint` / `models.UniqueIndex` / `models.Index` (names start with `_`). → Flag any `_sql_constraints`.

### 5.9 Deprecated ORM accessors (since 19.0)
`self._cr` → `self.env.cr`; `self._context` → `self.env.context`; `self._uid` → `self.env.uid`; `read_group` → newer grouping calls; `_table_query`/`_init_column`/`_table_has_rows` removed/deprecated. → Flag each.

### 5.10 RPC / external API
`/xmlrpc`, `/xmlrpc/2`, `/jsonrpc` are deprecated for removal; the `db` RPC service is removed in 20; `common`/`object` slated for removal in 22. Binary-field RPC format changed. → Flag any integration (including OnePay IPN tooling or external scripts) relying on these; note the JSON-2 API as the target.

### 5.11 Manifest & platform
`version` → `20.0.x`; confirm every `depends` name still exists in Odoo 20; re-pin external Python deps for Python 3.12–3.14; confirm PostgreSQL 16+ assumptions. → Flag manifest and dependency items.

### 5.12 Payment-method data ownership
In Odoo 20 each provider module carries its own `payment.method` data. → Flag whether the module currently relies on core-seeded methods and must now ship its own.

> Note: this checklist reflects the Odoo 20.0 release-notes / ORM changelog as of the investigation date. A few items (exact removal vs deprecation of `_sql_constraints`, `get_param`) are reported inconsistently across sources — where behavior matters, the report should recommend verifying against the actual Odoo 20 source on the target build rather than assuming.

---

## 6. Report template

Produce `docs/onepay-odoo20-investigation-report.md` with these sections:

```
# OnePay Payment Gateway — Odoo 20 Migration Investigation Report

## 0. Summary
- Module name, current version, Odoo series supported.
- Overall migration difficulty: Low / Medium / High, with a one-paragraph justification.
- Top 5 highest-risk items.

## 1. Module inventory
- Directory tree.
- Manifest breakdown (depends, data, assets, hooks, external deps).

## 2. Models
- Per model: name, inherit, fields, overridden methods, responsibilities.

## 3. Controllers & OnePay flow
- Route table.
- Redirect / return / IPN flow.
- Signature & hash verification logic.

## 4. Data & security
- Access rules (full ir.model.access.csv + ir.rule contents).
- Provider & payment-method data seeding.
- Config parameters.

## 5. Views & frontend
- View inheritance table + deprecated-syntax flags.
- QWeb templates & asset bundles.
- JS/OWL inventory + Owl-3 flags.

## 6. End-to-end flow narrative
- Success path (step by step, with method/route names).
- Failure / cancel path.

## 7. Odoo 20 breaking-change findings
A table, one row per finding:
| # | Area (5.x) | File:Line | Current pattern | Required Odoo 20 change | Risk | Effort |

## 8. Migration plan outline
- Ordered list of change groups (security → manifest → models → controllers → views → JS → data), with dependencies between them.
- What must be verified against live Odoo 20 source.

## 9. Open questions
- Anything ambiguous, missing, or needing a human decision.
```

---

## 7. Done criteria

The investigation is complete when every Section 4 task and every Section 5 checklist item has either concrete findings (with locations) or an explicit "none found", the end-to-end flow is traced for both success and failure, and Section 8 gives an ordered migration outline. Keep the report factual and specific — it is the single source of truth for the Odoo 20 port.
# Full System Check — September 8, 2026

## Overall verdict

**Partially ready.** Core business workflows and role-gated pages are broadly functional, and all 31 repository regression checks pass. The system should not be treated as production-ready until the invoice reset data-loss defect is fixed and the existing local database is reconciled.

## Scope

- Python environment and dependency consistency
- All repository `tests/*_check.py` checks
- 443 simple GET requests across anonymous access and six roles
- Invalid and malformed request handling on primary write endpoints
- Isolated browser walkthrough of landing, login, home, Sales Order, Invoice, Expense, Analytics, Reports, report preview, and Admin Center
- Desktop and 390 × 844 mobile layouts
- Keyboard activation on analytics cards and actions
- Read-only integrity checks of local SQLite databases

The audit used isolated test databases for browser and mutation checks. Existing business records were not edited. Live Render, Supabase, load/stress behavior, multiple physical browsers, and a package vulnerability scan were outside this run.

## Confirmed strengths

- All 31 regression scripts pass.
- Installed Python packages have no broken requirements.
- Main role-protected pages return without server errors across admin, manager, sales staff, accounting staff, compatibility staff, and IT evaluator sessions.
- Login, dashboard navigation, Sales Order item entry, invoice listing and creation UI, Expense entry, Reports, report preview, Admin Center records, and client details load successfully.
- Sales reports correctly reflected the isolated Sales Order total and item detail.
- Analytics ledger generation completed and populated the analytics dashboard from isolated Sales Order and invoice records.
- Desktop layouts are visually consistent, with a clear gold/neutral theme and readable grouping.
- Main mobile page content reflows without page-level horizontal overflow in the checked Sales Order, Invoice, Expense, and Analytics views.
- Interactive analytics cards can be activated from the keyboard.

## Confirmed defects

### 1. Critical — invoice reset leaves orphaned collection receipts

The Admin Center transaction reset deletes invoices with a bulk query but does not delete their `collection_receipts`. SQLite foreign-key enforcement is disabled by default, so database cascade behavior does not run. An isolated reproduction returned success, deleted one invoice, left its receipt behind, and produced a foreign-key violation.

This explains the current `database.db` state: 836 collection receipts, zero invoices, and 836 broken foreign-key references covering 826 missing invoice IDs. The file itself passes SQLite `quick_check`, but its business relationships are invalid.

Evidence: `reset-reproduction.json` and `app.py` transaction-reset implementation.

### 2. High — malformed login can return a server error

Posting an existing username without a password field passes `None` to password verification and raises an exception. An empty password string does not trigger the same crash. The endpoint should normalize a missing password to an empty string and return the standard invalid-credentials response.

### 3. Medium — primary JSON endpoints accept the wrong JSON shape until runtime

Submitting a JSON array instead of an object causes server errors on Sales Order and Invoice creation because the handlers call `.get()` without first checking that the payload is an object. Invalid client input should produce a controlled 400 response rather than a 500.

### 4. Medium — mobile navigation hides destinations

At 390 px wide, navigation remains a single horizontal row. Analytics, Reports, Admin Center, and profile content can be clipped off-screen, with no visible menu button or clear cue that the row scrolls. This makes major destinations difficult to discover and reach on a phone.

### 5. Medium — expanded analytics layout is cramped on mobile

The expanded revenue/forecast card keeps chart controls and descriptive text beside a narrow chart. Text wraps into very short lines and the chart becomes difficult to interpret. Stack the heading, filters, explanation, and chart vertically at the mobile breakpoint.

### 6. Medium — Sales Order form labels are not programmatically associated

Visible labels exist, but several inputs have no associated `<label>` element or equivalent accessible name. Confirmed examples include order date, manual quantity, unit cost, and selling price. Placeholder text partially masks the problem for some text fields but does not replace a proper label.

### 7. Low — mojibake appears in Analytics

Several emoji strings are stored as corrupted text. The empty analytics state visibly renders `ðŸ“Š` instead of the intended chart symbol. Similar corrupted strings exist for table/card controls.

### 8. Release hardening — CSRF and login throttling are absent

State-changing form and JSON requests lack CSRF protection, and login attempts are not rate limited. Existing production protections for the secret key, secure cookies, upload size, and role checks are present.

## Layout review by step

1. **Landing — Healthy.** Clear value statement and calls to action; generous empty space but no visible breakage.
2. **Login — Healthy with error-handling defect.** Clean centered form and readable hierarchy; malformed missing-password submission can crash.
3. **Home — Healthy.** Role-specific shortcuts and activity are clear on desktop.
4. **Sales Order — Mostly healthy.** Item entry works and mobile fields stack cleanly; navigation clipping and missing accessible labels remain.
5. **Invoice — Mostly healthy.** Search, list, status, and creation stages are understandable; the wide summary table relies on contained horizontal scrolling on mobile.
6. **Expense — Mostly healthy.** Required fields and debit reconciliation are clear; the history table scrolls horizontally on mobile.
7. **Analytics — Needs correction.** Ledger generation and charts work; corrupted characters and cramped expanded mobile charts reduce clarity.
8. **Reports — Healthy.** Totals, grouped rows, filters, and preview are coherent. Wide tables require contained scrolling on narrow screens.
9. **Admin Center — Healthy with critical reset defect.** Records and client views load and are understandable; transaction reset can corrupt invoice/receipt relationships.

## Recommended repair order

1. Fix transaction reset to remove collection receipts in the same transaction before invoice deletion, and enable/verify foreign-key enforcement for SQLite connections.
2. Restore the missing invoices from a trusted backup or deliberately reconcile the 836 orphaned receipts. Do not delete them merely to silence the integrity check.
3. Normalize missing login fields and validate JSON object shape before accessing payload properties.
4. Replace corrupted analytics strings with valid UTF-8 text or accessible icons.
5. Add a mobile navigation menu and stack expanded analytics content at the small-screen breakpoint.
6. Associate every form label with its input and run keyboard/screen-reader verification.
7. Add CSRF protection and login throttling before public deployment.

## Evidence files

- `regression-results.json` — results of all 31 repository checks
- `route-results.json` — 443 role and route probes
- `invalid-input-results.json` — malformed payload behavior
- `reset-reproduction.json` — isolated invoice-reset integrity reproduction
- `01-landing.png` through `15-analytics-expanded-mobile.png` — visual evidence captured during this audit

No application source or existing business records were changed by this audit.

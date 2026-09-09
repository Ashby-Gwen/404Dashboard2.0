# System Check — September 8, 2026

Status: Automated checks pass; default local database requires attention.

## Verified

- Python 3.12.10 in the project virtual environment.
- Dependency consistency: pip check reports no broken requirements. This is not a vulnerability audit.
- All 31 repository `tests/*_check.py` scripts passed (exit code 0), covering authentication, approval, roles, sales orders, invoices, collections, expenses, imports, analytics, administration, layout assertions, and migration behavior.
- Database checks used read-only SQLite connections. All three database files passed PRAGMA quick_check.
- No listener was found on local port 5000 at the time of inspection.

## Findings

1. **High — orphaned collection receipts in database.db.** PRAGMA foreign_key_check reported 836 violations, all on collection_receipts.invoice_id referencing invoices.id. There are 836 receipts, zero invoices, and 826 distinct missing invoice IDs. This is the application's fallback database when DATABASE_URL is absent. Reconcile against a trusted backup or source before using it; do not delete receipts simply to clear the check. Passing isolated tests does not validate existing business data.
2. **Release hardening — CSRF protection and login throttling remain absent.** Confirmed against the login implementation and repository documentation. Production secret requirements, cookie settings, and upload limits are present.
3. **Environment — Git ownership mismatch.** Repository owner differs from the current Windows user. Inspection used a command-scoped safe-directory exception; no global settings were changed.
4. **Workspace — inaccessible temporary directory.** tmp3n2wcrue could not be enumerated. The repository checks completed successfully despite this. An existing untracked run.bat contains comments only; it does not start a server.

## Other databases

- instance/analytics_visual_qa.db: quick_check OK; zero foreign-key violations; 18 tables.
- instance/syluxent.db: quick_check OK; zero foreign-key violations; 16 tables.
- database.db: quick_check OK; 836 foreign-key violations; 21 tables.

Zero foreign-key violations does not establish schema completeness or business correctness.

## Scope and next steps

This check covers local code, installed dependency consistency, repository test scripts, and SQLite integrity. It does not verify the live Render deployment, Supabase, browser rendering, performance under load, or package vulnerabilities. Production readiness is not established by these results.

Priority: reconcile the missing invoices and receipts, then implement CSRF protection and login throttling before public release. No application code or business records were edited during this check.

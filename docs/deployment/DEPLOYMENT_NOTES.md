# Render Deployment Notes

This project is prepared for a Render free-tier web service using:

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

## Database Behavior

- Render free web services may sleep after inactivity. The first request after sleep can take longer while the service wakes up.
- Local development uses SQLite automatically when `DATABASE_URL` is not set.
- SQLite on Render free tier is suitable only for demo/prototype use because local file storage is ephemeral and does not persist reliably across restarts.
- For production cloud storage, set Render `DATABASE_URL` to the Supabase PostgreSQL connection string.
- Prefer the Supabase pooled connection string if available. Supabase pooler examples may use port `6543` or `5432` depending on the pooler mode and project region.
- If using the direct Supabase connection string, it may use port `5432`.
- URL-encode the database password if it contains special characters such as `@`, `#`, `%`, `/`, `:`, `?`, or `&`.
- Do not commit `DATABASE_URL` or any database password to GitHub.
- For this Supabase project, the pooler host shown by Supabase is `aws-1-ap-southeast-1.pooler.supabase.com` with user `postgres.bphnkzqgxdbdnxcudkhh`.
- Copy `.env.example` to `.env` for local connection testing only. `.env` is ignored by git.

## Environment Variables

Set this variable in Render:

- `SECRET_KEY`: a long random value used by Flask sessions.
- `DATABASE_URL`: Supabase PostgreSQL pooled connection string for production persistence.
- `DEFAULT_ADMIN_PASSWORD`: the private password for the initial demo admin user.

Optional:

- `DEFAULT_ADMIN_USERNAME`: defaults to `admin` if unset.
- `DEFAULT_MANAGER_PASSWORD`: set this only if you want the app to seed a demo manager user.
- `DEFAULT_STAFF_PASSWORD`: set this only if you want the app to seed a demo staff user.
- `SYLUXENT_ALLOW_INSECURE_DEMO_PASSWORDS`: local-development escape hatch only. Set to `true` to seed the old demo passwords locally; do not enable this on Render.

# Render Deployment Notes

This project is prepared for a Render free-tier web service using:

- Runtime: Python
- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:app`

## Free Tier Behavior

- Render free web services may sleep after inactivity. The first request after sleep can take longer while the service wakes up.
- The app still uses SQLite by default so local development stays simple.
- SQLite data on Render free tier may not persist permanently because free services use an ephemeral filesystem.
- This setup is acceptable for a capstone demo or prototype deployment.
- For production, use PostgreSQL or another persistent database, and set `SYLUXENT_DATABASE_URI` to that persistent database URL.

## Environment Variables

Set this variable in Render:

- `SECRET_KEY`: a long random value used by Flask sessions.
- `DEFAULT_ADMIN_PASSWORD`: the private password for the initial demo admin user.

Optional:

- `SYLUXENT_DATABASE_URI`: leave unset for the demo SQLite fallback, or set it when using a persistent database.
- `DEFAULT_ADMIN_USERNAME`: defaults to `admin` if unset.
- `DEFAULT_MANAGER_PASSWORD`: set this only if you want the app to seed a demo manager user.
- `DEFAULT_STAFF_PASSWORD`: set this only if you want the app to seed a demo staff user.
- `SYLUXENT_ALLOW_INSECURE_DEMO_PASSWORDS`: local-development escape hatch only. Set to `true` to seed the old demo passwords locally; do not enable this on Render.

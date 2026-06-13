# Syluxent Deployment Suggestions

## Detected Tech Stack

- Backend: Flask 2.3 with Flask-SQLAlchemy and Werkzeug authentication helpers
- Database: SQLite through SQLAlchemy
- Data processing: pandas and openpyxl for CSV/Excel imports
- Frontend: Jinja templates, static CSS/JavaScript, Chart.js from CDN
- Runtime assets: local `instance/` database and `static/uploads/` profile files

## Recommended Deployment Path

Use a small VPS or internal company server for the first production deployment. This system depends on a local SQLite database and uploaded files, so a persistent disk is more important than a stateless serverless setup.

Recommended baseline:

- Ubuntu Server LTS or Windows Server
- Python 3.11+
- Nginx or IIS as the reverse proxy
- Waitress on Windows or Gunicorn on Linux as the WSGI server
- Daily backup of `instance/syluxent.db` and `static/uploads/`

## Linux Production Example

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

Run with:

```bash
gunicorn -w 3 -b 127.0.0.1:8000 app:app
```

Place Nginx in front of Gunicorn and proxy HTTPS traffic to `127.0.0.1:8000`.

## Windows Production Example

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install waitress
waitress-serve --host=127.0.0.1 --port=8000 app:app
```

Use IIS, Nginx for Windows, or another reverse proxy to serve HTTPS and forward requests to Waitress.

## Required Production Settings

- Set a strong `SECRET_KEY`; do not rely on development defaults.
- Disable Flask debug mode.
- Keep the SQLite database in `instance/` or another persistent folder.
- Keep `static/uploads/` on persistent storage and include it in backups.
- Restrict direct public access to the database and backup files.
- Use HTTPS for all login and admin activity.

## SQLite Notes

SQLite is acceptable for a capstone, demo, or small office deployment with light concurrent use. If multiple staff members will upload files or write records at the same time, plan a future migration to PostgreSQL.

Before a PostgreSQL migration:

- Replace SQLite-specific date functions used in analytics queries.
- Move database URL into environment configuration.
- Test all reporting and analytics endpoints after migration.

## Backup Suggestions

- Daily: copy `instance/syluxent.db` and `static/uploads/` to a dated backup folder.
- Weekly: copy backups to external storage or cloud storage.
- Before deployment updates: take a manual database backup.
- Test restore at least once before relying on the backup routine.

## CDN And Offline Use

The app currently loads Chart.js and some libraries from CDNs. For internal/offline deployment, download those assets into `static/vendor/` and update templates to load local files.

## Deployment Checklist

- Install dependencies from `requirements.txt`.
- Configure a strong `SECRET_KEY`.
- Start the app under Gunicorn or Waitress, not the Flask development server.
- Put HTTPS reverse proxy in front of the WSGI server.
- Confirm login, admin password reset, data entry, uploads, analytics, and reports.
- Verify backups include the database and uploaded files.

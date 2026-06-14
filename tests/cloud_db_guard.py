import os
import sys


def require_destructive_cloud_db_tests():
    database_uri = (os.environ.get('SYLUXENT_DATABASE_URI') or '').strip()
    if (
        not database_uri
        or 'sqlite' in database_uri.lower()
        or '[YOUR-PASSWORD]' in database_uri
        or '<PASSWORD>' in database_uri
    ):
        print('Skipped cloud DB test: set SYLUXENT_DATABASE_URI to a Supabase Postgres URI.')
        sys.exit(0)

    if not database_uri.startswith(('postgresql://', 'postgresql+psycopg://', 'postgres://')):
        print('Skipped cloud DB test: SYLUXENT_DATABASE_URI must be a Postgres URI.')
        sys.exit(0)

    allow_reset = os.environ.get('ALLOW_DESTRUCTIVE_CLOUD_DB_TESTS', '').lower() in {'1', 'true', 'yes'}
    if not allow_reset:
        print(
            'Skipped cloud DB test: set ALLOW_DESTRUCTIVE_CLOUD_DB_TESTS=true '
            'to allow tests that reset database tables.'
        )
        sys.exit(0)

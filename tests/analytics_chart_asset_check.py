import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def login(client, user, role_name):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = role_name


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='analytics_chart_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        db.session.add(admin)
        db.session.commit()

        with app.test_client() as client:
            asset = client.get('/static/vendor/visuals/graphing-4.4.0.umd.js')
            assert asset.status_code == 200
            assert asset.content_type.startswith('text/javascript')
            assert b'Chart.js v4.4.0' in asset.data[:512]
            assert b'globalThis?globalThis:t||self).Chart=e()' in asset.data[:1024]

            login(client, admin, 'admin')
            html = client.get('/analytics').get_data(as_text=True)
            assert 'vendor/visuals/graphing-4.4.0.umd.js?v=4.4.0-analytics-2' in html
            assert 'vendor/chartjs/chart.umd.min.js' not in html
            assert 'cdn.jsdelivr.net/npm/chart.js' not in html
            assert 'ensureChartLibraryAvailable' in html
            assert 'createAnalyticsChart' in html
            assert 'analyticsChartStatus' in html
            assert 'analyticsChartCount' in html
            assert 'Chart preview is unavailable because the chart library did not load.' in html

    print('Analytics chart asset check passed.')


if __name__ == '__main__':
    main()

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role_name):
    role = Role.query.filter_by(role_name=role_name).first()
    if not role:
        role = Role(role_name=role_name, description=f'{role_name} role')
        db.session.add(role)
        db.session.flush()
    user = User(
        username=username,
        password_hash=generate_password_hash('test123'),
        role_id=role.id,
        status='ACTIVE',
    )
    db.session.add(user)
    return user


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()
        add_user('mobile_admin', 'admin')
        add_user('mobile_manager', 'manager')
        add_user('mobile_staff', 'staff')
        db.session.commit()

        with app.test_client() as client:
            admin_login = client.post('/login', data={
                'username': 'mobile_admin', 'password': 'test123',
            })
            assert admin_login.status_code == 302
            assert admin_login.headers['Location'].endswith('/dashboard')
            admin_page = client.get('/database-interface')
            assert admin_page.status_code == 200
            html = admin_page.get_data(as_text=True)
            assert 'id="recordsTab"' in html and 'nav-link active' in html
            assert 'activateInitialAdminTab' in html
            assert "requests: { id: 'notificationsTab', load: loadNotifications }" in html
            assert "audit: { id: 'auditTab', load: loadAuditLogs }" in html

        with app.test_client() as client:
            manager_login = client.post('/login', data={
                'username': 'mobile_manager', 'password': 'test123',
            })
            assert manager_login.status_code == 302
            assert manager_login.headers['Location'].endswith('/dashboard')
            denied = client.get('/database-interface')
            assert denied.status_code in {302, 403}

        with app.test_client() as client:
            staff_login = client.post('/login', data={
                'username': 'mobile_staff', 'password': 'test123',
            })
            assert staff_login.status_code == 302
            assert staff_login.headers['Location'].endswith('/dashboard')

    print('Admin mobile landing checks passed.')


if __name__ == '__main__':
    main()

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import AuditLog, Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='approval_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        db.session.add(admin)
        db.session.commit()

        with app.test_client() as client:
            register_response = client.post('/register', data={
                'email': 'new.staff@example.com',
                'username': 'new_staff',
                'password': 'staff123',
                'confirm_password': 'staff123',
            })
            assert register_response.status_code == 302

            pending_user = User.query.filter_by(username='new_staff').first()
            assert pending_user is not None
            assert pending_user.status == 'pending'

            blocked_login = client.post('/login', data={
                'username': 'new_staff',
                'password': 'staff123',
            })
            assert blocked_login.status_code == 200
            with client.session_transaction() as session:
                assert 'user_id' not in session

            with client.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            notifications = client.get('/admin/notifications').get_json()
            assert notifications['success'] is True
            assert notifications['pending_account_count'] == 1
            assert notifications['account_approvals'][0]['username'] == 'new_staff'

            approval_response = client.post(
                f'/admin/users/{pending_user.id}/action',
                json={'action': 'approve', 'admin_password': 'admin123'},
            ).get_json()
            assert approval_response['success'] is True

            db.session.refresh(pending_user)
            assert pending_user.status == 'approved'
            assert pending_user.approved_by == admin.id
            assert pending_user.approved_at is not None
            assert AuditLog.query.filter_by(action='APPROVE_USER', record_id=str(pending_user.id)).first() is not None

            client.get('/logout')
            approved_login = client.post('/login', data={
                'username': 'new_staff',
                'password': 'staff123',
            })
            assert approved_login.status_code == 302
            with client.session_transaction() as session:
                assert session['username'] == 'new_staff'

    print('User approval check passed.')


if __name__ == '__main__':
    main()

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
            password_hash=generate_password_hash('Admin123!'),
            password_updated_at=None,
            role_id=admin_role.id,
            status='approved',
        )
        db.session.add(admin)
        db.session.commit()

        with app.test_client() as client:
            admin_case_login = client.post('/login', data={
                'username': 'APPROVAL_ADMIN',
                'password': 'Admin123!',
            })
            assert admin_case_login.status_code == 302
            with client.session_transaction() as session:
                assert session['username'] == 'approval_admin'
            client.get('/logout')

            duplicate_case_response = client.post('/register', data={
                'email': 'duplicate.case@example.com',
                'username': 'Approval_Admin',
                'password': 'Staff123!',
                'confirm_password': 'Staff123!',
            })
            assert duplicate_case_response.status_code == 200
            assert User.query.filter_by(username='Approval_Admin').first() is None

            weak_register_response = client.post('/register', data={
                'email': 'weak.staff@example.com',
                'username': 'weak_staff',
                'password': 'staff123',
                'confirm_password': 'staff123',
            })
            assert weak_register_response.status_code == 200
            assert User.query.filter_by(username='weak_staff').first() is None

            register_response = client.post('/register', data={
                'email': 'new.staff@example.com',
                'username': 'new_staff',
                'password': 'Staff123!',
                'confirm_password': 'Staff123!',
            })
            assert register_response.status_code == 302

            pending_user = User.query.filter_by(username='new_staff').first()
            assert pending_user is not None
            assert pending_user.status == 'pending'
            assert pending_user.password_updated_at is not None
            assert pending_user.password_change_required is False

            blocked_login = client.post('/login', data={
                'username': 'new_staff',
                'password': 'Staff123!',
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
                json={'action': 'approve', 'admin_password': 'Admin123!'},
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
                'password': 'Staff123!',
            })
            assert approved_login.status_code == 302
            with client.session_transaction() as session:
                assert session['username'] == 'new_staff'

            temp_user = User(
                username='temp_staff',
                password_hash=generate_password_hash('Temp123!'),
                password_change_required=True,
                role_id=Role.query.filter_by(role_name='staff').first().id,
                status='approved',
            )
            db.session.add(temp_user)
            db.session.commit()

            client.get('/logout')
            temp_login = client.post('/login', data={
                'username': 'temp_staff',
                'password': 'Temp123!',
            })
            assert temp_login.status_code == 302
            forced_profile = client.get('/dashboard')
            assert forced_profile.status_code == 302
            assert '/profile' in forced_profile.location

            weak_profile = client.post('/profile', data={
                'username': 'temp_staff',
                'email': '',
                'current_password': 'Temp123!',
                'new_password': 'weakpass',
                'confirm_password': 'weakpass',
            })
            assert weak_profile.status_code == 200
            db.session.refresh(temp_user)
            assert temp_user.password_change_required is True

            strong_profile = client.post('/profile', data={
                'username': 'temp_staff',
                'email': '',
                'current_password': 'Temp123!',
                'new_password': 'Fresh123!',
                'confirm_password': 'Fresh123!',
            })
            assert strong_profile.status_code == 302
            db.session.refresh(temp_user)
            assert temp_user.password_change_required is False
            assert temp_user.password_updated_at is not None

            register_html = client.get('/register').get_data(as_text=True)
            assert 'static/js/password-strength.js' in register_html
            assert 'data-password-strength' in register_html
            assert 'data-password-input="#password"' in register_html
            assert 'data-confirm-password-input="#confirm_password"' in register_html
            assert 'role="progressbar"' in register_html

            with client.session_transaction() as session:
                session['user_id'] = temp_user.id
                session['username'] = temp_user.username
                session['role'] = 'staff'
            profile_html = client.get('/profile').get_data(as_text=True)
            assert 'static/js/password-strength.js' in profile_html
            assert 'data-password-input="#new_password"' in profile_html
            assert 'data-password-optional="true"' in profile_html
            assert 'data-strength-check="special"' in profile_html

    print('User approval check passed.')


if __name__ == '__main__':
    main()

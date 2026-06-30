import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import AuditLog, Role, SessionRecord, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role, password='pass123', status='approved'):
    user = User(
        username=username,
        password_hash=generate_password_hash(password),
        role_id=role.id,
        status=status,
    )
    db.session.add(user)
    db.session.flush()
    return user


def post_action(client, user, action, password='admin123', reason=''):
    return client.post(
        f'/admin/users/{user.id}/action',
        json={'action': action, 'admin_password': password, 'reason': reason},
    )


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        roles = {role.role_name: role for role in Role.query.all()}
        for role_name in ('sales staff', 'accounting staff', 'IT Evaluator'):
            if role_name not in roles:
                role = Role(role_name=role_name, description=role_name.title())
                db.session.add(role)
                db.session.flush()
                roles[role_name] = role
        admin = add_user('action_admin', roles['admin'], 'admin123')
        staff = add_user('action_staff', roles['staff'])
        sales = add_user('action_sales', roles['sales staff'])
        accounting = add_user('action_accounting', roles['accounting staff'])
        manager = add_user('action_manager', roles['manager'])
        evaluator = add_user('action_it_evaluator', roles['IT Evaluator'])
        pending = add_user('action_pending', roles['staff'], status='pending')
        pending_reject = add_user('action_pending_reject', roles['staff'], status='pending')
        rejected = add_user('action_rejected', roles['staff'], status='rejected')
        db.session.add(SessionRecord(
            user_id=staff.id,
            username=staff.username,
            role_name='staff',
            status='ACTIVE',
        ))
        db.session.add(SessionRecord(
            user_id=manager.id,
            username=manager.username,
            role_name='manager',
            status='ACTIVE',
        ))
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            wrong_password = post_action(client, staff, 'disable', 'wrong', 'Policy violation')
            assert wrong_password.status_code == 403
            assert db.session.get(User, staff.id).status == 'approved'

            missing_reason = post_action(client, staff, 'disable')
            assert missing_reason.status_code == 400

            disabled = post_action(client, staff, 'disable', reason='Repeated unauthorized access.')
            assert disabled.status_code == 200, disabled.get_json()
            db.session.refresh(staff)
            assert staff.status == 'disabled'
            assert staff.disabled_reason == 'Repeated unauthorized access.'
            active_session = SessionRecord.query.filter_by(user_id=staff.id).first()
            assert active_session.status == 'FORCED_LOGOUT'
            disable_audit = AuditLog.query.filter_by(action='DISABLE_USER', record_id=str(staff.id)).first()
            assert disable_audit is not None
            assert 'Repeated unauthorized access.' in disable_audit.new_value
            assert 'admin123' not in disable_audit.new_value

            enabled = post_action(client, staff, 'enable')
            assert enabled.status_code == 200
            db.session.refresh(staff)
            assert staff.status == 'approved'
            assert staff.disabled_reason is None
            enable_audit = AuditLog.query.filter_by(action='ENABLE_USER', record_id=str(staff.id)).first()
            assert 'Repeated unauthorized access.' in enable_audit.old_value

            assert evaluator.evaluation_enabled is False
            enabled_evaluation = post_action(client, evaluator, 'enable_evaluation')
            assert enabled_evaluation.status_code == 200, enabled_evaluation.get_json()
            db.session.refresh(evaluator)
            assert evaluator.evaluation_enabled is True
            evaluation_enable_audit = AuditLog.query.filter_by(
                action='ENABLE_EVALUATION_ACCESS',
                record_id=str(evaluator.id),
            ).first()
            assert evaluation_enable_audit is not None

            disabled_evaluation = post_action(client, evaluator, 'disable_evaluation')
            assert disabled_evaluation.status_code == 200, disabled_evaluation.get_json()
            db.session.refresh(evaluator)
            assert evaluator.evaluation_enabled is False
            evaluation_disable_audit = AuditLog.query.filter_by(
                action='DISABLE_EVALUATION_ACCESS',
                record_id=str(evaluator.id),
            ).first()
            assert evaluation_disable_audit is not None

            for specialized in (sales, accounting):
                promoted = post_action(client, specialized, 'promote_manager')
                assert promoted.status_code == 200, promoted.get_json()
                db.session.refresh(specialized)
                assert specialized.role.role_name == 'manager'

            promoted_staff = post_action(client, staff, 'promote_manager')
            assert promoted_staff.status_code == 200
            db.session.refresh(staff)
            assert staff.role.role_name == 'manager'

            demoted = post_action(client, manager, 'demote_staff')
            assert demoted.status_code == 200
            db.session.refresh(manager)
            assert manager.role.role_name == 'staff'
            assert SessionRecord.query.filter_by(user_id=manager.id).first().status == 'FORCED_LOGOUT'

            approved = post_action(client, pending, 'approve')
            assert approved.status_code == 200
            db.session.refresh(pending)
            assert pending.status == 'approved'
            assert pending.approved_by == admin.id

            rejected_pending = post_action(client, pending_reject, 'reject')
            assert rejected_pending.status_code == 200
            db.session.refresh(pending_reject)
            assert pending_reject.status == 'rejected'
            assert AuditLog.query.filter_by(
                action='REJECT_USER',
                record_id=str(pending_reject.id),
            ).first() is not None

            reenabled_rejected = post_action(client, rejected, 'enable')
            assert reenabled_rejected.status_code == 200
            db.session.refresh(rejected)
            assert rejected.status == 'approved'

            protected = post_action(client, admin, 'disable', reason='Not allowed')
            assert protected.status_code == 409

            bypass_update = client.post(
                f'/update-user/{staff.id}',
                json={
                    'username': staff.username,
                    'email': '',
                    'role_id': roles['staff'].id,
                },
            )
            assert bypass_update.status_code == 409

            bypass_bulk = client.post('/admin/bulk-update', json={
                'table': 'users',
                'ids': [staff.id],
                'status': 'disabled',
            })
            assert bypass_bulk.status_code == 409

            bypass_delete = client.delete(f'/delete-user/{staff.id}')
            assert bypass_delete.status_code == 409

            bypass_approval = client.post(
                f'/admin/users/{staff.id}/approval',
                json={'decision': 'reject'},
            )
            assert bypass_approval.status_code == 409

            grid = client.get('/admin/data-grid?table=users').get_json()['grid']
            assert 'role_name' in grid['columns']
            assert 'disabled_reason' in grid['columns']
            assert 'evaluation_enabled' in grid['columns']
            assert all('role_name' in row for row in grid['rows'])
            assert all('evaluation_enabled' in row for row in grid['rows'])

    admin_html = open(os.path.join(ROOT, 'templates', 'admin.html'), encoding='utf-8').read()
    assert 'id="gridTable"' in admin_html
    assert 'background-image: url("data:image/svg+xml' in admin_html
    assert 'id="editUserModal"' in admin_html
    assert '>Edit User</button>' in admin_html
    assert 'editUserAdminPassword' in admin_html
    assert 'editUserReason' in admin_html
    assert "action: selectedUserAction" in admin_html
    assert 'Enable evaluation access' in admin_html
    assert 'disable_evaluation' in admin_html
    assert 'deactivateUser(' not in admin_html

    print('Admin user management check passed.')


if __name__ == '__main__':
    main()

import os
import sys
from datetime import datetime


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AuditLog,
    Client,
    Role,
    SessionRecord,
    User,
    app,
    db,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()

        admin_role = Role(role_name='admin', description='Admin')
        manager_role = Role(role_name='manager', description='Manager')
        db.session.add_all([admin_role, manager_role])
        db.session.flush()
        admin = User(
            username='grid_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        manager = User(
            username='grid_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='approved',
        )
        db.session.add_all([admin, manager])
        db.session.add_all([
            Client(client_name='ALPHA STORE', contact_info='North region'),
            Client(client_name='BETA STORE', contact_info='South region'),
            Client(client_name='GAMMA SHOP', contact_info='North region'),
            Client(client_name='DELTA MART', contact_info='Central region'),
            Client(client_name='EPSILON MARKET', contact_info='East region'),
            Client(client_name='ZETA OUTLET', contact_info='West region'),
        ])
        db.session.add(SessionRecord(
            user_id=admin.id,
            username=admin.username,
            role_name='admin',
            login_at=datetime(2026, 7, 6, 0, 3, 5),
            status='ACTIVE',
        ))
        db.session.add(AuditLog(
            username='grid_admin',
            action='CONCURRENT_DEVICE_LOGIN',
            table_name='session_records',
            created_at=datetime(2026, 7, 6, 0, 4, 0),
        ))
        db.session.add(AuditLog(
            username='grid_admin',
            action='PROMOTE_USER_MANAGER',
            table_name='session_records',
            created_at=datetime(2026, 7, 6, 0, 5, 0),
        ))
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            first_page = client.get('/admin/data-grid?table=clients&page=1&page_size=5').get_json()
            assert first_page['success'] is True
            assert first_page['grid']['total'] == 6
            assert first_page['grid']['page_size'] == 5
            assert first_page['grid']['pages'] == 2
            assert len(first_page['grid']['rows']) == 5

            filtered = client.get('/admin/data-grid', query_string={
                'table': 'clients',
                'filters': '{"contact_info":"North"}',
                'sort': 'client_name',
                'direction': 'asc',
            }).get_json()
            assert filtered['success'] is True
            assert [row['client_name'] for row in filtered['grid']['rows']] == ['ALPHA STORE', 'GAMMA SHOP']

            searched = client.get('/admin/data-grid?table=clients&search=market').get_json()
            assert searched['success'] is True
            assert searched['grid']['total'] == 1
            assert searched['grid']['rows'][0]['client_name'] == 'EPSILON MARKET'

            sorted_payload = client.get('/admin/data-grid', query_string={
                'table': 'clients',
                'sort': 'client_name',
                'direction': 'desc',
                'page_size': 5,
            }).get_json()
            assert sorted_payload['success'] is True
            assert [row['client_name'] for row in sorted_payload['grid']['rows']] == [
                'ZETA OUTLET',
                'GAMMA SHOP',
                'EPSILON MARKET',
                'DELTA MART',
                'BETA STORE',
            ]

            unsafe = client.get('/admin/data-grid', query_string={
                'table': 'clients',
                'sort': 'client_name;drop table users',
                'filters': '{"unknown":"ALPHA","client_name":"STORE"}',
            }).get_json()
            assert unsafe['success'] is True
            assert unsafe['grid']['total'] == 2
            assert unsafe['grid']['sort'] == 'id'
            assert 'unknown' not in unsafe['grid']['filters']

            sessions = client.get('/admin/data-grid?table=session_records&page=1&page_size=5').get_json()
            assert sessions['success'] is True
            assert sessions['grid']['rows'][0]['login_at'] == '2026-07-06T00:03:05Z'

            audit_logs = client.get('/admin/audit-logs').get_json()
            assert audit_logs['success'] is True
            audit_row = audit_logs['logs'][0]
            assert audit_row['action'] == 'PROMOTE_USER_MANAGER'
            assert audit_row['table_name'] == 'session_records'
            assert audit_row['display_action'] == 'Promoted User To Manager'
            assert audit_row['display_table_name'] == 'Sessions'
            concurrent_row = next(log for log in audit_logs['logs'] if log['action'] == 'CONCURRENT_DEVICE_LOGIN')
            assert concurrent_row['display_action'] == 'Multiple Active Sessions'
            assert concurrent_row['display_table_name'] == 'Sessions'

            blocked_sql = client.post('/admin/sql-console', json={
                'sql': 'DROP TABLE clients',
                'dry_run': True,
            }).get_json()
            assert blocked_sql['success'] is False
            assert 'Blocked SQL keyword: DROP' in blocked_sql['error']
            assert blocked_sql['details']['type'] == 'blocked_keyword'
            assert blocked_sql['details']['keyword'] == 'drop'

            invalid_sql = client.post('/admin/sql-console', json={
                'sql': 'SELECT missing_column FROM clients',
                'dry_run': True,
            }).get_json()
            assert invalid_sql['success'] is False
            assert invalid_sql['error'] == 'SQL execution failed.'
            assert invalid_sql['details']['type']
            assert 'missing_column' in invalid_sql['details']['message']

            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'
            denied = client.get('/admin/data-grid?table=clients')
            assert denied.status_code in {302, 403}

    admin_html = open(os.path.join(ROOT, 'templates', 'admin.html'), encoding='utf-8').read()
    assert 'display_action || log.action' in admin_html
    assert 'display_table_name || log.table_name' in admin_html

    print('Admin data grid check passed.')


if __name__ == '__main__':
    main()

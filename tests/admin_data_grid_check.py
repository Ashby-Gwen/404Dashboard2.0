import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    Client,
    Role,
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

            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'
            denied = client.get('/admin/data-grid?table=clients')
            assert denied.status_code in {302, 403}

    print('Admin data grid check passed.')


if __name__ == '__main__':
    main()

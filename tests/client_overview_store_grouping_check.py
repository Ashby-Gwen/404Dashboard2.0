import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    Client,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, so_number, store_name, branch, total):
    order = SalesOrder(
        so_number=so_number,
        client_id=client.id,
        company_name=client.client_name,
        store_name=store_name,
        store_branch=branch,
        order_date=date(2026, 6, 1),
        total_amount=total,
        status='COMPLETED',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='POS TERMINAL',
        quantity=1,
        unit_cost=total / 2,
        selling_price=total,
        total=total,
    ))
    return order


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='store_group_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='approved',
        )
        north_owner = Client(client_name='NORTH HOLDINGS INC')
        alt_owner = Client(client_name='ALT RETAIL CORP')
        south_owner = Client(client_name='SOUTH RETAIL CORP')
        db.session.add_all([manager, north_owner, alt_owner, south_owner])
        db.session.flush()

        add_order(north_owner, 'SO-N-001', 'North Store', 'Branch A', 1000)
        add_order(alt_owner, 'SO-N-002', ' north store ', 'Branch B', 2000)
        add_order(south_owner, 'SO-S-001', 'South Store', 'Main', 700)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            payload = client.get('/api/analytics/clients?year=2026&period=year').get_json()
            assert payload['success'] is True
            stores = {row['store_key']: row for row in payload['clients']}

            assert len(payload['clients']) == 2
            north = stores['NORTH STORE']
            assert north['store_name'] == 'NORTH STORE'
            assert north['total_revenue'] == 3000
            assert north['order_count'] == 2
            assert north['branches_count'] == 2
            assert north['store_branches'] == ['BRANCH A', 'BRANCH B']
            assert north['company_name'] == 'ALT RETAIL CORP, NORTH HOLDINGS INC'

            south = stores['SOUTH STORE']
            assert south['store_name'] == 'SOUTH STORE'
            assert south['company_name'] == 'SOUTH RETAIL CORP'
            assert south['total_revenue'] == 700

    print('Client overview Store Name grouping check passed.')


if __name__ == '__main__':
    main()

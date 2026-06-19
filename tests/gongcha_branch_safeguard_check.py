import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Client, Role, SalesOrder, SalesOrderItem, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, number, store, branch, order_date):
    order = SalesOrder(
        so_number=number,
        client_id=client.id,
        company_name=client.client_name,
        store_name=store,
        store_branch=branch,
        order_date=order_date,
        total_amount=100,
        status='COMPLETED',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='TEA ITEM',
        quantity=1,
        unit_cost=50,
        selling_price=100,
        total=100,
    ))


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='gongcha_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='approved',
        )
        gongcha = Client(client_name='GONGCHA FOOD CORPORATION')
        db.session.add_all([manager, gongcha])
        db.session.flush()

        add_order(gongcha, 'SO-G-001', 'Gongcha', 'Branch-A', date(2026, 1, 1))
        add_order(gongcha, 'SO-G-002', ' GONGCHA ', 'BRANCH A', date(2026, 2, 1))
        add_order(gongcha, 'SO-G-003', 'Gongcha.', ' branch   a ', date(2026, 3, 1))
        add_order(gongcha, 'SO-G-004', 'Gongcha', 'HEAD OFFICE', date(2026, 4, 1))
        add_order(gongcha, 'SO-G-005', 'Gongcha', 'NO BRANCH', date(2026, 5, 1))
        add_order(gongcha, 'SO-G-006', 'Gongcha', 'N/A', date(2026, 6, 1))
        add_order(gongcha, 'SO-G-OLD', 'Gongcha', 'OLD BRANCH', date(2025, 6, 1))
        db.session.commit()

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            payload = web.get('/api/analytics/clients?year=2026&period=year').get_json()
            assert payload['success'] is True
            assert len(payload['clients']) == 1
            result = payload['clients'][0]
            assert result['store_name'] == 'GONGCHA'
            assert result['order_count'] == 6
            assert result['branches_count'] == 2
            assert result['store_branches'] == ['BRANCH A', 'HEAD OFFICE']

    print('Gongcha branch safeguard check passed.')


if __name__ == '__main__':
    main()

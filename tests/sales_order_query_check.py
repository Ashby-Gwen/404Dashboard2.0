import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    Client,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def add_sales_order(client, so_number, order_date, status='PENDING'):
    order = SalesOrder(
        so_number=so_number,
        client_id=client.id,
        company_name='DISPLAY COMPANY',
        official_client_name=client.client_name,
        original_entered_client_name='DISPLAY COMPANY',
        store_name='MAIN STORE',
        store_branch='NORTH BRANCH',
        order_date=order_date,
        sales_staff='Alex Sales',
        total_amount=999999,
        status=status,
    )
    db.session.add(order)
    db.session.flush()
    db.session.add_all([
        SalesOrderItem(
            sales_order_id=order.id,
            particular='POS TERMINAL',
            quantity=1,
            unit_cost=100,
            selling_price=1000,
            total=1000,
        ),
        SalesOrderItem(
            sales_order_id=order.id,
            particular='CASH DRAWER',
            quantity=2,
            unit_cost=50,
            selling_price=250,
            total=500,
        ),
    ])
    return order


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        accounting_role = Role.query.filter_by(role_name='accounting staff').first()
        if not accounting_role:
            accounting_role = Role(role_name='accounting staff', description='Accounting')
            db.session.add(accounting_role)
            db.session.flush()
        manager_role = Role.query.filter_by(role_name='manager').first()

        accounting = User(
            username='so_accounting',
            password_hash=generate_password_hash('pass123'),
            role_id=accounting_role.id,
            status='approved',
        )
        manager = User(
            username='so_manager',
            password_hash=generate_password_hash('pass123'),
            role_id=manager_role.id,
            status='approved',
        )
        client = Client(client_name='CANONICAL CLIENT', status='ACTIVE')
        db.session.add_all([accounting, manager, client])
        db.session.flush()

        first = add_sales_order(client, 'SO-001', date(2026, 6, 1))
        second = add_sales_order(client, 'SO-002', date(2026, 6, 5), status='COMPLETED')
        db.session.add_all([
            Invoice(
                invoice_number='INV-SO-001-A',
                sales_order_id=first.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 2),
                total_amount=1500,
                amount_paid=300,
                balance=1200,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='INV-SO-001-B',
                sales_order_id=first.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 3),
                total_amount=1500,
                amount_paid=200,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='INV-SO-002',
                sales_order_id=second.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 6),
                total_amount=1500,
                amount_paid=1500,
                balance=0,
                status='PAID',
            ),
        ])
        db.session.commit()

        with app.test_client() as client_app:
            with client_app.session_transaction() as session:
                session['user_id'] = accounting.id
                session['username'] = accounting.username
                session['role'] = 'accounting staff'

            pending_payload = client_app.get('/get-pending-sales-orders').get_json()
            assert pending_payload['success'] is True
            rows = pending_payload['sales_orders']
            assert [row['so_number'] for row in rows].count('SO-001') == 1
            assert all(row['so_number'] != 'SO-002' for row in rows)
            row = next(item for item in rows if item['so_number'] == 'SO-001')
            assert row['company_name'] == 'DISPLAY COMPANY'
            assert row['client_name'] == 'CANONICAL CLIENT'
            assert row['store_name'] == 'MAIN STORE'
            assert row['store_branch'] == 'NORTH BRANCH'
            assert row['sales_staff'] == 'Alex Sales'
            assert row['total_amount'] == 1500
            assert row['invoice_count'] == 2
            assert row['invoice_amount_paid'] == 500
            assert row['current_balance'] == 1000

            detail_payload = client_app.get(f'/get-sales-order-details/{first.id}').get_json()
            assert detail_payload['success'] is True
            assert detail_payload['sales_order']['total_amount'] == 1500
            assert detail_payload['sales_order']['last_invoice_date'] == '2026-06-03'
            assert len(detail_payload['sales_order']['items']) == 2
            assert detail_payload['sales_order']['items'][0]['particular'] == 'POS TERMINAL'
            assert detail_payload['sales_order']['items'][0]['quantity'] == 1
            assert detail_payload['sales_order']['items'][0]['selling_price'] == 1000
            assert detail_payload['sales_order']['items'][0]['total'] == 1000
            assert detail_payload['sales_order']['items'][1]['particular'] == 'CASH DRAWER'
            assert detail_payload['sales_order']['items'][1]['quantity'] == 2
            assert detail_payload['sales_order']['items'][1]['selling_price'] == 250
            assert detail_payload['sales_order']['items'][1]['total'] == 500

            search_cases = [
                'SO-001',
                'MAIN STORE',
                'DISPLAY COMPANY',
                'Alex Sales',
                'PENDING',
                '2026-06-01',
            ]
            for query in search_cases:
                search_payload = client_app.get('/get-pending-sales-orders', query_string={'q': query}).get_json()
                assert search_payload['success'] is True
                assert [row['so_number'] for row in search_payload['sales_orders']].count('SO-001') == 1
                assert all(row['so_number'] != 'SO-002' for row in search_payload['sales_orders'])

            no_match_payload = client_app.get('/get-pending-sales-orders', query_string={'q': 'SO-002'}).get_json()
            assert no_match_payload['success'] is True
            assert no_match_payload['sales_orders'] == []

        with app.test_client() as manager_app:
            with manager_app.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            analytics_payload = manager_app.get('/api/analytics/sales?year=2026&period=year').get_json()
            assert analytics_payload['success'] is True
            history_by_so = {item['so_number']: item for item in analytics_payload['history']['table_data']}
            assert history_by_so['SO-001']['total'] == 1500
            assert history_by_so['SO-001']['store_name'] == 'MAIN STORE'
            assert history_by_so['SO-001']['sales_staff'] == 'Alex Sales'

    print('Sales order query check passed.')


if __name__ == '__main__':
    main()

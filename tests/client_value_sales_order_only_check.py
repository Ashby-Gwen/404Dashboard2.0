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


def add_order(client, so_number, order_date, line_total, paid_amount=0, store_name='Main', store_branch='HQ'):
    order = SalesOrder(
        so_number=so_number,
        client_id=client.id,
        company_name=client.client_name,
        store_name=store_name,
        store_branch=store_branch,
        order_date=order_date,
        sales_staff='QA Staff',
        total_amount=line_total,
        status='COMPLETED',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='POS TERMINAL',
        quantity=1,
        unit_cost=100,
        selling_price=line_total,
        total=line_total,
    ))
    if paid_amount:
        db.session.add(Invoice(
            invoice_number=f'INV-{so_number}',
            sales_order_id=order.id,
            invoice_type='SALES',
            invoice_date=order_date,
            total_amount=line_total,
            amount_paid=paid_amount,
            balance=max(line_total - paid_amount, 0),
            status='PAID',
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
            username='sales_order_value_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='approved',
        )
        ordering_client = Client(client_name='ORDERING FIRST CLIENT')
        paid_client = Client(client_name='PAID ONLY CLIENT')
        broad_client = Client(client_name='BROAD COVERAGE CLIENT')
        narrow_client = Client(client_name='NARROW COVERAGE CLIENT')
        db.session.add_all([manager, ordering_client, paid_client, broad_client, narrow_client])
        db.session.flush()

        add_order(ordering_client, 'SO-HIGH-1', date(2026, 4, 1), 2500, paid_amount=0, store_name='Ordering Store', store_branch='North')
        add_order(ordering_client, 'SO-HIGH-2', date(2026, 5, 1), 3000, paid_amount=0, store_name='Ordering Store', store_branch='South')
        add_order(ordering_client, 'SO-HIGH-3', date(2026, 6, 1), 3500, paid_amount=0, store_name='Ordering Store', store_branch='Main')
        add_order(paid_client, 'SO-LOW-1', date(2026, 6, 1), 500, paid_amount=50000, store_name='Paid Store')
        add_order(broad_client, 'SO-BROAD-1', date(2026, 5, 1), 500, store_name='Broad Store', store_branch='East')
        add_order(broad_client, 'SO-BROAD-2', date(2026, 6, 1), 500, store_name='Broad Store', store_branch='West')
        add_order(narrow_client, 'SO-NARROW-1', date(2026, 5, 1), 500, store_name='Narrow Store', store_branch='Central')
        add_order(narrow_client, 'SO-NARROW-2', date(2026, 6, 1), 500, store_name='Narrow Store', store_branch='Central')
        add_order(broad_client, 'SO-BROAD-OLD', date(2025, 6, 1), 500, store_name='Broad Store', store_branch='Old Branch')
        db.session.commit()

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            response = web.get('/api/analytics/clients?year=2026&period=year')
            assert response.status_code == 200, response.get_data(as_text=True)
            payload = response.get_json()
            assert payload['success'] is True

            clients = {item['store_name'].upper(): item for item in payload['clients']}
            ordering = clients['ORDERING STORE']
            paid_only = clients['PAID STORE']
            broad = clients['BROAD STORE']
            narrow = clients['NARROW STORE']

            assert ordering['total_revenue'] == 9000
            assert paid_only['total_revenue'] == 500
            assert paid_only['total_paid'] == 50000
            assert ordering['client_performance_score'] > paid_only['client_performance_score']
            assert ordering['client_performance_score'] == 100

            breakdown = ordering['score_breakdown']
            assert 'payment_reliability' not in breakdown
            assert breakdown == {
                'total_sales_order_amount': 50,
                'order_frequency': 30,
                'branch_count': 20,
            }
            assert sum(breakdown.values()) == ordering['client_performance_score']
            assert broad['total_revenue'] == narrow['total_revenue'] == 1000
            assert broad['order_count'] == narrow['order_count'] == 2
            assert broad['branches_count'] == 2
            assert narrow['branches_count'] == 1
            assert broad['store_branches'] == ['EAST', 'WEST']
            assert broad['client_performance_score'] > narrow['client_performance_score']
            assert ordering['cohort'] in {
                'Core Ordering Clients',
                'Growth Ordering Clients',
                'Developing Ordering Clients',
                'Low Order Activity',
            }

    print('Client value Sales Order-only check passed.')


if __name__ == '__main__':
    main()

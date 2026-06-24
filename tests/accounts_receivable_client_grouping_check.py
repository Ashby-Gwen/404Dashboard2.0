import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    Client,
    ClientAlias,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
    normalize_client_match_key,
)
from analytics_services import build_analytics_payload  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, number, order_date, total):
    order = SalesOrder(
        so_number=number,
        client_id=client.id,
        company_name=client.client_name,
        official_client_name=client.client_name,
        order_date=order_date,
        total_amount=total,
        status='PENDING',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='GROUPING TEST ITEM',
        quantity=1,
        unit_cost=total / 2,
        selling_price=total,
        total=total,
    ))
    return order


def add_invoice(number, invoice_date, total, paid, balance, order=None, client_name=None):
    invoice = Invoice(
        invoice_number=number,
        sales_order_id=order.id if order else None,
        invoice_type='SALES',
        invoice_date=invoice_date,
        total_amount=total,
        amount_paid=paid,
        balance=balance,
        status='PAID' if balance == 0 else ('PARTIAL' if paid else 'UNPAID'),
        uploaded_client_name=client_name,
    )
    db.session.add(invoice)
    return invoice


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='ar_grouping_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='ACTIVE',
        )
        first_client = Client(client_name='CANONICAL CLIENT')
        duplicate_client = Client(client_name='CANONICAL CLIENT')
        db.session.add_all([manager, first_client, duplicate_client])
        db.session.flush()
        db.session.add(ClientAlias(
            alias_name='CANONICAL TRADING',
            normalized_alias=normalize_client_match_key('CANONICAL TRADING'),
            client_id=first_client.id,
            status='ACTIVE',
        ))

        first_order = add_order(first_client, 'SO-AR-001', date(2026, 1, 5), 1000)
        add_order(duplicate_client, 'SO-AR-002', date(2026, 2, 5), 500)
        add_order(first_client, 'SO-AR-OLD', date(2025, 2, 5), 700)
        add_invoice('INV-AR-001', date(2026, 1, 10), 1000, 400, 600, order=first_order)
        add_invoice('INV-AR-ALIAS', date(2026, 3, 1), 300, 100, 200, client_name='CANONICAL TRADING')
        add_invoice('INV-AR-EXACT', date(2026, 3, 2), 200, 50, 150, client_name='CANONICAL CLIENT')
        add_invoice('INV-AR-UNKNOWN-1', date(2026, 4, 1), 250, 50, 200, client_name='MYSTERY CO')
        add_invoice('INV-AR-UNKNOWN-2', date(2026, 4, 2), 100, 0, 100, client_name='Mystery Co.')
        add_invoice('INV-AR-OLD', date(2025, 4, 1), 900, 0, 900, client_name='CANONICAL CLIENT')
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            dashboard_html = client.get('/dashboard?year=2026').get_data(as_text=True)
            assert 'Generate Report' in dashboard_html
            assert 'View Analytics' in dashboard_html
            assert 'clients_summary' not in dashboard_html

            analytics_response = client.get('/get-analytics?year=2026')
            assert analytics_response.status_code == 200
            analytics = analytics_response.get_json()['analytics']
            assert analytics['summary']['accounts_receivable'] == 1750
            canonical_balance = next(
                item['balance'] for item in analytics['client_balances']
                if item['client_name'] == 'CANONICAL CLIENT'
            )
            assert canonical_balance == 1450
            assert analytics['unmapped_clients'][0]['balance'] == 300

        direct_analytics = build_analytics_payload(
            db,
            {
                'Client': Client,
                'ClientAlias': ClientAlias,
                'Invoice': Invoice,
                'PurchaseOrder': __import__('app').PurchaseOrder,
                'SalesOrder': SalesOrder,
                'SalesOrderItem': SalesOrderItem,
            },
            date(2026, 1, 1),
            date(2027, 1, 1),
        )
        assert direct_analytics['summary']['accounts_receivable'] == 1750

    print('Accounts receivable client grouping check passed.')


if __name__ == '__main__':
    main()

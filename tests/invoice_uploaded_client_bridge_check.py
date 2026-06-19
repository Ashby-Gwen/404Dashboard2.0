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
    normalize_upload_row,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, number, amount):
    order = SalesOrder(
        so_number=number,
        client_id=client.id,
        company_name=client.client_name,
        official_client_name=client.client_name,
        store_name='BRIDGE STORE',
        store_branch='MAIN',
        order_date=date(2026, 6, 1),
        total_amount=amount,
        status='PENDING',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='BRIDGE ITEM',
        quantity=1,
        unit_cost=amount / 2,
        selling_price=amount,
        total=amount,
    ))
    return order


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='invoice_bridge_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        bridge_client = Client(client_name='GONCHA FOOD CORPORATION')
        ambiguous_client = Client(client_name='MULTI ORDER CLIENT')
        db.session.add_all([admin, bridge_client, ambiguous_client])
        db.session.flush()
        bridge_order = add_order(bridge_client, 'SO-BRIDGE-1', 1000)
        add_order(ambiguous_client, 'SO-MULTI-1', 500)
        add_order(ambiguous_client, 'SO-MULTI-2', 700)
        db.session.commit()

        normalized_invoice = normalize_upload_row('invoice', {
            'Invoice Number': 'INV-BRIDGE-1',
            'Uploaded Client Name': 'GONCHA FOOD CORP',
            'Invoice Date': '2026-06-05',
            'Amount Paid': 400,
        })
        assert normalized_invoice['uploaded_client_name'] == 'GONCHA FOOD CORP'

        normalized_order = normalize_upload_row('sales_order', {
            'Sales Order Number': 'SO-HEADER-1',
            'Uploaded Client Name': 'GONCHA FOOD CORPORATION',
            'Order Date': '2026-06-05',
            'Total Amount': 100,
        })
        assert normalized_order['client_name'] == 'GONCHA FOOD CORPORATION'
        assert normalized_order['company_name'] == 'GONCHA FOOD CORPORATION'

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            linked_response = web.post('/admin/upload-commit/invoice', json={
                'rows': [normalized_invoice],
            })
            assert linked_response.status_code == 200, linked_response.get_json()
            linked_invoice = Invoice.query.filter_by(invoice_number='INV-BRIDGE-1').one()
            assert linked_invoice.sales_order_id == bridge_order.id
            assert linked_invoice.uploaded_client_name == 'GONCHA FOOD CORP'
            assert linked_invoice.invoice_type == 'SALES'
            assert linked_invoice.admin_upload_note == 'Matched using Uploaded Client Name'
            assert linked_invoice.balance == 600

            ambiguous_row = normalize_upload_row('invoice', {
                'Invoice Number': 'INV-MULTI-1',
                'Uploaded Client Name': 'MULTI ORDER CLIENT',
                'Invoice Date': '2026-06-06',
                'Amount Paid': 100,
            })
            ambiguous_response = web.post('/admin/upload-commit/invoice', json={
                'rows': [ambiguous_row],
            })
            assert ambiguous_response.status_code == 200, ambiguous_response.get_json()
            ambiguous_invoice = Invoice.query.filter_by(invoice_number='INV-MULTI-1').one()
            assert ambiguous_invoice.sales_order_id is None
            assert ambiguous_invoice.uploaded_client_name == 'MULTI ORDER CLIENT'

    print('Invoice Uploaded Client Name bridge check passed.')


if __name__ == '__main__':
    main()

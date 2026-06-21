import io
import os
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import app as app_module  # noqa: E402
from app import (  # noqa: E402
    Client,
    CollectionReceipt,
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


CSV_PATH = (
    ROOT.parent
    / 'Data'
    / 'Demo (defense)'
    / 'Collections (Paid Invoices)'
    / 'syluxent_collection_receipt_2.csv'
)


def upload_csv(web):
    with CSV_PATH.open('rb') as source:
        return web.post(
            '/admin/upload-preview/invoice',
            data={'files': (io.BytesIO(source.read()), CSV_PATH.name)},
            content_type='multipart/form-data',
            headers={'Accept': 'application/json'},
        )


def main():
    assert CSV_PATH.exists(), CSV_PATH
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()
        role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='collection_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=role.id,
            status='approved',
        )
        db.session.add(admin)
        db.session.commit()

        with app.test_client() as anonymous:
            unauthorized = anonymous.post(
                '/admin/upload-commit/invoice',
                json={'rows': []},
                headers={'Accept': 'application/json'},
            )
            assert unauthorized.status_code == 401
            assert unauthorized.is_json

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            preview = upload_csv(web)
            assert preview.status_code == 200, preview.get_data(as_text=True)
            payload = preview.get_json()
            assert len(payload['rows']) == 832
            assert payload['grouped_invoice_count'] == 824
            assert payload['conflicts'] == []
            assert payload['rows'][0]['invoice_number'] == 'CR-4640'
            assert any(
                row['invoice_number'].startswith(('SVI-', 'SVL-'))
                and row['invoice_type'] == 'SERVICE'
                for row in payload['rows']
            )
            assert any(
                row['invoice_number'].startswith('SI-') and row['invoice_type'] == 'SALES'
                for row in payload['rows']
            )

            invoice_conflict = web.post(
                '/admin/upload-commit/invoice',
                json={'rows': [
                    {
                        'invoice_number': 'SI-CONFLICT',
                        'uploaded_client_name': 'CLIENT A',
                        'invoice_date': '2025-01-01',
                        'amount_paid': 100,
                        'payment_amount': 100,
                        'cr_number': 'TEST-CONFLICT-1',
                    },
                    {
                        'invoice_number': 'SI-CONFLICT',
                        'uploaded_client_name': 'CLIENT B',
                        'invoice_date': '2025-01-01',
                        'amount_paid': 100,
                        'payment_amount': 100,
                        'cr_number': 'TEST-CONFLICT-2',
                    },
                ]},
                headers={'Accept': 'application/json'},
            )
            assert invoice_conflict.status_code == 409
            assert invoice_conflict.is_json
            assert Invoice.query.count() == 0

            accepted_rows = payload['rows']
            select_count = 0

            def count_selects(conn, cursor, statement, parameters, context, executemany):
                nonlocal select_count
                if statement.lstrip().upper().startswith('SELECT'):
                    select_count += 1

            event.listen(db.engine, 'before_cursor_execute', count_selects)
            try:
                committed = web.post(
                    '/admin/upload-commit/invoice',
                    json={'rows': accepted_rows},
                    headers={'Accept': 'application/json'},
                )
            finally:
                event.remove(db.engine, 'before_cursor_execute', count_selects)
            assert committed.status_code == 200, committed.get_data(as_text=True)
            result = committed.get_json()
            assert result['source_rows'] == 832
            assert result['grouped_records'] == 824
            assert result['created'] == 824
            assert result['standalone'] == 824
            assert result['duplicate_receipts_skipped'] == 0
            assert Invoice.query.count() == 824
            assert CollectionReceipt.query.count() == 832
            assert select_count < 40, f'Expected bounded SELECT queries, saw {select_count}'
            assert Invoice.query.filter_by(invoice_number='CR-4640').one().cr_number == '4640'
            assert Invoice.query.filter(
                Invoice.invoice_number.like('SVI-%'),
                Invoice.invoice_type == 'SERVICE',
            ).count() > 0
            assert Invoice.query.filter(Invoice.invoice_number.like('SI-%'), Invoice.invoice_type == 'SALES').count() > 0

            repeated = web.post(
                '/admin/upload-commit/invoice',
                json={'rows': accepted_rows},
                headers={'Accept': 'application/json'},
            )
            assert repeated.status_code == 200, repeated.get_data(as_text=True)
            repeated_result = repeated.get_json()
            assert repeated_result['created'] == 0
            assert repeated_result['updated'] == 0
            assert repeated_result['duplicate_receipts_skipped'] == 832
            assert Invoice.query.count() == 824
            assert CollectionReceipt.query.count() == 832

            overpay_client = Client(client_name='OVERPAY TEST CLIENT')
            db.session.add(overpay_client)
            db.session.flush()
            overpay_order = SalesOrder(
                so_number='SO-OVERPAY-1',
                client_id=overpay_client.id,
                company_name=overpay_client.client_name,
                official_client_name=overpay_client.client_name,
                store_name='OVERPAY STORE',
                order_date=date(2025, 1, 1),
                total_amount=100,
                status='PARTIAL',
            )
            db.session.add(overpay_order)
            db.session.flush()
            db.session.add(SalesOrderItem(
                sales_order_id=overpay_order.id,
                particular='TEST ITEM',
                quantity=1,
                unit_cost=50,
                selling_price=100,
                total=100,
            ))
            db.session.commit()

            client_only_overpayment = web.post(
                '/admin/upload-commit/invoice',
                json={'rows': [{
                    'invoice_number': 'SI-CLIENT-FALLBACK',
                    'uploaded_client_name': overpay_client.client_name,
                    'invoice_date': '2025-01-02',
                    'amount_paid': 150,
                    'payment_amount': 150,
                    'cr_number': 'TEST-OVERPAY-STANDALONE',
                }]},
                headers={'Accept': 'application/json'},
            )
            assert client_only_overpayment.status_code == 200
            fallback_result = client_only_overpayment.get_json()
            assert fallback_result['standalone'] == 1
            assert Invoice.query.filter_by(
                invoice_number='SI-CLIENT-FALLBACK',
            ).one().sales_order_id is None

            linked_invoice = Invoice(
                invoice_number='SI-EXACT-OVERPAY',
                sales_order_id=overpay_order.id,
                invoice_type='SALES',
                invoice_date=date(2025, 1, 2),
                payment_amount=90,
                total_amount=100,
                amount_paid=90,
                balance=10,
                status='PARTIAL',
                uploaded_client_name=overpay_client.client_name,
                upload_source='admin_upload',
                cr_number='TEST-EXACT-ORIGINAL',
            )
            db.session.add(linked_invoice)
            db.session.commit()
            exact_overpayment = web.post(
                '/admin/upload-commit/invoice',
                json={'rows': [{
                    'invoice_number': 'SI-EXACT-OVERPAY',
                    'uploaded_client_name': overpay_client.client_name,
                    'invoice_date': '2025-01-03',
                    'amount_paid': 20,
                    'payment_amount': 20,
                    'cr_number': 'TEST-EXACT-NEW',
                }]},
                headers={'Accept': 'application/json'},
            )
            assert exact_overpayment.status_code == 409
            assert exact_overpayment.get_json()['overpayments'][0]['available_balance'] == 10
            db.session.refresh(linked_invoice)
            assert linked_invoice.amount_paid == 90

            malformed = web.post(
                '/admin/upload-preview/invoice',
                data={'files': (
                    io.BytesIO(b'INVOICE #,CLIENT,DATE,AMOUNT PAID,CR #,SUMMARY\nSI 1,CLIENT,not-a-date,bad,1,test\n'),
                    'bad.csv',
                )},
                content_type='multipart/form-data',
                headers={'Accept': 'application/json'},
            )
            assert malformed.status_code == 400
            assert malformed.is_json

            with patch.object(
                app_module,
                'invoice_upload_schema_status',
                return_value={'ready': False, 'missing': ['sales_order_items.sales_order_branch_id']},
            ):
                schema_error = web.post(
                    '/admin/upload-commit/invoice',
                    json={'rows': [payload['rows'][0]]},
                    headers={'Accept': 'application/json'},
                )
            assert schema_error.status_code == 500
            assert schema_error.is_json
            assert schema_error.get_json()['error_type'] == 'database_schema'

            with patch.object(app_module, 'commit_invoice_upload_batch', side_effect=RuntimeError('forced failure')):
                server_error = web.post(
                    '/admin/upload-commit/invoice',
                    json={'rows': [payload['rows'][0]]},
                    headers={'Accept': 'application/json'},
                )
            assert server_error.status_code == 500
            assert server_error.is_json

    print('Invoice collection CSV check passed.')


if __name__ == '__main__':
    main()

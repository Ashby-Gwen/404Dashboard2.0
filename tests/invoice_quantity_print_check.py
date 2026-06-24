import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AuditLog,
    Client,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    canonical_invoice_type,
    db,
    init_db,
    normalize_upload_row,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='invoice_quantity_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        customer = Client(client_name='INVOICE QUANTITY CLIENT')
        db.session.add_all([admin, customer])
        db.session.flush()
        order = SalesOrder(
            so_number='SO-IQ-001',
            client_id=customer.id,
            company_name=customer.client_name,
            store_name='INVOICE QUANTITY STORE',
            store_branch='MAIN',
            order_date=date(2026, 6, 19),
            total_amount=1000,
            status='PENDING',
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(SalesOrderItem(
            sales_order_id=order.id,
            particular='WHOLE ITEM',
            quantity=2,
            unit_cost=100,
            selling_price=500,
            total=1000,
        ))
        db.session.add_all([
            Invoice(
                invoice_number='si-conflict-1',
                sales_order_id=order.id,
                invoice_type='SERVICE',
                invoice_date=date(2026, 6, 19),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='svi-conflict-1',
                sales_order_id=order.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 19),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='legacy-1',
                sales_order_id=order.id,
                invoice_type='SERVICE',
                invoice_date=date(2026, 6, 19),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
        ])
        db.session.commit()

        assert canonical_invoice_type(' svi-000001 ', 'SALES') == 'SERVICE'
        assert canonical_invoice_type('si-000001', 'SERVICE') == 'SALES'
        assert canonical_invoice_type('legacy-1', 'SERVICE') == 'SERVICE'

        try:
            normalize_upload_row('sales_order', {
                'Company Name': 'TEST',
                'Order Date': '2026-06-19',
                'Quantity': '1.5',
            })
            raise AssertionError('Fractional upload quantity was accepted.')
        except ValueError as error:
            assert 'whole number' in str(error)

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            created_invoice = web.post('/create-invoice', json={
                'sales_order_id': order.id,
                'invoice_number': 'svi-new-1',
                'invoice_type': 'SALES',
                'invoice_date': '2026-06-19',
                'payment_amount': 0,
                'tax_amount_paid': 0,
            })
            assert created_invoice.status_code == 200, created_invoice.get_json()
            saved_invoice = Invoice.query.filter_by(invoice_number='SVI-NEW-1').one()
            assert saved_invoice.invoice_type == 'SERVICE'

            sales_payload = web.get('/get-invoices?invoice_type=SALES').get_json()
            service_payload = web.get('/get-invoices?invoice_type=SERVICE').get_json()
            assert {row['invoice_number'] for row in sales_payload['invoices']} == {'SI-CONFLICT-1'}
            assert {row['invoice_number'] for row in service_payload['invoices']} == {
                'SVI-CONFLICT-1', 'SVI-NEW-1', 'LEGACY-1'
            }
            assert all(row['invoice_type'] == 'SALES' for row in sales_payload['invoices'])
            assert all(row['invoice_type'] == 'SERVICE' for row in service_payload['invoices'])

            fractional = web.post('/create-sales-order', json={
                'company_name': customer.client_name,
                'store_name': 'FRACTION STORE',
                'store_branch': 'MAIN',
                'order_date': '2026-06-19',
                'items': [{
                    'particular': 'FRACTIONAL ITEM',
                    'quantity': 1.5,
                    'unit_cost': 10,
                    'selling_price': 20,
                }],
            })
            assert fractional.status_code == 400
            assert 'whole number' in fractional.get_json()['error']

            fractional_commit = web.post('/admin/upload-commit/sales_order', json={
                'rows': [{
                    'company_name': customer.client_name,
                    'store_name': 'UPLOAD STORE',
                    'store_branch': 'MAIN',
                    'order_date': '2026-06-19',
                    'quantity': 2.5,
                    'selling_price': 20,
                    'total_amount': 50,
                }],
            })
            assert fractional_commit.status_code == 400
            assert 'whole number' in fractional_commit.get_json()['error']

            print_response = web.get(f'/sales-orders/{order.id}/print')
            print_html = print_response.get_data(as_text=True)
            assert '>2</td>' in print_html
            assert '>2.00</td>' not in print_html

            legacy_print_audit = web.post('/api/reports/audit-export', json={
                'report': 'revenue',
                'export_type': 'PDF',
            })
            assert legacy_print_audit.status_code == 200
            print_audit = AuditLog.query.filter_by(
                action='EXPORT_REPORT',
                record_id='revenue',
            ).order_by(AuditLog.id.desc()).first()
            assert print_audit is not None
            assert "'export_type': 'PRINT'" in print_audit.new_value

        analytics_html = open(
            os.path.join(ROOT, 'templates', 'analytics.html'),
            encoding='utf-8'
        ).read()
        assert "toDataURL('image/png', 1)" in analytics_html
        assert 'Chart preview is available on-screen before printing.' not in analytics_html
        assert '.analytics-paper *' in analytics_html
        assert 'Print Preview' in analytics_html
        assert '>Print</button>' in analytics_html
        assert 'Preview PDF' not in analytics_html
        assert 'Print / Save PDF' not in analytics_html
        assert 'analytics-print-heading' in analytics_html
        assert 'body>*:not(#analyticsPrintModal)' in analytics_html.replace(' ', '')
        assert '.analytics-preview-toolbar{display:none!important;}' in analytics_html.replace(' ', '').replace('\n', '')

        reports_html = open(
            os.path.join(ROOT, 'templates', 'reports.html'),
            encoding='utf-8'
        ).read()
        assert 'openReportPrintPreview()' in reports_html
        assert 'Print Preview' in reports_html
        assert '>Print</button>' in reports_html
        assert "auditExport('PRINT')" in reports_html
        assert 'exportReportPdf' not in reports_html
        assert 'Preview PDF' not in reports_html
        assert 'Print / Save PDF' not in reports_html
        assert 'print-heading' in reports_html
        assert 'body>*:not(#reportPreviewModal)' in reports_html.replace(' ', '')
        assert '.preview-toolbar{display:none!important;}' in reports_html.replace(' ', '').replace('\n', '')
        assert "letter ${isPortrait ? 'portrait' : 'landscape'}" in reports_html

    print('Invoice, quantity, and Analytics print check passed.')


if __name__ == '__main__':
    main()

import io
import os
import sys
from datetime import date

import pandas as pd


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AuditLog,
    Client,
    Invoice,
    PurchaseOrder,
    PurchaseOrderDebit,
    Role,
    SalesOrder,
    SalesOrderBranch,
    SalesOrderItem,
    User,
    app,
    app_models,
    db,
)
from analytics_services import get_clients_analysis  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


HEADERS = [
    'DATE',
    'SO NUMBER',
    'COMPANY NAME',
    'STORE NAME',
    'STORE BRANCH',
    'SALES STAFF',
    'PARTICULAR',
    'COST',
    'QUANTITY',
    'SELLING PRICE',
    'TOTAL REVENUE',
    'TOTAL COST',
]


def workbook(rows):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(rows, columns=HEADERS).to_excel(writer, sheet_name='Compiled', index=False)
    output.seek(0)
    return output


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        role = Role(role_name='admin', description='Test admin')
        client_record = Client(client_name='EXAMPLE COMPANY')
        db.session.add_all([role, client_record])
        db.session.flush()
        admin = User(
            username='compiled_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=role.id,
            status='approved',
        )
        db.session.add(admin)
        db.session.commit()

        source_rows = [
            ['2026-01-05', 1, 'EXAMPLE COMPANY', 'GONGCHA', 'SM MOA', 'MARITESS BALANQUIT', 'POS SET', 100, 1, 200, 200, 100],
            ['2026-01-05', 1, 'EXAMPLE COMPANY', 'GONGCHA', 'SM TAYTAY', 'MARITESS BALANQUIT', 'PRINTER', 50, 2, 100, 200, 100],
            ['2026-01-06', 1, 'EXAMPLE COMPANY', 'GONGCHA', 'SM CEBU', 'JOANNE ZAPANTA', 'DELIVERY FEE', 20, 0, 40, None, None],
        ]

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            preview = web.post(
                '/admin/compiled-sales/preview',
                data={'file': (workbook(source_rows), 'compiled.xlsx')},
                content_type='multipart/form-data',
            )
            assert preview.status_code == 200, preview.get_data(as_text=True)
            preview_data = preview.get_json()
            assert preview_data['summary']['sales_orders'] == 2
            assert preview_data['summary']['branches'] == 3
            assert preview_data['summary']['multi_branch_orders'] == 1
            assert preview_data['summary']['invalid_rows'] == 1

            rows = preview_data['rows']
            zero_row = next(row for row in rows if row['quantity'] == 0)
            zero_row['quantity'] = 1
            zero_row['total_revenue'] = 40
            zero_row['total_cost'] = 20

            committed = web.post('/admin/compiled-sales/commit', json={
                'filename': 'compiled.xlsx',
                'rows': rows,
                'resolutions': {},
            })
            assert committed.status_code == 200, committed.get_data(as_text=True)
            result = committed.get_json()
            assert result['created_orders'] == 2
            assert result['created_branches'] == 3
            assert result['created_items'] == 3

            maritess = SalesOrder.query.filter_by(sales_staff='MARITESS BALANQUIT').one()
            assert maritess.so_number == 'SO-001'
            assert maritess.store_branch == 'MULTIPLE BRANCHES'
            assert SalesOrderBranch.query.filter_by(sales_order_id=maritess.id).count() == 2
            assert SalesOrderItem.query.filter_by(sales_order_id=maritess.id).count() == 2
            assert all(item.sales_order_branch_id for item in maritess.items)

            analysis = get_clients_analysis(
                db,
                app_models(),
                date(2026, 1, 1),
                date(2027, 1, 1),
            )
            gongcha = analysis['clients'][0]
            assert gongcha['branches_count'] == 3
            assert set(gongcha['store_branches']) == {'SM MOA', 'SM TAYTAY', 'SM CEBU'}

            duplicate = web.post('/admin/compiled-sales/commit', json={
                'filename': 'compiled.xlsx',
                'rows': rows,
                'resolutions': {},
            }).get_json()
            assert duplicate['created_orders'] == 0
            assert len(duplicate['skipped_duplicates']) == 2
            assert SalesOrder.query.count() == 2
            assert SalesOrderItem.query.count() == 3

            invoice = Invoice(
                invoice_number='SI-RESET-1',
                sales_order_id=maritess.id,
                invoice_type='SALES',
                invoice_date=date(2026, 1, 7),
                total_amount=400,
                amount_paid=0,
                balance=400,
                status='UNPAID',
            )
            expense = PurchaseOrder(
                check_voucher_number='CV-RESET',
                check_number='CHK-RESET',
                check_date=date(2026, 1, 8),
                date=date(2026, 1, 8),
                particulars='Reset test',
                supplier_payee='Supplier',
                cash_amount=100,
            )
            db.session.add_all([invoice, expense])
            db.session.flush()
            db.session.add(PurchaseOrderDebit(
                purchase_order_id=expense.id,
                debit_type='Various Expenses',
                amount=100,
            ))
            db.session.commit()

            blocked = web.post('/admin/transaction-reset', json={
                'areas': ['sales_orders'],
                'confirmation': 'RESET TRANSACTIONS',
            })
            assert blocked.status_code == 409

            reset = web.post('/admin/transaction-reset', json={
                'areas': ['sales_orders', 'invoices', 'expenses'],
                'confirmation': 'RESET TRANSACTIONS',
            })
            assert reset.status_code == 200, reset.get_data(as_text=True)
            assert SalesOrder.query.count() == 0
            assert SalesOrderBranch.query.count() == 0
            assert SalesOrderItem.query.count() == 0
            assert Invoice.query.count() == 0
            assert PurchaseOrder.query.count() == 0
            assert PurchaseOrderDebit.query.count() == 0
            assert AuditLog.query.filter_by(action='RESET_TRANSACTIONS').first() is not None

    print('Compiled Sales import check passed.')


if __name__ == '__main__':
    main()

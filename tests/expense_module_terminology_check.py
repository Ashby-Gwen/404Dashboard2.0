import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AuditLog,
    PurchaseOrder,
    PurchaseOrderDebit,
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
        accounting_role = Role(role_name='accounting staff', description='Accounting')
        sales_role = Role(role_name='sales staff', description='Sales')
        db.session.add_all([accounting_role, sales_role])
        db.session.flush()
        user = User(
            username='expense_user',
            password_hash=generate_password_hash('expense123'),
            role_id=accounting_role.id,
            status='approved',
        )
        sales_user = User(
            username='sales_user',
            password_hash=generate_password_hash('sales123'),
            role_id=sales_role.id,
            status='approved',
        )
        legacy_expense = PurchaseOrder(
            check_voucher_number='CV-OLD',
            check_number='CHK-OLD',
            check_date=date(2026, 6, 1),
            date=date(2026, 6, 2),
            particulars='Legacy stored expense',
            supplier_payee='Legacy Supplier',
            cash_amount=1200,
            net_balance=0,
            status='PAID',
            category='VARIABLE',
        )
        db.session.add_all([user, sales_user, legacy_expense])
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = user.id
                session['username'] = user.username
                session['role'] = 'accounting staff'

            page = client.get('/expenses')
            assert page.status_code == 200
            html = page.get_data(as_text=True)
            assert 'Expense History' in html
            assert 'Create Expense' in html
            assert 'Purchase Order' not in html

            legacy_route = client.get('/purchase-orders', follow_redirects=False)
            assert legacy_route.status_code in {301, 302}
            assert legacy_route.headers['Location'].endswith('/expenses')

            history = client.get('/get-expenses').get_json()
            assert history['success'] is True
            assert len(history['expenses']) == 1
            assert history['expenses'][0]['check_voucher_number'] == 'CV-OLD'

            created = client.post('/create-expense', json={
                'check_voucher_number': 'CV-NEW',
                'check_number': 'CHK-NEW',
                'check_date': '2026-06-03',
                'date': '2026-06-03',
                'or_date': '',
                'ar_cr_or_number': 'OR-NEW',
                'po_number': 'REF-NEW',
                'lf_no': '',
                'particulars': 'New expense',
                'supplier_payee': 'New Supplier',
                'tin_number': '',
                'cash_amount': 800,
                'net_balance': 0,
                'debits': [{'debit_type': 'Various Expenses', 'amount': 800}],
            }).get_json()
            assert created['success'] is True
            assert PurchaseOrder.query.count() == 2
            assert PurchaseOrderDebit.query.count() == 1

            compatibility = client.get('/get-purchase-orders').get_json()
            assert compatibility['success'] is True
            assert len(compatibility['purchase_orders']) == 2
            assert len(compatibility['expenses']) == 2

            created_expense = PurchaseOrder.query.filter_by(check_voucher_number='CV-NEW').first()
            update_response = client.put(f'/expenses/{created_expense.id}', json={
                'check_voucher_number': 'CV-EDITED',
                'check_number': 'CHK-EDITED',
                'check_date': '2026-06-04',
                'date': '2026-06-05',
                'or_date': '',
                'ar_cr_or_number': 'OR-EDITED',
                'po_number': 'REF-EDITED',
                'lf_no': 'LF-EDITED',
                'particulars': 'Edited expense',
                'supplier_payee': 'Edited Supplier',
                'tin_number': 'TIN-EDITED',
                'cash_amount': 900,
                'debits': [{'debit_type': 'Various Expenses', 'amount': 1000}],
            })
            assert update_response.status_code == 200, update_response.get_json()
            db.session.expire_all()
            edited = db.session.get(PurchaseOrder, created_expense.id)
            assert edited.check_voucher_number == 'CV-EDITED'
            assert edited.cash_amount == 900
            assert edited.net_balance == 100
            assert edited.status == 'PENDING'
            assert edited.category == 'VARIABLE'
            assert PurchaseOrderDebit.query.filter_by(purchase_order_id=edited.id).one().amount == 1000

            refreshed = client.get('/get-expenses').get_json()
            edited_payload = next(item for item in refreshed['expenses'] if item['id'] == edited.id)
            assert edited_payload['check_voucher_number'] == 'CV-EDITED'
            assert edited_payload['debits'][0]['amount'] == 1000

            audit = AuditLog.query.filter_by(action='UPDATE', table_name='purchase_orders', record_id=str(edited.id)).first()
            assert audit is not None
            assert audit.username == 'expense_user'
            assert 'CV-NEW' in audit.old_value
            assert 'CV-EDITED' in audit.new_value

            with client.session_transaction() as session:
                session['user_id'] = sales_user.id
                session['username'] = sales_user.username
                session['role'] = 'sales staff'
            denied = client.put(f'/expenses/{edited.id}', json={
                'check_voucher_number': 'CV-DENIED',
                'check_number': 'CHK-DENIED',
                'check_date': '2026-06-04',
                'date': '2026-06-05',
                'particulars': 'Denied expense',
                'supplier_payee': 'Denied Supplier',
                'cash_amount': 1,
                'debits': [{'debit_type': 'Various Expenses', 'amount': 1}],
            })
            assert denied.status_code in {302, 403}
            db.session.expire_all()
            assert db.session.get(PurchaseOrder, edited.id).check_voucher_number == 'CV-EDITED'

    print('Expense module terminology check passed.')


if __name__ == '__main__':
    main()

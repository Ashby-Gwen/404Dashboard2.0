import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cloud_db_guard import require_destructive_cloud_db_tests  # noqa: E402

require_destructive_cloud_db_tests()

from app import (  # noqa: E402
    PurchaseOrder,
    PurchaseOrderDebit,
    Role,
    User,
    app,
    db,
    normalize_upload_row,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def build_upload_row(**overrides):
    row = {
        'PURCHASE_ORDER_ID': '42',
        'CHECK_VOUCHER_NUMBER': 'CV-42',
        'CHECK_NUMBER': 'CHK-42',
        'CHECK_DATE': '05/06/2026',
        'DATE': '04/06/2026',
        'OR_DATE': '',
        'AR_CR_OR_NUMBER': 'OR-42',
        'PO_NUMBER': 'PO-42',
        'LF_NO': 'LF-42',
        'PARTICULARS': 'Internet and supplies',
        'SUPPLIER_PAYEE': 'Example Supplier',
        'TIN_NUMBER': '123-456',
        'CASH': '1,500.00',
        'CASH_AMOUNT': '999,999.00',
        'NET_BALANCE': '123.00',
        'STATUS': 'WRONG',
        'CATEGORY': 'WRONG',
        'GLOBE_SMART_SUN': '1,000.00',
        'VARIOUS_EXPENSES': '500.00',
    }
    row.update(overrides)
    return row


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        admin_role = Role(role_name='admin', description='Test admin')
        db.session.add(admin_role)
        db.session.flush()
        admin_user = User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='ACTIVE',
        )
        db.session.add(admin_user)
        db.session.commit()

        normalized = normalize_upload_row('purchase_order', build_upload_row())
        assert normalized['purchase_order_id'] == 42
        assert normalized['cash_amount'] == 1500
        assert normalized['total_debits'] == 1500
        assert normalized['net_balance'] == 0
        assert normalized['status'] == 'PAID'
        assert normalized['category'] == 'FIXED'
        assert len(normalized['debits']) == 2

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = admin_user.id
                session['username'] = 'admin'
                session['role'] = 'admin'

            create_response = client.post(
                '/admin/upload-commit/purchase_order',
                json={'rows': [normalized]},
            )
            assert create_response.status_code == 200, create_response.get_json()
            assert create_response.get_json()['created'] == 1

            order = db.session.get(PurchaseOrder, 42)
            assert order is not None
            assert order.cash_amount == 1500
            assert order.net_balance == 0
            assert order.status == 'PAID'
            assert order.category == 'FIXED'
            assert PurchaseOrderDebit.query.filter_by(purchase_order_id=42).count() == 2

            updated_row = normalize_upload_row(
                'purchase_order',
                build_upload_row(CASH='800.00', GLOBE_SMART_SUN='', VARIOUS_EXPENSES='500.00'),
            )
            update_response = client.post(
                '/admin/upload-commit/purchase_order',
                json={'rows': [updated_row]},
            )
            assert update_response.status_code == 200, update_response.get_json()
            assert update_response.get_json()['created'] == 0
            assert update_response.get_json()['updated'] == 1

            db.session.expire_all()
            order = db.session.get(PurchaseOrder, 42)
            assert order.cash_amount == 800
            assert order.net_balance == 300
            assert order.status == 'PENDING'
            assert order.category == 'VARIABLE'
            debits = PurchaseOrderDebit.query.filter_by(purchase_order_id=42).all()
            assert len(debits) == 1
            assert debits[0].debit_type == 'Various Expenses'
            assert debits[0].amount == 500

    print('Purchase order upload check passed.')


if __name__ == '__main__':
    main()

import io
import os
import sys
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import event


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

import app as app_module  # noqa: E402
from app import Invoice, Role, User, app, db, init_db  # noqa: E402
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
            assert len(payload['rows']) == 837
            assert payload['grouped_invoice_count'] == 829
            assert len(payload['conflicts']) == 5
            assert payload['rows'][0]['invoice_number'] == 'CR-4640'
            assert any(
                row['invoice_number'].startswith('SVL-') and row['invoice_type'] == 'SERVICE'
                for row in payload['rows']
            )
            assert any(
                row['invoice_number'].startswith('SI-') and row['invoice_type'] == 'SALES'
                for row in payload['rows']
            )

            blocked = web.post(
                '/admin/upload-commit/invoice',
                json={'rows': payload['rows']},
                headers={'Accept': 'application/json'},
            )
            assert blocked.status_code == 409
            assert blocked.is_json
            assert Invoice.query.count() == 0

            conflict_numbers = {
                conflict['invoice_number']
                for conflict in payload['conflicts']
            }
            accepted_rows = [
                row for row in payload['rows']
                if row['invoice_number'] not in conflict_numbers
            ]
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
            assert result['source_rows'] == 827
            assert result['grouped_records'] == 819
            assert result['created'] == 819
            assert result['standalone'] == 819
            assert Invoice.query.count() == 819
            assert select_count < 40, f'Expected bounded SELECT queries, saw {select_count}'
            assert Invoice.query.filter_by(invoice_number='CR-4640').one().cr_number == '4640'
            assert Invoice.query.filter(Invoice.invoice_number.like('SVL-%'), Invoice.invoice_type == 'SERVICE').count() > 0
            assert Invoice.query.filter(Invoice.invoice_number.like('SI-%'), Invoice.invoice_type == 'SALES').count() > 0

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

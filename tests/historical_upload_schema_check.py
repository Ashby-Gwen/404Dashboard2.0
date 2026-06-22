import os
import sys
from io import BytesIO

import pandas as pd


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import AnalyticsData, Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


LEDGER_ROWS = [
    {
        'source_type': 'INVOICE',
        'source_id': 'SI-1234',
        'transaction_date': '2026-06-22',
        'financial_stage': 'PAID',
        'flow_direction': 'INFLOW',
        'flow_status': 'ACTUAL',
        'party_name': 'ASHBY INC',
        'party_role': 'CUSTOMER',
        'amount': 12000,
        'balance_amount': 0,
        'category': 'COLLECTION',
        'status': 'PAID',
        'description': 'Sample',
    },
    {
        'source_type': 'PURCHASE_ORDER',
        'source_id': '1234',
        'transaction_date': '22/06/2026',
        'financial_stage': 'PAID_OUT',
        'flow_direction': 'OUTFLOW',
        'flow_status': 'ACTUAL',
        'party_name': 'Printer Supplier',
        'party_role': 'SUPPLIER',
        'amount': 8500,
        'balance_amount': 0,
        'category': 'EXPENSE_PAYMENT',
        'status': 'PAID',
        'description': 'Printer',
    },
]


def upload_buffer(rows, excel=False):
    buffer = BytesIO()
    frame = pd.DataFrame(rows)
    if excel:
        frame.to_excel(buffer, index=False)
    else:
        buffer.write(frame.to_csv(index=False).encode('utf-8'))
    buffer.seek(0)
    return buffer


def post_upload(client, rows, filename='historical.csv', excel=False):
    return client.post(
        '/api/analytics/overview/upload',
        data={'file': (upload_buffer(rows, excel=excel), filename)},
        content_type='multipart/form-data',
    )


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()
        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='historical_upload_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='ACTIVE',
        )
        db.session.add(manager)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            response = post_upload(client, LEDGER_ROWS)
            assert response.status_code == 200, response.get_json()
            assert response.get_json()['summary']['schema'] == 'historical_ledger'
            assert AnalyticsData.query.filter_by(flow_direction='INFLOW').count() == 1
            assert AnalyticsData.query.filter_by(flow_direction='OUTFLOW').count() == 1
            assert AnalyticsData.query.filter_by(source_id='SI-1234').one().amount == 12000

            duplicate = post_upload(client, LEDGER_ROWS)
            assert duplicate.status_code == 400, duplicate.get_json()
            assert duplicate.get_json()['summary']['duplicate_rows_already_in_database'] == 2

            spaced_headers = {
                f' {key.upper()} ': value for key, value in {
                    **LEDGER_ROWS[0],
                    'source_id': 'SI-SPACED',
                }.items()
            }
            excel_response = post_upload(
                client, [spaced_headers], filename='historical.xlsx', excel=True,
            )
            assert excel_response.status_code == 200, excel_response.get_json()
            assert AnalyticsData.query.filter_by(source_id='SI-SPACED').count() == 1

            invalid_rows = [
                {**LEDGER_ROWS[0], 'source_id': 'BAD-DATE', 'transaction_date': '06/22/2026'},
                {**LEDGER_ROWS[0], 'source_id': 'BAD-FLOW', 'flow_direction': 'SIDEWAYS'},
                {**LEDGER_ROWS[0], 'source_id': 'BAD-AMOUNT', 'amount': 'not money'},
            ]
            invalid = post_upload(client, invalid_rows)
            assert invalid.status_code == 400, invalid.get_json()
            fields = {error['field'] for error in invalid.get_json()['validation_errors']}
            assert {'transaction_date', 'flow_direction', 'amount'} <= fields
            assert AnalyticsData.query.filter(
                AnalyticsData.source_id.in_(['BAD-DATE', 'BAD-FLOW', 'BAD-AMOUNT'])
            ).count() == 0

            missing = post_upload(client, [{
                key: value for key, value in LEDGER_ROWS[0].items() if key != 'description'
            }])
            assert missing.status_code == 400, missing.get_json()
            assert 'DESCRIPTION' in missing.get_json()['summary']['missing_columns']

            empty = post_upload(client, [], filename='empty.xlsx', excel=True)
            assert empty.status_code == 400, empty.get_json()

    print('historical upload schema checks passed')


if __name__ == '__main__':
    main()

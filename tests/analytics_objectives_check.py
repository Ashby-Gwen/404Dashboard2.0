import os
import sys
from io import BytesIO

import pandas as pd


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AnalyticsData,
    Client,
    EvaluationSession,
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


def excel_upload(rows):
    buffer = BytesIO()
    pd.DataFrame(rows).to_excel(buffer, index=False)
    buffer.seek(0)
    return buffer


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='analytics_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='ACTIVE',
        )
        client_record = Client(client_name='TEST POS CLIENT')
        db.session.add_all([manager, client_record])
        db.session.flush()

        for month in range(1, 9):
            order = SalesOrder(
                so_number=f'SO-T-{month:02d}',
                client_id=client_record.id,
                company_name='TEST POS CLIENT',
                order_date=pd.Timestamp(2026, month, 1).date(),
                total_amount=1000 + month * 100,
                status='COMPLETED',
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(SalesOrderItem(
                sales_order_id=order.id,
                particular='POS TERMINAL',
                quantity=month + 1,
                unit_cost=400,
                selling_price=800,
                total=(month + 1) * 800,
            ))
            db.session.add(Invoice(
                invoice_number=f'INV-T-{month:02d}',
                sales_order_id=order.id,
                invoice_type='SALES',
                invoice_date=pd.Timestamp(2026, month, 5).date(),
                total_amount=1000 + month * 100,
                amount_paid=1000 + month * 100,
                balance=0,
                status='PAID',
            ))
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            rows = [
                {'DATE': '01/01/2025', 'COMPANY NAME': 'TEST POS CLIENT', 'STORE NAME': 'Main', 'COST': 500, 'QUANTITY': 2, 'SELLING PRICE': 900, 'PARTICULAR': 'POS TERMINAL'},
                {'DATE': '01/02/2025', 'COMPANY NAME': 'TEST POS CLIENT', 'STORE NAME': 'Main', 'COST': 520, 'QUANTITY': 3, 'SELLING PRICE': 920, 'PARTICULAR': 'POS TERMINAL'},
                {'DATE': '01/03/2025', 'COMPANY NAME': 'TEST POS CLIENT', 'STORE NAME': 'Main', 'COST': 540, 'QUANTITY': 4, 'SELLING PRICE': 940, 'PARTICULAR': 'POS TERMINAL'},
                {'DATE': '01/04/2025', 'COMPANY NAME': 'TEST POS CLIENT', 'STORE NAME': 'Main', 'COST': 560, 'QUANTITY': 50, 'SELLING PRICE': 960, 'PARTICULAR': 'POS TERMINAL'},
            ]
            response = client.post('/api/analytics/overview/upload', data={
                'file': (excel_upload(rows), 'historical.xlsx'),
            }, content_type='multipart/form-data')
            assert response.status_code == 409, response.get_json()
            assert response.get_json()['requires_confirmation'] is True
            assert response.get_json()['eda_summary']['source_format'] == 'excel'

            confirmed = client.post('/api/analytics/overview/upload', data={
                'file': (excel_upload(rows), 'historical.xlsx'),
                'confirm_outliers': 'true',
            }, content_type='multipart/form-data')
            assert confirmed.status_code == 200, confirmed.get_json()
            assert AnalyticsData.query.filter_by(source_format='excel').count() == 4

            clients_payload = client.get('/api/analytics/clients').get_json()
            assert clients_payload['success'] is True
            assert 'client_performance_score' in clients_payload['clients'][0]
            assert clients_payload['clients'][0]['cohort'] in {'Core Partners', 'Growth Clients', 'At-Risk Clients', 'Low Engagement'}

            sales_payload = client.get('/api/analytics/sales?mape_threshold=25').get_json()
            assert sales_payload['success'] is True
            assert sales_payload['forecast_accuracy']['mape_threshold'] == 25
            assert 'descriptive' in sales_payload and 'predictive' in sales_payload and 'prescriptive' in sales_payload

            questions = client.get('/api/evaluation/questions').get_json()
            assert questions['success'] is True
            ratings = [{'question_id': question['id'], 'rating': 5} for question in questions['questions']]
            submitted = client.post('/api/evaluation/responses', json={
                'evaluator_name': 'QA Manager',
                'evaluator_role': 'manager',
                'overall_comment': 'Useful analytics dashboard.',
                'responses': ratings,
            }).get_json()
            assert submitted['success'] is True
            assert EvaluationSession.query.count() == 1

            results = client.get('/api/evaluation/results').get_json()
            assert results['success'] is True
            assert results['overall_mean'] == 5

    print('Analytics objective check passed.')


if __name__ == '__main__':
    main()

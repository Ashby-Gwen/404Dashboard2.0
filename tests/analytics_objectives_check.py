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
    AnalyticsItemCategory,
    Client,
    EvaluationSession,
    Invoice,
    PurchaseOrder,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
)
from analytics_services import build_monthly_revenue_forecast  # noqa: E402
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
            evaluation_enabled=True,
        )
        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='analytics_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='ACTIVE',
        )
        staff_role = Role.query.filter_by(role_name='staff').first()
        staff = User(
            username='analytics_staff',
            password_hash=generate_password_hash('staff123'),
            role_id=staff_role.id,
            status='ACTIVE',
        )
        client_record = Client(client_name='TEST POS CLIENT')
        db.session.add_all([manager, admin, staff, client_record])
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
            db.session.add(SalesOrderItem(
                sales_order_id=order.id,
                particular='Roll out implementation',
                quantity=1,
                unit_cost=100,
                selling_price=200,
                total=200,
            ))
            db.session.add(SalesOrderItem(
                sales_order_id=order.id,
                particular='rollout implementation',
                quantity=2,
                unit_cost=100,
                selling_price=200,
                total=400,
            ))
            db.session.add(SalesOrderItem(
                sales_order_id=order.id,
                particular='TMU220D JOURNAL PAPER SINGLE PLY',
                quantity=100,
                unit_cost=1,
                selling_price=2,
                total=200,
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
        for month in range(1, 5):
            order = SalesOrder(
                so_number=f'SO-OLD-{month:02d}',
                client_id=client_record.id,
                company_name='TEST POS CLIENT',
                order_date=pd.Timestamp(2025, month, 1).date(),
                total_amount=700 + month * 50,
                status='COMPLETED',
            )
            db.session.add(order)
            db.session.flush()
            db.session.add(SalesOrderItem(
                sales_order_id=order.id,
                particular='LEGACY POS TERMINAL',
                quantity=month,
                unit_cost=300,
                selling_price=500,
                total=month * 500,
            ))
            db.session.add(Invoice(
                invoice_number=f'INV-OLD-{month:02d}',
                sales_order_id=order.id,
                invoice_type='SALES',
                invoice_date=pd.Timestamp(2025, month, 5).date(),
                total_amount=700 + month * 50,
                amount_paid=700 + month * 50,
                balance=0,
                status='PAID',
            ))
        db.session.add_all([
            PurchaseOrder(
                check_voucher_number='CV-FIXED',
                check_number='CHK-FIXED',
                check_date=pd.Timestamp(2026, 2, 1).date(),
                date=pd.Timestamp(2026, 2, 1).date(),
                particulars='Office Rent',
                supplier_payee='Mailyn',
                cash_amount=300,
                category='FIXED',
            ),
            PurchaseOrder(
                check_voucher_number='CV-VARIABLE',
                check_number='CHK-VARIABLE',
                check_date=pd.Timestamp(2026, 2, 2).date(),
                date=pd.Timestamp(2026, 2, 2).date(),
                particulars='Delivery Fuel',
                supplier_payee='Fuel Supplier',
                cash_amount=700,
                category='VARIABLE',
            ),
        ])
        db.session.commit()

        with app.test_client() as client:
            unauthenticated_report = client.get('/api/analytics/overview/revenue-report?year=2026')
            assert unauthenticated_report.status_code == 401
            unauthenticated_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026')
            assert unauthenticated_trend.status_code == 401
            with client.session_transaction() as session:
                session['user_id'] = staff.id
                session['username'] = staff.username
                session['role'] = 'staff'
            blocked_report = client.get('/api/analytics/overview/revenue-report?year=2026')
            assert blocked_report.status_code == 403
            blocked_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026')
            assert blocked_trend.status_code == 403

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
            db.session.add_all([
                AnalyticsData(
                    source_type='TEST',
                    source_id='overview-current',
                    transaction_date=pd.Timestamp(2026, 1, 1).date(),
                    financial_stage='PAID',
                    flow_direction='INFLOW',
                    flow_status='ACTUAL',
                    party_name='TEST POS CLIENT',
                    party_role='CUSTOMER',
                    amount=2000,
                    category='COLLECTION',
                ),
                AnalyticsData(
                    source_type='TEST',
                    source_id='overview-expense-current',
                    transaction_date=pd.Timestamp(2026, 1, 1).date(),
                    financial_stage='PAID_OUT',
                    flow_direction='OUTFLOW',
                    flow_status='ACTUAL',
                    party_name='TEST SUPPLIER',
                    party_role='SUPPLIER',
                    amount=750,
                    category='EXPENSE_PAYMENT',
                ),
                AnalyticsData(
                    source_type='TEST',
                    source_id='overview-previous',
                    transaction_date=pd.Timestamp(2025, 1, 1).date(),
                    financial_stage='PAID',
                    flow_direction='INFLOW',
                    flow_status='ACTUAL',
                    party_name='TEST POS CLIENT',
                    party_role='CUSTOMER',
                    amount=1000,
                    category='COLLECTION',
                ),
            ])
            db.session.commit()

            overview_payload = client.get('/api/analytics/overview?year=2026').get_json()
            assert overview_payload['success'] is True
            assert overview_payload['kpis']['comparison_label'] == '2025'
            assert overview_payload['kpis']['revenue_change_percent'] is not None
            assert overview_payload['kpis']['profit'] == (
                overview_payload['kpis']['gross_revenue']
                - overview_payload['kpis']['total_cost_of_goods']
            )
            assert overview_payload['trend_data']['revenue_values'][0] == 2000
            assert overview_payload['trend_data']['expense_values'][0] == 750

            clients_payload = client.get('/api/analytics/clients').get_json()
            assert clients_payload['success'] is True
            assert 'client_performance_score' in clients_payload['clients'][0]
            assert clients_payload['clients'][0]['cohort'] in {'A-Class Clients', 'B-Class Clients', 'C-Class Clients'}
            assert {'master_priority_rank', 'abc_category', 'cumulative_revenue_percent'} <= set(clients_payload['clients'][0])
            assert {'order_count', 'sales_order_value', 'branches_count', 'cohort'} <= set(clients_payload['clients'][0])
            assert {'label', 'order_count', 'sales_order_value', 'branches_count', 'cohort'} <= set(clients_payload['chart_data'][0])
            assert {'master_priority_rank', 'abc_category', 'cumulative_revenue_percent'} <= set(clients_payload['chart_data'][0])

            expenses_payload = client.get('/api/analytics/expenses?year=2026').get_json()
            assert expenses_payload['success'] is True
            assert expenses_payload['total_expenses'] == 1000
            assert expenses_payload['fixed_share_percent'] == 30
            assert expenses_payload['variable_share_percent'] == 70
            assert expenses_payload['ranked_particulars'][0]['label'] == 'Delivery Fuel'
            assert expenses_payload['ranked_suppliers'][0]['label'] == 'Fuel Supplier'
            expense_supplier_labels = [item['label'] for item in expenses_payload['ranked_suppliers']]
            assert 'Manager' in expense_supplier_labels
            assert 'Mailyn' not in expense_supplier_labels
            assert expenses_payload['fixed_items'][0]['supplier_payee'] == 'Manager'

            sales_payload = client.get('/api/analytics/sales?mape_threshold=25').get_json()
            assert sales_payload['success'] is True
            assert sales_payload['forecast_accuracy']['mape_threshold'] == 25
            assert sales_payload['kpis']['total_revenue'] == 41600
            assert 'descriptive' in sales_payload and 'predictive' in sales_payload and 'prescriptive' in sales_payload
            assert sales_payload['descriptive']['monthly_trend'][0]['period_label'] == 'Jan'
            assert 'quantity' in sales_payload['descriptive']['peak_periods']['months'][0]
            assert 'quantity' in sales_payload['descriptive']['peak_periods']['weekdays'][0]
            assert 'average_quantity' in sales_payload['descriptive']['peak_periods']['months'][0]
            assert 'average_quantity' in sales_payload['descriptive']['peak_periods']['weekdays'][0]
            assert 'active_sales_days' in sales_payload['descriptive']['peak_periods']['months'][0]
            assert 'active_sales_days' in sales_payload['descriptive']['peak_periods']['weekdays'][0]
            assert sales_payload['descriptive']['peak_periods']['months'][0]['average_quantity'] >= sales_payload['descriptive']['peak_periods']['months'][-1]['average_quantity']
            assert sales_payload['descriptive']['peak_periods']['weekdays'][0]['average_quantity'] >= sales_payload['descriptive']['peak_periods']['weekdays'][-1]['average_quantity']
            product_distribution = sales_payload['descriptive']['product_distribution']
            rollout_rows = [item for item in product_distribution if item['item'] == 'ROLL OUT IMPLEMENTATION']
            assert len(rollout_rows) == 1
            assert rollout_rows[0]['quantity'] == 24
            assert rollout_rows[0]['revenue'] == 4800
            assert rollout_rows[0]['category'] == 'Uncategorized'
            assert not any(item['item'] == 'Roll out implementation' for item in product_distribution)
            assert not any(item['item'] == 'roll out implementation' for item in product_distribution)
            assert not any(item['item'] == 'rollout implementation' for item in product_distribution)
            assert not any(item['item'] == 'TMU220D JOURNAL PAPER SINGLE PLY' for item in sales_payload['forecast'])
            client_forecasting = sales_payload['client_forecasting']
            assert {
                'category_trends',
                'category_forecasts',
                'top_client_trends',
                'top_client_forecasts',
                'purchase_recommendations',
                'client_forecast_lookup',
                'purchase_recommendation_lookup',
            } <= set(client_forecasting)
            assert len(client_forecasting['top_client_forecasts']) <= 5
            assert len(client_forecasting['top_client_trends']) <= 5
            assert {row['category'] for row in client_forecasting['category_trends']} == {
                'A-Class Clients',
                'B-Class Clients',
                'C-Class Clients',
            }
            assert client_forecasting['top_client_forecasts'][0]['store_name']
            assert 'forecast_points' in client_forecasting['top_client_forecasts'][0]
            assert 'peak_month' in client_forecasting['top_client_forecasts'][0]
            assert client_forecasting['client_forecast_lookup']
            assert client_forecasting['purchase_recommendation_lookup']
            top_purchase_row = client_forecasting['purchase_recommendations'][0]
            assert len(top_purchase_row['recommendations']) <= 3
            assert top_purchase_row['recommendations']
            first_purchase = top_purchase_row['recommendations'][0]
            assert 'confidence_score' in first_purchase
            assert 'accuracy' not in first_purchase
            assert first_purchase['status'] in {'High Confidence', 'Needs Review', 'Insufficient History'}
            specific_sales_payload = client.get('/api/analytics/sales?forecast_filter_mode=year&year=2026').get_json()
            assert specific_sales_payload['success'] is True
            specific_periods = [
                point['period']
                for point in specific_sales_payload['predictive']['monthly_revenue_forecast']['historical_points']
            ]
            assert specific_periods and all(period.startswith('2026-') for period in specific_periods)

            range_sales_payload = client.get('/api/analytics/sales?forecast_filter_mode=range&start_year=2025&end_year=2026').get_json()
            assert range_sales_payload['success'] is True
            range_periods = [
                point['period']
                for point in range_sales_payload['predictive']['monthly_revenue_forecast']['historical_points']
            ]
            assert range_periods == sorted(range_periods)
            assert range_periods[0].startswith('2025-')
            assert range_periods[-1].startswith('2026-')
            assert range_sales_payload['filter']['label'] == '2025-2026'

            all_years_sales_payload = client.get('/api/analytics/sales?forecast_filter_mode=all').get_json()
            assert all_years_sales_payload['success'] is True
            all_year_periods = [
                point['period']
                for point in all_years_sales_payload['predictive']['monthly_revenue_forecast']['historical_points']
            ]
            assert all_years_sales_payload['filter']['label'] == 'All years'
            assert all_year_periods == sorted(all_year_periods)
            assert any(period.startswith('2025-') for period in all_year_periods)
            assert any(period.startswith('2026-') for period in all_year_periods)
            top_store_order = SalesOrder(
                so_number='SO-TOP-CLIENT',
                client_id=client_record.id,
                company_name='TEST POS CLIENT',
                store_name='GIGA STORE',
                order_date=pd.Timestamp(2026, 1, 20).date(),
                total_amount=5000,
                status='COMPLETED',
            )
            db.session.add(top_store_order)
            db.session.flush()
            db.session.add(SalesOrderItem(
                sales_order_id=top_store_order.id,
                particular='SUPPORT PACKAGE',
                quantity=1,
                unit_cost=1000,
                selling_price=5000,
                total=5000,
            ))
            db.session.commit()

            revenue_report = client.get('/api/analytics/overview/revenue-report?year=2026').get_json()
            assert revenue_report['success'] is True
            assert revenue_report['year'] == 2026
            assert revenue_report['columns'] == ['month', 'revenue', 'growth rate', 'top client', 'top client revenue']
            assert len(revenue_report['rows']) == 12
            assert revenue_report['rows'][0] == {
                'month': 'Jan 2026',
                'revenue': 7400.0,
                'growth_rate': 'N/A',
                'top_client': 'GIGA STORE',
                'top_client_revenue': 5000.0,
            }
            assert revenue_report['rows'][1]['month'] == 'Feb 2026'
            assert revenue_report['rows'][1]['revenue'] == 3200.0
            assert revenue_report['rows'][1]['growth_rate'] == '-56.76%'
            assert revenue_report['rows'][1]['top_client'] == 'TEST POS CLIENT'
            assert revenue_report['rows'][1]['top_client_revenue'] == 3200.0

            yearly_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026&mode=yearly').get_json()
            assert yearly_trend['success'] is True
            assert yearly_trend['mode'] == 'yearly'
            assert yearly_trend['selected_year'] == 2026
            assert yearly_trend['previous_year'] == 2025
            assert len(yearly_trend['points']) == 12
            assert yearly_trend['labels'][:3] == ['Jan', 'Feb', 'Mar']
            assert yearly_trend['current_values'][:3] == [7400.0, 3200.0, 4000.0]
            assert yearly_trend['previous_values'][:3] == [500.0, 1000.0, 1500.0]
            assert yearly_trend['points'][0]['quarter'] == 1
            assert yearly_trend['points'][0]['current_params'] == {'year': 2026, 'period': 'month', 'month': 1}
            assert yearly_trend['peak']['label'] == 'Aug'
            assert yearly_trend['forecast_status'] == 'ready'
            assert len(yearly_trend['forecast_points']) == 3
            assert yearly_trend['forecast_points'][0]['period'] == '2026-09'

            quarterly_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026&mode=quarterly&quarter=1').get_json()
            assert quarterly_trend['success'] is True
            assert quarterly_trend['mode'] == 'quarterly'
            assert quarterly_trend['label'] == 'Q1 (Jan-Mar) 2026'
            assert quarterly_trend['labels'] == ['Jan', 'Feb', 'Mar']
            assert quarterly_trend['current_values'] == [7400.0, 3200.0, 4000.0]
            assert quarterly_trend['previous_values'] == [500.0, 1000.0, 1500.0]
            assert quarterly_trend['forecast_status'] == 'ready'
            assert len(quarterly_trend['forecast_points']) == 3
            assert quarterly_trend['forecast_points'][0]['period'] == '2026-04'

            monthly_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026&mode=monthly&month=1').get_json()
            assert monthly_trend['success'] is True
            assert monthly_trend['mode'] == 'monthly'
            assert monthly_trend['label'] == 'Jan 2026'
            assert monthly_trend['labels'][0] == 'W1 (Jan 1-7)'
            assert monthly_trend['current_values'][:3] == [2400.0, 0.0, 5000.0]
            assert monthly_trend['previous_values'][:3] == [500.0, 0.0, 0.0]
            assert monthly_trend['points'][0]['week'] == 1
            assert monthly_trend['forecast_status'] == 'ready'
            assert len(monthly_trend['forecast_points']) == 3
            assert monthly_trend['forecast_points'][0]['label'] == 'Forecast W6'

            invalid_trend = client.get('/api/analytics/overview/trend-drilldown?year=2026&mode=bad&quarter=9&month=99').get_json()
            assert invalid_trend['success'] is True
            assert invalid_trend['mode'] == 'yearly'
            assert invalid_trend['quarter'] == 1
            assert invalid_trend['month'] == 1
            category_payload = client.get('/api/analytics/item-categories').get_json()
            assert category_payload['success'] is True
            assert category_payload['allowed_categories'] == ['System', 'Hardware', 'Services', 'Office Materials']
            rollout_category_rows = [item for item in category_payload['items'] if item['display_item_name'] == 'ROLL OUT IMPLEMENTATION']
            assert len(rollout_category_rows) == 1
            assert rollout_category_rows[0]['category'] == 'Uncategorized'
            save_category_payload = client.post('/api/analytics/item-categories', json={
                'assignments': [{
                    'normalized_item_key': rollout_category_rows[0]['normalized_item_key'],
                    'display_item_name': 'ROLL OUT IMPLEMENTATION',
                    'category': 'System',
                }]
            }).get_json()
            assert save_category_payload['success'] is True
            assert AnalyticsItemCategory.query.filter_by(display_item_name='ROLL OUT IMPLEMENTATION', category='System').first() is not None
            sales_payload = client.get('/api/analytics/sales?mape_threshold=25').get_json()
            product_distribution = sales_payload['descriptive']['product_distribution']
            rollout_rows = [item for item in product_distribution if item['item'] == 'ROLL OUT IMPLEMENTATION']
            assert rollout_rows[0]['category'] == 'System'
            monthly_forecast = sales_payload['predictive']['monthly_revenue_forecast']
            assert monthly_forecast['status'] == 'ready'
            assert monthly_forecast['latest_historical_month'] == '2026-08'
            assert monthly_forecast['forecast_start_month'] == '2026-09'
            assert [item['period'] for item in monthly_forecast['forecast_points'][:3]] == ['2026-09', '2026-10', '2026-11']
            assert len(monthly_forecast['forecast_points']) == 12
            assert monthly_forecast['default_horizon'] == 3
            assert monthly_forecast['horizon_options'] == [3, 6, 12]
            assert monthly_forecast['historical_points'][0]['label'] == 'Jan'
            assert all(item['type'] == 'forecast' for item in monthly_forecast['forecast_points'])
            insufficient_forecast = build_monthly_revenue_forecast(['2026-01', '2026-02'], [1000, 1200])
            assert insufficient_forecast['status'] == 'insufficient_data'
            assert insufficient_forecast['message'] == 'Not enough historical data to generate a reliable 3-month forecast.'

            questions = client.get('/api/evaluation/questions').get_json()
            assert questions['success'] is True
            assert [item['value'] for item in questions['scale']] == [1, 2, 3, 4, 5]
            ratings = [{'question_id': question['id'], 'rating': 4} for question in questions['questions']]
            submitted = client.post('/api/evaluation/responses', json={
                'evaluator_name': 'QA Manager',
                'evaluator_role': 'manager',
                'overall_comment': 'Useful analytics dashboard.',
                'responses': ratings,
            }).get_json()
            assert submitted['success'] is True
            assert EvaluationSession.query.count() == 1

            with client.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            results = client.get('/api/evaluation/results').get_json()
            assert results['success'] is True
            assert results['overall_mean'] == 4

    print('Analytics objective check passed.')


if __name__ == '__main__':
    main()

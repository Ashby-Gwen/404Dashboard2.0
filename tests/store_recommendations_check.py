import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Client, Role, SalesOrder, SalesOrderItem, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, number, store, branch, order_date, quantity, unit_cost, selling_price):
    total = quantity * selling_price
    order = SalesOrder(
        so_number=number,
        client_id=client.id,
        company_name=client.client_name,
        store_name=store,
        store_branch=branch,
        order_date=order_date,
        total_amount=total,
        status='PENDING',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='SHARED ITEM',
        quantity=quantity,
        unit_cost=unit_cost,
        selling_price=selling_price,
        total=total,
    ))


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        manager_role = Role.query.filter_by(role_name='manager').first()
        manager = User(
            username='store_recommendation_manager',
            password_hash=generate_password_hash('manager123'),
            role_id=manager_role.id,
            status='approved',
        )
        low_margin_client = Client(client_name='LOW MARGIN COMPANY')
        high_margin_client = Client(client_name='HIGH MARGIN COMPANY')
        missing_cost_client = Client(client_name='MISSING COST COMPANY')
        db.session.add_all([manager, low_margin_client, high_margin_client, missing_cost_client])
        db.session.flush()

        add_order(low_margin_client, 'SO-LM-1', 'LOW MARGIN STORE', 'NORTH', date(2026, 1, 10), 100, 9, 10)
        add_order(low_margin_client, 'SO-LM-2', 'LOW MARGIN STORE', 'SOUTH', date(2026, 2, 10), 100, 9, 10)
        add_order(low_margin_client, 'SO-LM-3', 'LOW MARGIN STORE', 'MAIN', date(2026, 3, 10), 50, 9, 10)

        add_order(high_margin_client, 'SO-HM-1', 'HIGH MARGIN STORE', 'MAIN', date(2026, 1, 10), 10, 3, 10)
        add_order(high_margin_client, 'SO-HM-2', 'HIGH MARGIN STORE', 'MAIN', date(2026, 2, 10), 10, 3, 10)
        add_order(high_margin_client, 'SO-HM-3', 'HIGH MARGIN STORE', 'MAIN', date(2026, 3, 10), 10, 3, 10)

        add_order(missing_cost_client, 'SO-MC-1', 'MISSING COST STORE', 'HQ', date(2026, 3, 10), 5, 0, 10)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            response = client.get('/api/analytics/sales?year=2026&period=year')
            assert response.status_code == 200, response.get_data(as_text=True)
            payload = response.get_json()
            assert payload['success'] is True

            performance = {item['store_name']: item for item in payload['store_performance']}
            low_margin = performance['LOW MARGIN STORE']
            high_margin = performance['HIGH MARGIN STORE']
            missing_cost = performance['MISSING COST STORE']

            assert low_margin['sales_order_value'] == 2500
            assert low_margin['total_cost'] == 2250
            assert low_margin['gross_profit'] == 250
            assert low_margin['profit_margin'] == 10
            assert low_margin['trend_status'] == 'declining'
            assert low_margin['trend_change_percent'] == -50
            assert low_margin['top_item']['item'] == 'SHARED ITEM'

            assert high_margin['profit_margin'] == 70
            assert high_margin['top_item']['item'] == 'SHARED ITEM'
            assert missing_cost['cost_data_status'] == 'insufficient_cost_data'

            recommendations = {item['store_name']: item for item in payload['store_recommendations']}
            assert 'high_sales_low_margin' in recommendations['LOW MARGIN STORE']['rule_matches']
            assert 'declining_store_trend' in recommendations['LOW MARGIN STORE']['rule_matches']
            assert 'Strong sales but weak margin' in recommendations['LOW MARGIN STORE']['friendly_trigger_labels']
            assert 'Recent sales decline' in recommendations['LOW MARGIN STORE']['friendly_trigger_labels']
            assert recommendations['LOW MARGIN STORE']['why_this_appeared']
            assert recommendations['LOW MARGIN STORE']['what_it_means']
            assert recommendations['LOW MARGIN STORE']['recommended_action']
            assert {item['label'] for item in recommendations['LOW MARGIN STORE']['evidence']} >= {
                'Sales Order Value', 'Profit Margin', 'Order Count', 'Branch Count', 'Top Item'
            }
            assert 'high_profit_store' in recommendations['HIGH MARGIN STORE']['rule_matches']
            assert 'insufficient_cost_data' in recommendations['MISSING COST STORE']['rule_matches']
            assert all(item['type'] == 'store_performance' for item in payload['store_recommendations'])
            assert all(item['type'] not in {'procurement', 'forecast_review'} for item in payload['recommendations'])
            assert len(payload['system_warnings']) == 1
            assert payload['system_warnings'][0]['type'] == 'budget'
            assert payload['rule_thresholds']['client_value_formula'] == {
                'sales_order_value': 50,
                'order_frequency': 30,
                'branch_count': 20,
            }

    print('Per-store recommendations check passed.')


if __name__ == '__main__':
    main()

import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cloud_db_guard import require_destructive_cloud_db_tests  # noqa: E402

require_destructive_cloud_db_tests()

from app import (  # noqa: E402
    Client,
    ClientAlias,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
    normalize_client_match_key,
    refresh_client_financials,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def add_order(client, so_number, total, paid, order_date):
    order = SalesOrder(
        so_number=so_number,
        client_id=client.id,
        company_name=client.client_name,
        official_client_name=client.client_name,
        original_entered_client_name=client.client_name,
        store_name='MAIN STORE',
        store_branch='OLD BRANCH',
        order_date=order_date,
        total_amount=total,
        status='PENDING',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='POS TERMINAL',
        quantity=1,
        unit_cost=total / 2,
        selling_price=total,
        total=total,
    ))
    if paid:
        db.session.add(Invoice(
            invoice_number=f'INV-{so_number}',
            sales_order_id=order.id,
            invoice_type='SALES',
            invoice_date=order_date,
            total_amount=total,
            amount_paid=paid,
            balance=max(total - paid, 0),
            status='PAID' if paid >= total else 'UNPAID',
        ))
    return order


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='client_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='ACTIVE',
        )
        alpha = Client(client_name='ALPHA FOODS INC', status='ACTIVE')
        beta = Client(client_name='BETA RETAIL CORP', status='ACTIVE')
        db.session.add_all([admin, alpha, beta])
        db.session.flush()

        alpha_order = add_order(alpha, 'SO-A-001', 1000, 200, date(2026, 6, 1))
        add_order(beta, 'SO-B-001', 300, 300, date(2026, 6, 2))
        db.session.commit()
        refresh_client_financials()
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            client_list = client.get('/admin/client-list').get_json()
            assert client_list['success'] is True
            assert len(client_list['clients']) == 2
            assert any(row['client_name'] == 'ALPHA FOODS INC' and row['sales_order_count'] == 1 for row in client_list['clients'])

            match_payload = client.get('/admin/client-match?q=Beta%20Retail').get_json()
            assert match_payload['success'] is True
            assert match_payload['candidates'][0]['client_name'] == 'BETA RETAIL CORP'

            update_payload = client.post(
                f'/admin/sales-orders/{alpha_order.id}/client-store-branch',
                json={
                    'client_id': beta.id,
                    'company_name': 'BETTA RETAIL',
                    'store_name': 'UPTOWN STORE',
                    'store_branch': 'NORTH BRANCH',
                    'learn_alias': True,
                },
            ).get_json()
            assert update_payload['success'] is True
            db.session.refresh(alpha_order)
            assert alpha_order.client_id == beta.id
            assert alpha_order.company_name == 'BETA RETAIL CORP'
            assert alpha_order.store_name == 'UPTOWN STORE'
            assert alpha_order.store_branch == 'NORTH BRANCH'
            assert ClientAlias.query.filter_by(normalized_alias=normalize_client_match_key('BETTA RETAIL')).first() is not None

            refreshed = client.get('/admin/client-list').get_json()['clients']
            alpha_row = next(row for row in refreshed if row['client_name'] == 'ALPHA FOODS INC')
            beta_row = next(row for row in refreshed if row['client_name'] == 'BETA RETAIL CORP')
            assert alpha_row['sales_order_count'] == 0
            assert beta_row['sales_order_count'] == 2

            analytics_payload = client.get('/api/analytics/clients?year=2026&period=year').get_json()
            assert analytics_payload['success'] is True
            analytics_by_name = {row['company_name']: row for row in analytics_payload['clients']}
            assert analytics_by_name['ALPHA FOODS INC']['total_revenue'] == 0
            assert analytics_by_name['BETA RETAIL CORP']['total_revenue'] == 1300

    print('Admin client list check passed.')


if __name__ == '__main__':
    main()

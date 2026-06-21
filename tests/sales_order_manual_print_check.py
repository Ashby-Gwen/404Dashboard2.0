import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Role, SalesOrder, SalesOrderItem, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        sales_role = Role.query.filter_by(role_name='sales staff').first()
        if not sales_role:
            sales_role = Role(role_name='sales staff', description='Sales operations')
            db.session.add(sales_role)
            db.session.flush()

        sales_user = User(
            username='manual_sales',
            password_hash=generate_password_hash('pass123'),
            role_id=sales_role.id,
            status='approved',
        )
        db.session.add(sales_user)
        db.session.commit()

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = sales_user.id
                session['username'] = sales_user.username
                session['role'] = 'sales staff'

            create_response = client.post('/create-sales-order', json={
                'company_name': 'Manual Company Inc',
                'store_name': 'Manual Store',
                'store_branch': 'Main Branch',
                'order_date': '2026-06-17',
                'sales_staff': 'Manual Sales',
                'terms_days': 15,
                'notes': 'Manual entry test',
                'items': [
                    {
                        'particular': 'POS Terminal',
                        'quantity': 2,
                        'unit_cost': 100,
                        'selling_price': 350,
                    },
                    {
                        'particular': 'Cash Drawer',
                        'quantity': 1,
                        'unit_cost': 50,
                        'selling_price': 125,
                    },
                ],
            })
            assert create_response.status_code == 200, create_response.get_json()
            payload = create_response.get_json()
            assert payload['success'] is True
            assert payload['print_url'].startswith('/sales-orders/')
            order_id = payload['sales_order']['id']

            order = db.session.get(SalesOrder, order_id)
            assert order is not None
            assert order.company_name == 'MANUAL COMPANY INC'
            assert order.store_name == 'MANUAL STORE'
            assert order.store_branch == 'MAIN BRANCH'
            assert order.total_amount == 825
            assert SalesOrderItem.query.filter_by(sales_order_id=order_id).count() == 2

            history_payload = client.get('/get-sales-orders').get_json()
            assert history_payload['success'] is True
            history_row = next(row for row in history_payload['sales_orders'] if row['id'] == order_id)
            assert history_row['so_number'] == order.so_number
            assert history_row['store_name'] == 'MANUAL STORE'
            assert history_row['total_amount'] == 825

            print_response = client.get(payload['print_url'])
            assert print_response.status_code == 200
            print_html = print_response.get_data(as_text=True)
            assert order.so_number in print_html
            assert 'MANUAL COMPANY INC' in print_html
            assert 'MANUAL STORE' in print_html
            assert 'POS TERMINAL' in print_html
            assert '>Print</button>' in print_html
            assert 'Print / Save PDF' not in print_html

    print('Sales order manual print check passed.')


if __name__ == '__main__':
    main()

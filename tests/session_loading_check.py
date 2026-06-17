import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Client, Invoice, Role, SalesOrder, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role_name):
    role = Role.query.filter_by(role_name=role_name).first()
    if not role:
        role = Role(role_name=role_name, description=f'{role_name} role')
        db.session.add(role)
        db.session.flush()
    user = User(
        username=username,
        email=f'{username}@example.com',
        password_hash=generate_password_hash('pass123'),
        role_id=role.id,
        status='approved',
    )
    db.session.add(user)
    db.session.flush()
    return user


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        accounting = add_user('session_accounting', 'accounting staff')
        sales = add_user('session_sales', 'sales staff')
        client = Client(client_name='SESSION CLIENT', status='ACTIVE', total_revenue=12345, total_paid=2345)
        db.session.add(client)
        db.session.flush()

        sales_order = SalesOrder(
            so_number='SO-SESSION',
            client_id=client.id,
            company_name='SESSION CLIENT',
            store_name='SESSION STORE',
            store_branch='HQ',
            order_date=date(2026, 6, 17),
            sales_staff='Session Sales',
            total_amount=1000,
            status='PENDING',
        )
        db.session.add(sales_order)
        db.session.flush()

        for index in range(3):
            db.session.add(Invoice(
                invoice_number=f'INV-SESSION-{index}',
                sales_order_id=sales_order.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 17),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ))
        db.session.commit()

        with app.test_client() as accounting_client:
            with accounting_client.session_transaction() as session:
                session['user_id'] = accounting.id
                session['username'] = accounting.username
                session['role'] = 'accounting staff'

            first_page = accounting_client.get('/get-invoices', query_string={'page': 1, 'page_size': 2}).get_json()
            assert first_page['success'] is True
            assert first_page['count'] == 3
            assert first_page['page'] == 1
            assert first_page['page_size'] == 2
            assert first_page['total_pages'] == 2
            assert len(first_page['invoices']) == 2

            second_page = accounting_client.get('/get-invoices', query_string={'page': 2, 'page_size': 2}).get_json()
            assert len(second_page['invoices']) == 1

            logout_response = accounting_client.get('/logout')
            assert logout_response.status_code == 200
            assert b'sessionStorage.clear()' in logout_response.data

        with app.test_client() as sales_client:
            with sales_client.session_transaction() as session:
                session['user_id'] = sales.id
                session['username'] = sales.username
                session['role'] = 'sales staff'

            references = sales_client.get('/get-client-references').get_json()
            assert references['success'] is True
            reference = next(item for item in references['clients'] if item['client_name'] == 'SESSION CLIENT')
            assert set(reference) == {'id', 'client_name', 'status', 'aliases'}
            assert 'total_revenue' not in reference
            assert 'total_paid' not in reference

    print('Session loading check passed.')


if __name__ == '__main__':
    main()

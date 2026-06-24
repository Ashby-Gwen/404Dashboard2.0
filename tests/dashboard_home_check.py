import os
import sys
from datetime import date


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    AuditLog,
    Client,
    Invoice,
    PasswordReset,
    PurchaseOrder,
    Role,
    SalesOrder,
    User,
    app,
    db,
    init_db,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role_name, status='ACTIVE'):
    role = Role.query.filter_by(role_name=role_name).first()
    if not role:
        role = Role(role_name=role_name, description=f'{role_name} role')
        db.session.add(role)
        db.session.flush()
    user = User(
        username=username,
        email=f'{username}@example.com',
        password_hash=generate_password_hash('test123'),
        role_id=role.id,
        status=status,
    )
    db.session.add(user)
    db.session.flush()
    return user


def login_as(client, user, role_name):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = role_name


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        staff = add_user('home_staff', 'staff')
        manager = add_user('home_manager', 'manager')
        admin = add_user('home_admin', 'admin')
        pending_user = add_user('needs_approval', 'staff', status='pending')

        client_record = Client(client_name='HOME TEST CLIENT')
        db.session.add(client_record)
        db.session.flush()

        db.session.add_all([
            Invoice(
                invoice_number='HOME-INV-UNPAID',
                invoice_type='SALES',
                invoice_date=date(2026, 1, 3),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='HOME-INV-PAID',
                invoice_type='SALES',
                invoice_date=date(2026, 1, 4),
                total_amount=500,
                amount_paid=500,
                balance=0,
                status='PAID',
            ),
            Invoice(
                invoice_number='HOME-INV-OLD',
                invoice_type='SALES',
                invoice_date=date(2025, 12, 30),
                total_amount=250,
                amount_paid=0,
                balance=250,
                status='UNPAID',
            ),
            SalesOrder(
                so_number='HOME-SO-PENDING',
                client_id=client_record.id,
                company_name=client_record.client_name,
                order_date=date(2026, 1, 5),
                total_amount=700,
                status='PENDING',
            ),
            SalesOrder(
                so_number='HOME-SO-DONE',
                client_id=client_record.id,
                company_name=client_record.client_name,
                order_date=date(2026, 1, 6),
                total_amount=900,
                status='COMPLETED',
            ),
            PurchaseOrder(
                check_voucher_number='CV-HOME-1',
                check_number='CHK-HOME-1',
                check_date=date(2026, 1, 7),
                date=date(2026, 1, 7),
                particulars='Homepage expense pending',
                supplier_payee='Homepage Supplier',
                cash_amount=300,
                net_balance=300,
                status='PENDING',
            ),
            PurchaseOrder(
                check_voucher_number='CV-HOME-2',
                check_number='CHK-HOME-2',
                check_date=date(2026, 1, 8),
                date=date(2026, 1, 8),
                particulars='Homepage expense paid',
                supplier_payee='Homepage Supplier',
                cash_amount=200,
                net_balance=0,
                status='PAID',
            ),
            PasswordReset(user_id=pending_user.id, username=pending_user.username, status='PENDING'),
            AuditLog(username='home_admin', action='LOGIN', table_name='session_records'),
        ])
        db.session.commit()

        with app.test_client() as client:
            login_as(client, staff, 'staff')
            staff_html = client.get('/dashboard?year=2026').get_data(as_text=True)
            assert 'Welcome, home_staff' in staff_html
            assert 'Create Invoice' in staff_html
            assert 'Enter Sales Order' in staff_html
            assert 'Enter Expense' in staff_html
            assert 'id="homeDateFilter"' in staff_html
            assert '<option value="all"' in staff_html
            assert 'Transaction Summary for 2026' in staff_html
            assert 'Invoices' in staff_html
            assert 'UNPAID' in staff_html
            assert 'PHP 1,000.00' in staff_html
            assert 'PHP 1,250.00' not in staff_html
            assert 'Sales Orders' in staff_html
            assert 'COMPLETED' in staff_html
            assert 'Expenses' in staff_html
            assert 'Cashflow Report' not in staff_html
            assert 'Historical Records' not in staff_html

            all_html = client.get('/dashboard?period=all').get_data(as_text=True)
            assert 'Transaction Summary for All dates' in all_html
            assert 'PHP 1,250.00' in all_html

        with app.test_client() as client:
            login_as(client, manager, 'manager')
            manager_html = client.get('/dashboard?year=2026').get_data(as_text=True)
            assert 'Generate Report' in manager_html
            assert 'View Analytics' in manager_html
            assert 'Reporting Workspace' in manager_html
            assert 'Cashflow Report' not in manager_html

        with app.test_client() as client:
            login_as(client, admin, 'admin')
            admin_html = client.get('/dashboard?year=2026').get_data(as_text=True)
            assert 'New User Requests' in admin_html
            assert 'Password Change Requests' in admin_html
            assert 'Recent User Activities' in admin_html
            assert 'Quick Actions' not in admin_html
            assert '/database-interface?tab=requests' in admin_html
            assert '/database-interface?tab=audit' in admin_html
            assert 'Latest Activity' in admin_html
            assert 'Admin Shortcuts' in admin_html
            assert 'Admin Center' in admin_html

    print('Dashboard home check passed.')


if __name__ == '__main__':
    main()

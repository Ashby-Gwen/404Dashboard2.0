import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, inspect


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    Client,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
)
from analytics_services import _sales_performance, build_analytics_payload  # noqa: E402
from defense_migrations import ensure_defense_schema  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


class DbHandle:
    def __init__(self, engine):
        self.engine = engine


def migration_check():
    db_path = Path(ROOT) / '.defense-migration-test.db'
    db_path.unlink(missing_ok=True)
    backup_path = None
    handle = None
    try:
        connection = sqlite3.connect(db_path)
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(80) NOT NULL,
                password_hash VARCHAR(120) NOT NULL,
                role_id INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL
            );
            CREATE TABLE evaluation_sessions (
                id INTEGER PRIMARY KEY,
                evaluator_name VARCHAR(120) NOT NULL,
                created_at DATETIME
            );
            CREATE TABLE invoices (
                id INTEGER PRIMARY KEY,
                amount_paid FLOAT,
                balance FLOAT,
                invoice_date DATE
            );
            """
        )
        connection.commit()
        connection.close()

        handle = DbHandle(create_engine(f'sqlite:///{db_path.as_posix()}'))
        first = ensure_defense_schema(handle)
        second = ensure_defense_schema(handle)
        backup_path = first['backup_path']
        schema = inspect(handle.engine)
        user_columns = {column['name'] for column in schema.get_columns('users')}
        evaluation_columns = {column['name'] for column in schema.get_columns('evaluation_sessions')}
        assert {'profile_photo_data', 'profile_photo_mime'} <= user_columns
        assert 'user_id' in evaluation_columns
        assert first['backup_path'] and Path(first['backup_path']).exists()
        assert second['backup_path'] is None
    finally:
        if handle is not None:
            handle.engine.dispose()
        db_path.unlink(missing_ok=True)
        if backup_path:
            Path(backup_path).unlink(missing_ok=True)


def login_session(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = 'staff'


def create_order(client_record, suffix, total=1000):
    order = SalesOrder(
        so_number=f'SO-DEF-{suffix}',
        client_id=client_record.id,
        company_name=client_record.client_name,
        order_date=date.today(),
        total_amount=total,
        status='PENDING',
    )
    db.session.add(order)
    db.session.flush()
    db.session.add(SalesOrderItem(
        sales_order_id=order.id,
        particular='POS TERMINAL',
        quantity=1,
        unit_cost=600,
        selling_price=total,
        total=total,
    ))
    db.session.commit()
    return order


def invoice_payload(order, number, payment, cr='CR-1'):
    return {
        'sales_order_id': order.id,
        'invoice_number': number,
        'invoice_type': 'SALES',
        'invoice_date': date.today().isoformat(),
        'summary': 'Defense payment test',
        'payment_type': 'DOWNPAYMENT',
        'cr_number': cr,
        'payment_amount': payment,
        'tax_amount_paid': 0,
        'is_2307_checked': False,
    }


def accounting_and_analytics_check():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()
        staff_role = Role.query.filter_by(role_name='staff').first()
        user = User(
            username='defense_staff',
            password_hash=generate_password_hash('pass123'),
            role_id=staff_role.id,
            status='approved',
        )
        client_record = Client(client_name='DEFENSE CLIENT')
        db.session.add_all([user, client_record])
        db.session.commit()

        order = create_order(client_record, 'PARTIAL')
        zero_order = create_order(client_record, 'ZERO', 500)

        with app.test_client() as web:
            login_session(web, user)

            zero = web.post('/create-invoice', json=invoice_payload(
                zero_order, 'SI-DEF-ZERO', 0, cr=''
            ))
            assert zero.status_code == 200, zero.get_json()
            assert zero.get_json()['invoice_status'] == 'UNPAID'
            assert zero.get_json()['balance'] == 500

            partial = web.post('/create-invoice', json=invoice_payload(
                order, 'SI-DEF-1', 300
            ))
            assert partial.status_code == 200, partial.get_json()
            assert partial.get_json()['invoice_status'] == 'PARTIAL'
            assert partial.get_json()['balance'] == 700

            duplicate = web.post('/create-invoice', json=invoice_payload(
                order, 'SI-DEF-1', 100
            ))
            assert duplicate.status_code == 409

            full = web.post('/create-invoice', json=invoice_payload(
                order, 'SI-DEF-2', 700, cr='CR-2'
            ))
            assert full.status_code == 200, full.get_json()
            assert full.get_json()['invoice_status'] == 'PAID'
            assert full.get_json()['balance'] == 0

            second_invoice = Invoice.query.filter_by(invoice_number='SI-DEF-2').one()
            edited = web.post(f'/update-invoice-payment/{second_invoice.id}', json={
                'payment_type': 'DOWNPAYMENT',
                'cr_number': 'CR-2',
                'payment_amount': 600,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert edited.status_code == 200, edited.get_json()
            assert edited.get_json()['invoice_status'] == 'PARTIAL'
            assert edited.get_json()['balance'] == 100

            overpayment = web.post(f'/update-invoice-payment/{second_invoice.id}', json={
                'payment_type': 'FULL',
                'cr_number': 'CR-2',
                'payment_amount': 800,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert overpayment.status_code == 400
            db.session.expire_all()
            assert db.session.get(Invoice, second_invoice.id).amount_paid == 600

        standalone = Invoice(
            invoice_number='ADMIN-DEF-1',
            sales_order_id=None,
            invoice_type='ADMIN UPLOAD',
            invoice_date=date.today(),
            total_amount=400,
            amount_paid=150,
            balance=250,
            status='PARTIAL',
            uploaded_client_name='DEFENSE CLIENT',
        )
        db.session.add(standalone)
        db.session.commit()

        payload = build_analytics_payload(db, {
            'Client': Client,
            'ClientAlias': __import__('app').ClientAlias,
            'Invoice': Invoice,
            'PurchaseOrder': __import__('app').PurchaseOrder,
            'SalesOrder': SalesOrder,
            'SalesOrderItem': SalesOrderItem,
        })
        assert payload['summary']['paid_revenue'] == 1050
        assert payload['summary']['accounts_receivable'] == 850
        defense_balance = next(
            item['balance'] for item in payload['client_balances']
            if item['client_name'] == 'DEFENSE CLIENT'
        )
        assert defense_balance == 850

        old_entry_order = SalesOrder(
            so_number='SO-BUSINESS-DATE',
            client_id=client_record.id,
            company_name=client_record.client_name,
            order_date=date.today(),
            total_amount=10,
            created_at=datetime(2020, 1, 1),
        )
        db.session.add(old_entry_order)
        db.session.commit()
        current_period = _sales_performance(SalesOrder, Invoice)[-1]
        assert current_period['sales_count'] >= 3


def production_guard_source_check():
    app_source = Path(ROOT, 'app.py').read_text(encoding='utf-8')
    admin_template = Path(ROOT, 'templates', 'admin.html').read_text(encoding='utf-8')
    analytics_template = Path(ROOT, 'templates', 'analytics.html').read_text(encoding='utf-8')
    dashboard_template = Path(ROOT, 'templates', 'dashboard.html').read_text(encoding='utf-8')
    analytics_services_source = Path(ROOT, 'analytics_services.py').read_text(encoding='utf-8')
    assert "dry_run = True if IS_PRODUCTION" in app_source
    assert "if IS_PRODUCTION:" in app_source
    assert "app.run(debug=os.environ.get('FLASK_DEBUG'" in app_source
    assert "Production read-only mode" in admin_template
    assert "previous_year_comparison_filter" in app_source
    assert "filters['start_date']" in app_source
    assert "ranked_particulars" in analytics_services_source
    assert 'data-section="expenses"' in analytics_template
    assert "x: Number(c.order_count || 0)" in analytics_template
    assert "y: Number(c.sales_order_value || c.total_revenue || 0)" in analytics_template
    assert "Net Cash Flow" in dashboard_template


def main():
    migration_check()
    accounting_and_analytics_check()
    production_guard_source_check()
    print('Defense readiness check passed.')


if __name__ == '__main__':
    main()

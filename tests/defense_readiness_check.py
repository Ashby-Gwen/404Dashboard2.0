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
    ClientAlias,
    CollectionReceipt,
    Invoice,
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    db,
    init_db,
    revenue_report_rows,
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
        collection_columns = {column['name'] for column in schema.get_columns('collection_receipts')}
        assert {'profile_photo_data', 'profile_photo_mime', 'disabled_reason'} <= user_columns
        assert 'user_id' in evaluation_columns
        assert {'invoice_id', 'receipt_date', 'normalized_cr_number', 'collected_total'} <= collection_columns
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
        'receipt_date': date.today().isoformat(),
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
        db.session.flush()
        db.session.add(ClientAlias(
            alias_name='DEFENSE ALIAS',
            normalized_alias='DEFENSE ALIAS',
            client_id=client_record.id,
            status='ACTIVE',
        ))
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

            zero_invoice = Invoice.query.filter_by(invoice_number='SI-DEF-ZERO').one()
            original_details = {
                'payment_type': zero_invoice.payment_type,
                'cr_number': zero_invoice.cr_number,
                'payment_amount': zero_invoice.payment_amount,
            }
            missing_receipt_date = web.post(
                f'/invoices/{zero_invoice.id}/collection-receipts',
                json={
                    'payment_type': 'DOWNPAYMENT',
                    'cr_number': 'CR-NO-DATE',
                    'payment_amount': 100,
                },
            )
            assert missing_receipt_date.status_code == 400
            first_receipt = web.post(f'/invoices/{zero_invoice.id}/collection-receipts', json={
                'receipt_date': date.today().isoformat(),
                'payment_type': 'DOWNPAYMENT',
                'cr_number': 'CR-ZERO-1',
                'payment_amount': 200,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert first_receipt.status_code == 200, first_receipt.get_json()
            assert first_receipt.get_json()['invoice_status'] == 'PARTIAL'
            assert first_receipt.get_json()['balance'] == 300

            duplicate_receipt = web.post(f'/update-invoice-payment/{zero_invoice.id}', json={
                'receipt_date': date.today().isoformat(),
                'payment_type': 'DOWNPAYMENT',
                'cr_number': 'cr-zero-1',
                'payment_amount': 100,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert duplicate_receipt.status_code == 400

            wrong_full = web.post(f'/invoices/{zero_invoice.id}/collection-receipts', json={
                'receipt_date': date.today().isoformat(),
                'payment_type': 'FULL',
                'cr_number': 'CR-ZERO-2',
                'payment_amount': 250,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert wrong_full.status_code == 400

            final_receipt = web.post(f'/invoices/{zero_invoice.id}/collection-receipts', json={
                'receipt_date': date.today().isoformat(),
                'payment_type': 'FULL',
                'cr_number': 'CR-ZERO-2',
                'payment_amount': 300,
                'tax_amount_paid': 0,
                'is_2307_checked': False,
            })
            assert final_receipt.status_code == 200, final_receipt.get_json()
            assert final_receipt.get_json()['invoice_status'] == 'PAID'
            assert final_receipt.get_json()['balance'] == 0
            db.session.expire_all()
            refreshed_zero_invoice = db.session.get(Invoice, zero_invoice.id)
            assert refreshed_zero_invoice.amount_paid == 500
            assert {
                'payment_type': refreshed_zero_invoice.payment_type,
                'cr_number': refreshed_zero_invoice.cr_number,
                'payment_amount': refreshed_zero_invoice.payment_amount,
            } == original_details
            assert CollectionReceipt.query.filter_by(invoice_id=zero_invoice.id).count() == 2

            receipt_history = web.get(f'/invoices/{zero_invoice.id}/collection-receipts').get_json()
            assert receipt_history['success'] is True
            assert [item['cr_number'] for item in receipt_history['collection_receipts']] == [
                'CR-ZERO-1', 'CR-ZERO-2'
            ]
            report_receipts = [
                row for row in revenue_report_rows()
                if row['invoice_number'] == 'SI-DEF-ZERO'
            ]
            assert [row['cr_number'] for row in report_receipts] == ['CR-ZERO-1', 'CR-ZERO-2']
            assert [row['amount_paid'] for row in report_receipts] == [200, 300]
            assert all(row['invoice_date'] == date.today().isoformat() for row in report_receipts)
            combined_search = web.get(
                '/get-invoices?general_search=SI-DEF-ZERO'
                '&cr_search=zero-2&client_search=DEFENSE'
            ).get_json()
            assert combined_search['success'] is True
            assert [item['invoice_number'] for item in combined_search['invoices']] == ['SI-DEF-ZERO']
            assert combined_search['invoices'][0]['receipt_count'] == 2
            alias_search = web.get('/get-invoices?client_search=DEFENSE%20ALIAS').get_json()
            assert alias_search['success'] is True
            assert any(item['invoice_number'] == 'SI-DEF-ZERO' for item in alias_search['invoices'])

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
        assert payload['summary']['paid_revenue'] == 1650
        assert payload['summary']['accounts_receivable'] == 250
        defense_balance = next(
            item['balance'] for item in payload['client_balances']
            if item['client_name'] == 'DEFENSE CLIENT'
        )
        assert defense_balance == 250

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
    assert "Quick Actions" in dashboard_template
    assert "Admin Command Center" in dashboard_template
    assert "Net Cash Flow" not in dashboard_template


def main():
    migration_check()
    accounting_and_analytics_check()
    production_guard_source_check()
    print('Defense readiness check passed.')


if __name__ == '__main__':
    main()

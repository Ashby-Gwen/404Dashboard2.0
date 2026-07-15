import os
import sys
from datetime import UTC, date, datetime, timedelta


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import AuditLog, Client, DEVICE_COOKIE_NAME, Invoice, Role, SalesOrder, SessionRecord, User, app, db, humanize_activity_action, init_db  # noqa: E402
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

        first_device = app.test_client()
        second_device = app.test_client()
        first_login = first_device.post('/login', data={'username': accounting.username, 'password': 'pass123'})
        assert first_login.status_code == 302
        assert DEVICE_COOKIE_NAME in first_login.headers.get('Set-Cookie', '')

        second_login = second_device.post(
            '/login',
            data={'username': accounting.username, 'password': 'pass123'},
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126.0'},
        )
        assert second_login.status_code == 302

        session_records = SessionRecord.query.filter_by(user_id=accounting.id).order_by(SessionRecord.id.asc()).all()
        assert len(session_records) == 2
        old_session, new_session = session_records
        assert old_session.device_id
        assert new_session.device_id
        assert old_session.device_id != new_session.device_id
        assert old_session.status == 'FORCED_LOGOUT'
        assert old_session.logout_at is not None
        assert new_session.status == 'ACTIVE'
        assert new_session.device_label == 'Chrome on Windows'
        assert new_session.concurrent_note == 'Multiple active sessions: previous session signed out automatically.'
        active_sessions = SessionRecord.query.filter_by(user_id=accounting.id, status='ACTIVE').order_by(SessionRecord.id.asc()).all()
        assert active_sessions == [new_session]
        concurrent_audit = AuditLog.query.filter_by(action='CONCURRENT_DEVICE_LOGIN', record_id=str(new_session.id)).first()
        assert concurrent_audit is not None
        assert humanize_activity_action(concurrent_audit.action) == 'Multiple Active Sessions'

        old_browser_response = first_device.get('/dashboard')
        assert old_browser_response.status_code == 302
        assert '/login' in old_browser_response.headers['Location']
        with first_device.session_transaction() as old_browser_session:
            assert 'user_id' not in old_browser_session

        with second_device.session_transaction() as active_session:
            active_session['last_activity_at'] = datetime.now(UTC).isoformat()
        active_response = second_device.get('/get-invoices', query_string={'page': 1, 'page_size': 2})
        assert active_response.status_code == 200
        with second_device.session_transaction() as near_idle_session:
            near_idle_session['last_activity_at'] = (datetime.now(UTC) - timedelta(minutes=4, seconds=30)).isoformat()
        activity_response = second_device.post(
            '/api/session/activity',
            headers={'Accept': 'application/json'},
        )
        assert activity_response.status_code == 200
        assert activity_response.get_json()['success'] is True
        refreshed_response = second_device.get('/get-invoices', query_string={'page': 1, 'page_size': 2})
        assert refreshed_response.status_code == 200

        with second_device.session_transaction() as stale_session:
            stale_session['last_activity_at'] = (datetime.now(UTC) - timedelta(minutes=6)).isoformat()
        timeout_response = second_device.get(
            '/get-invoices',
            query_string={'page': 1, 'page_size': 2},
            headers={'Accept': 'application/json'},
        )
        assert timeout_response.status_code == 401
        assert 'timed out' in timeout_response.get_json()['error']
        db.session.refresh(new_session)
        assert new_session.status == 'TIMED_OUT'

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

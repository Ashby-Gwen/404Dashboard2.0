import os
import sys
from io import BytesIO


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Role, SystemSetting, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role_name):
    role = Role.query.filter_by(role_name=role_name).first()
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


def login(client, username):
    response = client.post('/login', data={'username': username, 'password': 'pass123'})
    assert response.status_code == 302


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        sales_role = Role.query.filter_by(role_name='sales staff').first()
        if not sales_role:
            db.session.add(Role(role_name='sales staff', description='Sales operations'))
        accounting_role = Role.query.filter_by(role_name='accounting staff').first()
        if not accounting_role:
            db.session.add(Role(role_name='accounting staff', description='Accounting operations'))
        db.session.flush()

        admin = add_user('multi_admin', 'admin')
        sales = add_user('multi_sales', 'sales staff')
        accounting = add_user('multi_accounting', 'accounting staff')
        db.session.commit()

        admin_client = app.test_client()
        sales_client = app.test_client()
        accounting_client = app.test_client()

        login(admin_client, admin.username)
        login(sales_client, sales.username)
        login(accounting_client, accounting.username)

        with sales_client.session_transaction() as session:
            assert session['username'] == sales.username
            assert session['role'] == 'sales staff'
        with accounting_client.session_transaction() as session:
            assert session['username'] == accounting.username
            assert session['role'] == 'accounting staff'

        assert sales_client.get('/sales-order').status_code == 200
        assert sales_client.get('/invoices').status_code == 302
        assert accounting_client.get('/invoices').status_code == 200
        assert accounting_client.get('/sales-order').status_code == 302

        theme_response = admin_client.post('/admin/theme', json={'settings': {'bg': '#111827', 'orange': '#F59E0B'}})
        assert theme_response.status_code == 200, theme_response.get_json()
        assert SystemSetting.query.filter_by(key='theme_settings').first() is not None
        assert b'--bg: #111827' in admin_client.get('/theme-overrides.css').data

        tiny_png = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
            b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde'
            b'\x00\x00\x00\x0cIDATx\x9cc```\x00\x00\x00\x04'
            b'\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        profile_response = sales_client.post('/profile', data={
            'username': sales.username,
            'email': sales.email,
            'profile_photo': (BytesIO(tiny_png), 'avatar.png'),
        }, content_type='multipart/form-data')
        assert profile_response.status_code == 302
        db.session.refresh(sales)
        assert sales.profile_photo is None
        assert sales.profile_photo_mime == 'image/png'
        assert sales.profile_photo_data

    print('Render multi-user check passed.')


if __name__ == '__main__':
    main()

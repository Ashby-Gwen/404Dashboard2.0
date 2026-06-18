import os
import sys
from html.parser import HTMLParser


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


class AccessibilityParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.labels_for = set()
        self.controls = {}
        self.buttons_without_name = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        element_id = values.get('id')
        if element_id:
            self.ids.append(element_id)
        if tag == 'label' and values.get('for'):
            self.labels_for.add(values['for'])
        if tag in {'input', 'select', 'textarea'} and element_id:
            self.controls[element_id] = values
        if tag == 'button':
            has_name = bool(values.get('aria-label') or values.get('title'))
            if values.get('class', '').find('btn-remove-debit') >= 0 and not has_name:
                self.buttons_without_name.append(values)


def assert_unique_ids(html):
    parser = AccessibilityParser()
    parser.feed(html)
    duplicates = {item for item in parser.ids if parser.ids.count(item) > 1}
    assert not duplicates, f'Duplicate HTML ids: {sorted(duplicates)}'
    return parser


def login(client, user, role_name):
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

        admin_role = Role.query.filter_by(role_name='admin').first()
        accounting_role = Role.query.filter_by(role_name='accounting staff').first()
        if not accounting_role:
            accounting_role = Role(role_name='accounting staff', description='Accounting operations')
            db.session.add(accounting_role)
            db.session.flush()
        admin = User(
            username='a11y_admin',
            password_hash=generate_password_hash('pass123'),
            role_id=admin_role.id,
            status='approved',
        )
        accounting = User(
            username='a11y_accounting',
            password_hash=generate_password_hash('pass123'),
            role_id=accounting_role.id,
            status='approved',
        )
        db.session.add_all([admin, accounting])
        db.session.commit()

        with app.test_client() as client:
            login(client, admin, 'admin')
            admin_html = client.get('/database-interface').get_data(as_text=True)
            admin_parser = assert_unique_ids(admin_html)
            assert 'href="#adminMain"' in admin_html
            assert 'id="adminTabs"' in admin_html
            assert 'aria-label="Admin sections"' in admin_html
            assert 'Advanced technical tools' in admin_html
            assert 'Show technical columns' in admin_html
            assert 'role="tabpanel"' in admin_html
            assert {'gridTable', 'gridSearch', 'gridStatus', 'gridPageSize'} <= set(admin_parser.controls)

            login(client, accounting, 'accounting staff')
            expense_html = client.get('/expenses').get_data(as_text=True)
            expense_parser = assert_unique_ids(expense_html)
            assert 'href="#expenseMain"' in expense_html
            assert 'role="dialog"' in expense_html
            assert 'aria-modal="true"' in expense_html
            assert 'aria-labelledby="editExpenseTitle"' in expense_html
            assert 'aria-label="Expense history"' in expense_html
            assert not expense_parser.buttons_without_name

            labeled_expense_controls = {
                'checkVoucherNumber', 'checkNumber', 'checkDate', 'poDate',
                'orDate', 'arCrOrNumber', 'poNumber', 'lfNo', 'particulars',
                'supplierPayee', 'tinNumber', 'cashAmount',
                'editCheckVoucherNumber', 'editCheckNumber', 'editCheckDate',
                'editPoDate', 'editOrDate', 'editArCrOrNumber', 'editPoNumber',
                'editLfNo', 'editParticulars', 'editSupplierPayee',
                'editTinNumber', 'editCashAmount',
            }
            missing_labels = labeled_expense_controls - expense_parser.labels_for
            assert not missing_labels, f'Expense controls missing labels: {sorted(missing_labels)}'
            assert 'Reference/PO Number' not in expense_html

    admin_source = open(os.path.join(ROOT, 'templates', 'admin.html'), encoding='utf-8').read()
    expense_source = open(os.path.join(ROOT, 'templates', 'purchase_orders.html'), encoding='utf-8').read()
    styles = open(os.path.join(ROOT, 'static', 'css', 'styles.css'), encoding='utf-8').read()

    for key in ('ArrowRight', 'ArrowLeft', 'Home', 'End'):
        assert key in admin_source
    assert "event.key === 'Escape'" in expense_source
    assert "event.key !== 'Tab'" in expense_source
    assert 'expenseModalReturnFocus' in expense_source
    assert ':focus-visible' in styles
    assert '.skip-link:focus' in styles

    print('Accessibility and keyboard check passed.')


if __name__ == '__main__':
    main()

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

            analytics_html = client.get('/analytics').get_data(as_text=True)
            analytics_parser = assert_unique_ids(analytics_html)
            assert 'id="analyticsToolsDrawer"' in analytics_html
            assert 'aria-labelledby="analyticsToolsTitle"' in analytics_html
            assert 'aria-controls="analyticsToolsDrawer"' in analytics_html
            assert 'aria-haspopup="dialog"' in analytics_html
            assert 'aria-label="Close Analytics Tools"' in analytics_html
            assert 'aria-label="Analytics date filter and actions"' in analytics_html
            assert {'analyticsYear', 'analyticsPeriod'} <= set(analytics_parser.controls)

            invoice_html = client.get('/invoices').get_data(as_text=True)
            invoice_parser = assert_unique_ids(invoice_html)
            assert 'aria-label="Invoice search filters"' in invoice_html
            assert {
                'invoiceGeneralSearch', 'invoiceCrSearch', 'invoiceClientSearch',
                'receiptDate', 'editReceiptDate',
            } <= set(invoice_parser.controls)
            assert {
                'invoiceGeneralSearch', 'invoiceCrSearch', 'invoiceClientSearch',
                'receiptDate', 'editReceiptDate',
            } <= invoice_parser.labels_for
            assert 'All Invoices' not in invoice_html
            assert 'Sales Invoices' not in invoice_html
            assert 'Service Invoices' not in invoice_html
            assert 'View / Add Receipts' in invoice_html
            assert 'Print Preview' in analytics_html
            assert 'Review the active' in analytics_html
            assert 'analytics tab before printing.' in analytics_html
            assert 'data-section="expenses"' in analytics_html
            assert 'aria-label="Monthly revenue trend chart"' in analytics_html
            assert 'aria-label="Client opportunity relationship chart"' in analytics_html
            assert 'aria-label="Fixed and variable expense composition chart"' in analytics_html

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
    analytics_source = open(os.path.join(ROOT, 'templates', 'analytics.html'), encoding='utf-8').read()
    expense_source = open(os.path.join(ROOT, 'templates', 'purchase_orders.html'), encoding='utf-8').read()
    styles = open(os.path.join(ROOT, 'static', 'css', 'styles.css'), encoding='utf-8').read()

    for key in ('ArrowRight', 'ArrowLeft', 'Home', 'End'):
        assert key in admin_source
    assert "event.key === 'Escape'" in expense_source
    assert "event.key !== 'Tab'" in expense_source
    assert 'expenseModalReturnFocus' in expense_source
    assert "event.key === 'Escape'" in analytics_source
    assert "event.key !== 'Tab'" in analytics_source
    assert 'analyticsOverlayReturnFocus' in analytics_source
    assert 'recommendationModalReturnFocus' in analytics_source
    assert "indexAxis: 'y'" in analytics_source
    assert 'loadOverviewComparison' in analytics_source
    dashboard_source = open(os.path.join(ROOT, 'templates', 'dashboard.html'), encoding='utf-8').read()
    assert 'Quick Actions' in dashboard_source
    assert 'Admin Command Center' in dashboard_source
    assert 'Net Cash Flow' not in dashboard_source
    assert ':focus-visible' in styles
    assert '.skip-link:focus' in styles

    print('Accessibility and keyboard check passed.')


if __name__ == '__main__':
    main()

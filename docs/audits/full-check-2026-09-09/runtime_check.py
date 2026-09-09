"""Read-only business database audit; all application mutations use memory SQLite."""
import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import date

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ.pop('RENDER', None)
os.environ['FLASK_ENV'] = 'development'
os.environ['SYLUXENT_ALLOW_INSECURE_DEMO_PASSWORDS'] = 'false'
from app import app, db, User, Role, Invoice, CollectionReceipt
from werkzeug.security import generate_password_hash
from sqlalchemy import text

OUT = Path(__file__).parent
app.config.update(TESTING=False, PROPAGATE_EXCEPTIONS=False)
result = {}
with app.app_context():
    result['tables'] = sorted(db.metadata.tables)
    result['route_count'] = len(list(app.url_map.iter_rules()))
    result['seeded_roles'] = [r.role_name for r in Role.query.all()]
    role_names = ['admin', 'manager', 'staff', 'sales staff', 'accounting staff', 'IT Evaluator']
    users = {}
    for index, name in enumerate(role_names):
        role = Role.query.filter_by(role_name=name).first()
        if not role:
            role = Role(role_name=name)
            db.session.add(role)
            db.session.flush()
        user = User(username=f'audit_{index}', password_hash=generate_password_hash('Audit!2026'), role_id=role.id, status='approved')
        db.session.add(user)
        db.session.flush()
        users[name] = user.id
    db.session.commit()

    def client_for(role):
        client = app.test_client()
        if role != 'anonymous':
            user = db.session.get(User, users[role])
            with client.session_transaction() as session:
                session.update(user_id=user.id, username=user.username, role=role.lower())
        return client

    routes = [r.rule for r in app.url_map.iter_rules() if 'GET' in r.methods and not r.arguments and r.rule not in ['/logout', '/session-timeout']]
    probes = []
    for role in ['anonymous'] + role_names:
        for route in routes:
            response = client_for(role).get(route)
            probes.append({'role': role, 'route': route, 'status': response.status_code})
    result['route_probes'] = probes
    malformed = []
    response = app.test_client().post('/login', data={'username': 'audit_0'})
    malformed.append({'route': '/login', 'input': 'existing user, missing password', 'status': response.status_code})
    for route in ['/create-sales-order', '/create-invoice', '/create-expense', '/create-client', '/admin/transaction-reset']:
        for payload in [{}, ['unexpected'], 'unexpected']:
            response = client_for('admin').post(route, json=payload)
            malformed.append({'route': route, 'input': payload, 'status': response.status_code, 'response': response.get_json(silent=True)})
    result['malformed_requests'] = malformed
    invoice = Invoice(invoice_number='AUDIT-RESET', invoice_type='SALES', invoice_date=date.today(), total_amount=100, amount_paid=20, balance=80)
    db.session.add(invoice)
    db.session.flush()
    db.session.add(CollectionReceipt(invoice_id=invoice.id, receipt_date=date.today(), cr_number='AUDIT-CR', normalized_cr_number='AUDIT-CR', payment_type='DOWNPAYMENT', payment_amount=20, collected_total=20))
    db.session.commit()
    response = client_for('admin').post('/admin/transaction-reset', json={'areas': ['invoices'], 'confirmation': 'RESET TRANSACTIONS'})
    result['reset_reproduction'] = {'status': response.status_code, 'invoices_remaining': Invoice.query.count(), 'receipts_remaining': CollectionReceipt.query.count(), 'foreign_key_violations': [list(r) for r in db.session.execute(text('PRAGMA foreign_key_check'))]}
    result['template_errors'] = []
    for template in app.jinja_env.list_templates():
        try:
            app.jinja_env.get_template(template)
        except Exception as exc:
            result['template_errors'].append({'template': template, 'error': str(exc)})

result['local_databases'] = []
for path in [ROOT / 'database.db', ROOT / 'instance' / 'database.db']:
    if not path.exists():
        continue
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    checks = {'path': str(path), 'quick_check': connection.execute('PRAGMA quick_check').fetchone()[0], 'foreign_key_violation_count': len(connection.execute('PRAGMA foreign_key_check').fetchall()), 'table_count': len(tables), 'missing_model_tables': sorted(set(result['tables']) - set(tables)), 'counts': {}}
    checks['missing_model_columns'] = {}
    checks['extra_tables'] = sorted(set(tables) - set(result['tables']))
    for name, model in db.metadata.tables.items():
        if name in tables:
            actual = {r[1] for r in connection.execute('PRAGMA table_info("' + name + '")')}
            missing = sorted(set(model.columns.keys()) - actual)
            if missing:
                checks['missing_model_columns'][name] = missing
    for table in ['sales_orders', 'invoices', 'collection_receipts', 'purchase_orders', 'analytics_data']:
        if table in tables:
            checks['counts'][table] = connection.execute('SELECT COUNT(*) FROM "' + table + '"').fetchone()[0]
    result['local_databases'].append(checks)
    connection.close()
(OUT / 'runtime-results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({key: value for key, value in result.items() if key != 'route_probes'}, indent=2))
print('GET probes:', len(probes), 'server errors:', sum(p['status'] >= 500 for p in probes))

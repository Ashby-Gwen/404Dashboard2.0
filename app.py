# store name ang focus hindi company name.
try:
    from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response, has_request_context  # type: ignore[import]
    # from flask_login import login_required
    from flask_sqlalchemy import SQLAlchemy  # type: ignore[import]
    from werkzeug.security import generate_password_hash, check_password_hash  # type: ignore[import]
    from werkzeug.utils import secure_filename  # type: ignore[import]
    from collections import defaultdict
    from sqlalchemy import func, extract, asc, desc, or_, and_, case, inspect as sa_inspect # type: ignore[import]
    from sqlalchemy.orm import selectinload, synonym
    from dotenv import load_dotenv  # type: ignore[import]
    from decimal import Decimal, InvalidOperation     # <--- ADD THIS LINE HERE
    import pandas as pd  # type: ignore[import]
    from openpyxl import load_workbook  # type: ignore[import]
    from openpyxl.utils import get_column_letter  # type: ignore[import]
    import Levenshtein  # type: ignore[import]
    import csv  # <--- ADD THIS LINE TO YOUR IMPORTS
    import base64
    try:
        from rapidfuzz import fuzz as rapidfuzz_fuzz  # type: ignore[import]
    except ImportError:
        rapidfuzz_fuzz = None
except ImportError as e:
    raise ImportError(
        "Missing required package. Install dependencies with `pip install flask flask_sqlalchemy werkzeug sqlalchemy pandas openpyxl python-Levenshtein rapidfuzz`."
    ) from e

# Assumes these already exist in your project:
# db, SalesOrder, SalesOrderItem, Invoice, PurchaseOrder, Client

from datetime import UTC, date, datetime, timedelta
import os
import json
from functools import wraps
from io import StringIO, TextIOWrapper, BytesIO# <--- MAKE SURE THIS IS HERE
import re

from analytics_services import (
    build_analytics_payload,
    preview_excel_workbook,
    calculate_customer_behavior_score,
    get_client_status,
    get_overview_kpis,
    get_sales_trend_graph,
    get_clients_analysis,
    get_expenses_breakdown,
    get_sales_analysis,
    get_comparative_analysis,
)
from admin_services import (
    bulk_delete,
    bulk_update_status,
    export_data_grid_csv,
    get_data_grid,
    get_db_health,
    get_schema,
    run_maintenance,
    run_safe_sql,
)
from defense_migrations import ensure_defense_schema

load_dotenv()

app = Flask(__name__)
os.makedirs(app.instance_path, exist_ok=True)

IS_PRODUCTION = bool(os.environ.get("RENDER") or os.environ.get("FLASK_ENV") == "production")
configured_secret_key = os.environ.get('SECRET_KEY')
if IS_PRODUCTION and not configured_secret_key:
    raise RuntimeError("SECRET_KEY is required in production.")
app.config['SECRET_KEY'] = configured_secret_key or 'dev-secret-key'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = bool(IS_PRODUCTION or os.environ.get('SESSION_COOKIE_SECURE') == 'true')
app.config['MAX_CONTENT_LENGTH'] = int(os.environ.get('MAX_UPLOAD_BYTES', 10 * 1024 * 1024))
basedir = os.path.abspath(os.path.dirname(__file__))
database_url = os.environ.get("DATABASE_URL")
if database_url and database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url[len("postgres://"):]

if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
elif IS_PRODUCTION:
    raise RuntimeError("DATABASE_URL is required on Render/production so permanent data stays in Supabase.")
else:
    # SQLite on Render free tier is suitable only for demo/prototype use because
    # local file storage is ephemeral and does not persist reliably across restarts.
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}

db = SQLAlchemy(app)

def db_year(column):
    return extract('year', column).cast(db.Integer)

def db_month_number(column):
    return extract('month', column).cast(db.Integer)

def db_month_key(column):
    if db.engine.dialect.name == 'postgresql':
        return func.to_char(column, 'YYYY-MM')
    return func.strftime('%Y-%m', column)

# Database Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)
    password_hash = db.Column(db.String(120), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)
    disabled_reason = db.Column(db.Text)
    approved_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    approved_at = db.Column(db.DateTime)
    profile_photo = db.Column(db.String(255))
    profile_photo_data = db.Column(db.Text)
    profile_photo_mime = db.Column(db.String(80))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    role = db.relationship('Role', backref='users')
    approved_by_user = db.relationship('User', remote_side=[id])

class Role(db.Model):
    __tablename__ = 'roles'
    id = db.Column(db.Integer, primary_key=True)
    role_name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)

class Client(db.Model):
    __tablename__ = 'clients'
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(200), nullable=False)
    contact_info = db.Column(db.String(500))
    status = db.Column(db.String(20), default='ACTIVE')
    total_revenue = db.Column(db.Float, default=0.0)
    total_paid = db.Column(db.Float, default=0.0)
    total_balance = db.Column(db.Float, default=0.0)
    balance_status = db.Column(db.String(30), default='Settled')
    last_invoice_date = db.Column(db.Date)
    last_payment_date = db.Column(db.Date)
    financials_updated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ClientAlias(db.Model):
    __tablename__ = 'client_aliases'
    id = db.Column(db.Integer, primary_key=True)
    alias_name = db.Column(db.String(200), nullable=False)
    normalized_alias = db.Column(db.String(200), nullable=False, unique=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    status = db.Column(db.String(20), default='ACTIVE')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    client = db.relationship('Client', backref='aliases')

class SalesOrder(db.Model):
    __tablename__ = 'sales_orders'
    id = db.Column(db.Integer, primary_key=True)
    so_number = db.Column(db.String(50), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
    company_name = db.Column(db.String(200))
    official_client_name = db.Column(db.String(200))
    original_entered_client_name = db.Column(db.String(200))
    store_name = db.Column(db.String(200))
    store_branch = db.Column(db.String(200))
    order_date = db.Column(db.Date, nullable=False)
    sales_staff = db.Column(db.String(100))
    terms = db.Column(db.Integer, default=30)
    notes = db.Column(db.Text)
    total_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='PENDING')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    client = db.relationship('Client', backref='sales_orders')
    items = db.relationship('SalesOrderItem', backref='sales_order', cascade='all, delete-orphan')
    branches = db.relationship('SalesOrderBranch', backref='sales_order', cascade='all, delete-orphan')

class SalesOrderBranch(db.Model):
    __tablename__ = 'sales_order_branches'
    __table_args__ = (
        db.UniqueConstraint('sales_order_id', 'normalized_branch_key', name='uq_sales_order_branch_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    branch_name = db.Column(db.String(200), nullable=False)
    normalized_branch_key = db.Column(db.String(200), nullable=False)

class SalesOrderItem(db.Model):
    __tablename__ = 'sales_order_items'
    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    sales_order_branch_id = db.Column(db.Integer, db.ForeignKey('sales_order_branches.id'), nullable=True)
    particular = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)

    branch = db.relationship('SalesOrderBranch', backref='items')

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=True)
    invoice_type = db.Column(db.String(20), nullable=False)  # 'SALES' or 'SERVICE'
    invoice_date = db.Column(db.Date, nullable=False)
    summary = db.Column(db.Text)
    payment_type = db.Column(db.String(20))  # 'DOWNPAYMENT' or 'FULL'
    cr_number = db.Column(db.String(50))
    payment_amount = db.Column(db.Float, default=0.0)
    tax_amount_paid = db.Column(db.Float, default=0.0)
    is_2307_checked = db.Column(db.Boolean, default=False)
    total_amount = db.Column(db.Float, nullable=True)
    amount_paid = db.Column(db.Float, default=0.0)
    balance = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default='UNPAID')
    uploaded_client_name = db.Column(db.String(200))
    upload_source = db.Column(db.String(50))
    admin_upload_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    sales_order = db.relationship('SalesOrder', backref='invoices')

class CollectionReceipt(db.Model):
    __tablename__ = 'collection_receipts'
    __table_args__ = (
        db.UniqueConstraint(
            'invoice_id',
            'normalized_cr_number',
            name='uq_collection_receipts_invoice_cr',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(
        db.Integer,
        db.ForeignKey('invoices.id', ondelete='CASCADE'),
        nullable=False,
    )
    receipt_date = db.Column(db.Date, nullable=False)
    cr_number = db.Column(db.String(50), nullable=False)
    normalized_cr_number = db.Column(db.String(50), nullable=False)
    payment_type = db.Column(db.String(20), nullable=False)
    payment_amount = db.Column(db.Float, nullable=False, default=0.0)
    tax_amount_paid = db.Column(db.Float, nullable=False, default=0.0)
    is_2307_checked = db.Column(db.Boolean, default=False, nullable=False)
    collected_total = db.Column(db.Float, nullable=False, default=0.0)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recorded_by = db.Column(db.String(80), nullable=False, default='system')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    invoice = db.relationship(
        'Invoice',
        backref=db.backref(
            'collection_receipts',
            cascade='all, delete-orphan',
            order_by='CollectionReceipt.receipt_date, CollectionReceipt.id',
        ),
    )
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

class PurchaseOrder(db.Model):
    __tablename__ = 'purchase_orders'
    id = db.Column(db.Integer, primary_key=True)
    check_voucher_number = db.Column(db.String(50), nullable=False)
    check_number = db.Column(db.String(50), nullable=False)
    check_date = db.Column(db.Date, nullable=False)
    date = db.Column(db.Date, nullable=False)
    or_date = db.Column(db.Date)
    ar_cr_or_number = db.Column(db.String(50))
    po_number = db.Column(db.String(50))
    lf_no = db.Column(db.String(50))
    particulars = db.Column(db.String(500), nullable=False)
    supplier_payee = db.Column(db.String(200), nullable=False)
    tin_number = db.Column(db.String(50))
    cash_amount = db.Column(db.Float, nullable=False)
    net_balance = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='PENDING')
    category = db.Column(db.String(20), default='FIXED')  # 'FIXED' or 'VARIABLE'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    debits = db.relationship('PurchaseOrderDebit', backref='purchase_order', cascade='all, delete-orphan')

class PurchaseOrderDebit(db.Model):
    __tablename__ = 'purchase_order_debits'
    id = db.Column(db.Integer, primary_key=True)
    purchase_order_id = db.Column(db.Integer, db.ForeignKey('purchase_orders.id'), nullable=False)
    debit_type = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)

class SessionRecord(db.Model):
    __tablename__ = 'session_records'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    username = db.Column(db.String(80), nullable=False)
    role_name = db.Column(db.String(50), nullable=False)
    login_at = db.Column(db.DateTime, default=datetime.utcnow)
    logout_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='ACTIVE')

    user = db.relationship('User', backref='session_records')

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    username = db.Column(db.String(80), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.String(100))
    old_value = db.Column(db.Text)
    new_value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='audit_logs')

class PasswordReset(db.Model):
    __tablename__ = 'password_resets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    username = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), default='PENDING', nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime)
    resolved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

    user = db.relationship('User', foreign_keys=[user_id], backref='password_reset_requests')
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_user_id])

class AnalyticsData(db.Model):
    __tablename__ = 'analytics_data'
    analytics_id = db.Column(db.Integer, primary_key=True)
    id = synonym('analytics_id')
    source_type = db.Column(db.Text, nullable=False)
    source_id = db.Column(db.Text, nullable=False)
    transaction_date = db.Column(db.Date, nullable=False)
    financial_stage = db.Column(db.Text, nullable=False)
    flow_direction = db.Column(db.Text, nullable=False)
    flow_status = db.Column(db.Text, nullable=False)
    party_name = db.Column(db.Text, nullable=False)
    party_role = db.Column(db.Text, nullable=False)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    balance_amount = db.Column(db.Float, default=0.0)
    category = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text)
    description = db.Column(db.Text)
    upload_batch_id = db.Column(db.String(80))
    source_filename = db.Column(db.String(255))
    source_format = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    def __repr__(self):
        return f"<analytics_data {self.analytics_id} - {self.source_type}:{self.source_id}>"

class EvaluationSession(db.Model):
    __tablename__ = 'evaluation_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    evaluator_name = db.Column(db.String(120), nullable=False)
    evaluator_role = db.Column(db.String(80))
    overall_comment = db.Column(db.Text)
    overall_mean = db.Column(db.Float, default=0.0)
    interpretation = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    responses = db.relationship('EvaluationResponse', backref='session', cascade='all, delete-orphan')
    user = db.relationship('User')

class EvaluationQuestion(db.Model):
    __tablename__ = 'evaluation_questions'
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(80), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    display_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)

class EvaluationResponse(db.Model):
    __tablename__ = 'evaluation_responses'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('evaluation_sessions.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('evaluation_questions.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    question = db.relationship('EvaluationQuestion')

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# End of Models Section


# Authentication helpers and decorators
USER_STATUS_PENDING = 'pending'
USER_STATUS_APPROVED = 'approved'
USER_STATUS_REJECTED = 'rejected'
USER_STATUS_DISABLED = 'disabled'
USER_STATUS_CHOICES = {
    USER_STATUS_PENDING,
    USER_STATUS_APPROVED,
    USER_STATUS_REJECTED,
    USER_STATUS_DISABLED,
}
LEGACY_USER_STATUS_MAP = {
    'ACTIVE': USER_STATUS_APPROVED,
    'INACTIVE': USER_STATUS_DISABLED,
}
SALES_ROLES = ('admin', 'staff', 'sales staff')
ACCOUNTING_ROLES = ('admin', 'staff', 'accounting staff')
OPERATIONS_ROLES = ('admin', 'staff', 'sales staff', 'accounting staff')
MANAGEMENT_ROLES = ('admin', 'manager')
ALL_BUSINESS_ROLES = ('admin', 'manager', 'staff', 'sales staff', 'accounting staff')
PROFILE_PHOTO_MAX_BYTES = 1024 * 1024
PROFILE_PHOTO_MIME_TYPES = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp',
}

ERROR_INTERFACE = {
    'validation': ('Check the Information', 'Some information is missing or needs correction.', 'Review the fields, then try again.'),
    'authentication': ('Sign In Required', 'Your session could not be verified.', 'Sign in again to continue.'),
    'permission': ('Access Not Allowed', 'Your account does not have permission to view this page.', 'Contact an administrator if you believe this is incorrect.'),
    'database': ('Database Unavailable', 'The system could not complete the database request.', 'Wait a moment, then try again.'),
    'network': ('Connection Problem', 'The system could not reach the server.', 'Check your connection and try again.'),
    'server': ('Server Error', 'Something went wrong while processing the request.', 'Try again. If the issue continues, contact an administrator.'),
    'empty': ('No Results Found', 'There is no data to show for the current filters.', 'Adjust the filters or add records first.'),
}

def wants_json_response():
    return (
        request.path.startswith('/api/')
        or request.path.startswith('/admin/')
        or request.accept_mimetypes.best == 'application/json'
        or request.is_json
    )

def error_interface_payload(error_type='server', details=None):
    title, message, action = ERROR_INTERFACE.get(error_type, ERROR_INTERFACE['server'])
    payload = {'type': error_type, 'title': title, 'message': message, 'action': action}
    if session.get('role') == 'admin' and details:
        payload['details'] = str(details)
    return payload

def render_error_interface(error_type='server', status_code=500, details=None):
    payload = error_interface_payload(error_type, details)
    if wants_json_response():
        response = {'success': False, 'error': payload['message'], 'error_type': payload['type']}
        if payload.get('details'):
            response['details'] = payload['details']
        return jsonify(response), status_code
    return render_template('error_interface.html', error_info=payload), status_code

def public_error_message(error, fallback='The request could not be completed. Please review the information and try again.'):
    if not IS_PRODUCTION or app.config.get('TESTING'):
        return str(error)
    app.logger.exception('Production request failed: %s', error)
    return fallback

def normalize_user_status(status):
    value = (status or USER_STATUS_PENDING).strip()
    return LEGACY_USER_STATUS_MAP.get(value.upper(), value.lower())

def is_user_approved(user):
    return bool(user and normalize_user_status(user.status) == USER_STATUS_APPROVED)

def user_access_message(user):
    status = normalize_user_status(user.status if user else None)
    if status == USER_STATUS_PENDING:
        return 'Your account is pending administrator approval.'
    if status == USER_STATUS_REJECTED:
        return 'Your account request was not approved. Contact the administrator for assistance.'
    if status == USER_STATUS_DISABLED:
        return 'Your account is disabled. Contact the administrator for assistance.'
    return 'Your account is not approved for access.'

def current_user_record():
    return db.session.get(User, session.get('user_id')) if session.get('user_id') else None

def user_role_name(user):
    return user.role.role_name.lower() if user and user.role and user.role.role_name else ''

def user_has_role(user, allowed_roles):
    allowed = {role.lower() for role in allowed_roles}
    return user_role_name(user) in allowed

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            if wants_json_response():
                return jsonify({'success': False, 'error': 'Your session has expired. Sign in again.'}), 401
            return redirect(url_for('login'))
        user = db.session.get(User, session['user_id'])
        if not is_user_approved(user):
            session.clear()
            if wants_json_response():
                return jsonify({'success': False, 'error': 'Your session is no longer active. Sign in again.'}), 401
            flash(user_access_message(user), 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                if wants_json_response():
                    return jsonify({'success': False, 'error': 'Your session has expired. Sign in again.'}), 401
                return redirect(url_for('login'))
            
            user = db.session.get(User, session['user_id'])
            if not is_user_approved(user) or not user_has_role(user, allowed_roles):
                if wants_json_response():
                    return jsonify({'success': False, 'error': 'Access denied. Insufficient permissions.'}), 403
                flash('Access denied. Insufficient permissions.', 'error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def app_models():
    return {
        'User': User,
        'Role': Role,
        'Client': Client,
        'ClientAlias': ClientAlias,
        'SalesOrder': SalesOrder,
        'SalesOrderBranch': SalesOrderBranch,
        'SalesOrderItem': SalesOrderItem,
        'Invoice': Invoice,
        'CollectionReceipt': CollectionReceipt,
        'PurchaseOrder': PurchaseOrder,
        'PurchaseOrderDebit': PurchaseOrderDebit,
        'SessionRecord': SessionRecord,
        'AuditLog': AuditLog,
        'PasswordReset': PasswordReset,
        'AnalyticsData': AnalyticsData,
        'EvaluationSession': EvaluationSession,
        'EvaluationQuestion': EvaluationQuestion,
        'EvaluationResponse': EvaluationResponse,
        'SystemSetting': SystemSetting,
    }

def admin_required_json():
    user = current_user_record()
    if not is_user_approved(user) or not user_has_role(user, ('admin',)):
        return jsonify({'success': False, 'error': 'Admin account required'}), 403
    return None

THEME_JSON_PATH = os.path.join(app.static_folder, 'css', 'theme-overrides.json')
THEME_CSS_PATH = os.path.join(app.static_folder, 'css', 'theme-overrides.css')
THEME_FIELDS = {
    'bg': {'label': 'Background', 'type': 'color', 'default': '#F3EFE6'},
    'bg_2': {'label': 'Background 2', 'type': 'color', 'default': '#FFF9ED'},
    'orange': {'label': 'Primary Orange', 'type': 'color', 'default': '#FF6A00'},
    'orange_2': {'label': 'Accent Orange', 'type': 'color', 'default': '#FF9F1C'},
    'text': {'label': 'Main Text', 'type': 'color', 'default': '#15130F'},
    'muted': {'label': 'Muted Text', 'type': 'color', 'default': '#70695D'},
    'glass_opacity': {'label': 'Glass Opacity', 'type': 'number', 'default': 0.58, 'min': 0, 'max': 0.75, 'step': 0.01},
    'glass_strong_opacity': {'label': 'Strong Glass Opacity', 'type': 'number', 'default': 0.72, 'min': 0, 'max': 0.85, 'step': 0.01},
    'glass_border_opacity': {'label': 'Glass Border Opacity', 'type': 'number', 'default': 0.68, 'min': 0, 'max': 0.90, 'step': 0.01},
    'blur_px': {'label': 'Glass Blur', 'type': 'number', 'default': 28, 'min': 0, 'max': 30, 'step': 1},
    'saturate_percent': {'label': 'Glass Saturation', 'type': 'number', 'default': 180, 'min': 80, 'max': 220, 'step': 5},
    'card_radius_px': {'label': 'Card Radius', 'type': 'number', 'default': 8, 'min': 0, 'max': 16, 'step': 1},
    'control_radius_px': {'label': 'Control Radius', 'type': 'number', 'default': 6, 'min': 0, 'max': 12, 'step': 1},
    'page_padding_px': {'label': 'Page Padding', 'type': 'number', 'default': 34, 'min': 12, 'max': 64, 'step': 1},
    'card_padding_px': {'label': 'Card Padding', 'type': 'number', 'default': 24, 'min': 10, 'max': 48, 'step': 1},
    'stat_padding_px': {'label': 'KPI Padding', 'type': 'number', 'default': 20, 'min': 10, 'max': 40, 'step': 1},
    'nav_padding_px': {'label': 'Navbar Padding', 'type': 'number', 'default': 10, 'min': 6, 'max': 24, 'step': 1},
}

def default_theme_settings():
    return {key: field['default'] for key, field in THEME_FIELDS.items()}

def get_system_setting(key):
    try:
        setting = db.session.get(SystemSetting, key)
        return setting.value if setting else None
    except Exception:
        db.session.rollback()
        return None

def set_system_setting(key, value):
    setting = db.session.get(SystemSetting, key)
    if not setting:
        setting = SystemSetting(key=key, value=value)
        db.session.add(setting)
    else:
        setting.value = value
        setting.updated_at = datetime.utcnow()
    return setting

def read_theme_settings():
    settings = default_theme_settings()
    saved_json = get_system_setting('theme_settings')
    if saved_json:
        try:
            saved = json.loads(saved_json)
            if isinstance(saved, dict):
                settings.update({key: saved[key] for key in THEME_FIELDS if key in saved})
                return sanitize_theme_settings(settings)
        except json.JSONDecodeError:
            pass
    try:
        with open(THEME_JSON_PATH, 'r', encoding='utf-8') as theme_file:
            saved = json.load(theme_file)
        if isinstance(saved, dict):
            settings.update({key: saved[key] for key in THEME_FIELDS if key in saved})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return sanitize_theme_settings(settings)

def sanitize_theme_settings(raw_settings):
    sanitized = {}
    for key, field in THEME_FIELDS.items():
        value = raw_settings.get(key, field['default']) if isinstance(raw_settings, dict) else field['default']
        if field['type'] == 'color':
            value = str(value).strip()
            sanitized[key] = value if re.fullmatch(r'#[0-9A-Fa-f]{6}', value) else field['default']
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            numeric_value = float(field['default'])
        numeric_value = max(float(field['min']), min(float(field['max']), numeric_value))
        sanitized[key] = int(numeric_value) if float(numeric_value).is_integer() else round(numeric_value, 2)
    return sanitized

def hex_to_rgba(hex_color, opacity):
    color = hex_color.lstrip('#')
    red, green, blue = (int(color[index:index + 2], 16) for index in (0, 2, 4))
    return f'rgba({red}, {green}, {blue}, {opacity})'

def hex_to_rgb_tuple(hex_color):
    color = hex_color.lstrip('#')
    return tuple(int(color[index:index + 2], 16) for index in (0, 2, 4))

def build_theme_css(settings):
    bg_r, bg_g, bg_b = hex_to_rgb_tuple(settings['bg'])
    bg_luminance = (0.2126 * bg_r + 0.7152 * bg_g + 0.0722 * bg_b) / 255
    is_dark_theme = bg_luminance < 0.35
    bg_upper = settings['bg'].upper()
    bg_2_upper = settings['bg_2'].upper()
    orange_upper = settings['orange'].upper()
    is_dashboard_dark = bg_upper == '#0F1115'
    is_black_mode = bg_upper in ('#000000', '#050505')
    is_contrast_mode = (
        (bg_upper == '#000000' and orange_upper == '#FF9800') or
        (bg_upper == '#111827' and bg_2_upper == '#1F2937' and orange_upper == '#F59E0B') or
        bg_upper == '#020B1F' or
        bg_2_upper == '#061A3A'
    )
    is_solid_mode = is_dashboard_dark or is_contrast_mode or int(settings.get('blur_px', 0)) == 0
    if is_dashboard_dark:
        surface_base = '#1A1D24'
        surface_strong_base = '#1A1D24'
        glass_base = '#1A1D24'
        glass_strong_base = '#1A1D24'
        border_base = '#334155'
        line_base = '#334155'
    elif is_contrast_mode:
        surface_base = '#1F2937'
        surface_strong_base = '#1F2937'
        glass_base = '#1F2937'
        glass_strong_base = '#1F2937'
        border_base = '#475569'
        line_base = border_base
    elif is_black_mode:
        surface_base = '#1A1D24'
        surface_strong_base = '#1A1D24'
        glass_base = '#1A1D24'
        glass_strong_base = '#1A1D24'
        border_base = '#334155'
        line_base = '#334155'
    elif is_contrast_mode:
        surface_base = '#788296'
        surface_strong_base = '#94A3B8'
        glass_base = '#94A3B8'
        glass_strong_base = '#94A3B8'
        border_base = '#FFFFFF'
        line_base = '#FFFFFF'
    elif is_dark_theme:
        surface_base = '#0F172A'
        surface_strong_base = '#0F172A'
        glass_base = '#0F172A'
        glass_strong_base = '#0F172A'
        border_base = '#94A3B8'
        line_base = '#94A3B8'
    else:
        surface_base = '#FFFFFF'
        surface_strong_base = '#FFFFFF'
        glass_base = '#F2F2F2'
        glass_strong_base = '#FFFFFF'
        border_base = '#FFFFFF'
        line_base = '#0F172A'
    white_glass = glass_base if is_solid_mode else hex_to_rgba(glass_base, settings['glass_opacity'])
    white_glass_strong = glass_strong_base if is_solid_mode else hex_to_rgba(glass_strong_base, settings['glass_strong_opacity'])
    white_border = border_base if is_solid_mode else hex_to_rgba(border_base, settings['glass_border_opacity'])
    text_rgba = hex_to_rgba(settings['text'], 0.96)
    muted_rgba = hex_to_rgba(settings['muted'], 0.78)
    ambient_primary = hex_to_rgba(settings['orange'], 0.16 if is_dark_theme else 0.24)
    ambient_secondary = hex_to_rgba(settings['orange_2'], 0.10 if is_dark_theme else 0.18)
    ambient_base = hex_to_rgba(settings['bg_2'], 0.34 if is_dark_theme else 0.16)
    surface_opacity = 1 if is_solid_mode else 0.72 if is_dark_theme else 0.64
    surface_strong_opacity = 1 if is_solid_mode else 0.90 if is_dark_theme else 0.82
    highlight_r, highlight_g, highlight_b = hex_to_rgb_tuple(settings['orange'])
    accent_r, accent_g, accent_b = hex_to_rgb_tuple(settings['orange_2'])
    glass_shadow = (
        '0 10px 26px rgba(2, 6, 23, 0.22)'
        if is_contrast_mode else
        '0 4px 20px rgba(0, 0, 0, 0.40)'
        if is_solid_mode else
        (
            '0 24px 70px rgba(0, 0, 0, 0.42), '
            '0 12px 34px rgba(0, 0, 0, 0.30), '
            'inset 1px 1px 0 rgba(255, 255, 255, 0.08), '
            f'inset -18px -18px 42px rgba({accent_r}, {accent_g}, {accent_b}, 0.08)'
        )
        if is_dark_theme else
        (
            f'0 24px 70px rgba({highlight_r}, {highlight_g}, {highlight_b}, 0.18), '
            '0 12px 34px rgba(15, 23, 42, 0.16), '
            'inset 1px 1px 0 rgba(255, 255, 255, 0.84), '
            f'inset -18px -18px 42px rgba({accent_r}, {accent_g}, {accent_b}, 0.13)'
        )
    )
    body_background = (
        f'var(--bg)'
        if is_dashboard_dark or is_contrast_mode else
        f'linear-gradient(135deg, var(--bg), var(--bg-2))'
        if is_solid_mode else
        '\n        '.join([
            f'radial-gradient(circle at 8% 5%, {ambient_primary}, transparent 34%),',
            f'radial-gradient(circle at 88% 8%, {ambient_secondary}, transparent 30%),',
            f'radial-gradient(circle at 80% 95%, {ambient_base}, transparent 34%),',
            'linear-gradient(135deg, var(--bg), var(--bg-2))'
        ])
    )
    return f"""/* Generated by Admin Theme Editor. Do not hand-edit; use Database Interface > Theme Editor. */
:root {{
    --bg: {settings['bg']};
    --bg-2: {settings['bg_2']};
    --bg-base: var(--bg);
    --bg-canvas: var(--bg-base);
    --orange: {settings['orange']};
    --orange-2: {settings['orange_2']};
    --accent-main: var(--orange);
    --accent-hover: var(--orange-2);
    --accent-muted: {hex_to_rgba(settings['orange'], 0.10)};
    --brand-orange: var(--orange);
    --text: {text_rgba};
    --text-main: var(--text);
    --text-primary: var(--text-main);
    --muted: {muted_rgba};
    --text-muted: var(--muted);
    --text-secondary: var(--text-muted);
    --surface: {hex_to_rgba(surface_base, surface_opacity)};
    --surface-strong: {hex_to_rgba(surface_strong_base, surface_strong_opacity)};
    --bg-surface: var(--surface-strong);
    --glass: {white_glass};
    --glass-strong: {white_glass_strong};
    --glass-border: {white_border};
    --border-color: var(--glass-border);
    --border-width: 1px;
    --card-bg: var(--surface-strong);
    --card-shadow: var(--shadow-soft);
    --line: {hex_to_rgba(line_base, 0.44 if (is_black_mode or is_contrast_mode) else 0.22 if is_dark_theme else 0.10)};
    --line-strong: {hex_to_rgba(line_base, 0.72 if (is_black_mode or is_contrast_mode) else 0.34 if is_dark_theme else 0.18)};
    --glass-blur: {'none' if is_solid_mode else f"blur({settings['blur_px']}px) saturate({settings['saturate_percent']}%)"};
    --radius-xl: {settings['card_radius_px']}px;
    --radius-lg: {settings['control_radius_px']}px;
    --radius-md: {max(0, settings['control_radius_px'] - 2)}px;
    --shadow: {'0 16px 40px rgba(2, 6, 23, 0.28)' if is_contrast_mode else '0 4px 20px rgba(0, 0, 0, 0.40)' if is_solid_mode else '0 28px 90px rgba(0, 0, 0, 0.48)' if is_dark_theme else '0 24px 80px rgba(15, 23, 42, 0.14)'};
    --shadow-soft: {'0 10px 26px rgba(2, 6, 23, 0.22)' if is_contrast_mode else '0 4px 20px rgba(0, 0, 0, 0.40)' if is_solid_mode else '0 14px 44px rgba(0, 0, 0, 0.38)' if is_dark_theme else '0 12px 38px rgba(15, 23, 42, 0.10)'};
    --glass-shadow: {glass_shadow};
}}

body {{
    background: {body_background} !important;
    background-attachment: fixed !important;
}}

body::before,
body::after {{
    {'display: none !important;' if is_solid_mode else ''}
}}

.glass,
.card,
.report-card,
.summary-item,
.stat-card,
.form-card,
.form-section,
.table-wrap,
.table-card,
.profile-card,
.admin-card,
.schema-box,
.sql-result,
.client-table-scroll,
.mapper-container,
.excel-panel,
.client-review-panel,
.invoice-container,
.sales-order-viewer,
.debit-section,
.debit-item,
.calculation-section,
.readonly-field-value,
.particulars-container,
.analytics-section .card {{
    border-color: var(--glass-border) !important;
    background-clip: padding-box;
}}

main,
.analytics-container,
.admin-shell {{
    padding-top: {settings['page_padding_px']}px !important;
    padding-bottom: {settings['page_padding_px'] + 14}px !important;
}}

nav {{
    padding: {settings['nav_padding_px']}px {max(8, settings['nav_padding_px'] + 2)}px !important;
}}

.card,
.report-card,
.form-card,
.form-section,
.table-card,
.profile-card,
.admin-card,
.analytics-section .card {{
    padding: {settings['card_padding_px']}px !important;
    border-radius: {settings['card_radius_px']}px !important;
}}

.stat-card,
.summary-item {{
    padding: {settings['stat_padding_px']}px !important;
    border-radius: {max(0, settings['card_radius_px'] - 2) if settings['card_radius_px'] > 2 else settings['card_radius_px']}px !important;
}}

input,
select,
textarea,
button,
.btn,
.nav-link,
.report-tab,
.analytics-tab {{
    border-radius: {settings['control_radius_px']}px !important;
}}

input:not([type="checkbox"]):not([type="radio"]),
select,
textarea {{
    min-height: 44px !important;
    padding: 0.7rem 0.85rem !important;
}}

input[type="checkbox"],
input[type="radio"] {{
    width: 20px !important;
    height: 20px !important;
    min-height: 20px !important;
    margin: 0 !important;
    accent-color: var(--orange);
}}

.btn,
button:not(.recommendation-card),
.filter-btn,
.view-toggle button {{
    min-height: 44px !important;
}}

.btn-sm,
button.btn-sm {{
    min-height: 38px !important;
}}

.checkbox-group {{
    min-height: 44px !important;
    align-items: center !important;
    gap: 12px !important;
}}

@media (max-width: 760px) {{
    .card,
    .report-card,
    .form-card,
    .form-section,
    .table-card,
    .profile-card,
    .admin-card,
    .analytics-section .card {{
        padding: 16px !important;
    }}
}}

nav,
nav.app-navbar,
body > nav {{
    position: sticky !important;
    top: 0 !important;
    width: 100% !important;
    max-width: none !important;
    min-height: 64px !important;
    margin: 0 !important;
    padding: 10px clamp(14px, 2.5vw, 28px) !important;
    display: grid !important;
    grid-template-columns: minmax(180px, 240px) minmax(0, 1fr) auto !important;
    gap: 14px !important;
    align-items: center !important;
    border: 0 !important;
    border-bottom: 1px solid var(--border-color) !important;
    border-radius: 0 !important;
    background: var(--card-bg) !important;
    background-image: none !important;
    box-shadow: 0 1px 0 var(--line) !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
}}

.nav-menu {{
    width: 100% !important;
    min-width: 0 !important;
    display: flex !important;
    justify-content: center !important;
    align-items: center !important;
    gap: 4px !important;
    overflow-x: auto !important;
    padding: 0 !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    scrollbar-width: none !important;
}}

.nav-link {{
    min-height: 38px !important;
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    padding: 8px 12px !important;
    border: 1px solid transparent !important;
    border-radius: {settings['control_radius_px']}px !important;
    background: transparent !important;
    color: var(--text-muted) !important;
    font-size: 0.86rem !important;
    font-weight: 700 !important;
    line-height: 1.15 !important;
    text-decoration: none !important;
    white-space: nowrap !important;
    box-shadow: none !important;
}}

.nav-link:hover {{
    color: var(--text-main) !important;
    background: var(--surface) !important;
    border-color: var(--border-color) !important;
    transform: none !important;
}}

.nav-link.active {{
    color: #000000 !important;
    background: var(--orange) !important;
    background-image: none !important;
    border-color: var(--orange) !important;
}}

.surface-card,
.surface-panel,
.metric-card,
.toolbar-surface,
.table-surface,
.dashboard-card,
.analytics-section,
.admin-card,
.stat-card,
.summary-item,
.card,
.report-card,
.form-card,
.form-section,
.table-card,
.table-wrap,
.excel-panel,
.client-review-panel,
.invoice-container,
.sales-order-viewer,
.purchase-order-container,
.debit-section,
.calculation-section,
.readonly-field-value {{
    background: var(--card-bg) !important;
    background-image: none !important;
    border: var(--border-width) solid var(--border-color) !important;
    border-radius: var(--radius-xl) !important;
    box-shadow: var(--card-shadow) !important;
    color: var(--text-main) !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
}}

.metric-card,
.stat-card,
.summary-item {{
    border-radius: var(--radius-lg) !important;
}}

.toolbar-surface,
.filter-controls,
.dashboard-filter,
.view-toggle,
.filter-group,
.grid-toolbar {{
    background: var(--card-bg) !important;
    border: var(--border-width) solid var(--border-color) !important;
    border-radius: var(--radius-lg) !important;
    box-shadow: none !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
}}

.table-surface,
.table-wrap,
.client-table-scroll,
.excel-table,
.report-table,
.client-table,
.data-table,
table {{
    background: var(--card-bg) !important;
    color: var(--text-main) !important;
}}

th,
.report-table th,
.client-table thead th {{
    background: var(--surface) !important;
    color: var(--text-muted) !important;
    border-color: var(--border-color) !important;
    -webkit-backdrop-filter: none !important;
    backdrop-filter: none !important;
}}

td,
.report-table td,
.client-table tbody td {{
    border-color: var(--line) !important;
    color: var(--text-main) !important;
}}

.nav-user {{
    min-width: 0 !important;
    display: inline-flex !important;
    justify-content: flex-end !important;
    align-items: center !important;
    gap: 10px !important;
    color: var(--text-muted) !important;
}}

.profile-link,
#datetime {{
    min-height: 36px !important;
    display: inline-flex !important;
    align-items: center !important;
    gap: 8px !important;
    padding: 6px 10px !important;
    border: 1px solid var(--border-color) !important;
    border-radius: {settings['control_radius_px']}px !important;
    background: transparent !important;
    color: var(--text-muted) !important;
    box-shadow: none !important;
}}

main,
.analytics-container,
.admin-shell {{
    width: min(1480px, calc(100% - 28px)) !important;
    padding-top: 24px !important;
}}

body[data-theme-mode="dark"] [style*="background: white"],
body[data-theme-mode="dark"] [style*="background:white"],
body[data-theme-mode="dark"] [style*="background: #fff"],
body[data-theme-mode="dark"] [style*="background:#fff"],
body[data-theme-mode="dark"] [style*="background: #F9FAFB"],
body[data-theme-mode="dark"] [style*="background:#F9FAFB"],
body[data-theme-mode="dark"] [style*="background: #F8FAFC"],
body[data-theme-mode="dark"] [style*="background:#F8FAFC"],
body[data-theme-mode="contrast"] [style*="background: white"],
body[data-theme-mode="contrast"] [style*="background:white"],
body[data-theme-mode="contrast"] [style*="background: #fff"],
body[data-theme-mode="contrast"] [style*="background:#fff"],
body[data-theme-mode="contrast"] [style*="background: #F9FAFB"],
body[data-theme-mode="contrast"] [style*="background:#F9FAFB"],
body[data-theme-mode="contrast"] [style*="background: #F8FAFC"],
body[data-theme-mode="contrast"] [style*="background:#F8FAFC"] {{
    background: var(--surface-strong) !important;
    color: var(--text-main) !important;
}}

@media (max-width: 980px) {{
    nav,
    nav.app-navbar,
    body > nav {{
        grid-template-columns: 1fr auto !important;
        gap: 8px !important;
        padding: 9px 12px !important;
    }}

    .nav-menu {{
        grid-column: 1 / -1 !important;
        grid-row: 2 !important;
        justify-content: flex-start !important;
        padding-top: 6px !important;
    }}

    #datetime {{
        display: none !important;
    }}
}}
"""

def write_theme_files(settings):
    # Render file systems are ephemeral; persist runtime theme changes in Supabase Postgres.
    set_system_setting('theme_settings', json.dumps(settings, separators=(',', ':')))

def clean_text(value, keep_period=False, keep_ampersand=False):
    value = '' if value is None else str(value).strip()
    allowed = 'A-Za-z0-9\\s'
    if keep_period:
        allowed += '.'
    if keep_ampersand:
        allowed += '&'
    pattern = rf'[^{allowed}]'
    return re.sub(r'\s+', ' ', re.sub(pattern, '', value)).strip()

def clean_code(value):
    value = '' if value is None else str(value).strip()
    return re.sub(r'\s+', ' ', re.sub(r'[^A-Za-z0-9\s#./_-]', '', value)).strip()

def normalize_invoice_number(value, cr_number=None):
    number = clean_code(value).upper()
    if number in ('', 'NULL', 'N/A', 'NA', 'NONE'):
        receipt = clean_code(cr_number).upper()
        return f'CR-{receipt}' if receipt else ''
    match = re.match(r'^(SVI|SVL|SI)[\s_-]*(.+)$', number)
    if match:
        suffix = re.sub(r'[\s_-]+', '-', match.group(2)).strip('-')
        return f'{match.group(1)}-{suffix}' if suffix else match.group(1)
    return re.sub(r'\s+', '-', number)

def canonical_invoice_type(invoice_number, stored_type=''):
    normalized_number = re.sub(r'[^A-Z0-9]', '', clean_code(invoice_number).upper())
    if normalized_number.startswith(('SVI', 'SVL')):
        return 'SERVICE'
    if normalized_number.startswith('SI'):
        return 'SALES'
    return clean_code(stored_type).upper()

def parse_positive_whole_quantity(value, field_label='Quantity'):
    try:
        quantity = Decimal(str(value).strip())
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        raise ValueError(f'{field_label} must be a valid whole number.')
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError(f'{field_label} must be greater than zero.')
    if quantity != quantity.to_integral_value():
        raise ValueError(f'{field_label} must be a whole number.')
    return int(quantity)

def normalize_client_name(value):
    value = '' if value is None else str(value).upper()
    value = value.replace('&', ' AND ')
    value = re.sub(r'[.,]', ' ', value)
    value = re.sub(r'[^A-Z0-9\s]', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()

def normalize_client_match_key(value):
    return normalize_client_name(value)

CLIENT_LIKELY_TYPO_PERCENT = 95
CLIENT_REVIEW_MATCH_PERCENT = 85
DEFAULT_STORE_BRANCH = 'HEAD OFFICE'
CLIENT_FUZZY_MATCH_EXCEPTIONS = {
    (
        normalize_client_match_key('TEAMAKERS INC'),
        normalize_client_match_key('TEAMASTERS INC'),
    ),
}
CLIENT_FUZZY_IGNORE_TOKENS = {
    'INC', 'INCORPORATED', 'CORP', 'CORPORATION', 'CO', 'COMPANY',
    'LTD', 'LLC', 'OPC', 'PHILS', 'PHILIPPINES'
}

def is_client_fuzzy_exception(candidate_name, matched_name):
    pair = (
        normalize_client_match_key(candidate_name),
        normalize_client_match_key(matched_name),
    )
    return pair in CLIENT_FUZZY_MATCH_EXCEPTIONS or (pair[1], pair[0]) in CLIENT_FUZZY_MATCH_EXCEPTIONS

def simplify_client_key_for_fuzzy(value):
    tokens = []
    for token in normalize_client_match_key(value).split():
        if token in CLIENT_FUZZY_IGNORE_TOKENS:
            continue
        if token.isdigit() and len(token) >= 4:
            continue
        tokens.append(token)
    return ' '.join(tokens)

def client_token_sort_ratio(left, right):
    return Levenshtein.ratio(' '.join(sorted(left.split())), ' '.join(sorted(right.split()))) * 100

def client_token_set_ratio(left, right):
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0
    common = left_tokens & right_tokens
    left_only = left_tokens - common
    right_only = right_tokens - common
    common_text = ' '.join(sorted(common))
    left_text = ' '.join(sorted(common | left_only))
    right_text = ' '.join(sorted(common | right_only))
    return max(
        Levenshtein.ratio(common_text, left_text) * 100 if common_text else 0,
        Levenshtein.ratio(common_text, right_text) * 100 if common_text else 0,
        Levenshtein.ratio(left_text, right_text) * 100,
    )

def calculate_client_match_percent(candidate_key, existing_key):
    if not candidate_key or not existing_key:
        return 0
    simplified_candidate = simplify_client_key_for_fuzzy(candidate_key)
    simplified_existing = simplify_client_key_for_fuzzy(existing_key)
    comparison_pairs = [(candidate_key, existing_key)]
    if simplified_candidate and simplified_existing:
        comparison_pairs.append((simplified_candidate, simplified_existing))
    scores = []
    if rapidfuzz_fuzz:
        for left, right in comparison_pairs:
            scores.extend([
                rapidfuzz_fuzz.ratio(left, right),
                rapidfuzz_fuzz.token_sort_ratio(left, right),
                rapidfuzz_fuzz.token_set_ratio(left, right),
            ])
        return round(max(scores), 2)
    for left, right in comparison_pairs:
        scores.extend([
            Levenshtein.ratio(left, right) * 100,
            client_token_sort_ratio(left, right),
            client_token_set_ratio(left, right),
        ])
    return round(max(scores), 2)

def build_client_registry():
    clients = Client.query.all()
    aliases = ClientAlias.query.filter_by(status='ACTIVE').all()
    lookup = {}
    official_entries = []
    for client in clients:
        key = normalize_client_match_key(client.client_name)
        if not key:
            continue
        entry = {
            'client_id': client.id,
            'client_name': client.client_name,
            'status': client.status or 'ACTIVE',
            'normalized': key,
            'source': 'official',
        }
        lookup[key] = entry
        official_entries.append(entry)
    for alias in aliases:
        if not alias.client:
            continue
        alias_key = alias.normalized_alias or normalize_client_match_key(alias.alias_name)
        if not alias_key:
            continue
        lookup[alias_key] = {
            'client_id': alias.client.id,
            'client_name': alias.client.client_name,
            'status': alias.client.status or 'ACTIVE',
            'normalized': alias_key,
            'source': 'alias',
            'alias_name': alias.alias_name,
        }
    return {
        'clients': clients,
        'aliases': aliases,
        'lookup': lookup,
        'official_entries': official_entries,
    }

def learn_client_alias(alias_name, client):
    alias_key = normalize_client_match_key(alias_name)
    official_key = normalize_client_match_key(client.client_name)
    if not alias_key or alias_key == official_key:
        return None
    existing_alias = ClientAlias.query.filter_by(normalized_alias=alias_key).first()
    if existing_alias:
        existing_alias.client_id = client.id
        existing_alias.alias_name = clean_text(alias_name, keep_period=True, keep_ampersand=True).upper()
        existing_alias.status = 'ACTIVE'
        return existing_alias
    alias = ClientAlias(
        alias_name=clean_text(alias_name, keep_period=True, keep_ampersand=True).upper(),
        normalized_alias=alias_key,
        client_id=client.id,
        status='ACTIVE'
    )
    db.session.add(alias)
    return alias

def find_client_match(client_name, registry=None):
    candidate = clean_text(client_name, keep_period=True, keep_ampersand=True)
    candidate_key = normalize_client_match_key(candidate)
    if not candidate_key:
        return None

    best = None
    registry = registry or build_client_registry()
    for entry in registry['official_entries']:
        existing_key = entry['normalized']
        if not existing_key:
            continue
        score = calculate_client_match_percent(candidate_key, existing_key)
        if best is None or score > best['match_percent']:
            best = {
                'client_id': entry['client_id'],
                'client_name': entry['client_name'],
                'match_percent': score,
                'match_level': 'likely_typo' if score >= CLIENT_LIKELY_TYPO_PERCENT else 'review_required'
            }
    return best

def resolve_client_name(client_name, resolutions=None, create_client=False, contact_info='', registry=None):
    cleaned_name = clean_text(client_name, keep_period=True, keep_ampersand=True).upper() or 'UNMAPPED CLIENT'
    match_key = normalize_client_match_key(cleaned_name)
    resolutions = resolutions or {}
    chosen = resolutions.get(match_key) or resolutions.get(cleaned_name)
    registry = registry or build_client_registry()

    if chosen:
        action = chosen.get('action') if isinstance(chosen, dict) else str(chosen)
        selected_name = chosen.get('client_name') if isinstance(chosen, dict) else None
        selected_id = chosen.get('client_id') if isinstance(chosen, dict) else None
        if action in ('use_suggested', 'use_existing') and selected_name:
            existing = db.session.get(Client, selected_id) if selected_id else None
            if not existing:
                existing = Client.query.filter_by(client_name=selected_name).first()
            if existing:
                learn_client_alias(cleaned_name, existing)
                return {
                    'status': 'resolved',
                    'client': existing,
                    'client_name': existing.client_name,
                    'official_client_name': existing.client_name,
                    'original_entered_client_name': cleaned_name,
                    'match_percent': chosen.get('match_percent') if isinstance(chosen, dict) else None,
                    'resolution_key': match_key,
                }
        if action == 'ignore':
            return {'status': 'ignored', 'client': None, 'client_name': cleaned_name, 'resolution_key': match_key}
        if action == 'create_new':
            existing_entry = registry['lookup'].get(match_key)
            existing = db.session.get(Client, existing_entry['client_id']) if existing_entry else None
            if existing:
                return {'status': 'resolved', 'client': existing, 'client_name': existing.client_name, 'official_client_name': existing.client_name, 'original_entered_client_name': cleaned_name, 'resolution_key': match_key}
            if create_client:
                client = Client(client_name=cleaned_name, contact_info=contact_info or '', status='ACTIVE')
                db.session.add(client)
                db.session.flush()
                return {'status': 'created', 'client': client, 'client_name': client.client_name, 'official_client_name': client.client_name, 'original_entered_client_name': cleaned_name, 'resolution_key': match_key}
            return {'status': 'create_new', 'client': None, 'client_name': cleaned_name, 'resolution_key': match_key}

    exact_entry = registry['lookup'].get(match_key)
    if exact_entry:
        exact = db.session.get(Client, exact_entry['client_id'])
        return {
            'status': 'resolved',
            'client': exact,
            'client_name': exact.client_name,
            'official_client_name': exact.client_name,
            'original_entered_client_name': cleaned_name,
            'match_percent': 100,
            'match_source': exact_entry.get('source', 'official'),
            'resolution_key': match_key
        }

    match = find_client_match(cleaned_name, registry)
    if match and match['match_percent'] >= CLIENT_REVIEW_MATCH_PERCENT:
        return {
            'status': 'needs_choice',
            'client': None,
            'client_name': cleaned_name,
            'uploaded_name': cleaned_name,
            'suggested_client_id': match['client_id'],
            'suggested_client_name': match['client_name'],
            'match_percent': match['match_percent'],
            'match_level': match['match_level'],
            'resolution_key': match_key,
        }

    if create_client:
        client = Client(client_name=cleaned_name, contact_info=contact_info or '', status='ACTIVE')
        db.session.add(client)
        db.session.flush()
        return {'status': 'created', 'client': client, 'client_name': client.client_name, 'official_client_name': client.client_name, 'original_entered_client_name': cleaned_name, 'resolution_key': match_key}
    return {'status': 'create_new', 'client': None, 'client_name': cleaned_name, 'uploaded_name': cleaned_name, 'resolution_key': match_key}

def parse_resolution_payload(payload):
    raw = (payload or {}).get('resolutions', {})
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}

def client_resolution_public(resolution, row_number=None):
    return {
        'row': row_number,
        'status': resolution.get('status'),
        'resolution_key': resolution.get('resolution_key'),
        'uploaded_name': resolution.get('uploaded_name') or resolution.get('client_name'),
        'suggested_client_id': resolution.get('suggested_client_id'),
        'suggested_client_name': resolution.get('suggested_client_name'),
        'match_percent': resolution.get('match_percent'),
        'match_level': resolution.get('match_level'),
    }


def client_match_candidates(query, limit=10):
    cleaned_query = clean_text(query, keep_period=True, keep_ampersand=True).upper()
    query_key = normalize_client_match_key(cleaned_query)
    if not query_key:
        return []

    registry = build_client_registry()
    candidates = {}

    def add_candidate(client_id, client_name, score, source, alias_name=None):
        if not client_id or not client_name:
            return
        existing = candidates.get(client_id)
        payload = {
            'client_id': client_id,
            'client_name': client_name,
            'match_percent': round(float(score or 0), 2),
            'source': source,
            'alias_name': alias_name,
        }
        if existing is None or payload['match_percent'] > existing['match_percent']:
            candidates[client_id] = payload

    for entry in registry['official_entries']:
        score = calculate_client_match_percent(query_key, entry['normalized'])
        if query_key in entry['normalized'] or entry['normalized'] in query_key:
            score = max(score, 92)
        add_candidate(entry['client_id'], entry['client_name'], score, 'client')

    for alias in registry['aliases']:
        if not alias.client:
            continue
        alias_key = alias.normalized_alias or normalize_client_match_key(alias.alias_name)
        score = calculate_client_match_percent(query_key, alias_key)
        if query_key in alias_key or alias_key in query_key:
            score = max(score, 92)
        add_candidate(alias.client_id, alias.client.client_name, score, 'alias', alias.alias_name)

    return sorted(candidates.values(), key=lambda item: item['match_percent'], reverse=True)[:limit]

def sales_order_item_totals_subquery():
    return (
        db.session.query(
            SalesOrderItem.sales_order_id.label('sales_order_id'),
            db.func.count(SalesOrderItem.id).label('item_count'),
            db.func.coalesce(db.func.sum(SalesOrderItem.total), 0).label('item_total')
        )
        .group_by(SalesOrderItem.sales_order_id)
        .subquery()
    )

def sales_order_invoice_summary_subquery():
    return (
        db.session.query(
            Invoice.sales_order_id.label('sales_order_id'),
            db.func.count(Invoice.id).label('invoice_count'),
            db.func.coalesce(db.func.sum(Invoice.amount_paid), 0).label('invoice_amount_paid'),
            db.func.coalesce(db.func.sum(Invoice.balance), 0).label('invoice_balance'),
            db.func.max(Invoice.invoice_date).label('last_invoice_date')
        )
        .filter(Invoice.sales_order_id.isnot(None))
        .group_by(Invoice.sales_order_id)
        .subquery()
    )

def sales_order_query(statuses=None, outstanding_only=False):
    item_totals = sales_order_item_totals_subquery()
    invoice_summary = sales_order_invoice_summary_subquery()
    computed_total = db.func.coalesce(item_totals.c.item_total, SalesOrder.total_amount, 0)
    amount_paid = db.func.coalesce(invoice_summary.c.invoice_amount_paid, 0)
    query = (
        db.session.query(
            SalesOrder.id.label('id'),
            SalesOrder.so_number.label('so_number'),
            SalesOrder.client_id.label('client_id'),
            SalesOrder.company_name.label('company_name'),
            SalesOrder.official_client_name.label('official_client_name'),
            SalesOrder.original_entered_client_name.label('original_entered_client_name'),
            SalesOrder.store_name.label('store_name'),
            SalesOrder.store_branch.label('store_branch'),
            SalesOrder.order_date.label('order_date'),
            SalesOrder.sales_staff.label('sales_staff'),
            SalesOrder.terms.label('terms'),
            computed_total.label('total_amount'),
            SalesOrder.status.label('status'),
            SalesOrder.created_at.label('created_at'),
            Client.client_name.label('client_name'),
            db.func.coalesce(item_totals.c.item_count, 0).label('item_count'),
            db.func.coalesce(invoice_summary.c.invoice_count, 0).label('invoice_count'),
            db.func.coalesce(invoice_summary.c.invoice_amount_paid, 0).label('invoice_amount_paid'),
            db.func.coalesce(invoice_summary.c.invoice_balance, 0).label('invoice_balance'),
            invoice_summary.c.last_invoice_date.label('last_invoice_date'),
        )
        .select_from(SalesOrder)
        .join(Client, SalesOrder.client_id == Client.id)
        .outerjoin(item_totals, SalesOrder.id == item_totals.c.sales_order_id)
        .outerjoin(invoice_summary, SalesOrder.id == invoice_summary.c.sales_order_id)
    )
    filters = []
    if statuses:
        filters.append(SalesOrder.status.in_(statuses))
    if outstanding_only:
        filters.append(computed_total > amount_paid)
    if filters:
        query = query.filter(or_(*filters))
    return query

def sales_order_row_payload(row):
    company_name = row.company_name or row.client_name or ''
    total_amount = float(row.total_amount or 0)
    amount_paid = float(row.invoice_amount_paid or 0)
    current_balance = max(total_amount - amount_paid, 0)
    return {
        'id': row.id,
        'so_number': row.so_number,
        'client_id': row.client_id,
        'company_name': company_name,
        'client_name': row.client_name,
        'official_client_name': row.official_client_name,
        'original_entered_client_name': row.original_entered_client_name,
        'store_name': row.store_name or company_name,
        'store_branch': row.store_branch or DEFAULT_STORE_BRANCH,
        'order_date': row.order_date.isoformat() if row.order_date else None,
        'sales_staff': row.sales_staff,
        'terms': row.terms,
        'total_amount': total_amount,
        'status': row.status,
        'item_count': int(row.item_count or 0),
        'invoice_count': int(row.invoice_count or 0),
        'invoice_amount_paid': amount_paid,
        'invoice_balance': current_balance,
        'current_balance': current_balance,
        'last_invoice_date': row.last_invoice_date.isoformat() if row.last_invoice_date else None,
        'created_at': row.created_at.isoformat() if row.created_at else None,
    }

def resolve_uploaded_invoice_client(uploaded_client_name, registry=None):
    candidate = clean_text(
        uploaded_client_name,
        keep_period=True,
        keep_ampersand=True
    ).upper()
    if not candidate:
        return None
    registry = registry or build_client_registry()
    exact_entry = registry['lookup'].get(normalize_client_match_key(candidate))
    if exact_entry:
        return db.session.get(Client, exact_entry['client_id'])
    fuzzy_match = find_client_match(candidate, registry)
    if (
        fuzzy_match
        and float(fuzzy_match.get('match_percent') or 0) >= CLIENT_REVIEW_MATCH_PERCENT
        and not is_client_fuzzy_exception(candidate, fuzzy_match.get('client_name'))
    ):
        return db.session.get(Client, fuzzy_match['client_id'])
    return None

def match_sales_order_for_uploaded_invoice(uploaded_client_name, so_number=None, registry=None):
    normalized_so_number = clean_code(so_number)
    if normalized_so_number:
        exact_order = SalesOrder.query.filter(
            func.lower(SalesOrder.so_number) == normalized_so_number.lower()
        ).first()
        if exact_order:
            return exact_order

    client = resolve_uploaded_invoice_client(uploaded_client_name, registry)
    if not client:
        return None

    outstanding_orders = []
    orders = (
        SalesOrder.query
        .options(
            selectinload(SalesOrder.client),
            selectinload(SalesOrder.items),
            selectinload(SalesOrder.invoices),
        )
        .filter(SalesOrder.client_id == client.id)
        .order_by(SalesOrder.order_date.desc(), SalesOrder.id.desc())
        .all()
    )
    for order in orders:
        paid = sum(float(invoice.amount_paid or 0) for invoice in order.invoices)
        if sales_order_total(order) - paid > MONEY_TOLERANCE:
            outstanding_orders.append(order)
    return outstanding_orders[0] if len(outstanding_orders) == 1 else None


def sales_order_admin_payload(order):
    line_total = sum(float(item.total or 0) for item in getattr(order, 'items', []) or [])
    invoices = getattr(order, 'invoices', []) or []
    amount_paid = sum(float(invoice.amount_paid or 0) for invoice in invoices)
    total_amount = line_total if line_total else float(order.total_amount or 0)
    return {
        'id': order.id,
        'so_number': order.so_number,
        'client_id': order.client_id,
        'company_name': order.company_name or (order.client.client_name if order.client else ''),
        'official_client_name': order.official_client_name,
        'original_entered_client_name': order.original_entered_client_name,
        'store_name': order.store_name,
        'store_branch': order.store_branch,
        'order_date': order.order_date.isoformat() if order.order_date else None,
        'sales_staff': order.sales_staff,
        'total_amount': total_amount,
        'status': order.status,
        'invoice_count': len(invoices),
        'invoice_amount_paid': amount_paid,
        'current_balance': max(total_amount - amount_paid, 0),
    }


def admin_client_list_payload():
    clients = (
        Client.query
        .options(
            selectinload(Client.aliases),
            selectinload(Client.sales_orders).selectinload(SalesOrder.items),
            selectinload(Client.sales_orders).selectinload(SalesOrder.invoices),
        )
        .order_by(Client.client_name.asc())
        .all()
    )
    rows = []
    for client in clients:
        orders = sorted(client.sales_orders, key=lambda item: item.order_date or date.min, reverse=True)
        stores = {}
        for order in orders:
            store_key = (
                (order.store_name or '').strip().upper(),
                (order.store_branch or '').strip().upper(),
            )
            if store_key not in stores:
                stores[store_key] = {
                    'store_name': order.store_name or '',
                    'store_branch': order.store_branch or '',
                    'sales_order_count': 0,
                    'total_amount': 0.0,
                }
            stores[store_key]['sales_order_count'] += 1
            stores[store_key]['total_amount'] += float(order.total_amount or 0)

        rows.append({
            'id': client.id,
            'client_name': client.client_name,
            'contact_info': client.contact_info,
            'status': client.status or 'ACTIVE',
            'total_revenue': float(client.total_revenue or 0),
            'total_paid': float(client.total_paid or 0),
            'total_balance': float(client.total_balance or 0),
            'balance_status': client.balance_status or 'Settled',
            'aliases': [
                alias.alias_name
                for alias in client.aliases
                if alias.status == 'ACTIVE'
            ],
            'sales_order_count': len(orders),
            'store_count': len(stores),
            'stores': sorted(stores.values(), key=lambda item: (item['store_name'], item['store_branch'])),
            'sales_orders': [sales_order_admin_payload(order) for order in orders],
        })
    return rows


def resolve_existing_client_for_summary(name, registry=None):
    cleaned_name = clean_text(name, keep_period=True, keep_ampersand=True).upper()
    if not cleaned_name:
        return None
    registry = registry or build_client_registry()
    exact_entry = registry['lookup'].get(normalize_client_match_key(cleaned_name))
    return db.session.get(Client, exact_entry['client_id']) if exact_entry else None

def refresh_client_financials(client=None):
    registry = build_client_registry()
    clients = [client] if client else Client.query.all()
    financials = {
        item.id: {
            'sales_revenue': 0.0,
            'historical_revenue': 0.0,
            'paid': 0.0,
            'last_invoice_date': None,
            'last_payment_date': None,
        }
        for item in clients
        if item
    }

    for sales_order in SalesOrder.query.options(selectinload(SalesOrder.items)).all():
        if sales_order.client_id in financials:
            line_total = sum(float(item.total or 0) for item in sales_order.items)
            financials[sales_order.client_id]['sales_revenue'] += line_total if line_total else float(sales_order.total_amount or 0)

    linked_invoices = (
        Invoice.query.options(selectinload(Invoice.collection_receipts))
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id)
        .all()
    )
    for invoice in linked_invoices:
        client_id = invoice.sales_order.client_id if invoice.sales_order else None
        if client_id not in financials:
            continue
        financials[client_id]['paid'] += float(invoice.amount_paid or 0)
        if invoice.invoice_date:
            current_last = financials[client_id]['last_invoice_date']
            if current_last is None or invoice.invoice_date > current_last:
                financials[client_id]['last_invoice_date'] = invoice.invoice_date
            if (invoice.amount_paid or 0) > 0:
                payment_date = max(
                    (receipt.receipt_date for receipt in invoice.collection_receipts if receipt.receipt_date),
                    default=invoice.invoice_date,
                )
                current_payment_last = financials[client_id]['last_payment_date']
                if payment_date and (current_payment_last is None or payment_date > current_payment_last):
                    financials[client_id]['last_payment_date'] = payment_date

    admin_invoices = (
        Invoice.query.options(selectinload(Invoice.collection_receipts))
        .filter(Invoice.sales_order_id.is_(None))
        .filter(Invoice.uploaded_client_name.isnot(None))
        .all()
    )
    for invoice in admin_invoices:
        matched_client = resolve_existing_client_for_summary(invoice.uploaded_client_name, registry)
        if not matched_client or matched_client.id not in financials:
            continue
        financials[matched_client.id]['paid'] += float(invoice.amount_paid or 0)
        if invoice.invoice_date:
            current_last = financials[matched_client.id]['last_invoice_date']
            if current_last is None or invoice.invoice_date > current_last:
                financials[matched_client.id]['last_invoice_date'] = invoice.invoice_date
            if (invoice.amount_paid or 0) > 0:
                payment_date = max(
                    (receipt.receipt_date for receipt in invoice.collection_receipts if receipt.receipt_date),
                    default=invoice.invoice_date,
                )
                current_payment_last = financials[matched_client.id]['last_payment_date']
                if payment_date and (current_payment_last is None or payment_date > current_payment_last):
                    financials[matched_client.id]['last_payment_date'] = payment_date

    for row in AnalyticsData.query.filter_by(source_type='HISTORICAL_UPLOAD', flow_direction='INFLOW').all():
        matched_client = resolve_existing_client_for_summary(row.party_name, registry)
        if matched_client and matched_client.id in financials:
            financials[matched_client.id]['historical_revenue'] += float(row.amount or 0)

    now = datetime.now(UTC)
    for item in clients:
        if not item:
            continue
        totals = financials.get(item.id, {})
        sales_revenue = totals.get('sales_revenue', 0.0)
        historical_revenue = totals.get('historical_revenue', 0.0)
        revenue = sales_revenue if sales_revenue > 0 else historical_revenue
        paid = totals.get('paid', 0.0)
        balance = max(revenue - paid, 0)
        item.total_revenue = round(revenue, 2)
        item.total_paid = round(paid, 2)
        item.total_balance = round(balance, 2)
        item.balance_status = 'Settled' if balance <= 0.01 else 'Unsettled Balance'
        item.last_invoice_date = totals.get('last_invoice_date')
        item.last_payment_date = totals.get('last_payment_date')
        item.financials_updated_at = now

def analytics_party_name_for_invoice(invoice):
    if invoice.sales_order and invoice.sales_order.client:
        return invoice.sales_order.client.client_name
    return invoice.uploaded_client_name or 'Admin Upload'

def purchase_order_source_id(purchase_order):
    return purchase_order.po_number or purchase_order.check_voucher_number or f"PO-{purchase_order.id}"

def sales_order_description(sales_order):
    item_names = [item.particular for item in sales_order.items if item.particular]
    if item_names:
        return ', '.join(item_names[:5])
    return sales_order.notes or 'Sales order'

def report_available_years():
    current_year = datetime.now().year
    available_year_rows = (
        db.session.query(db_year(SalesOrder.order_date).label('year'))
        .filter(SalesOrder.order_date.isnot(None))
        .union(
            db.session.query(db_year(Invoice.invoice_date).label('year'))
            .filter(Invoice.invoice_date.isnot(None)),
            db.session.query(db_year(CollectionReceipt.receipt_date).label('year'))
            .filter(CollectionReceipt.receipt_date.isnot(None)),
            db.session.query(db_year(PurchaseOrder.date).label('year'))
            .filter(PurchaseOrder.date.isnot(None))
        )
        .all()
    )
    return sorted(
        {current_year, *(int(row.year) for row in available_year_rows if row.year)},
        reverse=True
    )

def parse_report_date_filter():
    available_years = report_available_years()
    selected_year = request.args.get('year', default=available_years[0], type=int)
    if selected_year not in available_years:
        selected_year = available_years[0]

    period = request.args.get('period', default='year', type=str)
    if period not in ('year', 'quarter', 'month'):
        period = 'year'

    quarter = request.args.get('quarter', default=1, type=int)
    if quarter not in (1, 2, 3, 4):
        quarter = 1

    month = request.args.get('month', default=1, type=int)
    if month < 1 or month > 12:
        month = 1

    if period == 'quarter':
        start_month = ((quarter - 1) * 3) + 1
        start_date = date(selected_year, start_month, 1)
        end_date = date(selected_year + 1, 1, 1) if quarter == 4 else date(selected_year, start_month + 3, 1)
        label = f'Q{quarter} {selected_year}'
    elif period == 'month':
        start_date = date(selected_year, month, 1)
        end_date = date(selected_year + 1, 1, 1) if month == 12 else date(selected_year, month + 1, 1)
        label = start_date.strftime('%B %Y')
    else:
        start_date = date(selected_year, 1, 1)
        end_date = date(selected_year + 1, 1, 1)
        label = str(selected_year)

    return {
        'available_years': available_years,
        'selected_year': selected_year,
        'period': period,
        'quarter': quarter,
        'month': month,
        'start_date': start_date,
        'end_date': end_date,
        'label': label,
    }

def previous_year_comparison_filter(filters):
    """Return the same calendar period one year earlier."""
    previous_year = filters['selected_year'] - 1
    return {
        **filters,
        'selected_year': previous_year,
        'start_date': filters['start_date'].replace(year=filters['start_date'].year - 1),
        'end_date': filters['end_date'].replace(year=filters['end_date'].year - 1),
        'label': filters['label'].replace(str(filters['selected_year']), str(previous_year)),
    }

def date_range_filter(query, column, filters):
    return query.filter(column >= filters['start_date'], column < filters['end_date'])

def revenue_report_rows(filters=None):
    query = (
        db.session.query(CollectionReceipt, Invoice, SalesOrder, Client)
        .select_from(CollectionReceipt)
        .join(Invoice, CollectionReceipt.invoice_id == Invoice.id)
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True)
        .join(Client, SalesOrder.client_id == Client.id, isouter=True)
    )
    if filters:
        query = date_range_filter(query, CollectionReceipt.receipt_date, filters)
    rows = query.order_by(
        CollectionReceipt.receipt_date.asc(),
        Invoice.id.asc(),
        CollectionReceipt.id.asc(),
    ).all()
    result = [
        {
            'invoice_date': receipt.receipt_date.isoformat() if receipt.receipt_date else None,
            'invoice_number': clean_code(invoice.invoice_number).upper(),
            'so_number': order.so_number if order else '',
            'client_name': client.client_name if client else (invoice.uploaded_client_name or 'Admin Upload'),
            'invoice_type': canonical_invoice_type(invoice.invoice_number, invoice.invoice_type),
            'payment_type': receipt.payment_type,
            'cr_number': receipt.cr_number,
            'total_amount': float(invoice.total_amount or 0),
            'amount_paid': float(receipt.collected_total or 0),
            'balance': float(invoice.balance or 0),
            'status': invoice.status,
        }
        for receipt, invoice, order, client in rows
    ]
    legacy_query = (
        db.session.query(Invoice, SalesOrder, Client)
        .select_from(Invoice)
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True)
        .join(Client, SalesOrder.client_id == Client.id, isouter=True)
        .filter(Invoice.amount_paid > 0, ~Invoice.collection_receipts.any())
    )
    if filters:
        legacy_query = date_range_filter(legacy_query, Invoice.invoice_date, filters)
    result.extend({
        'invoice_date': invoice.invoice_date.isoformat() if invoice.invoice_date else None,
        'invoice_number': clean_code(invoice.invoice_number).upper(),
        'so_number': order.so_number if order else '',
        'client_name': client.client_name if client else (invoice.uploaded_client_name or 'Admin Upload'),
        'invoice_type': canonical_invoice_type(invoice.invoice_number, invoice.invoice_type),
        'payment_type': invoice.payment_type,
        'cr_number': invoice.cr_number,
        'total_amount': float(invoice.total_amount or 0),
        'amount_paid': float(invoice.amount_paid or 0),
        'balance': float(invoice.balance or 0),
        'status': invoice.status,
    } for invoice, order, client in legacy_query.all())
    return sorted(result, key=lambda item: (item['invoice_date'] or '', item['invoice_number']))

def sales_report_itemized_rows(filters=None):
    query = (
        db.session.query(SalesOrder, SalesOrderItem, Client)
        .join(SalesOrderItem, SalesOrder.id == SalesOrderItem.sales_order_id)
        .join(Client, SalesOrder.client_id == Client.id)
    )
    if filters:
        query = date_range_filter(query, SalesOrder.order_date, filters)
    rows = query.order_by(SalesOrder.order_date.asc(), SalesOrder.so_number.asc(), SalesOrderItem.id.asc()).all()
    return [
        {
            'date': order.order_date.isoformat() if order.order_date else None,
            'so_number': order.so_number,
            'company_name': order.company_name or client.client_name,
            'client_name': client.client_name,
            'store_name': order.store_name,
            'store_branch': order.store_branch,
            'sales_staff': order.sales_staff,
            'particular': item.particular,
            'quantity': int(item.quantity or 0),
            'unit_cost': float(item.unit_cost or 0),
            'selling_price': float(item.selling_price or 0),
            'total': float(item.total or 0),
            'status': order.status,
        }
        for order, item, client in rows
    ]

def expense_report_rows(filters=None):
    query = PurchaseOrder.query
    if filters:
        query = date_range_filter(query, PurchaseOrder.date, filters)
    return [
        {
            'date': po.date.isoformat() if po.date else None,
            'check_voucher_number': po.check_voucher_number,
            'check_number': po.check_number,
            'check_date': po.check_date.isoformat() if po.check_date else None,
            'po_number': po.po_number,
            'supplier_payee': po.supplier_payee,
            'particulars': po.particulars,
            'category': po.category,
            'cash_amount': float(po.cash_amount or 0),
            'net_balance': float(po.net_balance or 0),
            'status': po.status,
        }
        for po in query.order_by(PurchaseOrder.date.asc(), PurchaseOrder.id.asc()).all()
    ]

def report_historical_transaction_rows(filters=None):
    rows = []
    invoice_query = Invoice.query.options(selectinload(Invoice.sales_order).selectinload(SalesOrder.client))
    purchase_order_query = PurchaseOrder.query
    if filters:
        invoice_query = date_range_filter(invoice_query, Invoice.invoice_date, filters)
        purchase_order_query = date_range_filter(purchase_order_query, PurchaseOrder.date, filters)
    for invoice in invoice_query.order_by(Invoice.invoice_date.asc(), Invoice.id.asc()).all():
        party_name = analytics_party_name_for_invoice(invoice)
        if float(invoice.amount_paid or 0) > 0:
            rows.append({
                'source_type': 'INVOICE',
                'source_id': invoice.invoice_number,
                'transaction_date': invoice.invoice_date.isoformat() if invoice.invoice_date else None,
                'financial_stage': 'PAID',
                'flow_direction': 'INFLOW',
                'flow_status': 'ACTUAL',
                'party_name': party_name,
                'party_role': 'CUSTOMER',
                'amount': float(invoice.amount_paid or 0),
                'balance_amount': float(invoice.balance or 0),
                'category': 'COLLECTION',
                'status': invoice.status,
                'description': invoice.summary or invoice.admin_upload_note or 'Payment received from invoice',
            })
    for purchase_order in purchase_order_query.order_by(PurchaseOrder.date.asc(), PurchaseOrder.id.asc()).all():
        source_id = purchase_order_source_id(purchase_order)
        rows.append({
            'source_type': 'PURCHASE_ORDER',
            'source_id': source_id,
            'transaction_date': purchase_order.date.isoformat() if purchase_order.date else None,
            'financial_stage': 'PAID_OUT',
            'flow_direction': 'OUTFLOW',
            'flow_status': 'ACTUAL',
            'party_name': purchase_order.supplier_payee,
            'party_role': 'SUPPLIER',
            'amount': float(purchase_order.cash_amount or 0),
            'balance_amount': float(purchase_order.net_balance or 0),
            'category': 'EXPENSE_PAYMENT',
            'status': purchase_order.status,
            'description': purchase_order.particulars or 'Payment made to supplier',
        })
    return sorted(
        rows,
        key=lambda row: (row.get('transaction_date') or '', row.get('source_type') or '', row.get('source_id') or ''),
        reverse=False
    )

def csv_response(filename, rows, fieldnames):
    text_stream = StringIO()
    writer = csv.DictWriter(text_stream, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({field: row.get(field, '') for field in fieldnames})
    log_audit('EXPORT_REPORT_CSV', 'reports', filename, None, {'rows': len(rows)})
    db.session.commit()
    return Response(
        text_stream.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )

def rebuild_analytics_data():
    preserved_historical_rows = [
        {
            'source_type': row.source_type,
            'source_id': row.source_id,
            'transaction_date': row.transaction_date,
            'financial_stage': row.financial_stage,
            'flow_direction': row.flow_direction,
            'flow_status': row.flow_status,
            'party_name': row.party_name,
            'party_role': row.party_role,
            'amount': row.amount,
            'balance_amount': row.balance_amount,
            'category': row.category,
            'status': row.status,
            'description': row.description,
            'created_at': row.created_at,
        }
        for row in AnalyticsData.query.filter_by(source_type='HISTORICAL_UPLOAD').all()
    ]
    AnalyticsData.query.delete()
    now = datetime.now(UTC)

    for sales_order in SalesOrder.query.options(selectinload(SalesOrder.client), selectinload(SalesOrder.items)).all():
        db.session.add(AnalyticsData(
            source_type='SALES_ORDER',
            source_id=sales_order.so_number or f"SO-{sales_order.id}",
            transaction_date=sales_order.order_date,
            financial_stage='ORDERED',
            flow_direction='INFLOW',
            flow_status='EXPECTED',
            party_name=sales_order.client.client_name if sales_order.client else (sales_order.company_name or 'Unknown Customer'),
            party_role='CUSTOMER',
            amount=float(sales_order.total_amount or 0),
            balance_amount=float(sales_order.total_amount or 0),
            category='SALES',
            status=sales_order.status,
            description=sales_order_description(sales_order),
            created_at=now,
        ))

    for invoice in Invoice.query.options(selectinload(Invoice.sales_order).selectinload(SalesOrder.client)).all():
        party_name = analytics_party_name_for_invoice(invoice)
        invoice_balance = float(invoice.balance or 0)
        invoice_total = float(invoice.total_amount if invoice.total_amount is not None else invoice.amount_paid or 0)
        db.session.add(AnalyticsData(
            source_type='INVOICE',
            source_id=invoice.invoice_number,
            transaction_date=invoice.invoice_date,
            financial_stage='INVOICED',
            flow_direction='INFLOW',
            flow_status='RECEIVABLE',
            party_name=party_name,
            party_role='CUSTOMER',
            amount=invoice_total,
            balance_amount=invoice_balance,
            category='BILLING',
            status=invoice.status,
            description=invoice.summary or invoice.admin_upload_note or 'Invoice issued',
            created_at=now,
        ))
        if float(invoice.amount_paid or 0) > 0:
            db.session.add(AnalyticsData(
                source_type='INVOICE',
                source_id=invoice.invoice_number,
                transaction_date=invoice.invoice_date,
                financial_stage='PAID',
                flow_direction='INFLOW',
                flow_status='ACTUAL',
                party_name=party_name,
                party_role='CUSTOMER',
                amount=float(invoice.amount_paid or 0),
                balance_amount=invoice_balance,
                category='COLLECTION',
                status=invoice.status,
                description='Payment received from invoice',
                created_at=now,
            ))

    for row_data in preserved_historical_rows:
        db.session.add(AnalyticsData(**row_data))

    for purchase_order in PurchaseOrder.query.all():
        source_id = purchase_order_source_id(purchase_order)
        db.session.add(AnalyticsData(
            source_type='PURCHASE_ORDER',
            source_id=source_id,
            transaction_date=purchase_order.date,
            financial_stage='PURCHASED',
            flow_direction='OUTFLOW',
            flow_status='PAYABLE',
            party_name=purchase_order.supplier_payee,
            party_role='SUPPLIER',
            amount=float(purchase_order.cash_amount or 0),
            balance_amount=float(purchase_order.net_balance or 0),
            category='PURCHASE',
            status=purchase_order.status,
            description=purchase_order.particulars,
            created_at=now,
        ))
        if float(purchase_order.cash_amount or 0) > 0:
            db.session.add(AnalyticsData(
                source_type='PURCHASE_ORDER',
                source_id=source_id,
                transaction_date=purchase_order.date,
                financial_stage='PAID_OUT',
                flow_direction='OUTFLOW',
                flow_status='ACTUAL',
                party_name=purchase_order.supplier_payee,
                party_role='SUPPLIER',
                amount=float(purchase_order.cash_amount or 0),
                balance_amount=float(purchase_order.net_balance or 0),
                category='EXPENSE_PAYMENT',
                status=purchase_order.status,
                description='Payment made to supplier',
                created_at=now,
            ))

def build_client_review_queue(client_names):
    registry = build_client_registry()
    seen = set()
    review_items = []
    matched = []
    for idx, raw_name in enumerate(client_names, start=1):
        cleaned = clean_text(raw_name, keep_period=True, keep_ampersand=True).upper() or 'UNMAPPED CLIENT'
        key = normalize_client_match_key(cleaned)
        if not key or key in seen:
            continue
        seen.add(key)
        resolution = resolve_client_name(cleaned, create_client=False, registry=registry)
        if resolution['status'] == 'resolved':
            matched.append({
                'resolution_key': key,
                'uploaded_name': cleaned,
                'official_client_name': resolution['client_name'],
                'client_id': resolution['client'].id if resolution.get('client') else None,
                'match_percent': resolution.get('match_percent', 100),
                'match_source': resolution.get('match_source', 'official'),
            })
            continue
        item = client_resolution_public(resolution, idx)
        item['uploaded_name'] = cleaned
        if resolution['status'] == 'needs_choice':
            item['review_status'] = 'high_confidence' if (resolution.get('match_percent') or 0) >= CLIENT_LIKELY_TYPO_PERCENT else 'review_required'
        else:
            item['review_status'] = 'new_candidate'
            item['match_percent'] = 0
        review_items.append(item)
    return {
        'matched': matched,
        'review_items': review_items,
        'total_unique_clients': len(seen),
    }

def parse_amount(value):
    if value is None or value == '':
        return 0.0
    cleaned = re.sub(r'[^0-9.\-]', '', str(value))
    try:
        return float(cleaned) if cleaned not in ('', '-', '.') else 0.0
    except ValueError:
        return 0.0

MONEY_TOLERANCE = 0.01

def parse_nonnegative_amount(value, field_label):
    if value is None or value == '':
        return 0.0
    cleaned = re.sub(r'[^0-9.\-]', '', str(value).replace(',', ''))
    try:
        amount = float(Decimal(cleaned))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{field_label} must be a valid amount.')
    if amount < 0:
        raise ValueError(f'{field_label} cannot be negative.')
    return round(amount, 2)

def payment_state(total_amount, amount_paid):
    total = max(float(total_amount or 0), 0)
    paid = max(float(amount_paid or 0), 0)
    balance = max(round(total - paid, 2), 0)
    if paid <= MONEY_TOLERANCE:
        status = 'UNPAID'
    elif balance <= MONEY_TOLERANCE:
        status = 'PAID'
        balance = 0.0
    else:
        status = 'PARTIAL'
    return status, balance

def collected_payment_amount(cr_number, payment_amount, tax_amount_paid, is_2307_checked):
    payment = parse_nonnegative_amount(payment_amount, 'Payment amount')
    tax = parse_nonnegative_amount(tax_amount_paid, 'Tax amount paid')
    collected = round(payment + (tax if is_2307_checked else 0), 2)
    if collected > MONEY_TOLERANCE and not (cr_number or '').strip():
        raise ValueError('CR number is required when recording a payment.')
    return payment, tax, collected

def normalize_cr_number(value):
    return clean_code(value).upper()

def collection_receipt_payload(receipt):
    return {
        'id': receipt.id,
        'invoice_id': receipt.invoice_id,
        'receipt_date': receipt.receipt_date.isoformat() if receipt.receipt_date else None,
        'cr_number': receipt.cr_number,
        'payment_type': receipt.payment_type,
        'payment_amount': float(receipt.payment_amount or 0),
        'tax_amount_paid': float(receipt.tax_amount_paid or 0),
        'is_2307_checked': bool(receipt.is_2307_checked),
        'collected_total': float(receipt.collected_total or 0),
        'recorded_by': receipt.recorded_by or 'system',
        'created_at': receipt.created_at.isoformat() if receipt.created_at else None,
    }

def receipt_total_for_invoice(invoice):
    if invoice.collection_receipts:
        return round(sum(float(item.collected_total or 0) for item in invoice.collection_receipts), 2)
    return round(float(invoice.amount_paid or 0), 2)

def ensure_invoice_legacy_receipt(invoice):
    if invoice.collection_receipts or float(invoice.amount_paid or 0) <= MONEY_TOLERANCE:
        return None
    legacy_cr = clean_code(invoice.cr_number) or f'LEGACY-{invoice.id}'
    legacy_receipt = CollectionReceipt(
        invoice=invoice,
        receipt_date=invoice.invoice_date or date.today(),
        cr_number=legacy_cr,
        normalized_cr_number=normalize_cr_number(legacy_cr),
        payment_type=(
            'FULL'
            if str(invoice.payment_type or '').upper() == 'FULL'
            or float(invoice.balance or 0) <= MONEY_TOLERANCE
            else 'DOWNPAYMENT'
        ),
        payment_amount=(
            float(invoice.payment_amount or 0)
            if float(invoice.payment_amount or 0) > 0
            else float(invoice.amount_paid or 0)
        ),
        tax_amount_paid=float(invoice.tax_amount_paid or 0),
        is_2307_checked=bool(invoice.is_2307_checked),
        collected_total=float(invoice.amount_paid or 0),
        recorded_by='legacy migration',
    )
    db.session.add(legacy_receipt)
    db.session.flush()
    return legacy_receipt

def synchronize_invoice_receipt_state(invoice):
    amount_paid = receipt_total_for_invoice(invoice)
    invoice.amount_paid = amount_paid
    invoice.status, invoice.balance = payment_state(invoice.total_amount, amount_paid)
    return {
        'amount_paid': amount_paid,
        'balance': invoice.balance,
        'invoice_status': invoice.status,
    }

def append_collection_receipt(
    invoice,
    data,
    *,
    allow_legacy=False,
    recorded_by=None,
    existing_paid=None,
    prevalidated=False,
):
    if not prevalidated:
        ensure_invoice_legacy_receipt(invoice)
    receipt_date = parse_date_value(data.get('receipt_date'), default_today=False)
    if not receipt_date:
        raise ValueError('Collection Receipt date is required.')

    raw_cr_number = clean_code(data.get('cr_number'))
    if not raw_cr_number and not allow_legacy:
        raise ValueError('CR number is required when recording a payment.')
    cr_number = raw_cr_number or f'LEGACY-{invoice.id}'
    normalized_cr_number = normalize_cr_number(cr_number)
    if not prevalidated:
        duplicate = CollectionReceipt.query.filter_by(
            invoice_id=invoice.id,
            normalized_cr_number=normalized_cr_number,
        ).first()
        if duplicate:
            raise ValueError(f'CR number {cr_number} is already recorded for this invoice.')

    payment_type = clean_code(data.get('payment_type')).upper()
    if allow_legacy and payment_type not in {'DOWNPAYMENT', 'FULL'}:
        payment_type = 'FULL' if float(data.get('collected_total') or 0) >= float(invoice.total_amount or 0) else 'DOWNPAYMENT'
    if payment_type not in {'DOWNPAYMENT', 'FULL'}:
        raise ValueError('Payment type must be DOWNPAYMENT or FULL.')

    is_2307_checked = bool(data.get('is_2307_checked'))
    payment_amount, tax_amount_paid, collected_total = collected_payment_amount(
        cr_number,
        data.get('payment_amount'),
        data.get('tax_amount_paid'),
        is_2307_checked,
    )
    if collected_total <= MONEY_TOLERANCE:
        raise ValueError('Collection Receipt amount must be greater than zero.')

    current_paid = (
        float(existing_paid)
        if existing_paid is not None
        else receipt_total_for_invoice(invoice)
    )
    remaining = max(float(invoice.total_amount or 0) - current_paid, 0)
    if collected_total > remaining + MONEY_TOLERANCE:
        raise ValueError(f'Payment exceeds the remaining invoice balance of {remaining:.2f}.')
    if payment_type == 'FULL' and abs(collected_total - remaining) > MONEY_TOLERANCE:
        raise ValueError(f'Full Payment must exactly settle the remaining invoice balance of {remaining:.2f}.')

    receipt = CollectionReceipt(
        invoice=invoice,
        receipt_date=receipt_date,
        cr_number=cr_number,
        normalized_cr_number=normalized_cr_number,
        payment_type=payment_type,
        payment_amount=payment_amount,
        tax_amount_paid=tax_amount_paid,
        is_2307_checked=is_2307_checked,
        collected_total=collected_total,
        created_by_user_id=session.get('user_id') if has_request_context() else None,
        recorded_by=recorded_by or (session.get('username') if has_request_context() else 'system') or 'system',
    )
    db.session.add(receipt)
    if not prevalidated:
        db.session.flush()
    invoice.amount_paid = round(current_paid + collected_total, 2)
    invoice.status, invoice.balance = payment_state(invoice.total_amount, invoice.amount_paid)
    return receipt

def sales_order_total(sales_order):
    line_total = sum(float(item.total or 0) for item in getattr(sales_order, 'items', []) or [])
    return round(line_total if line_total > 0 else float(sales_order.total_amount or 0), 2)

def synchronize_sales_order_payment_state(sales_order):
    total = sales_order_total(sales_order)
    for invoice in sales_order.invoices:
        synchronize_invoice_receipt_state(invoice)
    paid = round(sum(float(invoice.amount_paid or 0) for invoice in sales_order.invoices), 2)
    if paid > total + MONEY_TOLERANCE:
        raise ValueError(f'Payment exceeds the Sales Order balance by {paid - total:.2f}.')
    status, balance = payment_state(total, paid)
    sales_order.total_amount = total
    sales_order.status = 'COMPLETED' if status == 'PAID' else status
    for invoice in sales_order.invoices:
        invoice.total_amount = total
        invoice.balance = balance
        invoice.status = status
    return {
        'total_amount': total,
        'amount_paid': paid,
        'balance': balance,
        'invoice_status': status,
        'sales_order_status': sales_order.status,
    }

def parse_date_value(value, default_today=True, dayfirst=False):
    if not value:
        return datetime.now().date() if default_today else None
    if hasattr(value, 'date'):
        return value.date()
    text_value = str(value).strip()
    if not text_value:
        return datetime.now().date() if default_today else None
    preferred_formats = ['%d/%m/%Y', '%Y-%m-%d', '%m/%d/%Y'] if dayfirst else ['%Y-%m-%d', '%m/%d/%Y', '%d/%m/%Y']
    for date_format in preferred_formats:
        try:
            return datetime.strptime(text_value, date_format).date()
        except ValueError:
            pass
    parsed = pd.to_datetime(value, errors='coerce', dayfirst=dayfirst)
    if not pd.isna(parsed):
        return parsed.date()
    return datetime.now().date() if default_today else None

FUTURE_DATE_WARNING_MESSAGE = 'Possible date error detected. The selected date is in the future. Please review before continuing.'

def future_date_warnings(date_fields):
    warnings = []
    today = datetime.now().date()
    for field_label, value in date_fields.items():
        parsed = value if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day') else parse_date_value(value, default_today=False)
        if parsed and parsed > today:
            warnings.append({
                'field': field_label,
                'message': FUTURE_DATE_WARNING_MESSAGE,
                'date': parsed.isoformat(),
            })
    return warnings

def json_success(payload=None, warnings=None):
    response = {'success': True}
    if payload:
        response.update(payload)
    if warnings:
        response['warnings'] = warnings
    return jsonify(response)

def format_upload_date_ddmmyyyy(value, field_label):
    parsed = parse_date_value(value, default_today=False, dayfirst=True)
    if not parsed:
        raise ValueError(f'{field_label} is required and must use DD/MM/YYYY format.')
    return parsed.strftime('%d/%m/%Y')

def read_admin_csv_upload(upload):
    encodings = ('utf-8-sig', 'utf-8', 'cp1252', 'latin-1')
    last_error = None
    for encoding in encodings:
        try:
            upload.stream.seek(0)
            return pd.read_csv(upload.stream, encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    filename = upload.filename or 'uploaded CSV'
    raise ValueError(f'Unable to decode {filename}. Tried CSV encodings: {", ".join(encodings)}.') from last_error

def normalize_upload_header(header):
    value = str(header or '').strip().lower()
    value = value.replace('#', ' number ')
    value = re.sub(r'[^a-z0-9]+', '_', value)
    return value.strip('_')

COMPILED_SALES_HEADERS = (
    'DATE',
    'SO NUMBER',
    'COMPANY NAME',
    'STORE NAME',
    'STORE BRANCH',
    'SALES STAFF',
    'PARTICULAR',
    'COST',
    'QUANTITY',
    'SELLING PRICE',
    'TOTAL REVENUE',
    'TOTAL COST',
)

def normalize_sales_order_number(value):
    text = clean_code(value).upper()
    numeric = re.sub(r'^SO[-\s]*', '', text)
    if numeric.isdigit():
        return f"SO-{int(numeric):03d}"
    return text

def sales_order_number_key(value):
    text = normalize_sales_order_number(value)
    numeric = re.sub(r'^SO[-\s]*', '', text)
    return str(int(numeric)) if numeric.isdigit() else normalize_client_match_key(text)

def normalized_sales_staff(value):
    return clean_text(value, keep_period=True).upper()

def compiled_sales_order_key(so_number, sales_staff):
    return f"{sales_order_number_key(so_number)}|{normalize_client_match_key(sales_staff)}"

def normalized_branch_key(value):
    text = clean_text(value, keep_period=True, keep_ampersand=True).upper().replace('&', ' AND ')
    return normalize_client_match_key(text)

def _optional_upload_amount(value):
    if value is None or str(value).strip() == '' or pd.isna(value):
        return None
    return parse_amount(value)

def _compiled_sales_row(raw_row, row_number):
    lower = {normalize_upload_header(key): value for key, value in raw_row.items()}
    quantity_raw = lower.get('quantity')
    quantity = None
    try:
        quantity_float = float(quantity_raw)
        quantity = int(quantity_float) if quantity_float.is_integer() else quantity_float
    except (TypeError, ValueError):
        quantity = None

    order_date = parse_date_value(lower.get('date'), default_today=False)
    unit_cost = _optional_upload_amount(lower.get('cost'))
    selling_price = _optional_upload_amount(lower.get('selling_price'))
    total_revenue = _optional_upload_amount(lower.get('total_revenue'))
    total_cost = _optional_upload_amount(lower.get('total_cost'))
    if total_revenue is None and quantity and selling_price is not None:
        total_revenue = round(float(quantity) * selling_price, 2)
    if total_cost is None and quantity and unit_cost is not None:
        total_cost = round(float(quantity) * unit_cost, 2)

    row = {
        'row_id': row_number,
        'source_row': row_number,
        'included': True,
        'order_date': order_date.isoformat() if order_date else None,
        'so_number': normalize_sales_order_number(lower.get('so_number')),
        'company_name': clean_text(lower.get('company_name'), keep_period=True, keep_ampersand=True).upper(),
        'store_name': clean_text(lower.get('store_name'), keep_period=True, keep_ampersand=True).upper(),
        'store_branch': clean_text(lower.get('store_branch'), keep_period=True, keep_ampersand=True).upper(),
        'sales_staff': normalized_sales_staff(lower.get('sales_staff')),
        'particular': clean_text(lower.get('particular'), keep_period=True, keep_ampersand=True).upper(),
        'unit_cost': unit_cost,
        'quantity': quantity,
        'selling_price': selling_price,
        'total_revenue': total_revenue,
        'total_cost': total_cost,
    }
    row['compound_key'] = compiled_sales_order_key(row['so_number'], row['sales_staff'])
    row['branch_key'] = normalized_branch_key(row['store_branch'])
    return row

def validate_compiled_sales_rows(rows):
    seen_lines = {}
    for row in rows:
        issues = []
        blocking = []
        if not row.get('order_date'):
            blocking.append('A valid Date is required.')
        for field, label in (
            ('so_number', 'SO Number'),
            ('company_name', 'Company Name'),
            ('store_name', 'Store Name'),
            ('store_branch', 'Store Branch'),
            ('sales_staff', 'Sales Staff'),
            ('particular', 'Particular'),
        ):
            if not str(row.get(field) or '').strip():
                blocking.append(f'{label} is required.')
        quantity = row.get('quantity')
        if not isinstance(quantity, int) or quantity <= 0:
            blocking.append('Quantity must be a positive whole number.')
        for field, label in (('unit_cost', 'Cost'), ('selling_price', 'Selling Price')):
            value = row.get(field)
            if value is None or float(value) < 0:
                blocking.append(f'{label} is required and cannot be negative.')
        if row.get('total_revenue') is None:
            blocking.append('Total Revenue is required or must be derivable.')
        if row.get('total_cost') is None:
            blocking.append('Total Cost is required or must be derivable.')
        if isinstance(quantity, int) and quantity > 0 and row.get('selling_price') is not None and row.get('total_revenue') is not None:
            computed = round(quantity * float(row['selling_price']), 2)
            if abs(computed - float(row['total_revenue'])) > 0.01:
                blocking.append(f'Total Revenue differs from Quantity × Selling Price ({computed:.2f}).')
        if isinstance(quantity, int) and quantity > 0 and row.get('unit_cost') is not None and row.get('total_cost') is not None:
            computed_cost = round(quantity * float(row['unit_cost']), 2)
            if abs(computed_cost - float(row['total_cost'])) > 0.01:
                blocking.append(f'Total Cost differs from Quantity × Cost ({computed_cost:.2f}).')

        duplicate_key = (
            row.get('compound_key'),
            row.get('branch_key'),
            normalize_client_match_key(row.get('particular')),
            row.get('quantity'),
            row.get('unit_cost'),
            row.get('selling_price'),
            row.get('total_revenue'),
        )
        previous = seen_lines.get(duplicate_key)
        if previous:
            issues.append(f'Possible duplicate of source row {previous}.')
        else:
            seen_lines[duplicate_key] = row.get('source_row')
        row['issues'] = issues + blocking
        row['blocking_issues'] = blocking
    return rows

def group_compiled_sales_rows(rows):
    grouped = {}
    for row in rows:
        if not row.get('included', True):
            continue
        group = grouped.setdefault(row['compound_key'], {
            'compound_key': row['compound_key'],
            'so_number': row['so_number'],
            'sales_staff': row['sales_staff'],
            'order_date': row['order_date'],
            'company_name': row['company_name'],
            'store_name': row['store_name'],
            'branches': {},
            'rows': [],
        })
        for field in ('order_date', 'company_name', 'store_name'):
            if group[field] != row[field]:
                raise ValueError(
                    f"Compound order {row['so_number']} / {row['sales_staff']} has conflicting {field.replace('_', ' ')} values."
                )
        group['branches'][row['branch_key']] = row['store_branch']
        group['rows'].append(row)
    return list(grouped.values())

def existing_compiled_sales_orders():
    existing = {}
    for order in SalesOrder.query.all():
        key = compiled_sales_order_key(order.so_number, order.sales_staff)
        existing.setdefault(key, order)
    return existing

def normalize_submitted_compiled_row(raw_row):
    row = {
        'row_id': raw_row.get('row_id') or raw_row.get('source_row'),
        'source_row': raw_row.get('source_row') or raw_row.get('row_id'),
        'included': bool(raw_row.get('included', True)),
        'order_date': parse_date_value(raw_row.get('order_date'), default_today=False),
        'so_number': normalize_sales_order_number(raw_row.get('so_number')),
        'company_name': clean_text(raw_row.get('company_name'), keep_period=True, keep_ampersand=True).upper(),
        'store_name': clean_text(raw_row.get('store_name'), keep_period=True, keep_ampersand=True).upper(),
        'store_branch': clean_text(raw_row.get('store_branch'), keep_period=True, keep_ampersand=True).upper(),
        'sales_staff': normalized_sales_staff(raw_row.get('sales_staff')),
        'particular': clean_text(raw_row.get('particular'), keep_period=True, keep_ampersand=True).upper(),
        'unit_cost': _optional_upload_amount(raw_row.get('unit_cost')),
        'selling_price': _optional_upload_amount(raw_row.get('selling_price')),
        'total_revenue': _optional_upload_amount(raw_row.get('total_revenue')),
        'total_cost': _optional_upload_amount(raw_row.get('total_cost')),
    }
    quantity_raw = raw_row.get('quantity')
    try:
        quantity_float = float(quantity_raw)
        row['quantity'] = int(quantity_float) if quantity_float.is_integer() else quantity_float
    except (TypeError, ValueError):
        row['quantity'] = None
    row['order_date'] = row['order_date'].isoformat() if row['order_date'] else None
    if row['total_revenue'] is None and isinstance(row['quantity'], int) and row['selling_price'] is not None:
        row['total_revenue'] = round(row['quantity'] * row['selling_price'], 2)
    if row['total_cost'] is None and isinstance(row['quantity'], int) and row['unit_cost'] is not None:
        row['total_cost'] = round(row['quantity'] * row['unit_cost'], 2)
    row['compound_key'] = compiled_sales_order_key(row['so_number'], row['sales_staff'])
    row['branch_key'] = normalized_branch_key(row['store_branch'])
    return row

PURCHASE_ORDER_DEBIT_COLUMNS = {
    'input_vat': 'Input VAT',
    'cost_of_goods_sold': 'Cost of Goods Sold',
    'software': 'Software',
    'rent_expense': 'Rent Expense',
    'cash_advance': 'Cash Advance',
    'government_contribution_loan': 'Government Contribution/Loan',
    'pldt': 'PLDT',
    'globe_smart_sun': 'Globe/Smart, Sun',
    'petty_cash': 'Petty Cash',
    'commission': 'Commission',
    'bdo_amortization': 'BDO Amortization',
    'dividends_payable': 'Dividends Payable',
    'meralco': 'Meralco',
    'support_allowance': 'Support Allowance',
    'fund_transfer': 'Fund Transfer',
    'various_expenses': 'Various Expenses',
}
PURCHASE_ORDER_DEBIT_TYPES = set(PURCHASE_ORDER_DEBIT_COLUMNS.values())

FIXED_PURCHASE_ORDER_DEBIT_TYPES = {
    'PLDT',
    'Globe/Smart, Sun',
    'Meralco',
    'Rent Expense',
}

def parse_optional_integer(value):
    if value is None or str(value).strip() == '':
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        raise ValueError(f'Invalid expense ID: {value}')
    if not parsed.is_integer() or parsed <= 0:
        raise ValueError(f'Invalid expense ID: {value}')
    return int(parsed)

def normalize_purchase_order_debits(lower):
    debits = []
    for column_name, debit_type in PURCHASE_ORDER_DEBIT_COLUMNS.items():
        amount = parse_amount(lower.get(column_name))
        if amount > 0:
            debits.append({
                'debit_type': debit_type,
                'amount': amount,
            })
    return debits

def normalize_upload_row(interface, row):
    lower = {normalize_upload_header(k): v for k, v in row.items()}
    if interface == 'sales_order':
        uploaded_client_name = (
            lower.get('uploaded_client_name')
            or lower.get('client_name')
            or lower.get('company_name')
            or lower.get('company')
        )
        return {
            'so_number': clean_text(lower.get('so_number') or lower.get('s.o_no') or lower.get('order_number')),
            'client_name': clean_text(uploaded_client_name, keep_period=True, keep_ampersand=True),
            'company_name': clean_text(
                lower.get('company_name') or lower.get('company') or uploaded_client_name,
                keep_period=True,
                keep_ampersand=True
            ),
            'store_name': clean_text(lower.get('store_name') or lower.get('store')),
            'store_branch': clean_text(lower.get('store_branch') or lower.get('branch')),
            'order_date': parse_date_value(lower.get('order_date') or lower.get('date')).isoformat(),
            'sales_staff': clean_text(lower.get('sales_staff') or lower.get('staff')),
            'particular': clean_text(lower.get('particular') or lower.get('particulars') or lower.get('item')),
            'quantity': parse_positive_whole_quantity(
                lower.get('quantity') or lower.get('qty') or 1
            ),
            'unit_cost': parse_amount(lower.get('unit_cost') or lower.get('cost')),
            'selling_price': parse_amount(lower.get('selling_price') or lower.get('price')),
            'total_amount': parse_amount(lower.get('total_amount') or lower.get('total')),
            'terms': int(parse_amount(lower.get('terms') or lower.get('terms_days') or 30) or 30),
        }
    if interface == 'purchase_order':
        check_date_value = lower.get('check_date') or lower.get('checkdate') or lower.get('check_dt')
        po_date_value = lower.get('date') or lower.get('po_date') or lower.get('podate') or lower.get('purchase_order_date')
        or_date_value = lower.get('or_date') or lower.get('ordate')
        debits = normalize_purchase_order_debits(lower)
        cash_amount = parse_amount(lower.get('cash'))
        total_debits = round(sum(debit['amount'] for debit in debits), 2)
        net_balance = round(cash_amount - total_debits, 2)
        category = 'FIXED' if any(
            debit['debit_type'] in FIXED_PURCHASE_ORDER_DEBIT_TYPES
            for debit in debits
        ) else 'VARIABLE'
        return {
            'purchase_order_id': parse_optional_integer(lower.get('purchase_order_id')),
            'check_voucher_number': clean_text(
                lower.get('check_voucher_number')
                or lower.get('check_cash_voucher_number')
                or lower.get('cv_no')
                or lower.get('voucher')
            ),
            'check_number': clean_text(lower.get('check_number') or lower.get('check_no')),
            'check_date': format_upload_date_ddmmyyyy(check_date_value, 'CheckDate'),
            'date': format_upload_date_ddmmyyyy(po_date_value, 'poDate'),
            'or_date': format_upload_date_ddmmyyyy(or_date_value, 'OR Date') if or_date_value else None,
            'ar_cr_or_number': clean_text(lower.get('ar_cr_or_number') or lower.get('or_number')),
            'po_number': clean_text(lower.get('po_number') or lower.get('po_no')),
            'lf_no': clean_text(lower.get('lf_no')),
            'particulars': clean_text(lower.get('particulars') or lower.get('particular')),
            'supplier_payee': clean_text(lower.get('supplier_payee') or lower.get('supplier') or lower.get('payee')),
            'tin_number': clean_text(lower.get('tin_number') or lower.get('tin')),
            'cash_amount': cash_amount,
            'total_debits': total_debits,
            'net_balance': net_balance,
            'status': 'PAID' if abs(net_balance) < 0.005 else 'PENDING',
            'category': category,
            'debits': debits,
        }
    uploaded_client_name = clean_text(
        lower.get('uploaded_client_name')
        or lower.get('client')
        or lower.get('client_name')
        or lower.get('company_name')
        or lower.get('company'),
        keep_period=True,
        keep_ampersand=True
    )
    so_number = clean_code(lower.get('so_number') or lower.get('sales_order'))
    is_admin_upload = bool(uploaded_client_name and not so_number)
    raw_total = lower.get('total_amount') if lower.get('total_amount') not in (None, '') else lower.get('amount')
    raw_balance = lower.get('balance')
    cr_number = clean_code(lower.get('cr_number') or lower.get('cr_no'))
    invoice_number = normalize_invoice_number(
        lower.get('invoice_number') or lower.get('invoice_no'),
        cr_number,
    )
    stored_type = (clean_text(lower.get('invoice_type')) or '').upper()
    supplied_invoice_type = canonical_invoice_type(
        invoice_number,
        stored_type or ('ADMIN UPLOAD' if is_admin_upload else 'SALES'),
    )
    invoice_date = parse_date_value(lower.get('invoice_date') or lower.get('date'), default_today=False)
    if not invoice_date:
        raise ValueError('Invoice date is required and must be valid.')
    return {
        'invoice_number': invoice_number,
        'uploaded_client_name': uploaded_client_name,
        'so_number': so_number,
        'invoice_type': supplied_invoice_type,
        'invoice_date': invoice_date.isoformat(),
        'summary': clean_text(lower.get('summary') or lower.get('description')) or ('Admin Upload' if is_admin_upload else ''),
        'payment_type': 'Admin Upload' if is_admin_upload else clean_text(lower.get('payment_type')),
        'cr_number': cr_number,
        'payment_amount': parse_amount(lower.get('payment_amount') or lower.get('amount_paid') or lower.get('paid')),
        'tax_amount_paid': parse_amount(lower.get('tax_amount_paid') or lower.get('tax')),
        'total_amount': None if is_admin_upload and raw_total in (None, '') else parse_amount(raw_total),
        'amount_paid': parse_amount(lower.get('amount_paid') or lower.get('paid') or lower.get('payment_amount')),
        'balance': None if is_admin_upload and raw_balance in (None, '') else parse_amount(raw_balance),
        'status': 'Admin Upload' if is_admin_upload else (clean_text(lower.get('status')) or 'UNPAID').upper(),
    }

def zscore_outliers(rows, amount_key):
    values = [float(row.get(amount_key) or 0) for row in rows]
    if len(values) < 2:
        return []
    mean = sum(values) / len(values)
    std = (sum((v - mean) ** 2 for v in values) / len(values)) ** 0.5
    if std == 0:
        return []
    return [
        {'index': idx, 'field': amount_key, 'value': value, 'z_score': round((value - mean) / std, 2)}
        for idx, value in enumerate(values) if abs((value - mean) / std) >= 2.5
    ]

def invoice_upload_schema_status():
    inspector = sa_inspect(db.engine)
    tables = set(inspector.get_table_names())
    missing = []
    if 'sales_order_branches' not in tables:
        missing.append('sales_order_branches')
    if 'collection_receipts' not in tables:
        missing.append('collection_receipts')
    if 'sales_order_items' not in tables:
        missing.append('sales_order_items')
    else:
        item_columns = {column['name'] for column in inspector.get_columns('sales_order_items')}
        if 'sales_order_branch_id' not in item_columns:
            missing.append('sales_order_items.sales_order_branch_id')
    return {'ready': not missing, 'missing': missing}

def invoice_upload_client_key(value):
    return normalize_client_match_key(
        clean_text(value, keep_period=True, keep_ampersand=True).upper()
    )

def prepare_invoice_upload_rows(rows):
    prepared = []
    clients_by_invoice = defaultdict(set)
    source_rows_by_invoice = defaultdict(list)
    for index, raw in enumerate(rows, start=1):
        if raw.get('included') is False:
            continue
        client_name = clean_text(
            raw.get('uploaded_client_name'),
            keep_period=True,
            keep_ampersand=True,
        ).upper()
        cr_number = clean_code(raw.get('cr_number')).upper()
        invoice_number = normalize_invoice_number(raw.get('invoice_number'), cr_number)
        invoice_date = parse_date_value(raw.get('invoice_date'), default_today=False)
        amount_paid = parse_nonnegative_amount(
            raw.get('amount_paid') if raw.get('amount_paid') not in (None, '') else raw.get('payment_amount'),
            f'Row {index} Amount Paid',
        )
        payment_amount = parse_nonnegative_amount(
            raw.get('payment_amount') if raw.get('payment_amount') not in (None, '') else amount_paid,
            f'Row {index} Payment Amount',
        )
        if not client_name:
            raise ValueError(f'Row {index}: Uploaded Client Name is required.')
        if not invoice_number:
            raise ValueError(f'Row {index}: Invoice Number or CR Number is required.')
        if not invoice_date:
            raise ValueError(f'Row {index}: Invoice Date is required and must be valid.')
        if amount_paid <= 0:
            raise ValueError(f'Row {index}: Amount Paid must be greater than zero.')
        client_key = invoice_upload_client_key(client_name)
        number_key = invoice_number.upper()
        source_row = raw.get('_source_row') or raw.get('source_row') or index
        clients_by_invoice[number_key].add(client_key)
        source_rows_by_invoice[number_key].append(source_row)
        prepared.append({
            'source_row': source_row,
            'invoice_number': invoice_number,
            'invoice_key': number_key,
            'uploaded_client_name': client_name,
            'client_key': client_key,
            'so_number': clean_code(raw.get('so_number')),
            'invoice_type': canonical_invoice_type(
                invoice_number,
                raw.get('invoice_type') or 'ADMIN UPLOAD',
            ),
            'invoice_date': invoice_date,
            'summary': clean_text(raw.get('summary') or raw.get('description')),
            'payment_type': raw.get('payment_type') or 'Admin Upload',
            'cr_number': cr_number,
            'payment_amount': payment_amount,
            'tax_amount_paid': parse_nonnegative_amount(raw.get('tax_amount_paid'), f'Row {index} Tax Amount'),
            'total_amount': (
                None if raw.get('total_amount') in (None, '')
                else parse_nonnegative_amount(raw.get('total_amount'), f'Row {index} Total Amount')
            ),
            'amount_paid': amount_paid,
            'balance': (
                None if raw.get('balance') in (None, '')
                else parse_nonnegative_amount(raw.get('balance'), f'Row {index} Balance')
            ),
        })

    conflicts = [
        {
            'invoice_number': invoice_number,
            'clients': sorted({
                row['uploaded_client_name']
                for row in prepared
                if row['invoice_key'] == invoice_number
            }),
            'source_rows': source_rows_by_invoice[invoice_number],
        }
        for invoice_number, client_keys in clients_by_invoice.items()
        if len(client_keys) > 1
    ]
    grouped = {}
    for row in prepared:
        key = (row['invoice_key'], row['client_key'])
        if key not in grouped:
            grouped[key] = {
                **row,
                'source_rows': [row['source_row']],
                'collection_dates': {row['invoice_date']},
                'cr_numbers': {row['cr_number']} if row['cr_number'] else set(),
                'summaries': {row['summary']} if row['summary'] else set(),
                'receipts': [dict(row)],
            }
            continue
        current = grouped[key]
        current['amount_paid'] = round(current['amount_paid'] + row['amount_paid'], 2)
        current['payment_amount'] = round(current['payment_amount'] + row['payment_amount'], 2)
        current['tax_amount_paid'] = round(current['tax_amount_paid'] + row['tax_amount_paid'], 2)
        current['invoice_date'] = max(current['invoice_date'], row['invoice_date'])
        current['source_rows'].append(row['source_row'])
        current['collection_dates'].add(row['invoice_date'])
        if row['cr_number']:
            current['cr_numbers'].add(row['cr_number'])
        if row['summary']:
            current['summaries'].add(row['summary'])
        current['receipts'].append(dict(row))
    return list(grouped.values()), conflicts

def invoice_collection_note(row, matched):
    if len(row['source_rows']) == 1:
        return 'Matched using Uploaded Client Name' if matched else 'Admin Upload'
    dates = ', '.join(item.isoformat() for item in sorted(row['collection_dates']))
    receipts = ', '.join(sorted(row['cr_numbers']))
    summaries = '; '.join(sorted(row['summaries']))
    parts = [
        'Matched using Uploaded Client Name' if matched else 'Admin Upload',
        f"Source rows: {', '.join(map(str, row['source_rows']))}",
        f'Collection dates: {dates}',
    ]
    if receipts:
        parts.append(f'CR numbers: {receipts}')
    if summaries:
        parts.append(f'Summaries: {summaries}')
    return ' | '.join(parts)

def resolve_invoice_upload_client(client_name, registry, clients_by_id):
    client_key = invoice_upload_client_key(client_name)
    exact = registry['lookup'].get(client_key)
    if exact:
        return clients_by_id.get(exact['client_id'])
    fuzzy_match = find_client_match(client_name, registry)
    if (
        fuzzy_match
        and float(fuzzy_match.get('match_percent') or 0) >= CLIENT_REVIEW_MATCH_PERCENT
        and not is_client_fuzzy_exception(client_name, fuzzy_match.get('client_name'))
    ):
        return clients_by_id.get(fuzzy_match['client_id'])
    return None

def invoice_receipt_numbers(invoice):
    receipt_numbers = {
        normalize_cr_number(item.cr_number)
        for item in getattr(invoice, 'collection_receipts', []) or []
        if normalize_cr_number(item.cr_number)
    }
    direct_receipt = clean_code(invoice.cr_number).upper()
    if direct_receipt:
        receipt_numbers.add(direct_receipt)
    note = invoice.admin_upload_note or ''
    marker = 'CR numbers:'
    if marker in note:
        receipt_text = note.split(marker, 1)[1].split('|', 1)[0]
        receipt_numbers.update(
            clean_code(value).upper()
            for value in receipt_text.split(',')
            if clean_code(value)
        )
    return receipt_numbers

def existing_invoice_client_key(invoice):
    if invoice.sales_order and invoice.sales_order.client:
        return invoice_upload_client_key(invoice.sales_order.client.client_name)
    return invoice_upload_client_key(invoice.uploaded_client_name)

def filter_existing_invoice_receipts(rows, existing_invoices):
    existing_by_number = {
        normalize_invoice_number(invoice.invoice_number).upper(): invoice
        for invoice in existing_invoices
    }

    accepted_rows = []
    skipped_receipts = []
    receipt_conflicts = []
    for index, row in enumerate(rows, start=1):
        if row.get('included') is False:
            accepted_rows.append(row)
            continue
        receipt_number = normalize_cr_number(row.get('cr_number'))
        incoming_invoice_number = normalize_invoice_number(
            row.get('invoice_number'),
            receipt_number,
        ).upper()
        existing_invoice = existing_by_number.get(incoming_invoice_number)
        if not receipt_number or not existing_invoice:
            accepted_rows.append(row)
            continue

        source_row = row.get('_source_row') or row.get('source_row') or index
        if receipt_number in invoice_receipt_numbers(existing_invoice):
            skipped_receipts.append({
                'cr_number': receipt_number,
                'invoice_number': incoming_invoice_number,
                'existing_invoice_id': existing_invoice.id,
                'source_row': source_row,
            })
            continue
        accepted_rows.append(row)
    return accepted_rows, skipped_receipts, receipt_conflicts

def commit_invoice_upload_batch(rows):
    schema = invoice_upload_schema_status()
    if not schema['ready']:
        return jsonify({
            'success': False,
            'error': (
                'The database schema is not ready for invoice matching. Apply the current '
                f"Supabase migration first. Missing: {', '.join(schema['missing'])}."
            ),
            'error_type': 'database_schema',
            'missing_schema': schema['missing'],
        }), 500

    existing_invoices = (
        Invoice.query
        .options(
            selectinload(Invoice.sales_order).selectinload(SalesOrder.client),
            selectinload(Invoice.collection_receipts),
        )
        .all()
    )
    accepted_rows, skipped_receipts, receipt_conflicts = filter_existing_invoice_receipts(
        rows,
        existing_invoices,
    )
    if receipt_conflicts:
        return jsonify({
            'success': False,
            'needs_review': True,
            'error': 'Some CR numbers already exist under a different invoice or Uploaded Client Name.',
            'receipt_conflicts': receipt_conflicts,
        }), 409

    seen_import_receipts = {}
    duplicate_import_receipts = []
    for index, row in enumerate(accepted_rows, start=1):
        if row.get('included') is False:
            continue
        receipt_number = normalize_cr_number(row.get('cr_number'))
        if not receipt_number:
            continue
        invoice_number = normalize_invoice_number(
            row.get('invoice_number'),
            receipt_number,
        ).upper()
        receipt_key = (invoice_number, receipt_number)
        source_row = row.get('_source_row') or row.get('source_row') or index
        if receipt_key in seen_import_receipts:
            duplicate_import_receipts.append({
                'invoice_number': invoice_number,
                'cr_number': receipt_number,
                'source_rows': [seen_import_receipts[receipt_key], source_row],
            })
        else:
            seen_import_receipts[receipt_key] = source_row
    if duplicate_import_receipts:
        return jsonify({
            'success': False,
            'needs_review': True,
            'error': 'A CR number can appear only once within the same invoice.',
            'receipt_conflicts': duplicate_import_receipts,
        }), 409

    grouped_rows, conflicts = prepare_invoice_upload_rows(accepted_rows)
    if conflicts:
        return jsonify({
            'success': False,
            'needs_review': True,
            'error': 'Some invoice numbers belong to different Uploaded Client Names. Correct or exclude those rows.',
            'conflicts': conflicts,
        }), 409

    registry = build_client_registry()
    clients_by_id = {client.id: client for client in registry['clients']}
    client_cache = {}
    orders = (
        SalesOrder.query
        .options(selectinload(SalesOrder.items), selectinload(SalesOrder.invoices))
        .order_by(SalesOrder.order_date.desc(), SalesOrder.id.desc())
        .all()
    )
    orders_by_so = defaultdict(list)
    outstanding_by_client = defaultdict(list)
    for order in orders:
        orders_by_so[clean_code(order.so_number).upper()].append(order)
        paid = sum(float(invoice.amount_paid or 0) for invoice in order.invoices)
        if sales_order_total(order) - paid > MONEY_TOLERANCE:
            outstanding_by_client[order.client_id].append(order)

    existing_by_number = {
        normalize_invoice_number(invoice.invoice_number).upper(): invoice
        for invoice in existing_invoices
    }

    prepared_actions = []
    database_conflicts = []
    additions_by_order = defaultdict(float)
    for row in grouped_rows:
        if row['client_key'] not in client_cache:
            client_cache[row['client_key']] = resolve_invoice_upload_client(
                row['uploaded_client_name'],
                registry,
                clients_by_id,
            )
        client = client_cache[row['client_key']]
        sales_order = None
        bridge_candidate = None
        match_source = 'standalone'
        so_number = clean_code(row.get('so_number')).upper()
        if so_number:
            candidates = orders_by_so.get(so_number, [])
            if len(candidates) == 1:
                sales_order = candidates[0]
                match_source = 'explicit_sales_order'
        elif client:
            candidates = outstanding_by_client.get(client.id, [])
            if len(candidates) == 1:
                bridge_candidate = candidates[0]

        existing_invoice = existing_by_number.get(row['invoice_key'])
        existing_client_id = None
        existing_client_name = None
        if existing_invoice:
            if existing_invoice.sales_order:
                existing_client_id = existing_invoice.sales_order.client_id
                existing_client_name = (
                    existing_invoice.sales_order.client.client_name
                    if existing_invoice.sales_order.client else existing_invoice.uploaded_client_name
                )
            elif existing_invoice.uploaded_client_name:
                existing_client = resolve_invoice_upload_client(
                    existing_invoice.uploaded_client_name,
                    registry,
                    clients_by_id,
                )
                existing_client_id = existing_client.id if existing_client else None
                existing_client_name = existing_invoice.uploaded_client_name
        if existing_invoice and client and existing_client_id and existing_client_id != client.id:
            database_conflicts.append({
                'invoice_number': row['invoice_number'],
                'uploaded_client_name': row['uploaded_client_name'],
                'existing_client_name': existing_client_name,
                'source_rows': row['source_rows'],
            })
            continue
        if existing_invoice and existing_invoice.sales_order:
            sales_order = existing_invoice.sales_order
            match_source = 'existing_invoice'
        if sales_order and match_source != 'uploaded_client_name':
            addition = float(row['amount_paid'] or 0)
            if existing_invoice and existing_invoice.sales_order_id is None:
                addition += float(existing_invoice.amount_paid or 0)
            additions_by_order[sales_order.id] += addition
        prepared_actions.append({
            'row': row,
            'client': client,
            'sales_order': sales_order,
            'existing_invoice': existing_invoice,
            'match_source': match_source,
            'bridge_candidate': bridge_candidate,
        })

    if database_conflicts:
        return jsonify({
            'success': False,
            'needs_review': True,
            'error': 'Some invoice numbers already exist under a different client.',
            'conflicts': database_conflicts,
        }), 409

    overpayments = []
    orders_by_id = {order.id: order for order in orders}
    for order_id, addition in additions_by_order.items():
        order = orders_by_id[order_id]
        current_paid = sum(float(invoice.amount_paid or 0) for invoice in order.invoices)
        available = max(sales_order_total(order) - current_paid, 0)
        if addition > available + MONEY_TOLERANCE:
            overpayments.append({
                'sales_order_id': order.id,
                'so_number': order.so_number,
                'available_balance': round(available, 2),
                'uploaded_payment': round(addition, 2),
            })
    if overpayments:
        return jsonify({
            'success': False,
            'needs_review': True,
            'error': 'One or more uploaded payments exceed the matched Sales Order balance.',
            'overpayments': overpayments,
        }), 409

    bridge_reservations_by_order = defaultdict(float)
    for action in prepared_actions:
        if action['sales_order'] is not None or action['bridge_candidate'] is None:
            continue
        candidate = action['bridge_candidate']
        current_paid = sum(float(invoice.amount_paid or 0) for invoice in candidate.invoices)
        available = max(
            sales_order_total(candidate)
            - current_paid
            - additions_by_order[candidate.id]
            - bridge_reservations_by_order[candidate.id],
            0,
        )
        amount_to_link = float(action['row']['amount_paid'] or 0)
        existing_invoice = action['existing_invoice']
        if existing_invoice and existing_invoice.sales_order_id is None:
            amount_to_link += float(existing_invoice.amount_paid or 0)
        if amount_to_link <= available + MONEY_TOLERANCE:
            action['sales_order'] = candidate
            action['match_source'] = 'uploaded_client_name'
            bridge_reservations_by_order[candidate.id] += amount_to_link

    created = 0
    updated = 0
    linked = 0
    standalone = 0
    affected_orders = {}
    for action in prepared_actions:
        row = action['row']
        client = action['client']
        sales_order = action['sales_order']
        existing_invoice = action['existing_invoice']
        match_source = action['match_source']
        matched = sales_order is not None
        collection_note = invoice_collection_note(row, matched)
        if not matched and client:
            collection_note = (
                f'{collection_note} | Uploaded Client Name matched a client, '
                'but no single Sales Order had enough available balance.'
            )
        first_receipt = row['receipts'][0]
        summary = '; '.join(sorted(row['summaries'])) or ('Admin Upload' if not matched else None)
        invoice_type = canonical_invoice_type(
            row['invoice_number'],
            row['invoice_type'] or ('SALES' if matched else 'ADMIN UPLOAD'),
        )
        if matched and invoice_type == 'ADMIN UPLOAD':
            invoice_type = 'SALES'
        if existing_invoice:
            if existing_invoice.total_amount is None:
                existing_invoice.total_amount = round(
                    float(existing_invoice.amount_paid or 0) + float(row['amount_paid'] or 0),
                    2,
                )
            running_paid = float(existing_invoice.amount_paid or 0)
            for receipt_row in row['receipts']:
                receipt = append_collection_receipt(existing_invoice, {
                    'receipt_date': receipt_row['invoice_date'].isoformat(),
                    'cr_number': receipt_row['cr_number'] or f"LEGACY-{existing_invoice.id}-{receipt_row['source_row']}",
                    'payment_type': receipt_row['payment_type'],
                    'payment_amount': receipt_row['payment_amount'],
                    'tax_amount_paid': receipt_row['tax_amount_paid'],
                    'is_2307_checked': bool(receipt_row.get('tax_amount_paid')),
                }, allow_legacy=True, recorded_by='admin upload',
                    existing_paid=running_paid, prevalidated=True)
                running_paid += float(receipt.collected_total or 0)
            if existing_invoice.sales_order:
                affected_orders[existing_invoice.sales_order.id] = existing_invoice.sales_order
                linked += 1
            else:
                standalone += 1
            updated += 1
            continue

        total = (
            sales_order_total(sales_order)
            if sales_order
            else (row['total_amount'] if row['total_amount'] is not None else row['amount_paid'])
        )
        invoice = Invoice(
            invoice_number=row['invoice_number'],
            sales_order_id=sales_order.id if sales_order else None,
            invoice_type=invoice_type,
            invoice_date=row['invoice_date'],
            summary=summary,
            payment_type=first_receipt['payment_type'],
            cr_number=first_receipt['cr_number'],
            payment_amount=first_receipt['payment_amount'],
            tax_amount_paid=first_receipt['tax_amount_paid'],
            is_2307_checked=bool(first_receipt.get('tax_amount_paid')),
            total_amount=total,
            amount_paid=0,
            balance=total,
            status='UNPAID',
            uploaded_client_name=row['uploaded_client_name'],
            upload_source='admin_upload',
            admin_upload_note=collection_note,
        )
        db.session.add(invoice)
        db.session.flush()
        running_paid = 0.0
        for receipt_row in row['receipts']:
            receipt = append_collection_receipt(invoice, {
                'receipt_date': receipt_row['invoice_date'].isoformat(),
                'cr_number': receipt_row['cr_number'] or f"LEGACY-{invoice.id}-{receipt_row['source_row']}",
                'payment_type': receipt_row['payment_type'],
                'payment_amount': receipt_row['payment_amount'],
                'tax_amount_paid': receipt_row['tax_amount_paid'],
                'is_2307_checked': bool(receipt_row.get('tax_amount_paid')),
            }, allow_legacy=True, recorded_by='admin upload',
                existing_paid=running_paid, prevalidated=True)
            running_paid += float(receipt.collected_total or 0)
        if sales_order:
            affected_orders[sales_order.id] = sales_order
            linked += 1
        else:
            standalone += 1
        created += 1

    db.session.flush()
    for order in affected_orders.values():
        synchronize_sales_order_payment_state(order)
    refresh_client_financials()
    log_audit('UPLOAD_COMMIT', 'invoices', None, None, {
        'source_rows': len(rows),
        'grouped_records': len(grouped_rows),
        'created': created,
        'updated': updated,
        'linked': linked,
        'standalone': standalone,
        'duplicate_receipts_skipped': len(skipped_receipts),
        'excluded': len(rows) - sum(1 for row in rows if row.get('included') is not False),
    })
    db.session.commit()
    if grouped_rows:
        message = f'Processed {len(grouped_rows)} new collection record(s).'
    else:
        message = 'No new collection records were added.'
    if skipped_receipts:
        message += f' Skipped {len(skipped_receipts)} CR number(s) already in the database.'
    return jsonify({
        'success': True,
        'message': message,
        'source_rows': len(rows),
        'grouped_records': len(grouped_rows),
        'created': created,
        'updated': updated,
        'linked': linked,
        'standalone': standalone,
        'duplicate_receipts_skipped': len(skipped_receipts),
        'skipped_receipts': skipped_receipts,
        'excluded': len(rows) - sum(1 for row in rows if row.get('included') is not False),
    })

def serialize_record(record):
    if not record:
        return None
    data = {
        column.name: (
            getattr(record, column.name).isoformat()
            if hasattr(getattr(record, column.name), 'isoformat')
            else getattr(record, column.name)
        )
        for column in record.__table__.columns
    }
    if 'password_hash' in data:
        data['password_hash'] = '[REDACTED]'
    return data

def log_audit(action, table_name, record_id=None, old_value=None, new_value=None):
    entry = AuditLog(
        user_id=session.get('user_id'),
        username=session.get('username', 'system'),
        action=action,
        table_name=table_name,
        record_id=str(record_id) if record_id is not None else None,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,
    )
    db.session.add(entry)

def admin_role():
    return Role.query.filter(func.lower(Role.role_name) == 'admin').first()

def is_admin_role_id(role_id):
    role = db.session.get(Role, role_id)
    return bool(role and role.role_name.lower() == 'admin')

def force_logout_user(user_id):
    SessionRecord.query.filter_by(user_id=user_id, status='ACTIVE').update({
        'status': 'FORCED_LOGOUT',
        'logout_at': datetime.now(UTC)
    })

def pending_password_reset_count():
    if session.get('role') != 'admin':
        return 0
    return PasswordReset.query.filter_by(status='PENDING').count()

def pending_account_approval_count():
    if session.get('role') != 'admin':
        return 0
    return User.query.filter(func.lower(User.status) == USER_STATUS_PENDING).count()

def pending_admin_notification_count():
    return pending_password_reset_count() + pending_account_approval_count()

def profile_photo_src(user):
    if not user:
        return None
    if user.profile_photo_data and user.profile_photo_mime:
        return f'data:{user.profile_photo_mime};base64,{user.profile_photo_data}'
    if user.profile_photo:
        return url_for('static', filename=user.profile_photo)
    return None

@app.context_processor
def inject_user_navigation():
    current_user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    return {
        'current_user': current_user,
        'pending_notification_count': pending_admin_notification_count(),
        'profile_photo_src': profile_photo_src,
    }

# Initialize Database
DEFAULT_EVALUATION_QUESTIONS = [
    ("User Experience", "The web app is easy to navigate and understand."),
    ("User Experience", "The web app provides clear feedback for my actions, such as confirmations and error messages."),
    ("User Experience", "The web app minimizes the number of steps needed to complete a task."),
    ("User Experience", "The web app enhances my ability to analyze business performance effectively."),
    ("Features", "The web app provides all the features I need for business analysis."),
    ("Features", "The data visualizations, such as charts and graphs, are useful for decision-making."),
    ("Design", "The layout of the web app is well-organized and not cluttered."),
    ("Design", "The interface adapts well to different screen sizes."),
    ("Design", "The web app maintains a consistent design throughout its different sections."),
    ("Compatibility", "The web app runs smoothly on both mobile and desktop devices."),
    ("Compatibility", "The web app functions well across different web browsers, such as Chrome, Firefox, and others."),
    ("Compatibility", "The web app supports multiple operating systems, such as Windows, macOS, and others."),
    ("Reliability", "The web app consistently performs without major crashes or errors."),
    ("Reliability", "The web app correctly reflects the latest business transactions."),
    ("Reliability", "I can rely on the web app for daily business operations."),
    ("Efficiency", "The web app helps me complete tasks faster than manual methods."),
    ("Efficiency", "The web app reduces the time needed to analyze sales and profits."),
    ("Efficiency", "The web app minimizes unnecessary steps in data processing."),
    ("Efficiency", "The web app reduces the workload of the management staff."),
    ("Efficiency", "The web app improves overall workflow efficiency in the workspace."),
    ("Security", "The login and authentication process is secure and reliable."),
    ("Security", "The web app effectively protects sensitive business information from unauthorized access."),
    ("Security", "I trust that my login credentials and personal data are well-protected."),
    ("Portability", "The web app maintains full functionality across different platforms."),
    ("Portability", "The mobile experience is just as effective as the desktop experience."),
    ("Overall Agreement", "I am satisfied with the overall performance of the web app."),
    ("Overall Agreement", "The web app meets my expectations for business analysis and insights."),
    ("Overall Agreement", "The web app is a necessary tool for optimizing business decisions."),
    ("Overall Agreement", "I would continue using this web app in the long term."),
]

def default_seed_users():
    allow_insecure_demo_passwords = os.environ.get('SYLUXENT_ALLOW_INSECURE_DEMO_PASSWORDS', '').lower() in {'1', 'true', 'yes'}
    local_demo_passwords = {
        'admin': 'admin123',
        'manager': 'manager123',
        'staff': 'staff123',
    } if allow_insecure_demo_passwords else {}
    return [
        {
            "username": os.environ.get("DEFAULT_ADMIN_USERNAME", "admin"),
            "role_name": "admin",
            "password": os.environ.get("DEFAULT_ADMIN_PASSWORD") or local_demo_passwords.get("admin"),
        },
        {
            "username": os.environ.get("DEFAULT_MANAGER_USERNAME", "manager"),
            "role_name": "manager",
            "password": os.environ.get("DEFAULT_MANAGER_PASSWORD") or local_demo_passwords.get("manager"),
        },
        {
            "username": os.environ.get("DEFAULT_STAFF_USERNAME", "staff"),
            "role_name": "staff",
            "password": os.environ.get("DEFAULT_STAFF_PASSWORD") or local_demo_passwords.get("staff"),
        },
    ]

def seed_evaluation_questions():
    expected_questions = list(enumerate(DEFAULT_EVALUATION_QUESTIONS, start=1))
    current_questions = EvaluationQuestion.query.order_by(EvaluationQuestion.display_order.asc()).all()
    current_signature = [
        (question.display_order, question.category, question.question_text)
        for question in current_questions
    ]
    expected_signature = [
        (order, category, text)
        for order, (category, text) in expected_questions
    ]
    if current_signature and current_signature != expected_signature:
        EvaluationResponse.query.delete()
        EvaluationSession.query.delete()
        EvaluationQuestion.query.delete()
        db.session.flush()
    for order, (category, text) in expected_questions:
        question = EvaluationQuestion.query.filter_by(display_order=order).first()
        if not question:
            question = EvaluationQuestion(display_order=order)
            db.session.add(question)
        question.category = category
        question.question_text = text
        question.is_active = True
    EvaluationQuestion.query.filter(EvaluationQuestion.display_order > len(DEFAULT_EVALUATION_QUESTIONS)).update({'is_active': False})
    db.session.commit()

def init_db():
    with app.app_context():
        pre_schema_status = ensure_defense_schema(db)
        db.create_all()
        schema_status = ensure_defense_schema(db)
        backup_path = pre_schema_status.get('backup_path') or schema_status.get('backup_path')
        if backup_path:
            app.logger.warning(
                'SQLite database backed up before defense migration: %s',
                backup_path,
            )
        
        # Create default roles if they don't exist
        if not Role.query.first():
            roles = [
                Role(role_name='admin', description='Full access to all features including user management and database administration.'),
                Role(role_name='manager', description='Access to analytics, reports, and all business data. Can view but not modify records.'),
                Role(role_name='staff', description='Can create sales orders and manage invoices/payments. Limited to operational tasks.')
            ]
            db.session.bulk_save_objects(roles)
            db.session.commit()
        
        # Create default admin user if they don't exist

        default_users = default_seed_users()
        for user_info in default_users:
            if user_info["role_name"] == "admin" and User.query.join(Role).filter(func.lower(Role.role_name) == 'admin').first():
                continue
            if not user_info["password"]:
                print(f"Skipped default {user_info['role_name']} user. Set DEFAULT_{user_info['role_name'].upper()}_PASSWORD to seed it.")
                continue
            # Check if the user already exists
            if not User.query.filter_by(username=user_info["username"]).first():
                # Find the matching role record
                role = Role.query.filter_by(role_name=user_info["role_name"]).first()
                
                if role:
                    new_user = User(
                        username=user_info["username"],
                        password_hash=generate_password_hash(user_info["password"]),
                        role_id=role.id,
                        status=USER_STATUS_APPROVED,
                        approved_at=datetime.now(UTC)
                    )
                    db.session.add(new_user)
                    print(f"Created default user: {user_info['username']}")
                else:
                    print(f"Warning: Could not create {user_info['username']} because role '{user_info['role_name']}' does not exist in the database.")
        db.session.commit()
        refresh_client_financials()
        seed_evaluation_questions()
        db.session.commit()


# Routes
@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/theme-overrides.css')
def theme_overrides_css():
    return Response(
        build_theme_css(read_theme_settings()),
        mimetype='text/css',
        headers={'Cache-Control': 'no-store'}
    )

@app.errorhandler(400)
def bad_request_error(error):
    return render_error_interface('validation', 400, error)

@app.errorhandler(401)
def unauthorized_error(error):
    return render_error_interface('authentication', 401, error)

@app.errorhandler(403)
def forbidden_error(error):
    return render_error_interface('permission', 403, error)

@app.errorhandler(404)
def not_found_error(error):
    return render_error_interface('empty', 404, error)

@app.errorhandler(500)
def internal_server_error(error):
    return render_error_interface('server', 500, error)

@app.errorhandler(413)
def upload_too_large_error(error):
    return render_error_interface(
        'validation',
        413,
        f"Upload exceeds the {app.config['MAX_CONTENT_LENGTH'] // (1024 * 1024)} MB limit.",
    )

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            if not is_user_approved(user):
                flash(user_access_message(user), 'error')
                return render_template('login.html')
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user_role_name(user)
            session_record = SessionRecord(
                user_id=user.id,
                username=user.username,
                role_name=user.role.role_name
            )
            db.session.add(session_record)
            db.session.commit()
            session['session_record_id'] = session_record.id
            log_audit('LOGIN', 'session_records', session_record.id, None, {'username': user.username, 'role': user.role.role_name})
            db.session.commit()
            flash(f'Welcome back, {username}!', 'success')
            if session['role'] == 'admin':
                return redirect(url_for('database_interface'))
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid login credentials. Please check your details and try again.', 'error')
    
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user and is_user_approved(user):
            existing = PasswordReset.query.filter_by(user_id=user.id, status='PENDING').first()
            if not existing:
                reset_request = PasswordReset(user_id=user.id, username=user.username)
                db.session.add(reset_request)
                db.session.flush()
                db.session.add(AuditLog(
                    user_id=user.id,
                    username=user.username,
                    action='PASSWORD_RESET_REQUEST',
                    table_name='password_resets',
                    record_id=str(reset_request.id),
                    new_value=str({'username': user.username, 'status': 'PENDING'})
                ))
                db.session.commit()
        flash('If the username is active, the administrator has been notified.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        username = request.form.get('username')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not email or not username or not password or not confirm_password:
            flash('All fields are required', 'error')
            return render_template('register.html')
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html')
        
        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash('An account with those details already exists or cannot be created.', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with those details already exists or cannot be created.', 'error')
            return render_template('register.html')

        staff_role = Role.query.filter_by(role_name='staff').first()
        if not staff_role:
            flash('Staff role is not configured', 'error')
            return render_template('register.html')
        
        user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            role_id=staff_role.id,
            status=USER_STATUS_PENDING
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(AuditLog(
            user_id=user.id,
            username=user.username,
            action='REGISTER',
            table_name='users',
            record_id=str(user.id),
            new_value=str({'username': user.username, 'role': 'staff', 'status': user.status})
        ))
        db.session.commit()
        
        flash('Registration received. Your account is pending administrator approval.', 'info')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = db.session.get(User, session['user_id'])
    if request.method == 'POST':
        old_value = serialize_record(user)
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        current_password = request.form.get('current_password') or ''
        new_password = request.form.get('new_password') or ''
        confirm_password = request.form.get('confirm_password') or ''

        if not username:
            flash('Username is required.', 'error')
            return render_template('profile.html', user=user)
        if User.query.filter(func.lower(User.username) == username.lower(), User.id != user.id).first():
            flash('Username already exists.', 'error')
            return render_template('profile.html', user=user)
        if email and User.query.filter(func.lower(User.email) == email.lower(), User.id != user.id).first():
            flash('Email already exists.', 'error')
            return render_template('profile.html', user=user)
        if new_password:
            if not check_password_hash(user.password_hash, current_password):
                flash('Current password is incorrect.', 'error')
                return render_template('profile.html', user=user)
            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return render_template('profile.html', user=user)
            user.password_hash = generate_password_hash(new_password)

        photo = request.files.get('profile_photo')
        if photo and photo.filename:
            extension = os.path.splitext(secure_filename(photo.filename))[1].lower()
            if extension not in PROFILE_PHOTO_MIME_TYPES:
                flash('Profile photo must be PNG, JPG, JPEG, or WEBP.', 'error')
                return render_template('profile.html', user=user)
            photo_bytes = photo.read(PROFILE_PHOTO_MAX_BYTES + 1)
            if len(photo_bytes) > PROFILE_PHOTO_MAX_BYTES:
                flash('Profile photo must be 1 MB or smaller.', 'error')
                return render_template('profile.html', user=user)
            user.profile_photo_data = base64.b64encode(photo_bytes).decode('ascii')
            user.profile_photo_mime = PROFILE_PHOTO_MIME_TYPES[extension]
            user.profile_photo = None

        user.username = username
        user.email = email
        session['username'] = user.username
        log_audit('UPDATE_PROFILE', 'users', user.id, old_value, serialize_record(user))
        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html', user=user)

@app.route('/logout')
def logout():
    session_record_id = session.get('session_record_id')
    if session_record_id:
        session_record = db.session.get(SessionRecord, session_record_id)
        if session_record and session_record.status == 'ACTIVE':
            session_record.logout_at = datetime.now(UTC)
            session_record.status = 'LOGGED_OUT'
            log_audit('LOGOUT', 'session_records', session_record.id, None, {'username': session.get('username')})
            db.session.commit()
    session.clear()
    return render_template('logout.html', login_url=url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    today = datetime.now().date()
    current_year = today.year
    selected_year = request.args.get('year', default=current_year, type=int)
    if selected_year is None or selected_year < 1900 or selected_year > 9998:
        selected_year = current_year
    refresh_client_financials()
    year_start = date(selected_year, 1, 1)
    next_year_start = date(selected_year + 1, 1, 1)
    thirty_days_ago = datetime.now() - timedelta(days=30)

    def nz(value):
        return value or 0

    available_year_rows = (
        db.session.query(db_year(SalesOrder.order_date).label('year'))
        .filter(SalesOrder.order_date.isnot(None))
        .union(
            db.session.query(db_year(Invoice.invoice_date).label('year'))
            .filter(Invoice.invoice_date.isnot(None)),
            db.session.query(db_year(PurchaseOrder.date).label('year'))
            .filter(PurchaseOrder.date.isnot(None))
        )
        .all()
    )
    available_years = sorted(
        {current_year, *(int(row.year) for row in available_year_rows if row.year)},
        reverse=True
    )

    # Revenue and profit
    revenue_totals = (
        db.session.query(
            func.coalesce(func.sum(CollectionReceipt.collected_total), 0).label('total_revenue'),
            func.coalesce(
                func.sum(
                    case(
                        (CollectionReceipt.is_2307_checked.is_(True), CollectionReceipt.tax_amount_paid),
                        else_=0
                    )
                ),
                0
            ).label('total_tax_collected'),
            func.count(CollectionReceipt.id).label('payment_count')
        )
        .filter(
            CollectionReceipt.receipt_date >= year_start,
            CollectionReceipt.receipt_date < next_year_start
        )
        .one()
    )

    total_revenue = float(revenue_totals.total_revenue or 0)
    total_tax_collected = float(revenue_totals.total_tax_collected or 0)
    payment_count = int(revenue_totals.payment_count or 0)
    legacy_revenue = (
        db.session.query(
            func.coalesce(func.sum(Invoice.amount_paid), 0),
            func.coalesce(func.sum(case(
                (Invoice.is_2307_checked.is_(True), Invoice.tax_amount_paid),
                else_=0,
            )), 0),
            func.count(Invoice.id),
        )
        .filter(
            Invoice.amount_paid > 0,
            ~Invoice.collection_receipts.any(),
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start,
        )
        .one()
    )
    total_revenue += float(legacy_revenue[0] or 0)
    total_tax_collected += float(legacy_revenue[1] or 0)
    payment_count += int(legacy_revenue[2] or 0)

    # Expenses and available pondo
    total_expenses = (
        db.session.query(db.func.coalesce(db.func.sum(PurchaseOrder.cash_amount), 0))
        .filter(
            PurchaseOrder.date >= year_start,
            PurchaseOrder.date < next_year_start
        )
        .scalar()
    ) or 0

    pondo_remaining = total_revenue - total_expenses

    expected_gross_revenue = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(SalesOrderItem.quantity * SalesOrderItem.selling_price),
                0
            )
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
        .filter(
            SalesOrder.order_date >= year_start,
            SalesOrder.order_date < next_year_start
        )
        .scalar()
    ) or 0

    expected_profit = (
        db.session.query(
            db.func.coalesce(
                db.func.sum(
                    SalesOrderItem.quantity * (
                        SalesOrderItem.selling_price - SalesOrderItem.unit_cost
                    )
                ),
                0
            )
        )
        .join(SalesOrder, SalesOrderItem.sales_order_id == SalesOrder.id)
        .filter(
            SalesOrder.order_date >= year_start,
            SalesOrder.order_date < next_year_start
        )
        .scalar()
    ) or 0

    actual_profit = total_revenue - total_expenses

    recent_sales_orders = (
        sales_order_query()
        .filter(
            SalesOrder.order_date >= year_start,
            SalesOrder.order_date < next_year_start
        )
        .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc(), SalesOrder.id.desc())
        .limit(10)
        .all()
    )

    # Recent invoices
    recent_invoices = (
        db.session.query(
            Invoice.invoice_number,
            Invoice.invoice_type,
            Invoice.invoice_date,
            Invoice.total_amount,
            Invoice.amount_paid,
            Invoice.balance,
            Invoice.status,
            Client.client_name,
            Invoice.uploaded_client_name
        )
        .select_from(Invoice)
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True)
        .join(Client, SalesOrder.client_id == Client.id, isouter=True)
        .filter(
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start
        )
        .order_by(Invoice.created_at.desc())
        .limit(10)
        .all()
    )

    # Load all orders once, then group in Python to avoid repeated queries
    all_orders = (
        SalesOrder.query
        .options(
            selectinload(SalesOrder.invoices),
            selectinload(SalesOrder.items)
        )
        .filter(
            SalesOrder.order_date >= year_start,
            SalesOrder.order_date < next_year_start
        )
        .order_by(SalesOrder.order_date.desc())
        .all()
    )

    client_registry = build_client_registry()
    client_groups = {}
    client_key_by_id = {}
    for client in Client.query.order_by(Client.client_name.asc(), Client.id.asc()).all():
        client_key = normalize_client_match_key(client.client_name) or f'CLIENT-{client.id}'
        group = client_groups.setdefault(client_key, {
            'primary_client': client,
            'client_ids': set(),
        })
        group['client_ids'].add(client.id)
        client_key_by_id[client.id] = client_key

    orders_by_client = defaultdict(list)
    for order in all_orders:
        client_key = client_key_by_id.get(order.client_id)
        if not client_key:
            client_name = order.client.client_name if order.client else order.company_name
            client_key = normalize_client_match_key(client_name) or f'CLIENT-{order.client_id or order.id}'
        orders_by_client[client_key].append(order)

    invoice_counts_by_client = defaultdict(int)
    standalone_financials_by_client = defaultdict(lambda: {
        'total_amount': 0.0,
        'total_paid': 0.0,
        'current_balance': 0.0,
    })
    unmapped_clients = {}
    year_invoices = (
        Invoice.query
        .options(selectinload(Invoice.sales_order))
        .filter(
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start
        )
        .all()
    )
    for invoice in year_invoices:
        if invoice.sales_order:
            client_key = client_key_by_id.get(invoice.sales_order.client_id)
            if client_key:
                invoice_counts_by_client[client_key] += 1
            continue
        normalized_name = normalize_client_match_key(invoice.uploaded_client_name)
        registry_entry = client_registry['lookup'].get(normalized_name)
        if not registry_entry:
            fuzzy_match = find_client_match(invoice.uploaded_client_name, client_registry)
            if (
                fuzzy_match
                and float(fuzzy_match.get('match_percent') or 0) >= CLIENT_REVIEW_MATCH_PERCENT
                and not is_client_fuzzy_exception(invoice.uploaded_client_name, fuzzy_match.get('client_name'))
            ):
                registry_entry = {
                    'client_id': fuzzy_match['client_id'],
                    'client_name': fuzzy_match['client_name'],
                }
        if registry_entry:
            client_key = client_key_by_id.get(registry_entry['client_id'])
            if client_key:
                total_amount = float(
                    invoice.total_amount
                    if invoice.total_amount is not None
                    else invoice.amount_paid or 0
                )
                paid_amount = max(float(invoice.amount_paid or 0), 0)
                balance = max(float(
                    invoice.balance
                    if invoice.balance is not None
                    else total_amount - paid_amount
                ), 0)
                invoice_counts_by_client[client_key] += 1
                standalone_financials_by_client[client_key]['total_amount'] += total_amount
                standalone_financials_by_client[client_key]['total_paid'] += paid_amount
                standalone_financials_by_client[client_key]['current_balance'] += balance
                continue

        display_name = clean_text(
            invoice.uploaded_client_name,
            keep_period=True,
            keep_ampersand=True
        ).upper() or 'UNMAPPED CLIENT'
        unmapped_key = normalized_name or f'UNMAPPED-{invoice.id}'
        unmapped = unmapped_clients.setdefault(unmapped_key, {
            'client_name': display_name,
            'total_invoices': 0,
            'total_amount': 0.0,
            'total_paid': 0.0,
            'current_balance': 0.0,
        })
        total_amount = float(
            invoice.total_amount
            if invoice.total_amount is not None
            else invoice.amount_paid or 0
        )
        paid_amount = max(float(invoice.amount_paid or 0), 0)
        balance = max(float(
            invoice.balance
            if invoice.balance is not None
            else total_amount - paid_amount
        ), 0)
        unmapped['total_invoices'] += 1
        unmapped['total_amount'] += total_amount
        unmapped['total_paid'] += paid_amount
        unmapped['current_balance'] += balance

    client_summaries = []
    analysis_clients = get_clients_analysis(db, app_models(), year_start, next_year_start).get('clients', [])

    analysis_by_client_key = defaultdict(lambda: {
        'client_performance_score': 0.0,
        'cohort': None,
        'value_status': None,
        'balance_status': None,
        'last_purchase': None,
    })
    for item in analysis_clients:
        client_ids = item.get('client_ids') or []
        item_client_keys = {
            client_key_by_id.get(client_id)
            for client_id in client_ids
            if client_key_by_id.get(client_id)
        }
        for client_key in item_client_keys:
            summary = analysis_by_client_key[client_key]
            if float(item.get('client_performance_score') or 0) > float(summary.get('client_performance_score') or 0):
                summary['client_performance_score'] = item.get('client_performance_score')
                summary['cohort'] = item.get('cohort')
                summary['value_status'] = item.get('value_status')
            if item.get('balance_status') == 'Unsettled Balance':
                summary['balance_status'] = item.get('balance_status')
            elif not summary.get('balance_status'):
                summary['balance_status'] = item.get('balance_status')
            if item.get('last_purchase') and (
                not summary.get('last_purchase') or item.get('last_purchase') > summary.get('last_purchase')
            ):
                summary['last_purchase'] = item.get('last_purchase')

    for client_key, group in client_groups.items():
        client = group['primary_client']
        client_orders = orders_by_client.get(client_key, [])
        unpaid_sales_orders = []
        client_revenue = 0.0
        client_paid = 0.0
        current_balance = 0.0

        for order in client_orders:
            order_total = sum(
                nz(item.quantity) * nz(item.selling_price)
                for item in order.items
            )
            paid_total = sum(
                nz(invoice.amount_paid)
                for invoice in order.invoices
                if invoice.invoice_date
                and year_start <= invoice.invoice_date < next_year_start
            )
            client_revenue += order_total
            client_paid += paid_total
            unpaid_balance = max(order_total - paid_total, 0)
            current_balance += unpaid_balance

            if not order.invoices or unpaid_balance > 0.01:
                unpaid_sales_orders.append({
                    'id': order.id,
                    'so_number': order.so_number,
                    'order_date': order.order_date.isoformat() if order.order_date else None,
                    'total_amount': order_total,
                    'paid_total': paid_total,
                    'unpaid_balance': unpaid_balance,
                    'status': order.status
                })

        standalone = standalone_financials_by_client.get(client_key, {})
        client_revenue += float(standalone.get('total_amount', 0) or 0)
        client_paid += float(standalone.get('total_paid', 0) or 0)
        current_balance += float(standalone.get('current_balance', 0) or 0)

        analysis_client = analysis_by_client_key.get(client_key, {})
        client_summaries.append({
            'id': client.id,
            'client_name': client.client_name,
            'contact_info': client.contact_info,
            'total_invoices': invoice_counts_by_client.get(client_key, 0),
            'current_balance': round(current_balance, 2),
            'total_revenue': round(client_revenue, 2),
            'total_paid': round(client_paid, 2),
            'balance_status': analysis_client.get('balance_status') or ('Settled' if current_balance <= 0.01 else 'Unsettled Balance'),
            'client_performance_score': analysis_client.get('client_performance_score', 0),
            'cohort': analysis_client.get('cohort') or analysis_client.get('value_status') or 'Low Order Activity',
            'last_purchase': analysis_client.get('last_purchase'),
            'unpaid_sales_order_count': len(unpaid_sales_orders),
            'unpaid_sales_orders': unpaid_sales_orders
        })

    unmapped_clients_list = sorted(
        (
            {
                **item,
                'total_amount': round(item['total_amount'], 2),
                'total_paid': round(item['total_paid'], 2),
                'current_balance': round(item['current_balance'], 2),
            }
            for item in unmapped_clients.values()
        ),
        key=lambda item: (-item['current_balance'], item['client_name'])
    )
    accounts_receivable_total = sum(
        float(client['current_balance'] or 0)
        for client in client_summaries
    ) + sum(float(client['current_balance'] or 0) for client in unmapped_clients_list)
    accounts_receivable_count = sum(
        1 for client in client_summaries
        if float(client['current_balance'] or 0) > 0.01
    ) + sum(
        1 for client in unmapped_clients_list
        if float(client['current_balance'] or 0) > 0.01
    )

    # Analytics data
    selected_year_revenue = total_revenue

    aging_0_30 = (
        db.session.query(db.func.coalesce(db.func.sum(Invoice.balance), 0))
        .filter(
            Invoice.balance > MONEY_TOLERANCE,
            Invoice.invoice_date >= max(year_start, thirty_days_ago.date()),
            Invoice.invoice_date < next_year_start
        )
        .scalar()
    ) or 0

    monthly_cashflow = [
        {
            'month': month,
            'cash_in': 0.0,
            'cash_out': 0.0
        }
        for month in range(1, 13)
    ]
    invoice_cash_rows = (
        db.session.query(
            extract('month', CollectionReceipt.receipt_date).label('month'),
            func.coalesce(func.sum(CollectionReceipt.collected_total), 0).label('total')
        )
        .filter(
            CollectionReceipt.receipt_date >= year_start,
            CollectionReceipt.receipt_date < next_year_start
        )
        .group_by(extract('month', CollectionReceipt.receipt_date))
        .all()
    )
    legacy_invoice_cash_rows = (
        db.session.query(
            extract('month', Invoice.invoice_date).label('month'),
            func.coalesce(func.sum(Invoice.amount_paid), 0).label('total')
        )
        .filter(
            Invoice.amount_paid > 0,
            ~Invoice.collection_receipts.any(),
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start,
        )
        .group_by(extract('month', Invoice.invoice_date))
        .all()
    )
    purchase_cash_rows = (
        db.session.query(
            extract('month', PurchaseOrder.date).label('month'),
            func.coalesce(func.sum(PurchaseOrder.cash_amount), 0).label('total')
        )
        .filter(
            PurchaseOrder.date >= year_start,
            PurchaseOrder.date < next_year_start
        )
        .group_by(extract('month', PurchaseOrder.date))
        .all()
    )
    for row in invoice_cash_rows:
        monthly_cashflow[int(row.month) - 1]['cash_in'] = float(row.total or 0)
    for row in legacy_invoice_cash_rows:
        monthly_cashflow[int(row.month) - 1]['cash_in'] += float(row.total or 0)
    for row in purchase_cash_rows:
        monthly_cashflow[int(row.month) - 1]['cash_out'] = float(row.total or 0)

    dashboard_data = {
        'accounts_receivable': {
            'total_amount': accounts_receivable_total,
            'invoice_count': accounts_receivable_count
        },
        'total_revenue': {
            'total_amount': total_revenue,
            'payment_count': payment_count,
            'total_tax_collected': total_tax_collected
        },
        'revenue_kpis': {
            'expected_gross_revenue': expected_gross_revenue,
            'actual_gross_revenue': total_revenue,
            'expected_profit': expected_profit,
            'actual_profit': actual_profit
        },
        'total_expenses': {
            'total_amount': total_expenses
        },
        'pondo_remaining': {
            'total_amount': pondo_remaining
        },
        'recent_sales_orders': [
            {
                'id': order.id,
                'client_name': order.client_name,
                'order_date': order.order_date.isoformat() if order.order_date else None,
                'item_count': order.item_count,
                'total_amount': order.total_amount,
                'status': order.status
            }
            for order in recent_sales_orders
        ],
        'recent_invoices': [
            {
                'invoice_number': inv.invoice_number,
                'invoice_type': inv.invoice_type,
                'client_name': inv.client_name or inv.uploaded_client_name or 'Admin Upload',
                'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                'total_amount': inv.total_amount,
                'amount_paid': inv.amount_paid,
                'balance': inv.balance,
                'status': inv.status
            }
            for inv in recent_invoices
        ],
        'clients_summary': client_summaries,
        'unmapped_clients': unmapped_clients_list,
        'selected_year_revenue': selected_year_revenue,
        'aging_0_30': aging_0_30,
        'monthly_cashflow': monthly_cashflow,
        'selected_year': selected_year,
        'available_years': available_years,
        'timeline_label': str(selected_year)
    }

    return render_template('dashboard.html', dashboard_data=dashboard_data)

@app.route('/sales-order')
@login_required
@role_required(*SALES_ROLES)
def sales_order():
    return render_template('sales_order.html')

@app.route('/reports')
@login_required
@role_required('manager', 'admin')
def reports():
    return render_template('reports.html', datetime=datetime, available_years=report_available_years())

@app.route('/api/reports/sales-orders', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def get_sales_order_reports():
    try:
        filters = parse_report_date_filter()
        report_rows = sales_report_itemized_rows(filters)
        year_month = db_month_key(SalesOrder.order_date).label('year_month')

        monthly_query = (
            db.session.query(
                year_month,
                func.sum(SalesOrderItem.total).label('monthly_total')
            )
            .join(SalesOrderItem, SalesOrder.id == SalesOrderItem.sales_order_id)
            .filter(
                SalesOrder.order_date.isnot(None),
                SalesOrder.order_date >= filters['start_date'],
                SalesOrder.order_date < filters['end_date']
            )
            .group_by(year_month)
            .order_by(asc(year_month))
        )
        monthly_summary = monthly_query.all()

        monthly_data = [
            {'month': row.year_month, 'monthly_total': float(row.monthly_total or 0)}
            for row in monthly_summary
        ]

        total_revenue = float(sum(row['total'] for row in report_rows))

        return jsonify({
            'success': True,
            'rows': report_rows,
            'monthly_summary': monthly_data,
            'total_revenue': total_revenue,
            'filter': {
                'available_years': filters['available_years'],
                'selected_year': filters['selected_year'],
                'period': filters['period'],
                'quarter': filters['quarter'],
                'month': filters['month'],
                'label': filters['label'],
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reports/expenses', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def get_expense_reports():
    try:
        filters = parse_report_date_filter()
        rows = expense_report_rows(filters)
        return jsonify({
            'success': True,
            'rows': rows,
            'total_expenses': float(sum(row['cash_amount'] for row in rows)),
            'total_balance': float(sum(row['net_balance'] for row in rows)),
            'filter': {
                'available_years': filters['available_years'],
                'selected_year': filters['selected_year'],
                'period': filters['period'],
                'quarter': filters['quarter'],
                'month': filters['month'],
                'label': filters['label'],
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reports/revenue', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def get_revenue_reports():
    try:
        filters = parse_report_date_filter()
        rows = revenue_report_rows(filters)
        return jsonify({
            'success': True,
            'rows': rows,
            'total_paid_revenue': float(sum(row['amount_paid'] for row in rows)),
            'total_invoice_amount': float(sum(row['total_amount'] for row in rows)),
            'total_balance': float(sum(row['balance'] for row in rows)),
            'filter': {
                'available_years': filters['available_years'],
                'selected_year': filters['selected_year'],
                'period': filters['period'],
                'quarter': filters['quarter'],
                'month': filters['month'],
                'label': filters['label'],
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reports/historical-transactions', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def get_historical_transaction_reports():
    try:
        filters = parse_report_date_filter()
        rows = report_historical_transaction_rows(filters)
        return jsonify({
            'success': True,
            'rows': rows,
            'total_inflow': float(sum(row['amount'] for row in rows if row['flow_direction'] == 'INFLOW')),
            'total_outflow': float(sum(row['amount'] for row in rows if row['flow_direction'] == 'OUTFLOW')),
            'filter': {
                'available_years': filters['available_years'],
                'selected_year': filters['selected_year'],
                'period': filters['period'],
                'quarter': filters['quarter'],
                'month': filters['month'],
                'label': filters['label'],
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reports/historical-transactions/export.csv', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def export_historical_transactions_csv():
    filters = parse_report_date_filter()
    fields = [
        'source_type', 'source_id', 'transaction_date', 'financial_stage',
        'flow_direction', 'flow_status', 'party_name', 'party_role', 'amount',
        'balance_amount', 'category', 'status', 'description'
    ]
    return csv_response('historical-transactions.csv', report_historical_transaction_rows(filters), fields)

@app.route('/api/reports/audit-export', methods=['POST'])
@login_required
@role_required('manager', 'admin')
def audit_report_export():
    try:
        data = request.get_json() or {}
        report_name = data.get('report') or 'report'
        requested_export_type = clean_code(data.get('export_type') or 'PRINT').upper()
        export_type = 'PRINT' if requested_export_type in {'PRINT', 'PDF'} else requested_export_type
        log_audit('EXPORT_REPORT', 'reports', report_name, None, {'export_type': export_type})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get-clients')
@login_required
@role_required(*ALL_BUSINESS_ROLES)
def get_clients():
    try:
        clients_list = Client.query.order_by(Client.created_at.desc()).all()
        return jsonify({
            'success': True,
            'clients': [
                {
                    'id': client.id,
                    'client_name': client.client_name,
                    'contact_info': client.contact_info,
                    'status': client.status or 'ACTIVE',
                    'total_revenue': client.total_revenue or 0,
                    'total_paid': client.total_paid or 0,
                    'total_balance': client.total_balance or 0,
                    'balance_status': client.balance_status or 'Settled',
                    'last_invoice_date': client.last_invoice_date.isoformat() if client.last_invoice_date else None,
                    'last_payment_date': client.last_payment_date.isoformat() if client.last_payment_date else None,
                    'aliases': [alias.alias_name for alias in client.aliases if alias.status == 'ACTIVE'],
                    'created_at': client.created_at.isoformat() if client.created_at else None
                } for client in clients_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/client-match-preview', methods=['POST'])
@login_required
@role_required(*OPERATIONS_ROLES)
def client_match_preview():
    try:
        payload = request.get_json() or {}
        client_names = payload.get('client_names') or []
        if not isinstance(client_names, list):
            return jsonify({'success': False, 'error': 'client_names must be a list'}), 400
        queue = build_client_review_queue(client_names)
        return jsonify({
            'success': True,
            'matched': queue['matched'],
            'review_items': queue['review_items'],
            'total_unique_clients': queue['total_unique_clients'],
            'review_count': len(queue['review_items']),
            'matched_count': len(queue['matched']),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/create-client', methods=['POST'])
@login_required
@role_required(*OPERATIONS_ROLES)
def create_client():
    try:
        data = request.get_json()
        resolution = resolve_client_name(
            data.get('client_name', ''),
            parse_resolution_payload(data),
            create_client=True,
            contact_info=data.get('contact_info', '')
        )
        if resolution['status'] == 'needs_choice':
            return jsonify({
                'success': False,
                'needs_resolution': True,
                'client_resolution': client_resolution_public(resolution),
                'error': 'Client name is similar to an existing client. Confirm whether to use the suggested client or create a new client.'
            }), 409
        if resolution.get('client'):
            client = resolution['client']
            if resolution['status'] in ('resolved', 'auto_match'):
                refresh_client_financials(client)
                db.session.commit()
                return jsonify({
                    'success': True,
                    'client_id': client.id,
                    'client_name': client.client_name,
                    'message': 'Existing client matched successfully'
                })
        if resolution['status'] == 'ignored':
            return jsonify({'success': False, 'error': 'Client was ignored and no client record was created'}), 400
        
        log_audit('CREATE', 'clients', None, None, {'client_name': client.client_name})
        refresh_client_financials(client)
        db.session.commit()
        
        return jsonify({'success': True, 'client_id': client.id, 'client_name': client.client_name, 'message': 'Client created successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/upload-excel', methods=['POST'])
@login_required
@role_required(*OPERATIONS_ROLES)
def upload_excel():
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    if not file.filename.endswith('.xlsx'):
        return jsonify({'success': False, 'error': 'Please upload an Excel file'})
    
    try:
        # Read Excel file
        df = pd.read_excel(file)
        data = df.fillna('').to_dict('records')
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/compiled-sales/preview', methods=['POST'])
@login_required
@role_required('admin')
def admin_compiled_sales_preview():
    denied = admin_required_json()
    if denied:
        return denied
    upload = request.files.get('file')
    if not upload or not upload.filename:
        return jsonify({'success': False, 'error': 'Select the compiled Sales Order Excel file.'}), 400
    if not upload.filename.lower().endswith(('.xlsx', '.xls')):
        return jsonify({'success': False, 'error': 'The compiled Sales Order upload must be an Excel file.'}), 400
    try:
        workbook = pd.ExcelFile(upload)
        if 'Compiled' not in workbook.sheet_names:
            return jsonify({'success': False, 'error': 'The workbook must contain a sheet named Compiled.'}), 400
        frame = pd.read_excel(workbook, sheet_name='Compiled')
        actual_headers = [str(column).strip().upper() for column in frame.columns]
        missing_headers = [header for header in COMPILED_SALES_HEADERS if header not in actual_headers]
        if missing_headers:
            return jsonify({
                'success': False,
                'error': f"Missing required columns: {', '.join(missing_headers)}"
            }), 400
        frame.columns = actual_headers
        frame = frame[list(COMPILED_SALES_HEADERS)].dropna(how='all')
        rows = [
            _compiled_sales_row(record, row_number)
            for row_number, record in enumerate(frame.to_dict('records'), start=2)
        ]
        validate_compiled_sales_rows(rows)
        groups = group_compiled_sales_rows(rows)
        existing = existing_compiled_sales_orders()
        duplicate_orders = [
            {
                'compound_key': group['compound_key'],
                'so_number': group['so_number'],
                'sales_staff': group['sales_staff'],
                'existing_id': existing[group['compound_key']].id,
            }
            for group in groups if group['compound_key'] in existing
        ]
        registry = build_client_registry()
        client_resolutions = []
        seen_companies = set()
        for row in rows:
            company_key = normalize_client_match_key(row['company_name'])
            if company_key in seen_companies:
                continue
            seen_companies.add(company_key)
            resolution = resolve_client_name(
                row['company_name'],
                create_client=False,
                registry=registry,
            )
            if resolution['status'] in ('needs_choice', 'create_new'):
                client_resolutions.append(client_resolution_public(resolution))

        invalid_rows = [row for row in rows if row['blocking_issues']]
        warning_rows = [row for row in rows if row['issues'] and not row['blocking_issues']]
        return jsonify({
            'success': True,
            'filename': upload.filename,
            'rows': rows,
            'summary': {
                'source_rows': len(rows),
                'sales_orders': len(groups),
                'branches': sum(len(group['branches']) for group in groups),
                'multi_branch_orders': sum(len(group['branches']) > 1 for group in groups),
                'invalid_rows': len(invalid_rows),
                'warning_rows': len(warning_rows),
                'duplicate_orders': len(duplicate_orders),
                'new_orders': len(groups) - len(duplicate_orders),
            },
            'duplicate_orders': duplicate_orders,
            'client_resolutions': client_resolutions,
        })
    except Exception as exc:
        app.logger.exception('Compiled Sales Order preview failed')
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/admin/compiled-sales/commit', methods=['POST'])
@login_required
@role_required('admin')
def admin_compiled_sales_commit():
    denied = admin_required_json()
    if denied:
        return denied
    payload = request.get_json() or {}
    submitted_rows = payload.get('rows') or []
    if not submitted_rows:
        return jsonify({'success': False, 'error': 'No compiled Sales Order rows are ready.'}), 400
    try:
        rows = [normalize_submitted_compiled_row(row) for row in submitted_rows]
        validate_compiled_sales_rows(rows)
        included_rows = [row for row in rows if row.get('included', True)]
        invalid_rows = [row for row in included_rows if row['blocking_issues']]
        if invalid_rows:
            return jsonify({
                'success': False,
                'error': 'Fix or exclude every invalid row before importing.',
                'invalid_rows': invalid_rows[:100],
            }), 400
        groups = group_compiled_sales_rows(rows)
        resolutions = parse_resolution_payload(payload)
        registry = build_client_registry()
        unresolved = []
        seen_companies = set()
        for group in groups:
            company_key = normalize_client_match_key(group['company_name'])
            if company_key in seen_companies:
                continue
            seen_companies.add(company_key)
            resolution = resolve_client_name(
                group['company_name'],
                resolutions,
                create_client=False,
                registry=registry,
            )
            if resolution['status'] == 'needs_choice':
                unresolved.append(client_resolution_public(resolution))
        if unresolved:
            return jsonify({
                'success': False,
                'needs_resolution': True,
                'error': 'Choose how to resolve the similar company names before importing.',
                'client_resolutions': unresolved,
            }), 409

        existing = existing_compiled_sales_orders()
        created_orders = 0
        created_branches = 0
        created_items = 0
        skipped_duplicates = []
        created_clients = 0
        for group in groups:
            if group['compound_key'] in existing:
                skipped_duplicates.append({
                    'compound_key': group['compound_key'],
                    'so_number': group['so_number'],
                    'sales_staff': group['sales_staff'],
                    'existing_id': existing[group['compound_key']].id,
                })
                continue
            resolution = resolve_client_name(
                group['company_name'],
                resolutions,
                create_client=True,
            )
            if resolution['status'] == 'ignored':
                continue
            if resolution['status'] == 'created':
                created_clients += 1
            client = resolution['client']
            branch_names = list(group['branches'].values())
            total_amount = round(sum(float(row['total_revenue'] or 0) for row in group['rows']), 2)
            order = SalesOrder(
                so_number=group['so_number'],
                client_id=client.id,
                company_name=resolution['client_name'],
                official_client_name=resolution['client_name'],
                original_entered_client_name=resolution.get('original_entered_client_name') or group['company_name'],
                store_name=group['store_name'],
                store_branch=branch_names[0] if len(branch_names) == 1 else 'MULTIPLE BRANCHES',
                order_date=parse_date_value(group['order_date'], default_today=False),
                sales_staff=group['sales_staff'],
                terms=30,
                total_amount=total_amount,
                status='PENDING',
                notes=f"Compiled Excel import: {payload.get('filename') or 'uploaded workbook'}",
            )
            db.session.add(order)
            db.session.flush()
            branches = {}
            for branch_key, branch_name in group['branches'].items():
                branch = SalesOrderBranch(
                    sales_order_id=order.id,
                    branch_name=branch_name,
                    normalized_branch_key=branch_key,
                )
                db.session.add(branch)
                db.session.flush()
                branches[branch_key] = branch
                created_branches += 1
            for row in group['rows']:
                db.session.add(SalesOrderItem(
                    sales_order_id=order.id,
                    sales_order_branch_id=branches[row['branch_key']].id,
                    particular=row['particular'],
                    quantity=row['quantity'],
                    unit_cost=float(row['unit_cost']),
                    selling_price=float(row['selling_price']),
                    total=float(row['total_revenue']),
                ))
                created_items += 1
            created_orders += 1

        excluded_rows = len(rows) - len(included_rows)
        log_audit('UPLOAD_COMPILED_SALES', 'sales_orders', None, None, {
            'filename': payload.get('filename'),
            'created_orders': created_orders,
            'created_branches': created_branches,
            'created_items': created_items,
            'created_clients': created_clients,
            'skipped_duplicates': len(skipped_duplicates),
            'excluded_rows': excluded_rows,
        })
        refresh_client_financials()
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Imported {created_orders} Sales Orders and {created_items} items.',
            'created_orders': created_orders,
            'created_branches': created_branches,
            'created_items': created_items,
            'created_clients': created_clients,
            'skipped_duplicates': skipped_duplicates,
            'excluded_rows': excluded_rows,
        })
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Compiled Sales Order import failed')
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/admin/upload-preview/<interface>', methods=['POST'])
@login_required
@role_required('admin')
def admin_upload_preview(interface):
    denied = admin_required_json()
    if denied:
        return denied
    if interface not in ('sales_order', 'purchase_order', 'invoice'):
        return jsonify({'success': False, 'error': 'Unknown upload interface'}), 400

    uploads = request.files.getlist('files')
    if not uploads:
        single = request.files.get('file')
        uploads = [single] if single else []
    if not uploads:
        return jsonify({'success': False, 'error': 'No files uploaded'}), 400

    try:
        rows = []
        for upload in uploads:
            name = (upload.filename or '').lower()
            if name.endswith('.csv'):
                df = read_admin_csv_upload(upload)
            elif name.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(upload)
            else:
                return jsonify({'success': False, 'error': f'Unsupported file type: {upload.filename}'}), 400
            for row_index, row in enumerate(df.fillna('').to_dict('records'), start=2):
                try:
                    normalized = normalize_upload_row(interface, row)
                except ValueError as validation_error:
                    return jsonify({
                        'success': False,
                        'error': f'{upload.filename}, row {row_index}: {validation_error}'
                    }), 400
                normalized['_source_file'] = upload.filename
                normalized['_source_row'] = row_index
                rows.append(normalized)

        amount_key = 'cash_amount' if interface == 'purchase_order' else 'total_amount'
        warning_fields = []
        for index, row in enumerate(rows, start=1):
            if interface == 'sales_order':
                warning_fields.append((f'Row {index} Sales Order date', row.get('order_date')))
            elif interface == 'invoice':
                warning_fields.append((f'Row {index} Invoice date', row.get('invoice_date')))
            elif interface == 'purchase_order':
                warning_fields.extend([
                    (f'Row {index} Check date', row.get('check_date')),
                    (f'Row {index} Expense date', row.get('date')),
                    (f'Row {index} OR date', row.get('or_date')),
                ])
        conflicts = []
        grouped_invoice_count = None
        if interface == 'invoice':
            grouped_invoice_rows, conflicts = prepare_invoice_upload_rows(rows)
            grouped_invoice_count = len(grouped_invoice_rows)
        return jsonify({
            'success': True,
            'rows': rows,
            'outliers': zscore_outliers(rows, amount_key),
            'conflicts': conflicts,
            'grouped_invoice_count': grouped_invoice_count,
            'warnings': future_date_warnings(dict(warning_fields)),
            'documentation': [
                'Upload: select one or more CSV/Excel files for this interface.',
                'Cleaning: dates, amounts, names, and special characters are normalized into database fields.',
                'Outlier Identifier: Z-score flags amount values with absolute score >= 2.5.',
                'Excel Mapping: recognized headers are mapped into existing 404 Dashboard model variables before saving.'
            ]
        })
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Admin upload preview failed for %s', interface)
        return jsonify({
            'success': False,
            'error': public_error_message(e, 'The upload could not be read. Check the CSV format and values.'),
        }), 400

@app.route('/admin/upload-commit/<interface>', methods=['POST'])
@login_required
@role_required('admin')
def admin_upload_commit(interface):
    denied = admin_required_json()
    if denied:
        return denied
    try:
        if interface not in ('sales_order', 'purchase_order', 'invoice'):
            return jsonify({'success': False, 'error': 'Unknown upload interface'}), 400
        payload = request.get_json(silent=True) or {}
        rows = payload.get('rows', [])
        resolutions = parse_resolution_payload(payload)
        if not rows:
            return jsonify({'success': False, 'error': 'No rows to upload'}), 400
        if interface == 'invoice':
            return commit_invoice_upload_batch(rows)
        if interface == 'sales_order':
            unresolved = []
            registry = build_client_registry()
            for idx, row in enumerate(rows, start=1):
                resolution = resolve_client_name(
                    row.get('company_name') or row.get('client_name') or 'UNMAPPED CLIENT',
                    resolutions,
                    create_client=False,
                    registry=registry,
                )
                if resolution['status'] == 'needs_choice':
                    unresolved.append(client_resolution_public(resolution, idx))
            if unresolved:
                return jsonify({
                    'success': False,
                    'needs_resolution': True,
                    'client_resolutions': unresolved,
                    'error': 'Some uploaded company names look similar to existing clients. Choose whether to use the suggestion or create a new client.'
                }), 409
        created = 0
        updated = 0
        client_registry = build_client_registry() if interface == 'invoice' else None
        upload_warning_fields = []
        for index, row in enumerate(rows, start=1):
            if interface == 'sales_order':
                upload_warning_fields.append((f'Row {index} Sales Order date', row.get('order_date')))
            elif interface == 'invoice':
                upload_warning_fields.append((f'Row {index} Invoice date', row.get('invoice_date')))
            elif interface == 'purchase_order':
                upload_warning_fields.extend([
                    (f'Row {index} Check date', row.get('check_date')),
                    (f'Row {index} Expense date', row.get('date')),
                    (f'Row {index} OR date', row.get('or_date')),
                ])
        warnings = future_date_warnings(dict(upload_warning_fields))
        for row in rows:
            if interface == 'sales_order':
                original_company_name = row.get('company_name') or row.get('client_name') or 'UNMAPPED CLIENT'
                try:
                    qty = parse_positive_whole_quantity(row.get('quantity') or 1)
                except ValueError as quantity_error:
                    db.session.rollback()
                    return jsonify({'success': False, 'error': str(quantity_error)}), 400
                resolution = resolve_client_name(
                    original_company_name,
                    resolutions,
                    create_client=True
                )
                if resolution['status'] == 'ignored':
                    continue
                client = resolution['client']
                client_name = resolution['client_name']
                so_number = normalize_sales_order_number(
                    row.get('so_number') or f"SO-{SalesOrder.query.count() + created + 1:06d}"
                )
                store_name = clean_text(row.get('store_name', '')) or clean_text(original_company_name, keep_period=True, keep_ampersand=True)
                branch_name = (clean_text(row.get('store_branch', '')) or DEFAULT_STORE_BRANCH).upper()
                sales_staff = normalized_sales_staff(row.get('sales_staff') or session.get('username', ''))
                duplicate = existing_compiled_sales_orders().get(compiled_sales_order_key(so_number, sales_staff))
                if duplicate:
                    continue
                order = SalesOrder(
                    so_number=so_number,
                    client_id=client.id,
                    company_name=client_name,
                    official_client_name=client_name,
                    original_entered_client_name=resolution.get('original_entered_client_name') or clean_text(original_company_name, keep_period=True, keep_ampersand=True).upper(),
                    store_name=store_name.upper(),
                    store_branch=branch_name,
                    order_date=parse_date_value(row.get('order_date')),
                    sales_staff=sales_staff,
                    terms=int(row.get('terms') or 30),
                    total_amount=float(row.get('total_amount') or 0),
                    status='PENDING'
                )
                db.session.add(order)
                db.session.flush()
                branch = SalesOrderBranch(
                    sales_order_id=order.id,
                    branch_name=branch_name,
                    normalized_branch_key=normalized_branch_key(branch_name),
                )
                db.session.add(branch)
                db.session.flush()
                price = float(row.get('selling_price') or row.get('total_amount') or 0)
                db.session.add(SalesOrderItem(
                    sales_order_id=order.id,
                    sales_order_branch_id=branch.id,
                    particular=row.get('particular') or 'UPLOADED ITEM',
                    quantity=qty,
                    unit_cost=float(row.get('unit_cost') or 0),
                    selling_price=price,
                    total=float(row.get('total_amount') or price * qty)
                ))
            elif interface == 'purchase_order':
                purchase_order_id = parse_optional_integer(row.get('purchase_order_id'))
                purchase_order = db.session.get(PurchaseOrder, purchase_order_id) if purchase_order_id else None
                is_update = purchase_order is not None
                if not purchase_order:
                    purchase_order = PurchaseOrder()
                    if purchase_order_id:
                        purchase_order.id = purchase_order_id
                    db.session.add(purchase_order)

                debits = []
                for debit in row.get('debits', []):
                    debit_type = str(debit.get('debit_type') or '').strip()
                    amount = float(debit.get('amount') or 0)
                    if debit_type in PURCHASE_ORDER_DEBIT_TYPES and amount > 0:
                        debits.append({
                            'debit_type': debit_type,
                            'amount': amount,
                        })
                total_debits = round(sum(debit['amount'] for debit in debits), 2)
                cash_amount = float(row.get('cash_amount') or 0)
                net_balance = round(cash_amount - total_debits, 2)

                purchase_order.check_voucher_number = row.get('check_voucher_number') or f"CV-{PurchaseOrder.query.count() + created + 1:06d}"
                purchase_order.check_number = row.get('check_number') or 'N/A'
                purchase_order.check_date = parse_date_value(row.get('check_date'), dayfirst=True)
                purchase_order.date = parse_date_value(row.get('date'), dayfirst=True)
                purchase_order.or_date = parse_date_value(row.get('or_date'), dayfirst=True) if row.get('or_date') else None
                purchase_order.ar_cr_or_number = row.get('ar_cr_or_number')
                purchase_order.po_number = row.get('po_number')
                purchase_order.lf_no = row.get('lf_no')
                purchase_order.particulars = row.get('particulars') or 'UPLOADED EXPENSE'
                purchase_order.supplier_payee = row.get('supplier_payee') or 'UNMAPPED SUPPLIER'
                purchase_order.tin_number = row.get('tin_number')
                purchase_order.cash_amount = cash_amount
                purchase_order.net_balance = net_balance
                purchase_order.status = 'PAID' if abs(net_balance) < 0.005 else 'PENDING'
                purchase_order.category = 'FIXED' if any(
                    debit['debit_type'] in FIXED_PURCHASE_ORDER_DEBIT_TYPES
                    for debit in debits
                ) else 'VARIABLE'

                if is_update:
                    PurchaseOrderDebit.query.filter_by(purchase_order_id=purchase_order.id).delete()
                    updated += 1
                db.session.flush()
                for debit in debits:
                    db.session.add(PurchaseOrderDebit(
                        purchase_order_id=purchase_order.id,
                        debit_type=debit['debit_type'],
                        amount=debit['amount'],
                    ))
            if interface != 'purchase_order' or not is_update:
                created += 1
        if interface in ('sales_order', 'invoice'):
            refresh_client_financials()
        log_audit('UPLOAD_COMMIT', f'{interface}s', None, None, {'created': created, 'updated': updated})
        db.session.commit()
        message = f'Uploaded {created} rows'
        if updated:
            message += f' and updated {updated} existing invoice(s)'
        return json_success({'created': created, 'updated': updated, 'message': message}, warnings)
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e), 'error_type': 'validation'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Admin upload commit failed for %s', interface)
        return jsonify({
            'success': False,
            'error': public_error_message(e, 'The upload could not be completed. No records were saved.'),
            'error_type': 'server',
        }), 500

@app.route('/auto-identify-fields', methods=['POST'])
@login_required
@role_required(*OPERATIONS_ROLES)
def auto_identify_fields():
    try:
        data = request.get_json().get('data', [])
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'})
        
        identified_fields = {}
        
        # Simple field identification logic
        for row_idx, row in enumerate(data):
            for col_name, value in row.items():
                if not value:
                    continue
                    
                value_str = str(value).strip().lower()
                
                # SO Number patterns
                if 'so' in value_str or value_str.isdigit() and len(value_str) >= 4:
                    identified_fields['so_number'] = {'value': value, 'row': row_idx, 'column': col_name}
                
                # Company name patterns
                elif any(keyword in value_str for keyword in ['company', 'corporation', 'inc', 'ltd']):
                    identified_fields['company_name'] = {'value': value, 'row': row_idx, 'column': col_name}
                
                # Store name patterns
                elif any(keyword in value_str for keyword in ['store', 'branch', 'outlet']):
                    if 'store_name' not in identified_fields:
                        identified_fields['store_name'] = {'value': value, 'row': row_idx, 'column': col_name}
                    else:
                        identified_fields['store_branch'] = {'value': value, 'row': row_idx, 'column': col_name}
                
                # Date patterns
                elif any(char in value_str for char in ['-', '/', '.']) and len(value_str) >= 8:
                    try:
                        # Try to parse as date
                        if '-' in value_str:
                            date_obj = datetime.strptime(value_str, '%Y-%m-%d')
                        elif '/' in value_str:
                            date_obj = datetime.strptime(value_str, '%m/%d/%Y')
                        else:
                            date_obj = datetime.strptime(value_str, '%m.%d.%Y')
                        
                        identified_fields['order_date'] = {
                            'value': date_obj.strftime('%Y-%m-%d'), 
                            'row': row_idx, 
                            'column': col_name
                        }
                    except:
                        pass
        
        return jsonify({'success': True, 'identified_fields': identified_fields})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-sales-order', methods=['POST'])
@login_required
@role_required(*SALES_ROLES)
def create_sales_order():
    try:
        data = request.get_json(silent=True) or {}
        warnings = future_date_warnings({'Sales Order date': data.get('order_date')})

        company_name = (data.get('company_name') or data.get('client_name') or '').strip()
        order_date = parse_date_value(data.get('order_date'), default_today=False)
        client_id = data.get('client_id')
        resolutions = parse_resolution_payload(data)

        if not company_name:
            return jsonify({'success': False, 'error': 'Company name is required'}), 400
        if not order_date:
            return jsonify({'success': False, 'error': 'Order date is required'}), 400

        valid_items = []
        for item_index, item in enumerate(data.get('items') or [], start=1):
            particular = clean_text(item.get('particular', ''), keep_period=True, keep_ampersand=True).upper()
            try:
                quantity = parse_positive_whole_quantity(
                    item.get('quantity') or item.get('qty'),
                    f'Item {item_index} quantity'
                )
            except ValueError as quantity_error:
                return jsonify({'success': False, 'error': str(quantity_error)}), 400
            unit_cost = parse_amount(item.get('unit_cost') or item.get('cost'))
            selling_price = parse_amount(item.get('selling_price') or item.get('item_price') or item.get('price'))
            calculated_total = selling_price * quantity
            total = parse_amount(item.get('total')) or calculated_total
            if total <= 0:
                total = calculated_total
            if particular and quantity > 0 and selling_price > 0:
                valid_items.append({
                    'particular': particular,
                    'quantity': quantity,
                    'unit_cost': unit_cost,
                    'selling_price': selling_price,
                    'total': total,
                })

        if not valid_items:
            return jsonify({'success': False, 'error': 'At least one valid line item is required'}), 400

        # Create or get client. The client basket is derived from sales order
        # items, so every order must be attached to the saved client id.
        client = None
        if client_id:
            client = db.session.get(Client, client_id)
        if not client:
            resolution = resolve_client_name(
                company_name,
                resolutions,
                create_client=True,
                contact_info=data.get('contact_info', '')
            )
            if resolution['status'] == 'needs_choice':
                return jsonify({
                    'success': False,
                    'needs_resolution': True,
                    'client_resolution': client_resolution_public(resolution),
                    'error': 'Company name is similar to an existing client. Confirm whether to use the suggested client or create a new client.'
                }), 409
            if resolution['status'] == 'ignored':
                return jsonify({'success': False, 'error': 'Client was ignored and cannot be used for a sales order'}), 400
            client = resolution['client']
            original_company_name = resolution.get('original_entered_client_name') or clean_text(company_name, keep_period=True, keep_ampersand=True).upper()
        else:
            original_company_name = clean_text(company_name or client.client_name, keep_period=True, keep_ampersand=True).upper()
        client_name = client.client_name
        
        # Generate SO number if not provided
        so_number = data.get('so_number')
        if not so_number:
            last_so = SalesOrder.query.order_by(SalesOrder.id.desc()).first()
            last_id = last_so.id if last_so else 0
            so_number = f"SO-{last_id + 1:06d}"
        so_number = normalize_sales_order_number(so_number)
        sales_staff = normalized_sales_staff(data.get('sales_staff') or session.get('username', ''))
        duplicate_key = compiled_sales_order_key(so_number, sales_staff)
        duplicate_order = existing_compiled_sales_orders().get(duplicate_key)
        if duplicate_order:
            return jsonify({
                'success': False,
                'error': f'This SO Number and Sales Staff combination already exists as record #{duplicate_order.id}.'
            }), 409
        
        # Create sales order
        store_name = clean_text(data.get('store_name', '')) or clean_text(company_name or client_name, keep_period=True, keep_ampersand=True)
        total_amount = sum(item['total'] for item in valid_items)
        terms_days = int(parse_amount(data.get('terms_days') or data.get('terms')) or 30)
        if terms_days <= 0:
            terms_days = 30
        branch_name = (clean_text(data.get('store_branch', '')) or DEFAULT_STORE_BRANCH).upper()
        sales_order = SalesOrder(
            so_number=so_number,
            order_date=order_date,
            client_id=client.id,
            company_name=client_name,
            official_client_name=client_name,
            original_entered_client_name=original_company_name,
            store_name=store_name.upper(),
            store_branch=branch_name,
            sales_staff=sales_staff,
            total_amount=total_amount,
            terms=terms_days,
            notes=data.get('notes', ''),
            status='PENDING'
        )
        
        db.session.add(sales_order)
        db.session.flush()
        sales_order_branch = SalesOrderBranch(
            sales_order_id=sales_order.id,
            branch_name=branch_name,
            normalized_branch_key=normalized_branch_key(branch_name),
        )
        db.session.add(sales_order_branch)
        db.session.flush()
        
        # Add items
        for item in valid_items:
            order_item = SalesOrderItem(
                sales_order_id=sales_order.id,
                sales_order_branch_id=sales_order_branch.id,
                particular=item['particular'],
                quantity=item['quantity'],
                unit_cost=item['unit_cost'],
                selling_price=item['selling_price'],
                total=item['total']
            )
            db.session.add(order_item)
        
        refresh_client_financials(client)
        log_audit('CREATE', 'sales_orders', sales_order.id, None, {'so_number': sales_order.so_number, 'total_amount': sales_order.total_amount})
        db.session.commit()
        
        return json_success({
            'message': 'Sales order created successfully',
            'sales_order': {
                'id': sales_order.id,
                'so_number': sales_order.so_number,
                'company_name': sales_order.company_name,
                'store_name': sales_order.store_name,
                'store_branch': sales_order.store_branch,
                'order_date': sales_order.order_date.isoformat(),
                'sales_staff': sales_order.sales_staff,
                'total_amount': sales_order.total_amount,
                'status': sales_order.status,
            },
            'print_url': url_for('print_sales_order', so_id=sales_order.id)
        }, warnings)
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e), 'error_type': 'validation'}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Sales Order creation failed')
        return jsonify({
            'success': False,
            'error': public_error_message(e, 'The Sales Order could not be created.'),
            'error_type': 'server',
        }), 500

@app.route('/get-sales-orders')
@login_required
@role_required(*SALES_ROLES)
def get_sales_orders():
    try:
        sales_orders_list = (
            sales_order_query()
            .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc(), SalesOrder.id.desc())
            .limit(100)
            .all()
        )
        return jsonify({
            'success': True,
            'sales_orders': [sales_order_row_payload(so) for so in sales_orders_list]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-client-references')
@login_required
@role_required(*ALL_BUSINESS_ROLES)
def get_client_references():
    try:
        clients_list = (
            Client.query
            .options(selectinload(Client.aliases))
            .filter(Client.status != 'INACTIVE')
            .order_by(Client.client_name.asc())
            .limit(500)
            .all()
        )
        return jsonify({
            'success': True,
            'clients': [
                {
                    'id': client.id,
                    'client_name': client.client_name,
                    'status': client.status or 'ACTIVE',
                    'aliases': [alias.alias_name for alias in client.aliases if alias.status == 'ACTIVE'],
                } for client in clients_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/sales-orders/<int:so_id>/print')
@login_required
@role_required(*SALES_ROLES)
def print_sales_order(so_id):
    sales_order = SalesOrder.query.options(
        selectinload(SalesOrder.client),
        selectinload(SalesOrder.items),
    ).filter(SalesOrder.id == so_id).first_or_404()
    return render_template('sales_order_print.html', sales_order=sales_order, datetime=datetime)

@app.route('/invoices')
@login_required
@role_required(*ACCOUNTING_ROLES)
def invoices():
    return render_template('invoices.html')


@app.route('/get-invoices')
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_invoices():
    try:
        try:
            page = max(int(request.args.get('page', 1)), 1)
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = min(max(int(request.args.get('page_size', 50)), 1), 100)
        except (TypeError, ValueError):
            page_size = 50
        invoice_type = (request.args.get('invoice_type') or '').upper()
        general_search = (request.args.get('general_search') or '').strip()
        cr_search = (request.args.get('cr_search') or '').strip()
        client_search = (request.args.get('client_search') or '').strip()

        invoice_query = db.session.query(
            Invoice.id, Invoice.invoice_number, Invoice.sales_order_id, SalesOrder.so_number,
            Invoice.invoice_type, Invoice.invoice_date, Invoice.summary, Invoice.total_amount,
            Invoice.payment_type, Invoice.cr_number, Invoice.payment_amount,
            Invoice.tax_amount_paid, Invoice.is_2307_checked,
            Invoice.amount_paid, Invoice.balance, Invoice.status, Client.client_name,
            Invoice.uploaded_client_name, Invoice.upload_source, Invoice.admin_upload_note
        ).select_from(Invoice).join(
            SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True
        ).join(
            Client, SalesOrder.client_id == Client.id
            , isouter=True
        )
        normalized_number = func.upper(func.trim(Invoice.invoice_number))
        known_prefix = or_(
            normalized_number.like('SI-%'),
            normalized_number.like('SVI-%'),
        )
        if invoice_type == 'SALES':
            invoice_query = invoice_query.filter(or_(
                normalized_number.like('SI-%'),
                and_(~known_prefix, func.upper(Invoice.invoice_type) == 'SALES'),
            ))
        elif invoice_type == 'SERVICE':
            invoice_query = invoice_query.filter(or_(
                normalized_number.like('SVI-%'),
                and_(~known_prefix, func.upper(Invoice.invoice_type) == 'SERVICE'),
            ))

        if general_search:
            pattern = f'%{general_search}%'
            general_filters = [
                Invoice.invoice_number.ilike(pattern),
                SalesOrder.so_number.ilike(pattern),
                Invoice.status.ilike(pattern),
                Invoice.invoice_type.ilike(pattern),
                Invoice.summary.ilike(pattern),
            ]
            parsed_general_date = parse_date_value(general_search, default_today=False)
            if parsed_general_date:
                general_filters.append(Invoice.invoice_date == parsed_general_date)
            invoice_query = invoice_query.filter(or_(*general_filters))

        if cr_search:
            cr_pattern = f'%{normalize_cr_number(cr_search)}%'
            invoice_query = invoice_query.filter(
                Invoice.collection_receipts.any(
                    CollectionReceipt.normalized_cr_number.ilike(cr_pattern)
                )
            )

        if client_search:
            client_pattern = f'%{client_search}%'
            alias_client_ids = db.session.query(ClientAlias.client_id).filter(
                ClientAlias.status == 'ACTIVE',
                ClientAlias.alias_name.ilike(client_pattern),
            )
            invoice_query = invoice_query.filter(or_(
                Client.client_name.ilike(client_pattern),
                Invoice.uploaded_client_name.ilike(client_pattern),
                SalesOrder.company_name.ilike(client_pattern),
                SalesOrder.official_client_name.ilike(client_pattern),
                SalesOrder.original_entered_client_name.ilike(client_pattern),
                Client.id.in_(alias_client_ids),
            ))

        invoice_count = invoice_query.count()
        invoices_list = (
            invoice_query
            .order_by(Invoice.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        invoice_ids = [item.id for item in invoices_list]
        receipt_rows = (
            CollectionReceipt.query
            .filter(CollectionReceipt.invoice_id.in_(invoice_ids))
            .order_by(
                CollectionReceipt.invoice_id,
                CollectionReceipt.receipt_date.desc(),
                CollectionReceipt.id.desc(),
            )
            .all()
        ) if invoice_ids else []
        receipts_by_invoice = defaultdict(list)
        for receipt in receipt_rows:
            receipts_by_invoice[receipt.invoice_id].append(collection_receipt_payload(receipt))
        
        return jsonify({
            'success': True,
            'count': invoice_count,
            'page': page,
            'page_size': page_size,
            'total_pages': max((invoice_count + page_size - 1) // page_size, 1),
            'invoices': [
                {
                    'id': inv.id,
                    'invoice_number': clean_code(inv.invoice_number).upper(),
                    'sales_order_id': inv.sales_order_id,
                    'so_number': inv.so_number,
                    'invoice_type': canonical_invoice_type(inv.invoice_number, inv.invoice_type),
                    'client_name': inv.client_name or inv.uploaded_client_name or 'Admin Upload',
                    'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                    'summary': inv.summary,
                    'total_amount': inv.total_amount,
                    'payment_type': inv.payment_type,
                    'cr_number': inv.cr_number,
                    'payment_amount': inv.payment_amount,
                    'tax_amount_paid': inv.tax_amount_paid,
                    'is_2307_checked': inv.is_2307_checked,
                    'amount_paid': inv.amount_paid,
                    'balance': inv.balance,
                    'status': inv.status,
                    'uploaded_client_name': inv.uploaded_client_name,
                    'upload_source': inv.upload_source,
                    'admin_upload_note': inv.admin_upload_note,
                    'receipt_count': len(receipts_by_invoice[inv.id]),
                    'latest_cr_number': (
                        receipts_by_invoice[inv.id][0]['cr_number']
                        if receipts_by_invoice[inv.id] else inv.cr_number
                    ),
                } for inv in invoices_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-pending-sales-orders')
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_pending_sales_orders():
    try:
        search = (request.args.get('q') or '').strip()
        try:
            limit = min(max(int(request.args.get('limit', 25)), 1), 50)
        except (TypeError, ValueError):
            limit = 25

        query = sales_order_query(statuses=['PENDING', 'PARTIAL'], outstanding_only=True)
        if search:
            pattern = f'%{search}%'
            search_filters = [
                SalesOrder.so_number.ilike(pattern),
                SalesOrder.company_name.ilike(pattern),
                SalesOrder.official_client_name.ilike(pattern),
                SalesOrder.original_entered_client_name.ilike(pattern),
                SalesOrder.store_name.ilike(pattern),
                SalesOrder.store_branch.ilike(pattern),
                SalesOrder.sales_staff.ilike(pattern),
                SalesOrder.status.ilike(pattern),
                Client.client_name.ilike(pattern),
            ]
            parsed_date = parse_date_value(search, default_today=False)
            if parsed_date:
                search_filters.append(SalesOrder.order_date == parsed_date)
            query = query.filter(or_(*search_filters))

        pending_orders = (
            query
            .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc(), SalesOrder.id.desc())
            .limit(limit)
            .all()
        )
        
        return jsonify({
            'success': True,
            'query': search,
            'sales_orders': [sales_order_row_payload(so) for so in pending_orders]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-sales-order-details/<int:so_id>')
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_sales_order_details(so_id):
    try:
        sales_order = sales_order_query().filter(SalesOrder.id == so_id).first()
        
        if not sales_order:
            return jsonify({'success': False, 'error': 'Sales order not found'})
        
        return jsonify({
            'success': True,
            'sales_order': sales_order_row_payload(sales_order)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/generate-invoice-number')
@login_required
@role_required(*ACCOUNTING_ROLES)
def generate_invoice_number():
    try:
        invoice_type = clean_code(request.args.get('type', 'SALES')).upper()
        prefix = 'SVI-' if invoice_type == 'SERVICE' else 'SI-'
        
        last_invoice = Invoice.query.filter(
            Invoice.invoice_number.startswith(prefix)
        ).order_by(Invoice.id.desc()).first()
        
        if last_invoice:
            last_num = int(last_invoice.invoice_number.split('-')[1])
            new_num = last_num + 1
        else:
            new_num = 1
        
        invoice_number = f"{prefix}{new_num:06d}"
        
        return jsonify({
            'success': True,
            'invoice_number': invoice_number
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-invoice', methods=['POST'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def create_invoice():
    try:
        data = request.get_json(silent=True) or {}
        warnings = future_date_warnings({'Invoice date': data.get('invoice_date')})

        invoice_number = clean_code(data.get('invoice_number')).upper()
        invoice_type = canonical_invoice_type(invoice_number, data.get('invoice_type'))
        invoice_date = parse_date_value(data.get('invoice_date'), default_today=False)
        if not invoice_number:
            return jsonify({'success': False, 'error': 'Invoice number is required'}), 400
        if Invoice.query.filter(func.lower(Invoice.invoice_number) == invoice_number.lower()).first():
            return jsonify({'success': False, 'error': 'Invoice number already exists'}), 409
        if invoice_type not in {'SALES', 'SERVICE'}:
            return jsonify({'success': False, 'error': 'Invoice type must be SALES or SERVICE'}), 400
        if not invoice_date:
            return jsonify({'success': False, 'error': 'Invoice date is required'}), 400

        sales_order = db.session.get(SalesOrder, data.get('sales_order_id'))
        if not sales_order:
            return jsonify({'success': False, 'error': 'Sales order not found'}), 404

        cr_number = (data.get('cr_number') or '').strip()
        is_2307_checked = bool(data.get('is_2307_checked'))
        payment_amount, tax_amount_paid, total_paid_now = collected_payment_amount(
            cr_number,
            data.get('payment_amount'),
            data.get('tax_amount_paid'),
            is_2307_checked,
        )
        order_total = sales_order_total(sales_order)
        previous_paid = round(sum(float(inv.amount_paid or 0) for inv in sales_order.invoices), 2)
        if previous_paid + total_paid_now > order_total + MONEY_TOLERANCE:
            return jsonify({
                'success': False,
                'error': f'Payment exceeds the remaining Sales Order balance of {max(order_total - previous_paid, 0):.2f}.'
            }), 400
        
        invoice = Invoice(
            invoice_number=invoice_number,
            sales_order=sales_order,
            invoice_type=invoice_type,
            invoice_date=invoice_date,
            summary=data.get('summary', ''),
            payment_type=data.get('payment_type', ''),
            cr_number=cr_number,
            payment_amount=payment_amount,
            tax_amount_paid=tax_amount_paid,
            is_2307_checked=is_2307_checked,
            total_amount=order_total,
            amount_paid=0,
            balance=order_total,
            status='UNPAID'
        )
        
        db.session.add(invoice)
        db.session.flush()
        if total_paid_now > MONEY_TOLERANCE:
            append_collection_receipt(invoice, {
                'receipt_date': data.get('receipt_date'),
                'cr_number': cr_number,
                'payment_type': data.get('payment_type', ''),
                'payment_amount': payment_amount,
                'tax_amount_paid': tax_amount_paid,
                'is_2307_checked': is_2307_checked,
            })
        payment_summary = synchronize_sales_order_payment_state(sales_order)
        
        refresh_client_financials(sales_order.client)
        log_audit('CREATE', 'invoices', invoice.id, None, {
            'invoice_number': invoice.invoice_number,
            'total_amount': invoice.total_amount,
            'amount_paid': invoice.amount_paid,
            'balance': invoice.balance,
            'status': invoice.status,
        })
        db.session.commit()
        
        return json_success({
            'message': 'Invoice created successfully',
            'invoice_id': invoice.id,
            'invoice_status': invoice.status,
            'sales_order_status': sales_order.status,
            'amount_paid': payment_summary['amount_paid'],
            'balance': payment_summary['balance'],
        }, warnings)
    
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Invoice creation failed')
        return jsonify({'success': False, 'error': 'The invoice could not be created. Please review the information and try again.'}), 500

@app.route('/invoices/<int:invoice_id>/collection-receipts', methods=['GET'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_invoice_collection_receipts(invoice_id):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return jsonify({'success': False, 'error': 'Invoice not found'}), 404
    return jsonify({
        'success': True,
        'invoice': {
            'id': invoice.id,
            'invoice_number': invoice.invoice_number,
            'total_amount': invoice.total_amount,
            'amount_paid': invoice.amount_paid,
            'balance': invoice.balance,
            'status': invoice.status,
        },
        'collection_receipts': [
            collection_receipt_payload(item)
            for item in invoice.collection_receipts
        ],
    })

def create_collection_receipt_for_invoice(invoice_id, data):
    invoice = db.session.get(Invoice, invoice_id)
    if not invoice:
        return jsonify({'success': False, 'error': 'Invoice not found'}), 404
    payload = dict(data or {})
    warnings = future_date_warnings({'Collection Receipt date': payload.get('receipt_date')})
    receipt = append_collection_receipt(invoice, payload)
    sales_order = invoice.sales_order
    if sales_order:
        payment_summary = synchronize_sales_order_payment_state(sales_order)
    else:
        payment_summary = synchronize_invoice_receipt_state(invoice)
        payment_summary['sales_order_status'] = None
    refresh_client_financials(sales_order.client if sales_order else None)
    log_audit('CREATE_COLLECTION_RECEIPT', 'collection_receipts', receipt.id, None, {
        'invoice_id': invoice.id,
        'invoice_number': invoice.invoice_number,
        'cr_number': receipt.cr_number,
        'collected_total': receipt.collected_total,
    })
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Collection Receipt recorded successfully',
        'collection_receipt': collection_receipt_payload(receipt),
        'invoice_status': invoice.status,
        'sales_order_status': sales_order.status if sales_order else None,
        'amount_paid': payment_summary['amount_paid'],
        'balance': payment_summary['balance'],
        'warnings': warnings,
    })

@app.route('/invoices/<int:invoice_id>/collection-receipts', methods=['POST'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def create_invoice_collection_receipt(invoice_id):
    try:
        return create_collection_receipt_for_invoice(
            invoice_id,
            request.get_json(silent=True) or {},
        )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Collection Receipt creation failed')
        return jsonify({'success': False, 'error': 'The Collection Receipt could not be recorded. Please review the information and try again.'}), 500

@app.route('/update-invoice-payment/<int:invoice_id>', methods=['POST'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def update_invoice_payment(invoice_id):
    try:
        return create_collection_receipt_for_invoice(
            invoice_id,
            request.get_json(silent=True) or {},
        )
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception:
        db.session.rollback()
        app.logger.exception('Invoice payment compatibility route failed')
        return jsonify({'success': False, 'error': 'The Collection Receipt could not be recorded.'}), 500

def expense_history_payload(limit=None):
    query = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc())
    if limit:
        query = query.limit(limit)
    purchase_orders_list = query.all()
    return [
        {
            'id': po.id,
            'check_voucher_number': po.check_voucher_number,
            'check_number': po.check_number,
            'check_date': po.check_date.isoformat() if po.check_date else None,
            'supplier_payee': po.supplier_payee,
            'date': po.date.isoformat() if po.date else None,
            'particulars': po.particulars,
            'cash_amount': po.cash_amount,
            'net_balance': po.net_balance,
            'status': po.status or 'PENDING',
            'category': po.category or 'VARIABLE',
            'created_at': po.created_at.isoformat() if po.created_at else None,
            'or_date': po.or_date.isoformat() if po.or_date else None,
            'ar_cr_or_number': po.ar_cr_or_number,
            'po_number': po.po_number,
            'lf_no': po.lf_no,
            'tin_number': po.tin_number,
            'debits': [
                {
                    'id': debit.id,
                    'debit_type': debit.debit_type,
                    'amount': debit.amount,
                }
                for debit in po.debits
            ],
        }
        for po in purchase_orders_list
    ]


def expense_audit_snapshot(expense):
    data = serialize_record(expense) or {}
    data['debits'] = [
        {
            'debit_type': debit.debit_type,
            'amount': float(debit.amount or 0),
        }
        for debit in PurchaseOrderDebit.query
        .filter_by(purchase_order_id=expense.id)
        .order_by(PurchaseOrderDebit.id.asc())
        .all()
    ]
    return data


def normalize_expense_payload(data):
    data = data or {}
    required_text_fields = {
        'check_voucher_number': 'Check/Cash Voucher Number',
        'check_number': 'Check Number',
        'particulars': 'Particulars',
        'supplier_payee': 'Supplier/Payee',
    }
    normalized = {}
    for field, label in required_text_fields.items():
        value = str(data.get(field) or '').strip()
        if not value:
            raise ValueError(f'{label} is required.')
        normalized[field] = value

    for field, label in {'check_date': 'Check date', 'date': 'Expense date'}.items():
        value = data.get(field)
        if not value:
            raise ValueError(f'{label} is required.')
        normalized[field] = datetime.strptime(value, '%Y-%m-%d').date()

    normalized['or_date'] = (
        datetime.strptime(data.get('or_date'), '%Y-%m-%d').date()
        if data.get('or_date') else None
    )
    for field in ('ar_cr_or_number', 'po_number', 'lf_no', 'tin_number'):
        normalized[field] = str(data.get(field) or '').strip()

    try:
        cash_amount = float(data.get('cash_amount'))
    except (TypeError, ValueError):
        raise ValueError('Cash amount is required.')
    if cash_amount < 0:
        raise ValueError('Cash amount cannot be negative.')
    normalized['cash_amount'] = round(cash_amount, 2)

    debits = []
    for debit in data.get('debits', []):
        debit_type = str(debit.get('debit_type') or '').strip()
        if not debit_type:
            continue
        try:
            amount = float(debit.get('amount'))
        except (TypeError, ValueError):
            raise ValueError(f'Invalid amount for debit account {debit_type}.')
        if amount <= 0:
            raise ValueError(f'Debit amount for {debit_type} must be greater than zero.')
        debits.append({'debit_type': debit_type, 'amount': round(amount, 2)})
    if not debits:
        raise ValueError('At least one debit account is required.')

    total_debits = round(sum(debit['amount'] for debit in debits), 2)
    net_balance = round(total_debits - normalized['cash_amount'], 2)
    normalized['debits'] = debits
    normalized['net_balance'] = net_balance
    normalized['category'] = 'FIXED' if any(
        debit['debit_type'] in ['PLDT', 'Globe/Smart, Sun', 'Meralco', 'Rent Expense']
        for debit in debits
    ) else 'VARIABLE'
    normalized['status'] = 'PAID' if abs(net_balance) < 0.005 else 'PENDING'
    return normalized


def apply_expense_payload(expense, normalized):
    expense.check_voucher_number = normalized['check_voucher_number']
    expense.check_number = normalized['check_number']
    expense.check_date = normalized['check_date']
    expense.date = normalized['date']
    expense.or_date = normalized['or_date']
    expense.ar_cr_or_number = normalized['ar_cr_or_number']
    expense.po_number = normalized['po_number']
    expense.lf_no = normalized['lf_no']
    expense.particulars = normalized['particulars']
    expense.supplier_payee = normalized['supplier_payee']
    expense.tin_number = normalized['tin_number']
    expense.cash_amount = normalized['cash_amount']
    expense.net_balance = normalized['net_balance']
    expense.category = normalized['category']
    expense.status = normalized['status']


def replace_expense_debits(expense, debits):
    PurchaseOrderDebit.query.filter_by(purchase_order_id=expense.id).delete()
    for debit_data in debits:
        db.session.add(PurchaseOrderDebit(
            purchase_order_id=expense.id,
            debit_type=debit_data['debit_type'],
            amount=debit_data['amount'],
        ))


def create_expense_record(data):
    warnings = future_date_warnings({
        'Check date': data.get('check_date') if data else None,
        'Expense date': data.get('date') if data else None,
        'OR date': data.get('or_date') if data else None,
    })
    normalized = normalize_expense_payload(data)

    expense = PurchaseOrder(
        check_voucher_number=normalized['check_voucher_number'],
        check_number=normalized['check_number'],
        check_date=normalized['check_date'],
        date=normalized['date'],
        or_date=normalized['or_date'],
        ar_cr_or_number=normalized['ar_cr_or_number'],
        po_number=normalized['po_number'],
        lf_no=normalized['lf_no'],
        particulars=normalized['particulars'],
        supplier_payee=normalized['supplier_payee'],
        tin_number=normalized['tin_number'],
        cash_amount=normalized['cash_amount'],
        net_balance=normalized['net_balance'],
        category=normalized['category'],
        status=normalized['status']
    )

    db.session.add(expense)
    db.session.flush()
    replace_expense_debits(expense, normalized['debits'])

    log_audit('CREATE', 'purchase_orders', expense.id, None, {
        'check_voucher_number': expense.check_voucher_number,
        'cash_amount': expense.cash_amount,
        'module_label': 'Expense',
    })
    db.session.commit()
    return warnings


@app.route('/expenses')
@login_required
@role_required(*ACCOUNTING_ROLES)
def expenses():
    return render_template('purchase_orders.html')

@app.route('/purchase-orders')
@login_required
@role_required(*ACCOUNTING_ROLES)
def purchase_orders():
    return redirect(url_for('expenses'))

@app.route('/get-expenses')
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_expenses():
    try:
        expenses_list = expense_history_payload()
        return jsonify({
            'success': True,
            'expenses': expenses_list,
            'purchase_orders': expenses_list,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-purchase-orders')
@login_required
@role_required(*ACCOUNTING_ROLES)
def get_purchase_orders():
    return get_expenses()

@app.route('/create-expense', methods=['POST'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def create_expense():
    try:
        data = request.get_json()
        warnings = create_expense_record(data)
        return json_success({'message': 'Expense created successfully'}, warnings)
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-purchase-order', methods=['POST'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def create_purchase_order():
    return create_expense()

@app.route('/expenses/<int:expense_id>', methods=['PUT'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def update_expense(expense_id):
    try:
        expense = db.session.get(PurchaseOrder, expense_id)
        if not expense:
            return jsonify({'success': False, 'error': 'Expense not found'}), 404

        data = request.get_json() or {}
        warnings = future_date_warnings({
            'Check date': data.get('check_date'),
            'Expense date': data.get('date'),
            'OR date': data.get('or_date'),
        })
        normalized = normalize_expense_payload(data)
        old_value = expense_audit_snapshot(expense)
        apply_expense_payload(expense, normalized)
        replace_expense_debits(expense, normalized['debits'])
        db.session.flush()
        new_value = expense_audit_snapshot(expense)
        log_audit('UPDATE', 'purchase_orders', expense.id, old_value, new_value)
        db.session.commit()
        return json_success({'message': 'Expense updated successfully'}, warnings)
    except ValueError as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': public_error_message(e, 'Analytics generation failed.')}), 500

@app.route('/update-expense/<int:expense_id>', methods=['POST', 'PUT'])
@login_required
@role_required(*ACCOUNTING_ROLES)
def update_expense_compat(expense_id):
    return update_expense(expense_id)

@app.route('/database-interface')
@login_required
@role_required('admin')
def database_interface():
    return render_template('admin.html', production_mode=IS_PRODUCTION)

@app.route('/get-database-stats')
@login_required
@role_required('admin')
def get_database_stats():
    try:
        stats = {
            'total_users': User.query.count(),
            'total_sales_orders': SalesOrder.query.count(),
            'total_invoices': Invoice.query.count(),
            'total_purchase_orders': PurchaseOrder.query.count(),
            'total_clients': Client.query.count()
        }
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-users')
@login_required
@role_required('admin')
def get_users():
    try:
        users_list = db.session.query(
            User.id, User.username, User.email, User.role_id, User.created_at,
            User.status, User.disabled_reason, User.profile_photo, Role.role_name
        ).join(Role).order_by(User.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'users': [
                {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role_name': user.role_name,
                    'status': user.status,
                    'disabled_reason': user.disabled_reason,
                    'profile_photo': user.profile_photo,
                    'created_at': user.created_at.isoformat() if user.created_at else None,
                    'role_id': user.role_id
                } for user in users_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-roles')
@login_required
@role_required('admin')
def get_roles():
    try:
        roles_list = Role.query.all()
        return jsonify({
            'success': True,
            'roles': [
                {
                    'id': role.id,
                    'role_name': role.role_name,
                    'description': role.description
                } for role in roles_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-session-records')
@login_required
@role_required('admin')
def get_session_records():
    try:
        sessions = SessionRecord.query.order_by(SessionRecord.login_at.desc()).limit(100).all()
        return jsonify({
            'success': True,
            'sessions': [
                {
                    'id': item.id,
                    'username': item.username,
                    'role_name': item.role_name,
                    'login_at': item.login_at.isoformat() if item.login_at else None,
                    'logout_at': item.logout_at.isoformat() if item.logout_at else None,
                    'status': item.status
                } for item in sessions
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-client-basket')
@login_required
@role_required('admin')
def get_client_basket():
    try:
        basket_items = db.session.query(
            Client.id.label('client_id'),
            Client.client_name,
            SalesOrder.so_number,
            SalesOrder.order_date,
            SalesOrderItem.particular,
            SalesOrderItem.quantity,
            SalesOrderItem.selling_price,
            SalesOrderItem.total
        ).join(SalesOrder, Client.id == SalesOrder.client_id).join(
            SalesOrderItem, SalesOrder.id == SalesOrderItem.sales_order_id
        ).order_by(SalesOrder.created_at.desc()).limit(100).all()

        return jsonify({
            'success': True,
            'client_basket': [
                {
                    'client_id': item.client_id,
                    'client_name': item.client_name,
                    'so_number': item.so_number,
                    'order_date': item.order_date.isoformat() if item.order_date else None,
                    'particular': item.particular,
                    'quantity': int(item.quantity or 0),
                    'selling_price': item.selling_price,
                    'total': item.total
                } for item in basket_items
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/get-sales-orders-admin')
@login_required
@role_required('admin')
def get_sales_orders_admin():
    try:
        sales_orders_list = (
            sales_order_query()
            .order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc(), SalesOrder.id.desc())
            .limit(50)
            .all()
        )
        
        return jsonify({
            'success': True,
            'sales_orders': [sales_order_row_payload(so) for so in sales_orders_list]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-invoices-admin')
@login_required
@role_required('admin')
def get_invoices_admin():
    try:
        invoices_list = db.session.query(
            Invoice.id, Invoice.invoice_number, Invoice.invoice_type,
            Invoice.invoice_date, Invoice.total_amount, Invoice.status,
            Client.client_name, Invoice.uploaded_client_name, Invoice.created_at
        ).select_from(Invoice).join(
            SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True
        ).join(
            Client, SalesOrder.client_id == Client.id, isouter=True
        ).order_by(Invoice.created_at.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'invoices': [
                {
                    'id': inv.id,
                    'invoice_number': clean_code(inv.invoice_number).upper(),
                    'invoice_type': canonical_invoice_type(inv.invoice_number, inv.invoice_type),
                    'client_name': inv.client_name or inv.uploaded_client_name or 'Admin Upload',
                    'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                    'total_amount': inv.total_amount,
                    'status': inv.status,
                    'created_at': inv.created_at.isoformat() if inv.created_at else None
                } for inv in invoices_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-purchase-orders-admin')
@login_required
@role_required('admin')
def get_purchase_orders_admin():
    try:
        expenses_list = expense_history_payload(limit=50)
        return jsonify({
            'success': True,
            'expenses': expenses_list,
            'purchase_orders': expenses_list,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-role', methods=['POST'])
@login_required
@role_required('admin')
def create_role():
    try:
        data = request.get_json()
        role_name = data['role_name'].strip()
        
        if Role.query.filter_by(role_name=role_name).first():
            return jsonify({'success': False, 'error': 'Role name already exists'})
        
        role = Role(
            role_name=role_name,
            description=data.get('description', '')
        )
        
        db.session.add(role)
        log_audit('CREATE', 'roles', None, None, {'role_name': role_name})
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Role created successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-user', methods=['POST'])
@login_required
@role_required('admin')
def create_user():
    try:
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        email = data.get('email', '').strip() or None

        if not username or not data.get('password') or not data.get('role_id'):
            return jsonify({'success': False, 'error': 'Username, password, and role are required'}), 400
        if User.query.filter(func.lower(User.username) == username.lower()).first():
            return jsonify({'success': False, 'error': 'Username already exists'}), 409
        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Email already exists'}), 409
        if is_admin_role_id(data['role_id']) and User.query.join(Role).filter(func.lower(Role.role_name) == 'admin').count() >= 1:
            return jsonify({'success': False, 'error': 'Only one admin account is allowed'}), 409
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(data['password']),
            role_id=data['role_id'],
            status=USER_STATUS_APPROVED,
            approved_by=session.get('user_id'),
            approved_at=datetime.now(UTC)
        )
        
        db.session.add(user)
        db.session.flush()
        log_audit('CREATE', 'users', user.id, None, {'username': user.username, 'email': user.email, 'role_id': user.role_id, 'status': user.status})
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'User created successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update-user/<int:user_id>', methods=['POST'])
@login_required
@role_required('admin')
def update_user(user_id):
    try:
        data = request.get_json() or {}
        if 'role_id' in data or 'status' in data:
            return jsonify({
                'success': False,
                'error': 'Role and account status changes require Edit User and admin password confirmation.'
            }), 409
        
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        username = (data.get('username') or '').strip()
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
        if User.query.filter(func.lower(User.username) == username.lower(), User.id != user_id).first():
            return jsonify({'success': False, 'error': 'Username already exists'}), 409
        email = data.get('email', '').strip() or None
        if email:
            existing_email = User.query.filter(User.email == email, User.id != user_id).first()
            if existing_email:
                return jsonify({'success': False, 'error': 'Email already exists'})
        old_value = serialize_record(user)
        user.username = username
        user.email = email
        if data.get('password'):
            user.password_hash = generate_password_hash(data['password'])
        
        log_audit('UPDATE', 'users', user.id, old_value, serialize_record(user))
        db.session.commit()
        if user.id == session['user_id']:
            session['username'] = user.username
            session['role'] = user_role_name(user)
        
        return jsonify({'success': True, 'message': 'User updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete-user/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_user(user_id):
    return jsonify({
        'success': False,
        'error': 'Use Edit User to disable an account with password confirmation and a reason.'
    }), 409


@app.route('/admin/users/<int:user_id>/action', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_action(user_id):
    try:
        data = request.get_json(silent=True) or {}
        action = (data.get('action') or '').strip().lower()
        allowed_actions = {
            'approve', 'reject', 'promote_manager',
            'demote_staff', 'disable', 'enable',
        }
        if action not in allowed_actions:
            return jsonify({'success': False, 'error': 'Choose a valid user action.'}), 400

        admin_user = db.session.get(User, session.get('user_id'))
        admin_password = data.get('admin_password') or ''
        if not admin_user or not check_password_hash(admin_user.password_hash, admin_password):
            return jsonify({'success': False, 'error': 'Admin password confirmation failed.'}), 403

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found.'}), 404

        role_name = user_role_name(user)
        status = normalize_user_status(user.status)
        protected_action = action in {'reject', 'promote_manager', 'demote_staff', 'disable'}
        if protected_action and (user.id == admin_user.id or role_name == 'admin'):
            return jsonify({
                'success': False,
                'error': 'The current administrator account cannot be rejected, role-changed, or disabled.'
            }), 409

        old_value = {
            'username': user.username,
            'role': role_name,
            'status': status,
            'disabled_reason': user.disabled_reason,
        }
        audit_action = ''
        message = ''

        if action == 'approve':
            if status != USER_STATUS_PENDING:
                return jsonify({'success': False, 'error': 'Only pending accounts can be approved.'}), 409
            user.status = USER_STATUS_APPROVED
            user.approved_by = admin_user.id
            user.approved_at = datetime.now(UTC)
            user.disabled_reason = None
            audit_action = 'APPROVE_USER'
            message = 'Account approved successfully.'
        elif action == 'reject':
            if status != USER_STATUS_PENDING:
                return jsonify({'success': False, 'error': 'Only pending accounts can be rejected.'}), 409
            user.status = USER_STATUS_REJECTED
            user.disabled_reason = None
            audit_action = 'REJECT_USER'
            message = 'Account request rejected.'
        elif action == 'promote_manager':
            if status != USER_STATUS_APPROVED or role_name not in {'staff', 'sales staff', 'accounting staff'}:
                return jsonify({'success': False, 'error': 'Only approved staff accounts can become managers.'}), 409
            manager_role = Role.query.filter(func.lower(Role.role_name) == 'manager').first()
            if not manager_role:
                return jsonify({'success': False, 'error': 'Manager role is not configured.'}), 409
            user.role = manager_role
            audit_action = 'PROMOTE_USER_MANAGER'
            message = 'User changed to manager successfully.'
        elif action == 'demote_staff':
            if status != USER_STATUS_APPROVED or role_name != 'manager':
                return jsonify({'success': False, 'error': 'Only approved manager accounts can become staff.'}), 409
            staff_role = Role.query.filter(func.lower(Role.role_name) == 'staff').first()
            if not staff_role:
                return jsonify({'success': False, 'error': 'Staff role is not configured.'}), 409
            user.role = staff_role
            audit_action = 'DEMOTE_USER_STAFF'
            message = 'Manager changed to staff successfully.'
        elif action == 'disable':
            reason = (data.get('reason') or '').strip()
            if status != USER_STATUS_APPROVED:
                return jsonify({'success': False, 'error': 'Only approved accounts can be disabled.'}), 409
            if not reason:
                return jsonify({'success': False, 'error': 'A disable reason is required.'}), 400
            if len(reason) > 1000:
                return jsonify({'success': False, 'error': 'Disable reason must be 1,000 characters or fewer.'}), 400
            user.status = USER_STATUS_DISABLED
            user.disabled_reason = reason
            audit_action = 'DISABLE_USER'
            message = 'User disabled successfully.'
        else:
            if status not in {USER_STATUS_DISABLED, USER_STATUS_REJECTED}:
                return jsonify({'success': False, 'error': 'Only disabled or rejected accounts can be re-enabled.'}), 409
            if role_name == 'admin' and user.id != admin_user.id:
                return jsonify({'success': False, 'error': 'Another administrator account cannot be enabled.'}), 409
            user.status = USER_STATUS_APPROVED
            user.approved_by = admin_user.id
            user.approved_at = datetime.now(UTC)
            user.disabled_reason = None
            audit_action = 'ENABLE_USER'
            message = 'User re-enabled successfully.'

        force_logout_user(user.id)
        db.session.flush()
        new_value = {
            'username': user.username,
            'role': user_role_name(user),
            'status': normalize_user_status(user.status),
            'disabled_reason': user.disabled_reason,
        }
        log_audit(audit_action, 'users', user.id, old_value, new_value)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': message,
            'user': {'id': user.id, **new_value},
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': public_error_message(e)}), 400


@app.route('/update-client/<int:client_id>', methods=['POST'])
@login_required
@role_required('admin')
def update_client(client_id):
    try:
        data = request.get_json()
        
        client = db.session.get(Client, client_id)
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'})
        old_value = serialize_record(client)
        client.client_name = data['client_name']
        client.contact_info = data.get('contact_info', '')
        log_audit('UPDATE', 'clients', client.id, old_value, serialize_record(client))
        refresh_client_financials(client)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Client updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete-client/<int:client_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_client(client_id):
    try:
        client = db.session.get(Client, client_id)
        if not client:
            return jsonify({'success': False, 'error': 'Client not found'})
        
        old_value = serialize_record(client)
        db.session.delete(client)
        log_audit('DELETE', 'clients', client_id, old_value, None)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Client deleted successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/data-grid')
@login_required
@role_required('admin')
def admin_data_grid():
    try:
        table = request.args.get('table', 'users')
        payload = get_data_grid(db, app_models(), table, request.args)
        return jsonify({'success': True, 'grid': payload})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/admin/client-list')
@login_required
@role_required('admin')
def admin_client_list():
    try:
        return jsonify({'success': True, 'clients': admin_client_list_payload()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/client-match')
@login_required
@role_required('admin')
def admin_client_match():
    try:
        query = request.args.get('q', '')
        return jsonify({'success': True, 'candidates': client_match_candidates(query)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/sales-orders/<int:sales_order_id>/client-store-branch', methods=['POST'])
@login_required
@role_required('admin')
def admin_update_sales_order_client_store_branch(sales_order_id):
    try:
        data = request.get_json() or {}
        sales_order = (
            SalesOrder.query
            .options(selectinload(SalesOrder.client))
            .filter(SalesOrder.id == sales_order_id)
            .first()
        )
        if not sales_order:
            return jsonify({'success': False, 'error': 'Sales order not found'}), 404

        target_client_id = parse_optional_integer(data.get('client_id'))
        target_client = db.session.get(Client, target_client_id) if target_client_id else None
        if not target_client:
            return jsonify({'success': False, 'error': 'Choose an existing client from the Client List before saving.'}), 400

        old_client = sales_order.client
        old_value = serialize_record(sales_order)
        entered_company = clean_text(
            data.get('company_name') or target_client.client_name,
            keep_period=True,
            keep_ampersand=True,
        ).upper()
        store_name = clean_text(data.get('store_name'), keep_period=True, keep_ampersand=True)
        store_branch = clean_text(data.get('store_branch'), keep_period=True, keep_ampersand=True)

        sales_order.client_id = target_client.id
        sales_order.company_name = target_client.client_name
        sales_order.official_client_name = target_client.client_name
        sales_order.original_entered_client_name = entered_company or target_client.client_name
        sales_order.store_name = (store_name or target_client.client_name).upper()
        sales_order.store_branch = (store_branch or DEFAULT_STORE_BRANCH).upper()

        if bool(data.get('learn_alias')) and entered_company and entered_company != target_client.client_name:
            learn_client_alias(entered_company, target_client)

        refresh_client_financials(old_client)
        if not old_client or old_client.id != target_client.id:
            refresh_client_financials(target_client)
        rebuild_analytics_data()
        log_audit(
            'UPDATE_CLIENT_STORE_BRANCH',
            'sales_orders',
            sales_order.id,
            old_value,
            serialize_record(sales_order),
        )
        db.session.commit()

        refreshed_order = (
            SalesOrder.query
            .options(selectinload(SalesOrder.client))
            .filter(SalesOrder.id == sales_order.id)
            .first()
        )
        return jsonify({
            'success': True,
            'message': 'Sales order client, store, and branch updated.',
            'sales_order': sales_order_admin_payload(refreshed_order),
            'clients': admin_client_list_payload(),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@app.route('/admin/export')
@login_required
@role_required('admin')
def admin_export():
    try:
        table = request.args.get('table', 'users')
        csv_file = export_data_grid_csv(db, app_models(), table, request.args)
        return send_file(
            csv_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'{table}-export.csv'
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/db-health')
@login_required
@role_required('admin')
def admin_db_health():
    try:
        db_path = os.path.join(app.instance_path, 'syluxent.db')
        backup_dir = os.path.join(app.instance_path, 'backups')
        return jsonify({'success': True, 'health': get_db_health(db_path, backup_dir)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/db-maintenance', methods=['POST'])
@login_required
@role_required('admin')
def admin_db_maintenance():
    try:
        command = (request.get_json() or {}).get('command', '')
        run_maintenance(db, command)
        log_audit('MAINTENANCE', 'database', None, None, {'command': command})
        db.session.commit()
        return jsonify({'success': True, 'message': f'{command.upper()} completed'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/transaction-reset', methods=['GET'])
@login_required
@role_required('admin')
def admin_transaction_reset_counts():
    return jsonify({
        'success': True,
        'counts': {
            'sales_orders': SalesOrder.query.count(),
            'sales_order_items': SalesOrderItem.query.count(),
            'sales_order_branches': SalesOrderBranch.query.count(),
            'invoices': Invoice.query.count(),
            'expenses': PurchaseOrder.query.count(),
            'expense_debits': PurchaseOrderDebit.query.count(),
        }
    })

@app.route('/admin/transaction-reset', methods=['POST'])
@login_required
@role_required('admin')
def admin_transaction_reset():
    denied = admin_required_json()
    if denied:
        return denied
    payload = request.get_json() or {}
    selected = set(payload.get('areas') or [])
    allowed = {'sales_orders', 'invoices', 'expenses'}
    if not selected or not selected.issubset(allowed):
        return jsonify({'success': False, 'error': 'Select at least one valid transaction area.'}), 400
    if 'sales_orders' in selected and 'invoices' not in selected:
        return jsonify({
            'success': False,
            'error': 'Invoices must also be selected when resetting Sales Orders.'
        }), 409
    if str(payload.get('confirmation') or '').strip().upper() != 'RESET TRANSACTIONS':
        return jsonify({
            'success': False,
            'error': 'Type RESET TRANSACTIONS to confirm this operation.'
        }), 400
    try:
        deleted = {}
        if 'invoices' in selected:
            deleted['invoices'] = Invoice.query.count()
            Invoice.query.delete(synchronize_session=False)
        if 'sales_orders' in selected:
            deleted['sales_order_items'] = SalesOrderItem.query.count()
            deleted['sales_order_branches'] = SalesOrderBranch.query.count()
            deleted['sales_orders'] = SalesOrder.query.count()
            SalesOrderItem.query.delete(synchronize_session=False)
            SalesOrderBranch.query.delete(synchronize_session=False)
            SalesOrder.query.delete(synchronize_session=False)
        if 'expenses' in selected:
            deleted['expense_debits'] = PurchaseOrderDebit.query.count()
            deleted['expenses'] = PurchaseOrder.query.count()
            PurchaseOrderDebit.query.delete(synchronize_session=False)
            PurchaseOrder.query.delete(synchronize_session=False)
        if {'sales_orders', 'invoices'} & selected:
            refresh_client_financials()
        log_audit('RESET_TRANSACTIONS', 'database', None, None, {
            'areas': sorted(selected),
            'deleted': deleted,
        })
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Selected transaction records were reset.',
            'deleted': deleted,
        })
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Transaction reset failed')
        return jsonify({'success': False, 'error': str(exc)}), 400

@app.route('/admin/schema')
@login_required
@role_required('admin')
def admin_schema():
    try:
        return jsonify({'success': True, 'schema': get_schema(db)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/sql-console', methods=['POST'])
@login_required
@role_required('admin')
def admin_sql_console():
    try:
        data = request.get_json() or {}
        requested_dry_run = bool(data.get('dry_run', True))
        dry_run = True if IS_PRODUCTION else requested_dry_run
        result = run_safe_sql(db, data.get('sql', ''), dry_run)
        log_audit('SQL_DRY_RUN' if result['dry_run'] else 'SQL_EXECUTE', 'database', None, None, {'sql': data.get('sql', '')})
        db.session.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        db.session.rollback()
        app.logger.exception('Admin SQL console failed')
        return jsonify({'success': False, 'error': 'The SQL request was rejected or could not be completed.'}), 400

@app.route('/admin/theme', methods=['GET'])
@login_required
@role_required('admin')
def admin_theme():
    return jsonify({
        'success': True,
        'fields': THEME_FIELDS,
        'settings': read_theme_settings()
    })

@app.route('/admin/theme', methods=['POST'])
@login_required
@role_required('admin')
def admin_theme_save():
    try:
        data = request.get_json() or {}
        settings = sanitize_theme_settings(data.get('settings') or {})
        write_theme_files(settings)
        log_audit('UPDATE_THEME', 'theme', 'theme-overrides.css', None, settings)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Theme updated successfully.', 'settings': settings})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/admin/theme/reset', methods=['POST'])
@login_required
@role_required('admin')
def admin_theme_reset():
    try:
        settings = default_theme_settings()
        write_theme_files(settings)
        log_audit('RESET_THEME', 'theme', 'theme-overrides.css', None, settings)
        db.session.commit()
        return jsonify({'success': True, 'message': 'Theme reset to defaults.', 'settings': settings})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/admin/bulk-update', methods=['POST'])
@login_required
@role_required('admin')
def admin_bulk_update():
    try:
        data = request.get_json() or {}
        table = data.get('table', '')
        if table == 'users':
            return jsonify({
                'success': False,
                'error': 'User status changes require Edit User and admin password confirmation.'
            }), 409
        count = bulk_update_status(db, app_models(), table, data.get('ids', []), data.get('status', ''))
        if table in ('sales_orders', 'invoices', 'purchase_orders'):
            refresh_client_financials()
        log_audit('BULK_UPDATE_STATUS', table, ','.join(map(str, data.get('ids', []))), None, {'status': data.get('status', '')})
        db.session.commit()
        return jsonify({'success': True, 'updated': count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/bulk-delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_bulk_delete():
    try:
        data = request.get_json() or {}
        table = data.get('table', '')
        count = bulk_delete(db, app_models(), table, data.get('ids', []))
        if table in ('sales_orders', 'invoices', 'purchase_orders'):
            refresh_client_financials()
        log_audit('BULK_DELETE', table, ','.join(map(str, data.get('ids', []))), None, None)
        db.session.commit()
        return jsonify({'success': True, 'deleted': count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/notifications')
@login_required
@role_required('admin')
def admin_notifications():
    reset_requests = PasswordReset.query.order_by(
        case((PasswordReset.status == 'PENDING', 0), else_=1),
        PasswordReset.requested_at.desc()
    ).limit(100).all()
    approval_requests = (
        User.query
        .join(Role)
        .filter(func.lower(User.status) == USER_STATUS_PENDING)
        .order_by(User.created_at.asc())
        .limit(100)
        .all()
    )
    pending_accounts = User.query.filter(func.lower(User.status) == USER_STATUS_PENDING).count()
    pending_resets = PasswordReset.query.filter_by(status='PENDING').count()
    return jsonify({
        'success': True,
        'pending_count': pending_accounts + pending_resets,
        'pending_account_count': pending_accounts,
        'pending_password_reset_count': pending_resets,
        'account_approvals': [
            {
                'id': item.id,
                'username': item.username,
                'email': item.email,
                'role_name': item.role.role_name if item.role else 'staff',
                'status': normalize_user_status(item.status),
                'created_at': item.created_at.isoformat() if item.created_at else None,
            }
            for item in approval_requests
        ],
        'password_resets': [
            {
                'id': item.id,
                'username': item.username,
                'status': item.status,
                'requested_at': item.requested_at.isoformat() if item.requested_at else None,
                'resolved_at': item.resolved_at.isoformat() if item.resolved_at else None,
                'resolved_by': item.resolved_by.username if item.resolved_by else None,
            }
            for item in reset_requests
        ]
    })

@app.route('/admin/users/<int:user_id>/approval', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_approval(user_id):
    return jsonify({
        'success': False,
        'error': 'Use Edit User to review accounts with admin password confirmation.'
    }), 409

@app.route('/admin/password-resets/<int:reset_id>/resolve', methods=['POST'])
@login_required
@role_required('admin')
def resolve_password_reset(reset_id):
    reset_request = db.session.get(PasswordReset, reset_id)
    if not reset_request:
        return jsonify({'success': False, 'error': 'Password reset request not found'}), 404
    if reset_request.status != 'PENDING':
        return jsonify({'success': False, 'error': 'Password reset request is already resolved'}), 409
    user = db.session.get(User, reset_request.user_id)
    if not is_user_approved(user):
        return jsonify({'success': False, 'error': 'The user account is unavailable or inactive'}), 409
    payload = request.get_json(silent=True) or {}
    admin_user = db.session.get(User, session['user_id'])
    admin_password = payload.get('admin_password') or ''
    if not admin_user or not check_password_hash(admin_user.password_hash, admin_password):
        return jsonify({'success': False, 'error': 'Admin password confirmation failed.'}), 403

    temporary_password = f'{user.username}123'
    user.password_hash = generate_password_hash(temporary_password)
    reset_request.status = 'RESOLVED'
    reset_request.resolved_at = datetime.now(UTC)
    reset_request.resolved_by_user_id = session['user_id']
    log_audit(
        'PASSWORD_RESET_RESOLVED',
        'password_resets',
        reset_request.id,
        {'status': 'PENDING', 'username': user.username},
        {'status': 'RESOLVED', 'username': user.username}
    )
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Password has been reset successfully.'
    })

@app.route('/admin/audit-logs')
@login_required
@role_required('admin')
def admin_audit_logs():
    try:
        query = AuditLog.query.outerjoin(User, AuditLog.user_id == User.id).outerjoin(Role, User.role_id == Role.id)
        username = (request.args.get('username') or '').strip()
        role_name = (request.args.get('role') or '').strip()
        if username:
            query = query.filter(AuditLog.username == username)
        if role_name:
            query = query.filter(Role.role_name == role_name)
        logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()
        return jsonify({
            'success': True,
            'logs': [
                {
                    'id': log.id,
                    'username': log.username,
                    'role_name': log.user.role.role_name if log.user and log.user.role else 'system',
                    'action': log.action,
                    'table_name': log.table_name,
                    'record_id': log.record_id,
                    'old_value': log.old_value,
                    'new_value': log.new_value,
                    'created_at': log.created_at.isoformat() if log.created_at else None,
                } for log in logs
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# Analytics Interface

@app.route('/analytics')
@login_required
@role_required('manager', 'admin')
def analytics():
    return render_template('analytics.html', available_years=report_available_years(), datetime=datetime)

@app.route('/api/analytics/generate', methods=['POST'])
@login_required
@role_required('manager', 'admin')
def generate_analytics_report():
    try:
        live_counts = {
            'sales_orders': SalesOrder.query.count(),
            'invoices': Invoice.query.count(),
            'purchase_orders': PurchaseOrder.query.count(),
        }
        if not any(live_counts.values()):
            return jsonify({
                'success': False,
                'needs_upload': True,
                'message': 'No live transaction data found. Upload Historical Transaction CSV first.'
            }), 400
        rebuild_analytics_data()
        total_records = AnalyticsData.query.count()
        log_audit('GENERATE_ANALYTICS_REPORT', 'analytics_data', None, None, {'records': total_records, **live_counts})
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Analytics report generated from live system data. {total_records} historical transaction rows are ready.',
            'records': total_records,
            'live_counts': live_counts
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analytics/overview', methods=['GET'])
@login_required
@role_required('manager', 'admin')
def get_overview():
    try:
        # Check if any data exists at all
        total_records = AnalyticsData.query.count()
        if total_records == 0:
            has_live_data = bool(SalesOrder.query.count() or Invoice.query.count() or PurchaseOrder.query.count())
            return jsonify({
                "success": True,
                "is_empty": True,
                "has_live_data": has_live_data,
                "message": "Generate Analytics Report" if has_live_data else "Generate Analytics Report. No system data found. Upload Historical Transaction CSV."
            })

        filters = parse_report_date_filter()
        comparison_filters = previous_year_comparison_filter(filters)
        selected_year = filters['selected_year']
        period = filters['period']

        # Get available unique years for filter dropdown
        years_query = db.session.query(db_year(AnalyticsData.transaction_date)).distinct().all()
        available_years = sorted([int(y[0]) for y in years_query if y[0] is not None], reverse=True)
        
        # 1. Calculate overall dashboard totals (Gross Revenue & Cost of Goods Sold)
        kpi_totals = db.session.query(
            func.sum(
                case(
                    (AnalyticsData.flow_direction == 'INFLOW', AnalyticsData.amount),
                    else_=0
                )
            ).label('gross_revenue'),
            func.sum(
                case(
                    (AnalyticsData.flow_direction == 'OUTFLOW', AnalyticsData.amount),
                    else_=0
                )
            ).label('total_cost')
        ).filter(
            AnalyticsData.transaction_date >= filters['start_date'],
            AnalyticsData.transaction_date < filters['end_date'],
            AnalyticsData.flow_status == 'ACTUAL'
        ).first()

        gross_revenue = kpi_totals.gross_revenue or 0.0
        total_cost = kpi_totals.total_cost or 0.0
        comparison_totals = db.session.query(
            func.sum(
                case(
                    (AnalyticsData.flow_direction == 'INFLOW', AnalyticsData.amount),
                    else_=0
                )
            ).label('gross_revenue'),
            func.sum(
                case(
                    (AnalyticsData.flow_direction == 'OUTFLOW', AnalyticsData.amount),
                    else_=0
                )
            ).label('total_cost')
        ).filter(
            AnalyticsData.transaction_date >= comparison_filters['start_date'],
            AnalyticsData.transaction_date < comparison_filters['end_date'],
            AnalyticsData.flow_status == 'ACTUAL'
        ).first()
        comparison_revenue = float(comparison_totals.gross_revenue or 0)
        comparison_cost = float(comparison_totals.total_cost or 0)

        def percentage_change(current, previous):
            current = float(current or 0)
            previous = float(previous or 0)
            if previous == 0:
                return None
            return round((current - previous) / previous * 100, 2)

        # 2. GROUP BY MONTH & SORT CHRONOLOGICALLY
        month_number = db_month_number(AnalyticsData.transaction_date).label('month_num')
        monthly_query = db.session.query(
            month_number,
            func.min(AnalyticsData.transaction_date).label('first_day_of_month'),
            func.sum(AnalyticsData.amount).label('monthly_revenue')
        ).filter(
            AnalyticsData.transaction_date >= filters['start_date'],
            AnalyticsData.transaction_date < filters['end_date'],
            AnalyticsData.flow_direction == 'INFLOW',
            AnalyticsData.flow_status == 'ACTUAL'
        ).group_by(
            month_number
        ).order_by(
            asc(month_number)
        ).all()
        comparison_month_number = db_month_number(AnalyticsData.transaction_date).label('month_num')
        comparison_monthly_rows = db.session.query(
            comparison_month_number,
            func.sum(AnalyticsData.amount).label('monthly_revenue')
        ).filter(
            AnalyticsData.transaction_date >= comparison_filters['start_date'],
            AnalyticsData.transaction_date < comparison_filters['end_date'],
            AnalyticsData.flow_direction == 'INFLOW',
            AnalyticsData.flow_status == 'ACTUAL'
        ).group_by(
            comparison_month_number
        ).all()
        comparison_by_month = {
            int(row.month_num): float(row.monthly_revenue or 0)
            for row in comparison_monthly_rows
            if row.month_num is not None
        }

        # 3. Format labels consistently as DD/MM/YYYY.
        labels = []
        values = []
        comparison_values = []
        
        DATE_OUTPUT_FORMAT = '%d/%m/%Y' 

        for row in monthly_query:
            if row.first_day_of_month:
                if isinstance(row.first_day_of_month, str):
                    parsed_date = datetime.strptime(row.first_day_of_month.split()[0], '%Y-%m-%d')
                    formatted_date = parsed_date.strftime(DATE_OUTPUT_FORMAT)
                else:
                    formatted_date = row.first_day_of_month.strftime(DATE_OUTPUT_FORMAT)
                    
                labels.append(formatted_date)
                values.append(float(row.monthly_revenue or 0.0))
                comparison_values.append(comparison_by_month.get(int(row.month_num), 0.0))

        return jsonify({
            "success": True,
            "is_empty": False,
            "selected_year": selected_year,
            "available_years": available_years,
            "filter": {
                "selected_year": filters["selected_year"],
                "period": filters["period"],
                "quarter": filters["quarter"],
                "month": filters["month"],
                "label": filters["label"],
            },
            "kpis": {
                "gross_revenue": float(gross_revenue),
                "total_cost_of_goods": float(total_cost),
                "profit": float(gross_revenue - total_cost),
                "comparison_gross_revenue": comparison_revenue,
                "comparison_total_cost_of_goods": comparison_cost,
                "comparison_profit": comparison_revenue - comparison_cost,
                "revenue_change_percent": percentage_change(gross_revenue, comparison_revenue),
                "cost_change_percent": percentage_change(total_cost, comparison_cost),
                "profit_change_percent": percentage_change(
                    gross_revenue - total_cost,
                    comparison_revenue - comparison_cost,
                ),
                "comparison_label": comparison_filters['label'],
                "period": period
            },
            "trend_data": {
                "labels": labels,
                "values": values,
                "comparison_values": comparison_values,
                "comparison_label": comparison_filters['label'],
            }
        })
    
    except Exception as e:
        return jsonify({"success": False, "error": public_error_message(e, 'Analytics overview could not be loaded.')}), 500

def upload_distribution(values):
    clean = [float(value or 0) for value in values]
    if not clean:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "std": 0}
    series = pd.Series(clean)
    return {
        "min": round(float(series.min()), 2),
        "max": round(float(series.max()), 2),
        "mean": round(float(series.mean()), 2),
        "median": round(float(series.median()), 2),
        "std": round(float(series.std(ddof=0) or 0), 2),
    }

def detect_upload_outliers(validated_records):
    outliers = []
    field_map = {
        "cost": "cost",
        "quantity": "qty",
        "selling_price": "selling_price",
        "total_sales": "total_sales",
    }
    for label, key in field_map.items():
        values = [float(record.get(key) or 0) for record in validated_records]
        if len(values) < 4:
            continue
        series = pd.Series(values)
        mean = float(series.mean())
        std = float(series.std(ddof=0) or 0)
        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - (1.5 * iqr)
        upper = q3 + (1.5 * iqr)
        for record, value in zip(validated_records, values):
            z_score = ((value - mean) / std) if std else 0
            if abs(z_score) >= 2.5 or (iqr and (value < lower or value > upper)):
                outliers.append({
                    "row": record.get("row_number"),
                    "field": label,
                    "value": round(value, 2),
                    "z_score": round(z_score, 2),
                    "method": "z_score_iqr",
                })
    return outliers

def build_historical_upload_eda(rows, validated_records, validation_errors, duplicate_rows, existing_duplicate_count, unused_columns, source_format):
    missing_counts = {}
    for field in ['DATE', 'COMPANY NAME', 'STORE NAME', 'COST', 'QUANTITY', 'SELLING PRICE']:
        missing_counts[field] = sum(
            1 for row in rows
            if not str(next((value for key, value in row.items() if str(key).strip().upper() == field), '') or '').strip()
        )
    numeric_values = {
        "cost": [float(record.get("cost") or 0) for record in validated_records],
        "quantity": [int(record.get("qty") or 0) for record in validated_records],
        "selling_price": [float(record.get("selling_price") or 0) for record in validated_records],
        "total_sales": [float(record.get("total_sales") or 0) for record in validated_records],
    }
    outliers = detect_upload_outliers(validated_records)
    eda_summary = {
        "rows_read": len(rows),
        "rows_ready": len(validated_records),
        "invalid_rows": len({error.get("row") for error in validation_errors}),
        "invalid_numeric_or_date_count": len(validation_errors),
        "missing_value_counts": missing_counts,
        "duplicate_rows_in_upload": duplicate_rows,
        "duplicate_rows_already_in_database": existing_duplicate_count,
        "unused_columns": unused_columns,
        "source_format": source_format,
        "outlier_count": len(outliers),
        "distributions": {field: upload_distribution(values) for field, values in numeric_values.items()},
    }
    return eda_summary, outliers

@app.route('/api/analytics/overview/upload', methods=['POST'])
@login_required
@role_required('manager', 'admin')
def upload_csv():
    """Validate analytics CSV rows and seed matching row items into analyticsData."""
    try:
        def get_upload_frame(upload):
            name = (upload.filename or '').lower()
            if name.endswith('.csv'):
                return read_admin_csv_upload(upload), 'csv'
            if name.endswith(('.xlsx', '.xls')):
                return pd.read_excel(upload), 'excel'
            raise ValueError('Upload must be a CSV or Excel file.')

        def parse_upload_date(row_number, raw_date, errors):
            if not raw_date:
                errors.append({'row': row_number, 'field': 'DATE', 'message': 'DATE is required.'})
                return None
            parsed = parse_date_value(raw_date, default_today=False, dayfirst=True)
            if not parsed:
                errors.append({'row': row_number, 'field': 'DATE', 'value': raw_date, 'message': 'Invalid date. Use DD/MM/YYYY when possible.'})
            return parsed

        def parse_upload_decimal(row_number, row, header_map, upper_header, errors):
            raw_value = row.get(header_map.get(upper_header), '')
            raw_text = '' if pd.isna(raw_value) else str(raw_value).strip()
            if not raw_text:
                errors.append({'row': row_number, 'field': upper_header, 'message': f'{upper_header} is required.'})
                return None
            cleaned = re.sub(r'[^0-9.\-]', '', raw_text.replace(',', ''))
            if cleaned in ('', '-', '.', '-.'):
                errors.append({'row': row_number, 'field': upper_header, 'value': raw_text, 'message': f'{upper_header} must be numeric.'})
                return None
            try:
                value = Decimal(cleaned)
            except InvalidOperation:
                errors.append({'row': row_number, 'field': upper_header, 'value': raw_text, 'message': f'{upper_header} must be numeric.'})
                return None
            if value <= 0:
                errors.append({'row': row_number, 'field': upper_header, 'value': raw_text, 'message': f'{upper_header} must be greater than zero.'})
                return None
            return value

        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file payload field detected.'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No selected file.'}), 400
        resolutions = parse_resolution_payload({'resolutions': request.form.get('resolutions', '{}')})
        confirmed_outliers = str(request.form.get('confirm_outliers', '')).lower() in ('1', 'true', 'yes')
        frame, source_format = get_upload_frame(file)
        rows = frame.fillna('').to_dict('records')
        original_fields = [str(column) for column in frame.columns]
        header_map = {str(column).strip().upper(): column for column in frame.columns}
        required_fields = ['DATE', 'COMPANY NAME', 'STORE NAME', 'COST', 'QUANTITY', 'SELLING PRICE']
        ledger_fields = [
            'SOURCE_TYPE', 'SOURCE_ID', 'TRANSACTION_DATE', 'FINANCIAL_STAGE',
            'FLOW_DIRECTION', 'FLOW_STATUS', 'PARTY_NAME', 'PARTY_ROLE',
            'AMOUNT', 'BALANCE_AMOUNT', 'CATEGORY', 'STATUS', 'DESCRIPTION',
        ]
        is_sales_detail = all(field in header_map for field in required_fields)
        is_historical_ledger = all(field in header_map for field in ledger_fields)

        if is_historical_ledger and not is_sales_detail:
            validation_errors = []
            validated_records = []
            duplicate_row_numbers = []
            seen_upload_keys = set()
            existing_duplicate_count = 0
            unused_columns = [
                field for field in original_fields
                if field and field.strip().upper() not in set(ledger_fields)
            ]

            def ledger_value(row, upper_header):
                value = row.get(header_map.get(upper_header), '')
                return '' if pd.isna(value) else str(value).strip()

            def required_ledger_text(row_number, row, upper_header):
                value = ledger_value(row, upper_header)
                if not value:
                    validation_errors.append({
                        'row': row_number,
                        'field': upper_header.lower(),
                        'message': f'{upper_header.lower()} is required.',
                    })
                return value

            def ledger_decimal(row_number, row, upper_header, allow_zero=False):
                raw_text = ledger_value(row, upper_header)
                if not raw_text:
                    validation_errors.append({
                        'row': row_number,
                        'field': upper_header.lower(),
                        'message': f'{upper_header.lower()} is required.',
                    })
                    return None
                cleaned = re.sub(r'[^0-9.\-]', '', raw_text.replace(',', ''))
                try:
                    value = Decimal(cleaned)
                except (InvalidOperation, ValueError):
                    validation_errors.append({
                        'row': row_number,
                        'field': upper_header.lower(),
                        'value': raw_text,
                        'message': f'{upper_header.lower()} must be numeric.',
                    })
                    return None
                if value < 0 or (not allow_zero and value == 0):
                    comparison = 'zero or greater' if allow_zero else 'greater than zero'
                    validation_errors.append({
                        'row': row_number,
                        'field': upper_header.lower(),
                        'value': raw_text,
                        'message': f'{upper_header.lower()} must be {comparison}.',
                    })
                    return None
                return value

            existing_keys = {
                (
                    item.source_type, item.source_id,
                    item.transaction_date.isoformat() if item.transaction_date else '',
                    item.flow_direction, str(Decimal(str(item.amount or 0)).normalize()),
                )
                for item in AnalyticsData.query.all()
            }

            for index, row in enumerate(rows, start=2):
                source_type = required_ledger_text(index, row, 'SOURCE_TYPE')
                source_id = required_ledger_text(index, row, 'SOURCE_ID')
                financial_stage = required_ledger_text(index, row, 'FINANCIAL_STAGE')
                flow_direction = required_ledger_text(index, row, 'FLOW_DIRECTION').upper()
                flow_status = required_ledger_text(index, row, 'FLOW_STATUS')
                party_name = required_ledger_text(index, row, 'PARTY_NAME')
                party_role = required_ledger_text(index, row, 'PARTY_ROLE')
                category = required_ledger_text(index, row, 'CATEGORY')
                status = required_ledger_text(index, row, 'STATUS')
                description = required_ledger_text(index, row, 'DESCRIPTION')
                amount = ledger_decimal(index, row, 'AMOUNT')
                balance_amount = ledger_decimal(index, row, 'BALANCE_AMOUNT', allow_zero=True)
                raw_date = ledger_value(row, 'TRANSACTION_DATE')
                parsed_date = None
                for date_format in ('%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        parsed_date = datetime.strptime(raw_date, date_format).date()
                        break
                    except (TypeError, ValueError):
                        continue
                if not raw_date or not parsed_date:
                    validation_errors.append({
                        'row': index,
                        'field': 'transaction_date',
                        'value': raw_date,
                        'message': 'transaction_date must use YYYY-MM-DD or DD/MM/YYYY.',
                    })
                if flow_direction and flow_direction not in {'INFLOW', 'OUTFLOW'}:
                    validation_errors.append({
                        'row': index,
                        'field': 'flow_direction',
                        'value': flow_direction,
                        'message': 'flow_direction must be INFLOW or OUTFLOW.',
                    })
                required_values = (
                    source_type, source_id, financial_stage, flow_direction, flow_status,
                    party_name, party_role, category, status, description,
                )
                if not all(required_values) or None in (amount, balance_amount, parsed_date):
                    continue
                duplicate_key = (
                    source_type, source_id, parsed_date.isoformat(), flow_direction,
                    str(amount.normalize()),
                )
                if duplicate_key in seen_upload_keys:
                    duplicate_row_numbers.append(index)
                seen_upload_keys.add(duplicate_key)
                if duplicate_key in existing_keys:
                    existing_duplicate_count += 1
                validated_records.append({
                    'source_type': source_type,
                    'source_id': source_id,
                    'transaction_date': parsed_date,
                    'financial_stage': financial_stage,
                    'flow_direction': flow_direction,
                    'flow_status': flow_status,
                    'party_name': party_name,
                    'party_role': party_role,
                    'amount': amount,
                    'balance_amount': balance_amount,
                    'category': category,
                    'status': status,
                    'description': description,
                    'row_number': index,
                })

            summary = {
                'schema': 'historical_ledger',
                'rows_read': len(rows),
                'rows_ready': len(validated_records),
                'invalid_rows': len({error['row'] for error in validation_errors}),
                'unused_columns': unused_columns,
                'duplicate_rows_in_upload': duplicate_row_numbers,
                'duplicate_rows_already_in_database': existing_duplicate_count,
                'date_format': 'YYYY-MM-DD or DD/MM/YYYY',
                'source_format': source_format,
            }
            if not rows:
                return jsonify({
                    'success': False,
                    'error': 'The upload has headers but no data rows.',
                    'summary': summary,
                    'validation_errors': [],
                    'outliers': [],
                }), 400
            if validation_errors:
                return jsonify({
                    'success': False,
                    'error': 'Upload rejected. Fix the invalid rows and upload again.',
                    'errors': validation_errors[:50],
                    'validation_errors': validation_errors[:50],
                    'summary': summary,
                    'outliers': [],
                }), 400
            if duplicate_row_numbers or existing_duplicate_count:
                return jsonify({
                    'success': False,
                    'error': 'Upload rejected. Remove duplicate ledger rows and upload again.',
                    'summary': summary,
                    'validation_errors': [],
                    'outliers': [],
                }), 400

            batch_id = f"HIST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(validated_records)}"
            filename = file.filename or 'historical_ledger_upload'
            for record_data in validated_records:
                db.session.add(AnalyticsData(
                    source_type=record_data['source_type'],
                    source_id=record_data['source_id'],
                    transaction_date=record_data['transaction_date'],
                    financial_stage=record_data['financial_stage'],
                    flow_direction=record_data['flow_direction'],
                    flow_status=record_data['flow_status'],
                    party_name=record_data['party_name'],
                    party_role=record_data['party_role'],
                    amount=float(record_data['amount']),
                    balance_amount=float(record_data['balance_amount']),
                    category=record_data['category'],
                    status=record_data['status'],
                    description=record_data['description'],
                    upload_batch_id=batch_id,
                    source_filename=filename,
                    source_format=source_format,
                ))
            refresh_client_financials()
            log_audit('UPLOAD_HISTORICAL_LEDGER', 'analytics_data', None, None, {
                'rows': len(validated_records), 'filename': filename, 'batch_id': batch_id,
            })
            db.session.commit()
            return jsonify({
                'success': True,
                'message': f'Success! Processing complete. {len(validated_records)} ledger entries seeded successfully.',
                'summary': summary,
                'outliers': [],
                'upload_batch_id': batch_id,
            })

        ledger_markers = {'SOURCE_TYPE', 'TRANSACTION_DATE', 'FLOW_DIRECTION', 'AMOUNT'}
        if not is_sales_detail and ledger_markers.intersection(header_map):
            missing_fields = [field for field in ledger_fields if field not in header_map]
            summary = {
                'rows_read': len(rows),
                'rows_ready': 0,
                'missing_columns': missing_fields,
                'required_columns': [field.lower() for field in ledger_fields],
                'schema': 'historical_ledger',
                'source_format': source_format,
            }
            return jsonify({
                'success': False,
                'error': 'Schema verification mismatch.',
                'summary': summary,
                'validation_errors': [
                    {'row': 1, 'field': field.lower(), 'message': 'Required column is missing.'}
                    for field in missing_fields
                ],
                'outliers': [],
            }), 400

        missing_fields = [field for field in required_fields if field not in header_map]
        if missing_fields:
            eda_summary = {
                'rows_read': len(rows),
                'rows_ready': 0,
                'missing_columns': missing_fields,
                'required_columns': required_fields,
                'accepted_ledger_columns': [field.lower() for field in ledger_fields],
                'source_format': source_format,
            }
            return jsonify({
                'success': False,
                'error': 'Schema verification mismatch.',
                'summary': eda_summary,
                'eda_summary': eda_summary,
                'validation_errors': [{'row': 1, 'field': field, 'message': 'Required column is missing.'} for field in missing_fields],
                'outliers': [],
            }), 400

        def row_value(row, upper_header):
            value = row.get(header_map.get(upper_header), '')
            return '' if pd.isna(value) else str(value).strip()

        validation_errors = []
        validated_records = []
        duplicate_row_numbers = []
        seen_upload_keys = set()
        existing_duplicate_count = 0
        used_fields = set(required_fields + ['STORE BRANCH', 'PARTICULAR'])
        unused_columns = [field for field in original_fields if field and field.strip().upper() not in used_fields]
        existing_keys = {
            (
                item.party_name,
                item.description or '',
                str(item.amount),
                item.transaction_date.isoformat() if item.transaction_date else ''
            )
            for item in AnalyticsData.query.filter_by(source_type='HISTORICAL_UPLOAD').all()
        }

        for index, row in enumerate(rows, start=2):
            company_name = row_value(row, 'COMPANY NAME')
            store_name = row_value(row, 'STORE NAME')
            if not company_name:
                validation_errors.append({'row': index, 'field': 'COMPANY NAME', 'message': 'COMPANY NAME is required.'})
            if not store_name:
                validation_errors.append({'row': index, 'field': 'STORE NAME', 'message': 'STORE NAME is required.'})
            store_branch = row_value(row, 'STORE BRANCH') or DEFAULT_STORE_BRANCH
            particular = row_value(row, 'PARTICULAR') or None
            cost = parse_upload_decimal(index, row, header_map, 'COST', validation_errors)
            qty_decimal = parse_upload_decimal(index, row, header_map, 'QUANTITY', validation_errors)
            selling_price = parse_upload_decimal(index, row, header_map, 'SELLING PRICE', validation_errors)
            parsed_date = parse_upload_date(index, row_value(row, 'DATE'), validation_errors)
            if qty_decimal is not None and qty_decimal != qty_decimal.to_integral_value():
                validation_errors.append({'row': index, 'field': 'QUANTITY', 'value': str(qty_decimal), 'message': 'QUANTITY must be a whole number.'})
                qty_decimal = None
            if None in (cost, qty_decimal, selling_price, parsed_date) or not company_name or not store_name:
                continue
            total_sales = selling_price * qty_decimal
            duplicate_key = (company_name, particular or store_name, str(total_sales), parsed_date.isoformat())
            if duplicate_key in seen_upload_keys:
                duplicate_row_numbers.append(index)
            seen_upload_keys.add(duplicate_key)
            if duplicate_key in existing_keys:
                existing_duplicate_count += 1
            validated_records.append({
                'company_name': company_name,
                'store_name': store_name,
                'store_branch': store_branch,
                'particular': particular,
                'cost': cost,
                'qty': int(qty_decimal),
                'selling_price': selling_price,
                'total_sales': total_sales,
                'date': parsed_date,
                'row_number': index,
            })

        eda_summary, outliers = build_historical_upload_eda(
            rows, validated_records, validation_errors, duplicate_row_numbers,
            existing_duplicate_count, unused_columns, source_format
        )
        summary = {
            'rows_read': len(rows),
            'rows_ready': len(validated_records),
            'invalid_rows': len({error['row'] for error in validation_errors}),
            'unused_columns': unused_columns,
            'duplicate_rows_in_upload': duplicate_row_numbers,
            'duplicate_rows_already_in_database': existing_duplicate_count,
            'date_format': 'DD/MM/YYYY',
            'source_format': source_format,
            'eda_summary': eda_summary,
        }
        if not rows:
            return jsonify({'success': False, 'error': 'The upload has headers but no data rows.', 'summary': summary, 'eda_summary': eda_summary, 'validation_errors': validation_errors, 'outliers': outliers}), 400
        if validation_errors:
            return jsonify({'success': False, 'error': 'Upload rejected. Fix the invalid rows and upload again.', 'errors': validation_errors[:50], 'validation_errors': validation_errors[:50], 'summary': summary, 'eda_summary': eda_summary, 'outliers': outliers[:50]}), 400
        if outliers and not confirmed_outliers:
            return jsonify({'success': False, 'requires_confirmation': True, 'error': 'EDA found outliers. Review them, then confirm the upload to save.', 'summary': summary, 'eda_summary': eda_summary, 'outliers': outliers[:50]}), 409

        client_resolutions = []
        for idx, record_data in enumerate(validated_records, start=2):
            resolution = resolve_client_name(record_data['company_name'], resolutions, create_client=False)
            if resolution['status'] == 'needs_choice':
                client_resolutions.append(client_resolution_public(resolution, idx))
        if client_resolutions:
            summary['client_resolutions'] = client_resolutions
            return jsonify({'success': False, 'needs_resolution': True, 'error': 'Some company names look similar to existing clients. Choose whether to use the suggested client or create a new client.', 'summary': summary, 'client_resolutions': client_resolutions, 'eda_summary': eda_summary, 'outliers': outliers[:50]}), 409

        records_to_insert = []
        for record_data in validated_records:
            resolution = resolve_client_name(record_data['company_name'], resolutions, create_client=True)
            if resolution['status'] == 'ignored':
                continue
            record_data['company_name'] = resolution['client_name']
            records_to_insert.append(record_data)
        batch_id = f"HIST-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(records_to_insert)}"
        filename = file.filename or 'analytics_upload'
        for insert_index, record_data in enumerate(records_to_insert, start=1):
            amount = float(record_data['total_sales'])
            db.session.add(AnalyticsData(
                source_type='HISTORICAL_UPLOAD',
                source_id=f"{batch_id}-{insert_index}",
                transaction_date=record_data['date'],
                financial_stage='PAID',
                flow_direction='INFLOW',
                flow_status='ACTUAL',
                party_name=record_data['company_name'],
                party_role='CUSTOMER',
                amount=amount,
                balance_amount=0,
                category='HISTORICAL_SALES',
                status='HISTORICAL',
                description=record_data.get('particular') or record_data.get('store_name') or 'Historical sales upload',
                upload_batch_id=batch_id,
                source_filename=filename,
                source_format=source_format,
            ))
        refresh_client_financials()
        log_audit('UPLOAD_HISTORICAL_ANALYTICS', 'analytics_data', None, None, {'rows': len(records_to_insert), 'filename': filename, 'batch_id': batch_id})
        db.session.commit()
        return jsonify({'success': True, 'message': f'Success! Processing complete. {len(records_to_insert)} entries seeded successfully.', 'summary': summary, 'eda_summary': eda_summary, 'outliers': outliers[:50], 'upload_batch_id': batch_id})

        # Read directly from stream buffer into string wrapper context
        csv_file = TextIOWrapper(file.stream, encoding='latin-1')
        
        # FIX: Normalize headers to uppercase directly to handle any user capitalization variance
        reader = csv.DictReader(csv_file)
        original_fields = reader.fieldnames or []
        
        # Create a mapping of UPPERCASE_HEADER -> original_header
        header_map = {h.strip().upper(): h for h in original_fields}
        
        required_fields = ['DATE', 'COMPANY NAME', 'STORE NAME', 'COST', 'QUANTITY', 'SELLING PRICE']
        if not all(field in header_map for field in required_fields):
            missing_fields = [field for field in required_fields if field not in header_map]
            return jsonify({
                'success': False, 
                'error': 'Schema verification mismatch.',
                'summary': {
                    'missing_columns': missing_fields,
                    'required_columns': required_fields
                }
            }), 400

        # Helper to safely clean price/numeric strings from currency characters (e.g., "₱1,250.50" -> 1250.50)
        def clean_numeric_string(val):
            if not val:
                return "0"
            return val.replace('₱', '').replace(',', '').strip()

        used_fields = set(required_fields + ['STORE BRANCH', 'PARTICULAR'])
        unused_columns = [h for h in original_fields if h and h.strip().upper() not in used_fields]

        def get_row_val(row, upper_header):
            orig_header = header_map.get(upper_header)
            return row.get(orig_header, '').strip() if orig_header else ''

        def parse_required_text(row_number, row, upper_header, errors):
            value = get_row_val(row, upper_header)
            if not value:
                errors.append({
                    'row': row_number,
                    'field': upper_header,
                    'message': f'{upper_header} is required.'
                })
            return value

        def parse_csv_date(row_number, raw_date, errors):
            if not raw_date:
                errors.append({
                    'row': row_number,
                    'field': 'DATE',
                    'message': 'DATE is required and must use DD/MM/YYYY, for example 01/01/2025.'
                })
                return None
            if not re.match(r'^\d{2}/\d{2}/\d{4}$', raw_date):
                errors.append({
                    'row': row_number,
                    'field': 'DATE',
                    'value': raw_date,
                    'message': 'Invalid date format. Use DD/MM/YYYY, for example 01/01/2025.'
                })
                return None
            try:
                return datetime.strptime(raw_date, '%d/%m/%Y').date()
            except ValueError:
                errors.append({
                    'row': row_number,
                    'field': 'DATE',
                    'value': raw_date,
                    'message': 'Invalid calendar date. Use a real date in DD/MM/YYYY format.'
                })
                return None

        def parse_decimal(row_number, row, upper_header, errors):
            raw_value = get_row_val(row, upper_header)
            if not raw_value:
                errors.append({
                    'row': row_number,
                    'field': upper_header,
                    'message': f'{upper_header} is required.'
                })
                return None
            cleaned = re.sub(r'[^0-9.\-]', '', raw_value.replace(',', ''))
            if cleaned in ('', '-', '.', '-.'):
                errors.append({
                    'row': row_number,
                    'field': upper_header,
                    'value': raw_value,
                    'message': f'{upper_header} must be a valid number.'
                })
                return None
            try:
                return Decimal(cleaned)
            except InvalidOperation:
                errors.append({
                    'row': row_number,
                    'field': upper_header,
                    'value': raw_value,
                    'message': f'{upper_header} must be a valid number.'
                })
                return None

        def parse_quantity(row_number, row, errors):
            qty_decimal = parse_decimal(row_number, row, 'QUANTITY', errors)
            if qty_decimal is None:
                return None
            if qty_decimal != qty_decimal.to_integral_value():
                errors.append({
                    'row': row_number,
                    'field': 'QUANTITY',
                    'value': get_row_val(row, 'QUANTITY'),
                    'message': 'QUANTITY must be a whole number.'
                })
                return None
            return int(qty_decimal)

        rows = list(reader)
        validation_errors = []
        validated_records = []
        duplicate_row_numbers = []
        seen_upload_keys = set()
        existing_duplicate_count = 0

        existing_keys = {
            (
                item.party_name,
                item.description or '',
                str(item.amount),
                item.transaction_date.isoformat() if item.transaction_date else ''
            )
            for item in AnalyticsData.query.filter_by(source_type='HISTORICAL_UPLOAD').all()
        }

        for index, row in enumerate(rows, start=2):
            company_name = parse_required_text(index, row, 'COMPANY NAME', validation_errors)
            store_name = parse_required_text(index, row, 'STORE NAME', validation_errors)
            store_branch = get_row_val(row, 'STORE BRANCH') or DEFAULT_STORE_BRANCH
            particular = get_row_val(row, 'PARTICULAR') or None
            cost = parse_decimal(index, row, 'COST', validation_errors)
            qty = parse_quantity(index, row, validation_errors)
            selling_price = parse_decimal(index, row, 'SELLING PRICE', validation_errors)
            parsed_date = parse_csv_date(index, get_row_val(row, 'DATE'), validation_errors)

            if None in (cost, qty, selling_price, parsed_date) or not company_name or not store_name:
                continue

            duplicate_key = (
                company_name,
                particular or store_name,
                str(selling_price * qty),
                parsed_date.isoformat()
            )
            if duplicate_key in seen_upload_keys:
                duplicate_row_numbers.append(index)
            seen_upload_keys.add(duplicate_key)
            if duplicate_key in existing_keys:
                existing_duplicate_count += 1

            validated_records.append({
                'company_name': company_name,
                'store_name': store_name,
                'store_branch': store_branch,
                'particular': particular,
                'cost': cost,
                'qty': qty,
                'selling_price': selling_price,
                'date': parsed_date
            })

        summary = {
            'rows_read': len(rows),
            'rows_ready': len(validated_records),
            'invalid_rows': len({error['row'] for error in validation_errors}),
            'unused_columns': unused_columns,
            'duplicate_rows_in_upload': duplicate_row_numbers,
            'duplicate_rows_already_in_database': existing_duplicate_count,
            'date_format': 'DD/MM/YYYY'
        }

        if not rows:
            return jsonify({
                'success': False,
                'error': 'The CSV has headers but no data rows.',
                'summary': summary
            }), 400

        if validation_errors:
            return jsonify({
                'success': False,
                'error': 'Upload rejected. Fix the invalid rows and upload again.',
                'errors': validation_errors[:50],
                'summary': summary
            }), 400

        client_resolutions = []
        for idx, record_data in enumerate(validated_records, start=2):
            resolution = resolve_client_name(
                record_data['company_name'],
                resolutions,
                create_client=False
            )
            if resolution['status'] == 'needs_choice':
                client_resolutions.append(client_resolution_public(resolution, idx))

        if client_resolutions:
            summary['client_resolutions'] = client_resolutions
            return jsonify({
                'success': False,
                'needs_resolution': True,
                'error': 'Some company names look similar to existing clients. Choose whether to use the suggested client or create a new client.',
                'summary': summary,
                'client_resolutions': client_resolutions
            }), 409

        records_to_insert = []
        for record_data in validated_records:
            resolution = resolve_client_name(
                record_data['company_name'],
                resolutions,
                create_client=True
            )
            if resolution['status'] == 'ignored':
                continue
            record_data['company_name'] = resolution['client_name']
            records_to_insert.append(record_data)

        for insert_index, record_data in enumerate(records_to_insert, start=1):
            amount = float(record_data['selling_price']) * float(record_data['qty'])
            db.session.add(AnalyticsData(
                source_type='HISTORICAL_UPLOAD',
                source_id=f"HIST-{record_data['date'].isoformat()}-{insert_index}",
                transaction_date=record_data['date'],
                financial_stage='PAID',
                flow_direction='INFLOW',
                flow_status='ACTUAL',
                party_name=record_data['company_name'],
                party_role='CUSTOMER',
                amount=amount,
                balance_amount=0,
                category='HISTORICAL_SALES',
                status='HISTORICAL',
                description=record_data.get('particular') or record_data.get('store_name') or 'Historical sales upload'
            ))

        refresh_client_financials()
        log_audit('UPLOAD_HISTORICAL_CSV', 'analytics_data', None, None, {'rows': len(records_to_insert), 'filename': file.filename})
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Success! Processing complete. {len(records_to_insert)} entries seeded successfully.',
            'summary': summary
        })
        
    except Exception as e:
        db.session.rollback() # Good practice to roll back if an insert crashes midway
        return jsonify({"success": False, "error": public_error_message(e, 'Historical data upload failed. Check the file format and content.')}), 500

@app.route('/api/analytics/clients')
@login_required
@role_required('manager', 'admin')
def api_analytics_clients():
    """Get clients analysis data."""
    try:
        filters = parse_report_date_filter()
        clients_data = get_clients_analysis(db, app_models(), filters['start_date'], filters['end_date'])
        return jsonify({'success': True, 'filter': {
            'selected_year': filters['selected_year'],
            'period': filters['period'],
            'quarter': filters['quarter'],
            'month': filters['month'],
            'label': filters['label'],
        }, **clients_data})
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'Client analytics could not be loaded.')}), 400

@app.route('/api/analytics/expenses')
@login_required
@role_required('manager', 'admin')
def api_analytics_expenses():
    """Get expenses breakdown data."""
    try:
        filters = parse_report_date_filter()
        expenses = get_expenses_breakdown(
            db,
            PurchaseOrder,
            filters['start_date'],
            filters['end_date'],
        )
        return jsonify({
            'success': True,
            'filter': {
                'selected_year': filters['selected_year'],
                'period': filters['period'],
                'quarter': filters['quarter'],
                'month': filters['month'],
                'label': filters['label'],
            },
            'fixed_expenses': expenses['fixed_expenses'],
            'variable_expenses': expenses['variable_expenses'],
            'total_expenses': expenses['total_expenses'],
            'fixed_share_percent': expenses['fixed_share_percent'],
            'variable_share_percent': expenses['variable_share_percent'],
            'fixed_items': expenses['fixed_items'],
            'variable_items': expenses['variable_items'],
            'ranked_particulars': expenses['ranked_particulars'],
            'ranked_suppliers': expenses['ranked_suppliers'],
            'pie_data': expenses['pie_data']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'Expense analytics could not be loaded.')}), 400

@app.route('/api/analytics/sales')
@login_required
@role_required('manager', 'admin')
def api_analytics_sales():
    """Get sales KPIs, history, and forecast."""
    try:
        threshold = request.args.get('mape_threshold', default=20.0, type=float)
        filters = parse_report_date_filter()
        return jsonify({'success': True, 'filter': {
            'selected_year': filters['selected_year'],
            'period': filters['period'],
            'quarter': filters['quarter'],
            'month': filters['month'],
            'label': filters['label'],
        }, **get_sales_analysis(db, app_models(), threshold, filters['start_date'], filters['end_date'])})
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'Sales analytics could not be loaded.')}), 400

def likert_interpretation(mean_score):
    if mean_score >= 4.21:
        return 'Strongly Agree'
    if mean_score >= 3.41:
        return 'Agree'
    if mean_score >= 2.61:
        return 'Neutral'
    if mean_score >= 1.81:
        return 'Disagree'
    return 'Strongly Disagree'

@app.route('/evaluation')
@login_required
@role_required(*ALL_BUSINESS_ROLES)
def evaluation():
    return render_template(
        'evaluation.html',
        can_view_results=session.get('role') == 'admin',
    )

@app.route('/api/evaluation/questions')
@login_required
@role_required(*ALL_BUSINESS_ROLES)
def evaluation_questions():
    seed_evaluation_questions()
    questions = EvaluationQuestion.query.filter_by(is_active=True).order_by(EvaluationQuestion.display_order.asc()).all()
    return jsonify({
        'success': True,
        'scale': [
            {'value': 1, 'label': 'Strongly Disagree'},
            {'value': 2, 'label': 'Disagree'},
            {'value': 3, 'label': 'Neutral'},
            {'value': 4, 'label': 'Agree'},
            {'value': 5, 'label': 'Strongly Agree'},
        ],
        'questions': [
            {'id': question.id, 'category': question.category, 'question_text': question.question_text, 'display_order': question.display_order}
            for question in questions
        ],
    })

@app.route('/api/evaluation/responses', methods=['POST'])
@login_required
@role_required(*ALL_BUSINESS_ROLES)
def evaluation_responses():
    payload = request.get_json() or {}
    responses = payload.get('responses') or []
    active_questions = EvaluationQuestion.query.filter_by(is_active=True).order_by(EvaluationQuestion.display_order.asc()).all()
    if len(responses) != len(active_questions):
        return jsonify({'success': False, 'error': 'A rating is required for every evaluation question.'}), 400
    ratings = []
    session_record = EvaluationSession(
        user_id=session.get('user_id'),
        evaluator_name=clean_text(payload.get('evaluator_name')) or session.get('username', 'Evaluator'),
        evaluator_role=clean_text(payload.get('evaluator_role')) or session.get('role', ''),
        overall_comment=clean_text(payload.get('overall_comment'), keep_period=True, keep_ampersand=True),
    )
    db.session.add(session_record)
    db.session.flush()
    valid_question_ids = {question.id for question in active_questions}
    submitted_question_ids = set()
    for item in responses:
        question_id = int(item.get('question_id') or 0)
        rating = int(item.get('rating') or 0)
        if question_id not in valid_question_ids or question_id in submitted_question_ids or rating < 1 or rating > 5:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Invalid question or rating detected.'}), 400
        submitted_question_ids.add(question_id)
        ratings.append(rating)
        db.session.add(EvaluationResponse(
            session_id=session_record.id,
            question_id=question_id,
            rating=rating,
            comment=clean_text(item.get('comment'), keep_period=True, keep_ampersand=True),
        ))
    session_record.overall_mean = round(sum(ratings) / len(ratings), 2)
    session_record.interpretation = likert_interpretation(session_record.overall_mean)
    log_audit('SUBMIT_LIKERT_EVALUATION', 'evaluation_sessions', session_record.id, None, {'overall_mean': session_record.overall_mean})
    db.session.commit()
    return jsonify({'success': True, 'session_id': session_record.id, 'overall_mean': session_record.overall_mean, 'interpretation': session_record.interpretation})

@app.route('/api/evaluation/results')
@login_required
@role_required('admin')
def evaluation_results():
    filters = parse_report_date_filter()
    response_join_conditions = [EvaluationQuestion.id == EvaluationResponse.question_id]
    response_join_conditions.append(EvaluationResponse.created_at >= datetime.combine(filters['start_date'], datetime.min.time()))
    response_join_conditions.append(EvaluationResponse.created_at < datetime.combine(filters['end_date'], datetime.min.time()))
    rows = (
        db.session.query(EvaluationQuestion, func.avg(EvaluationResponse.rating).label('avg_rating'), func.count(EvaluationResponse.id).label('response_count'))
        .outerjoin(EvaluationResponse, and_(*response_join_conditions))
        .filter(EvaluationQuestion.is_active == True)
        .group_by(EvaluationQuestion.id)
        .order_by(EvaluationQuestion.display_order.asc())
        .all()
    )
    question_results = []
    category_totals = {}
    all_scores = []
    for question, avg_rating, response_count in rows:
        average = round(float(avg_rating or 0), 2)
        question_results.append({
            'question_id': question.id,
            'category': question.category,
            'question_text': question.question_text,
            'average': average,
            'response_count': int(response_count or 0),
            'interpretation': likert_interpretation(average) if response_count else 'No responses',
        })
        if response_count:
            category_totals.setdefault(question.category, []).append(average)
            all_scores.append(average)
    categories = [
        {
            'category': category,
            'average': round(sum(scores) / len(scores), 2),
            'interpretation': likert_interpretation(sum(scores) / len(scores)),
        }
        for category, scores in category_totals.items()
    ]
    overall_mean = round(sum(all_scores) / len(all_scores), 2) if all_scores else 0
    sessions = EvaluationSession.query.filter(
        EvaluationSession.created_at >= datetime.combine(filters['start_date'], datetime.min.time()),
        EvaluationSession.created_at < datetime.combine(filters['end_date'], datetime.min.time()),
    ).order_by(EvaluationSession.created_at.desc()).limit(10).all()
    return jsonify({
        'success': True,
        'filter': {
            'selected_year': filters['selected_year'],
            'period': filters['period'],
            'quarter': filters['quarter'],
            'month': filters['month'],
            'label': filters['label'],
        },
        'overall_mean': overall_mean,
        'interpretation': likert_interpretation(overall_mean) if all_scores else 'No responses',
        'categories': categories,
        'questions': question_results,
        'sessions': [
            {
                'id': item.id,
                'evaluator_name': item.evaluator_name,
                'evaluator_role': item.evaluator_role,
                'overall_mean': item.overall_mean,
                'interpretation': item.interpretation,
                'overall_comment': item.overall_comment,
                'created_at': item.created_at.isoformat() if item.created_at else None,
            }
            for item in sessions
        ],
    })

@app.route('/api/analytics/comparative')
@login_required
@role_required('manager', 'admin')
def api_analytics_comparative():
    """Get comparative analysis for two years."""
    try:
        today = datetime.now().date()
        year1 = request.args.get('year1', today.year - 1, type=int)
        year2 = request.args.get('year2', today.year, type=int)
        
        comparison = get_comparative_analysis(
            db,
            Invoice,
            year1,
            year2,
            CollectionReceipt,
        )
        return jsonify({
            'success': True,
            'comparison': comparison
        })
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'Comparative analytics could not be loaded.')}), 400

@app.route('/get-analytics')
@login_required
@role_required('manager', 'admin')
def get_analytics():
    try:
        filters = parse_report_date_filter()
        analytics_data = build_analytics_payload(
            db,
            app_models(),
            filters['start_date'],
            filters['end_date'],
        )
        analytics_data['selected_year'] = filters['selected_year']
        analytics_data['available_years'] = filters['available_years']
        return jsonify({'success': True, 'analytics': analytics_data})
    
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'Analytics could not be loaded.')}), 500

@app.route('/analytics/excel-preview', methods=['POST'])
@login_required
@role_required('manager', 'admin')
def analytics_excel_preview():
    try:
        upload = request.files.get('excel_file')
        if not upload:
            return jsonify({'success': False, 'error': 'Excel file is required'}), 400
        filename = secure_filename(upload.filename or '').lower()
        if not filename.endswith(('.xlsx', '.xls')):
            return jsonify({'success': False, 'error': 'Upload must be an Excel workbook.'}), 400
        return jsonify({'success': True, 'workbook': preview_excel_workbook(upload)})
    except Exception as e:
        return jsonify({'success': False, 'error': public_error_message(e, 'The workbook could not be read.')}), 400

@app.route('/dev/viewer')
@login_required
@role_required('manager', 'admin')  # Keeping same permissions as your analytics route
def dev_json_viewer():
    """Render the generic HTML page to inspect and test returned JSON data."""
    if IS_PRODUCTION:
        return render_error_interface('empty', 404)
    return render_template('json.html')

init_db()

if __name__ == '__main__':
    app.run(debug=os.environ.get('FLASK_DEBUG', '').lower() == 'true')

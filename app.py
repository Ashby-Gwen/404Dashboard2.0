# store name ang focus hindi company name.
try:
    from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, Response  # type: ignore[import]
    # from flask_login import login_required
    from flask_sqlalchemy import SQLAlchemy  # type: ignore[import]
    from werkzeug.security import generate_password_hash, check_password_hash  # type: ignore[import]
    from werkzeug.utils import secure_filename  # type: ignore[import]
    from collections import defaultdict
    from sqlalchemy import func, extract, asc, desc, or_, and_, case # type: ignore[import]
    from sqlalchemy.orm import selectinload, synonym
    from decimal import Decimal, InvalidOperation     # <--- ADD THIS LINE HERE
    import pandas as pd  # type: ignore[import]
    from openpyxl import load_workbook  # type: ignore[import]
    from openpyxl.utils import get_column_letter  # type: ignore[import]
    import Levenshtein  # type: ignore[import]
    import csv  # <--- ADD THIS LINE TO YOUR IMPORTS
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
import sqlite3
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

app = Flask(__name__)
os.makedirs(app.instance_path, exist_ok=True)
os.makedirs(os.path.join(app.static_folder, 'uploads', 'profiles'), exist_ok=True)

default_database_path = os.path.join(app.instance_path, 'syluxent.db').replace(os.sep, '/')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
# Render free services use an ephemeral filesystem, so this SQLite fallback is suitable
# only for capstone demos/prototypes. Use SYLUXENT_DATABASE_URI for any persistent DB.
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('SYLUXENT_DATABASE_URI', f'sqlite:///{default_database_path}')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(255), unique=True)
    password_hash = db.Column(db.String(120), nullable=False)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False)
    status = db.Column(db.String(20), default='ACTIVE', nullable=False)
    profile_photo = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    role = db.relationship('Role', backref='users')

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

class SalesOrderItem(db.Model):
    __tablename__ = 'sales_order_items'
    id = db.Column(db.Integer, primary_key=True)
    sales_order_id = db.Column(db.Integer, db.ForeignKey('sales_orders.id'), nullable=False)
    particular = db.Column(db.String(500), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit_cost = db.Column(db.Float, nullable=False)
    selling_price = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)

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
    evaluator_name = db.Column(db.String(120), nullable=False)
    evaluator_role = db.Column(db.String(80))
    overall_comment = db.Column(db.Text)
    overall_mean = db.Column(db.Float, default=0.0)
    interpretation = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    responses = db.relationship('EvaluationResponse', backref='session', cascade='all, delete-orphan')

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

# End of Models Section


# Authentication Decorators
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = db.session.get(User, session['user_id'])
        if not user or user.status != 'ACTIVE':
            session.clear()
            flash('Your account is inactive. Contact the administrator.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            
            user = db.session.get(User, session['user_id'])
            if not user or user.status != 'ACTIVE' or user.role.role_name not in allowed_roles:
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
        'SalesOrderItem': SalesOrderItem,
        'Invoice': Invoice,
        'PurchaseOrder': PurchaseOrder,
        'PurchaseOrderDebit': PurchaseOrderDebit,
        'SessionRecord': SessionRecord,
        'AuditLog': AuditLog,
        'PasswordReset': PasswordReset,
        'AnalyticsData': AnalyticsData,
        'EvaluationSession': EvaluationSession,
        'EvaluationQuestion': EvaluationQuestion,
        'EvaluationResponse': EvaluationResponse,
    }

def admin_required_json():
    if session.get('role') != 'admin':
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

def read_theme_settings():
    settings = default_theme_settings()
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
    os.makedirs(os.path.dirname(THEME_CSS_PATH), exist_ok=True)
    with open(THEME_JSON_PATH, 'w', encoding='utf-8') as theme_file:
        json.dump(settings, theme_file, indent=2)
    with open(THEME_CSS_PATH, 'w', encoding='utf-8') as css_file:
        css_file.write(build_theme_css(settings))

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


def sales_order_admin_payload(order):
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
        'total_amount': float(order.total_amount or 0),
        'status': order.status,
    }


def admin_client_list_payload():
    clients = (
        Client.query
        .options(
            selectinload(Client.aliases),
            selectinload(Client.sales_orders),
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

    for sales_order in SalesOrder.query.all():
        if sales_order.client_id in financials:
            financials[sales_order.client_id]['sales_revenue'] += float(sales_order.total_amount or 0)

    linked_invoices = (
        Invoice.query
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
                current_payment_last = financials[client_id]['last_payment_date']
                if current_payment_last is None or invoice.invoice_date > current_payment_last:
                    financials[client_id]['last_payment_date'] = invoice.invoice_date

    admin_invoices = Invoice.query.filter(Invoice.sales_order_id.is_(None)).filter(Invoice.uploaded_client_name.isnot(None)).all()
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
                current_payment_last = financials[matched_client.id]['last_payment_date']
                if current_payment_last is None or invoice.invoice_date > current_payment_last:
                    financials[matched_client.id]['last_payment_date'] = invoice.invoice_date

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
        db.session.query(func.strftime('%Y', SalesOrder.order_date).label('year'))
        .filter(SalesOrder.order_date.isnot(None))
        .union(
            db.session.query(func.strftime('%Y', Invoice.invoice_date).label('year'))
            .filter(Invoice.invoice_date.isnot(None)),
            db.session.query(func.strftime('%Y', PurchaseOrder.date).label('year'))
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

def date_range_filter(query, column, filters):
    return query.filter(column >= filters['start_date'], column < filters['end_date'])

def revenue_report_rows(filters=None):
    query = (
        db.session.query(Invoice, SalesOrder, Client)
        .select_from(Invoice)
        .join(SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True)
        .join(Client, SalesOrder.client_id == Client.id, isouter=True)
        .filter(Invoice.amount_paid > 0)
    )
    if filters:
        query = date_range_filter(query, Invoice.invoice_date, filters)
    rows = query.order_by(Invoice.invoice_date.asc(), Invoice.id.asc()).all()
    return [
        {
            'invoice_date': invoice.invoice_date.isoformat() if invoice.invoice_date else None,
            'invoice_number': invoice.invoice_number,
            'so_number': order.so_number if order else '',
            'client_name': client.client_name if client else (invoice.uploaded_client_name or 'Admin Upload'),
            'invoice_type': invoice.invoice_type,
            'payment_type': invoice.payment_type,
            'cr_number': invoice.cr_number,
            'total_amount': float(invoice.total_amount or 0),
            'amount_paid': float(invoice.amount_paid or 0),
            'balance': float(invoice.balance or 0),
            'status': invoice.status,
        }
        for invoice, order, client in rows
    ]

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
            'particular': item.particular,
            'quantity': float(item.quantity or 0),
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
        raise ValueError(f'Invalid purchase order ID: {value}')
    if not parsed.is_integer() or parsed <= 0:
        raise ValueError(f'Invalid purchase order ID: {value}')
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
        return {
            'so_number': clean_text(lower.get('so_number') or lower.get('s.o_no') or lower.get('order_number')),
            'client_name': clean_text(lower.get('client_name') or lower.get('company_name') or lower.get('company'), keep_period=True),
            'company_name': clean_text(lower.get('company_name') or lower.get('company'), keep_period=True),
            'store_name': clean_text(lower.get('store_name') or lower.get('store')),
            'store_branch': clean_text(lower.get('store_branch') or lower.get('branch')),
            'order_date': parse_date_value(lower.get('order_date') or lower.get('date')).isoformat(),
            'sales_staff': clean_text(lower.get('sales_staff') or lower.get('staff')),
            'particular': clean_text(lower.get('particular') or lower.get('particulars') or lower.get('item')),
            'quantity': parse_amount(lower.get('quantity') or lower.get('qty')),
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
        lower.get('client') or lower.get('client_name') or lower.get('company_name') or lower.get('company'),
        keep_period=True,
        keep_ampersand=True
    )
    so_number = clean_code(lower.get('so_number') or lower.get('sales_order'))
    is_admin_upload = bool(uploaded_client_name and not so_number)
    raw_total = lower.get('total_amount') if lower.get('total_amount') not in (None, '') else lower.get('amount')
    raw_balance = lower.get('balance')
    return {
        'invoice_number': clean_code(lower.get('invoice_number') or lower.get('invoice_no')),
        'uploaded_client_name': uploaded_client_name,
        'so_number': so_number,
        'invoice_type': 'ADMIN UPLOAD' if is_admin_upload else (clean_text(lower.get('invoice_type') or 'SALES') or 'SALES').upper(),
        'invoice_date': parse_date_value(lower.get('invoice_date') or lower.get('date')).isoformat(),
        'summary': clean_text(lower.get('summary') or lower.get('description')) or ('Admin Upload' if is_admin_upload else ''),
        'payment_type': 'Admin Upload' if is_admin_upload else clean_text(lower.get('payment_type')),
        'cr_number': clean_code(lower.get('cr_number') or lower.get('cr_no')),
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

def pending_password_reset_count():
    if session.get('role') != 'admin':
        return 0
    return PasswordReset.query.filter_by(status='PENDING').count()

@app.context_processor
def inject_user_navigation():
    current_user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    return {
        'current_user': current_user,
        'pending_notification_count': pending_password_reset_count(),
    }

# Initialize Database
def get_configured_sqlite_path():
    database_path = db.engine.url.database
    if not database_path or database_path == ':memory:':
        return None
    if os.path.isabs(database_path):
        return database_path
    return os.path.join(app.instance_path, database_path)

def ensure_schema_updates():
    db_path = get_configured_sqlite_path()
    if not db_path:
        return
    if not os.path.exists(db_path):
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [column[1] for column in cursor.fetchall()]
        if 'email' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        if 'status' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'")
        if 'profile_photo' not in user_columns:
            cursor.execute("ALTER TABLE users ADD COLUMN profile_photo VARCHAR(255)")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS password_resets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username VARCHAR(80) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
                requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                resolved_by_user_id INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(resolved_by_user_id) REFERENCES users(id)
            )
        """)

        cursor.execute("PRAGMA table_info(clients)")
        client_columns = [column[1] for column in cursor.fetchall()]
        if 'status' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE'")
        if 'total_revenue' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN total_revenue FLOAT DEFAULT 0.0")
        if 'total_paid' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN total_paid FLOAT DEFAULT 0.0")
        if 'total_balance' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN total_balance FLOAT DEFAULT 0.0")
        if 'balance_status' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN balance_status VARCHAR(30) DEFAULT 'Settled'")
        if 'last_invoice_date' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN last_invoice_date DATE")
        if 'last_payment_date' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN last_payment_date DATE")
        if 'financials_updated_at' not in client_columns:
            cursor.execute("ALTER TABLE clients ADD COLUMN financials_updated_at DATETIME")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS client_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias_name VARCHAR(200) NOT NULL,
                normalized_alias VARCHAR(200) NOT NULL UNIQUE,
                client_id INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'ACTIVE',
                created_at DATETIME,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            )
        """)
        cursor.execute("PRAGMA table_info(sales_orders)")
        sales_order_columns = [column[1] for column in cursor.fetchall()]
        if 'official_client_name' not in sales_order_columns:
            cursor.execute("ALTER TABLE sales_orders ADD COLUMN official_client_name VARCHAR(200)")
        if 'original_entered_client_name' not in sales_order_columns:
            cursor.execute("ALTER TABLE sales_orders ADD COLUMN original_entered_client_name VARCHAR(200)")

        cursor.execute("PRAGMA table_info(purchase_orders)")
        purchase_order_columns = [column[1] for column in cursor.fetchall()]
        if 'status' not in purchase_order_columns:
            cursor.execute("ALTER TABLE purchase_orders ADD COLUMN status VARCHAR(20) DEFAULT 'PENDING'")
        if 'category' not in purchase_order_columns:
            cursor.execute("ALTER TABLE purchase_orders ADD COLUMN category VARCHAR(20) DEFAULT 'FIXED'")

        cursor.execute("PRAGMA table_info(invoices)")
        invoice_info = cursor.fetchall()
        invoice_columns = [column[1] for column in invoice_info]
        if 'cr_number' not in invoice_columns:
            cursor.execute("ALTER TABLE invoices ADD COLUMN cr_number VARCHAR(50)")
        if 'uploaded_client_name' not in invoice_columns:
            cursor.execute("ALTER TABLE invoices ADD COLUMN uploaded_client_name VARCHAR(200)")
        if 'upload_source' not in invoice_columns:
            cursor.execute("ALTER TABLE invoices ADD COLUMN upload_source VARCHAR(50)")
        if 'admin_upload_note' not in invoice_columns:
            cursor.execute("ALTER TABLE invoices ADD COLUMN admin_upload_note TEXT")

        cursor.execute("PRAGMA table_info(invoices)")
        invoice_info = cursor.fetchall()
        invoice_constraints = {column[1]: column for column in invoice_info}
        requires_invoice_rebuild = any(
            invoice_constraints.get(column_name, [None, None, None, 0])[3]
            for column_name in ('sales_order_id', 'total_amount', 'balance')
        )
        if requires_invoice_rebuild:
            rebuild_invoices_for_admin_upload(cursor)

        ensure_analytics_data_ledger_schema(cursor)
        ensure_evaluation_schema(cursor)
        cursor.execute("DROP TABLE IF EXISTS analytics_table")

        conn.commit()
    finally:
        conn.close()

def ensure_analytics_data_ledger_schema(cursor):
    cursor.execute("PRAGMA table_info(analytics_data)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    if existing_columns:
        if 'upload_batch_id' not in existing_columns:
            cursor.execute("ALTER TABLE analytics_data ADD COLUMN upload_batch_id VARCHAR(80)")
        if 'source_filename' not in existing_columns:
            cursor.execute("ALTER TABLE analytics_data ADD COLUMN source_filename VARCHAR(255)")
        if 'source_format' not in existing_columns:
            cursor.execute("ALTER TABLE analytics_data ADD COLUMN source_format VARCHAR(20)")
        return
    ledger_columns = {
        'analytics_id', 'source_type', 'source_id', 'transaction_date',
        'financial_stage', 'flow_direction', 'flow_status', 'party_name',
        'party_role', 'amount', 'balance_amount', 'category', 'status', 'description',
        'upload_batch_id', 'source_filename', 'source_format', 'created_at'
    }
    if set(existing_columns) == ledger_columns:
        return
    cursor.execute("DROP TABLE IF EXISTS analytics_data")
    cursor.execute("""
        CREATE TABLE analytics_data (
            analytics_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            transaction_date DATE NOT NULL,
            financial_stage TEXT NOT NULL,
            flow_direction TEXT NOT NULL,
            flow_status TEXT NOT NULL,
            party_name TEXT NOT NULL,
            party_role TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            balance_amount REAL DEFAULT 0,
            category TEXT NOT NULL,
            status TEXT,
            description TEXT,
            upload_batch_id VARCHAR(80),
            source_filename VARCHAR(255),
            source_format VARCHAR(20),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

def ensure_evaluation_schema(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evaluator_name VARCHAR(120) NOT NULL,
            evaluator_role VARCHAR(80),
            overall_comment TEXT,
            overall_mean FLOAT DEFAULT 0.0,
            interpretation VARCHAR(50),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category VARCHAR(80) NOT NULL,
            question_text TEXT NOT NULL,
            display_order INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evaluation_responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            question_id INTEGER NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(session_id) REFERENCES evaluation_sessions(id),
            FOREIGN KEY(question_id) REFERENCES evaluation_questions(id)
        )
    """)

def rebuild_invoices_for_admin_upload(cursor):
    cursor.execute("PRAGMA foreign_keys=OFF")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invoices_admin_upload_migration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number VARCHAR(50) NOT NULL UNIQUE,
            sales_order_id INTEGER,
            invoice_type VARCHAR(20) NOT NULL,
            invoice_date DATE NOT NULL,
            summary TEXT,
            payment_type VARCHAR(20),
            cr_number VARCHAR(50),
            payment_amount FLOAT DEFAULT 0.0,
            tax_amount_paid FLOAT DEFAULT 0.0,
            is_2307_checked BOOLEAN DEFAULT 0,
            total_amount FLOAT,
            amount_paid FLOAT DEFAULT 0.0,
            balance FLOAT,
            status VARCHAR(20) DEFAULT 'UNPAID',
            uploaded_client_name VARCHAR(200),
            upload_source VARCHAR(50),
            admin_upload_note TEXT,
            created_at DATETIME,
            FOREIGN KEY(sales_order_id) REFERENCES sales_orders(id)
        )
    """)
    cursor.execute("PRAGMA table_info(invoices)")
    existing_columns = [column[1] for column in cursor.fetchall()]
    target_columns = [
        'id', 'invoice_number', 'sales_order_id', 'invoice_type', 'invoice_date',
        'summary', 'payment_type', 'cr_number', 'payment_amount', 'tax_amount_paid',
        'is_2307_checked', 'total_amount', 'amount_paid', 'balance', 'status',
        'uploaded_client_name', 'upload_source', 'admin_upload_note', 'created_at'
    ]
    select_columns = [
        column if column in existing_columns else 'NULL'
        for column in target_columns
    ]
    cursor.execute(f"""
        INSERT INTO invoices_admin_upload_migration ({', '.join(target_columns)})
        SELECT {', '.join(select_columns)} FROM invoices
    """)
    cursor.execute("DROP TABLE invoices")
    cursor.execute("ALTER TABLE invoices_admin_upload_migration RENAME TO invoices")
    cursor.execute("PRAGMA foreign_keys=ON")

DEFAULT_EVALUATION_QUESTIONS = [
    ("Functionality", "The system provides the analytics functions needed to monitor POS and hardware sales performance."),
    ("Functionality", "The upload and validation workflow supports accurate sales data entry."),
    ("Usability", "The dashboard is easy to navigate and understand."),
    ("Usability", "The analytics controls and filters are clear for regular users."),
    ("Analytics Accuracy", "The displayed metrics and forecasts are useful for understanding sales performance."),
    ("Analytics Accuracy", "The Client Performance Score fairly represents client value and payment behavior."),
    ("Dashboard Readability", "Charts and tables are readable and help compare sales performance."),
    ("Decision Support", "The recommendations help users decide what action to take next."),
    ("Performance", "The dashboard loads and responds within an acceptable time."),
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
    if EvaluationQuestion.query.first():
        return
    for order, (category, text) in enumerate(DEFAULT_EVALUATION_QUESTIONS, start=1):
        db.session.add(EvaluationQuestion(category=category, question_text=text, display_order=order, is_active=True))
    db.session.commit()

def init_db():
    with app.app_context():
        db_path = get_configured_sqlite_path()
        if db_path:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db.create_all()
        ensure_schema_updates()
        
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
                        status='ACTIVE'
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.status == 'ACTIVE' and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role.role_name
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
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid login credentials. Please check your details and try again.', 'error')
    
    return render_template('login.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user and user.status == 'ACTIVE':
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
            flash('Username already exists', 'error')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return render_template('register.html')

        staff_role = Role.query.filter_by(role_name='staff').first()
        if not staff_role:
            flash('Staff role is not configured', 'error')
            return render_template('register.html')
        
        user = User(
            email=email,
            username=username,
            password_hash=generate_password_hash(password),
            role_id=staff_role.id
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(AuditLog(
            user_id=user.id,
            username=user.username,
            action='REGISTER',
            table_name='users',
            record_id=str(user.id),
            new_value=str({'username': user.username, 'email': user.email, 'role': 'staff'})
        ))
        db.session.commit()
        
        flash('Account created successfully!', 'success')
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
            if extension not in {'.png', '.jpg', '.jpeg', '.webp'}:
                flash('Profile photo must be PNG, JPG, JPEG, or WEBP.', 'error')
                return render_template('profile.html', user=user)
            upload_dir = os.path.join(app.static_folder, 'uploads', 'profiles')
            os.makedirs(upload_dir, exist_ok=True)
            filename = f'user-{user.id}-{int(datetime.now().timestamp())}{extension}'
            photo.save(os.path.join(upload_dir, filename))
            user.profile_photo = f'uploads/profiles/{filename}'

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
    flash('You have been logged out', 'info')
    return redirect(url_for('login'))

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
        db.session.query(func.strftime('%Y', SalesOrder.order_date).label('year'))
        .filter(SalesOrder.order_date.isnot(None))
        .union(
            db.session.query(func.strftime('%Y', Invoice.invoice_date).label('year'))
            .filter(Invoice.invoice_date.isnot(None)),
            db.session.query(func.strftime('%Y', PurchaseOrder.date).label('year'))
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
            func.coalesce(func.sum(Invoice.amount_paid), 0).label('total_revenue'),
            func.coalesce(
                func.sum(
                    case(
                        (Invoice.is_2307_checked.is_(True), Invoice.tax_amount_paid),
                        else_=0
                    )
                ),
                0
            ).label('total_tax_collected'),
            func.count(Invoice.id).label('payment_count')
        )
        .filter(
            Invoice.amount_paid > 0,
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start
        )
        .one()
    )

    total_revenue = float(revenue_totals.total_revenue or 0)
    total_tax_collected = float(revenue_totals.total_tax_collected or 0)
    payment_count = int(revenue_totals.payment_count or 0)

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

    # Recent sales orders
    item_count_sq = (
        db.session.query(
            SalesOrderItem.sales_order_id.label('sales_order_id'),
            db.func.count(SalesOrderItem.id).label('item_count'),
            db.func.coalesce(
                db.func.sum(SalesOrderItem.quantity * SalesOrderItem.selling_price),
                0
            ).label('item_total')
        )
        .group_by(SalesOrderItem.sales_order_id)
        .subquery()
    )

    recent_sales_orders = (
        db.session.query(
            SalesOrder.id,
            SalesOrder.so_number,
            SalesOrder.order_date,
            db.func.coalesce(item_count_sq.c.item_total, 0).label('total_amount'),
            SalesOrder.status,
            Client.client_name,
            db.func.coalesce(item_count_sq.c.item_count, 0).label('item_count')
        )
        .join(Client, SalesOrder.client_id == Client.id)
        .outerjoin(item_count_sq, SalesOrder.id == item_count_sq.c.sales_order_id)
        .filter(
            SalesOrder.order_date >= year_start,
            SalesOrder.order_date < next_year_start
        )
        .order_by(SalesOrder.created_at.desc())
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

    orders_by_client = defaultdict(list)
    for order in all_orders:
        orders_by_client[order.client_id].append(order)

    invoice_counts_by_client = defaultdict(int)
    admin_paid_by_client = defaultdict(float)
    client_registry = build_client_registry()
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
            invoice_counts_by_client[invoice.sales_order.client_id] += 1
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
            client_id = registry_entry['client_id']
            invoice_counts_by_client[client_id] += 1
            admin_paid_by_client[client_id] += nz(invoice.amount_paid)

    client_summaries = []
    analysis_clients = get_clients_analysis(db, app_models(), year_start, next_year_start).get('clients', [])

    analysis_by_name = {
        normalize_client_match_key(item.get('company_name')): item
        for item in analysis_clients
    }
    for client in Client.query.order_by(Client.client_name.asc()).all():
        client_orders = orders_by_client.get(client.id, [])
        unpaid_sales_orders = []
        client_revenue = 0.0
        client_paid = 0.0

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

        client_paid += admin_paid_by_client.get(client.id, 0)

        analysis_client = analysis_by_name.get(normalize_client_match_key(client.client_name), {})
        client_revenue = float(analysis_client.get('total_revenue', client_revenue) or 0)
        client_paid = float(client_paid or 0)
        current_balance = max(client_revenue - client_paid, 0)
        client_summaries.append({
            'id': client.id,
            'client_name': client.client_name,
            'contact_info': client.contact_info,
            'total_invoices': invoice_counts_by_client.get(client.id, 0),
            'current_balance': current_balance,
            'total_revenue': client_revenue,
            'total_paid': client_paid,
            'balance_status': analysis_client.get('balance_status') or ('Settled' if current_balance <= 0.01 else 'Unsettled Balance'),
            'client_performance_score': analysis_client.get('client_performance_score', 0),
            'cohort': analysis_client.get('cohort') or analysis_client.get('value_status') or 'Low Engagement',
            'last_purchase': analysis_client.get('last_purchase'),
            'unpaid_sales_order_count': len(unpaid_sales_orders),
            'unpaid_sales_orders': unpaid_sales_orders
        })

    accounts_receivable_total = sum(
        float(client['current_balance'] or 0)
        for client in client_summaries
    )
    accounts_receivable_count = sum(
        1 for client in client_summaries
        if float(client['current_balance'] or 0) > 0.01
    )

    # Analytics data
    selected_year_revenue = total_revenue

    aging_0_30 = (
        db.session.query(db.func.coalesce(db.func.sum(Invoice.balance), 0))
        .filter(
            Invoice.status != 'PAID',
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
            extract('month', Invoice.invoice_date).label('month'),
            func.coalesce(func.sum(Invoice.payment_amount), 0).label('total')
        )
        .filter(
            Invoice.invoice_date >= year_start,
            Invoice.invoice_date < next_year_start
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

        monthly_query = (
            db.session.query(
                func.strftime('%Y-%m', SalesOrder.order_date).label('year_month'),
                func.sum(SalesOrderItem.total).label('monthly_total')
            )
            .join(SalesOrderItem, SalesOrder.id == SalesOrderItem.sales_order_id)
            .filter(
                SalesOrder.order_date.isnot(None),
                SalesOrder.order_date >= filters['start_date'],
                SalesOrder.order_date < filters['end_date']
            )
            .group_by('year_month')
            .order_by(asc('year_month'))
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
        export_type = data.get('export_type') or 'PDF'
        log_audit('EXPORT_REPORT', 'reports', report_name, None, {'export_type': export_type})
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get-clients')
@login_required
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

@app.route('/admin/upload-preview/<interface>', methods=['POST'])
@login_required
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
            for row in df.fillna('').to_dict('records'):
                normalized = normalize_upload_row(interface, row)
                normalized['_source_file'] = upload.filename
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
                    (f'Row {index} Purchase Order date', row.get('date')),
                    (f'Row {index} OR date', row.get('or_date')),
                ])
        return jsonify({
            'success': True,
            'rows': rows,
            'outliers': zscore_outliers(rows, amount_key),
            'warnings': future_date_warnings(dict(warning_fields)),
            'documentation': [
                'Upload: select one or more CSV/Excel files for this interface.',
                'Cleaning: dates, amounts, names, and special characters are normalized into database fields.',
                'Outlier Identifier: Z-score flags amount values with absolute score >= 2.5.',
                'Excel Mapping: recognized headers are mapped into existing Syluxent model variables before saving.'
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/upload-commit/<interface>', methods=['POST'])
@login_required
def admin_upload_commit(interface):
    denied = admin_required_json()
    if denied:
        return denied
    payload = request.get_json() or {}
    rows = payload.get('rows', [])
    resolutions = parse_resolution_payload(payload)
    if not rows:
        return jsonify({'success': False, 'error': 'No rows to upload'}), 400
    try:
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
        if interface == 'invoice':
            grouped_rows = {}
            for row in rows:
                invoice_number = row.get('invoice_number')
                if not invoice_number:
                    grouped_rows[(None, id(row))] = row
                    continue
                if invoice_number not in grouped_rows:
                    grouped_rows[invoice_number] = row.copy()
                    continue
                grouped_rows[invoice_number]['amount_paid'] = float(grouped_rows[invoice_number].get('amount_paid') or 0) + float(row.get('amount_paid') or row.get('payment_amount') or 0)
                grouped_rows[invoice_number]['payment_amount'] = float(grouped_rows[invoice_number].get('payment_amount') or 0) + float(row.get('payment_amount') or row.get('amount_paid') or 0)
            rows = list(grouped_rows.values())

        created = 0
        updated = 0
        upload_warning_fields = []
        for index, row in enumerate(rows, start=1):
            if interface == 'sales_order':
                upload_warning_fields.append((f'Row {index} Sales Order date', row.get('order_date')))
            elif interface == 'invoice':
                upload_warning_fields.append((f'Row {index} Invoice date', row.get('invoice_date')))
            elif interface == 'purchase_order':
                upload_warning_fields.extend([
                    (f'Row {index} Check date', row.get('check_date')),
                    (f'Row {index} Purchase Order date', row.get('date')),
                    (f'Row {index} OR date', row.get('or_date')),
                ])
        warnings = future_date_warnings(dict(upload_warning_fields))
        for row in rows:
            if interface == 'sales_order':
                original_company_name = row.get('company_name') or row.get('client_name') or 'UNMAPPED CLIENT'
                resolution = resolve_client_name(
                    original_company_name,
                    resolutions,
                    create_client=True
                )
                if resolution['status'] == 'ignored':
                    continue
                client = resolution['client']
                client_name = resolution['client_name']
                so_number = row.get('so_number') or f"SO-{SalesOrder.query.count() + created + 1:06d}"
                store_name = clean_text(row.get('store_name', '')) or clean_text(original_company_name, keep_period=True, keep_ampersand=True)
                order = SalesOrder(
                    so_number=so_number,
                    client_id=client.id,
                    company_name=client_name,
                    official_client_name=client_name,
                    original_entered_client_name=resolution.get('original_entered_client_name') or clean_text(original_company_name, keep_period=True, keep_ampersand=True).upper(),
                    store_name=store_name.upper(),
                    store_branch=(clean_text(row.get('store_branch', '')) or DEFAULT_STORE_BRANCH).upper(),
                    order_date=parse_date_value(row.get('order_date')),
                    sales_staff=row.get('sales_staff') or session.get('username', ''),
                    terms=int(row.get('terms') or 30),
                    total_amount=float(row.get('total_amount') or 0),
                    status='PENDING'
                )
                db.session.add(order)
                db.session.flush()
                qty = float(row.get('quantity') or 1)
                price = float(row.get('selling_price') or row.get('total_amount') or 0)
                db.session.add(SalesOrderItem(
                    sales_order_id=order.id,
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
            elif interface == 'invoice':
                sales_order = SalesOrder.query.filter_by(so_number=row.get('so_number')).first()
                total = float(row.get('total_amount') or 0) if row.get('total_amount') not in (None, '') else (float(sales_order.total_amount or 0) if sales_order else None)
                paid = float(row.get('amount_paid') or row.get('payment_amount') or 0)
                uploaded_client_name = clean_text(row.get('uploaded_client_name'), keep_period=True, keep_ampersand=True).upper()
                if not sales_order and not uploaded_client_name:
                    continue
                is_admin_upload = sales_order is None
                existing_invoice = Invoice.query.filter_by(invoice_number=row.get('invoice_number')).first() if row.get('invoice_number') else None
                if existing_invoice:
                    existing_invoice.payment_amount = float(existing_invoice.payment_amount or 0) + float(row.get('payment_amount') or paid)
                    existing_invoice.amount_paid = float(existing_invoice.amount_paid or 0) + paid
                    if existing_invoice.total_amount is not None:
                        existing_invoice.balance = max((existing_invoice.total_amount or 0) - (existing_invoice.amount_paid or 0), 0)
                    if existing_invoice.sales_order_id is None:
                        existing_invoice.status = 'Admin Upload'
                        existing_invoice.uploaded_client_name = existing_invoice.uploaded_client_name or uploaded_client_name or None
                        existing_invoice.upload_source = existing_invoice.upload_source or 'admin_upload'
                        existing_invoice.admin_upload_note = existing_invoice.admin_upload_note or 'Admin Upload'
                    elif existing_invoice.total_amount is not None and existing_invoice.amount_paid >= existing_invoice.total_amount and existing_invoice.total_amount > 0:
                        existing_invoice.status = 'PAID'
                    updated += 1
                    continue
                db.session.add(Invoice(
                    invoice_number=row.get('invoice_number') or f"INV-{Invoice.query.count() + created + 1:06d}",
                    sales_order_id=sales_order.id if sales_order else None,
                    invoice_type='ADMIN UPLOAD' if is_admin_upload else (row.get('invoice_type') or 'SALES'),
                    invoice_date=parse_date_value(row.get('invoice_date')),
                    summary=row.get('summary') or ('Admin Upload' if is_admin_upload else None),
                    payment_type='Admin Upload' if is_admin_upload else row.get('payment_type'),
                    cr_number=row.get('cr_number'),
                    payment_amount=float(row.get('payment_amount') or paid),
                    tax_amount_paid=float(row.get('tax_amount_paid') or 0),
                    total_amount=total,
                    amount_paid=paid,
                    balance=None if is_admin_upload and row.get('balance') in (None, '') else float(row.get('balance') if row.get('balance') not in (None, '') else max((total or 0) - paid, 0)),
                    status='Admin Upload' if is_admin_upload else (row.get('status') or ('PAID' if total is not None and paid >= total and total > 0 else 'UNPAID')),
                    uploaded_client_name=uploaded_client_name or None,
                    upload_source='admin_upload' if is_admin_upload else None,
                    admin_upload_note='Admin Upload' if is_admin_upload else None
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
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/auto-identify-fields', methods=['POST'])
@login_required
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
def create_sales_order():
    try:
        data = request.get_json()
        warnings = future_date_warnings({'Sales Order date': data.get('order_date')})

        company_name = (data.get('company_name') or data.get('client_name') or '').strip()
        client_id = data.get('client_id')
        resolutions = parse_resolution_payload(data)

        # Create or get client. The client basket is derived from sales order
        # items, so every order must be attached to the saved client id.
        client = None
        if client_id:
            client = db.session.get(Client, client_id)
        if not client:
            if not company_name:
                return jsonify({'success': False, 'error': 'Company name is required'})
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
        
        # Create sales order
        store_name = clean_text(data.get('store_name', '')) or clean_text(company_name or client_name, keep_period=True, keep_ampersand=True)
        sales_order = SalesOrder(
            so_number=so_number,
            order_date=datetime.strptime(data['order_date'], '%Y-%m-%d').date(),
            client_id=client.id,
            company_name=client_name,
            official_client_name=client_name,
            original_entered_client_name=original_company_name,
            store_name=store_name.upper(),
            store_branch=(clean_text(data.get('store_branch', '')) or DEFAULT_STORE_BRANCH).upper(),
            sales_staff=data.get('sales_staff') or session.get('username', ''),
            total_amount=float(data.get('total_amount') or 0),
            terms=int(data.get('terms_days') or data.get('terms') or 30),
            notes=data.get('notes', ''),
            status='PENDING'
        )
        
        db.session.add(sales_order)
        db.session.flush()
        
        # Add items
        for item in data['items']:
            quantity = float(item.get('quantity') or item.get('qty') or 0)
            unit_cost = float(item.get('unit_cost') or item.get('cost') or 0)
            selling_price = float(item.get('selling_price') or item.get('item_price') or item.get('price') or 0)
            total = float(item.get('total') or (selling_price * quantity))
            order_item = SalesOrderItem(
                sales_order_id=sales_order.id,
                particular=item['particular'],
                quantity=quantity,
                unit_cost=unit_cost,
                selling_price=selling_price,
                total=total
            )
            db.session.add(order_item)
        
        refresh_client_financials(client)
        log_audit('CREATE', 'sales_orders', sales_order.id, None, {'so_number': sales_order.so_number, 'total_amount': sales_order.total_amount})
        db.session.commit()
        
        return json_success({'message': 'Sales order created successfully'}, warnings)
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/invoices')
@login_required
def invoices():
    return render_template('invoices.html')


@app.route('/get-invoices')
@login_required
def get_invoices():
    try:
        invoices_list = db.session.query(
            Invoice.id, Invoice.invoice_number, Invoice.sales_order_id, SalesOrder.so_number,
            Invoice.invoice_type, Invoice.invoice_date, Invoice.total_amount,
            Invoice.payment_type, Invoice.cr_number, Invoice.payment_amount,
            Invoice.tax_amount_paid, Invoice.is_2307_checked,
            Invoice.amount_paid, Invoice.balance, Invoice.status, Client.client_name,
            Invoice.uploaded_client_name, Invoice.upload_source, Invoice.admin_upload_note
        ).select_from(Invoice).join(
            SalesOrder, Invoice.sales_order_id == SalesOrder.id, isouter=True
        ).join(
            Client, SalesOrder.client_id == Client.id
            , isouter=True
        ).order_by(Invoice.created_at.desc()).all()
        
        invoice_count = len(invoices_list)
        
        return jsonify({
            'success': True,
            'count': invoice_count,
            'invoices': [
                {
                    'id': inv.id,
                    'invoice_number': inv.invoice_number,
                    'sales_order_id': inv.sales_order_id,
                    'so_number': inv.so_number,
                    'invoice_type': inv.invoice_type,
                    'client_name': inv.client_name or inv.uploaded_client_name or 'Admin Upload',
                    'invoice_date': inv.invoice_date.isoformat() if inv.invoice_date else None,
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
                    'admin_upload_note': inv.admin_upload_note
                } for inv in invoices_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-pending-sales-orders')
@login_required
def get_pending_sales_orders():
    try:
        pending_orders = db.session.query(
            SalesOrder.id, SalesOrder.so_number, SalesOrder.order_date,
            SalesOrder.total_amount, SalesOrder.status, Client.client_name
        ).join(Client).filter(SalesOrder.status.in_(['PENDING', 'PARTIAL'])).all()
        
        return jsonify({
            'success': True,
            'sales_orders': [
                {
                    'id': so.id,
                    'so_number': so.so_number,
                    'client_name': so.client_name,
                    'order_date': so.order_date.isoformat() if so.order_date else None,
                    'total_amount': so.total_amount,
                    'status': so.status
                } for so in pending_orders
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get-sales-order-details/<int:so_id>')
@login_required
def get_sales_order_details(so_id):
    try:
        sales_order = db.session.query(
            SalesOrder.id, SalesOrder.so_number, SalesOrder.order_date,
            SalesOrder.total_amount, SalesOrder.status, Client.client_name
        ).join(Client).filter(SalesOrder.id == so_id).first()
        
        if not sales_order:
            return jsonify({'success': False, 'error': 'Sales order not found'})
        
        return jsonify({
            'success': True,
            'sales_order': {
                'id': sales_order.id,
                'so_number': sales_order.so_number,
                'client_name': sales_order.client_name,
                'order_date': sales_order.order_date.isoformat() if sales_order.order_date else None,
                'total_amount': sales_order.total_amount,
                'status': sales_order.status
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/generate-invoice-number')
@login_required
def generate_invoice_number():
    try:
        invoice_type = request.args.get('type', 'SALES')
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
def create_invoice():
    try:
        data = request.get_json()
        warnings = future_date_warnings({'Invoice date': data.get('invoice_date')})
        
        # Get sales order
        sales_order = db.session.get(SalesOrder, data['sales_order_id'])
        if not sales_order:
            return jsonify({'success': False, 'error': 'Sales order not found'})

        cr_number = (data.get('cr_number') or '').strip()
        payment_amount = float(data.get('payment_amount') or 0)
        tax_amount_paid = float(data.get('tax_amount_paid') or 0)
        is_2307_checked = bool(data.get('is_2307_checked'))
        total_amount = float(data.get('total_amount') or sales_order.total_amount or 0)
        total_paid_now = payment_amount + (tax_amount_paid if is_2307_checked else 0) if cr_number else 0
        previous_paid = sum(inv.amount_paid or 0 for inv in sales_order.invoices)
        cumulative_paid = previous_paid + total_paid_now
        balance = max(total_amount - cumulative_paid, 0)
        invoice_status = 'PAID' if cr_number else 'UNPAID'
        
        # Create invoice
        invoice = Invoice(
            invoice_number=data['invoice_number'],
            sales_order_id=data['sales_order_id'],
            invoice_type=data['invoice_type'],
            invoice_date=datetime.strptime(data['invoice_date'], '%Y-%m-%d').date(),
            summary=data.get('summary', ''),
            payment_type=data.get('payment_type', ''),
            cr_number=cr_number,
            payment_amount=payment_amount,
            tax_amount_paid=tax_amount_paid,
            is_2307_checked=is_2307_checked,
            total_amount=total_amount,
            amount_paid=total_paid_now,
            balance=balance,
            status=invoice_status
        )
        
        db.session.add(invoice)
        db.session.flush()
        
        # Update sales order status from cumulative invoice payments.
        if balance <= 0.01:
            sales_order.status = 'COMPLETED'
        elif cumulative_paid > 0:
            sales_order.status = 'PARTIAL'
        else:
            sales_order.status = 'PENDING'
        
        refresh_client_financials(sales_order.client)
        log_audit('CREATE', 'invoices', invoice.id, None, {'invoice_number': invoice.invoice_number, 'total_amount': invoice.total_amount})
        db.session.commit()
        
        return json_success({'message': 'Invoice created successfully'}, warnings)
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/update-invoice-payment/<int:invoice_id>', methods=['POST'])
@login_required
def update_invoice_payment(invoice_id):
    try:
        data = request.get_json()
        invoice = db.session.get(Invoice, invoice_id)
        if not invoice:
            return jsonify({'success': False, 'error': 'Invoice not found'})

        invoice.payment_type = data.get('payment_type', invoice.payment_type) or ''
        invoice.cr_number = (data.get('cr_number') or '').strip()
        invoice.payment_amount = float(data.get('payment_amount') or 0)
        invoice.tax_amount_paid = float(data.get('tax_amount_paid') or 0)
        invoice.is_2307_checked = bool(data.get('is_2307_checked'))

        invoice.amount_paid = (
            invoice.payment_amount + (invoice.tax_amount_paid if invoice.is_2307_checked else 0)
            if invoice.cr_number else 0
        )
        invoice.balance = max((invoice.total_amount or 0) - (invoice.amount_paid or 0), 0) if invoice.total_amount is not None else None
        invoice.status = 'Admin Upload' if invoice.sales_order_id is None else ('PAID' if invoice.cr_number else 'UNPAID')

        sales_order = invoice.sales_order
        if sales_order:
            total_paid = sum(inv.amount_paid or 0 for inv in sales_order.invoices)
            sales_order_balance = max((sales_order.total_amount or 0) - total_paid, 0)
            if sales_order_balance <= 0.01:
                sales_order.status = 'COMPLETED'
            elif total_paid > 0:
                sales_order.status = 'PARTIAL'
            else:
                sales_order.status = 'PENDING'

        refresh_client_financials(sales_order.client if sales_order else None)
        log_audit('UPDATE_PAYMENT', 'invoices', invoice.id, None, {'invoice_number': invoice.invoice_number, 'amount_paid': invoice.amount_paid, 'balance': invoice.balance})
        db.session.commit()
        return jsonify({'success': True, 'message': 'Invoice payment updated successfully'})

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/purchase-orders')
@login_required
def purchase_orders():
    return render_template('purchase_orders.html')

@app.route('/get-purchase-orders')
@login_required
def get_purchase_orders():
    try:
        purchase_orders_list = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
        
        return jsonify({
            'success': True,
            'purchase_orders': [
                {
                    'check_voucher_number': po.check_voucher_number,
                    'check_number': po.check_number,
                    'supplier_payee': po.supplier_payee,
                    'date': po.date.isoformat() if po.date else None,
                    'particulars': po.particulars,
                    'cash_amount': po.cash_amount,
                    'net_balance': po.net_balance,
                    'status': po.status or 'PENDING',
                    'category': po.category or 'VARIABLE'
                } for po in purchase_orders_list
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/create-purchase-order', methods=['POST'])
@login_required
def create_purchase_order():
    try:
        data = request.get_json()
        warnings = future_date_warnings({
            'Check date': data.get('check_date'),
            'Purchase Order date': data.get('date'),
            'OR date': data.get('or_date'),
        })
        
        # Create purchase order
        category = data.get('category')
        if not category:
            category = 'FIXED' if any(
                debit.get('debit_type') in ['PLDT', 'Globe/Smart, Sun', 'Meralco', 'Rent Expense']
                for debit in data.get('debits', [])
            ) else 'VARIABLE'

        purchase_order = PurchaseOrder(
            check_voucher_number=data['check_voucher_number'],
            check_number=data['check_number'],
            check_date=datetime.strptime(data['check_date'], '%Y-%m-%d').date(),
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            or_date=datetime.strptime(data['or_date'], '%Y-%m-%d').date() if data.get('or_date') else None,
            ar_cr_or_number=data.get('ar_cr_or_number', ''),
            po_number=data.get('po_number', ''),
            lf_no=data.get('lf_no', ''),
            particulars=data['particulars'],
            supplier_payee=data['supplier_payee'],
            tin_number=data.get('tin_number', ''),
            cash_amount=data['cash_amount'],
            net_balance=data['net_balance'],
            category=category,
            status='PENDING'
        )
        
        db.session.add(purchase_order)
        db.session.flush()
        
        # Add debit items
        for debit_data in data['debits']:
            debit_item = PurchaseOrderDebit(
                purchase_order_id=purchase_order.id,
                debit_type=debit_data['debit_type'],
                amount=debit_data['amount']
            )
            db.session.add(debit_item)
        
        log_audit('CREATE', 'purchase_orders', purchase_order.id, None, {'check_voucher_number': purchase_order.check_voucher_number, 'cash_amount': purchase_order.cash_amount})
        db.session.commit()
        
        return json_success({'message': 'Purchase order created successfully'}, warnings)
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/database-interface')
@login_required
@role_required('admin')
def database_interface():
    return render_template('admin.html')

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
            User.status, User.profile_photo, Role.role_name
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
                    'quantity': item.quantity,
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
        sales_orders_list = db.session.query(
            SalesOrder.id, SalesOrder.so_number, SalesOrder.order_date,
            SalesOrder.total_amount, SalesOrder.status, Client.client_name,
            SalesOrder.created_at
        ).join(Client).order_by(SalesOrder.created_at.desc()).limit(50).all()
        
        return jsonify({
            'success': True,
            'sales_orders': [
                {
                    'id': so.id,
                    'so_number': so.so_number,
                    'client_name': so.client_name,
                    'order_date': so.order_date.isoformat() if so.order_date else None,
                    'total_amount': so.total_amount,
                    'status': so.status,
                    'created_at': so.created_at.isoformat() if so.created_at else None
                } for so in sales_orders_list
            ]
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
                    'invoice_number': inv.invoice_number,
                    'invoice_type': inv.invoice_type,
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
        purchase_orders_list = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).limit(50).all()
        return jsonify({
            'success': True,
            'purchase_orders': [
                {
                    'id': po.id,
                    'check_voucher_number': po.check_voucher_number,
                    'supplier_payee': po.supplier_payee,
                    'date': po.date.isoformat() if po.date else None,
                    'cash_amount': po.cash_amount,
                    'status': po.status or 'PENDING',
                    'created_at': po.created_at.isoformat() if po.created_at else None
                } for po in purchase_orders_list
            ]
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
            status='ACTIVE'
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
        data = request.get_json()
        
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
        requested_role_id = int(data.get('role_id') or user.role_id)
        user_is_admin = user.role and user.role.role_name.lower() == 'admin'
        requested_admin = is_admin_role_id(requested_role_id)
        if requested_admin and not user_is_admin:
            return jsonify({'success': False, 'error': 'Only one admin account is allowed'}), 409
        if user_is_admin and not requested_admin:
            return jsonify({'success': False, 'error': 'The only admin account cannot be demoted'}), 409

        old_value = serialize_record(user)
        user.username = username
        user.email = email
        user.role_id = requested_role_id
        requested_status = (data.get('status') or user.status or 'ACTIVE').upper()
        if user_is_admin and requested_status != 'ACTIVE':
            return jsonify({'success': False, 'error': 'The only admin account cannot be deactivated'}), 409
        user.status = requested_status if requested_status in {'ACTIVE', 'INACTIVE'} else user.status
        
        if data.get('password'):
            user.password_hash = generate_password_hash(data['password'])
        
        log_audit('UPDATE', 'users', user.id, old_value, serialize_record(user))
        db.session.commit()
        if user.id == session['user_id']:
            session['username'] = user.username
        
        return jsonify({'success': True, 'message': 'User updated successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/delete-user/<int:user_id>', methods=['DELETE'])
@login_required
@role_required('admin')
def delete_user(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        if user.id == session['user_id'] or (user.role and user.role.role_name.lower() == 'admin'):
            return jsonify({'success': False, 'error': 'The current or admin account cannot be deactivated'}), 409
        
        old_value = serialize_record(user)
        user.status = 'INACTIVE'
        SessionRecord.query.filter_by(user_id=user.id, status='ACTIVE').update({
            'status': 'FORCED_LOGOUT',
            'logout_at': datetime.now(UTC)
        })
        log_audit('DEACTIVATE', 'users', user_id, old_value, serialize_record(user))
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'User marked inactive successfully'})
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


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
        result = run_safe_sql(db, data.get('sql', ''), bool(data.get('dry_run', True)))
        log_audit('SQL_DRY_RUN' if result['dry_run'] else 'SQL_EXECUTE', 'database', None, None, {'sql': data.get('sql', '')})
        db.session.commit()
        return jsonify({'success': True, 'result': result})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

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
            status = (data.get('status') or '').upper()
            if status not in {'ACTIVE', 'INACTIVE'}:
                return jsonify({'success': False, 'error': 'Users only support ACTIVE or INACTIVE status'}), 400
            selected_users = User.query.filter(User.id.in_(data.get('ids', []))).all()
            if status == 'INACTIVE' and any(
                user.id == session['user_id']
                or (user.role and user.role.role_name.lower() == 'admin')
                for user in selected_users
            ):
                return jsonify({'success': False, 'error': 'The current or admin account cannot be deactivated'}), 409
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
    requests = PasswordReset.query.order_by(
        case((PasswordReset.status == 'PENDING', 0), else_=1),
        PasswordReset.requested_at.desc()
    ).limit(100).all()
    return jsonify({
        'success': True,
        'pending_count': PasswordReset.query.filter_by(status='PENDING').count(),
        'notifications': [
            {
                'id': item.id,
                'username': item.username,
                'status': item.status,
                'requested_at': item.requested_at.isoformat() if item.requested_at else None,
                'resolved_at': item.resolved_at.isoformat() if item.resolved_at else None,
                'resolved_by': item.resolved_by.username if item.resolved_by else None,
            }
            for item in requests
        ]
    })

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
    if not user or user.status != 'ACTIVE':
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
        selected_year = filters['selected_year']
        period = filters['period']

        # Get available unique years for filter dropdown
        years_query = db.session.query(func.strftime('%Y', AnalyticsData.transaction_date)).distinct().all()
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

        # 2. GROUP BY MONTH & SORT CHRONOLOGICALLY
        monthly_query = db.session.query(
            func.strftime('%m', AnalyticsData.transaction_date).label('month_num'),
            func.min(AnalyticsData.transaction_date).label('first_day_of_month'),
            func.sum(AnalyticsData.amount).label('monthly_revenue')
        ).filter(
            AnalyticsData.transaction_date >= filters['start_date'],
            AnalyticsData.transaction_date < filters['end_date'],
            AnalyticsData.flow_direction == 'INFLOW',
            AnalyticsData.flow_status == 'ACTUAL'
        ).group_by(
            func.strftime('%m', AnalyticsData.transaction_date)
        ).order_by(
            asc(func.strftime('%m', AnalyticsData.transaction_date)) 
        ).all()

        # 3. Format labels consistently as DD/MM/YYYY.
        labels = []
        values = []
        
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
                "period": period
            },
            "trend_data": {
                "labels": labels,
                "values": values   
            }
        })
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

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
        "quantity": [float(record.get("qty") or 0) for record in validated_records],
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
        missing_fields = [field for field in required_fields if field not in header_map]
        if missing_fields:
            eda_summary = {
                'rows_read': len(rows),
                'rows_ready': 0,
                'missing_columns': missing_fields,
                'required_columns': required_fields,
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
        return jsonify({"success": False, "error": str(e)}), 500

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
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/analytics/expenses')
@login_required
@role_required('manager', 'admin')
def api_analytics_expenses():
    """Get expenses breakdown data."""
    try:
        expenses = get_expenses_breakdown(db, PurchaseOrder)
        return jsonify({
            'success': True,
            'fixed_expenses': expenses['fixed_expenses'],
            'variable_expenses': expenses['variable_expenses'],
            'total_expenses': expenses['total_expenses'],
            'fixed_items': expenses['fixed_items'],
            'variable_items': expenses['variable_items'],
            'pie_data': expenses['pie_data']
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

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
        return jsonify({'success': False, 'error': str(e)}), 400

def likert_interpretation(mean_score):
    if mean_score >= 4.20:
        return 'Excellent'
    if mean_score >= 3.40:
        return 'Very Good'
    if mean_score >= 2.60:
        return 'Good'
    if mean_score >= 1.80:
        return 'Fair'
    return 'Needs Improvement'

@app.route('/api/evaluation/questions')
@login_required
@role_required('manager', 'admin')
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
@role_required('manager', 'admin')
def evaluation_responses():
    payload = request.get_json() or {}
    responses = payload.get('responses') or []
    if not responses:
        return jsonify({'success': False, 'error': 'At least one Likert response is required.'}), 400
    ratings = []
    session_record = EvaluationSession(
        evaluator_name=clean_text(payload.get('evaluator_name')) or session.get('username', 'Evaluator'),
        evaluator_role=clean_text(payload.get('evaluator_role')) or session.get('role', ''),
        overall_comment=clean_text(payload.get('overall_comment'), keep_period=True, keep_ampersand=True),
    )
    db.session.add(session_record)
    db.session.flush()
    valid_question_ids = {question.id for question in EvaluationQuestion.query.filter_by(is_active=True).all()}
    for item in responses:
        question_id = int(item.get('question_id') or 0)
        rating = int(item.get('rating') or 0)
        if question_id not in valid_question_ids or rating < 1 or rating > 5:
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Invalid question or rating detected.'}), 400
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
@role_required('manager', 'admin')
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
        
        comparison = get_comparative_analysis(db, Invoice, year1, year2)
        return jsonify({
            'success': True,
            'comparison': comparison
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/get-analytics')
@login_required
@role_required('manager', 'admin')
def get_analytics():
    try:
        analytics_data = build_analytics_payload(db, app_models())
        return jsonify({'success': True, 'analytics': analytics_data})
    
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/analytics/excel-preview', methods=['POST'])
@login_required
@role_required('manager', 'admin')
def analytics_excel_preview():
    try:
        upload = request.files.get('excel_file')
        if not upload:
            return jsonify({'success': False, 'error': 'Excel file is required'})
        return jsonify({'success': True, 'workbook': preview_excel_workbook(upload)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/dev/viewer')
@login_required
@role_required('manager', 'admin')  # Keeping same permissions as your analytics route
def dev_json_viewer():
    """Render the generic HTML page to inspect and test returned JSON data."""
    return render_template('json.html')

init_db()

if __name__ == '__main__':
    app.run(
        debug=True,
        host=os.environ.get('FLASK_RUN_HOST', '0.0.0.0'),
        port=int(os.environ.get('FLASK_RUN_PORT', 5000))
    )

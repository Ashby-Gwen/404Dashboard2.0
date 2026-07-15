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
    Role,
    SalesOrder,
    SalesOrderItem,
    User,
    app,
    canonical_invoice_type,
    db,
    init_db,
    normalize_upload_row,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        admin_role = Role.query.filter_by(role_name='admin').first()
        admin = User(
            username='invoice_quantity_admin',
            password_hash=generate_password_hash('admin123'),
            role_id=admin_role.id,
            status='approved',
        )
        customer = Client(client_name='INVOICE QUANTITY CLIENT')
        db.session.add_all([admin, customer])
        db.session.flush()
        order = SalesOrder(
            so_number='SO-IQ-001',
            client_id=customer.id,
            company_name=customer.client_name,
            store_name='INVOICE QUANTITY STORE',
            store_branch='MAIN',
            order_date=date(2026, 6, 19),
            total_amount=1000,
            status='PENDING',
        )
        db.session.add(order)
        db.session.flush()
        db.session.add(SalesOrderItem(
            sales_order_id=order.id,
            particular='WHOLE ITEM',
            quantity=2,
            unit_cost=100,
            selling_price=500,
            total=1000,
        ))
        db.session.add_all([
            Invoice(
                invoice_number='si-conflict-1',
                sales_order_id=order.id,
                invoice_type='SERVICE',
                invoice_date=date(2026, 6, 19),
                summary='Whole item service summary',
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='svi-conflict-1',
                sales_order_id=order.id,
                invoice_type='SALES',
                invoice_date=date(2026, 6, 19),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
            Invoice(
                invoice_number='legacy-1',
                sales_order_id=order.id,
                invoice_type='SERVICE',
                invoice_date=date(2026, 6, 19),
                total_amount=1000,
                amount_paid=0,
                balance=1000,
                status='UNPAID',
            ),
        ])
        db.session.commit()

        assert canonical_invoice_type(' svi-000001 ', 'SALES') == 'SERVICE'
        assert canonical_invoice_type('si-000001', 'SERVICE') == 'SALES'
        assert canonical_invoice_type('legacy-1', 'SERVICE') == 'SERVICE'

        try:
            normalize_upload_row('sales_order', {
                'Company Name': 'TEST',
                'Order Date': '2026-06-19',
                'Quantity': '1.5',
            })
            raise AssertionError('Fractional upload quantity was accepted.')
        except ValueError as error:
            assert 'whole number' in str(error)

        with app.test_client() as web:
            with web.session_transaction() as session:
                session['user_id'] = admin.id
                session['username'] = admin.username
                session['role'] = 'admin'

            created_invoice = web.post('/create-invoice', json={
                'sales_order_id': order.id,
                'invoice_number': 'svi-new-1',
                'invoice_type': 'SALES',
                'invoice_date': '2026-06-19',
                'payment_amount': 0,
                'tax_amount_paid': 0,
            })
            assert created_invoice.status_code == 200, created_invoice.get_json()
            saved_invoice = Invoice.query.filter_by(invoice_number='SVI-NEW-1').one()
            assert saved_invoice.invoice_type == 'SERVICE'

            sales_payload = web.get('/get-invoices?invoice_type=SALES').get_json()
            service_payload = web.get('/get-invoices?invoice_type=SERVICE').get_json()
            assert {row['invoice_number'] for row in sales_payload['invoices']} == {'SI-CONFLICT-1'}
            assert {row['invoice_number'] for row in service_payload['invoices']} == {
                'SVI-CONFLICT-1', 'SVI-NEW-1', 'LEGACY-1'
            }
            assert next(row for row in sales_payload['invoices'] if row['invoice_number'] == 'SI-CONFLICT-1')['summary'] == 'Whole item service summary'
            assert all(row['invoice_type'] == 'SALES' for row in sales_payload['invoices'])
            assert all(row['invoice_type'] == 'SERVICE' for row in service_payload['invoices'])

            fractional = web.post('/create-sales-order', json={
                'company_name': customer.client_name,
                'store_name': 'FRACTION STORE',
                'store_branch': 'MAIN',
                'order_date': '2026-06-19',
                'items': [{
                    'particular': 'FRACTIONAL ITEM',
                    'quantity': 1.5,
                    'unit_cost': 10,
                    'selling_price': 20,
                }],
            })
            assert fractional.status_code == 400
            assert 'whole number' in fractional.get_json()['error']

            fractional_commit = web.post('/admin/upload-commit/sales_order', json={
                'rows': [{
                    'company_name': customer.client_name,
                    'store_name': 'UPLOAD STORE',
                    'store_branch': 'MAIN',
                    'order_date': '2026-06-19',
                    'quantity': 2.5,
                    'selling_price': 20,
                    'total_amount': 50,
                }],
            })
            assert fractional_commit.status_code == 400
            assert 'whole number' in fractional_commit.get_json()['error']

            upload_commit = web.post('/admin/upload-commit/sales_order', json={
                'rows': [{
                    'so_number': '44',
                    'so_generation_year': 2025,
                    'company_name': customer.client_name,
                    'store_name': 'UPLOAD STORE',
                    'store_branch': 'MAIN',
                    'order_date': '2026-06-20',
                    'sales_staff': 'Upload Staff',
                    'particular': 'UPLOADED ITEM',
                    'quantity': 1,
                    'selling_price': 120,
                    'total_amount': 120,
                }],
            })
            assert upload_commit.status_code == 200, upload_commit.get_json()
            uploaded_order = SalesOrder.query.filter_by(source_so_number='SO-044').one()
            assert uploaded_order.so_number == 'SO-2025-0001'
            assert uploaded_order.so_number != uploaded_order.source_so_number
            assert uploaded_order.sales_staff == 'UPLOAD STAFF'

            duplicate_upload = web.post('/admin/upload-commit/sales_order', json={
                'rows': [{
                    'so_number': '44',
                    'so_generation_year': 2025,
                    'company_name': customer.client_name,
                    'store_name': 'UPLOAD STORE',
                    'store_branch': 'MAIN',
                    'order_date': '2026-06-20',
                    'sales_staff': 'Upload Staff',
                    'particular': 'UPLOADED ITEM',
                    'quantity': 1,
                    'selling_price': 120,
                    'total_amount': 120,
                }],
            })
            assert duplicate_upload.status_code == 409
            assert 'source SO Number, Sales Staff, and Order Date' in duplicate_upload.get_json()['error']

            print_response = web.get(f'/sales-orders/{order.id}/print')
            print_html = print_response.get_data(as_text=True)
            assert '>2</td>' in print_html
            assert '>2.00</td>' not in print_html

            legacy_print_audit = web.post('/api/reports/audit-export', json={
                'report': 'revenue',
                'export_type': 'PDF',
            })
            assert legacy_print_audit.status_code == 200
            print_audit = AuditLog.query.filter_by(
                action='EXPORT_REPORT',
                record_id='revenue',
            ).order_by(AuditLog.id.desc()).first()
            assert print_audit is not None
            assert "'export_type': 'PRINT'" in print_audit.new_value

        analytics_template = open(
            os.path.join(ROOT, 'templates', 'analytics.html'),
            encoding='utf-8'
        ).read()
        analytics_css = open(
            os.path.join(ROOT, 'static', 'css', 'analytics-layout.css'),
            encoding='utf-8'
        ).read()
        analytics_html = analytics_template + '\n' + analytics_css
        app_source = open(os.path.join(ROOT, 'app.py'), encoding='utf-8').read()
        requirements = open(os.path.join(ROOT, 'requirements.txt'), encoding='utf-8').read()
        assert "filename='css/analytics-layout.css'" in analytics_template
        assert '<style>' not in analytics_template
        assert '</style>' not in analytics_template
        assert '/* --- 1. Core Dashboard Layout & Shell --- */' in analytics_css
        assert '/* --- 2. Interactive & Morph Cards --- */' in analytics_css
        assert '/* --- 3. Data Tables & Scroll Containers --- */' in analytics_css
        assert '/* --- 4. Chart Aspect Ratios & Containers --- */' in analytics_css
        assert '/* --- 5. Print Preview & Print Output Media Queries --- */' in analytics_css
        assert 'WeasyPrint' not in requirements
        assert 'reportlab' not in requirements
        assert "@app.route('/api/analytics/export.pdf', methods=['POST'])" not in app_source
        assert 'def validate_analytics_pdf_html(report_html):' not in app_source
        assert 'WeasyPrintHTML' not in app_source
        assert 'render_analytics_reportlab_pdf_bytes' not in app_source
        assert 'canvasToPrintImage(sourceCanvas, index, printOptions)' in analytics_html
        assert 'function buildAnalyticsPrintPreview()' in analytics_html
        assert 'function buildAnalyticsOverviewPrintPreview()' in analytics_html
        assert "document.querySelector('#analytics-content .analytics-section.overview')" in analytics_html
        assert 'function stripAnalyticsOverviewPrintClone(root)' in analytics_html
        assert 'function replaceOverviewPrintCanvases(clone)' in analytics_html
        assert 'function overviewPrintCanvasOptions(canvasId)' in analytics_html
        assert "if (canvasId === 'trendChart')" in analytics_html
        assert "if (canvasId === 'overviewCategoryRevenueChart')" in analytics_html
        assert "if (canvasId === 'overviewCategoryMomentumChart')" in analytics_html
        assert 'analyticsPrintClientTable' in analytics_html
        assert 'function analyticsPrintDataLabelPlugin(formatter, options = {})' in analytics_html
        assert 'afterDatasetsDraw(chart)' in analytics_html
        assert 'function canvasHasDrawablePixels(canvas)' in analytics_html
        assert "if (!sourceChart && !canvasHasDrawablePixels(sourceCanvas)) return '';" in analytics_html
        assert "if (!canvasHasDrawablePixels(sourceCanvas)) throw new Error('No chart image available.');" in analytics_html
        assert "labelFormatter: value => formatCurrency(value, { maximumFractionDigits: 0 })" in analytics_html
        assert "labelFormatter: value => `${Number(value || 0).toFixed(1)}%`" in analytics_html
        assert 'dataLabelFontSize: 72' in analytics_html
        assert "dataLabelAlign: 'end'" in analytics_html
        assert 'dataLabelStrokeWidth: 9' in analytics_html
        assert 'function applyAnalyticsPrintCleanScales(exportOptions)' in analytics_html
        assert 'if (printOptions.cleanAxes) applyAnalyticsPrintCleanScales(exportOptions);' in analytics_html
        assert 'cleanAxes: true' in analytics_html
        assert 'exportWidth: 1100' in analytics_html
        assert 'exportHeight: 620' in analytics_html
        assert 'lineMultiplier: 4' in analytics_html
        assert 'legendFontSize: 36' in analytics_html
        assert 'minWidth: 3000' in analytics_html
        assert 'minHeight: 1300' in analytics_html
        assert 'dataLabelFontSize: 28' in analytics_html
        assert 'dataLabelStrokeWidth: 5' in analytics_html
        assert "getContext('2d', { willReadFrequently: true })" in analytics_html
        assert 'analyticsDrawableCanvasCache' in analytics_html
        assert ".analytics-print-chart.is-large img" in analytics_html
        assert '.analytics-paper .analytics-print-chart.is-large img.analytics-print-chart' in analytics_html
        assert 'height: 96mm;' in analytics_html
        assert 'strokeWidth: printOptions.dataLabelStrokeWidth' in analytics_html
        assert 'function validCanvasDataUrl(value)' in analytics_html
        assert "if (!validCanvasDataUrl(imageSrc) && canvasHasDrawablePixels(sourceCanvas))" in analytics_html
        assert "if (!validCanvasDataUrl(imageSrc)) throw new Error('Chart image export was empty.');" in analytics_html
        assert 'const sampleCanvas = document.createElement(\'canvas\');' in analytics_html
        assert 'context.drawImage(canvas, 0, 0, sampleWidth, sampleHeight);' in analytics_html
        assert '.analytics-print-table th,\n.analytics-print-table td' in analytics_html
        assert 'font-size: 6.5pt;' in analytics_html
        assert 'line-height: 1.05;' in analytics_html
        assert 'overflow-wrap: anywhere;' in analytics_html
        assert 'white-space: normal;' in analytics_html
        assert '<th class="numeric">Delta</th>' in analytics_html
        assert 'transform: scale(0.94);' in analytics_html
        assert 'transform: none !important;' in analytics_html
        assert "if (!rows.length) return '';" in analytics_html
        assert "if (sourceChart && !chartHasPrintableData(sourceChart)) return '';" in analytics_html
        assert 'prepareAnalyticsPrintClone' not in analytics_html
        assert 'function isAnalyticsPrintVisible' not in analytics_html
        assert 'function stripAnalyticsPrintInteractivity' not in analytics_html
        assert 'function removeHiddenAnalyticsPrintNodes' not in analytics_html
        assert 'document.getElementById(\'analytics-content\')?.cloneNode(true)' not in analytics_html
        assert 'const clone = overview.cloneNode(true);' in analytics_html
        assert "root.classList.add('analytics-overview-print-clone', 'analytics-overview-print-summary-only', 'analytics-overview-print-one-page');" in analytics_html
        assert "root.dataset.printSource = 'analytics-section-overview';" in analytics_html
        assert "root.dataset.printExpandedState = 'summary-only';" in analytics_html
        assert "root.dataset.printLayout = 'one-page-landscape';" in analytics_html
        assert "element.setAttribute('aria-expanded', 'false');" in analytics_html
        assert ".overview-layer-canvas, .overview-morph-back, .overview-morph-hint, .overview-morph-ghost" in analytics_html
        assert "element.classList.remove('is-expanded', 'is-morphing');" in analytics_html
        assert 'analytics-print-report' in analytics_html
        assert 'analytics-print-grid' in analytics_html
        assert '.analytics-print-grid.chart-pair' in analytics_html
        assert '.analytics-print-grid.table-pair' in analytics_html
        assert 'analytics-print-panel' in analytics_html
        assert 'analytics-print-kpi' in analytics_html
        assert 'analytics-print-table' in analytics_html
        assert '.analytics-paper .analytics-print-table th,' in analytics_html
        assert 'font-size: 6.5pt !important;' in analytics_html
        assert 'padding: 2pt 3pt !important;' in analytics_html
        assert '.analytics-paper .analytics-print-table .numeric' in analytics_html
        assert '.analytics-print-grid.chart-pair .analytics-print-chart img' in analytics_html
        assert '.analytics-paper .analytics-print-grid.chart-pair .analytics-print-chart img.analytics-print-chart' in analytics_html
        assert 'height: 92mm;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-canvas-trendChart' in analytics_html
        assert 'max-height: 58mm;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page>.analytics-story-header' in analytics_html
        assert 'grid-template-columns: minmax(0, 1fr) auto !important;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page .analytics-story-heading' in analytics_html
        assert 'flex-wrap: nowrap !important;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page .analytics-story-logo-box' in analytics_html
        assert 'width: 42mm !important;' in analytics_html
        assert 'min-width: 42mm !important;' in analytics_html
        assert 'justify-self: end !important;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page>.overview-asymmetric-layout.overview-morph-grid' in analytics_html
        assert 'grid-template-columns: minmax(0, 1fr) minmax(0, 2fr) !important;' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page .overview-left-column' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page .overview-main-panel' in analytics_html
        assert '.analytics-paper .analytics-overview-print-one-page .overview-tier-panel' in analytics_html
        assert 'border-right: 0 !important;' in analytics_html
        assert 'max-height: 46mm !important;' in analytics_html
        assert 'max-height: 43mm !important;' in analytics_html
        assert 'size: letter landscape' in analytics_html
        assert "pageSize: '330mm 216mm'" in analytics_html
        assert 'width: 279mm;' in analytics_html
        assert 'min-height: var(--analytics-paper-height);' in analytics_html
        assert 'width: auto;' in analytics_html
        assert 'min-height: auto;' in analytics_html
        assert 'height: auto !important;' in analytics_html
        assert 'overflow: visible !important;' in analytics_html
        assert 'analytics-print-content' in analytics_html
        assert 'function renderAnalyticsPrintPreviewContent()' in analytics_html
        assert "paper.dataset.printPreviewSource = 'analytics-section-overview';" in analytics_html
        assert "paper.dataset.printPreviewMode = 'summary-only';" in analytics_html
        assert 'role="dialog" aria-modal="true"' in analytics_html
        assert 'aria-labelledby="analyticsPrintTitle"' in analytics_html
        assert 'class="analytics-preview-title"' in analytics_html
        assert '.analytics-print-modal {' in analytics_html
        assert 'align-items: center;' in analytics_html
        assert 'justify-content: center;' in analytics_html
        assert 'width: 100vw !important;' in analytics_html
        assert 'height: 100vh !important;' in analytics_html
        assert 'max-width: none !important;' in analytics_html
        assert 'max-height: none !important;' in analytics_html
        assert '--analytics-paper-width: 279mm;' in analytics_html
        assert '--analytics-paper-height: 216mm;' in analytics_html
        assert '--analytics-print-margin: 10mm;' in analytics_html
        assert '--analytics-page-content-height:' in analytics_html
        assert 'width: min(1480px, calc(100vw - 28px));' in analytics_html
        assert 'max-width: min(1480px, calc(100vw - 28px));' in analytics_html
        assert 'max-height: calc(100vh - 28px);' in analytics_html
        assert '.analytics-preview-viewport {' in analytics_html
        assert 'width: 100%;' in analytics_html
        assert 'min-width: 0;' in analytics_html
        assert 'min-height: 0;' in analytics_html
        assert 'box-sizing: border-box;' in analytics_html
        assert 'id="analyticsPrintPaperSize"' in analytics_html
        assert 'id="analyticsPrintMargin"' in analytics_html
        assert 'letter-landscape' in analytics_html
        assert 'folio-landscape' in analytics_html
        assert 'a4-landscape' in analytics_html
        assert 'legal-landscape' not in analytics_html
        assert 'Folio Landscape (8.5 x 13)' in analytics_html
        assert 'Legal Landscape' not in analytics_html
        assert 'function updateAnalyticsPrintPaperSettings()' in analytics_html
        assert 'function renderAnalyticsPageCutoffGuides()' in analytics_html
        assert 'function repaginateAnalyticsPrintComponents()' in analytics_html
        assert 'function clearAnalyticsPrintPagination(paperElement)' in analytics_html
        assert '.analytics-print-page-break-before' in analytics_html
        assert 'break-before: page;' in analytics_html
        assert 'page-break-before: always;' in analytics_html
        assert 'elementHeight >= contentHeightPx * 0.92' in analytics_html
        assert 'element.matches(\'table, thead, tbody, tfoot, tr\')' in analytics_html
        assert 'paperElement.offsetWidth / paper.width' in analytics_html
        assert 'analytics-page-cutoff-guide' in analytics_html
        assert 'analyticsDynamicPrintPageStyle' in analytics_html
        assert 'Page ${page + 1} starts here' in analytics_html
        assert 'paper.height - (margin * 2)' in analytics_html
        assert "document.body.style.overflow = 'hidden'" in analytics_html
        assert 'analyticsPrintPreviousOverflow' in analytics_html
        assert '.analytics-paper :hover,' in analytics_html
        assert 'pointer-events: none;' in analytics_html
        assert 'border-bottom: 4pt solid #FF6A00' in analytics_html
        assert 'border: 1.5pt solid #CBD5E1 !important' in analytics_html
        assert 'style="margin-top:16pt;"' not in analytics_html
        assert 'display: table-header-group;' in analytics_html
        assert '.analytics-paper tr,' in analytics_html
        assert 'Chart preview is available on-screen before printing.' not in analytics_html
        assert '.analytics-paper *' in analytics_html
        assert 'Print Preview' in analytics_html
        assert '>Print / Save PDF</button>' in analytics_html
        assert 'window.print()' in analytics_html
        assert 'repaginateAnalyticsPrintComponents();\n            renderAnalyticsPageCutoffGuides();\n            await waitForAnalyticsPrintReady();\n            window.print();' in analytics_html
        assert 'function buildAnalyticsPdfPayload()' not in analytics_html
        assert 'function downloadAnalyticsPdf()' not in analytics_html
        assert "fetch('/api/analytics/export.pdf'" not in analytics_html
        assert 'analytics-overview-print-clone' in analytics_html
        assert 'analytics-overview-print-summary-only' in analytics_html
        assert '.analytics-paper .analytics-overview-print-summary-only .overview-layer-summary' in analytics_html
        assert 'analytics-overview-print-canvas' in analytics_html
        assert 'analytics-overview-print-canvas-trendChart' in analytics_html
        assert 'stripAnalyticsPdfInteractivity' not in analytics_html
        assert 'cloneNode(true)' in analytics_html
        assert 'Preview PDF' not in analytics_html
        assert 'Print / Save PDF' in analytics_html
        assert 'analytics-print-heading' in analytics_html
        assert 'body>*:not(#analyticsPrintModal)' in analytics_html.replace(' ', '')
        assert '.analytics-preview-toolbar{display:none!important;}' in analytics_html.replace(' ', '').replace('\n', '')

        reports_html = open(
            os.path.join(ROOT, 'templates', 'reports.html'),
            encoding='utf-8'
        ).read()
        assert 'openReportPrintPreview()' in reports_html
        assert 'Print Preview' in reports_html
        assert '>Print</button>' in reports_html
        assert "auditExport('PRINT')" in reports_html
        assert 'exportReportPdf' not in reports_html
        assert 'Preview PDF' not in reports_html
        assert 'Print / Save PDF' not in reports_html
        assert 'print-heading' in reports_html
        assert 'body>*:not(#reportPreviewModal)' in reports_html.replace(' ', '')
        assert '.preview-toolbar{display:none!important;}' in reports_html.replace(' ', '').replace('\n', '')
        assert "letter ${isPortrait ? 'portrait' : 'landscape'}" in reports_html
        assert '.print-table .value-positive' in reports_html
        assert '.print-table .value-negative' in reports_html
        assert 'print-color-adjust: exact' in reports_html

        invoices_html = open(
            os.path.join(ROOT, 'templates', 'invoices.html'),
            encoding='utf-8'
        ).read()
        assert 'Particular Summary' in invoices_html
        assert 'invoice-summary-cell' in invoices_html
        assert 'colspan="11"' in invoices_html
        assert "inv.summary || inv.admin_upload_note || '-'" in invoices_html
        assert 'soParticularsPanel' in invoices_html
        assert 'soParticularsList' in invoices_html
        assert 'displaySalesOrderParticulars(selectedSalesOrder.items || [])' in invoices_html
        assert 'class="so-particular-row"' in invoices_html

    print('Invoice, quantity, and Analytics print check passed.')


if __name__ == '__main__':
    main()

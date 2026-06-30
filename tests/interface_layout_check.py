import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import build_theme_css, default_theme_settings  # noqa: E402


def read(path):
    with open(os.path.join(ROOT, path), encoding='utf-8') as source:
        return source.read()


def main():
    styles = read(os.path.join('static', 'css', 'styles.css'))
    analytics = read(os.path.join('templates', 'analytics.html'))
    evaluation = read(os.path.join('templates', 'evaluation.html'))
    admin = read(os.path.join('templates', 'admin.html'))
    invoices = read(os.path.join('templates', 'invoices.html'))
    sales_order = read(os.path.join('templates', 'sales_order.html'))
    expenses = read(os.path.join('templates', 'purchase_orders.html'))
    generated_theme = build_theme_css(default_theme_settings())

    assert '--ui-control-height: 44px' in styles
    assert 'input[type="checkbox"]' in styles
    assert 'width: 20px !important' in styles
    assert '.form-grid-3col' in styles
    assert '.button-group-responsive' in styles
    assert '@media (max-width: 760px)' in styles
    assert 'System-wide UX foundation' in styles
    assert '--system-page-max: 1760px' in styles
    assert '--ui-font-page-title: clamp(1.4rem, 1.8vw, 1.8rem)' in styles
    assert '--ui-font-card-title: 0.95rem' in styles
    assert '--ui-font-kpi: clamp(1.25rem, 1.8vw, 1.55rem)' in styles
    assert 'font-size: var(--ui-font-page-title) !important' in styles
    assert 'font-size: var(--ui-font-card-title) !important' in styles
    assert 'font-size: var(--ui-font-table) !important' in styles
    assert '.history-fit-table' in styles
    assert 'width: max-content !important' in styles
    assert 'table-layout: auto' in styles
    assert 'white-space: normal !important' in styles
    assert 'white-space: nowrap !important' in styles
    assert '.invoice-history-table .invoice-summary-cell' in styles
    assert '.sales-workflow-tabs' in styles
    assert '.evaluation-page-header' in styles
    assert '.report-filter' in styles
    assert '.table-wrap table' in styles
    assert '-webkit-overflow-scrolling: touch' in styles
    assert '.component-scroll' in styles
    assert '.analytics-row-stack' in styles
    assert '.analytics-flow-row' in styles
    assert '@media (min-width: 1024px) and (pointer: fine)' in styles
    assert 'overflow-x: auto;' in styles
    assert 'display: revert !important' in styles
    assert '.auth-card' in styles

    assert '.recommendation-list' in analytics
    assert '.recommendation-row-metrics' in analytics
    assert '.recommendation-primary-action' in analytics
    assert '.recommendation-card-section' in analytics
    assert 'recommendation-store-name' in analytics
    assert 'This rule-based recommendation system' in analytics
    assert 'Why this appeared' in analytics
    assert 'What it means' in analytics
    assert 'Recommended action' in analytics
    assert 'How this was calculated' in analytics
    assert 'width: min(760px, calc(100vw - 2rem)) !important' in analytics
    assert '.recommendation-modal .table-wrap' in analytics
    assert '.recommendation-modal .data-table' in analytics
    assert 'Revenue Forecast' in analytics
    assert 'revenueForecastChart' in analytics
    assert 'Top 15 products ranked by Sales Order value' in analytics
    assert 'productContributionSummary' in analytics
    assert 'item: \'Other\'' not in analytics
    assert 'remaining products are grouped as Other' not in analytics
    assert 'revenueForecastRange' in analytics
    assert 'revenueForecastGrouping' in analytics
    assert 'revenueForecastHorizon' in analytics
    assert 'Last 12 months' in analytics
    assert 'Last 3 years' in analytics
    assert 'Custom range' in analytics
    assert 'Quarterly' in analytics
    assert 'Yearly' in analytics
    assert '12 months' in analytics
    assert 'Forecast starts here' in analytics
    assert 'Revenue Forecast chart shows historical Sales Order value' in analytics
    assert 'extends it into the next forecast period' in analytics
    assert 'Overview Revenue IN' in analytics
    assert 'average item quantity sold per active sales day' in analytics
    assert 'Forecast vs Actual Validation' not in analytics
    assert 'forecastValidationChart' not in analytics
    assert 'recommendationStoreSearch' in analytics
    assert 'setRecommendationSeverityFilter' in analytics
    assert 'No recommendations match the selected severity and Store Name.' in analytics
    assert 'analyticsToolsDrawer' in analytics
    assert 'openAnalyticsTools' in analytics
    assert 'Generate Analytics Report' in analytics
    assert 'Upload Historical CSV/Excel' in analytics
    assert 'data-section="evaluation"' not in analytics
    assert 'class="analytics-row-stack"' in analytics
    assert 'class="analytics-flow-row"' in analytics
    assert 'grid-template-columns: 1fr 300px' not in analytics
    assert 'grid-template-columns: minmax(0, 1.2fr)' not in analytics
    assert 'grid-template-columns: minmax(0, 1fr) minmax(0, 1fr)' not in analytics
    assert 'Web App Evaluation Questionnaire' in evaluation
    assert "category === 'Design/User Experience' ? 'Usability' : category" in evaluation
    assert 'evaluationPrintOverlay' in evaluation
    assert 'evaluation-rating-cell' in evaluation
    assert 'role="tablist"' in evaluation
    assert 'id="questionnairePanel"' in evaluation
    assert 'id="testCasesPanel"' in evaluation
    assert 'qa-summary-dashboard' in evaluation
    assert 'downloadQaCsv' in evaluation
    assert 'Screenshot Filename' in evaluation
    assert '#adminTabs' in admin
    assert 'overflow-x: auto' in admin
    assert '-webkit-overflow-scrolling: touch' in admin
    assert 'min-width: 820px' in admin
    assert 'position: sticky' in admin
    assert 'overflow-wrap: anywhere' in admin
    assert '@media (max-width: 700px)' in analytics
    assert 'input[type="checkbox"]' in generated_theme
    assert 'min-height: 44px !important' in generated_theme
    assert 'padding: 16px !important' in generated_theme
    assert '--ui-font-page-title: clamp(1.4rem, 1.8vw, 1.8rem)' in generated_theme
    assert 'font-size: var(--ui-font-kpi) !important' in generated_theme
    assert 'id="tax2307Checked"' in invoices
    assert 'class="invoice-table history-fit-table invoice-history-table"' in invoices
    assert sales_order.count('id="field-companyName"') == 1
    assert sales_order.count('id="salesOrderFormPanel"') == 1
    assert 'id="manualFormSlot"' in sales_order
    assert 'id="excelFormSlot"' in sales_order
    assert 'width: min(100%, 920px)' in sales_order
    assert 'margin: 0 auto' in sales_order
    assert 'width: min(100%, 1280px)' in sales_order
    assert 'margin: 1.5rem auto 0' in sales_order
    assert 'class="history-actions"' in sales_order
    assert 'class="history-filter"' in sales_order
    assert 'class="mapper-container workflow-upload-grid"' in sales_order
    assert 'class="history-table history-fit-table sales-order-history-table"' in sales_order
    assert 'id="excelPreview"' in sales_order
    assert 'targetSlot.appendChild(formPanel)' in sales_order
    assert 'manualPane.hidden = !manualSelected' in sales_order
    assert 'excelPane.hidden = manualSelected' in sales_order
    assert 'id="salesOrderStatusFilter"' in sales_order
    assert 'renderSalesOrderHistory()' in sales_order
    assert 'id="expenseStatusFilter"' in expenses
    assert 'displayPurchaseOrders()' in expenses
    assert 'class="history-fit-table expense-history-table"' in expenses
    assert 'class="card expense-entry-card"' in expenses
    assert 'class="expense-entry-form"' in expenses
    assert 'class="form-grid expense-grid-docs"' in expenses
    assert 'class="form-grid expense-grid-details"' in expenses
    assert 'class="expense-entry-balance-grid"' in expenses
    assert 'class="expense-form-actions"' in expenses

    print('Interface layout check passed.')


if __name__ == '__main__':
    main()

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
    app_source = read('app.py')
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
    assert '<label for="cashAmount">Cash Amount</label>' in expenses
    assert 'id="cashAmount" min="0" step="0.01"' in expenses
    assert 'id="cashAmount" min="0" step="0.01" required' not in expenses
    assert '<label for="editCashAmount">Cash Amount</label>' in expenses
    assert 'id="editCashAmount" min="0" step="0.01"' in expenses
    assert 'id="editCashAmount" min="0" step="0.01" required' not in expenses
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
    assert '.analytics-graph-section' in styles
    assert '.analytics-table-section' in styles
    assert '.analytics-chart-frame' in styles
    assert '*::before' in styles
    assert '*::after' in styles
    assert 'box-shadow: none !important' in styles
    assert '--shadow: none' in styles
    assert '--shadow-soft: none' in styles
    assert '--glass-shadow: none' in styles
    assert '--card-shadow: none' in styles
    assert 'body *:not(#systemNoShadowOverride)' in styles
    assert '--radius-xl: 0' not in styles
    assert '--mode-radius: 0' not in styles
    assert '--table-inset-shadow' not in styles
    assert 'box-shadow: var(--table-inset-shadow) !important' not in styles
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
    assert '.analytics-story-header' in analytics
    assert '.analytics-purpose-line' in analytics
    assert '.analytics-key-answer' in analytics
    assert '.analytics-story-map' in analytics
    assert '.analytics-story-map-row' in analytics
    assert '.analytics-takeaway' in analytics
    assert '.analytics-manager-action' in analytics
    assert '.analytics-summary-strip' in analytics
    assert 'Business goal > Metric > Level of detail > Type of visualization' in analytics
    assert "label = start_date.strftime('%b %Y')" in app_source
    assert 'analyticsStoryHeader' in analytics
    assert 'analyticsBusinessGoalMap' in analytics
    assert 'analyticsManagerAction' in analytics
    assert 'analyticsSummaryStrip' in analytics
    assert 'Latest-month Sales Order revenue is the anchor; the rest of the dashboard explains trend, client value momentum, and client-level movement.' in analytics
    assert '.overview-asymmetric-layout' in analytics
    assert '.overview-left-column' in analytics
    assert '.overview-main-panel' in analytics
    assert 'border-right: 2px solid #c4c4c4' in analytics
    assert 'border-right-color: var(--border-color, #c4c4c4)' in analytics
    assert 'style="border-right: 2px solid #c4c4c4 !important; padding-right: 1.5rem !important;"' in analytics
    assert '.overview-main-row' in analytics
    assert '.overview-revenue-kpi-block' in analytics
    assert '.overview-revenue-kpi-grid' in analytics
    assert '.overview-highlight' in analytics
    assert '.overview-paired-charts' in analytics
    assert 'min-height: 235px' in analytics
    assert 'height: 165px' in analytics
    assert '.overview-chart-caption' in analytics
    assert '.overview-tier-panel .client-table thead th' in analytics
    assert 'font-size: 10px !important' in analytics
    assert 'padding: 2px 3px !important' in analytics
    assert 'border-bottom: 1px solid #c4c4c4 !important' in analytics
    assert 'table-layout: fixed' in analytics
    assert 'colspan="4"' in analytics
    assert 'background: #d1fae5; color: #065f46' in analytics
    assert 'background: #fecaca; color: #7f1d1d' in analytics
    assert 'background:${deltaBackground};color:${deltaColor};font-weight:500' in analytics
    assert '.overview-driver-table-increase.client-table th:nth-child(4)' in analytics
    assert '.overview-driver-table-decrease.client-table th:nth-child(4)' in analytics
    assert 'class="client-table overview-driver-table overview-driver-table-increase"' in analytics
    assert 'class="client-table overview-driver-table overview-driver-table-decrease"' in analytics
    assert '.overview-morph-grid' in analytics
    assert '.overview-morph-card' in analytics
    assert '.overview-morph-ghost' in analytics
    assert '.overview-morph-card.is-morphing' in analytics
    assert '.overview-morph-card.is-expanded' in analytics
    assert '.overview-layer-summary' in analytics
    assert '.overview-layer-canvas' in analytics
    assert '.overview-morph-tabs' not in analytics
    assert '.overview-morph-tab' not in analytics
    assert '.overview-morph-panel' not in analytics
    assert 'class="overview-morph-title"' not in analytics
    assert 'overview-morph-body' in analytics
    assert 'overview-revenue-summary' in analytics
    assert 'overview-year-trend' in analytics
    assert 'overview-client-category' in analytics
    assert 'overview-client-drivers' in analytics
    assert 'openOverviewMorph' in analytics
    assert 'closeOverviewMorph' in analytics
    assert 'measureOverviewCard' in analytics
    assert 'createOverviewGhost' in analytics
    assert 'overviewMorphContainerRect' in analytics
    assert 'overviewMorphContainerElement' in analytics
    assert 'overviewViewportRectToMorphRect' in analytics
    assert "card.style.position = hasContainer ? 'absolute' : 'fixed'" in analytics
    assert 'function overviewMorphTargetRect(card = activeOverviewMorph?.card)' in analytics
    assert "card?.closest('.overview-morph-grid')" in analytics
    assert 'top: rect.top - containerRect.top' in analytics
    assert 'syncOverviewMorphToContainer' in analytics
    assert "window.addEventListener('resize'" in analytics
    assert 'renderOverviewPlaceholderCanvas' in analytics
    assert 'ensureOverviewMorphData' in analytics
    assert 'destroyOverviewMorphCharts' in analytics
    assert 'overviewMorphCharts' in analytics
    assert 'overviewForecastAccuracy' in analytics
    assert 'salesOrderMonthlyTrendRows' in analytics
    assert 'buildOverviewSalesOrderTrend' in analytics
    assert 'sales_order_trend' in analytics
    assert "latest_data_source: 'Sales Order'" in analytics
    assert 'overviewClientsWithZScores' in analytics
    assert 'overviewMorphBody' in analytics
    assert 'overviewLatestActualForecastPoints' in analytics
    assert 'overviewMorphShortMonthLabel' in analytics
    assert '.slice(-12)' in analytics
    assert 'overviewSignedForecastTotal' in analytics
    assert 'overviewValueWithNegativeSign' in analytics
    assert 'const latestActualIndex = Math.min(Math.max(Number(tierData.latestIndex || 0), 0), Math.max(baseLabels.length - 1, 0))' in analytics
    assert 'const finalForecastIndex = labels.length - 1' in analytics
    assert 'const signedForecastLabel = overviewSignedForecastTotal(forecastTotal, forecastDelta)' in analytics
    assert "const negativeForecastColor = '#dc6b6b'" in analytics
    assert 'const forecastBoundaryIndex = baseLabels.length' in analytics
    assert "ctx.strokeStyle = '#cbd5e1'" in analytics
    assert "latestActualDate?.getMonth() === 11 ? String(latestActualDate.getFullYear() + 1) : ''" in analytics
    assert 'const labelWidth = ctx.measureText(signedForecastLabel).width' in analytics
    assert 'chartArea.right - labelWidth / 2 - 4' in analytics
    assert '_context.dataIndex === latestActualIndex ? 4 : 0' in analytics
    assert '_context.dataIndex === finalForecastIndex ? 4 : 0' in analytics
    assert 'overviewRevenueForecastParams' in analytics
    assert 'refreshOverviewRevenueForecastMorph' in analytics
    assert 'initializeOverviewRevenueForecastControls' in analytics
    assert 'renderOverviewRevenueForecastMorphChart' in analytics
    assert 'overviewMorphBarLabelPlugin' in analytics
    assert 'overviewZScoreBounds' in analytics
    assert 'renderOverviewRevenueSummaryMorph' in analytics
    assert 'renderOverviewYearTrendMorph' in analytics
    assert 'renderOverviewClientCategoryMorph' in analytics
    assert 'renderOverviewClientDriversMorph' in analytics
    assert 'activateOverviewMorphTab' not in analytics
    assert 'handleOverviewMorphKeydown' in analytics
    assert 'Back to Executive Grid' in analytics
    assert 'Descriptive' not in analytics
    assert 'Predictive' not in analytics
    assert 'Prescriptive' not in analytics
    assert "the ${overviewStoryHighlight('Revenue')} Generated" in analytics
    assert 'Forecasted ${overviewStoryHighlight' in analytics
    assert 'forecast <strong style="color:#111827;">Accuracy</strong> of' in analytics
    assert 'overviewMorphForecastScope' in analytics
    assert '<option value="all">All data</option>' in analytics
    assert '<option value="year">Specific year</option>' in analytics
    assert 'overviewMorphForecastMonths' in analytics
    assert '<option value="3">3 months</option>' in analytics
    assert '<option value="6">6 months</option>' in analytics
    assert '<option value="12">12 months</option>' in analytics
    assert 'Holt-Winters Forecast' in analytics
    assert "label: `${tierData.previousYear || 'Previous Year'} Sales Order Revenue`" in analytics
    assert "label: `${tierData.latestYear || 'Selected Year'} Sales Order Revenue`" in analytics
    assert "params.forecast_scope = 'all'" in analytics
    assert 'forecast_scope' in analytics
    assert 'Peak sale' in analytics
    assert 'overviewStoreNameOnly' in analytics
    assert 'const name = overviewStoreNameOnly(peakClient)' in analytics
    assert 'Store Name: <strong>${escapeHtml(name)}</strong>' not in analytics
    assert 'Combined client category frequency z-score and Sales Order value z-score scatter plot' in analytics
    assert 'Sales Order value z-score' in analytics
    assert 'overview-driver-recommendations' in analytics
    assert 'overview-driver-morph-grid' in analytics
    assert 'border: 1px solid #c4c4c4' in analytics
    assert 'borderDash: [5, 4]' in analytics
    assert "ticks: { callback: value => Number(value) === 0 ? '0%' : '' }" in analytics
    assert 'Top 5 clients driving revenue increase' in analytics
    assert 'Top 5 clients driving revenue decrease' in analytics
    assert 'Recommendation' in analytics
    assert 'overviewMorphRevenueForecastChart' in analytics
    assert 'overviewMorphYearTrendChart' in analytics
    assert 'overviewMorphCategoryRevenueChart' in analytics
    assert 'overviewMorphCategoryMomentumChart' in analytics
    assert 'overviewMorphCombinedScatterChart' in analytics
    assert 'overviewMorphClientParetoChart' in analytics
    assert 'Client Value and Categorization' in analytics
    assert 'activateOverviewCategoryView' in analytics
    assert 'overviewParetoRows' in analytics
    assert 'overviewParetoCategoryCuts' in analytics
    assert 'overviewParetoCategoryCutPlugin' in analytics
    assert 'overviewParetoRows(clients)' in analytics
    assert 'overviewParetoRows(clients, 12)' not in analytics
    assert 'The vertical lines show where the category cuts begin.' in analytics
    assert 'Cumulative Revenue %' in analytics
    assert 'this is how clients are' in analytics
    assert 'scatterColors' in analytics
    assert 'applyOverviewScatterVisibleBounds' in analytics
    assert 'overviewVisibleScatterPoints' in analytics
    assert 'overviewScatterDataBounds' in analytics
    assert 'chart.setDatasetVisibility(index, !chart.isDatasetVisible(index))' in analytics
    assert 'data: { datasets }' in analytics
    assert "legend: {\n                                display: true" in analytics
    assert 'overviewMorphScatterAChart' not in analytics
    assert 'overviewMorphScatterBChart' not in analytics
    assert 'overviewMorphScatterCChart' not in analytics
    assert analytics.count('id="trendChart"') == 1
    assert analytics.count('id="overviewCategoryRevenueChart"') == 1
    assert analytics.count('id="overviewCategoryMomentumChart"') == 1
    assert 'role="button"' in analytics
    assert 'tabindex="0"' in analytics
    assert 'aria-expanded="false"' in analytics
    assert '.analytics-category-manager' in analytics
    assert '.overview-change-badge' in analytics
    assert 'Overview revenue dashboard' in analytics
    assert 'Core Revenue Trends' in analytics
    assert 'Performance breakdown' in analytics
    assert 'This is the <span class="overview-highlight">Sales Order Revenue</span> generated...' in analytics
    assert 'Total Monthly Sales Order Revenue' in analytics
    assert 'Month-on-Month Sales Order Revenue % Change' in analytics
    assert 'Year-on-Year Sales Order Revenue % Change' in analytics
    assert 'Sales Order value by order date' in analytics
    assert '... and the trend of' in analytics
    assert 'overviewMonthAxisLabel' in analytics
    assert 'parseOverviewMonthLabel(label) || parseForecastPeriod(label)' in analytics
    assert 'const parsed = parseOverviewMonthLabel(label) || parseForecastPeriod(label)' in analytics
    assert 'function analyticsMonthDisplay' in analytics
    assert 'revenueForecast.latest_historical_month ? analyticsMonthDisplay(revenueForecast.latest_historical_month)' in analytics
    assert 'topMonth.period_label || analyticsMonthDisplay(topMonth.period)' in analytics
    assert 'peakMonth.period_label || analyticsMonthDisplay(peakMonth.period)' in analytics
    assert 'const extensionLabels = useSalesOrderTrend ? [] : nextOverviewMonthLabels(latestLabel)' in analytics
    assert 'nextOverviewMonthLabels' in analytics
    assert "month: 'short', year: 'numeric'" in analytics
    assert 'This is the Revenue split by <span class="overview-highlight">Client Value Category</span> this' in analytics
    assert 'Monthly Revenue' in analytics
    assert 'M-o-M revenue % Change' in analytics
    assert "['A-Class Clients', 'B-Class Clients', 'C-Class Clients']" in analytics
    assert 'overviewCategoryRevenueChart' in analytics
    assert 'overviewCategoryMomentumChart' in analytics
    assert analytics.count('border: { display: true }') >= 4
    assert '...where these 5 clients drive the <span class="overview-delta-increase">increase</span> and <span class="overview-delta-decrease">decrease</span> in revenue.' in analytics
    assert 'Product Category Manager' in analytics
    assert 'loadProductCategoryManager' in analytics
    assert 'saveProductCategories' in analytics
    assert '/item-categories' in analytics
    assert 'Potential Monthly Revenue Loss' not in analytics
    assert 'Products with 0 stock' not in analytics
    assert 'Client value is explained by Sales Order value, ordering frequency, and branch reach.' in analytics
    assert 'Client value categories show who drives cumulative revenue' in analytics
    assert 'ABC Pareto revenue bar and cumulative line chart' in analytics
    assert 'abcReferenceLinePlugin' in analytics
    assert 'Clients sorted by Master Priority Rank' in analytics
    assert 'Cumulative Revenue Contribution' in analytics
    assert '80% A-Class boundary' in analytics
    assert '95% B-Class boundary' in analytics
    assert 'Client ABC classification follows score ranking and Pareto grouping' in analytics
    assert 'Top 3 clients by combined score need the strongest retention focus' in analytics
    assert 'Score ${Number(client.client_performance_score || 0).toFixed(1)} = Revenue' in analytics
    assert 'Clients are sorted by combined score' in analytics
    assert 'Client Sales Order value' in analytics
    assert 'Cumulative revenue %' in analytics
    assert 'Total expenses are explained by fixed versus variable pressure and the largest recorded particulars.' in analytics
    assert 'Expense mix shows fixed versus variable pressure' in analytics
    assert 'Largest particulars reveal where spending is concentrated' in analytics
    assert 'Forecast quality comes first, then product, period, and item details explain the sales plan.' in analytics
    assert 'Forecasted Sales Order value needs stock planning review' in analytics
    assert 'Expected Sales Orders' in analytics
    assert 'When do we experience peak demand?' in analytics
    assert 'Which products drive booked revenue?' in analytics
    assert 'Item-level demand forecast' in analytics
    assert '.revenue-dashboard-grid' in analytics
    assert '.revenue-zone-hero' in analytics
    assert '.revenue-zone-timing' in analytics
    assert '.revenue-zone-products' in analytics
    assert '.revenue-zone-table' in analytics
    assert '.revenue-quality-chip' in analytics
    assert '.revenue-trend-indicator' in analytics
    assert '.revenue-peak-badge' in analytics
    assert '.revenue-status-chip' in analytics
    assert 'toggleProductContributionLimit' in analytics
    assert 'View All' in analytics
    assert 'Show Top 5' in analytics
    assert 'High-priority recommendations come first, then each card explains why it appeared and what to do next.' in analytics
    assert 'Rule-based recommendations convert analytics signals into manager actions' in analytics
    assert 'Revenue Forecast' in analytics
    assert 'revenueForecastChart' in analytics
    assert 'Top ${productDisplayLimit} products ranked by Sales Order value' in analytics
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
    assert '.graph-insights' in analytics
    assert '.graph-insight-status-pill' in analytics
    assert '.graph-insight-chip' in analytics
    assert 'graph-insight-metrics' in analytics
    assert 'graph-insight-explanation' in analytics
    assert 'graph-insight-action' in analytics
    assert '.forecast-quality-label' in analytics
    assert '.forecast-quality-chip' in analytics
    assert '.item-forecast-summary' in analytics
    assert 'Graph Insights' in analytics
    assert 'Forecast Quality' in analytics
    assert 'Forecast Status:' in analytics
    assert 'Reliable' in analytics
    assert 'Review Needed' in analytics
    assert 'Insufficient Data' in analytics
    assert 'Next Forecast' in analytics
    assert 'Prepare stock for expected demand but verify unpaid orders first.' in analytics
    assert 'predictive analytics using Holt-Winters forecasting' in analytics
    assert 'not actual collected cash' in analytics
    assert 'buildRevenueForecastInsights' in analytics
    assert 'buildProductContributionInsights' in analytics
    assert 'buildPeakPeriodInsights' in analytics
    assert 'buildItemForecastInsights' in analytics
    assert analytics.count('analytics-graph-section"') == 3
    assert analytics.count('analytics-table-section') == 1
    assert 'data-analytics-graph="revenue-forecast"' in analytics
    assert 'data-analytics-graph="product-contributions"' in analytics
    assert 'data-analytics-graph="peak-sales-periods"' in analytics
    assert 'data-analytics-graph="item-forecasts"' in analytics
    assert 'analytics-chart-frame-tall' in analytics
    assert 'analytics-chart-frame-compact' in analytics
    assert 'Top ${productDisplayLimit} products ranked by Sales Order value' in analytics
    assert 'const productDisplayLimit = 5' in analytics
    assert 'Today - Forecast starts here' in analytics
    assert "backgroundColor: [...peakMonths].reverse().map(item => Number(item.average_quantity || 0) === maxAverageQuantity ? '#F97316' : '#CBD5E1')" in analytics
    assert 'Historical Sales Order value transitions after Today into a dotted forecast segment.' in analytics
    assert 'expected booked Sales Order value, not actual collected cash' in analytics
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
    assert 'already_submitted' in evaluation
    assert 'You have already submitted your system evaluation.' in evaluation
    assert 'role="tablist"' in evaluation
    assert 'id="questionnairePanel"' in evaluation
    assert 'id="questionnaireResultsPanel"' in evaluation
    assert 'Questionnaire Results' in evaluation
    assert 'id="testCasesPanel"' in evaluation
    assert 'font-family: "Times New Roman", Times, serif' in evaluation
    assert 'font-size: 14px' in evaluation
    assert 'line-height: 1.15' in evaluation
    assert 'max-width: 8in' in evaluation
    assert 'class="evaluation-result-view-toggle"' in evaluation
    assert 'aria-pressed="true" data-results-view="table"' in evaluation
    assert 'aria-pressed="false" data-results-view="graph"' in evaluation
    assert 'toggleEvaluationResultsView' in evaluation
    assert 'renderEvaluationCategoryGraph' in evaluation
    assert 'category.rating_distribution' in evaluation
    assert 'class="evaluation-category-graph"' in evaluation
    assert '.evaluation-category-graph {' in evaluation
    assert 'evaluation-likert-landscape' in evaluation
    assert 'evaluation-likert-track' in evaluation
    assert 'evaluation-likert-segment' in evaluation
    assert 'max-width: 8in' in evaluation
    assert 'min-height: 46px' in evaluation
    assert 'grid-template-columns: repeat(5, minmax(0, 1fr))' in evaluation
    assert "1: { label: 'Strongly Disagree', color: '#ef4444' }" in evaluation
    assert "5: { label: 'Strongly Agree', color: '#15803d' }" in evaluation
    assert '.evaluation-category-bars' not in evaluation
    assert '.evaluation-category-bar-fill' not in evaluation
    assert 'Strongly Disagree' in evaluation
    assert 'Strongly Agree' in evaluation
    assert 'Total responses represented in this category' in evaluation
    assert 'Copy Table as Image' in evaluation
    assert 'Copy Graph as Image' in evaluation
    assert 'copyEvaluationElementAsImage' in evaluation
    assert 'ClipboardItem' in evaluation
    assert 'image/png' in evaluation
    assert 'toggleEvaluationCategoryView' not in evaluation
    assert '.evaluation-category-table {' in evaluation
    assert 'background: #fff;' in evaluation
    assert 'color: #000;' in evaluation
    assert '.evaluation-category-table thead th' in evaluation
    assert 'border-top: 1px solid #000;' in evaluation
    assert 'border-bottom: 1px solid #000;' in evaluation
    assert '.evaluation-category-table tfoot td' in evaluation
    assert 'font-weight: 400;' in evaluation
    assert '.evaluation-category-table tfoot td:last-child' in evaluation
    assert 'font-weight: 700;' in evaluation
    assert '/* as dasd' not in evaluation
    assert '<td colspan="2" style=' in evaluation
    assert 'Total Weighted Mean</td>' in evaluation
    assert "font-family:'Times New Roman', Times, serif" in evaluation
    assert 'font-size: 14px' in evaluation
    assert 'font-size:14px !important' in evaluation
    assert 'line-height:1.12' in evaluation
    assert 'background:#ffffff !important; color:#000000 !important' in evaluation
    assert 'border-top:1px solid #000000 !important; border-bottom:1px solid #000000 !important' in evaluation
    assert 'border:0 !important' in evaluation
    assert 'font-weight:400 !important;">Total Weighted Mean</td>' in evaluation
    assert 'font-weight:700 !important;">${Number(category.total_weighted_mean || 0).toFixed(2)}</td>' in evaluation
    assert 'renderCategoryPieChart' not in evaluation
    assert '.evaluation-category-pie' not in evaluation
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
    assert '--shadow: none' in generated_theme
    assert '--shadow-soft: none' in generated_theme
    assert '--glass-shadow: none' in generated_theme
    assert '--card-shadow: none' in generated_theme
    assert 'id="tax2307Checked"' in invoices
    assert 'class="invoice-table history-fit-table invoice-history-table"' in invoices
    assert sales_order.count('id="field-companyName"') == 1
    assert sales_order.count('id="salesOrderFormPanel"') == 1
    assert 'id="manualFormSlot"' in sales_order
    assert 'id="excelFormSlot"' in sales_order
    assert 'shadow-lg' not in sales_order
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

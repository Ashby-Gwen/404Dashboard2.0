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
    generated_theme = build_theme_css(default_theme_settings())

    assert '--ui-control-height: 44px' in styles
    assert 'input[type="checkbox"]' in styles
    assert 'width: 20px !important' in styles
    assert '.form-grid-3col' in styles
    assert '.button-group-responsive' in styles
    assert '@media (max-width: 760px)' in styles

    assert '.recommendation-list' in analytics
    assert '.recommendation-row-metrics' in analytics
    assert '.recommendation-primary-action' in analytics
    assert 'recommendation-store-name' in analytics
    assert 'recommendationStoreSearch' in analytics
    assert 'setRecommendationSeverityFilter' in analytics
    assert 'No recommendations match the selected severity and Store Name.' in analytics
    assert 'analyticsToolsDrawer' in analytics
    assert 'openAnalyticsTools' in analytics
    assert 'Generate Analytics Report' in analytics
    assert 'Upload Historical CSV/Excel' in analytics
    assert 'data-section="evaluation"' not in analytics
    assert 'Web App Evaluation Questionnaire' in evaluation
    assert 'evaluationPrintOverlay' in evaluation
    assert 'evaluation-rating-cell' in evaluation
    assert 'evaluation-score-track' in evaluation
    assert 'evaluation-feedback-result' in evaluation
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
    assert 'id="tax2307Checked"' in invoices

    print('Interface layout check passed.')


if __name__ == '__main__':
    main()

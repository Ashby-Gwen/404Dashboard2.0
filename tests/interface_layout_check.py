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
    invoices = read(os.path.join('templates', 'invoices.html'))
    generated_theme = build_theme_css(default_theme_settings())

    assert '--ui-control-height: 44px' in styles
    assert 'input[type="checkbox"]' in styles
    assert 'width: 20px !important' in styles
    assert '.form-grid-3col' in styles
    assert '.button-group-responsive' in styles
    assert '@media (max-width: 760px)' in styles

    assert '.recommendation-grid' in analytics
    assert '.recommendation-metrics' in analytics
    assert '.recommendation-action' in analytics
    assert 'recommendation-store-name' in analytics
    assert 'View details →' in analytics

    assert 'input[type="checkbox"]' in generated_theme
    assert 'min-height: 44px !important' in generated_theme
    assert 'padding: 16px !important' in generated_theme
    assert 'id="tax2307Checked"' in invoices

    print('Interface layout check passed.')


if __name__ == '__main__':
    main()

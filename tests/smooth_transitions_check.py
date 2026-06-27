import os


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def read(relative_path):
    with open(os.path.join(ROOT, relative_path), encoding='utf-8') as source:
        return source.read()


def main():
    system_states = read('static/js/system-states.js')
    styles = read('static/css/styles.css')

    for symbol in (
        'beginPageTransition',
        'cancelPageTransition',
        'replaceContent',
        'setContainerBusy',
        'initializePageLifecycle',
        'noTransition',
        'loadingDelay',
        'initializeSessionIdleLogout',
        '/session-timeout',
        '5 * 60 * 1000',
    ):
        assert symbol in system_states

    for selector in (
        'html.syluxent-js.syluxent-page-ready body',
        'html.syluxent-js.syluxent-page-leaving body',
        'html.syluxent-navigation-busy::after',
        '.is-content-replacing',
        '.is-content-entering',
        '@media (prefers-reduced-motion: reduce)',
    ):
        assert selector in styles

    interactive_templates = (
        'dashboard.html', 'landing.html', 'error_interface.html',
        'forgot_password.html', 'admin.html', 'purchase_orders.html',
        'invoices.html', 'login.html', 'register.html', 'logout.html',
        'profile.html', 'evaluation.html', 'analytics.html',
        'reports.html', 'sales_order.html',
    )
    for template_name in interactive_templates:
        template = read(os.path.join('templates', template_name))
        assert 'css/styles.css' in template, template_name
        assert 'js/system-states.js' in template, template_name

    analytics = read('templates/analytics.html')
    assert 'SyluxentUI.replaceContent(contentDiv, html)' in analytics
    assert 'SyluxentUI.setContainerBusy(contentDiv, true)' in analytics
    assert 'location.reload()' not in analytics

    print('Smooth transitions check passed.')


if __name__ == '__main__':
    main()

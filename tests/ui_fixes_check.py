import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import EvaluationSession, Role, User, app, db, init_db  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def add_user(username, role_name):
    role = Role.query.filter_by(role_name=role_name).first()
    if not role:
        role = Role(role_name=role_name, description=f'{role_name} role')
        db.session.add(role)
        db.session.flush()
    user = User(
        username=username,
        email=f'{username}@example.com',
        password_hash=generate_password_hash('pass123'),
        role_id=role.id,
        status='approved',
    )
    db.session.add(user)
    db.session.flush()
    return user


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()

        staff = add_user('ui_staff', 'sales staff')
        manager = add_user('ui_manager', 'manager')
        db.session.commit()

        with app.test_client() as staff_client:
            with staff_client.session_transaction() as session:
                session['user_id'] = staff.id
                session['username'] = staff.username
                session['role'] = 'sales staff'

            questions = staff_client.get('/api/evaluation/questions').get_json()
            assert questions['success'] is True
            assert [item['label'] for item in questions['scale']] == [
                'Strongly Disagree',
                'Disagree',
                'Neutral',
                'Agree',
                'Strongly Agree',
            ]
            assert {item['category'] for item in questions['questions']} == {
                'User Experience',
                'Features',
                'Design',
                'Compatibility',
                'Reliability',
                'Efficiency',
                'Security',
                'Portability',
                'Overall Agreement',
            }
            submit_payload = staff_client.post('/api/evaluation/responses', json={
                'overall_comment': 'Evaluation page works.',
                'responses': [{'question_id': question['id'], 'rating': 5} for question in questions['questions']],
            }).get_json()
            assert submit_payload['success'] is True
            session_record = EvaluationSession.query.first()
            assert session_record.user_id == staff.id
            assert session_record.evaluator_role == 'sales staff'

            missing_page = staff_client.get('/missing-page')
            assert missing_page.status_code == 404
            assert b'system-error-state' in missing_page.data

        with app.test_client() as manager_client:
            with manager_client.session_transaction() as session:
                session['user_id'] = manager.id
                session['username'] = manager.username
                session['role'] = 'manager'

            dashboard_html = manager_client.get('/dashboard').get_data(as_text=True)
            assert "switchTab('clients')" not in dashboard_html
            assert 'id="tab-clients"' not in dashboard_html
            assert 'Generate Report' in dashboard_html
            assert 'View Analytics' in dashboard_html
            assert 'Reporting Workspace' in dashboard_html
            assert 'Cashflow Report' not in dashboard_html
            assert 'Historical Records' not in dashboard_html

            reports_html = manager_client.get('/reports').get_data(as_text=True)
            assert 'report-color-legend' in reports_html
            assert 'value-positive' in reports_html
            assert 'value-negative' in reports_html

    system_states = open(os.path.join(ROOT, 'static', 'js', 'system-states.js'), encoding='utf-8').read()
    assert 'withButtonLoading' in system_states
    assert 'evaluationModalRoot' in system_states
    assert 'href="/evaluation"' in system_states
    assert 'data-evaluation-backdrop' not in system_states
    assert '/static/images/icons/evaluation-icon.png' in system_states
    assert 'class="evaluation-launcher-label">Evaluate System</span>' in system_states
    assert 'aria-label="Evaluate System"' in system_states
    assert 'system-error-state' in system_states
    for theme_name in ('dark', 'light', 'contrast', 'rose', 'ashby'):
        assert f'{theme_name}:' in system_states

    styles = open(os.path.join(ROOT, 'static', 'css', 'styles.css'), encoding='utf-8').read()
    assert '.evaluation-launcher.btn-outline:hover' in styles
    assert '.evaluation-launcher.btn-outline:focus-visible' in styles
    assert 'background: var(--card-bg) !important;' in styles
    assert 'background: var(--accent-muted) !important;' in styles
    assert 'width 180ms ease' in styles
    assert 'box-shadow 180ms ease !important' in styles
    assert 'max-width 180ms ease' in styles
    assert 'opacity 120ms ease' in styles
    assert 'bottom: 74px;' in styles
    assert 'bottom: 132px;' in styles

    deployment_doc = open(os.path.join(ROOT, 'docs', 'deployment.md'), encoding='utf-8').read()
    assert 'GitHub Steps' in deployment_doc
    assert 'Render Steps' in deployment_doc
    assert 'Supabase Steps' in deployment_doc
    assert 'Rollback Plan' in deployment_doc

    print('UI fixes check passed.')


if __name__ == '__main__':
    main()

import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import (  # noqa: E402
    DEFAULT_EVALUATION_QUESTIONS,
    EvaluationQuestion,
    EvaluationResponse,
    EvaluationSession,
    Role,
    User,
    app,
    db,
    init_db,
    likert_interpretation,
)
from werkzeug.security import generate_password_hash  # noqa: E402


def login(client, user):
    with client.session_transaction() as session:
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role.role_name


def main():
    app.config['TESTING'] = True
    with app.app_context():
        db.drop_all()
        db.create_all()
        init_db()
        users = {}
        for role_name in ('admin', 'manager', 'staff', 'sales staff', 'accounting staff'):
            role = Role.query.filter_by(role_name=role_name).first()
            if not role:
                role = Role(role_name=role_name, description=f'{role_name} role')
                db.session.add(role)
                db.session.flush()
            user = User(
                username=role_name.replace(' ', '_'),
                password_hash=generate_password_hash('test123'),
                role_id=role.id,
                status='ACTIVE',
            )
            db.session.add(user)
            users[role_name] = user
        db.session.commit()

        assert len(DEFAULT_EVALUATION_QUESTIONS) == 29
        assert len({category for category, _ in DEFAULT_EVALUATION_QUESTIONS}) == 9
        assert EvaluationQuestion.query.filter_by(is_active=True).count() == 29
        assert likert_interpretation(5) == 'Strongly Agree'
        assert likert_interpretation(4.21) == 'Strongly Agree'
        assert likert_interpretation(3.41) == 'Agree'
        assert likert_interpretation(2.61) == 'Neutral'
        assert likert_interpretation(1.81) == 'Disagree'
        assert likert_interpretation(1) == 'Strongly Disagree'

        with app.test_client() as client:
            anonymous = client.get('/evaluation')
            assert anonymous.status_code in {302, 401}

            for role_name, user in users.items():
                login(client, user)
                page = client.get('/evaluation')
                assert page.status_code == 200
                html = page.get_data(as_text=True)
                assert 'Web App Evaluation Questionnaire' in html
                assert ('Evaluation Results' in html) == (role_name == 'admin')

            login(client, users['staff'])
            questions_payload = client.get('/api/evaluation/questions').get_json()
            assert len(questions_payload['questions']) == 29
            assert [item['value'] for item in questions_payload['scale']] == [1, 2, 3, 4, 5]
            questions = questions_payload['questions']

            incomplete = client.post('/api/evaluation/responses', json={
                'responses': [{'question_id': questions[0]['id'], 'rating': 5}],
            })
            assert incomplete.status_code == 400
            assert EvaluationSession.query.count() == 0

            invalid = client.post('/api/evaluation/responses', json={
                'responses': [
                    {'question_id': question['id'], 'rating': 6}
                    for question in questions
                ],
            })
            assert invalid.status_code == 400
            assert EvaluationSession.query.count() == 0

            valid = client.post('/api/evaluation/responses', json={
                'overall_comment': 'Useful system.',
                'responses': [
                    {'question_id': question['id'], 'rating': 5}
                    for question in questions
                ],
            })
            assert valid.status_code == 200, valid.get_json()
            assert valid.get_json()['overall_mean'] == 5
            assert valid.get_json()['interpretation'] == 'Strongly Agree'
            assert EvaluationSession.query.count() == 1
            assert EvaluationResponse.query.count() == 29

            assert client.get('/api/evaluation/results').status_code == 403
            login(client, users['manager'])
            assert client.get('/api/evaluation/results').status_code == 403
            login(client, users['admin'])
            results = client.get('/api/evaluation/results')
            assert results.status_code == 200
            assert results.get_json()['overall_mean'] == 5

    print('Evaluation interface checks passed.')


if __name__ == '__main__':
    main()

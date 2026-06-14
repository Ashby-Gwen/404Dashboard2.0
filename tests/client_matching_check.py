import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import Client, ClientAlias, Role, SalesOrder, User, app, db, normalize_client_match_key, resolve_client_name  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def seed_clients():
    db.session.add_all([
        Client(client_name='ARIZONA ICE CREAM CORPORATION'),
        Client(client_name='TEAMASTERS INC'),
        Client(client_name='ELEVATED FOOD RECIPE INC'),
    ])
    db.session.commit()


def assert_status(name, expected_statuses, minimum_match=None):
    result = resolve_client_name(name, create_client=False)
    statuses = {expected_statuses} if isinstance(expected_statuses, str) else set(expected_statuses)
    assert result['status'] in statuses, f'{name}: expected {statuses}, got {result}'
    if minimum_match is not None:
        assert result.get('match_percent', 0) >= minimum_match, f'{name}: low match {result}'
    return result


def main():
    app.config['TESTING'] = True

    with app.app_context():
        db.drop_all()
        db.create_all()
        staff_role = Role(role_name='staff', description='Test staff')
        db.session.add(staff_role)
        db.session.flush()
        staff_user = User(
            username='staff',
            password_hash=generate_password_hash('staff123'),
            role_id=staff_role.id,
            status='ACTIVE',
        )
        db.session.add(staff_user)
        db.session.commit()
        seed_clients()

        assert_status(
            'ARIZONA ICE CREAM CORPORATION',
            'resolved',
            100,
        )
        assert_status(
            'TEAMASTERS INC',
            'resolved',
            100,
        )
        assert_status(
            'TEAMAKERS INC',
            'needs_choice',
        )
        assert_status(
            'HEALTHY SHABU SHABU',
            'create_new',
        )

        with app.test_client() as client:
            with client.session_transaction() as session:
                session['user_id'] = staff_user.id
                session['role'] = 'staff'

            exact_response = client.post('/create-client', json={
                'client_name': 'ARIZONA ICE CREAM CORPORATION',
            })
            assert exact_response.status_code == 200
            assert exact_response.get_json()['message'] == 'Existing client matched successfully'

            new_response = client.post('/create-client', json={
                'client_name': 'BRAND NEW COMPANY',
            })
            assert new_response.status_code == 200
            assert new_response.get_json()['message'] == 'Client created successfully'

            similar_response = client.post('/create-client', json={
                'client_name': 'TEAMAKERS INC',
            })
            assert similar_response.status_code == 409
            similar_payload = similar_response.get_json()
            assert similar_payload['needs_resolution'] is True
            resolution = similar_payload['client_resolution']

            preview_response = client.post('/client-match-preview', json={
                'client_names': [
                    'TEAMAKERS INC',
                    'TEAMAKERS INC',
                    'XYZ GLOBAL INC',
                    'ARIZONA ICE CREAM CORPORATION',
                ]
            })
            assert preview_response.status_code == 200
            preview_payload = preview_response.get_json()
            assert preview_payload['total_unique_clients'] == 3
            assert preview_payload['review_count'] == 2

            suggested_response = client.post('/create-client', json={
                'client_name': 'TEAMAKERS INC',
                'resolutions': {
                    resolution['resolution_key']: {
                        'action': 'use_suggested',
                        'client_id': resolution['suggested_client_id'],
                        'client_name': resolution['suggested_client_name'],
                        'match_percent': resolution['match_percent'],
                    }
                }
            })
            assert suggested_response.status_code == 200
            assert suggested_response.get_json()['message'] == 'Existing client matched successfully'
            learned = ClientAlias.query.filter_by(
                normalized_alias=normalize_client_match_key('TEAMAKERS INC')
            ).first()
            assert learned is not None

            alias_response = client.post('/create-client', json={
                'client_name': 'TEAMAKERS INC',
            })
            assert alias_response.status_code == 200
            assert alias_response.get_json()['message'] == 'Existing client matched successfully'

            create_new_response = client.post('/create-client', json={
                'client_name': 'TEAMASTERS NORTH',
                'resolutions': {
                    normalize_client_match_key('TEAMASTERS NORTH'): {
                        'action': 'create_new',
                        'client_name': '',
                        'match_percent': 0,
                    }
                }
            })
            assert create_new_response.status_code == 200
            assert create_new_response.get_json()['message'] == 'Client created successfully'

            order_response = client.post('/create-sales-order', json={
                'company_name': 'ARIZONA ICE CREAM CORPORATION',
                'store_name': 'COLDSTONE',
                'store_branch': 'NO BRANCH',
                'order_date': '2026-06-04',
                'sales_staff': 'staff',
                'total_amount': 100,
                'items': [
                    {
                        'particular': 'TEST ITEM',
                        'quantity': 1,
                        'unit_cost': 50,
                        'selling_price': 100,
                        'total': 100,
                    }
                ],
            })
            assert order_response.status_code == 200
            assert order_response.get_json()['message'] == 'Sales order created successfully'
            order = SalesOrder.query.order_by(SalesOrder.id.desc()).first()
            assert order.company_name == 'ARIZONA ICE CREAM CORPORATION'
            assert order.official_client_name == 'ARIZONA ICE CREAM CORPORATION'
            assert order.store_name == 'COLDSTONE'
            assert order.store_branch == 'NO BRANCH'
            assert 'COLDSTONE' not in order.company_name
            assert 'NO BRANCH' not in order.company_name

    print('Client matching check passed.')


if __name__ == '__main__':
    main()

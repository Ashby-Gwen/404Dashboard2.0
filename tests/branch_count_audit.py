import argparse
import csv
import os
import sys
from collections import defaultdict
from datetime import datetime


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analytics_services import _branch_group_key, _display_text, _store_group_key  # noqa: E402
from app import SalesOrder, app, db  # noqa: E402


def order_store_name(order):
    client_name = order.client.client_name if order.client else ''
    return _display_text(order.store_name or order.company_name or client_name or 'Unspecified Store').upper()


def parse_date(value):
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


def audit_store(search_text, year=None, start_date=None, end_date=None):
    search_key = _store_group_key(search_text)
    query = SalesOrder.query
    if year:
        query = query.filter(
            SalesOrder.order_date >= f'{year}-01-01',
            SalesOrder.order_date < f'{year + 1}-01-01',
        )
    else:
        if start_date:
            query = query.filter(SalesOrder.order_date >= start_date)
        if end_date:
            query = query.filter(SalesOrder.order_date <= end_date)

    matching_orders = [
        order for order in query.order_by(SalesOrder.order_date.asc(), SalesOrder.id.asc()).all()
        if search_key in _store_group_key(order_store_name(order))
    ]

    branch_groups = defaultdict(list)
    excluded_orders = []
    for order in matching_orders:
        branch_key = _branch_group_key(order.store_branch)
        if branch_key:
            branch_groups[branch_key].append(order)
        else:
            excluded_orders.append(order)

    return matching_orders, branch_groups, excluded_orders


def print_summary(search_text, period_label, matching_orders, branch_groups, excluded_orders):
    store_names = sorted({order_store_name(order) for order in matching_orders})
    print(f'Search: {search_text}')
    print(f'Period: {period_label}')
    print(f'Matching Sales Orders: {len(matching_orders)}')
    print(f'Unique Valid Branches: {len(branch_groups)}')
    print(f'Excluded Blank/Placeholder Orders: {len(excluded_orders)}')
    print(f'Matched Store Names: {", ".join(store_names) or "None"}')
    print()

    for index, (branch_key, orders) in enumerate(sorted(branch_groups.items()), start=1):
        raw_values = sorted({_display_text(order.store_branch) for order in orders})
        print(f'{index:03d}. {branch_key} ({len(orders)} order(s))')
        print(f'     Raw values: {", ".join(raw_values)}')
        for order in orders:
            client_name = order.client.client_name if order.client else ''
            print(
                f'     SO={order.so_number} Date={order.order_date} '
                f'Store={order_store_name(order)} Company={order.company_name or ""} '
                f'Client={client_name}'
            )

    if excluded_orders:
        print()
        print('Excluded blank or placeholder branch values:')
        for order in excluded_orders:
            print(
                f'  SO={order.so_number} Date={order.order_date} '
                f'RawBranch={order.store_branch!r} Store={order_store_name(order)}'
            )


def export_csv(path, matching_orders):
    with open(path, 'w', newline='', encoding='utf-8-sig') as output:
        writer = csv.DictWriter(output, fieldnames=[
            'sales_order_id',
            'so_number',
            'order_date',
            'raw_store_name',
            'normalized_store_name',
            'raw_branch',
            'normalized_branch',
            'branch_included',
            'company_name',
            'client_name',
        ])
        writer.writeheader()
        for order in matching_orders:
            branch_key = _branch_group_key(order.store_branch)
            writer.writerow({
                'sales_order_id': order.id,
                'so_number': order.so_number,
                'order_date': order.order_date.isoformat() if order.order_date else '',
                'raw_store_name': order.store_name or '',
                'normalized_store_name': _store_group_key(order_store_name(order)),
                'raw_branch': order.store_branch or '',
                'normalized_branch': branch_key,
                'branch_included': 'YES' if branch_key else 'NO',
                'company_name': order.company_name or '',
                'client_name': order.client.client_name if order.client else '',
            })


def main():
    parser = argparse.ArgumentParser(
        description='Read-only audit of the Sales Orders counted as branches for a Store Name.'
    )
    parser.add_argument('store', help='Store name or part of its normalized name, such as "Goncha".')
    parser.add_argument('--year', type=int, help='Limit the audit to one calendar year.')
    parser.add_argument('--start-date', help='Optional inclusive start date in YYYY-MM-DD format.')
    parser.add_argument('--end-date', help='Optional inclusive end date in YYYY-MM-DD format.')
    parser.add_argument('--csv', dest='csv_path', help='Optional CSV output path.')
    args = parser.parse_args()

    with app.app_context():
        host = db.engine.url.host
        if host not in (None, '', 'localhost', '127.0.0.1', '::1'):
            raise SystemExit(
                f'Refusing to audit non-local database host: {host}. '
                'Point DATABASE_URL to a local database first.'
            )
        start_date = parse_date(args.start_date)
        end_date = parse_date(args.end_date)
        matching_orders, branch_groups, excluded_orders = audit_store(
            args.store,
            args.year,
            start_date,
            end_date,
        )
        period_label = (
            str(args.year)
            if args.year
            else f'{args.start_date or "beginning"} to {args.end_date or "latest"}'
        )
        print_summary(
            args.store,
            period_label,
            matching_orders,
            branch_groups,
            excluded_orders,
        )
        if args.csv_path:
            export_csv(args.csv_path, matching_orders)
            print()
            print(f'CSV written to: {os.path.abspath(args.csv_path)}')


if __name__ == '__main__':
    main()

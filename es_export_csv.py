import argparse
import csv
from getpass import getpass, getuser
from datetime import datetime, timedelta

from elasticsearch import Elasticsearch


def grab(args):
    """
    Find index pattern, iterate through documents, collecting entries. If
    fields is set we will narrow our results to only include the specified
    fields. Otherwise, all fields will be returned, using the first document
    to determine the fields.
    """

    # Setup client
    username = args.username
    password = args.password
    if not args.password:
        password = getpass()
    auth = (username, password)

    es = Elasticsearch(
        args.host,
        use_ssl='https' in args.host,
        verify_certs=True,
        http_auth=auth
    )

    if not es.ping():
        raise SystemExit('Cannot authenticate!')

    query_string = args.query

    # Build query
    query = {
        'query': {
            'bool': {
                'must': [
                    {
                        'range': {
                            '@timestamp': {
                                'gte': args.range_from,
                                'lte': args.range_to
                            }
                        }
                    }
                ]
            }
        }
    }

    if query_string:
        query['query']['bool']['must'].append({
            'query_string': {
                'query': query_string
            }
        })
    else:
        query['query']['bool']['must'].append({'match_all': {}})

    # Search for records
    kwargs = {}
    kwargs['index'] = args.index
    kwargs['size'] = int(args.total)
    kwargs['body'] = query
    if args.fields:
        kwargs['_source_include'] = args.fields
    results = es.search(**kwargs)

    def flatten(d, path=None):
        """
        Returns list of fields and their path recursively separated by dot
        notation.
        """
        l = []
        path = path or []
        for key, value in d.items():
            if isinstance(value, dict):
                for item in flatten(value, [*path, key]):
                    l.append(item)
            else:
                if isinstance(value, list):
                    l.append(('.'.join([*path, key]), ','.join(value)))
                else:
                    l.append(('.'.join([*path, key]), value))

        return l

    if results['hits']['total'] == 0:
        raise SystemExit('Query returned no results')

    # Flatten all records to dot notation
    records = []
    for hit in results['hits']['hits']:
        if args.only_source:
            records.append(dict(flatten(hit['_source'])))
        else:
            records.append(dict(flatten(hit)))

    # Setup CSV field names
    field_names = set()
    for item in records:
        for key in item.keys():
            field_names.add(key)

    # Save as CSV
    with open(args.output, 'w') as f:
        writer = csv.DictWriter(f, sorted(field_names), extrasaction='ignore')
        if not args.no_header:
            writer.writeheader()
        writer.writerows(records)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('index', help='index to export')
    parser.add_argument('fields', nargs='*', help='limit output to fields (if set) or return all fields')
    parser.add_argument('-q', '--query', default=None, help='query_string to submit, empty (return everything) by default')
    parser.add_argument('-t', '--total', default=500, help='max docs to return')
    parser.add_argument('-e', '--host', default='localhost:9200', help='cluster API')
    parser.add_argument('--from', dest='range_from', default='now-1d/d', help='range start')
    parser.add_argument('--to', dest='range_to', default='now/d', help='range end')
    parser.add_argument('-o', '--output', default='results.csv', help='output file')
    parser.add_argument('--only-source', action='store_false', default=True, help='only return source fields; exclude metadata fields')
    parser.add_argument('--no-header', action='store_true', default=False, help='do not write csv header')
    parser.add_argument('-u', '--username', default=getuser(), help='basic auth username')
    parser.add_argument('-p', '--password', help='basic auth password')
    args = parser.parse_args()
    grab(args)


if __name__ == '__main__':
    main()

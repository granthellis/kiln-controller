#!/usr/bin/env python3
"""Move the built-in candle out of stored schedules (docs/candle-and-peak-holds.md).

A schedule that starts at ambient, ramps to 90-130 C, holds, and then fires is
rewritten to its body (starting at [0, T]) plus "candle": true; the controller
then prepends the candle at run time. Everything else is left alone.

    tools/migrate_candle.py [--dir storage/profiles]            # dry run
    tools/migrate_candle.py [--dir storage/profiles] --apply    # rewrite files
    tools/migrate_candle.py --json                              # machine summary

The summary lists each converted schedule's old candle length in seconds:
Home Assistant needs it to cut the old candle out of what it has learned.
"""
import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'lib'))

from holds import split_candle  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--dir', default=os.path.join(ROOT, 'storage', 'profiles'))
    ap.add_argument('--apply', action='store_true', help='rewrite the files')
    ap.add_argument('--json', action='store_true', help='print a JSON summary')
    args = ap.parse_args()

    converted, skipped = {}, []
    for filename in sorted(os.listdir(args.dir)):
        if not filename.endswith('.json'):
            continue
        path = os.path.join(args.dir, filename)
        with open(path) as f:
            obj = json.load(f)
        new, old_candle_s = split_candle(obj)
        if new is None:
            skipped.append(obj.get('name', filename))
            continue
        converted[obj['name']] = {'old_candle_s': old_candle_s,
                                  'candle_temp': new['data'][0][1],
                                  'old_data': sorted(obj['data'])[:3],
                                  'body_head': new['data'][:2]}
        if args.apply:
            tmp = path + '.tmp'
            with open(tmp, 'w') as f:
                json.dump(new, f)
            os.replace(tmp, path)

    if args.json:
        print(json.dumps({'applied': args.apply, 'converted': converted,
                          'skipped': skipped}, indent=1))
        return
    verb = 'converted' if args.apply else 'would convert'
    for name, c in converted.items():
        print('%s %-45s candle %5d s at %s C  %s -> %s' % (
            verb, name, c['old_candle_s'], c['candle_temp'], c['old_data'], c['body_head']))
    print('left alone (%d): %s' % (len(skipped), ', '.join(skipped)))
    if not args.apply:
        print('dry run - nothing written; rerun with --apply')


if __name__ == '__main__':
    main()

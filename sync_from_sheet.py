#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pull the 行程時間表 tab BACK into index.html (the reverse of sync_sheet.py).

Mocha edits the timetable in the Sheet (easier to read than the giant DATA
literal), then runs this to push it down into index.html.

    dry run :  python3 sync_from_sheet.py
    apply   :  python3 sync_from_sheet.py --apply

It only ever touches days[].route / days[].slots[].text / days[].stay.
places[] and notes[] are NOT in this tab and are left alone.

A blank cell is treated as a mistake, not as "delete this" — the run aborts and
names the cells. Pass --allow-blank if you really mean to empty them.

⚠️ Direction matters: this and sync_sheet.py overwrite each other. Edit in ONE
place, sync, then carry on. Never edit both and hope.

Auth is identical to sync_sheet.py — see its docstring for the dead ends.
"""
import json
import os
import sys

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

SHEET = '1HVN5GNsVmnhzPZCARpT-5TJa9d7Wtcbh-qBAbg5y6GQ'
SA = 'koreatrip@project-930c0e6c-0dac-4179-8d0.iam.gserviceaccount.com'
SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'index.html')
TAB = '行程時間表'


def read_tab():
    source, _ = google.auth.default()
    cred = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=SA,
        target_scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sess = AuthorizedSession(cred)
    r = sess.get('https://sheets.googleapis.com/v4/spreadsheets/%s/values/%s!A1:G9'
                 % (SHEET, TAB))
    r.raise_for_status()
    return r.json().get('values', [])


def main():
    apply_ = '--apply' in sys.argv
    allow_blank = '--allow-blank' in sys.argv

    html = open(SRC, encoding='utf-8').read()
    at = html.find('const DATA=') + len('const DATA=')
    D, end = json.JSONDecoder().raw_decode(html[at:])
    days = D['days']

    rows = read_tab()
    if len(rows) < 9:
        sys.exit('%s has %d rows, expected 9 — did the layout change?'
                 % (TAB, len(rows)))
    # Sheets truncates trailing empties; pad every row to 7 columns.
    rows = [list(r) + [''] * (7 - len(r)) for r in rows]

    labels = [r[0].strip() for r in rows]
    if labels[2] != '路線' or labels[8] != '今晚住邊':
        sys.exit('row labels moved (got %r) — fix the tab, not this script' % labels)
    want = [sl['label'] for sl in days[0]['slots']]
    if labels[3:8] != want:
        sys.exit('slot rows are %r, index.html expects %r' % (labels[3:8], want))

    # Collect every change first, so a blank cell aborts before anything is written.
    edits, blanks = [], []
    for col, day in enumerate(days, start=1):
        def take(ridx, field, cur):
            new = rows[ridx][col].replace('\r\n', '\n').rstrip()
            cell = '%s%d' % (chr(ord('A') + col), ridx + 1)
            if not new.strip():
                if cur.strip():
                    blanks.append('%s (%s %s)' % (cell, day['date'], field))
                return
            if new != cur:
                edits.append((day, field, cell, cur, new))

        take(2, '路線', day['route'])
        for n, sl in enumerate(day['slots']):
            take(3 + n, sl['label'], sl['text'])
        take(8, '住宿', day['stay'])

    if blanks and not allow_blank:
        print('⛔ blank cells that would wipe existing text:')
        for b in blanks:
            print('   ', b)
        sys.exit('\nnothing written. fill them in, or re-run with --allow-blank')

    if not edits:
        print('no differences — index.html already matches %s' % TAB)
        return

    print('%d change%s%s\n' % (len(edits), '' if len(edits) == 1 else 's',
                               '' if apply_ else ' (dry run)'))
    for day, field, cell, cur, new in edits:
        print('  %s  %s %s' % (cell, day['date'], field))
        print('    - %d chars: %s' % (len(cur), cur[:70].replace('\n', ' ⏎ ')))
        print('    + %d chars: %s' % (len(new), new[:70].replace('\n', ' ⏎ ')))
    if not apply_:
        print('\ndry run — re-run with --apply to write index.html')
        return

    for day, field, cell, cur, new in edits:
        if field == '路線':
            day['route'] = new
        elif field == '住宿':
            day['stay'] = new
        else:
            [sl for sl in day['slots'] if sl['label'] == field][0]['text'] = new

    open(SRC, 'w', encoding='utf-8').write(
        html[:at] + json.dumps(D, ensure_ascii=False) + html[at + end:])
    print('\n✅ index.html updated. Commit it, then push.')


if __name__ == '__main__':
    main()

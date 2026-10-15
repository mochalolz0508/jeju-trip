#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Rebuild the 4 GENERATED tabs of the Jeju Google Sheet from index.html.

index.html is the SOURCE OF TRUTH. The sheet is a read-only-ish mirror of it,
except for five tabs that are maintained by hand and must never be touched.

    Usage:  /Users/mochakam/.pyenv/versions/3.10.13/bin/python3 sync_sheet.py

Auth (the only path that works — see the notes below):
  * ADC must be a Google account that holds roles/iam.serviceAccountTokenCreator
    on the SA below.  `gcloud auth application-default login` once is enough.
  * The SA is then impersonated for the spreadsheets scope.  Do NOT try
    `gcloud auth application-default login --scopes=...spreadsheets` (blocked
    globally for the gcloud client) and do NOT try to create an SA JSON key
    (blocked by org policy iam.disableServiceAccountKeyCreation).
  * `gcloud auth print-access-token --impersonate-service-account=... --scopes=`
    silently IGNORES --scopes and yields 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT on
    write.  A successful READ proves nothing: the sheet is published to web.
  * Needs google-api-python-client + google-auth (present in pyenv 3.10.13).
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
CHECKED = '2026/10/15'

# Rebuilt from index.html every run.
GENERATED = ['行程時間表', '必去必食與備註', '餐廳營業核對', '景點地址']
# Hand-maintained by Mocha. NEVER write to these.
PROTECTED = ['住宿', '費用', '預約清單', '行前準備', 'Ava bookmark']


def load_data():
    """Pull the `const DATA={...}` literal out of index.html."""
    html = open(SRC, encoding='utf-8').read()
    start = html.find('const DATA=') + len('const DATA=')
    data, _ = json.JSONDecoder().raw_decode(html[start:])
    return data


def build(D):
    days = D['days']
    places = {p['id']: p for p in D['places']}

    hdr = {'10.30': '10/30（五）', '10.31': '10/31（六）', '11.01': '11/01（日）',
           '11.02': '11/02（一）', '11.03': '11/03（二）', '11.04': '11/04（三）'}

    def slot(d, label):
        for sl in d['slots']:
            if sl['label'] == label:
                return sl['text']
        return ''

    timetable = [
        ['', '6 日 5 夜｜2026 濟州自駕（由 index.html 生成・%s）' % CHECKED],
        ['時段'] + [hdr[d['date']] for d in days],
        ['路線'] + [d['route'] for d in days],
    ]
    for label in ['上午', '午餐', '下午', '晚餐', '晚上']:
        timetable.append([label] + [slot(d, label) for d in days])
    timetable.append(['今晚住邊'] + [d['stay'] for d in days])

    notes = [['項目', '安排／狀態', '原因與待確認', '來源']]
    notes += [list(r) for r in D['notes']]

    # Chronological: walk the days, then append anything unscheduled (備選／已剪).
    order, seen = [], set()
    for d in days:
        for pid in d['places']:
            if pid in places and pid not in seen:
                seen.add(pid)
                order.append(pid)
    order += [p['id'] for p in D['places'] if p['id'] not in seen]

    food = [['日期／安排', '餐廳／韓文導航名', '地址（韓國濟州）', '公開營業時間',
             '休息／午休／最後落單', '日期核對（非指定日保證）', '電話', '來源', '查核日']]
    spots = [['日期／安排', '景點／導航名', '地址（韓國濟州）', '公開時間',
              '休息／注意', '備註', '來源', '查核日']]
    for pid in order:
        p = places[pid]
        row = [p['when'], p['name'], p['address'], p['hours'], p['rest'], p['note']]
        if p['kind'] == '餐廳':
            food.append(row + [p['phone'], p['sources'], CHECKED])
        else:
            spots.append(row + [p['sources'], CHECKED])

    return timetable, notes, food, spots


def main():
    D = load_data()
    timetable, notes, food, spots = build(D)

    source, _ = google.auth.default()
    cred = impersonated_credentials.Credentials(
        source_credentials=source, target_principal=SA,
        target_scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sess = AuthorizedSession(cred)
    base = 'https://sheets.googleapis.com/v4/spreadsheets/' + SHEET

    live = [x['properties']['title'] for x in
            sess.get(base + '?fields=sheets(properties(title))').json()['sheets']]
    missing = set(GENERATED) - set(live)
    if missing:
        sys.exit('generated tab missing from sheet: %s' % sorted(missing))
    print('rewriting     :', GENERATED)
    print('left untouched:', [t for t in live if t not in GENERATED])

    clear = ['行程時間表!A1:H50', '必去必食與備註!A1:D60',
             '餐廳營業核對!A1:I60', '景點地址!A1:H60']
    sess.post(base + '/values:batchClear', json={'ranges': clear}).raise_for_status()

    r = sess.post(base + '/values:batchUpdate', json={
        'valueInputOption': 'RAW',
        'data': [
            {'range': '行程時間表!A1', 'values': timetable},
            {'range': '必去必食與備註!A1', 'values': notes},
            {'range': '餐廳營業核對!A1', 'values': food},
            {'range': '景點地址!A1', 'values': spots},
        ]})
    r.raise_for_status()
    for u in r.json()['responses']:
        print('   %-22s %s rows x %s cols'
              % (u['updatedRange'], u['updatedRows'], u['updatedColumns']))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""把一份 CRD xlsx 解析成 MSPN–QPN Mapping 工具的 imports 文件（與頁面 parseCRD／analyze 規則相同）。

用法：
  python3 -I crd_import.py <CRD.xlsx> --name "XIO Gen10.3" --project "S21A1 XIO Gen10.3/T6YA" \
      [--doc M1441179 --rev E --ver 0.05] [--known known.json] [--out imports.json]

--known：既有 mapping 的 JSON（{"pairs":[["MSPN","QPN"],...]}）；用來判斷哪些組合是新的。
        沒給就視為全部都是新組合（狀態 new）。
輸出：imports.json = {"docs":[{doc_id, data}], "summary":{...}}，每個 data 的 shape 跟頁面寫入 DB 的一樣。
"""
import argparse, json, re, sys, time, os
from collections import OrderedDict

MSP_RE = re.compile(r'M\d{7}-\d{3}')
QPN_RE = re.compile(r'^[A-Z0-9^]{11}$')
LIM = 170000

def cl(v):
    if v is None: return ''
    if isinstance(v, float) and v.is_integer(): v = int(v)
    return str(v).strip()

def norm(s): return re.sub(r'\s+', '', str(s or '')).upper()

def level_of(n):
    n = n.strip()
    if n.startswith('HW Config'): return 'HW Config'
    if 'Cable' in n: return 'Cable QPN'
    if 'L11' in n: return 'L11 Rack'
    if 'Utility' in n: return 'L10 Utility'
    if 'JBOD' in n: return 'L10 JBOD'
    if 'Node' in n: return 'L10 Node'
    return n

def sheet_rows(ws):
    out = []
    for row in ws.iter_rows(values_only=True):
        out.append([cl(c) for c in row])
    return out

def parse_crd(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    names = wb.sheetnames
    use = [n for n in names if n.strip() != 'Bom Report' and not re.match(r'^(L11|Node|Utility|JBOD|Rack)_M\d{7}-\d{3}', n.strip(), re.I)]
    cover = next((n for n in names if re.match(r'^cover', n.strip(), re.I)), None)
    if cover and cover not in use: use.append(cover)
    rows, sheets, meta = [], [], {}
    for sh in use:
        ws = wb[sh]
        d = sheet_rows(ws)
        if sh == cover:
            for r in d:
                vv = [x for x in r if x]
                lab = vv[0] if vv else ''
                val = vv[1] if len(vv) > 1 else ''
                if re.match(r'^Document', lab, re.I) and re.search(r'M\d{7}', val): meta['doc'] = re.search(r'M\d{7}', val).group(0)
                elif re.match(r'^Revision', lab, re.I) and val: meta['rev'] = val
                elif re.match(r'^Version', lab, re.I) and val: meta['ver'] = val
            continue
        h, hv = -1, None
        for i in range(min(len(d), 80)):
            v = d[i]
            if 'QPN' in v and any(re.match(r'^MSFT ?PN$', a) for a in v):
                h, hv = i, v; break
        if h < 0: continue
        cq = hv.index('QPN'); cm = next(j for j, a in enumerate(hv) if re.match(r'^MSFT ?PN$', a))
        cg = hv.index('Group') if 'Group' in hv else 1
        ci = hv.index('Item') if 'Item' in hv else (hv.index('Description') if 'Description' in hv else -1)
        cn = [j for j, a in enumerate(hv) if a.startswith('Note')]
        grp, cnt = None, 0
        for i in range(h + 1, len(d)):
            v = d[i]
            g = lambda k: v[k] if 0 <= k < len(v) else ''
            if g(cq) == 'QPN': continue
            if g(cg): grp = g(cg)
            qraw, mraw = g(cq).upper(), g(cm).upper()
            if not qraw and not mraw: continue
            qs = [re.sub(r'\s', '', q) for q in re.split(r'[/\n,]', qraw) if q.strip()]
            ms = MSP_RE.findall(mraw)
            note = ' | '.join(x for x in (g(j).replace('\n', ' ') for j in cn) if x)
            base = dict(level=level_of(sh), group=grp or '', item=g(ci) if ci >= 0 else '', alt=('Alt.' in v), note=note)
            if not ms: ms = ['']
            if not qs: qs = ['']
            if len(ms) == len(qs): combos = list(zip(ms, qs))
            elif len(ms) == 1: combos = [(ms[0], q) for q in qs]
            elif len(qs) == 1: combos = [(m, qs[0]) for m in ms]
            else:
                combos = [(m, q) for m in ms for q in qs]; base['note'] += ' [多對多拆解]'
            for m, q in combos:
                rows.append(dict(base, mspn=m, qpn=q, qvalid=bool(QPN_RE.match(q)))); cnt += 1
        sheets.append(f'{sh.strip()}（{cnt}）')
    return dict(rows=rows, sheets=sheets, meta=meta)

def analyze(rows, known_pairs, known_m, known_q):
    has = {r['qpn'] for r in rows if r['mspn']}
    rows = [r for r in rows if not (r['mspn'] == '' and r['qpn'] in has) and not (r['mspn'] == '' and r['qpn'] == '')]
    def st(r):
        if not r['mspn'] and not r['qvalid']: return 'invalid'
        if not r['mspn']: return 'no_mspn'
        if not r['qvalid']: return 'no_qpn'
        if (r['mspn'], r['qpn']) in known_pairs: return 'exists'
        hm, hq = r['mspn'] in known_m, r['qpn'] in known_q
        return 'new_both_known' if hm and hq else 'new_qpn_for_mspn' if hm else 'new_mspn_for_qpn' if hq else 'new'
    for r in rows: r['status'] = st(r)
    rows = [r for r in rows if r['status'] != 'invalid']
    qm = {}
    for r in rows:
        if r['mspn'] and r['qvalid']: qm.setdefault(r['qpn'], set()).add(r['mspn'])
    multi = {q for q, s in qm.items() if len(s) > 1}
    np = OrderedDict()
    for r in rows:
        if not r['status'].startswith('new'): continue
        k = (r['mspn'], r['qpn'])
        p = np.get(k)
        if not p:
            p = dict(m=r['mspn'], q=r['qpn'], status=r['status'], levels=[], groups=[], items=[],
                     warn=r['status'] in ('new_mspn_for_qpn', 'new_both_known') or r['qpn'] in multi)
            np[k] = p
        if r['level'] not in p['levels']: p['levels'].append(r['level'])
        if r['group'] and r['group'] not in p['groups']: p['groups'].append(r['group'])
        if r['item'] and not p['items']: p['items'].append(r['item'])
    lst = list(np.values())
    for p in lst: p['sel'] = not p['warn']
    return dict(rows=rows, list=lst, multi=sorted(multi))

def guess_meta(fn):
    doc = (re.search(r'M\d{7}', fn) or [''])[0] if re.search(r'M\d{7}', fn) else ''
    rev = (re.search(r'Rev([A-Za-z]+)', fn).group(1).upper() if re.search(r'Rev([A-Za-z]+)', fn) else '')
    ver = (re.search(r'[._]v(\d+(?:\.\d+)?)', fn, re.I).group(1) if re.search(r'[._]v(\d+(?:\.\d+)?)', fn, re.I) else '')
    g = re.search(r'GEN\s?(\d+\.\d+)', fn, re.I); t = re.search(r'XIO|XSTORE', fn, re.I)
    name = (('XIO' if re.match(r'xio', t.group(0), re.I) else 'Xstore') + ' Gen' + g.group(1)) if g and t else re.sub(r'\.[^.]+$', '', fn)
    return dict(doc=doc, rev=rev, ver=ver, name=name)

def build_docs(res, an, meta, selected=None):
    sel = [p for p in an['list'] if (p['sel'] if selected is None else ((p['m'], p['q']) in selected))]
    selK = {(p['m'], p['q']) for p in sel}
    warnK = {(p['m'], p['q']) for p in an['list'] if p['warn']}
    remark = lambda p: f"{meta['name']} CRD {meta['doc']}{' Rev' + meta['rev'] if meta['rev'] else ''} {' / '.join(p['levels'])}"
    map_rows = [[p['m'], p['q'], remark(p), meta['project'], meta['date']] for p in sel]
    seen, crd_rows = set(), []
    for r in an['rows']:
        k = (r['mspn'], r['qpn'])
        if r['status'] == 'exists': s = 'orig'
        elif r['status'].startswith('new'): s = ('b4' + ('w' if k in warnK else '')) if k in selK else 'skip'
        else: s = r['status']
        row = [r['level'], r['group'], r['item'], r['mspn'], r['qpn'], s, 1 if r['alt'] else 0, r['note']]
        dkc = '|'.join(map(str, row[:6]))
        if dkc in seen: continue
        seen.add(dkc); crd_rows.append(row)
    imp = re.sub(r'[^A-Za-z0-9_-]', '', f"{meta['doc']}_{meta['rev'] or 'x'}_{meta['ver'] or 'x'}") + '_' + format(int(time.time() * 1000), 'x')[-8:]
    base = dict(imp=imp, name=meta['name'], doc=meta['doc'], rev=meta['rev'], ver=meta['ver'], project=meta['project'], date=meta['date'], at=int(time.time() * 1000), by=None, file=meta['file'])
    parts = [dict(map=[], crd=[])]; sz = 0
    def add(kind, row):
        nonlocal sz
        n = len(json.dumps(row, ensure_ascii=False).encode()) + 2
        if sz + n > LIM and (len(parts[-1]['map']) + len(parts[-1]['crd'])) > 0:
            parts.append(dict(map=[], crd=[])); sz = 0
        parts[-1][kind].append(row); sz += n
    for r in map_rows: add('map', r)
    for r in crd_rows: add('crd', r)
    docs = [dict(doc_id=f'{imp}~{i}', data=dict(base, part=i, parts=len(parts), map=p['map'], crd=p['crd'])) for i, p in enumerate(parts)]
    return docs, map_rows, crd_rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('xlsx'); ap.add_argument('--name'); ap.add_argument('--project', default='')
    ap.add_argument('--doc'); ap.add_argument('--rev'); ap.add_argument('--ver'); ap.add_argument('--date')
    ap.add_argument('--known'); ap.add_argument('--out', default='imports.json'); ap.add_argument('--dump-rows')
    a = ap.parse_args()
    res = parse_crd(a.xlsx)
    gm = guess_meta(os.path.basename(a.xlsx)); cm = res['meta']
    meta = dict(name=a.name or gm['name'], doc=a.doc or cm.get('doc') or gm['doc'], rev=a.rev or cm.get('rev') or gm['rev'],
                ver=a.ver or cm.get('ver') or gm['ver'], project=a.project, date=a.date or time.strftime('%Y/%-m/%-d'), file=os.path.basename(a.xlsx))
    known_pairs, known_m, known_q = set(), set(), set()
    if a.known:
        k = json.load(open(a.known, encoding='utf-8'))
        for m, q in k.get('pairs', []):
            known_pairs.add((norm(m), norm(q))); known_m.add(norm(m)); known_q.add(norm(q))
    an = analyze(res['rows'], known_pairs, known_m, known_q)
    if a.dump_rows:
        json.dump(dict(rows=res['rows'], sheets=res['sheets'], meta=res['meta']), open(a.dump_rows, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    docs, map_rows, crd_rows = build_docs(res, an, meta)
    summary = dict(meta=meta, sheets=res['sheets'], rows=len(an['rows']), new=len(map_rows), warn=[p for p in an['list'] if p['warn']],
                   multi=an['multi'], no_qpn=sum(1 for r in an['rows'] if r['status'] == 'no_qpn'), no_mspn=sum(1 for r in an['rows'] if r['status'] == 'no_mspn'), crd=len(crd_rows), parts=len(docs))
    json.dump(dict(docs=docs, summary=summary, candidates=an['list']), open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"{meta['name']} {meta['doc']} Rev{meta['rev']} v{meta['ver']}：有效列 {summary['rows']}、新增 mapping {summary['new']}（⚠ {len(summary['warn'])} 筆預設不勾）、QPN TBD {summary['no_qpn']}、無 MSPN {summary['no_mspn']}、CRD 列 {summary['crd']}、分 {summary['parts']} 份 → {a.out}")

if __name__ == '__main__':
    main()

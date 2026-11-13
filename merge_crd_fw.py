#!/usr/bin/env python3
import re, copy, argparse, collections, warnings
import openpyxl
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
warnings.filterwarnings("ignore")
YELLOW = PatternFill("solid", fgColor="FFFFFF00")

def norm(s): return re.sub(r"\s+", "", str(s or "")).lower()

def find_header(ws):
    for r in range(1, 15):
        if norm(ws.cell(r, 1).value) == "group":
            cols = {}
            for c in range(1, ws.max_column + 1):
                n = norm(ws.cell(r, c).value)
                if n: cols[n] = c
            return r, cols
    raise SystemExit(f"找不到表頭列（A欄=Group）：{ws.title}")

def colmap(cols):
    g = lambda *ks: next((cols[k] for k in ks if k in cols), None)
    return dict(group=g("group"), comp=g("componentgroup"), loc=g("location"),
                item=g("item"), model=g("model"), manu=g("manufacturer"),
                mpn=g("mpn"), mspn=g("mspn"), fw=g("fwversion"),
                vrc=g("vrcid"), chk=g("checksum"), path=g("fwcentralpaths"))

def pick_sheets(wb, want_vrc):
    for ws in wb.worksheets:
        if "fw-sw" not in ws.title.lower() and "fwsw" not in norm(ws.title): continue
        try: h, cols = find_header(ws)
        except SystemExit: continue
        if (("vrcid" in cols) == want_vrc): return ws
    return None

def read_rows(ws):
    h, cols = find_header(ws); m = colmap(cols)
    rows, fru, g = [], [], None
    comp = loc = None
    for r in range(h + 1, ws.max_row + 1):
        v = lambda k: ws.cell(r, m[k]).value if m.get(k) else None
        if v("group"):
            ng = str(v("group")).strip()
            if ng != g: comp = loc = None
            g = ng
        if g == "Group": g = "FRU"   # FRU table's own header row
        if v("comp"): comp = v("comp")
        if v("loc"): loc = v("loc")
        if g == "FRU":
            fru.append(r); continue
        item = v("item")
        if item is None or str(item).strip() == "": continue
        rows.append(dict(r=r, group=g, comp=comp, loc=loc, item=str(item).strip(),
                         model=v("model"), manu=v("manu"), mpn=v("mpn"), mspn=v("mspn"),
                         fw=("" if v("fw") is None else str(v("fw")).strip()),
                         vrc=v("vrc"), chk=v("chk"),
                         path=("" if v("path") is None else str(v("path")).strip())))
    return h, m, rows, fru

def match(new_rows, base_rows):
    used = set(); res = {}
    by = collections.defaultdict(list)
    for b in base_rows: by[(b["group"], b["item"])].append(b)
    def take(n, pred):
        for b in by[(n["group"], n["item"])]:
            if id(b) not in used and pred(b):
                used.add(id(b)); return b
    for n in new_rows:
        b = take(n, lambda b: b["fw"] == n["fw"] and b["path"] == n["path"])
        if b: res[id(n)] = b
    for n in new_rows:
        if id(n) in res: continue
        b = take(n, lambda b: b["fw"] == n["fw"])
        if b: res[id(n)] = b
    for n in new_rows:
        if id(n) in res: continue
        b = take(n, lambda b: True)
        if b: res[id(n)] = b
    removed = [b for b in base_rows if id(b) not in used]
    return res, removed

def copy_style(src, dst):
    dst.font = copy.copy(src.font); dst.border = copy.copy(src.border)
    dst.fill = copy.copy(src.fill); dst.alignment = copy.copy(src.alignment)
    dst.number_format = src.number_format; dst.protection = copy.copy(src.protection)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("old"); ap.add_argument("new"); ap.add_argument("out")
    ap.add_argument("--old-sheet"); ap.add_argument("--new-sheet")
    a = ap.parse_args()
    wbo = openpyxl.load_workbook(a.old); wbn = openpyxl.load_workbook(a.new)
    wso = wbo[a.old_sheet] if a.old_sheet else pick_sheets(wbo, True)
    wsn = wbn[a.new_sheet] if a.new_sheet else pick_sheets(wbn, False)
    if not wso or not wsn: raise SystemExit("找不到 FW-SW 頁，請用 --old-sheet / --new-sheet 指定")
    ho, mo, orows, ofru = read_rows(wso); hn, mn, nrows, _ = read_rows(wsn)
    res, removed = match(nrows, orows)
    out = openpyxl.Workbook(); ws = out.active; ws.title = "FW-SW Merged"
    for r in range(1, ho + 1):
        for c in range(1, wso.max_column + 1):
            s = wso.cell(r, c); d = ws.cell(r, c, s.value); copy_style(s, d)
    for c in range(1, wso.max_column + 1):
        w = wso.column_dimensions[get_column_letter(c)].width
        if w: ws.column_dimensions[get_column_letter(c)].width = w
    report = []; r = ho + 1; last_style_row = ho
    cat = lambda n, b: ("新增" if b is None else "FW改版" if n["fw"] != b["fw"] else "路徑改" if n["path"] != b["path"] else "不變")
    for n in nrows:
        b = res.get(id(n)); st = cat(n, b)
        src = b["r"] if b else None
        for c in range(1, wso.max_column + 1):
            s = wso.cell(src or last_style_row, c); d = ws.cell(r, c); copy_style(s, d)
            if b and c > mo["path"]: d.value = s.value
        put = lambda k, val: ws.cell(r, mo[k]).__setattr__("value", val) if mo.get(k) else None
        for k in ("group", "comp", "loc"): put(k, n[k])
        for k in ("item", "model", "manu", "mpn", "mspn"): put(k, n[k] if n[k] is not None else (b[k] if b else None))
        put("fw", n["fw"] or None); put("path", n["path"] or None)
        put("vrc", b["vrc"] if b else None); put("chk", b["chk"] if b else None)
        for k in ("vrc", "chk"):
            cell = ws.cell(r, mo[k])
            if st != "不變": cell.fill = YELLOW
            elif cell.fill.fgColor.rgb == "FFFFFF00": cell.fill = PatternFill(fill_type=None)
        note = ""
        if st == "不變" and b and b["vrc"] in (None, ""): note = "VRCID 空白（舊版也空白）"
        report.append([n["group"], n["item"], st, b["fw"] if b else "", n["fw"], b["path"] if b else "", n["path"],
                       b["vrc"] if b else "", b["chk"] if b else "", note])
        last_style_row = src or last_style_row; r += 1
    for b in removed:
        report.append([b["group"], b["item"], "新版已移除", b["fw"], "", b["path"], "", b["vrc"], b["chk"], "新版沒有此列，合併結果未保留"])
    for fr in ofru:
        for c in range(1, wso.max_column + 1):
            s = wso.cell(fr, c); d = ws.cell(r, c, s.value); copy_style(s, d)
        r += 1
    gi, ci, li = mo["group"], mo.get("comp"), mo.get("loc")
    prev = [None, None, None]
    for i, n in enumerate(nrows):
        rr = ho + 1 + i; cur = [n["group"], n["comp"], n["loc"]]
        for j, col in enumerate((gi, ci, li)):
            if col is None: continue
            if cur[:j + 1] == prev[:j + 1] and i > 0: ws.cell(rr, col).value = None
        prev = cur
    sheet = out.create_sheet("Change Report")
    sheet.append(["Group", "Item", "狀態", "舊 FW", "新 FW", "舊路徑", "新路徑", "舊 VRCID", "舊 Checksum", "備註"])
    for row in sorted(report, key=lambda x: x[2] == "不變"): sheet.append(row)
    for row in sheet.iter_rows(min_row=2):
        if row[2].value not in ("不變",):
            for c in row: c.fill = YELLOW
    for col, w in zip("ABCDEFGHIJ", (14, 28, 12, 26, 26, 50, 50, 12, 36, 30)): sheet.column_dimensions[col].width = w
    out.save(a.out)
    cnt = collections.Counter(x[2] for x in report)
    print(f"舊版頁：{wso.title}｜新版頁：{wsn.title}｜結果：{dict(cnt)}")
    for x in report:
        if x[2] != "不變": print(x[2], x[0], x[1], "|", x[3], "→", x[4], "| VRC", x[7])

if __name__ == "__main__": main()

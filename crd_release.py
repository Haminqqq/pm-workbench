#!/usr/bin/env python3
"""CRD 版本管理：目前版放專案資料夾、舊版進 old/、CHANGELOG 記一行。

用法（在 pm-workbench 資料夾）：
  python crd_release.py --status
  python crd_release.py --publish --project "XIO Gen10.3" --new "CRD/out/XIO Gen10.3/M1441179.xlsx" --rev F --note "FW 合併 MSFT RevF"
  python crd_release.py --rollback --project "XIO Gen10.3"

CRD_DIR 讀 CLAUDE.md 的 `CRD_DIR = ...`，或用 --crd-dir 指定。
原檔絕不直接覆蓋：上架前一定先搬到 old/；被 Excel 開著就停（exit 2），什麼都不動。
"""
import argparse, datetime as dt, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
XL = (".xlsx", ".xlsm")


def crd_dir_from_claude_md():
    p = os.path.join(HERE, "CLAUDE.md")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            m = re.match(r"\s*CRD_DIR\s*=\s*(.+?)\s*(←.*)?$", line)
            if m:
                return m.group(1).strip().strip('"')
    return None


def is_locked(path):
    """Excel 開著：同資料夾有 ~$ 鎖檔，或檔案無法以寫入模式開啟。"""
    d, n = os.path.split(path)
    if os.path.exists(os.path.join(d, "~$" + n)):
        return True
    try:
        with open(path, "r+b"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def read_rev(path):
    """從 Cover／Change history 類分頁猜 Rev；讀不到回 '?'。"""
    try:
        import openpyxl
    except ImportError:
        return "?"
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception:
        return "?"
    try:
        names = [s for s in wb.sheetnames if re.search(r"change|history|revision|cover", s, re.I)]
        rev = None
        for sn in names or wb.sheetnames[:1]:
            ws = wb[sn]
            for row in ws.iter_rows(min_row=1, max_row=200, values_only=True):
                for c in row:
                    if not isinstance(c, str):
                        continue
                    m = re.search(r"\bRev(?:ision)?\.?\s*[:：]?\s*([A-Z]{1,2}|\d{1,2}(?:\.\d+)?)\b", c)
                    if m:
                        rev = m.group(1)  # 取最後出現的
        return rev or "?"
    finally:
        wb.close()


def current_files(proj_dir):
    return sorted(f for f in os.listdir(proj_dir)
                  if f.lower().endswith(XL) and not f.startswith("~$") and os.path.isfile(os.path.join(proj_dir, f)))


def fmt_time(path):
    return dt.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")


def status(crd_dir):
    print(f"CRD_DIR = {crd_dir}")
    if not os.path.isdir(crd_dir):
        print("  （資料夾不存在，先到 CLAUDE.md 改 CRD_DIR）"); return
    for proj in sorted(os.listdir(crd_dir)):
        pd = os.path.join(crd_dir, proj)
        if not os.path.isdir(pd):
            continue
        files = current_files(pd)
        old = os.path.join(pd, "old")
        nold = len([f for f in os.listdir(old) if f.lower().endswith(XL)]) if os.path.isdir(old) else 0
        print(f"\n[{proj}]  舊版 {nold} 份")
        if not files:
            print("  （沒有目前版）")
        for f in files:
            p = os.path.join(pd, f)
            lock = "  ⚠ Excel 開著" if is_locked(p) else ""
            print(f"  {f}  Rev {read_rev(p)}  {fmt_time(p)}{lock}")
        if len(files) > 1:
            print("  ⚠ 不只一份，上架時要用 --name 指定是哪一份")
    outdir = os.path.join(HERE, "CRD", "out")
    pending = []
    if os.path.isdir(outdir):
        for root, _, fs in os.walk(outdir):
            pending += [os.path.relpath(os.path.join(root, f), HERE) for f in fs if f.lower().endswith(XL)]
    if pending:
        print("\n等著上架（CRD/out）：")
        for p in pending:
            print("  " + p)


def changelog(proj_dir, line):
    p = os.path.join(proj_dir, "CHANGELOG.md")
    new = not os.path.exists(p)
    with open(p, "a", encoding="utf-8") as f:
        if new:
            f.write("# CRD 變更紀錄\n\n")
        f.write(line + "\n")
    return line


def unique(path):
    base, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(path):
        path = f"{base}-{i}{ext}"; i += 1
    return path


def publish(crd_dir, project, new, rev=None, note="", name=None, who="Claude"):
    pd = os.path.join(crd_dir, project)
    if not os.path.isdir(pd):
        sys.exit(f"找不到專案資料夾：{pd}（名稱要跟 CRD_DIR 底下的一樣）")
    if not os.path.isfile(new):
        sys.exit(f"找不到新檔：{new}")
    target_name = name or os.path.basename(new)
    files = current_files(pd)
    cur = os.path.join(pd, target_name) if target_name in files else None
    if cur is None and files:
        print("目前版找不到同名檔。專案資料夾裡有：")
        for f in files:
            print("  " + f)
        sys.exit("請用 --name 指定要取代哪一份（新檔會改成那個檔名），或確認檔名。")
    if cur and is_locked(cur):
        print(f"⚠ 請先關閉 Excel 裡的「{target_name}」，再跑一次。什麼都還沒動。")
        sys.exit(2)
    if is_locked(new):
        print(f"⚠ 新檔「{new}」也被開著，先關掉。"); sys.exit(2)
    today = dt.date.today().strftime("%Y%m%d")
    moved = None
    if cur:
        old_dir = os.path.join(pd, "old"); os.makedirs(old_dir, exist_ok=True)
        old_rev = read_rev(cur)
        stem, ext = os.path.splitext(target_name)
        moved = unique(os.path.join(old_dir, f"{stem}_Rev{old_rev}_{today}{ext}"))
        shutil.move(cur, moved)
    dst = os.path.join(pd, target_name)
    shutil.copy2(new, dst)
    rev = rev or read_rev(dst)
    line = changelog(pd, f"- {dt.date.today().isoformat()} Rev {rev}｜{note or '（未填說明）'}｜{who}｜舊版→ {os.path.relpath(moved, pd) if moved else '無'}")
    print(f"✅ 已上架：{dst}")
    if moved:
        print(f"   舊版：{moved}")
    print(f"   CHANGELOG：{line}")
    if os.path.abspath(new).startswith(os.path.join(HERE, "CRD", "out")):
        try:
            os.remove(new)  # 只清 CRD/out 裡的暫存檔
        except OSError:
            pass


def rollback(crd_dir, project, name=None):
    pd = os.path.join(crd_dir, project)
    old_dir = os.path.join(pd, "old")
    olds = sorted((f for f in os.listdir(old_dir) if f.lower().endswith(XL)),
                  key=lambda f: os.path.getmtime(os.path.join(old_dir, f))) if os.path.isdir(old_dir) else []
    if not olds:
        sys.exit("old/ 裡沒有舊版可以回復。")
    last = olds[-1]
    m = re.match(r"(.+?)_Rev[^_]+_\d{8}(?:-\d+)?(\.xls[xm])$", last)
    target_name = name or (m.group(1) + m.group(2) if m else last)
    cur = os.path.join(pd, target_name)
    if os.path.exists(cur):
        if is_locked(cur):
            print(f"⚠ 請先關閉 Excel 裡的「{target_name}」。"); sys.exit(2)
        today = dt.date.today().strftime("%Y%m%d")
        stem, ext = os.path.splitext(target_name)
        shutil.move(cur, unique(os.path.join(old_dir, f"{stem}_Rev{read_rev(cur)}_{today}_undone{ext}")))
    shutil.move(os.path.join(old_dir, last), cur)
    changelog(pd, f"- {dt.date.today().isoformat()} 回復｜從 old/{last} 回復為目前版｜Claude")
    print(f"✅ 已回復：{cur}（來自 old/{last}）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--crd-dir")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--status", action="store_true")
    g.add_argument("--publish", action="store_true")
    g.add_argument("--rollback", action="store_true")
    ap.add_argument("--project")
    ap.add_argument("--new", help="要上架的新檔（通常在 CRD/out/<專案>/）")
    ap.add_argument("--name", help="專案資料夾裡要取代的檔名（新檔檔名不同時用）")
    ap.add_argument("--rev")
    ap.add_argument("--note", default="")
    ap.add_argument("--who", default="Claude")
    a = ap.parse_args()
    crd_dir = a.crd_dir or crd_dir_from_claude_md()
    if not crd_dir:
        sys.exit("沒有 CRD_DIR：到 CLAUDE.md 填，或加 --crd-dir")
    if a.status:
        status(crd_dir)
    elif a.publish:
        if not (a.project and a.new):
            sys.exit("--publish 需要 --project 和 --new")
        publish(crd_dir, a.project, a.new, a.rev, a.note, a.name, a.who)
    else:
        if not a.project:
            sys.exit("--rollback 需要 --project")
        rollback(crd_dir, a.project, a.name)


if __name__ == "__main__":
    main()

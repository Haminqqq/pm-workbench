---
name: "mspn-qpn-lookup"
description: "查料號：使用者給 MSPN（M1xxxxxx-001）、QPN（11 碼）或廠牌料號 MPN，或說「查料號」「這顆料在哪幾份 CRD」「EOL 換料分析」時使用。讀 MSPN–QPN Mapping 工具的資料庫（base＋imports），回對照表與所在 CRD；EOL 時列出每份 CRD 要做的 Q／B／F／C 步驟並寫入工具的 EOL 紀錄。其他 skill（掃信、CRD 合併）也呼叫這個流程。"
---

# MSPN–QPN 查詢與 EOL 分析

資料來源是 MSPN–QPN Mapping 工具 https://claude.ai/artifact/Pk7jBE6rQJxjhCy6sKEy1H 的資料庫（用 ArtifactData，url 填這個）。不用打開頁面。

## 資料庫結構
- `base/_meta`：`buckets`（每個 family 有哪些桶）、`layout`。**每次對話第一次查詢先讀一次**，之後用它決定要讀哪個桶。
- `base/map-<MSPN前綴>`：`rows:[MSPN,QPN,remark,project,date,flag]`（內建對照表 10,953 筆）。
- `base/qidx-<QPN前綴>`：`rows:[QPN,MSPN]`（QPN 反查）。
- `base/pi-<前綴>`：`Q:{QPN:[品名,Ver,多版提示]}`、`M:{MSPN:[Rev,多版提示,品名]}`。
- `base/crd-<key>`：`label`＋`rows:[key,level,group,desc,MSPN,QPN,batch,isAlt,note]`（內建 7 份：g94_xstore、g94_xio、g95_xstore、g97_xstore、g103_xstore、g103_xio、sku＝SKU 總表）。
- `base/bom-<MSPN前綴>`：`m:{MSPN:{l:專案層級,r:Rev,d:品名,m:[[廠牌,MPN]]}}`；`base/bomp-<MPN前綴>`：`p:{MPN:[[MSPN,…]]}`（MPN 反查）。
- `imports/*`：她匯入的 CRD（每份可能分成 `<imp>~0`、`~1`…）：`name,doc,rev,ver,project,date,map:[[MSPN,QPN,remark,project,date]],crd:[[level,group,item,MSPN,QPN,status,isAlt,note]]`。status：orig／b4／b4w（這次新增）／skip／no_qpn／no_mspn。
- `deleted/*`：`k`＝"MSPN|QPN|project" 標記刪除的對照（查詢時排除）。
- `flags/<QPN>`：`{qpn,label:"EOL",date,note}`。
- `crdmeta/<doc>`：`{doc,stage:"NPI"|"MP",link:"auto"|"yes"|"no"}`（EOL 用）。
- `eolruns/<id>`：EOL 紀錄（shape 見下）。

桶的選法：normalize（去空白、轉大寫）後，在 `_meta.buckets[family]` 裡找**最長的前綴相符**者；找不到就代表內建資料沒有。

## 查詢流程
1. 整理輸入：抓出所有 `M\d{7}-\d{3}`（MSPN）、11 碼英數（含 ^）的 QPN、其餘當 MPN。去重，一次最多 40 個；超過先問她要哪些。
2. 讀 `base/_meta`（一次）、`imports` 全部（`list`，limit 50；一次）、`deleted`、`flags`（各一次，快取整個對話）。
3. 每個料號：
   - MSPN → 讀對應 `base/map-*` 桶，取 `rows[0]==MSPN` 的列，加上 imports 所有 `map` 裡相符的；排除 deleted。
   - QPN → 讀 `base/qidx-*` 桶反查 MSPN，再照 MSPN 查；imports 的 `map` 也用 QPN 比對。
   - MPN → 讀 `base/bomp-*` 桶拿 MSPN 清單，再照 MSPN 查。
   - 版本與品名：`base/pi-*`（M 給 Rev、Q 給 Ver 與品名）；品名沒有就用 `base/bom-*` 的 `d`。
   - 出現在哪些 CRD：掃 `base/crd-*`（7 份，第一次全讀後快取）＋ imports 的 `crd`，MSPN 或 QPN 相符就算；同一份 doc 有多個 Rev 時只列最新匯入的那份（imports 的 `at` 最大者）。
4. 輸出表格（繁體中文）：

| 輸入 | MSPN | Rev | QPN | Ver | 品名 | 出現在 | 標記 |
|---|---|---|---|---|---|---|---|
| … | … | … | … | … | … | XIO Gen10.3 RevE L10 Node（Alt）；SKU 總表 | ⛔ EOL 11/5 |

- 一個 MSPN 對多個 QPN 就列多列，並在備註說明哪個是最新匯入或 remark 寫的專案。
- 找不到：寫「不在 mapping」，若有 MPN 反查到就補上；仍沒有就建議「先申請 QPN（SOP：申請Assign QPN）」。
- 只回報資料庫裡有的，不要猜 QPN。

## EOL 換料分析（她說「EOL」「停產」「換料」或掃信遇到 EOL／PCN 信）
輸入：EOL 料號（MSPN／QPN／MPN）、新料 MSPN（可空）、新料 QPN（可空）、日期、備註、「新料是不是 NPI 要備料的那顆」。缺的先問她（一次問完）。

步驟（照工具頁 analyzeEol 的規則）：
1. 解析 EOL 料：MSPN → 它的所有 QPN；QPN → 只算這顆 QPN（同 MSPN 其他廠牌不算）；MPN → 對應的 MSPN 們。
2. 找受影響 CRD：base 的 7 份 crd ＋ imports 的 crd，MSPN／QPN 相符且 level ≠ "HW Config" 的列；同一 doc 只取最新 Rev；`note` 提到該 MSPN（一字階／二字階）的列另列為「備註提到」。SKU 總表相符另外註明。
3. 每份 CRD 讀 `crdmeta/<doc>`：`stage`（NPI／MP）與 `link`；沒設定就標「階段未設定」。L10／L11 QPN 串了沒：找該 CRD `HW Config` 層對應 level 的列（Node／Utility／JBOD／L11），QPN 是 11 碼＝已串（link 設 yes／no 時以設定為準）。
4. 產出每份 CRD 的四組步驟：
   - **Q**：新料沒填→「先跟 PjE／客人確認有沒有取代料」；新料有但 mapping 沒 QPN→「先申請 QPN」；多個 QPN→請她指定。
   - **B**：該層級 QPN 已串→「請 PjE 發 ECN（移除 EOL 料、加入新料）」；沒串→「更新 BOM list 該分頁：移除 EOL 料、加入新料」；判斷不出→「到工具『各 CRD 階段設定』手動指定」。
   - **F**：NPI→「更新 FCST：EOL 料需求改成新料（或先移除）」；MP→「不放 FCST，進 MP 時替代料都要驗證並導入 BOM」；未設定→提醒設定。
   - **C**：每列「level › group：MSPN/QPN（品名）→ 劃刪除線＋灰底，Notes 加 EOL <日期>」；新料已在 CRD→依「是否備料那顆」決定拿掉或保留刪除線＋粉紅底；不在→「同 Group 新增新料／QPN 待申請」；最後一行 Change history 摘要。
5. 寫入工具 `eolruns/<id>`（`set`，id＝`eol_<時間36進位>_<EOL料號>`）：
```json
{"id":"…","at":1731400000000,"by":null,
 "inp":{"eol":"M1205954-001","nm":"M1248369-001","nq":"DQ5DC44P278","date":"2026/11/13","note":"PjE 11/13 來信","stock":true},
 "eolM":["M1205954-001"],"eolQ":["DQ5DC44P279"],"nm":"M1248369-001","nq":"DQ5DC44P278","q":"Q 步驟一句",
 "crds":[{"doc":"M1441179","label":"XIO Gen10.3 RevE","stage":"NPI","levels":["L10 Node","L10 Utility"],"B":["…"],"F":["…"],"C":["…"]}],
 "done":{}}
```
   她要求時再對 EOL 的 QPN 寫 `flags/<QPN>`：`{qpn,label:"EOL",date,note,at,by:null}`。
6. 回覆：影響範圍一句（N 份 CRD、幾份 NPI 要放 FCST、幾份要 ECN）＋每份 CRD 的 Q/B/F/C 條列。掃信流程會再據此建待追清單卡片。

## 規則
- 只讀必要的桶，不要整個 `base` 讀完；每個對話每個桶只讀一次。
- 不改 `base/*`（那是內建資料快照）。要新增對照一律寫 `imports`（照 crd-fw-merge／crd-fru-update 的「回寫 mapping」步驟）。
- 寫 `eolruns`、`flags` 前先把結果給她看一眼；她說好再寫。
- 回覆繁體中文；料號、Rev 原樣照抄，不確定寫 [待確認]。

## 同步 mapping（她說「同步 mapping」「把本機 CRD 補進 mapping」；只在 pm-workbench 本機用）
把本機每個專案的目前版 CRD 補進工具的 `imports`，之後查料號、EOL 分析才查得到。
1. `python crd_release.py --status` 取得每個專案的目前版檔案與 Rev。
2. ArtifactData `list` `imports`（limit 50）→ 整理成「doc（M 編號）→ 已匯入的 rev／ver／at」。
3. 比對：本機 CRD 的 doc＋Rev 已在 imports 裡 → 跳過；沒有、或本機 Rev 較新、或檔名裡的版本（V0.16 這種）比已匯入的新 → 列入待同步。先把待同步清單給她看（專案、檔名、Rev、工具裡最新匯入的是哪版），她確認再做。
4. 每份待同步 CRD：
   - 先用 `python crd_release.py --status` 之外的方式讀檔名裡的 project 標籤；`--project` 用工具既有寫法（例如 `S2185 Xstore Gen9.4/T6Y`，從 `base/map-*` 同專案列的第 4 欄抄）。
   - 準備 `known.json`：讀這份 CRD 出現的 MSPN 前綴對應的 `base/map-*` 桶（通常 ≤15 桶）＋全部 imports 的 map，寫成 `{"pairs":[["MSPN","QPN"],…]}`。
   - `python crd_import.py "<CRD 路徑>" --name "<專案>" --project "<標籤>" --rev <Rev> --known known.json --out imports_<doc>.json`。
   - 把 `summary` 給她：新增對照 N 筆、⚠ N 筆（QPN 已對應其他 MSPN）、QPN TBD N 筆。
5. 她確認後，`docs[]` 每份 ArtifactData `set` 到 `imports/<imp>`（doc_id 用 json 裡的 `imp`，分 part 時 `<imp>~<part>`）。同 doc＋rev＋ver 已存在就只補缺的組合（update 該文件的 map／crd 陣列）。
6. 回覆：每份 CRD 一行「<專案> <Rev>：mapping 新增 N 筆、TBD N 筆（已記為待申請）」。TBD 的料號另列一張「申請 QPN」清單，問她要不要建待追卡。

規則：`base/*` 不改；寫入前一定先給她看摘要；一次最多同步 10 份，超過先問。

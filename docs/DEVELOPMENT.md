# RetroWave 開發者指南（DEVELOPMENT.md）

> **文件分工**：`RetroWave_Design.md` 是**語言無關的設計規格**（概念、演算法、不變量、協定），
> 不含任何 Python/tkinter 字眼；本文件則以**程式碼對應**的手法解釋同一份設計 —
> 設計章節 ↔ 實際符號（class/method）。改了程式請回頭核對兩份文件。
> `README.md` 面向使用者；`CLAUDE.md` 面向 AI 助手；`COWORK_INSTRUCTIONS.md` 是收尾同步流程。

## 1. 環境與常用指令

- **Python 3.8+**，需含 `tkinter`（CPython 內建；部分 Linux 需 `sudo apt install python3-tk`）。
- 選配：`pip install pillow`（只有 PNG 匯出需要）、`pip install pytest`（開發必裝）。

```bash
python run.py                  # 啟動（開啟示範波形）；或 cd src && python -m retrowave
python -m pytest               # 全部測試（<1s；GUI 測試會短暫開視窗）
python -m pytest tests/test_model.py -k group        # 跑子集
python -m compileall -q src    # 語法檢查
```

**提交門檻**：pytest 全綠 + 語法檢查通過，缺一不可。

## 2. 程式碼地圖（設計章節 ↔ 符號）

程式碼在 `src/retrowave/` 套件，依設計文件 §14 嚴格分層 —
**除了 shell 層（`app.py`、`tutorial.py`、`__main__.py`）外，任何模組不得 `import tkinter`**
（有邊界測試把關）。GUI 測試/自動化以環境變數 `RETROWAVE_NO_TUTORIAL=1` 抑制首啟教學。
推 `v*` 標籤會觸發 `.github/workflows/release.yml`：windows-latest 跑全套測試 →
PyInstaller onefile → 發佈 GitHub Release。

```
src/retrowave/
├── theme.py       Style                    共用底層（顏色/字型常數）
├── geometry.py    Geometry                 共用底層（座標/斜率幾何）
├── model.py       Row, DEFAULT_PERIODS, Model   邏輯單元（文件核心，headless）
├── templates.py   TemplateLibrary          邏輯單元（範本索引）
├── elements.py    WAVE_TYPES, *Element     繪圖單元（六種元件演算法）
├── engine.py      Engine                   繪圖單元（單一繪製流程）
├── backends.py    PILCanvas, SVGCanvas     繪圖單元（PNG/SVG 匯出後端）
├── export.py      export_png/svg/wavedrom  繪圖單元（匯出管線，純函式）
├── document.py    Document                 傳遞層（命令/事件/交易/undo；§8）
├── app.py         App, make_key_button     UI 殼層（tkinter）
├── tutorial.py    TutorialOverlay          UI 殼層（開啟教學遮罩；設定存 ~/.retrowave/settings.json）
├── __init__.py    __version__ + re-export（UI 名稱 PEP 562 延遲載入）
└── __main__.py    python -m retrowave
```

對照表以符號名為準（行號會漂移，請用搜尋）：

| 設計章節 | 程式碼符號 | 說明 |
|---|---|---|
| §2.1–2.2 訊號/格子 | `Model.signals`、`Model.new_cell` | 訊號 = dict（name/offset/color/group/sid/cells） |
| §2.3 群組樹 | `Model.group_tree`、`Model._dfs_leaves` | 巢狀結構真相；`signal["group"]` 只是父群組快取 |
| §2.4 標注 | `Model.nodes` / `Model.edges`、`add_node` / `add_edge` / `prune_annotations` | 以 sid 錨定 |
| §2.5 幾何 | `Geometry`（`period_w`/`row_h`/`ramp_ratio`/`tw()`/`levels()`） | `copy_scaled(k)` 供高解析匯出 |
| §2.6 不變量 | `tests/conftest.py::assert_invariants` | **七條鐵則的可執行版本** |
| §3.3 統一斜率 | `Geometry.tw`、各 `Element.draw` | 斜率恆為 swing/tw；半擺幅寬 tw/2 |
| §4 繪圖面抽象 | `PILCanvas`、`SVGCanvas` | duck-type tkinter Canvas API（`create_line` 等） |
| §5 版面演算法 | `Model.layout` → `Row(kind, ref, depth, gcol)` | 樹 → 可見列；折疊群組不展開 |
| §6 波形渲染 | `Engine.draw`；排程見 `App.request_render` / `App.render` | 46 個互動點走 request（合併）；首繪與 EPS 快照同步 |
| §6.3 元件繪製 | `ClkElement` / `HighElement` / `LowElement` / `HiZElement` / `BusElement` / `UnknownElement` | `Engine.elem(t)` 取實例 |
| §6.4 接縫解析 | `Engine.meet` | 相鄰格 exit_y/entry_y → 過渡線 |
| §7 標注渲染/互動 | `Engine.node_positions` / `draw_node` / `draw_edge`；`App._node_at_xy` / `on_wave_menu` | |
| §8.1 畫格/筆刷 | `App.on_press` / `on_motion` / `on_release`、`_paint_cell` / `_click_cell` | 筆刷鎖列：列取自 `_press[0]` |
| §8.1a 拖曳模式 | `App._enter_pan_mode`、`_scrollable` | 逐軸計算，內容未超出視窗則鎖原點 |
| §8.2–8.4 名稱欄拖曳 | `App.on_name_press` / `on_name_drag` / `on_name_release`、`_compute_drop` | marker 三步驟在 `Model.move_leaf_to` / `move_group_to` |
| §8.5 複製貼上 | `App.do_copy` / `do_paste`、`_paste_group` | 複本一律配發新 sid |
| §9 匯出 | `export.py`：`export_png` / `svg_string` / `export_svg` / `wavedrom_dict` / `export_wavedrom`（純函式）；`App.do_export` 只留對話框 | EPS 例外留在 app（`wave_cv.postscript` 快照畫布，須同步 render） |
| §10 持久化/遷移 | `Model.to_dict` / `load_dict` / `_migrate_flat_to_tree` | 舊扁平格式 → 樹 |
| §11 UI 結構 | `App._build_menubar` / `_build_toolbar` / `_build_main` / `_build_statusbar` | |
| §14 UI↔Core protocol | （目標架構，見下方 §5） | 尚未實作，遷移路線見 §6 |
| 範本庫 | `TemplateLibrary`（索引在 `~/.retrowave/templates_index.json`） | 與專案檔獨立 |

## 3. 七條鐵則 ↔ 程式碼與測試

| # | 鐵則（§2.6） | 實作所在 | 守門測試 |
|---|---|---|---|
| 1 | 斜率恆 = swing/tw；半擺幅寬 tw/2 | `Geometry.tw`、`Engine.meet`、各 `Element.draw` | （視覺規則，靠 review） |
| 2 | 複製/貼上/範本必配新 sid | `do_paste`、`_paste_group`、`_insert_template` | `test_copy_paste_signals_fresh_sids`、`test_insert_template_*` |
| 3 | 群組樹為真相；signals 同步 DFS 葉序 | `Model._resync_signals` / `_after_tree_change` | `assert_invariants` 第 2/5 條 |
| 4 | 拖曳用 marker 三步驟 | `Model.move_leaf_to` / `move_group_to` | `test_move_leaf_downward_*` |
| 5 | 標注以 sid 錨定 | `Model.nodes`、`Engine.node_positions` | `assert_invariants` 第 6 條 |
| 6 | 總高度用 `len(layout())` | `Engine.draw`（total_h） | `assert_invariants` 第 8 條 |
| 7 | 匯出倍率叫 `export_scale` 且防呆 | `PILCanvas`、`_export_png` | （命名規約） |

## 4. 開發循環

1. 改程式 → `python -m pytest` 全綠。
2. 任何**功能或行為變更**：版本號 `vMAJOR.MINOR` 遞增 MINOR，**三處同步** —
   `src/retrowave/__init__.py` 的 `__version__`（視窗標題與關於對話框自動帶出，**程式內不得再硬編版本字串**，有測試把關）、設計文件（`Spec version` + §15 Changelog 最上方新增一條）、`README.md`（若影響使用者）。
3. Commit 格式：`vX.Y: <一句話摘要>`，內文條列重點。
4. Push 前向 owner 確認（見 `COWORK_INSTRUCTIONS.md`）；禁止 force-push。

### 測試撰寫須知

- `tests/test_model.py`：純 Model 測試，不開視窗；**每個變更型測試最後呼叫 `check(model)`**（= `assert_invariants`）。
- `tests/test_app_interactions.py`：用 `Ev` 假事件驅動真實 handler（`on_press`/`on_motion`/`on_release`），座標用 `cell_xy(app, row, period)` 算。
- ⚠️ **整個 session 共用一個 Tk root**（`conftest._root`，session scope）：同一行程反覆 create/destroy `Tk()` 會觸發 Tcl 的 `tcl_findLibrary` 錯誤。新 GUI 測試一律拿 `app` fixture（每測前自動重置狀態），**不要自己 new `retrowave.App()`**。
- 會彈對話框的路徑（BUS 改值、關係線標籤、各 messagebox）不要在測試中觸發。

## 5. UI ↔ Core 切分現況（protocol 違規清單）

設計文件 §14 的 protocol（R1–R5）已於 **v1.24 實作完成**，下表違規全數消除
（守門：`test_module_boundaries.py::test_app_writes_only_via_document`）：

| 原違規點 | 解法 |
|---|---|
| `App.do_paste`（訊號貼上）直接操作池/樹 | → `doc.paste_signals()`（複本配新 sid 的邏輯移入 Document） |
| `App._insert_template` / `_paste_group` | → `doc.insert_template()` / `doc.paste_group()`（共用 `_paste_as_group`） |
| 核心不發事件、靠 UI 記得重繪 | → `doc.subscribe()` + `changed(scopes)`；render 已事件驅動（互動點殘留的 `request_render` 為無害冗餘，合併機制吸收） |
| 群組選單直接改 `groups[gid][...]` | → `toggle_group` / `set_group_color` / `rename_group` 命令 |
| 一次筆刷 = N 次散裝 `set_cell` | → `begin()/commit()` 手勢交易（一手勢 = 一 undo 單位） |

殘留偏差（記錄於設計文件 §14 狀態註）：命令引數沿用池索引（選取是 shell 的索引暫態；
池序==視覺序保證單一手勢內穩定）；sid-only 識別為長期目標。

## 6. 重構路線圖（依 §14 protocol 重塑架構）

每段獨立 commit + push，全程 54+ 測試保護；失敗退回上一 commit 重試。

| 版本 | 內容 | 驗收門檻 |
|---|---|---|
| **v1.22** ✅ | **套件拆分**：`src/retrowave.py` → `src/retrowave/` 套件（`model` / `elements` / `engine` / `backends` / `templates` / `geometry` / `theme` / `app`），行為零變更 | 既有測試原樣全綠 + `test_module_boundaries.py`（headless 子行程鐵證、AST 禁 tkinter、re-export 完整、版本單一來源） |
| **v1.23** ✅ | **匯出抽離**：`_export_png/svg/wavedrom` → `export.py` 純函式 `(model, geom) → file` | `test_export.py`（SVG 結構/虛線/位移寬度、WaveDrom 波形字串/巢狀群組/phase/edge、PNG 2× 尺寸） |
| **v1.24 前置** ✅ | **Model 函式分類**（不拆類 — 評估結論：現階段單一 Model 已足夠靈活，先以 §7 分類表明確化各 function 性質與修改風險） | §7 分類表與程式碼一致 |
| **v1.24** ✅ | **命令層**：`document.py` 實作 §14.3 命令目錄 + §14.4 change events；App 全部改走命令；消除上表違規（三層架構見 §8） | `test_document.py`（19 tests：命令/事件合併/錯誤策略/交易/undo 基建）+ 邊界測試禁 app 私有存取 |
| **v1.25** ✅ | **Undo/Redo**：快照式（§14.5），`Ctrl+Z/Y`，深度 5；undo/redo 後夾住選取、清舊暫態 | `test_undo_ui.py`（8 tests：筆刷/填入/貼上=單步、無變更不入棧、深度 5、空棧安全） |
| 後續 | 增量重繪（dirty rows，靠 §14.4 scope）、App controller 拆分、VCD import | — |

### 已知技術債（上表未涵蓋）

- `App` 仍是 1,400+ 行上帝類別（96 方法）— v1.24 後拆 controller。
- 選取/hover 等暫態與文件內容混在 App 屬性裡 — 命令層引入時順勢歸類（§14.1）。
- PNG 匯出的虛線網格目前是實線（PIL 後端無 dash）— roadmap 既有項目。

## 7. Model 函式分類（值 / 算 / 流）

> 目的：不拆類的前提下，明確每個 function 的**性質**與**修改風險**。三類定義：
>
> - **值** — 純回覆數值/資料或單一賦值；無遍歷、無遞迴，看一眼即懂。改動風險低。
> - **算** — 內含演算法（遞迴/搜尋/重排/過濾）；模組的「智力」所在。**改它必配單元測試**。
> - **流** — 自己幾乎不運算，**編排**「值/算」成用例流程。改它要檢查：呼叫順序、
>   失敗回滾、是否以對帳（`_after_tree_change`）收尾。
>
> ✏ 欄 = 副作用（寫入什麼）；「—」= 純讀。分組沿用 §5 討論的參照層級（L0–L3）。

### L0 實體層（訊號池；不知道樹的存在）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `new_cell` | 值 | — | cell dict 工廠 |
| `_new_sid` | 值 | `_sid_seq` | 發號器（遞增後回號） |
| `set_cell` | 值 | `cells` | 邊界檢查 + 整格替換 |
| `set_n_periods` | 算 | `cells` `n_periods` | 全池補齊/截斷迴圈 |
| `add_signal` | 流 | pool + tree | 發號→建 dict→掛頂層葉（**已知 L0+L1 滲漏點**，v1.24 命令化時改由協調者分派） |
| `remove_signal` | 流 | pool + tree + groups | 刪池→摘葉→剪空→重建快取（注意：未走完整 `_after_tree_change`，因池已自行刪除、無需 resync） |
| `_demo` | 流 | `cells` | 啟動示範資料 |

### L1 參照結構層（群組樹拓撲；只認 sid/gid，不碰訊號內容）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `_dfs_leaves` | 算 | — | 遞迴攤平 → 正典葉序 |
| `_find_group_node` / `_find_leaf_loc` / `_locate` | 算 | — | 遞迴搜尋（gid / sid / 任意述詞） |
| `_container_children` | 值 | — | 分派：None→樹根，否則委派 `_find_group_node` |
| `_is_self_or_descendant` | 算 | — | 兩段搜尋組合（巢狀防環） |
| `_top_index_of_sid` | 算 | — | 線性掃描 + 子樹成員測試 |
| `_detach_sid` / `_detach_group` | 算 | tree | 遞迴搜尋**＋摘除**（鐵則 4 的「摘」半步） |
| `new_gid` | 值 | `_gid_seq` | 發號器（含撞名防護迴圈） |
| `move_leaf_to` / `move_group_to` | 流 | tree | **marker 三步驟編排**（插佔位→摘→取代）＋失敗撤回 marker；對帳收尾 |

### L2 對帳層（唯一允許同時讀寫兩個域的地方）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `_prune_empty_groups` | 算 | tree | 遞迴剪除空群組 |
| `_resync_signals` | 算 | pool + tree | **池序 := DFS 葉序**（鐵則 3 的執行者）＋漏葉補回修復 |
| `_reindex_groups` | 算 | `groups`、`signal["group"]` | 遞迴重建快取 |
| `_after_tree_change` | 流 | （上三者） | 固定順序管線：剪→排→建。**所有樹變更的標準收尾** |
| `prune_groups` | 流 | tree + groups | 公開精簡版（剪＋重建） |
| `prune_annotations` | 算 | nodes + edges | 孤兒錨點/斷頭關係線過濾，回報清除數 |

### 用例動詞（公開 API；組合 L0/L1，以 L2 收尾）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `group_signals` | 流 | tree + groups | 葉序排序選取→marker→摘 N 葉→建群組節點 |
| `merge_into_group` / `merge_groups` | 流 | tree | 摘→附加到目標 children（merge_into 有「已在目標群」跳過判斷 — **L1 流程讀訊號內容的滲漏點**） |
| `remove_from_group` | 流 | tree + `color` | marker 法批次移出到頂層＋清自訂色 |
| `ungroup` | 流 | tree | 遞迴尋標的→children 就地提升一層 |
| `delete_group` | 流 | 全域 | 摘子樹→池中刪 sids→對帳→剪標注（唯一動到四個域的動詞） |

### 標注（平行參照集；只認 sid）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `new_nid` | 算 | — | 字母配號搜尋（a..z → aa..zz） |
| `add_node` / `add_edge` | 值 | nodes / edges | 驗證＋寫入（edge 拒自迴圈與無效端點） |
| `remove_node` | 值 | nodes + edges | 刪錨＋級聯過濾關係線 |

### L3 投影（唯讀衍生查詢）

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `layout` | 算 | — | 遞迴展開樹→`Row` 列表；折疊不展開；色彩繼承（最近祖先勝） |

### 持久化

| 方法 | 類 | ✏ | 說明 |
|---|---|---|---|
| `to_dict` | 值 | — | 組裝可序列化 dict |
| `_all_group_nodes` | 算 | — | 遞迴收集全部群組節點 |
| `_migrate_flat_to_tree` | 算 | tree | 舊扁平格式→單層樹 |
| `load_dict` | 流 | 全域 | 正規化訊號→建樹（新舊分流）→還原序號→對帳→剪標注 |

**閱讀/修改指引**：動「算」先寫測試釘住行為；動「流」核對編排順序與收尾；
「值」風險最低但發號器（`_new_sid`/`new_gid`）攸關鐵則 2，不可繞過。

## 8. 三層架構目標圖（v1.24 討論基礎）

> 狀態：**v1.24 已實施**（`document.py`）。對應設計文件 §14（語言無關契約）；本節是程式碼層面的落地圖。

```
╔═ 應用層 ═══════════════════════════════════════════════════╗
║  shell（tkinter 殼）            呈現核心（headless 繪圖）      ║
║  app.py：手勢→命令、對話框、     elements / engine / backends  ║
║  暫態(工具/選取/hover/marquee)、 export（讀 model 畫圖，不寫）  ║
║  request_render、EPS 快照                                    ║
╚═══════╤══════════════════════════════════▲═════════════════╝
        │ ① 命令（純資料,sid/gid/nid）        │ ③ changed(scope) 事件
        ▼                                   │    （注入的 scheduler 合併派發）
╔═ 傳遞層 ═══════════════════════════════════╧═══════════════╗
║  document.py：命令目錄(§14.3)、驗證、undo 快照、              ║
║               begin/commit 手勢交易、subscribe/事件派發       ║
║  jobs.py（未來）：worker thread + queue（VCD/大檔/高倍PNG）   ║
╚═══════╤════════════════════════════════════════════════════╝
        │ ② 內部方法呼叫（唯一允許進入邏輯層的寫路徑）
        ▼
╔═ 邏輯層 ═══════════════════════════════════════════════════╗
║  model.py（單一 Model，函式分類見 §7）                        ║
║  layout 純函式 + 命中測試數學（自 app 下放）   templates.py    ║
╚════════════════════════════════════════════════════════════╝

共用底盤（無方向性）：theme.py、geometry.py（純值物件/常數）
讀路徑（CQRS）：engine.draw(model, geom) 唯讀直通邏輯層，不過傳遞層
```

### 邊界規則（import 方向矩陣；v1.24 起以 AST 測試強制）

| 層 | 准 import | 禁止 |
|---|---|---|
| 共用底盤 | （無） | 任何套件內模組 |
| 邏輯層（model/templates） | 共用底盤 | document / engine / app、tkinter |
| 傳遞層（document） | 邏輯層、共用底盤 | engine / backends / app、**tkinter**（scheduler 注入） |
| 呈現核心（elements/engine/backends/export） | 邏輯層（唯讀）、共用底盤 | document、app、tkinter |
| shell（app） | 全部 | — |

### 已定案的設計決策

1. **命令同步執行、事件非同步合併**（方案 B）：shell 下完命令立刻可讀回新狀態；
   `changed(scope)` 走注入的 scheduler（tk 下= `after_idle`，測試下=同步呼叫）合併派發。
   真正耗時工作（VCD/大檔）另走 `jobs.py` 的 worker queue，與命令通道分離。
2. **具名方法外皮 + `_apply` 單一咽喉**：`doc.set_cell(...)` 等方法內部統一走
   `_apply(name, args)`（執行→驗 §2.6 不變量→undo 快照→排程事件）；命令即資料，
   未來錄製/重播免改呼叫端。
3. **`begin()/commit()` 手勢交易**：一次筆刷（press→release）= 一個 undo 單位 =
   至多一個事件（R5），拖曳中即時生效的手感不變。
4. **事件 scope 先粗粒度**：`{cells, structure, annotations, document}`，全部映射到
   `request_render`；增量重繪需要 dirty-rows payload 時再細化。
5. **CQRS**：寫嚴格走 document；讀（engine/layout/命中測試）唯讀直通 model。
6. **暫態歸 shell**：工具/選取/hover/marquee/拖曳狀態不進文件、不持久化、不可 undo。

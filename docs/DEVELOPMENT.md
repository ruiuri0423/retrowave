# RetroWave 開發者指南（DEVELOPMENT.md）

> **文件分工**：`RetroWave_Design.md` 是**語言無關的設計規格**（概念、演算法、不變量、協定），
> 不含任何 Python/tkinter 字眼；本文件則以**程式碼對應**的手法解釋同一份設計 —
> 設計章節 ↔ 實際符號（class/method）。改了程式請回頭核對兩份文件。
> `README.md` 面向使用者；`CLAUDE.md` 面向 AI 助手；`COWORK_INSTRUCTIONS.md` 是收尾同步流程。

## 1. 環境與常用指令

- **Python 3.8+**，需含 `tkinter`（CPython 內建；部分 Linux 需 `sudo apt install python3-tk`）。
- 選配：`pip install pillow`（只有 PNG 匯出需要）、`pip install pytest`（開發必裝）。

```bash
python src/retrowave.py        # 啟動（開啟示範波形）
python -m pytest               # 全部測試（~54 個，<1s；GUI 測試會短暫開視窗）
python -m pytest tests/test_model.py -k group        # 跑子集
python -c "import ast; ast.parse(open('src/retrowave.py',encoding='utf-8').read())"  # 語法檢查
```

**提交門檻**：pytest 全綠 + 語法檢查通過，缺一不可。

## 2. 程式碼地圖（設計章節 ↔ 符號）

全部程式碼都在 `src/retrowave.py`（單檔，由上而下分層）。對照表以符號名為準（行號會漂移，請用搜尋）：

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
| §9 匯出 | `App.do_export`、`_export_png` / `_export_svg` / `_export_wavedrom` | EPS 用 `wave_cv.postscript`（須同步 render） |
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
   `retrowave.py`（檔頭 docstring、視窗標題、關於對話框）、設計文件（`Spec version` + §15 Changelog 最上方新增一條）、`README.md`（若影響使用者）。
3. Commit 格式：`vX.Y: <一句話摘要>`，內文條列重點。
4. Push 前向 owner 確認（見 `COWORK_INSTRUCTIONS.md`）；禁止 force-push。

### 測試撰寫須知

- `tests/test_model.py`：純 Model 測試，不開視窗；**每個變更型測試最後呼叫 `check(model)`**（= `assert_invariants`）。
- `tests/test_app_interactions.py`：用 `Ev` 假事件驅動真實 handler（`on_press`/`on_motion`/`on_release`），座標用 `cell_xy(app, row, period)` 算。
- ⚠️ **整個 session 共用一個 Tk root**（`conftest._root`，session scope）：同一行程反覆 create/destroy `Tk()` 會觸發 Tcl 的 `tcl_findLibrary` 錯誤。新 GUI 測試一律拿 `app` fixture（每測前自動重置狀態），**不要自己 new `retrowave.App()`**。
- 會彈對話框的路徑（BUS 改值、關係線標籤、各 messagebox）不要在測試中觸發。

## 5. UI ↔ Core 切分現況（protocol 違規清單）

設計文件 §14 已定義 protocol（R1–R5）。**目前程式尚未遵守**，已知違規（重構時逐一消除）：

| 違規點 | 行為 | 違反 |
|---|---|---|
| `App.do_paste`（訊號貼上） | 直接 `model.signals.append` + `group_tree.insert` + `_new_sid` + `_after_tree_change` | R1 |
| `App._insert_template` | 同上手法繞過所有封裝 | R1 |
| `App._paste_group` | 直接組樹節點 | R1 |
| 各互動 handler | 變更後自行呼叫 `request_render()`（核心不發事件，靠 UI 記得重繪） | R2/事件缺失 |
| 群組選單操作 | 直接改 `model.groups[gid]["collapsed"/"color"/"name"]` | R1 |
| `set_cell` 粒度 | 一次筆刷 = N 次 `set_cell`（無 stroke 級命令） | R5 |

## 6. 重構路線圖（依 §14 protocol 重塑架構）

每段獨立 commit + push，全程 54+ 測試保護；失敗退回上一 commit 重試。

| 版本 | 內容 | 驗收門檻 |
|---|---|---|
| **v1.22** | **套件拆分**：`src/retrowave.py` → `src/retrowave/` 套件（`model` / `elements` / `engine` / `backends` / `templates` / `geometry` / `theme` / `app`），行為零變更 | 既有測試原樣全綠 + 新增邊界測試：核心模組匯入後 `tkinter not in sys.modules` |
| **v1.23** | **匯出抽離**：`_export_png/svg/wavedrom` → `export.py` 純函式 `(model, geom) → file` | 新增匯出單元測試（SVG 內容、WaveDrom schema、PNG 尺寸） |
| **v1.24** | **命令層**：`document.py` 實作 §14.3 命令目錄 + §14.4 change events；App 全部改走命令；消除上表違規 | 邊界測試：App 原始碼不得出現 `model._` 與直接結構操作；命令層 headless 測試 |
| **v1.25** | **Undo/Redo**：快照式（§14.5），`Ctrl+Z/Y` | 手勢級 undo 測試（一次筆刷 = 一步） |
| 後續 | 增量重繪（dirty rows，靠 §14.4 scope）、App controller 拆分、VCD import | — |

### 已知技術債（上表未涵蓋）

- `App` 仍是 1,400+ 行上帝類別（96 方法）— v1.24 後拆 controller。
- 選取/hover 等暫態與文件內容混在 App 屬性裡 — 命令層引入時順勢歸類（§14.1）。
- PNG 匯出的虛線網格目前是實線（PIL 後端無 dash）— roadmap 既有項目。

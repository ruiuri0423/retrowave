# -*- coding: utf-8 -*-
"""Traditional Chinese (zh-TW) catalog. Keys are the English source strings.

NOTE: this file intentionally contains Chinese text — it is a translation
resource, the one sanctioned exception to the English-only source rule.
"""
TRANSLATIONS = {
    # ---- mandatory seed entries (keep) ----
    "Language": "語言",
    "Experimental": "實驗功能",
    "Gesture mode (select cell, then pick element)": "手勢模式（先選格，再選元件）",
    " Gesture mode ON: tap a cell to pick an element; long-press = pan":
        " 手勢模式開啟：點一格挑選元件；長按=平移畫布",
    " Gesture mode off": " 手勢模式關閉",
    "Interactive tutorial": "互動教學",
    "Language preference saved. Restart RetroWave to apply.":
        "語言偏好已儲存，重新啟動 RetroWave 後生效。",

    # ---- window title ----
    "RetroWave - Digital Waveform Editor": "RetroWave - 數位波型繪製工具",

    # ---- menubar: menubuttons ----
    "File": "檔案 (File)",
    "Template": "範本 (Template)",
    "Help": "說明 (Help)",

    # ---- File menu ----
    "New...": "新增… (New)",      # menu item (opens a confirm dialog)
    "New": "新增 (New)",          # dialog title (no ellipsis)
    "Load...": "開啟… (Load)",
    "Save...": "儲存… (Save)",
    "Import Template...": "匯入範本… (Import Template)",
    "Export Image...": "匯出圖片… (Export)",
    "Import WaveDrom JSON...": "匯入 WaveDrom JSON…",
    "Export WaveDrom JSON...": "匯出 WaveDrom JSON…",
    "Import WaveDrom JSON": "匯入 WaveDrom JSON",
    "Import Failed": "匯入失敗",
    " Imported WaveDrom ({n} signals)": " 已匯入 WaveDrom（{n} 條訊號）",
    "Exit": "離開 (Exit)",

    # ---- Help menu (already-wrapped + new) ----
    "Usage": "使用說明",
    "Shortcuts": "快捷鍵",
    "About RetroWave": "關於 RetroWave",

    # ---- Template menu ----
    "Remove Template": "移除範本",
    "(No templates yet)": "(尚無範本)",
    "Save Current Canvas as Template...": "將目前畫布存成範本…",

    # ---- startup templates warning ----
    "unknown path": "路徑未知",
    "Template Loading": "範本載入",
    "The following template files could not be found and were removed from the list:\n\n{lines}":
        "以下範本檔案找不到，已從清單移除：\n\n{lines}",

    # ---- import template ----
    "Import Template (JSON)": "匯入範本 (JSON)",
    "Waveform JSON": "波型 JSON",
    "All Files": "所有檔案",
    "Not a valid waveform JSON (missing signals field)": "不是有效的波型 JSON（缺 signals 欄位）",
    "Import Template Failed": "匯入範本失敗",
    "Import Template": "匯入範本",
    "Template name:": "範本名稱:",
    "Template \"{name}\" added.\n(This template loads automatically every time "
    "the tool opens; pick it from the Template menu to insert it as a group.)":
        "已加入範本「{name}」。\n（此範本會在每次開啟工具時自動載入，"
        "從 Template 選單點選即可插入為群組。）",

    # ---- save as template ----
    "Save Current Canvas as Template": "將目前畫布存成範本",
    "Save as Template Failed": "存成範本失敗",
    "Save as Template": "存成範本",
    "Template": "範本",
    "Saved as template \"{name}\".": "已存成範本「{name}」。",

    # ---- remove / insert template ----
    " Removed \"{name}\" from the template library (the original file is unaffected)":
        " 已從範本庫移除「{name}」（原檔案不受影響）",
    "Insert Template Failed": "插入範本失敗",
    "Read failed; the file may have been moved or deleted.\n{path}\n\n{ex}":
        "讀取失敗，檔案可能已移動或刪除。\n{path}\n\n{ex}",
    "Insert Template": "插入範本",
    "This template has no signals.": "此範本沒有任何訊號。",
    " Inserted template \"{gname}\" ({n} signals, grouped)":
        " 已插入範本「{gname}」（{n} 條，已成群組）",

    # ---- toolbar ----
    "Width": "寬度",
    "Row H": "列高",
    "Slope%": "斜率%",
    "Periods": "週期",
    "Element:": "元件:",
    "+ Signal": "＋訊號",
    "(right-click a signal for actions)": "(訊號右鍵：調色/位移/群組/改名/刪除；點群組標頭折疊)",

    # ---- set offset dialog ----
    "Set Offset": "設定位移",
    "Offset (0 ~ 0.95 of a period):": "位移 (0 ~ 0.95 週期):",

    # ---- fill ----
    "Fill BUS": "填入 BUS",
    "Data value for this range:": "此範圍的資料值:",
    "Filled {t}": "已填入 {t}",
    " (selection kept, Esc to clear)": "（選取保留，Esc 清除）",

    # ---- status: pan / brush ----
    " Pan mode | Left-drag = pan canvas | Shift/Ctrl+left-drag = box-select "
    "| Click an element button or number key to draw | Periods {n}":
        " 拖曳模式 | 左鍵拖曳=平移畫布 | Shift/Ctrl+左鍵拖曳=框選 "
        "| 點元件鈕或數字鍵回繪製 | 週期{n}",
    "Click/drag = draw BUS (existing BUS kept, non-BUS replaced); click same cell again = edit value":
        "點/拖曳=畫BUS(原為BUS保留, 非BUS取代);再點同格=改值",
    "Click/drag to paint (row-locked)": "點/拖曳上色(鎖列)",
    " Brush: {tool} | {hint} | Shift/Ctrl drag = box-select (press element key to fill / Ctrl+C to copy) "
    "| Name Ctrl/Shift multi-select -> right-click: color/offset/delete | Esc = pan mode | Periods {n}":
        " 筆刷:{tool} | {hint} | Shift/Ctrl拖曳=框選(按元件鍵填入/Ctrl+C複製) "
        "| 名稱Ctrl/Shift多選 -> 右鍵: 調色/位移/刪除 | Esc=拖曳模式 | 週期{n}",

    # ---- relationship line creation ----
    "Relationship Line": "關係線",
    "Label (optional, e.g. t_su):": "標籤 (可留空，例如 t_su):",
    " Created relationship line {frm} -> {to}": " 已建立關係線 {frm} → {to}",
    " Box-selected; press an element key to fill, or Ctrl+C to copy":
        " 已框選；按元件鍵填入、或 Ctrl+C 複製",

    # ---- wave context menu ----
    "Delete anchor {nid}": "刪除錨點 {nid}",
    "Edit label...": "編輯標籤…",
    "Double arrow (measurement)": "雙箭頭（量測）",
    "Single arrow (causal)": "單箭頭（因果）",
    "No arrow (measurement line)": "無箭頭（量測線）",
    "Arrow style": "箭頭樣式",
    "Delete relationship line": "刪除關係線",
    "Create anchor here": "在此建立錨點",
    "Clear to L": "清成 L",

    # ---- anchor / edge status ----
    " Created anchor {nid} (drag an anchor to draw a relationship line; Del to delete)":
        " 已建立錨點 {nid}（拖曳錨點可拉關係線；Del 刪除）",
    " Deleted anchor {nid}": " 已刪除錨點 {nid}",
    "Relationship Line Label": "關係線標籤",
    "Label:": "標籤:",
    " Deleted relationship line": " 已刪除關係線",
    " Relationship line style: {label}": " 關係線樣式：{label}",
    "double arrow": "雙箭頭",
    "single arrow (causal)": "單箭頭因果",
    "no-arrow measurement": "無箭頭量測",

    # ---- BUS data edit ----
    "BUS Data": "BUS 資料",
    "Enter data value:": "輸入資料值:",

    # ---- copy / paste status ----
    " Copied {n} signals; Ctrl+V pastes after the selected row":
        " 已複製 {n} 條訊號；Ctrl+V 貼在選取列之後",
    " Copied {rows}x{cols} waveform; move to the target cell and Ctrl+V to paste":
        " 已複製 {rows}x{cols} 波形；移到目標格 Ctrl+V 貼上",
    " Pasted {n} signals (copies are ungrouped)":
        " 已貼上 {n} 條訊號（複本未分組）",
    " Pasted waveform at signal {s} T{p}": " 已貼上波形於 訊號{s} T{p}",

    # ---- color ----
    "Signal Color": "訊號顏色",
    "Group Color": "群組顏色",

    # ---- name drag move status ----
    " Moved signal": " 已移動訊號",
    " Moved {n} signals": " 已移動 {n} 條訊號",
    " (merged into group)": "（併入群組）",
    " (moved to top level)": "（移到頂層）",
    " Moved group": " 已移動群組",
    " (nested as a subgroup)": "（巢狀為子群組）",
    " (top level)": "（頂層）",

    # ---- group header menu ----
    "Expand": "展開",
    "Collapse": "折疊",
    "Group color...": "群組調色…",
    "Set group offset...": "設定群組位移…",
    "Rename group...": "重新命名群組…",
    "Merge into group": "合併至群組",
    "Copy group": "複製群組",
    "Paste group": "貼上群組",
    "Dissolve group (keep members)": "解散群組（保留成員）",
    "Delete group (with members)": "刪除群組（含成員）",

    # ---- signal menu ----
    " ({n} signals)": "（{n} 條）",
    "Color...": "調色…",
    "Clear color": "清除顏色",
    "Set offset...": "設定位移…",
    "Create new group...": "建立新群組…",
    "Remove from group": "移出群組",
    "Rename...": "重新命名…",
    "Delete signal": "刪除訊號",

    # ---- rename signal ----
    "Rename": "改名",
    "Signal name:": "訊號名稱:",

    # ---- group operations ----
    "Create New Group": "建立新群組",
    "Group name:": "群組名稱:",
    "Group": "群組",
    " Created group \"{nm}\" ({n} signals); click the header to collapse":
        " 已建立群組「{nm}」（{n} 條）；點標頭可折疊",
    " Merged into group \"{nm}\" ({n} signals)": " 已併入群組「{nm}」（{n} 條）",
    " Nested the group into \"{nm}\"": " 已將群組巢狀至「{nm}」",
    " Cannot merge (cannot move into its own subgroup)": " 無法合併（不可移入自己的子群組）",
    " Removed {n} signals (color reset to default)": " 已移出 {n} 條訊號（顏色回預設）",
    " The selected signals are not in any group": " 選取的訊號不在任何群組中",
    " Group dissolved (members/subgroups kept, promoted one level)":
        " 已解散群組（成員/子群組保留、提升一層）",
    "Delete Group": "刪除群組",
    "Delete group \"{nm}\" and its {n} signals?": "確定刪除群組「{nm}」及其 {n} 條訊號？",
    " Deleted group \"{nm}\" and {n} signals": " 已刪除群組「{nm}」及 {n} 條訊號",
    "Group Offset": "群組位移",
    "Offset (0 ~ 0.95, applied to the whole group including subgroups):":
        "位移 (0 ~ 0.95，整組含子群組套用相同值):",
    " Group offset set to {v} for the whole group ({n} signals)":
        " 群組整組位移設為 {v}（{n} 條）",
    " Copied group \"{nm}\" ({n} signals); Ctrl+V to paste":
        " 已複製群組「{nm}」（{n} 條）；Ctrl+V 貼上",
    " Pasted group \"{gname}\" ({n} signals, new group at the bottom)":
        " 已貼上群組「{gname}」（{n} 條，新群組於底部）",
    "Rename Group": "群組改名",

    # ---- signal add / delete ----
    "Delete Signals": "刪除訊號",
    "Delete the {n} selected signals?": "確定刪除選取的 {n} 條訊號？",

    # ---- undo / redo ----
    "Undone": "已復原",
    "Redone": "已重做",
    " Nothing to undo": " 沒有可復原的步驟",
    " Nothing to redo": " 沒有可重做的步驟",
    " {verb} (undo {u}/{depth}, redo {r})": " {verb}（可復原 {u}/{depth}、可重做 {r}）",

    # ---- new / save / open ----
    "Clear the current content and start a new document?": "清空目前內容並新建？",
    "Save": "儲存",
    "Saved:\n{path}": "已儲存:\n{path}",
    " Opened; detected unmappable annotations, removed {cn} anchors and {ce} relationship lines":
        " 已開啟；偵測到無法對應的標注，已清除錨點 {cn}、關係線 {ce}",
    "Open Failed": "開啟失敗",

    # ---- export ----
    "PNG Image": "PNG 圖片",
    "SVG Vector": "SVG 向量圖",
    "EPS Vector": "EPS 向量圖",
    "PostScript": "PostScript",
    "PNG Resolution": "PNG 解析度",
    "Scale (1~4, higher = sharper):": "倍率 (1~4，越大越清晰):",
    "Export": "匯出",
    "Exported PNG ({scale}x resolution):\n{path}": "已輸出 PNG（{scale}× 解析度）:\n{path}",
    "PNG export only needs Pillow (Ghostscript not required).\nPlease install it first:\n  pip install pillow":
        "PNG 匯出只需要 Pillow（不需要 Ghostscript）。\n請先安裝：\n  pip install pillow",
    "Export Failed": "匯出失敗",
    "Exported SVG (vector, infinitely scalable):\n{path}": "已輸出 SVG（向量、可無限縮放）:\n{path}",
    "Exported:\n{path}": "已輸出:\n{path}",
    "Export WaveDrom JSON": "匯出 WaveDrom JSON",
    "Export WaveDrom": "匯出 WaveDrom",
    "Exported WaveDrom JSON:\n{path}\n\n"
    "You can paste it into wavedrom.com or render it with wavedrom-cli.\n"
    "Note: visuals such as color and uniform slope are redrawn by WaveDrom and not preserved.":
        "已輸出 WaveDrom JSON：\n{path}\n\n"
        "可貼到 wavedrom.com 或用 wavedrom-cli 算圖。\n"
        "註：顏色與統一斜率等視覺由 WaveDrom 自行重畫，不會保留。",

    # ---- about ----
    "About": "關於",
    "RetroWave v{v}\nDigital circuit waveform editor\nPython + tkinter":
        "RetroWave v{v}\n數位電路波型繪製工具\nPython + tkinter",

    # ---- help: usage (long text) ----
    "[Drawing waveforms] After picking an element: click a cell to draw it; drag to brush along the starting row (row-locked).\n"
    "  - BUS: cells that are already BUS keep continuing; only non-BUS cells become BUS.\n"
    "         Click the same cell again to enter/edit the data value.\n"
    "[Box-select (canvas)] Shift or Ctrl + drag is always pure box-select:\n"
    "  - After selecting, press an element key = fill the block (BUS asks for text once).\n"
    "  - Ctrl+C to copy; move to the target cell and Ctrl+V to paste (rows are added automatically if you run past the end).\n"
    "[Name column] Click to select signals (Ctrl/Shift for multi-select); press and drag up/down to move:\n"
    "  - Drag to the lower half of a group header / inside the group = merge into that group (the cursor position is the insertion point; merge + reorder in one go).\n"
    "  - Drag to the upper half of a group header = move before that group (same level); drag between top-level signals = move out to the top level.\n"
    "  - Drag a group header = move the whole group; dropping it on another group nests it as a subgroup (cannot drop into its own descendants).\n"
    "  - While dragging, the background dims, the target container lights up, and an insertion line is shown.\n"
    "  - Right-click a group header: collapse/color/group offset/copy/merge (nest)/dissolve/delete (with members).\n"
    "  - Nesting: a signal's right-click \"Merge into group\" adds it in; a group's right-click \"Merge into group\" makes it a subgroup.\n"
    "[Annotations] Right-click a waveform -> \"Create anchor here\" (snaps to the nearest cell edge).\n"
    "  - Hovering over an anchor highlights it; press and drag from an anchor to another anchor to create a relationship line\n"
    "    (while dragging, the waveform dims and freezes to highlight the foreground); enter a label on release (e.g. t_su).\n"
    "  - Anchors/relationship lines: hover to highlight, then press Del to delete; right-click a relationship line to change its label/arrow style.\n"
    "[Pan mode] Press Esc to fall back to pan mode (deselect element, clear box-select):\n"
    "  - Left-drag = pan the canvas (no accidental drawing).\n"
    "  - Shift/Ctrl + left-drag = box-select (same as draw mode).\n"
    "  - Click an element button or press number keys 1~6 to return to draw mode.\n"
    "[Offset] After shifting offset right, the left edge auto-extends the first cell's level and the right end is trimmed flush, giving a sense of continuity.\n"
    "[Export] Images PNG (1-4x)/SVG (vector)/EPS; you can also export the WaveDrom JSON interchange format.\n"
    "[Other] Right-click a waveform also offers \"Clear to L\"; double-click a name to rename; Esc falls back to pan mode and clears box-select.":
        "[畫波形]選元件後：點一格畫一格；拖曳沿起始列刷 (鎖列)。\n"
        "  · BUS：原本是 BUS 的格會保留延續；非 BUS 的格才轉成 BUS。\n"
        "         再點同格可輸入/修改資料值。\n"
        "[框選 (畫布)]Shift 或 Ctrl + 拖曳都是純框選：\n"
        "  · 框選後按元件鍵 = 整塊填入 (BUS 問一次文字)。\n"
        "  · Ctrl+C 複製、移到目標格 Ctrl+V 貼上 (超出列數自動新增列)。\n"
        "[名稱欄]點選訊號 (Ctrl/Shift 多選)；按住上下拖曳可移動：\n"
        "  · 拖到群組標頭下半/群組內 = 併入該群組(游標位置即插入點，合併+排序一次到位)。\n"
        "  · 拖到群組標頭上半 = 移到該群組之前(同層)；拖到頂層訊號間 = 移出到頂層。\n"
        "  · 拖群組標頭 = 整組移動，落在另一群組上即巢狀為子群組(不可落入自己子孫)。\n"
        "  · 拖曳時背景反灰、點亮將落入的容器並顯示插入線。\n"
        "  · 群組標頭右鍵：折疊/調色/群組位移/複製/合併(巢狀)/解散/刪除(含成員)。\n"
        "  · 巢狀：訊號右鍵「合併至群組」可放入；群組右鍵「合併至群組」成為子群組。\n"
        "[標注]波形右鍵 →「在此建立錨點」(吸附到最近的格邊緣)。\n"
        "  · 游標移到錨點上會高亮；按住錨點拖曳到另一錨點即建立關係線\n"
        "    (拉線時波形會反灰冷凍，凸顯前景)；放開後輸入標籤 (如 t_su)。\n"
        "  · 錨點/關係線：游標移上去高亮後按 Del 刪除；關係線右鍵可改標籤/箭頭樣式。\n"
        "[拖曳模式]按 Esc 退回拖曳模式（取消元件選擇、清除框選）：\n"
        "  · 左鍵拖曳 = 平移畫布（不會誤畫元件）。\n"
        "  · Shift/Ctrl + 左鍵拖曳 = 框選（與繪製模式相同）。\n"
        "  · 點元件鈕或按 1~6 數字鍵即回到繪製模式。\n"
        "[位移]右移 offset 後左緣自動延伸第一格準位、右端裁齊，呈現延續感。\n"
        "[匯出]圖片 PNG(1–4×)/SVG(向量)/EPS；另可匯出 WaveDrom JSON 交換格式。\n"
        "[其他]波形右鍵亦可「清成 L」；雙擊名稱改名；Esc 退回拖曳模式並清除框選。",

    # ---- help: shortcuts (long text) ----
    "Ctrl+N/O/S/E New/Open/Save/Export   Ctrl+C/V Copy/Paste\n"
    "Ctrl+Z/Y Undo/Redo (last 5 steps; one brush/fill/paste = one step)\n"
    "1~6 Switch element (CLK/H/L/BUS/HiZ/Unknown)\n"
    "Esc Pan mode (deselect element/clear box-select); in pan mode left-drag = pan canvas\n"
    "Shift/Ctrl+drag Box-select (works in both modes)   Press an element key = fill the selection\n"
    "Name column Ctrl/Shift+click for multi-select -> right-click menu (color/offset/group/rename/delete)\n"
    "Right-click a waveform Create anchor/Clear to L; drag an anchor to draw a relationship line; Del deletes annotations\n"
    "Double-click a name to rename":
        "Ctrl+N/O/S/E 新增/開啟/儲存/匯出   Ctrl+C/V 複製/貼上\n"
        "Ctrl+Z/Y 復原/重做（最近 5 步；一次筆刷/填入/貼上=一步）\n"
        "1~6 切換元件 (CLK/H/L/BUS/HiZ/Unknown)\n"
        "Esc 拖曳模式(取消元件選擇/清除框選)；拖曳模式下左鍵拖曳=平移畫布\n"
        "Shift/Ctrl+拖曳 框選(兩種模式皆可)   按元件鍵=填入框選\n"
        "名稱欄 Ctrl/Shift+點擊 多選 -> 右鍵選單(調色/位移/群組/改名/刪除)\n"
        "波形右鍵 建立錨點/清成L；拖曳錨點拉關係線；Del 刪除標注\n"
        "雙擊名稱 改名",

    # ---- tutorial steps (tutorial.py + app.py _tutorial_steps) ----
    "Welcome to RetroWave": "歡迎使用 RetroWave",
    "This is a retro-style digital timing / waveform editor.\n"
    "The next few steps walk you through the main operations - the highlighted area "
    "is what you can act on right now, so feel free to try it directly.\n\n"
    "(Press Esc or \"Skip\" any time to end the tutorial.)":
        "這是一支復古風的數位時序／波形編輯器。\n"
        "接下來用幾步帶你認識主要操作 — 亮起的區域就是當下可以動手的地方，"
        "你可以直接在上面操作試試。\n\n（隨時按 Esc 或「略過」結束教學）",
    "Element Toolbar": "元件工具列",
    "Pick an element (or press number keys 1-6): CLK clock, H high level, L low level, "
    "BUS data bus, HiZ high impedance, Unknown.\n"
    "\"+ Signal\" adds a new signal row. Once an element is selected you can draw "
    "waveforms on the canvas to the right.":
        "點選元件（或按數字鍵 1~6）：CLK 時脈、H 高準位、L 低準位、"
        "BUS 資料匯流排、HiZ 高阻抗、Unknown 未知。\n"
        "「＋訊號」新增一條訊號列。選好元件後就能在右側畫布上畫波形。",
    "Waveform Canvas": "波形畫布",
    "Click a cell to draw it; press and drag to brush along the same row (row-locked, no slips).\n"
    "Click a BUS cell again to enter its data value.\n"
    "Shift/Ctrl + drag = box-select (press an element key to fill the block, Ctrl+C/V to copy and paste).\n"
    "Right-click to create an anchor; drag from one anchor to another to draw a measurement / relationship line.":
        "點一格畫一格；按住拖曳沿同一列連刷（鎖列不怕手抖）。\n"
        "BUS 格再點一次可輸入資料值。\n"
        "Shift/Ctrl + 拖曳 = 框選（按元件鍵整塊填入、Ctrl+C/V 複製貼上）。\n"
        "右鍵可建立錨點，按住錨點拖到另一錨點 = 拉量測/關係線。",
    "Signal Name Column": "訊號名稱欄",
    "Select signals (Ctrl/Shift for multi-select); right-click menu: color, offset, create group, rename, delete.\n"
    "Press and drag a name up/down to reorder; drag into a group = merge in, drag to the empty space at the bottom = move out of the group.\n"
    "Click a group header to collapse/expand the whole group.":
        "點選訊號（Ctrl/Shift 多選）；右鍵選單：調色、位移、建立群組、改名、刪除。\n"
        "按住名稱上下拖曳可重排，拖進群組 = 併入、拖到最下方空白 = 移出群組。\n"
        "點群組標頭可折疊/展開整組。",
    "Geometry and Periods": "幾何與週期",
    "Adjust cell width, row height, transition slope ratio and period count - the view updates instantly.\n"
    "These are view settings and are saved together with the project JSON.":
        "調整格寬、列高、轉換斜率比例與週期數，畫面即時反映。\n"
        "這些屬於檢視設定，會跟著專案 JSON 一起存檔。",
    "A Few Last Tricks": "最後幾招",
    "Esc = pan mode (left-drag pans the canvas, no accidental drawing).\n"
    "Ctrl+Z / Ctrl+Y = undo / redo (last 5 steps, one gesture counts as one step).\n"
    "The File menu lets you save (JSON) and export PNG/SVG/EPS and WaveDrom.\n"
    "To see the tutorial again later: Help -> Interactive tutorial.":
        "Esc = 拖曳模式（左鍵平移畫布，不會誤畫）。\n"
        "Ctrl+Z / Ctrl+Y = 復原 / 重做（最近 5 步，一次手勢算一步）。\n"
        "File 選單可存檔（JSON）、匯出 PNG/SVG/EPS 與 WaveDrom。\n"
        "之後想重看教學：Help → 使用教學。",

    # ---- tutorial overlay buttons (tutorial.py, already wrapped there) ----
    "Skip (don't show again)": "略過（不再顯示）",
    "◀ Back": "◀ 上一步",
    "Next ▶": "下一步 ▶",
    "Finish": "完成",
    "Don't show this tutorial again": "下次啟動不再顯示這個教學",

    # ---- text window close button ----
    "Close": "關閉",
}

# Shortcuts table (key reproduced exactly from app.help_keys)
TRANSLATIONS['[File]\n  Ctrl+N            New\n  Ctrl+O            Open\n  Ctrl+S            Save\n  Ctrl+E            Export image\n[Edit]\n  Ctrl+Z            Undo (last 5 steps; one gesture = one step)\n  Ctrl+Y            Redo\n  Ctrl+C            Copy (cells / signals / group)\n  Ctrl+V            Paste (auto-adds rows when needed)\n[Drawing]\n  1 - 6             Pick element (CLK / H / L / BUS / HiZ / Unknown)\n  Click / drag      Paint a cell / brush along the row (row-locked)\n  Shift/Ctrl + drag Box-select (then press an element key to fill)\n  Esc               Pan mode (left-drag pans; clears box-select)\n[Name column]\n  Click             Select a signal\n  Ctrl/Shift+click  Multi-select\n  Drag              Reorder / merge into group / move out (multi-select OK)\n  Double-click      Rename\n  Right-click       Menu: color / offset / group / rename / delete\n[Annotations]\n  Right-click wave  Create anchor / Clear to L\n  Drag anchor       Draw a relationship line to another anchor\n  Del               Delete the annotation under the cursor'] = '[檔案]\n  Ctrl+N            新增\n  Ctrl+O            開啟\n  Ctrl+S            儲存\n  Ctrl+E            匯出圖片\n[編輯]\n  Ctrl+Z            復原（最近 5 步；一次手勢 = 一步）\n  Ctrl+Y            重做\n  Ctrl+C            複製（波形格／訊號／群組）\n  Ctrl+V            貼上（需要時自動新增列）\n[繪製]\n  1 - 6             選擇元件（CLK / H / L / BUS / HiZ / Unknown）\n  Click / drag      畫一格／沿列連刷（鎖列）\n  Shift/Ctrl + drag 框選（再按元件鍵填入）\n  Esc               拖曳模式（左鍵平移；清除框選）\n[名稱欄]\n  Click             選取訊號\n  Ctrl/Shift+click  多選\n  Drag              重排／併入群組／移出（可多選）\n  Double-click      改名\n  Right-click       選單：調色／位移／群組／改名／刪除\n[標注]\n  Right-click wave  建立錨點／清成 L\n  Drag anchor       拉關係線到另一錨點\n  Del               刪除游標下的標注'

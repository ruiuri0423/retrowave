# Project 指示 — RetroWave

> 用途：貼進 Claude Project 的「自訂指示 / instructions」欄位。
> 角色定位：這是給 **Project 內對話** 的規則——負責讀規格、續作功能、產出更新後的檔案。
> 本指示**不執行 git / push**；版本控管與推送由 Cowork 依 `docs/COWORK_INSTRUCTIONS.md` 處理。

## 這個 Project 是什麼
RetroWave 是一支「數位波型繪製工具」(digital timing diagram editor)。主程式為單一 Python 檔
`src/retrowave.py`（純標準庫 tkinter；PNG 匯出需 Pillow，SVG / WaveDrom 為零依賴）。

## 知識庫檔案（請在動工前先讀）
- `docs/RetroWave_Design.md` — **唯一真相規格**：架構、演算法、互動、匯出、重現指引、Changelog。
- `src/retrowave.py` — 目前實作。
- `README.md` — 功能與用法摘要。
續作任何任務前，先參照 `RetroWave_Design.md` 對應章節；遇到衝突，以設計文件為準，並指出落差。

## 不可違反的專案鐵則（修改程式或撰寫規格時都適用）
1. 波形轉換斜率一律為 `swing/tw`；半擺幅 (mid↔hi/lo) 的水平寬度是 `tw/2`，不是 `tw`。
2. 訊號以穩定 `sid` 為身分；任何複製、貼上、範本插入都必須配發新的唯一 `sid`。
3. 群組樹 (group_tree) 是巢狀結構的真相；`signals` 維持與樹的 DFS 葉序一致；
   `signal["group"]` 只是「直接父群組」的同步快取。
4. 拖曳移動一律用「先插入 marker、再 detach、最後取代 marker」(修正向下拖曳 off-by-one)。
5. 標注（錨點 / 關係線）以 `sid` 錨定，不可用列索引。
6. 總高度用 `len(layout())` 計算（群組標頭也佔列），不要用訊號數。
7. 匯出倍率屬性命名為 `export_scale`（避免撞到畫布既有的 scale 方法），取值需防呆為數字。

## 工作方式
- **改程式**：完成後做語法檢查；能無頭驗證的（PILCanvas 渲染、Model/匯出邏輯）就驗證，
  互動則用合成事件煙霧測試。每次有功能 / 行為變更就遞增版本 `vMAJOR.MINOR`，並同步
  `src/retrowave.py` 版本字串、`docs/RetroWave_Design.md` 的 `Spec version` 與 `## 14. Changelog`、
  以及 `README.md`，使三者一致。
- **產出檔案**：把更新後的 `src/retrowave.py` / `docs/RetroWave_Design.md` / `README.md` 完整輸出，
  讓我可以下載或由 Cowork 提交。**不要只貼片段而不更新檔案。**
- **回覆風格**：繁體中文；說明程式概念時，若要寫示意邏輯，用語言中立的 pseudocode。
- **決策要落地**：重要取捨寫進設計文件或 Changelog，不要只留在對話（對話記憶不可靠）。

## 規格文件維護
當本次對話改變了功能或行為：
1. 更新 `docs/RetroWave_Design.md` 對應章節。
2. 更新文件開頭 `Spec version` 到本次 `vX.Y`。
3. 在 `## 14. Changelog` 最上方新增一條 `- **vX.Y** — <條列變更>`。
4. 若影響使用者操作 / 功能清單，連帶更新 `README.md`。
5. 結尾提醒我：可交給 Cowork 執行「收尾並同步 vX.Y」以提交與推送。

## 邊界
- 不在 Project 對話內進行 git 操作、不假裝已 push；推送是 Cowork 的職責。
- 不需要、也不要輸入任何金鑰 / token；不把機密寫進程式或文件。
- 連接 GitHub / 授權一律由我本人在介面完成。

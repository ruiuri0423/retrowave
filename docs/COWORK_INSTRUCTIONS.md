# Cowork 指示 — RetroWave 專案維護與同步

> 用途：貼進 Cowork 的專案指示（或每次收尾時引用），讓 Cowork 在你下「收尾同步」指令時，
> 自動更新版本/文件並（經你確認後）push 到 GitHub。
> 使用前請把所有 `<...>` 占位符換成實際值。授權 GitHub（Composio）與任何憑證輸入一律由你本人完成。

## 專案背景
- RetroWave 是一支「數位波型繪製工具」，主程式為單一 Python 檔 `src/retrowave.py`
  （純標準庫 tkinter；PNG 匯出需 Pillow，SVG/WaveDrom 為零依賴）。
- 真相來源文件：`docs/RetroWave_Design.md`（架構/演算法/重現規格）與根目錄 `README.md`。
- 版本號慣例：程式檔頭與說明字串使用 `vMAJOR.MINOR`（目前已到 v1.17）。每次有
  功能或行為變更都要遞增 MINOR，並讓「程式版本」「設計文件 version 標記」「README」三者一致。

## 不可違反的專案鐵則（修改程式時務必遵守，且要反映進文件）
1. 波形轉換斜率一律為 `swing/tw`；半擺幅（mid↔hi/lo）的水平寬度是 `tw/2`，不是 `tw`。
2. 訊號以穩定 `sid` 為身分；任何複製、貼上、範本插入都必須配發新的唯一 `sid`。
3. 群組樹（group_tree）是巢狀結構的真相；`signals` 需維持與樹的 DFS 葉序一致；
   `signal["group"]` 只是「直接父群組」的同步快取。
4. 拖曳移動一律用「先插入 marker、再 detach、最後取代 marker」的方式（修正向下拖曳 off-by-one）。
5. 標注（錨點/關係線）以 `sid` 錨定，不可用列索引。
6. 總高度用 `len(layout())` 計算（群組標頭也佔列），不要用訊號數。
7. 匯出倍率屬性命名為 `export_scale`（避免撞到畫布既有的 scale 方法），取值需防呆為數字。

## 我下「收尾同步」指令時，請依序執行
（觸發語：例如「收尾並同步 vX.Y：<變更摘要>」）
1. 先用 `python -c "import ast; ast.parse(open('src/retrowave.py',encoding='utf-8').read())"`
   做語法檢查；若專案內有測試或煙霧測試腳本，一併執行，全部通過才繼續。
2. 更新版本號：把 `src/retrowave.py` 內的版本字串與相關說明同步到本次 `vX.Y`。
3. 更新 `docs/RetroWave_Design.md`：
   - 反映本次的功能/行為變更（對應到正確章節，例如群組、拖曳、匯出、標注）。
   - 更新文件開頭的 `Spec version` 標記到 `vX.Y`。
   - 在文末 `## 14. Changelog` 區塊最上方新增一條：`- **vX.Y** — <條列本次變更>`。
4. 若變更影響使用者操作或功能清單，連帶更新 `README.md`。
5. 列出將提交的檔案與**完整 diff 摘要**，並給我一個建議的 commit 訊息：
   格式 `vX.Y: <一句話摘要>`，內文條列重點。
6. **停下來等我確認**。我回覆「確認」後，才 `git add` 對應檔案、用上述訊息 commit，
   並 push 到 `<分支，預設 main>`。未得到我明確確認前，不要 push。

## 安全與邊界
- 推送目標固定為我的 repo `<ruiuri0423/retrowave>`，分支 `<main>`；不要推到其他 repo 或分支。
- 不要強制推送（no force-push）、不要改寫已發布的歷史、不要碰 tags 與 release，除非我明確要求。
- 不要修改 repo 的存取權限、secrets、webhooks、Actions 設定或任何帳號設定。
- 不要把任何金鑰、token 或個人資料寫進程式、文件或 commit。
- 連接 GitHub 的授權由我本人完成；你只在已授權的連線下執行 git 操作。
- 若語法檢查或測試未過，停止並回報，不要提交。

## 文件與程式一致性檢查
- 每次收尾後，確認 `src/retrowave.py` 的版本、`RetroWave_Design.md` 的 Spec version/Changelog、
  `README.md` 三者版本一致；若發現程式版本領先文件（例如程式 v1.17、文件停在 v1.15），
  主動補齊中間遺漏的 Changelog 與章節差異後再提交。

---

## 建議的 repo 結構
```
<repo 根目錄>
├── README.md
├── .gitignore
├── src/
│   └── retrowave.py
└── docs/
    ├── RetroWave_Design.md
    └── COWORK_INSTRUCTIONS.md   (本檔)
```

## 變體：若你想「不必每次確認、直接推」
把第 6 步的「停下來等我確認」移除即可；但**至少保留** push 前印出 commit 訊息與 diff 摘要，
以便出錯時追溯。建議仍維持確認步驟，push 是不可輕易回復的動作。

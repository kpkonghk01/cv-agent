# 技術決策簡介（白話版）

這份文件用白話解釋本專案幾個關鍵技術選擇的「**為什麼**」，以及「**為什麼不選別的**」。
正式、精簡的決策留痕見 [`docs/adr/`](./adr/)；本文是給人讀的導覽。

每一節的格式：**決策 → 理由 → 否決的替代方案 → 取捨 / 何時該重新考慮**。

---

## 1. OCR 用 Marker（force-OCR），不用 PaddleOCR、不用視覺 LLM 直接讀

**決策**：CV 先用 **Marker 的 force-OCR 模式**光柵化後重新 OCR，輸出乾淨 Markdown，再交給 LLM 結構化。相關：[ADR 0001](./adr/0001-marker-ocr-llm-structuring.md)。

**為什麼**：
- boss直聘 之類平台匯出的 PDF，**文字層被下毒**（塞不可見水印/假文字防複製分析），還常見**雙欄版面**。
- **force-OCR 會直接放棄被下毒的文字層、只認畫面像素**，從根本上繞過水印；Marker 的版面模型再還原雙欄的閱讀順序。
- Marker 對**表格、雙欄、混排**的處理成熟，且**離線、確定性高、成本可控**。

**為什麼不選 PaddleOCR**：
- PaddleOCR 是**純 OCR 引擎**，給你「文字 + 座標」，但**不還原文件結構/閱讀順序**——雙欄、表格、標題層級要你自己拼。等於還要再寫一層版面重建。
- Marker 是「PDF → 結構化 Markdown」的**端到端**方案（內含 Surya OCR + 版面 + 表格），少維護一整層。
- 補充：Marker 底層的 Surya 本來就是強力 OCR，中文/英文混排都吃，我們不缺 OCR 能力，缺的是**結構還原**。

**為什麼不選視覺 LLM（VL）直接 OCR**：
- 把每頁截圖丟給 VL 模型「一次 OCR + 結構化」很誘人，但**貴、逐頁 token 成本高、且不確定**（同一頁兩次結果可能不同）。
- 招聘場景要**可重現、可離線、可審計**，確定性引擎比 VL 穩。
- 不過我們**保留 VL 當 fallback**（`--ocr-fallback`）：Marker 信心低時再上。而且你本地的模型本身多模態，日後開這條幾乎零成本。

**何時該重新考慮**：若來源 PDF 都很乾淨（無水印、單欄），Marker 這層就顯得重，可退回輕量方案。

---

## 2. LLM 用 BYOK / OpenAI 相容，不「內建拉 HF 模型自己跑」

**決策**：每個 LLM 節點都打一個 **OpenAI 相容端點**（`base_url + api_key + model`），模型由**使用者自備**（Bring-Your-Own-Key）。相關：[ADR 0002](./adr/0002-byok-openai-compatible-model-agnostic.md)。

**為什麼**：
- **關注點分離**：模型的下載、量化、GPU/MPS 排程、記憶體管理是**推理伺服器**（vMLX / vLLM / Ollama…）的專業，不該塞進這個「招聘流程」應用裡。
- **可攜、不綁廠**：本地跑或雲端跑，只是換一個 `base_url`；換模型只是改一行設定。
- **產品與模型解耦**：正式上線用的是**營運者的設定**，產品本身不內含、不強制任何模型（也就不背模型的授權/合規包袱）。

**為什麼不「inline pull HF model 跑」**：
- 一旦在應用內 `from_pretrained` 拉模型自跑，就把 **torch/accelerate/量化/顯存** 全綁進來，部署變重、跨機器難搬、還要處理 OOM 與硬體差異。
- 也**綁死執行環境**：別人想用雲端 API 或現成 server 就用不了。
- BYOK 把「怎麼 host 模型」這個難題**外包給專門工具**，我們只負責「怎麼用模型做對的事」。

**取捨**：使用者要自己起一個推理 server（見 [`vmlx/README.md`](../vmlx/README.md)）。換來的是零廠商鎖定與極簡部署。

---

## 3. 每個節點可各自設定模型（per-node override）

**決策**：一個預設模型 + 可選的**逐節點覆寫**（`STRUCTURE_CV` / `JD_RUBRIC` / `SCREEN` / `INTERVIEW`）。

**為什麼**：四個節點難度差很多——CV 結構化偏機械，可用便宜/本地小模型；面試題生成最需要「聰明」，可指向最強模型。**甚至能不同節點打不同 provider**（結構化打本地 vMLX、面試題打雲端）。這是**成本 / 品質**的細粒度旋鈕，且成本幾乎為零（只是設定）。

---

## 4. Filter 是「帶證據的評分器」，不是「LLM 判官」

**決策**：JD 先拆成 rubric（must-have / nice-to-have 的 requirement），LLM 只**逐條抽證據打分**（Met/Partial/Unmet），最後由**確定性規則**決定 pass/reject。相關：[ADR 0004](./adr/0004-deterministic-workflow-not-autonomous-agents.md)、規則細節見 [AGENT.md](../AGENT.md)。

**為什麼**：
- 用 LLM 對人**直接**判 pass/reject 是**招聘偏見與合規高風險區**（履歷篩選在不少法規被列 high-risk）。
- 「證據 + 分數 + 確定性規則」讓每個判決**可解釋、可重現、可辯護**；審核報告本身就是一張評分表。
- 規則是「**must-have 有 Unmet 才 reject；Partial 算過（偏寬鬆）；nice-to-have 只影響強弱與 borderline 標記**」——寬進嚴出，把關留給後面的面試。

**為什麼不「一個 prompt 丟 JD+CV 讓模型回 pass/reject」**：不可重現、難審計、易偏見，且無法對候選人交代理由。

---

## 5. 用 LangGraph 當「工作流引擎」，不搞自主 agent

**決策**：雖名為 multi-agent，實作是**有狀態的確定性工作流** + 少數結構化 LLM 節點，用 LangGraph 編排。相關：[ADR 0004](./adr/0004-deterministic-workflow-not-autonomous-agents.md)。

**為什麼**：這條流程本質是流水線（OCR→結構化→評分→面試），不需要會自己開迴圈、亂用工具的 agent。確定性工作流**更可靠、可測、便宜、可審計**。LangGraph 的價值在**狀態管理、重試、fan-out、日後的 checkpointer / human-in-the-loop 接縫**，我們就當它是工作流引擎用。

---

## 6. 為什麼要有 JD meta YAML

**決策**：每份 JD 旁可放一個**選用**的 `<jd>.meta.yaml`，覆寫「這個職位怎麼面」（role_archetype、面試形式、時長、語言、嚴格度）。

**為什麼**：
- **一份 JD 天然對應一種面試風格**，把這些設定**跟 JD 綁在一起**最內聚——換 JD 就換整套面試取向，不用每次在命令列重打。
- **全部選填**：不寫 meta 就走預設 + 自動判定（例如 role 由 LLM 讀 JD 自動分技術/管理職）。要覆寫才寫，符合「自動優先、可手動」。
- 保留 **CLI 臨時覆寫**（`--minutes` 等）做單次調整；優先序 **CLI > meta > 預設**。

**為什麼不寫死在程式或 .env**：JD 會變、會有多份（技術職 vs PM），寫死每次要改碼/改環境；放 JD 旁邊，新增一份 JD 就自帶它的面試設定，零程式改動。

---

## 7. cvs / jds / reports 用「界面分離」（ports & adapters）

**決策**：讀取（`Source`）、輸出（`ReportSink`）、通知（`Notifier`）都定義成**抽象埠**，目前用本地資料夾實作，日後換 Google Drive 只加一個 adapter，**流程一行不動**。

**為什麼**：
- 你明講「現在讀 folder，以後可能接 Google Drive / GUI」。把「**做什麼**（列出、讀取、寫出）」跟「**存在哪**（本地/雲端）」分開，就是為了這種**未來替換**。
- **可測試性**：測試時塞假的 Source/Sink，不碰真檔案/網路（我們的測試就是這樣跑到高覆蓋率的）。
- **CV 和 JD 共用同一個 `Source` 埠**——它們本質都是「從某來源讀文件」，差別只是 CV 全讀、JD 挑一份，不必寫兩套。

**取捨**：多一層抽象。但換來的是「換儲存後端 = 寫一個檔案」而非「改整條 pipeline」。

---

## 8. 用 SQLite 存紀錄（三層快取 + 去重）

**決策**：已處理紀錄、Candidate Profile 快取、JD rubric 快取，**三者同一個 SQLite 檔**，各藏在聚焦的埠後面。相關：[ADR 0003](./adr/0003-three-layer-cache-dedup.md)。

**為什麼用 SQLite（而非單一 txt）**：
- 我們要存的不只是「處理過的清單」，還有 **rubric 快取（key-value 查詢）**、verdict、時間、報告路徑——txt 很快就不夠。
- SQLite **零安裝**（Python 內建 `sqlite3`）、單檔、支援結構化查詢與交易，比自己拼 txt 穩太多。
- 一樣包在埠後面，**日後要換 Postgres / 雲端只換實作**。

**為什麼要三層、鍵還不一樣**：
- **OCR + 結構化最貴、且與 JD 無關** → Candidate Profile 用 `cv_hash` 快取，**同一份 CV 面多個 JD 時 OCR 只做一次**。
- **screening 判決與 JD 相關** → 去重用 `(cv_hash, jd_hash)`；同一份 CV 換 JD 要重新審。
- **rubric 與 CV 無關** → 用 `jd_hash` 快取，跨所有 CV 重用。
- 這樣分層讓「一批 CV × 多份 JD」的未來功能**天然便宜**，也讓中斷後重跑**靠冪等自動續跑**（v1 不需 checkpointer）。

**去重鍵為什麼用「檔案 hash + 軟身分」**：檔案內容 hash 最單純、OCR 前就能判斷跳過（省最貴的一步）；同時額外存抽到的姓名/電話當「軟身分」，方便日後升級成「同一個人」的比對。代價：同一人重新匯出 PDF（bytes 變了）會被當新檔——v1 可接受的取捨。

---

## 一句話總結

**把「難且會變的東西」都推到邊界後面**：模型交給推理伺服器（BYOK）、儲存交給可替換的埠（Source/Sink/Store）、面試取向交給 JD 旁的 meta；**核心只保留「可重現、可審計的確定性邏輯」**（rubric 評分、判決規則、去重）。這樣每個未來需求（換雲端、換模型、加通知、多 JD）都是「加一個 adapter / 改一行設定」，而不是「改整條 pipeline」。

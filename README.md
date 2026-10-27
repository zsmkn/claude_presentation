# Claude 大小姐 報告影片產生器

像素風視覺小說式的報告影片：一位主持人加上幾位配角串場（目前有 Claude、GPT、DeepSeek、Gemini），誰主持、誰上鏡都寫在設定檔。
畫面 1920×1080 / 24fps，聲音用 edge-tts，畫面用 Pillow 逐格合成後交給 ffmpeg 編碼。

## 用 GUI 編輯（建議）

```bash
python studio.py
```

所有原本要改程式碼或設定檔的項目都在 GUI 裡，`Ctrl+S` 儲存：

| 分頁 | 內容 | 寫入 |
|---|---|---|
| 01 劇本 | 段落（頻道、標題、截圖、NOTE 小抄、整段在台的配角）、台詞（講者、表情、文字、鏡頭、換圖）。右側截圖上可以直接拖曳／滾輪框鏡頭；可播放單句語音、預覽單句成品畫面 | `story.json` |
| 02 蓋章 | 台詞包含某字串時右上角跳出的螢光標籤，並列出每個標籤命中哪幾句 | `story.json` |
| 03 演出 | 片頭大標／副標／右上角小字、主持人、上鏡配角與站位順序（含站位示意圖） | 報告的 `config.toml` |
| 04 角色 | 角色名冊：名牌名稱與顏色、edge-tts 聲線／語速／音高（可試聽）、像素立繪、片頭角色卡與角色卡產生器 | 根目錄 `config.toml` |
| 05 設定 | 時間、音量、BGM、編碼品質、配角站位、字型、配色、畫面固定文字；可切換「全域」或「本報告覆寫」 | 兩個 `config.toml` |
| 06 輸出 | 產生語音、預覽指定時間點、輸出影片（含進度與記錄）、清理用不到的語音 | — |

## 資料夾

| 路徑 | 內容 |
|---|---|
| `studio.py` | GUI 編輯器 |
| `config.toml` | 全域設定：時間、音量、編碼、站位、字型與配色、固定文字、角色名冊、角色卡產生設定 |
| `characters/` | 角色像素圖 `spr_*.png`、片頭角色卡 `card_*.png` |
| `references/` | 原始參考圖 |
| `sprites.py` | 嘴巴動畫：`claude`、`gpt`、`deepseek_open` 三張圖有手工嘴型（Claude 依表情切換睜眼／閉眼兩張圖）；其他圖直接用原圖 |
| `config.py` | 讀寫設定檔（全域 + 報告各自的），檢查主持人／配角名單 |
| `project.py` | 讀寫 `story.json`、語音檔命名；舊的 `story.py` 第一次開啟時自動轉換 |
| `gen_tts.py` | 依劇本產生語音（已存在的跳過） |
| `render.py` | 合成影片 |
| `make_card.py` | 用立繪產生同風格的角色卡，參數在 `config.toml` 的 `[cards.<名稱>]` |
| `extract_*.py` | 從參考圖擷取像素角色／切角色卡（需要時才跑） |
| `projects/<名稱>/` | 單一份報告：`config.toml`、`story.json` 劇本、`shots/` 截圖、`audio/` 語音、成品 `presentation.mp4` |

## 版本

| 版本 | Git tag | 內容 |
|---|---|---|
| Alpha 0.1.0 | `v0.1.0-alpha` | 初版：劇本寫在 `story.py`、設定改 `config.toml` |
| Alpha 0.2.0 | `v0.2.0-alpha` | GUI 編輯器 `studio.py`；劇本改為 `story.json`、語音以內容命名、畫面參數移入設定檔 |

語音、混音、成品影片與預覽圖不進版控（見 `.gitignore`），用 `gen_tts.py` / `render.py` 重新產生。

## 劇本格式（story.json）

```json
{
  "scenes": [
    {"ch": "CH-01", "title": "專題動機", "shot": "motivation.png", "guests": [], "note": ["大字", "小字"], "lines": [
      {"who": "C", "text": "台詞", "eyes": "o", "view": [0, 0, 1600], "shot": null}
    ]}
  ],
  "pops": [["台詞包含的字串", "標籤"]]
}
```

- `eyes`：`o` 睜眼、`s` 微笑、`c` 閉眼從容。
- `view`：截圖上 16:9 的取景 `[x, y, 寬]`；`null` 沿用上一句。`shot`：這句起換截圖，`null` 沿用。
- `guests`：整段都站在台上的配角；其他配角只在講話前後出現。

## 語音檔

`audio/` 裡的檔名是「台詞文字 + 角色聲線／語速／音高」的雜湊。改台詞、插入或刪除台詞、改角色聲線，只有受影響的句子會在下次產生語音時重錄，不會錯位。
GUI 的「清理用不到的語音」可以刪掉舊版本留下的檔案。

## 命令列（GUI 做的事也可以直接跑）

```bash
python gen_tts.py projects/my_report                 # 產生語音
python render.py projects/my_report preview 5 30 #12 # 預覽第 5、30 秒與第 12 句（沒有語音的句子以靜音估算）
python render.py projects/my_report                  # 輸出完整影片
python make_card.py gemini                           # 依 [cards.gemini] 產生角色卡
```

## 新增角色

1. 像素圖放進 `characters/spr_<名字>.png`（去背；GUI「04 角色」可以匯入）。不是格狀像素圖就勾「高解析度圖」。
2. 角色卡：匯入現成的 `card_<名字>.png`，或在 GUI 建立產生設定後按「產生角色卡」。
3. 在 GUI 按「＋ 新角色」，填名稱、名牌色、聲線、立繪、角色卡。

## 需要的環境

- Python 3.11 以上：`pillow`、`numpy`、`edge-tts`（產生語音、試聽需要網路）；GUI 只用內建的 tkinter
- `ffmpeg`、`ffprobe` 在 PATH 上
- Windows 字型：微軟正黑體（`msjhbd.ttc`）、Segoe UI Black、Segoe UI / Segoe UI Bold、Segoe UI Symbol、Consolas（可在「05 設定」改）

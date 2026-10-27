# Claude 大小姐 報告影片產生器

像素風視覺小說式的報告影片：一位主持人加上幾位配角串場（目前有 Claude、GPT、DeepSeek、Gemini），誰主持、誰上鏡都寫在設定檔。
畫面 1920×1080 / 24fps，聲音用 edge-tts，畫面用 Pillow 逐格合成後交給 ffmpeg 編碼。

## 資料夾

| 路徑 | 內容 |
|---|---|
| `config.toml` | 全域設定：角色名冊（名牌、顏色、聲線、像素圖、角色卡）、時間、音量、配角站位 |
| `characters/` | 角色像素圖 `spr_*.png`：`spr_claude`（閉眼）、`spr_claude_open`（睜眼）、`spr_gpt`、`spr_deepseek_open`（目前使用）、`spr_deepseek`（舊版）、`spr_gemini`（原圖只裁切，高解析度）；片頭角色卡 `card_*.png` |
| `references/` | 原始參考圖：像素三人組、Claude 睜眼像素圖、DeepSeek 睜眼像素圖、角色立繪卡（`cast_cards.png`）、對話框樣式、Gemini 像素圖與立繪 |
| `sprites.py` | 角色動畫：Claude、GPT、DeepSeek 只動嘴巴（Claude 依台詞切換睜眼／閉眼兩張圖）；其他角色直接用原圖 |
| `config.py` | 讀設定檔（全域 + 報告各自的），檢查主持人／配角名單 |
| `gen_tts.py` | 依劇本產生每句語音 |
| `render.py` | 合成影片（版面、運鏡、絕區零風格特效、BGM） |
| `extract_sprites.py` / `extract_trio.py` | 從新參考圖擷取像素角色用（需要時才跑） |
| `extract_cards.py` | 把 `cast_cards.png` 切成每人一張角色卡（已切好，需要時才跑） |
| `make_card.py` | 用立繪產生同風格的角色卡（目前產生 Gemini 的，名字、副標寫在檔案裡的 `CARDS`） |
| `projects/<名稱>/` | 單一份報告：`config.toml` 本次設定、`story.py` 劇本、`shots/` 投影畫面截圖、`audio/` 語音、成品 `presentation.mp4` |

## 做一份新報告

1. 複製 `projects/hoyo_proxy_hub` 成新資料夾，例如 `projects/my_report`，清掉 `audio/`、`shots/`、`mix.wav`、`presentation.mp4`。
2. 編輯 `config.toml`（這份報告的設定）：

   ```toml
   [show]
   host = "M"                 # 主持人：C=Claude、G=GPT、D=DeepSeek、M=Gemini
   guests = ["C", "D"]        # 上鏡配角，順序 = 由左到右站位（片頭角色卡、片尾謝幕也照這份名單）
   title = "我的報告"
   subtitle = "期末專題"
   topbar = "我的報告 · 期末"
   ```

   只要寫想改的項目，其餘沿用根目錄 `config.toml`；那邊的 `[timing]`、`[audio]`、`[layout]`、`[characters.X]` 也都能在這裡覆寫。
3. 把要投影的畫面截圖（建議寬 1600px）放進 `shots/`。
4. 編輯 `story.py`：
   - `SCENES`：每個段落的頻道標籤、標題、預設截圖、台詞；`guests` 寫的角色整段都會站在台上，其他配角只在講話前後出現。
   - 每句台詞 `(講者, 文字, 表情, 鏡頭, 換圖)`：講者是角色代號，必須是本次的主持人或配角（不在名單會直接報錯）；表情 `o` 睜眼、`c` 閉眼從容、`s` 微笑；鏡頭 `(x, y, 寬)` 是截圖上 16:9 的取景位置，`None` 沿用上一句。
   - `NOTES`：左上 NOTE 方塊的公式小抄；`POPS`：台詞含某字串時右上跳出的螢光標籤。
5. 執行（在本資料夾）：

```bash
python gen_tts.py projects/my_report            # 產生語音（已存在的會跳過）
python render.py projects/my_report preview 5 30  # 先輸出第 5、30 秒的預覽圖
python render.py projects/my_report             # 輸出完整影片（約 20 分鐘）
```

改了某句台詞要重錄時，刪掉 `audio/` 裡對應編號的 `.wav` 再跑 `gen_tts.py`。
改聲線（`config.toml` 的 `voice` / `rate` / `pitch`）後要整個刪掉 `audio/` 重新產生。

## 新增角色

1. 像素圖放進 `characters/spr_<名字>.png`（去背）。不是格狀像素圖的高解析度圖，在名冊加 `hires = true`，會縮放到和其他角色一樣高（沒有嘴巴動畫）。
2. 角色卡：在 `make_card.py` 的 `CARDS` 加一筆（立繪路徑、名字、副標、顏色），執行 `python make_card.py <名字>`。
3. 在根目錄 `config.toml` 加 `[characters.<代號>]`（名牌、顏色、聲線、`sprite`、`card`）。

## 需要的環境

- Python 3.11 以上：`pillow`、`numpy`、`edge-tts`（產生語音需要網路）
- `ffmpeg`、`ffprobe` 在 PATH 上
- Windows 字型：微軟正黑體（`msjhbd.ttc`）、Segoe UI Black、Segoe UI / Segoe UI Bold、Segoe UI Symbol、Consolas

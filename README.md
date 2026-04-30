# CardioLLM 心臟超音波翻譯 / 摘要系統

![姆茲咪](docs/images/ui-preview.png)
姆茲咪超級可愛
這個專案是台中榮總心臟科使用的心臟超音波報告翻譯與臨床摘要 Web 系統。  
前端提供報告輸入、翻譯模型選擇、摘要模型選擇、量化版本 Q4/Q5/Q8 選擇，以及心臟示意圖標註；後端透過 Ollama 載入本機 GGUF 模型進行推論。

## 專案結構

```text
cardiollm/
├── docker-compose.yml        # Docker 服務設定
├── Caddyfile                 # HTTPS / reverse proxy 設定
├── .env.example              # 環境變數範例
├── requirements.txt          # proxy container 的 Python 依賴
├── restart_ollama.sh         # 只重啟 Ollama 的維運腳本
├── gguf/                     # GGUF 模型檔案放置處
├── ollama/                   # Ollama Modelfile
├── ollama_store/             # Ollama 模型 registry / blobs
└── proxy/
    ├── server.py             # FastAPI 後端
    ├── templates/            # HTML template
    └── static/               # JS / CSS / 圖片
```

## Docker 服務說明

`docker-compose.yml` 會啟動三個服務：

### 1. `ollama`

負責載入 GGUF 模型並提供 Ollama API。

- container name: `ollama`
- 對外 port: `${OLLAMA_BIND:-127.0.0.1}:${OLLAMA_PORT:-11434}:11434`
- 預設只綁定 `127.0.0.1`，避免 Ollama API 直接暴露到外網
- 掛載：
  - `./gguf` -> `/models`
  - `./ollama` -> `/modelfile`
  - `./ollama_store` -> `/root/.ollama`

### 2. `proxy`

FastAPI Web 後端與前端靜態檔案服務。

- container name: `cardio-proxy`
- 使用 `python:3.11-slim`
- 啟動時會安裝 `requirements.txt`
- 啟動 `uvicorn server:app --host 0.0.0.0 --port 8000`
- 只 expose `8000` 給 Docker network，由 Caddy 對外代理

### 3. `caddy`

負責 HTTPS 與反向代理。

- container name: `cardio-caddy`
- 對外開放 `80` / `443`
- 讀取 `Caddyfile`
- 目前設定：

```text
echollm.thu.edu.tw {
    reverse_proxy proxy:8000
}
```

## 初次部署

### 1. 複製環境變數

```bash
cd ~/cardiollm
cp .env.example .env
```

請編輯 `.env`，至少設定：

```bash
API_KEY=replace-with-your-api-key
UI_PASSWORD=replace-with-your-ui-password
SESSION_HOURS=8
COOKIE_SECURE=true
KEEP_ALIVE=30m
OLLAMA_BIND=127.0.0.1
OLLAMA_PORT=11434
OLLAMA_TRANS_MODEL=replace-with-your-translator-model:q8
OLLAMA_SUM_MODEL=replace-with-your-summarizer-model:q5
```

注意：`.env` 內含密碼與金鑰，不應上傳到 git。

### 2. 放置 GGUF 模型

模型檔案放在：

```text
~/cardiollm/gguf/
```

GGUF 檔案命名範例：

```text
your-translator-model-q4.gguf
your-translator-model-q5.gguf
your-translator-model-q8.gguf
your-summarizer-model-q4.gguf
your-summarizer-model-q5.gguf
your-summarizer-model-q8.gguf
```

GGUF 通常很大，不建議直接放進 git。若要移植到新機器，請另外複製 `gguf/` 或從 Hugging Face 下載。

### 3. 建立 / 註冊 Ollama 模型

Modelfile 放在：

```text
~/cardiollm/ollama/
```

進入 Ollama container 後可用 `ollama create` 註冊模型，例如：

```bash
docker exec -it ollama bash
ollama create your-translator-model:q8 -f /modelfile/Your-Translator-Q8.Modelfile
ollama create your-summarizer-model:q5 -f /modelfile/Your-Summarizer-Q5.Modelfile
ollama list
```

實際可註冊哪些模型，取決於 `ollama/` 中的 Modelfile 與 `gguf/` 中是否有對應檔案。

### 4. 啟動服務

```bash
cd ~/cardiollm
docker compose up -d
```

查看狀態：

```bash
docker compose ps
docker logs -f cardio-proxy
docker logs -f ollama
```

## 常用指令

### 重啟整包服務

```bash
cd ~/cardiollm
docker compose restart
```

### 只重啟 Web proxy

改前端、`server.py`、CSS/JS 後通常只需要重啟 proxy：

```bash
cd ~/cardiollm
docker compose restart proxy
```

### 只重啟 Ollama

```bash
cd ~/cardiollm
./restart_ollama.sh
```

### 深度重建 Ollama container

```bash
cd ~/cardiollm
./restart_ollama.sh deep
```

## `restart_ollama.sh` 在做什麼？

`restart_ollama.sh` 是維運用腳本，目標是「只處理 Ollama」，避免每次都重啟整個網站。

它的流程是：

1. 進入 `/home/ct/cardiollm`
2. 根據參數選擇重啟模式
3. 把執行紀錄寫到 `/home/ct/cardiollm/ollama_store/restart_ollama.log`
4. 等待 `http://127.0.0.1:11434/api/tags` 恢復
5. 若 30 秒內 Ollama 有回應，就記錄 `ollama is up`

### fast 模式

預設模式：

```bash
./restart_ollama.sh
```

等同於：

```bash
docker compose restart -t 3 ollama
```

適合：

- Ollama 卡住
- 新增模型後想重新整理
- 不想影響 proxy / caddy

### deep 模式

```bash
./restart_ollama.sh deep
```

等同於：

```bash
docker compose up -d --force-recreate --no-deps ollama
```

適合：

- Ollama container 狀態異常
- 掛載或環境疑似沒有刷新
- fast restart 無法解決問題

## 模型選擇邏輯

網站目前將「模型系列」與「量化版本」拆開：

- 下拉選單選模型系列
- 下方水平按鈕選 `Q4` / `Q5` / `Q8`
- 若某模型沒有對應量化版本，該按鈕會反灰
- 送出時前端會自動組回完整 Ollama tag，例如：
  - `your-translator-model:q8`
  - `your-summarizer-model:q5`

設定範例：

- 翻譯模型：`your-translator-model:q8`
- 摘要模型：`your-summarizer-model:q5`

## 安全注意事項

- `.env` 不要上傳，裡面有 `API_KEY` 與 `UI_PASSWORD`
- Ollama API 預設只綁定 `127.0.0.1`，不要任意改成公開位址
- GGUF 模型檔案很大，通常不放 git
- 本系統輸出應作為醫療人員輔助，不能取代醫師最終判讀
- 喔愛 蝦咪系愛 你看我的眼神怎那麼可愛

## Troubleshooting

### 網頁修改後沒有變化

先 hard refresh 瀏覽器。若仍無效：

```bash
cd ~/cardiollm
docker compose restart proxy
```

### Ollama 模型清單沒有更新

```bash
cd ~/cardiollm
./restart_ollama.sh
docker exec -it ollama ollama list
```

### Ollama 還是沒有反應

```bash
cd ~/cardiollm
./restart_ollama.sh deep
tail -n 100 ollama_store/restart_ollama.log
```

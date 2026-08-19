# CardioLLM K8s 遠端 Ollama 版本

這份專案是 CardioLLM 的 K8s / CubeCOS 上線版本。它提供 React/Vite Web UI 與 FastAPI proxy，不在 K8s 內執行 Ollama，也不把 GGUF 模型放進 container image。

目前設計是由 CubeCOS / K8s 上的 proxy 遠端呼叫 5070 Ti 主機上的 Ollama：

```text
Browser
  -> CubeCOS / K8s Ingress
  -> cardiollm-proxy Pod
  -> protected remote Ollama endpoint
  -> 5070 Ti Ollama + GGUF
```

原本的 `/home/ct/cardiollm` 保留作為 5070 Ti 本地測試版與 GGUF / Ollama 管理位置。這份 `/home/ct/cardiollm-k8s` 則作為正式上線部署版本。

## 專案結構

```text
cardiollm-k8s/
├── Dockerfile
├── frontend/              # React/Vite source
├── docker-compose.yml
├── .env.k8s.example
├── requirements.txt
├── k8s/
└── proxy/
```

## 預設遠端 Ollama

```env
CORS_ORIGINS=https://your-domain.example
OLLAMA_URL=http://replace-with-protected-ollama-host:30678
OLLAMA_TRANS_MODEL=replace-with-your-translator-model:q8
OLLAMA_SUM_MODEL=replace-with-your-summarizer-model:q8
```

這些模型必須已經在 5070 Ti 主機上的 Ollama 裡註冊完成。K8s 版本只傳送 API request，不會直接讀取 `gguf/`。

安全重點：`OLLAMA_URL` 必須是只有 CubeCOS/K8s 節點可連的受保護端點，不應把 Ollama API 對全世界公開。

目前同步功能包含新版登入介面、React 響應式工作台、模型預熱、串流推論進度、結構化 JSON、固定來源的心臟標示、摘要術語 RAG，以及局部心臟示意圖產生。局部變形使用 headless OpenCV，容器不安裝桌面 GUI 元件。Docker image 採多階段建置，在 image build 時執行 Vite，不使用本機殘留的前端 bundle。

## 本機測試

本機 `docker compose` 測試預設只綁定 `127.0.0.1:8000`，避免使用範例密碼時被同網段直接存取。若要對外測試，請先換掉 `.env` 內的 `API_KEY` / `UI_PASSWORD`。

```bash
cd ~/cardiollm-k8s
cp .env.k8s.example .env
# 編輯 .env，填入實際 API_KEY、UI_PASSWORD、CORS_ORIGINS、OLLAMA_URL 與模型名稱
docker compose up -d --build
```

測試健康狀態：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/healthz
```

## 建立 Image

```bash
cd ~/cardiollm-k8s
docker build -t cardiollm-k8s:latest .
```

`k8s/deployment.yaml` 預設使用 `cardiollm-k8s:latest`。若部署到多節點叢集，請先把 image 匯入每個節點或改成你的 registry image。

目前保留 `imagePullPolicy: IfNotPresent`，方便將 image 匯入 CubeCOS 節點。正式環境建議改用不可變版本標籤或 image digest；若仍沿用 `latest`，每次更新後必須重新匯入 image 並重建 Pod，避免節點沿用舊快取。

## K8s 部署

`k8s/configmap.yaml` 放非機密設定。先把 Ingress host、TLS secret、`CORS_ORIGINS`、`OLLAMA_URL` 與模型名稱換成正式值。`k8s/secret.yaml` 應由 `k8s/secret.example.yaml` 複製後填入高強度 `API_KEY` 與 `UI_PASSWORD`，不要提交到 git。

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## Health Check

- `/health`：只確認 proxy 存活，適合 liveness probe。
- `/healthz`：確認 proxy 能連到遠端 Ollama；失敗時回傳 HTTP 503，適合 readiness probe。

## 安全注意事項

- 不要把遠端 Ollama API 對全世界開放。
- 建議只允許 CubeCOS / K8s 節點 IP 存取 Ollama API，或透過 VPN / firewall / private network 保護。
- `CORS_ORIGINS` 請設定正式網站 origin，不要使用萬用來源。
- `.env` 與 `k8s/secret.yaml` 不要上傳 git。
- 正式環境保持 `COOKIE_SECURE=true`、`DOCS_ENABLED=false`，並透過 TLS Ingress 提供服務。
- Pod 預設以 UID/GID 10001 執行、停用 ServiceAccount token、唯讀 root filesystem 並移除 Linux capabilities；只有 `/app/static/generated` 與 `/tmp` 可寫。
- GGUF 模型留在 5070 Ti 本機，不放進 K8s image。
- 此系統輸出應作為醫療人員輔助，不能取代醫師最終判讀。

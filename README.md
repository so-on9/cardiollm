# CardioLLM K8s 遠端 Ollama 版本

這份專案是 CardioLLM 的 K8s / CubeOS 上線版本。它只負責提供 Web UI 與 FastAPI proxy，不在 K8s 內執行 Ollama，也不把 GGUF 模型放進 container image。

目前設計是由 CubeOS / K8s 上的 proxy 遠端呼叫 5070 Ti 主機上的 Ollama：

```text
Browser
  -> CubeOS / K8s Ingress
  -> cardiollm-proxy Pod
  -> http://replace-with-ollama-host:11434
  -> 5070 Ti Ollama + GGUF
```

原本的 `/home/ct/cardiollm` 保留作為 5070 Ti 本地測試版與 GGUF / Ollama 管理位置。這份 `/home/ct/cardiollm-k8s` 則作為正式上線部署版本。

## 專案結構

```text
cardiollm-k8s/
├── Dockerfile
├── docker-compose.yml
├── .env.k8s.example
├── requirements.txt
├── k8s/
└── proxy/
```

## 預設遠端 Ollama

```env
OLLAMA_BASE_URL=http://replace-with-ollama-host:11434
OLLAMA_TRANS_MODEL=replace-with-your-translator-model:q8
OLLAMA_SUM_MODEL=replace-with-your-summarizer-model:q8
```

這些模型必須已經在 5070 Ti 主機上的 Ollama 裡註冊完成。K8s 版本只傳送 API request，不會直接讀取 `gguf/`。

## 本機測試

```bash
cd ~/cardiollm-k8s
cp .env.k8s.example .env
docker compose up -d --build
```

測試健康狀態：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/health/ollama
```

## 建立 Image

```bash
cd ~/cardiollm-k8s
docker build -t replace-with-your-registry/cardiollm-k8s:latest .
docker push replace-with-your-registry/cardiollm-k8s:latest
```

接著修改 `k8s/deployment.yaml`，把 `replace-with-your-registry/cardiollm-k8s:latest` 換成實際 image。

## K8s 部署

先建立 secret：

```bash
cp k8s/secret.example.yaml k8s/secret.yaml
```

修改 `k8s/secret.yaml` 裡的 `API_KEY` 與 `UI_PASSWORD` 後部署：

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
- `/api/health/ollama`：確認 proxy 能連到遠端 Ollama，適合 readiness probe。
- `/healthz`：相容舊版 health check，目前等同遠端 Ollama 檢查。

## 安全注意事項

- 不建議把遠端 Ollama API 對全世界開放。
- 建議只允許 CubeOS / K8s 節點 IP 存取 Ollama API。
- `.env` 與 `k8s/secret.yaml` 不要上傳 git。
- GGUF 模型留在 5070 Ti 本機，不放進 K8s image。
- 此系統輸出應作為醫療人員輔助，不能取代醫師最終判讀。

# CardioLLM K8s Remote Ollama 部署

這份 K8s 版本部署 React 網頁與 FastAPI proxy，不包含 Ollama，也不包含 GGUF 模型。

推論流程：

```text
Browser -> CubeOS/K8s Ingress -> cardiollm-proxy Pod -> protected remote Ollama endpoint -> remote Ollama GPU host
```

## 部署前檢查

1. 5070 Ti 主機上的 Ollama 需要對 CubeOS 節點可連線。
2. 遠端 Ollama API 不可對全世界開放；請只允許 CubeOS/K8s 節點 IP、VPN 或私有網路存取。
3. `configmap.yaml` 的 `CORS_ORIGINS` 必須設定正式網站 origin，不要使用萬用來源。
4. `configmap.yaml` 內的模型名稱必須已存在於 5070 Ti 的 Ollama。
5. `ingress.yaml` 的 host 與 `cardiollm-tls` 必須換成正式網域與 TLS Secret。

## Secret

請由 `k8s/secret.example.yaml` 複製成本機 `k8s/secret.yaml`，填入實際 `API_KEY` 與 `UI_PASSWORD`。`k8s/secret.yaml` 不應提交。

## 部署順序

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
```

## 健康檢查

- `/health`：只檢查 proxy 是否存活。
- `/healthz`：檢查 proxy 是否能連到遠端 Ollama；失敗時回傳 HTTP 503。

## 新版執行設定

- `TERM_RAG_ENABLED=false`：翻譯不注入術語 RAG，避免漏譯風險。
- `SUMMARY_RAG_ENABLED=true`：摘要使用術語檢索約束。
- `IMAGE_BACKEND=local_warp`：叢集內直接產生局部心臟示意圖，不依賴 ComfyUI。
- API 文件預設關閉；登入具失敗次數限制、同源請求檢查與安全 Cookie。
- Pod 使用非 root、唯讀 root filesystem、停用 ServiceAccount token，產圖目錄由 `emptyDir` 提供。

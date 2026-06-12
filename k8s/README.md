# CardioLLM K8s Remote Ollama 部署

這份 K8s 版本只部署網頁與 FastAPI proxy，不包含 Ollama，也不包含 GGUF 模型。

推論流程：

```text
Browser -> CubeOS/K8s Ingress -> cardiollm-proxy Pod -> protected remote Ollama endpoint -> remote Ollama GPU host
```

## 部署前檢查

1. 5070 Ti 主機上的 Ollama 需要對 CubeOS 節點可連線。
2. 遠端 Ollama API 不可對全世界開放；請只允許 CubeOS/K8s 節點 IP、VPN 或私有網路存取。
3. `configmap.yaml` 的 `CORS_ORIGINS` 必須設定正式網站 origin，不要使用萬用來源。
4. `configmap.yaml` 內的模型名稱必須已存在於 5070 Ti 的 Ollama。

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
- `/api/health/ollama`：檢查 proxy 是否能連到遠端 Ollama。
- `/healthz`：相容舊版 health check，等同檢查遠端 Ollama。

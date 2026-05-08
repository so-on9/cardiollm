# CardioLLM K8s Remote Ollama 部署

這份 K8s 版本只部署網頁與 FastAPI proxy，不包含 Ollama，也不包含 GGUF 模型。

推論流程：

```text
Browser -> CubeOS/K8s Ingress -> cardiollm-proxy Pod -> http://140.128.103.191:11434 -> remote Ollama GPU host
```

## 部署前檢查

1. 5070 Ti 主機上的 Ollama 需要對 CubeOS 節點可連線。
2. 建議只允許 CubeOS 節點 IP 存取遠端 Ollama API。
3. `configmap.yaml` 內的模型名稱必須已存在於 5070 Ti 的 Ollama。

## 建立 Secret

先複製範本：

```bash
cp k8s/secret.example.yaml k8s/secret.yaml
```

修改 `API_KEY` 與 `UI_PASSWORD` 後再部署。

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

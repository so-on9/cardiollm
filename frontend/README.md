# CardioLLM React UI

This directory contains the React/Vite source for the authenticated CardioLLM
workspace. FastAPI continues to provide authentication, APIs, templates, and
static assets.

Build with the repository-mounted Node container:

```bash
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/npm-cache \
  -v /home/ct/cardiollm:/workspace \
  -w /workspace/frontend \
  node:22-alpine npm install

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e npm_config_cache=/tmp/npm-cache \
  -v /home/ct/cardiollm:/workspace \
  -w /workspace/frontend \
  node:22-alpine npm run build
```

The production bundle is written to `proxy/static/react/` and loaded by
`proxy/templates/ui.html`.

export async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    const raw = await response.text();
    let message = raw || response.statusText;
    try {
      const data = JSON.parse(raw);
      message = data.detail || message;
    } catch {}
    throw new Error(message);
  }

  return response.json();
}

export async function apiStream(path, body, onEvent) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const raw = await response.text();
    let message = raw || response.statusText;
    try {
      const data = JSON.parse(raw);
      message = data.detail || message;
    } catch {}
    throw new Error(message);
  }

  if (!response.body) {
    throw new Error("此瀏覽器不支援串流回應");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consume = (raw) => {
    const line = raw.trim();
    if (!line) return;
    const event = JSON.parse(line);
    onEvent(event);
    if (event.event === "error") {
      throw new Error(event.message || "串流服務發生錯誤");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(consume);
  }

  buffer += decoder.decode();
  consume(buffer);
}

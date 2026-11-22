import { ApiError, getToken, parseError } from "./api.mjs";

const SSE_BLOCK_SEPARATOR = /\r?\n\r?\n/;

export function parseSseBlock(block) {
  const lines = block.split(/\r?\n/);
  let eventName = "message";
  const dataLines = [];
  for (const line of lines) {
    if (line.startsWith("event:")) {
      const candidate = line.slice(6).trim();
      if (candidate) eventName = candidate;
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return null;
  const raw = dataLines.join("\n");
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    data = raw;
  }
  return { event: eventName, data };
}

export function parseSseChunks(buffer, chunk) {
  const blocks = (buffer + chunk).split(SSE_BLOCK_SEPARATOR);
  const remainder = blocks.pop() || "";
  const events = blocks.map(parseSseBlock).filter(Boolean);
  return { events, remainder };
}

export async function streamChat(datasetId, payload, { onEvent, signal } = {}) {
  const headers = new Headers({
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  });
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`/datasets/${datasetId}/chat/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
    signal,
  });

  if (!response.ok) throw await parseError(response);
  if (!response.body) throw new ApiError("浏览器不支持流式响应", { code: "STREAM_UNSUPPORTED" });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parsed = parseSseChunks(buffer, "");
      buffer = parsed.remainder;
      for (const event of parsed.events) {
        if (event.event === "error") {
          const message =
            event.data && typeof event.data === "object" ? event.data.message : "分析失败";
          const code =
            event.data && typeof event.data === "object" ? event.data.code : "ANALYSIS_FAILED";
          onEvent?.("error", event.data);
          throw new ApiError(message || "分析失败", { code });
        }
        if (event.event === "final") finalData = event.data;
        onEvent?.(event.event, event.data);
      }
    }
    if (buffer.trim()) {
      const parsed = parseSseChunks(buffer, "\n\n");
      for (const event of parsed.events) {
        if (event.event === "error") {
          onEvent?.("error", event.data);
          throw new ApiError(
            event.data?.message || "分析失败",
            { code: event.data?.code || "ANALYSIS_FAILED" },
          );
        }
        if (event.event === "final") finalData = event.data;
        onEvent?.(event.event, event.data);
      }
    }
  } finally {
    reader.releaseLock();
  }

  return finalData;
}

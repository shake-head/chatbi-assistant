const SESSION_KEY = "chatbi.session";

export class ApiError extends Error {
  constructor(message, options = {}) {
    super(message);
    this.name = "ApiError";
    this.code = options.code || "UNKNOWN_ERROR";
    this.status = options.status || 0;
    this.detail = options.detail ?? null;
    this.requestId = options.requestId ?? null;
  }
}

const ERROR_MESSAGES = {
  VALIDATION_ERROR: "填写的内容不符合要求，请检查后重试。",
  DATABASE_ERROR: "数据保存时出现问题，请稍后重试。",
  INTERNAL_ERROR: "服务出现异常，请稍后重试。",
  UNKNOWN_ERROR: "请求失败，请稍后重试。",
  EMAIL_ALREADY_REGISTERED: "该邮箱已经注册，请直接登录或更换邮箱。",
  INVALID_CREDENTIALS: "邮箱或密码不正确，请重新输入。",
  UNAUTHORIZED: "登录已过期，请重新登录。",
  NOT_FOUND: "没有找到相关数据，可能已被删除或不属于当前账号。",
  FILE_TOO_LARGE: "文件过大，请改用更小的文件后重试。",
  EMPTY_FILE: "文件内容为空，请选择有效的 CSV 或 Excel 文件。",
  UNSUPPORTED_FILE_TYPE: "仅支持 CSV、XLSX、XLS 格式的文件。",
  DATASET_NOT_READY: "数据集还在准备中，请稍等片刻再提问。",
  DATASET_PARSE_FAILED: "无法把文件解析成表格数据，请检查文件内容。",
  DATASET_EMPTY: "文件里没有有效的数据行或列。",
  DATASET_TOO_LARGE: "数据行数超过限制，请减少行数后重试。",
  DATASET_TOO_WIDE: "数据列数超过限制，请减少列数后重试。",
  DATASET_PATH_INVALID: "数据存储路径异常，请重新上传。",
  ANALYSIS_PLAN_INVALID: "没有正确理解这个问题，请换一种更明确的说法。",
  ANALYSIS_TIMEOUT: "分析耗时过长，请缩小问题范围后重试。",
  ANALYSIS_EXECUTION_FAILED: "分析执行失败，请稍后重试。",
  ANALYSIS_RESULT_INVALID: "分析结果不符合要求，请换一种问法。",
  AI_NOT_CONFIGURED: "AI 服务尚未配置，请联系管理员。",
  AI_SERVICE_UNAVAILABLE: "AI 服务暂时不可用，请稍后再试。",
  AI_QUOTA_EXCEEDED: "本月的 AI 用量已用完，请查看用量或调整预算。",
  RATE_LIMIT_EXCEEDED: "操作过于频繁，请稍等片刻再试。",
};

const STATUS_MESSAGES = {
  401: "登录已过期，请重新登录。",
  404: "没有找到相关数据。",
  413: "文件过大或数据规模超限。",
  415: "文件格式不受支持。",
  422: "请求内容不符合要求，请检查后重试。",
  429: "操作过于频繁，请稍等片刻再试。",
  500: "服务出现异常，请稍后重试。",
  503: "服务暂时不可用，请稍后再试。",
};

export function errorMessage(error) {
  if (error instanceof ApiError) {
    return ERROR_MESSAGES[error.code] || STATUS_MESSAGES[error.status] || ERROR_MESSAGES.UNKNOWN_ERROR;
  }
  if (error instanceof TypeError || error?.name === "AbortError") {
    return error?.name === "AbortError" ? "操作已取消。" : "无法连接服务，请检查服务是否已启动。";
  }
  return ERROR_MESSAGES.UNKNOWN_ERROR;
}

function storage() {
  if (typeof sessionStorage !== "undefined") {
    return sessionStorage;
  }
  return null;
}

export function getSession() {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(SESSION_KEY);
    if (!raw) return null;
    const session = JSON.parse(raw);
    if (!session?.access_token || !session?.expires_at) return null;
    if (Date.now() >= session.expires_at) {
      clearSession();
      return null;
    }
    return session;
  } catch {
    clearSession();
    return null;
  }
}

export function setSession(payload) {
  const store = storage();
  if (!store) return;
  const expiresInSeconds = Math.max(0, Number(payload.expires_in) || 3600);
  const session = {
    access_token: payload.access_token,
    user: payload.user,
    expires_at: Date.now() + expiresInSeconds * 1000,
  };
  store.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  const store = storage();
  if (!store) return;
  store.removeItem(SESSION_KEY);
}

export function getToken() {
  return getSession()?.access_token ?? null;
}

export function currentUser() {
  return getSession()?.user ?? null;
}

export async function parseError(response) {
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  const requestId = response.headers.get("X-Request-ID");
  if (payload && typeof payload === "object" && payload.code) {
    return new ApiError(payload.message || "请求失败", {
      code: payload.code,
      status: response.status,
      detail: payload.detail ?? null,
      requestId,
    });
  }
  return new ApiError(`HTTP ${response.status}`, {
    code: `HTTP_${response.status}`,
    status: response.status,
    requestId,
  });
}

export async function request(path, options = {}) {
  const token = getToken();
  const headers = new Headers(options.headers || {});
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let body;
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(options.json);
  } else if (options.formData) {
    body = options.formData;
  }

  let response;
  try {
    response = await fetch(path, {
      method: options.method || (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
    });
  } catch (error) {
    if (error instanceof TypeError) throw error;
    throw new ApiError("请求失败", { code: "NETWORK_ERROR" });
  }

  if (response.status === 204) return null;
  if (!response.ok) throw await parseError(response);
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) return response.json();
  return response.text();
}

export function apiGet(path) {
  return request(path);
}

export function apiPost(path, body) {
  return request(path, { method: "POST", json: body });
}

export function apiDelete(path) {
  return request(path, { method: "DELETE" });
}

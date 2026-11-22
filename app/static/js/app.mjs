import {
  ApiError,
  clearSession,
  currentUser,
  errorMessage,
  getSession,
  request,
  setSession,
} from "./api.mjs";
import { streamChat } from "./sse.mjs";
import { downloadText, formatCell, formatDate, formatDateTime, formatNumber, rowsToCsv } from "./format.mjs";
import { disposeChart, initChart } from "./charts.mjs";

const state = {
  session: null,
  authMode: "login",
  authBusy: false,
  datasets: [],
  selectedDatasetId: null,
  selectedDetail: null,
  conversations: [],
  currentConversationId: null,
  messages: [],
  busy: false,
  progress: null,
  usage: null,
  charts: [],
};

const ICONS = {
  chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M21 11.5a8.38 8.38 0 0 1-8.5 8.4 8.5 8.5 0 0 1-3.9-.9L3 20l1.1-4.1A8.38 8.38 0 0 1 3 11.5a8.5 8.5 0 0 1 9.5-8.4 8.38 8.38 0 0 1 8.5 8.4Z"/></svg>',
  datasets: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5"/><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3"/></svg>',
  history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
  usage: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10M10 20V4M16 20v-8M22 20H2"/></svg>',
  upload: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/></svg>',
  empty: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7.5h16M6 7.5v11a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-11M9 7.5V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2.5"/></svg>',
};

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "innerHTML") node.innerHTML = value;
    else if (key === "value") node.value = value;
    else if (key === "disabled") node.disabled = Boolean(value);
    else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else {
      node.setAttribute(key, value);
    }
  }
  appendChildren(node, children);
  return node;
}

function appendChildren(node, children) {
  for (const child of [].concat(children)) {
    if (child === null || child === undefined || child === false) continue;
    if (child instanceof Node) node.appendChild(child);
    else node.appendChild(document.createTextNode(String(child)));
  }
}

function icon(name) {
  return el("span", { class: "icon", innerHTML: ICONS[name] || "" });
}

function spinner(small = false) {
  return el("span", { class: small ? "spinner spinner--sm" : "spinner" });
}

function mount(node) {
  const root = document.getElementById("app");
  root.replaceChildren(node);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureToastRegion() {
  let region = document.querySelector(".toast-region");
  if (!region) {
    region = el("div", { class: "toast-region", "aria-live": "polite" });
    document.body.appendChild(region);
  }
  return region;
}

function toast(message, type = "info") {
  const region = ensureToastRegion();
  const node = el("div", { class: `toast ${type === "error" ? "toast--error" : type === "success" ? "toast--success" : ""}`, text: message });
  region.appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

function isEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

function boot() {
  state.session = getSession();
  if (state.session) {
    renderWorkspace();
    loadInitialData();
  } else {
    renderAuth();
  }
}

function renderSplash() {
  mount(el("div", { class: "splash" }, [spinner(), el("div", { text: "正在加载…" })]));
}

function renderAuth() {
  const isLogin = state.authMode === "login";
  const fields = [
    el("div", { class: "field" }, [
      el("label", { for: "auth-email", text: "邮箱" }),
      el("input", {
        id: "auth-email",
        type: "email",
        autocomplete: "email",
        placeholder: "you@example.com",
      }),
      el("div", { class: "error", "data-error": "email" }),
    ]),
    passwordField("密码", "auth-password", "current-password", isLogin ? "请输入密码" : "至少 8 位，建议混合大小写与数字"),
    !isLogin
      ? passwordField("确认密码", "auth-confirm", "new-password", "再次输入密码")
      : null,
    el("div", { class: "form-error", style: "display:none", "data-error-box": "form" }, [
      el("span", { text: "！" }),
      el("div", { "data-error-text": "form" }),
    ]),
    el("button", { class: "btn btn-primary btn-block", type: "submit", "data-submit": "" }, [
      state.authBusy ? spinner(true) : null,
      el("span", { text: isLogin ? "登录" : "注册并登录" }),
    ]),
  ].filter(Boolean);

  const form = el("form", { novalidate: "true", class: "auth-form" }, fields);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitAuth(form);
  });

  const tab = (mode, label) =>
    el("button", {
      type: "button",
      class: `auth-tab ${state.authMode === mode ? "is-active" : ""}`,
      text: label,
      onclick: () => {
        state.authMode = mode;
        renderAuth();
      },
    });

  const card = el("div", { class: "auth-card" }, [
    el("div", { class: "auth-tabs" }, [tab("login", "登录"), tab("register", "注册")]),
    form,
  ]);

  const hero = el("div", { class: "auth-hero" }, [
    el("div", { class: "brand" }, [
      el("span", { class: "brand-mark", text: "AI" }),
      el("span", { text: "AI 数据分析助手" }),
    ]),
    el("h1", { text: "用中文提问，直接得到图表和结论" }),
    el("p", { text: "上传 CSV 或 Excel 表格，输入自然语言问题，系统会自动完成分析并给出图表、数据表和结论。" }),
    el("div", { class: "steps" }, [
      stepLine(1, "上传表格：支持 CSV、XLSX、XLS"),
      stepLine(2, "用中文提问：合计、趋势、占比、排序"),
      stepLine(3, "查看结果：图表 + 数据表 + 结论"),
    ]),
  ]);

  mount(el("div", { class: "auth-screen" }, [hero, card]));
}

function passwordField(label, id, autocomplete, hint) {
  const input = el("input", {
    id,
    type: "password",
    autocomplete,
    placeholder: label,
  });
  const toggle = el("button", {
    type: "button",
    class: "password-toggle",
    text: "显示",
    onclick: () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      toggle.textContent = show ? "隐藏" : "显示";
    },
  });
  return el("div", { class: "field" }, [
    el("label", { for: id, text: label }),
    el("div", { class: "password-wrap" }, [input, toggle]),
    el("div", { class: "error", "data-error": id }),
    el("div", { class: "hint", text: hint }),
  ]);
}

function stepLine(number, text) {
  return el("div", { class: "step" }, [
    el("span", { class: "step-num", text: String(number) }),
    el("span", { text }),
  ]);
}

async function submitAuth(form) {
  const email = form.querySelector("#auth-email").value.trim();
  const password = form.querySelector("#auth-password").value;
  const confirm = form.querySelector("#auth-confirm");
  clearFieldErrors(form);

  let valid = true;
  if (!isEmail(email)) {
    setFieldError(form, "email", "请输入有效的邮箱地址。");
    valid = false;
  }
  if (state.authMode === "register" && password.length < 8) {
    setFieldError(form, "auth-password", "密码至少需要 8 位。");
    valid = false;
  }
  if (!password) {
    setFieldError(form, "auth-password", "请输入密码。");
    valid = false;
  }
  if (confirm && confirm.value !== password) {
    setFieldError(form, "auth-confirm", "两次输入的密码不一致。");
    valid = false;
  }
  if (!valid) return;

  const button = form.querySelector("[data-submit]");
  state.authBusy = true;
  button.disabled = true;
  button.replaceChildren(spinner(true), el("span", { text: "请稍候…" }));

  try {
    const payload = { email, password };
    const result = await request(state.authMode === "login" ? "/auth/login" : "/auth/register", {
      method: "POST",
      json: payload,
    });
    setSession(result);
    state.session = getSession();
    renderWorkspace();
    await loadInitialData();
  } catch (error) {
    showFormError(form, errorMessage(error), error);
  } finally {
    state.authBusy = false;
    const submit = form.querySelector("[data-submit]");
    if (submit && submit.isConnected) {
      submit.disabled = false;
      submit.replaceChildren(el("span", { text: state.authMode === "login" ? "登录" : "注册并登录" }));
    }
  }
}

function clearFieldErrors(form) {
  form.querySelectorAll(".error").forEach((node) => {
    node.textContent = "";
    const input = form.querySelector(`#${node.dataset.error}`);
    if (input) input.classList.remove("is-invalid");
  });
  const box = form.querySelector("[data-error-box]");
  if (box) box.style.display = "none";
}

function setFieldError(form, key, message) {
  const node = form.querySelector(`[data-error="${key}"]`);
  if (node) node.textContent = message;
  const input = form.querySelector(`#${key}`);
  if (input) input.classList.add("is-invalid");
}

function showFormError(form, message, error) {
  const box = form.querySelector("[data-error-box]");
  const text = form.querySelector("[data-error-text]");
  if (box && text) {
    text.textContent = message;
    const requestId = error instanceof ApiError ? error.requestId : null;
    if (requestId) {
      text.appendChild(el("span", { class: "request-id", text: `请求编号：${requestId}` }));
    }
    box.style.display = "flex";
  }
}

function renderWorkspace() {
  const user = currentUser();
  const nav = [
    ["chat", "数据问答", ICONS.chat],
    ["datasets", "数据集", ICONS.datasets],
    ["history", "历史对话", ICONS.history],
    ["usage", "我的用量", ICONS.usage],
  ];
  const section = sectionFromHash();

  const navItems = nav.map(([key, label, svg]) =>
    el("button", {
      class: `nav-item ${section === key ? "is-active" : ""}`,
      onclick: () => {
        location.hash = `#/${key}`;
      },
    }, [icon(key), el("span", { text: label })]),
  );

  const sidebar = el("aside", { class: "sidebar" }, [
    el("div", { class: "brand" }, [
      el("span", { class: "brand-mark", text: "AI" }),
      el("span", { class: "brand-name", text: "数据分析助手" }),
    ]),
    ...navItems,
    el("div", { class: "sidebar-footer" }, [
      el("div", { class: "sidebar-user" }, [
        el("span", { class: "avatar", text: (user?.email || "?").slice(0, 1).toUpperCase() }),
        el("span", { class: "email", text: user?.email || "" }),
      ]),
      el("a", { class: "btn btn-ghost btn-sm", href: "/docs", target: "_blank", rel: "noopener", text: "开发者接口文档" }),
      el("button", { class: "btn btn-ghost btn-sm", onclick: logout, text: "退出登录" }),
    ]),
  ]);

  const main = el("main", { class: "main", "data-view": section });
  mount(el("div", { class: "workspace" }, [sidebar, main]));
  route();
}

function sectionFromHash() {
  const hash = location.hash.replace(/^#\/?/, "");
  if (["datasets", "history", "usage"].includes(hash)) return hash;
  return "chat";
}

function route() {
  if (!state.session) {
    renderAuth();
    return;
  }
  const section = sectionFromHash();
  const main = document.querySelector(".main");
  if (!main) return;
  disposeCharts();
  if (section === "datasets") renderDatasetsPage(main);
  else if (section === "history") renderHistoryPage(main);
  else if (section === "usage") renderUsagePage(main);
  else renderChatPage(main);
}

function logout() {
  clearSession();
  state.session = null;
  state.datasets = [];
  state.selectedDatasetId = null;
  state.selectedDetail = null;
  state.conversations = [];
  state.currentConversationId = null;
  state.messages = [];
  state.usage = null;
  location.hash = "#/auth";
  renderAuth();
}

async function loadInitialData() {
  try {
    const [datasets, conversations] = await Promise.all([
      request("/datasets"),
      request("/conversations"),
    ]);
    state.datasets = datasets?.items || [];
    state.conversations = conversations || [];
    if (state.datasets.length > 0 && state.selectedDatasetId === null) {
      await openDataset(state.datasets[0].id, { keepConversation: false });
    } else {
      route();
    }
  } catch (error) {
    if (error instanceof ApiError && error.code === "UNAUTHORIZED") {
      logout();
      return;
    }
    toast(errorMessage(error), "error");
    route();
  }
}

function pageHead(title, subtitle, action = null) {
  return el("div", { class: "page-head" }, [
    el("div", {}, [el("h2", { text: title }), el("p", { class: "subtitle", text: subtitle })]),
    action,
  ]);
}

function disposeCharts() {
  state.charts.forEach((chart) => disposeChart(chart));
  state.charts = [];
}

function emptyState(title, description, action = null) {
  return el("div", { class: "empty" }, [
    el("div", { class: "empty-icon", innerHTML: ICONS.empty }),
    el("h3", { text: title }),
    el("p", { text: description }),
    action,
  ]);
}

function datasetLabel(status) {
  return { uploading: "上传中", parsing: "解析中", ready: "可分析", failed: "解析失败" }[status] || status;
}

function statusChip(status) {
  const map = { ready: "chip--ready", parsing: "chip--parsing", uploading: "chip--parsing", failed: "chip--failed" };
  return el("span", { class: `chip ${map[status] || "chip--neutral"}` }, [
    status === "parsing" || status === "uploading" ? spinner(true) : null,
    el("span", { text: datasetLabel(status) }),
  ]);
}

function findDataset(id) {
  return state.datasets.find((item) => Number(item.id) === Number(id)) || null;
}

function updateDatasetSummary(id, detail) {
  const index = state.datasets.findIndex((item) => Number(item.id) === Number(id));
  if (index === -1) return;
  const current = state.datasets[index];
  state.datasets[index] = { ...current, ...detail };
}

async function openDataset(id, { keepConversation = false } = {}) {
  state.selectedDatasetId = Number(id);
  if (!keepConversation) {
    state.currentConversationId = null;
    state.messages = [];
  }
  try {
    const detail = await request(`/datasets/${id}`);
    state.selectedDetail = detail;
    updateDatasetSummary(id, detail);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
  route();
}

function datasetRow(dataset) {
  const ready = dataset.status === "ready";
  const actions = [
    ready
      ? el("button", { class: "btn btn-secondary btn-sm", text: "查看预览", onclick: () => togglePreview(dataset.id) })
      : null,
    ready
      ? el("button", {
          class: "btn btn-secondary btn-sm",
          text: "开始提问",
          onclick: async () => {
            await openDataset(dataset.id, { keepConversation: false });
            location.hash = "#/chat";
          },
        })
      : null,
    dataset.status === "failed"
      ? el("button", { class: "btn btn-secondary btn-sm", text: "重新上传", onclick: () => triggerUpload() })
      : null,
    el("button", {
      class: "btn btn-danger btn-sm",
      text: "删除",
      onclick: () => deleteDataset(dataset),
    }),
  ].filter(Boolean);

  return el("div", { class: "dataset-row" }, [
    statusChip(dataset.status),
    el("div", { style: "min-width:0" }, [
      el("p", { class: "dataset-name", text: dataset.name || "未命名数据集" }),
      el("div", { class: "dataset-meta", text: `${dataset.row_count ?? 0} 行 · 创建于 ${formatDate(dataset.created_at)}` }),
      dataset.status === "failed" && dataset.error_message
        ? el("div", { class: "dataset-meta", style: "color:var(--danger)", text: `失败原因：${dataset.error_message}` })
        : null,
    ]),
    el("div", { class: "actions" }, actions),
  ]);
}

function renderDatasetsPage(main) {
  const input = fileInput();
  const zone = uploadZone(input);

  const list = state.datasets.length
    ? el("div", { class: "dataset-list" }, state.datasets.map((dataset) => datasetRow(dataset)))
    : emptyState(
        "还没有数据集",
        "上传一个 CSV 或 Excel 文件，解析完成后就可以开始提问。",
        el("button", { class: "btn btn-primary", onclick: () => input.click(), text: "上传数据" }),
      );

  const uploadAction = el("button", { class: "btn btn-primary", onclick: () => input.click() }, [
    icon("upload"),
    el("span", { text: "上传数据" }),
  ]);

  main.replaceChildren(
    pageHead("数据集", "管理你的数据文件，解析完成后即可用于问答。", uploadAction),
    zone,
    list,
    el("div", { "data-preview": "" }),
  );
}

function fileInput() {
  const input = el("input", {
    type: "file",
    accept: ".csv,.xlsx,.xls",
    style: "display:none",
    onchange: (event) => {
      const file = event.target.files[0];
      if (file) handleUpload(file);
      input.value = "";
    },
  });
  return input;
}

function uploadZone(input) {
  const zone = el("div", {
    class: "upload-zone",
    role: "button",
    tabindex: "0",
    onclick: () => input.click(),
    onkeydown: (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        input.click();
      }
    },
  }, [
    el("div", { class: "upload-icon", innerHTML: ICONS.upload }),
    el("div", { class: "upload-title", text: "点击选择，或将文件拖到这里" }),
    el("div", { class: "upload-note", text: "支持 CSV、XLSX、XLS；文件解析在后台进行" }),
  ]);

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("is-dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    const file = event.dataTransfer.files[0];
    if (file) handleUpload(file);
  });
  return zone;
}

function triggerUpload() {
  const input = document.querySelector("input[type=file]");
  if (input) input.click();
}

async function handleUpload(file) {
  const extension = `.${(file.name.split(".").pop() || "").toLowerCase()}`;
  if (![".csv", ".xlsx", ".xls"].includes(extension)) {
    toast("仅支持 CSV、XLSX、XLS 格式的文件。", "error");
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("name", file.name.replace(/\.[^.]+$/, "") || file.name);
  toast("正在上传并解析，请稍候…");

  try {
    const created = await request("/datasets", { method: "POST", formData });
    const summary = {
      id: created.id,
      name: created.name,
      status: created.status,
      row_count: created.row_count,
      error_message: created.error_message,
      created_at: created.created_at,
    };
    state.datasets.unshift(summary);
    route();
    pollDataset(created.id);
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function pollDataset(id) {
  for (let attempt = 0; attempt < 240; attempt += 1) {
    if (!state.session) return;
    await sleep(1000);
    try {
      const detail = await request(`/datasets/${id}`);
      updateDatasetSummary(id, detail);
      if (Number(state.selectedDatasetId) === Number(id)) state.selectedDetail = detail;
      if (sectionFromHash() === "datasets") route();
      if (detail.status === "ready") {
        toast("数据解析完成，可以开始提问了。", "success");
        if (Number(state.selectedDatasetId) === Number(id)) route();
        return;
      }
      if (detail.status === "failed") {
        toast("数据解析失败，请检查文件内容。", "error");
        route();
        return;
      }
    } catch (error) {
      toast(errorMessage(error), "error");
      return;
    }
  }
  toast("解析耗时较长，请稍后在数据集列表刷新查看。");
}

function togglePreview(id) {
  const container = document.querySelector("[data-preview]");
  if (!container) return;
  container.replaceChildren(spinner(), el("span", { class: "muted", text: "正在加载预览…" }));
  request(`/datasets/${id}`)
    .then((detail) => {
      if (!detail?.schema) {
        container.replaceChildren(el("div", { class: "muted", text: "该数据集没有可用的字段信息。" }));
        return;
      }
      container.replaceChildren(renderPreview(detail));
    })
    .catch((error) => {
      container.replaceChildren(el("div", { class: "muted", text: errorMessage(error) }));
    });
}

function renderPreview(detail) {
  const schema = detail.schema;
  const columns = el("div", { class: "panel card" }, [
    el("h3", { text: `字段信息（${schema.columns.length} 列）` }),
    ...schema.columns.map((column) =>
      el("div", { style: "padding:6px 0;border-bottom:1px solid var(--border)" }, [
        el("span", { style: "font-weight:600", text: column.name }),
        el("span", { class: "chip chip--neutral", style: "margin-left:8px", text: dtypeLabel(column.dtype) }),
        column.sample_values?.length
          ? el("span", { class: "muted", style: "margin-left:8px", text: `示例：${column.sample_values.slice(0, 3).map(formatCell).join("、")}` })
          : null,
      ]),
    ),
  ]);
  const sample = schema.sample_rows?.length ? renderTable(schema.sample_rows) : null;
  return el("div", { style: "margin-top:16px;display:grid;gap:16px" }, [
    columns,
    el("div", { class: "panel card" }, [el("h3", { text: "数据预览（前 5 行）" }), sample || el("div", { class: "muted", text: "暂无样例行" })]),
  ]);
}

function dtypeLabel(dtype) {
  return { integer: "整数", number: "数值", boolean: "布尔", datetime: "日期时间", string: "文本" }[dtype] || dtype;
}

async function deleteDataset(dataset) {
  const ok = window.confirm(
    `确定删除数据集「${dataset.name}」吗？与之关联的所有对话也会一并删除，且无法恢复。`,
  );
  if (!ok) return;
  try {
    await request(`/datasets/${dataset.id}`, { method: "DELETE" });
    state.datasets = state.datasets.filter((item) => Number(item.id) !== Number(dataset.id));
    if (Number(state.selectedDatasetId) === Number(dataset.id)) {
      state.selectedDatasetId = null;
      state.selectedDetail = null;
      state.currentConversationId = null;
      state.messages = [];
    }
    toast("数据集已删除。", "success");
    route();
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

function renderTable(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return el("div", { class: "muted", text: "没有可展示的数据。" });
  }
  const columns = Object.keys(rows[0]);
  const table = el("table", { class: "data-table" }, [
    el("thead", {}, [el("tr", {}, columns.map((column) => el("th", { text: column })))]),
    el("tbody", {}, rows.map((row) => el("tr", {}, columns.map((column) => el("td", { text: formatCell(row[column]) }))))),
  ]);
  return el("div", { class: "table-scroll" }, [table]);
}

function renderAnswerBody(message) {
  const spec = message.chart_spec;
  const rows = message.result_table || [];
  const hasChart = spec && spec.type !== "table" && globalThis.echarts;

  const chartBox = el("div", { class: "chart-box" });
  const tableBox = renderTable(rows);
  const chartPane = el("div", { "data-chart-pane": "" }, [chartBox]);
  const tablePane = el("div", { "data-table-pane": "", style: "display:none" }, [tableBox]);

  const chartTab = hasChart
    ? el("button", { class: "view-tab is-active", text: "图表", onclick: () => switchView(chartTab, tableTab, chartPane, tablePane) })
    : null;
  const tableTab = el("button", {
    class: `view-tab ${hasChart ? "" : "is-active"}`,
    text: "数据表",
    onclick: () => switchView(tableTab, chartTab, tablePane, chartPane),
  });

  const tabs = el("div", { class: "view-tabs" }, [chartTab, tableTab].filter(Boolean));
  const body = el("div", {}, [tabs, chartPane, tablePane]);

  const download = el("button", {
    class: "btn btn-secondary btn-sm",
    text: "导出 CSV",
    onclick: () => downloadText("结果表.csv", rowsToCsv(rows), "text/csv"),
  });

  if (hasChart) {
    requestAnimationFrame(() => {
      const chart = initChart(chartBox, spec);
      if (chart) state.charts.push(chart);
    });
  } else {
    tablePane.style.display = "";
    chartPane.style.display = "none";
  }

  return el("div", {}, [
    el("p", { class: "conclusion", text: message.content || "已完成分析。" }),
    body,
    el("div", { class: "answer-actions" }, [download]),
  ]);
}

function switchView(activeTab, inactiveTab, activePane, inactivePane) {
  activeTab.classList.add("is-active");
  inactiveTab?.classList.remove("is-active");
  activePane.style.display = "";
  inactivePane.style.display = "none";
  if (activePane.querySelector(".chart-box")) {
    requestAnimationFrame(() => {
      activePane.querySelectorAll(".chart-box").forEach((box) => {
        const chart = globalThis.echarts?.getInstanceByDom?.(box);
        if (chart) chart.resize();
      });
    });
  }
}

function messageBubble(message) {
  if (message.role === "user") {
    return el("div", { class: "bubble bubble--user" }, [
      el("div", { class: "bubble-body", text: message.content }),
    ]);
  }
  return el("div", { class: "bubble bubble--assistant" }, [
    el("div", { class: "bubble-body" }, [
      el("div", { class: "bubble-meta", text: `助手 · ${formatDateTime(message.created_at)}` }),
      renderAnswerBody(message),
    ]),
  ]);
}

function renderThread() {
  const container = el("div", { class: "chat-thread" });
  if (state.messages.length === 0) {
    container.appendChild(
      emptyState(
        "开始你的第一次提问",
        "选择数据集后，用中文描述你想分析的问题，例如「各区域销售额合计是多少？」",
      ),
    );
  } else {
    state.messages.forEach((message) => container.appendChild(messageBubble(message)));
  }
  return container;
}

function renderChatPage(main) {
  const selected = state.selectedDetail;
  const readyDatasets = state.datasets.filter((dataset) => dataset.status === "ready");
  const select = el("select", { class: "dataset-select", "aria-label": "选择数据集" });

  readyDatasets.forEach((dataset) => {
    select.appendChild(el("option", { value: String(dataset.id), text: dataset.name || "未命名数据集" }));
  });
  if (readyDatasets.length === 0) {
    select.appendChild(el("option", { value: "", text: "暂无可用数据集" }));
  }
  if (selected) select.value = String(selected.id);
  select.addEventListener("change", () => {
    if (select.value) openDataset(select.value, { keepConversation: false });
  });

  const newConversation = el("button", {
    class: "btn btn-secondary btn-sm",
    text: "新建对话",
    onclick: () => {
      state.currentConversationId = null;
      state.messages = [];
      route();
    },
  });

  const toolbar = el("div", { class: "chat-toolbar" }, [
    el("span", { class: "muted", text: "当前数据集" }),
    select,
    state.currentConversationId
      ? el("span", { class: "chip chip--neutral", text: `对话 #${state.currentConversationId}` })
      : null,
    newConversation,
  ]);

  const thread = renderThread();
  const composer = renderComposer(selected);
  const progress = state.busy ? renderProgress() : null;

  main.replaceChildren(
    pageHead("数据问答", "选择数据集并用中文提问，系统会自动完成分析与结论。"),
    progress,
    el("div", { class: "chat-page" }, [
      toolbar,
      el("div", { class: "card" }, [thread]),
      composer,
    ]),
  );

  scrollThread();
}

function scrollThread() {
  const thread = document.querySelector(".chat-thread");
  if (thread) thread.scrollTop = thread.scrollHeight;
}

function renderProgress() {
  const stage = state.progress?.stage || "planning";
  const detail = state.progress?.detail || "";
  return el("div", { class: "progress-card" }, [
    spinner(),
    el("div", {}, [
      el("div", { class: "stage", text: stageText(stage) }),
      el("div", { class: "detail", text: detail }),
    ]),
  ]);
}

function stageText(stage) {
  return {
    conversation: "正在准备对话",
    planning: "正在理解问题并生成分析计划",
    executing: "正在计算数据",
    concluding: "正在生成结论",
  }[stage] || "正在分析";
}

function renderComposer(selected) {
  const textarea = el("textarea", {
    placeholder: selected ? "例如：各区域的销售额合计是多少？" : "请先上传并选择一个数据集",
    maxlength: "2000",
    disabled: !selected || selected.status !== "ready" || state.busy,
  });
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendQuestion(textarea);
    }
  });

  const count = el("span", { class: "composer-hint", text: "Enter 发送 · Shift+Enter 换行" });
  const send = el("button", {
    class: "btn btn-primary",
    disabled: !selected || selected.status !== "ready" || state.busy,
    onclick: () => sendQuestion(textarea),
  }, [state.busy ? spinner(true) : null, el("span", { text: "发送" })]);

  textarea.addEventListener("input", () => {
    send.disabled = state.busy || textarea.value.trim().length === 0 || !selected || selected.status !== "ready";
    count.textContent = `${textarea.value.length}/2000 · Enter 发送 · Shift+Enter 换行`;
  });

  const suggestions = selected?.schema?.columns?.length ? renderSuggestions(selected) : null;
  return el("div", { class: "card composer" }, [
    textarea,
    el("div", { class: "composer-foot" }, [count, send]),
    suggestions || null,
  ]);
}

function renderSuggestions(detail) {
  const columns = detail.schema.columns;
  const numeric = columns.find((column) => ["integer", "number"].includes(column.dtype));
  const datetime = columns.find((column) => column.dtype === "datetime");
  const dimension = columns.find((column) => column.dtype === "string");
  const text = columns.find((column) => column.dtype === "string");

  const items = [
    numeric ? `${numeric.name}合计是多少？` : null,
    datetime ? `${datetime.name}的变化趋势如何？` : null,
    dimension ? `各${dimension.name}的${numeric?.name || "数量"}分别是多少？` : null,
    text ? `${text.name}中哪些值出现最多？` : null,
    "一共有多少行数据？",
  ].filter(Boolean).slice(0, 4);

  if (items.length === 0) return null;
  return el("div", { class: "suggestions" }, [
    el("span", { class: "muted", style: "align-self:center", text: "可以这样问：" }),
    ...items.map((question) =>
      el("button", {
        type: "button",
        class: "suggestion",
        text: question,
        onclick: () => {
          const textarea = document.querySelector(".composer textarea");
          if (textarea) {
            textarea.value = question;
            sendQuestion(textarea);
          }
        },
      }),
    ),
  ]);
}

async function sendQuestion(textarea) {
  const question = textarea.value.trim();
  if (!question || state.busy) return;
  const detail = state.selectedDetail;
  if (!detail || detail.status !== "ready") {
    toast("当前数据集还未准备好，请稍后再试。", "error");
    return;
  }

  state.busy = true;
  state.progress = { stage: "planning", detail: "正在理解你的问题…" };
  state.messages.push({ role: "user", content: question, created_at: new Date().toISOString() });
  textarea.value = "";
  route();

  try {
    await streamChat(
      detail.id,
      { question, conversation_id: state.currentConversationId || null },
      {
        onEvent: (event, data) => {
          if (event === "status") {
            state.progress = { stage: data.stage, detail: "" };
          } else if (event === "plan") {
            state.progress = { stage: "executing", detail: data.title ? `分析主题：${data.title}` : "正在计算数据" };
          } else if (event === "result") {
            state.progress = { stage: "concluding", detail: "计算完成，正在总结结论…" };
          } else if (event === "final") {
            state.currentConversationId = data.conversation_id;
            state.messages.push({
              role: "assistant",
              content: data.conclusion,
              chart_spec: data.chart_spec,
              result_table: data.result_table,
              created_at: new Date().toISOString(),
            });
          }
          if (state.busy) route();
        },
      },
    );
  } catch (error) {
    toast(errorMessage(error), "error");
  } finally {
    state.busy = false;
    state.progress = null;
    route();
  }
}

function renderHistoryPage(main) {
  const conversations = state.conversations || [];
  const list = conversations.length
    ? el("div", { class: "dataset-list" }, conversations.map(conversationRow))
    : emptyState(
        "还没有历史对话",
        "完成一次提问后，对话记录会保存在这里，方便随时回顾。",
        el("button", { class: "btn btn-primary", onclick: () => { location.hash = "#/chat"; }, text: "去提问" }),
      );
  main.replaceChildren(pageHead("历史对话", "查看、继续或删除你的对话记录。"), list);
}

function conversationRow(conversation) {
  const dataset = findDataset(conversation.dataset_id);
  return el("div", { class: "dataset-row" }, [
    el("div", { style: "min-width:0" }, [
      el("p", { class: "dataset-name", text: dataset?.name || `数据集 #${conversation.dataset_id}` }),
      el("div", { class: "dataset-meta", text: `对话 #${conversation.id} · ${formatDate(conversation.created_at)}` }),
    ]),
    el("div", { class: "actions" }, [
      el("button", { class: "btn btn-secondary btn-sm", text: "查看", onclick: () => openConversation(conversation) }),
      el("button", { class: "btn btn-danger btn-sm", text: "删除", onclick: () => deleteConversation(conversation) }),
    ]),
  ]);
}

async function openConversation(conversation) {
  try {
    const messages = await request(`/conversations/${conversation.id}/messages`);
    state.messages = (messages || []).map((message) => ({
      role: message.role,
      content: message.content,
      chart_spec: message.chart_spec || null,
      result_table: message.result_table || [],
      created_at: message.created_at,
    }));
    await openDataset(conversation.dataset_id, { keepConversation: true });
    state.currentConversationId = conversation.id;
    location.hash = "#/chat";
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function deleteConversation(conversation) {
  const ok = window.confirm(`确定删除对话 #${conversation.id} 吗？此操作无法恢复。`);
  if (!ok) return;
  try {
    await request(`/conversations/${conversation.id}`, { method: "DELETE" });
    state.conversations = state.conversations.filter((item) => Number(item.id) !== Number(conversation.id));
    if (Number(state.currentConversationId) === Number(conversation.id)) {
      state.currentConversationId = null;
      state.messages = [];
    }
    toast("对话已删除。", "success");
    route();
  } catch (error) {
    toast(errorMessage(error), "error");
  }
}

async function renderUsagePage(main) {
  main.replaceChildren(pageHead("我的用量", "查看本月 AI 调用次数、Token、费用与预算。"), spinner());
  try {
    const usage = await request("/account/ai-usage");
    state.usage = usage;
  } catch (error) {
    main.replaceChildren(pageHead("我的用量", "查看本月 AI 用量。"), emptyState("无法加载用量", errorMessage(error)));
    return;
  }

  const usage = state.usage;
  const usedRatio = usage.monthly_budget_usd > 0 ? usage.cost_usd / usage.monthly_budget_usd : 0;
  const percent = Math.min(100, Math.round(usedRatio * 100));
  const barClass = percent >= 100 ? "is-over" : percent >= 80 ? "is-high" : "";

  const metrics = [
    metric("本月调用", formatNumber(usage.calls), `${usage.successful_calls} 次成功 · ${usage.failed_calls} 次失败`),
    metric("Token 用量", formatNumber(usage.total_tokens), `输入 ${formatNumber(usage.prompt_tokens)} · 输出 ${formatNumber(usage.completion_tokens)}`),
    metric("本月费用", `$${usage.cost_usd.toFixed(4)}`, `预算 $${usage.monthly_budget_usd.toFixed(2)}`),
    metric("剩余预算", `$${usage.remaining_budget_usd.toFixed(4)}`, `统计周期 ${formatDate(usage.period_start)} 至 ${formatDate(usage.period_end)}`),
  ];

  const budget = el("div", { class: "card panel" }, [
    el("h3", { text: "预算使用情况" }),
    el("div", { class: "budget-bar" }, [
      el("span", { class: barClass, style: `width:${percent}%` }),
    ]),
    el("div", { class: "muted", text: `已使用 $${usage.cost_usd.toFixed(4)} / $${usage.monthly_budget_usd.toFixed(2)}（${percent}%）` }),
  ]);

  main.replaceChildren(
    pageHead("我的用量", "查看本月 AI 调用次数、Token、费用与预算。"),
    el("div", { class: "usage-grid" }, metrics),
    budget,
  );
}

function metric(label, value, note) {
  return el("div", { class: "card metric" }, [
    el("div", { class: "metric-label", text: label }),
    el("div", { class: "metric-value", text: value }),
    el("div", { class: "metric-note", text: note }),
  ]);
}

window.addEventListener("hashchange", () => {
  if (!state.session) {
    renderAuth();
    return;
  }
  const main = document.querySelector(".main");
  if (main) route();
});

boot();










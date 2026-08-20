const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const sendButton = document.querySelector("#send");
const stopButton = document.querySelector("#stop");
const chat = document.querySelector("#chat");
const workspace = document.querySelector(".workspace");
const intro = document.querySelector("#intro");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");
const accountButton = document.querySelector("#account-button");
const authPanel = document.querySelector("#auth-panel");
const authForm = document.querySelector("#auth-form");
const authTitle = document.querySelector("#auth-title");
const authError = document.querySelector("#auth-error");
const authUsername = document.querySelector("#auth-username");
const authPassword = document.querySelector("#auth-password");
const authConfirmPassword = document.querySelector("#auth-confirm-password");
const authConfirmGroup = document.querySelector("#auth-confirm-group");
const authLoginTab = document.querySelector("#auth-login-tab");
const authRegisterTab = document.querySelector("#auth-register-tab");
const authDescription = document.querySelector("#auth-description");
const authSubmit = document.querySelector("#auth-submit");

sendButton.textContent = "发送";
sendButton.setAttribute("aria-label", "发送消息");

const state = {
  threadId: "",
  messages: [],
  busy: false,
  controller: null,
  user: null,
  authMode: "login",
  registrationEnabled: true,
};

function userStorageKey() {
  return state.user ? `nba-chat-messages-${state.user.id}` : "nba-chat-messages";
}

function threadStorageKey() {
  return state.user ? `nba-chat-thread-${state.user.id}` : "nba-chat-thread";
}

function updateAccountButton() {
  accountButton.textContent = state.user ? `${state.user.username} · 退出` : "登录";
}

function persist() {
  localStorage.setItem(userStorageKey(), JSON.stringify(state.messages));
}

function newThreadId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  if (typeof crypto !== "undefined" && typeof crypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  return `thread-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function resetConversation() {
  state.threadId = newThreadId();
  state.messages = [];
  localStorage.setItem(threadStorageKey(), state.threadId);
  persist();
  chat.replaceChildren();
  intro.hidden = false;
}

function restoreConversation() {
  state.threadId = localStorage.getItem(threadStorageKey()) || newThreadId();
  state.messages = JSON.parse(localStorage.getItem(userStorageKey()) || "[]");
  localStorage.setItem(threadStorageKey(), state.threadId);
  chat.replaceChildren();
  state.messages.forEach(({ role, content }) => addMessage(role, content, false));
  intro.hidden = state.messages.length > 0;
}

function scrollToLatest() {
  const scroll = () => {
    workspace.scrollTo({
      top: workspace.scrollHeight,
      behavior: "smooth",
    });
  };

  requestAnimationFrame(scroll);
  setTimeout(scroll, 50);
  setTimeout(scroll, 250);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderInlineMarkdown(value) {
  let html = escapeHtml(value);
  // Escape first for safety, then render the inline emphasis used in tables.
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
  return html;
}

function renderMarkdown(value) {
  const lines = String(value).split("\n");
  const output = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (/^###\s+/.test(line) && index + 2 < lines.length && lines[index + 1].trim().startsWith("|") && /^\s*\|?\s*:?-{3,}/.test(lines[index + 2])) {
      const heading = escapeHtml(line.replace(/^###\s+/, ""));
      const rows = [];
      index += 1;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        index += 1;
      }
      if (rows.length) {
        const table = `<table><thead><tr>${rows[0].map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
        output.push(`<section class="team-card"><h3>${heading}</h3>${table}</section>`);
      }
      continue;
    }
    if (line.trim().startsWith("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1])) {
      const rows = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        index += 1;
      }
      if (rows.length) {
        output.push(`<table><thead><tr>${rows[0].map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>`);
        rows.slice(1).forEach((row) => {
          output.push(`<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`);
        });
        output.push("</tbody></table>");
      }
      continue;
    }
    let html = escapeHtml(line);
    html = html.replace(/^###\s+(.*)$/, "<h4>$1</h4>");
    html = html.replace(/^##\s+(.*)$/, "<h3>$1</h3>");
    html = html.replace(/^#\s+(.*)$/, "<h2>$1</h2>");
    html = html.replace(/^\s*[-*]\s+(.*)$/, "<li>$1</li>");
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    output.push(html);
    index += 1;
  }
  return output.join("\n").replace(/(<li>.*<\/li>\n?)+/g, (list) => `<ul>${list}</ul>`);
}

function addMessage(role, content, save = true, webSearchUsed = false, gameDataUsed = false, playerDataUsed = false, nbaApiGameUsed = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "您" : "NBA Chat";

  const text = document.createElement("div");
  text.className = "message-text";
  text.innerHTML = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);

  article.append(label, text);
  if (role === "assistant" && webSearchUsed) {
    const meta = document.createElement("div");
    meta.className = "message-meta";
    meta.textContent = "已联网检索 · Tavily";
    article.append(meta);
  }
  if (role === "assistant" && gameDataUsed) {
    const meta = document.createElement("div");
    meta.className = "message-meta local-data";
    meta.textContent = nbaApiGameUsed ? "已查询 nba_api 比赛数据" : "已查询本地 NBA 数据";
    article.append(meta);
  }
  if (role === "assistant" && playerDataUsed) {
    const meta = document.createElement("div");
    meta.className = "message-meta boxscore-data";
    meta.textContent = "已查询 nba_api Box Score";
    article.append(meta);
  }
  chat.append(article);
  intro.hidden = true;

  if (save) {
    state.messages.push({ role, content });
    persist();
  }
  return article;
}

function hideAuth() {
  authPanel.hidden = true;
  accountButton.hidden = false;
  authError.textContent = "";
}

function setAuthMode(mode) {
  state.authMode = mode === "register" && state.registrationEnabled ? "register" : "login";
  const registering = state.authMode === "register";
  authLoginTab.classList.toggle("active", !registering);
  authRegisterTab.classList.toggle("active", registering);
  authLoginTab.setAttribute("aria-selected", String(!registering));
  authRegisterTab.setAttribute("aria-selected", String(registering));
  authTitle.textContent = registering ? "注册 NBA Chat" : "登录 NBA Chat";
  authDescription.textContent = registering
    ? "创建账号后即可开始独立的 NBA 对话。"
    : "登录后，对话和 Agent 上下文会按账号隔离。";
  authSubmit.textContent = registering ? "创建账号" : "登录";
  authConfirmGroup.hidden = !registering;
  authConfirmPassword.required = registering;
  authPassword.autocomplete = registering ? "new-password" : "current-password";
  authError.textContent = "";
}

function showAuth(mode = "login") {
  setAuthMode(mode);
  accountButton.hidden = true;
  authPanel.hidden = false;
  authUsername.focus();
}

async function loadUser() {
  const response = await fetch("/api/auth/me");
  if (!response.ok) return false;
  state.user = await response.json();
  updateAccountButton();
  return true;
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    state.registrationEnabled = data.registration_enabled !== false;
    authRegisterTab.hidden = !state.registrationEnabled;
    statusDot.classList.toggle("ready", data.agent_ready);
    const authenticated = data.auth_required ? await loadUser() : true;
    if (!data.auth_required) {
      state.user = { id: "guest", username: "guest" };
      hideAuth();
      accountButton.hidden = true;
    }
    if (!authenticated) {
      updateAccountButton();
      showAuth();
      statusText.textContent = "请先登录";
      return;
    }
    const storedServerId = localStorage.getItem("nba-chat-server-instance");
    if (!storedServerId || storedServerId !== data.server_instance_id) {
      resetConversation();
      localStorage.setItem("nba-chat-server-instance", data.server_instance_id);
    } else {
      restoreConversation();
    }
    statusText.textContent = data.agent_ready ? "NBA Chat 在线" : "等待配置";
  } catch {
    statusText.textContent = "正在唤醒";
  }
}

async function submitMessage(message) {
  if (state.busy || !message.trim()) return;
  state.busy = true;
  input.value = "";
  input.style.height = "auto";
  sendButton.disabled = true;
  stopButton.hidden = false;
  state.controller = new AbortController();
  addMessage("user", message.trim());

  const pending = addMessage("assistant", "正在思考…", false);
  pending.classList.add("pending");
  scrollToLatest();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: state.controller.signal,
      body: JSON.stringify({ message: message.trim(), thread_id: state.threadId }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || "请求失败");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let metadata = {};
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "token") {
          answer += event.content || "";
          pending.querySelector(".message-text").innerHTML = renderMarkdown(answer);
          scrollToLatest();
        } else if (event.type === "metadata") {
          metadata = event;
        } else if (event.type === "error") {
          throw new Error(event.message || "请求失败");
        }
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      if (event.type === "metadata") metadata = event;
    }
    pending.remove();
    addMessage("assistant", metadata.answer || answer, true, metadata.web_search_used, metadata.game_data_used, metadata.player_data_used, metadata.nba_api_game_used);
    scrollToLatest();
  } catch (error) {
    if (error.name === "AbortError") {
      const text = pending.querySelector(".message-text");
      if (!answer) text.textContent = "已停止生成";
      pending.classList.remove("pending");
      pending.classList.add("stopped");
      return;
    }
    pending.querySelector(".message-text").textContent = error.message;
    pending.classList.remove("pending");
    pending.classList.add("error");
  } finally {
    state.busy = false;
    state.controller = null;
    sendButton.disabled = false;
    stopButton.hidden = true;
    input.focus();
  }
}

stopButton.addEventListener("click", () => {
  if (state.controller) state.controller.abort();
});

accountButton.addEventListener("click", async () => {
  if (!state.user) {
    showAuth();
    return;
  }
  await fetch("/api/auth/logout", { method: "POST" });
  state.user = null;
  state.messages = [];
  chat.replaceChildren();
  updateAccountButton();
  showAuth();
});

authLoginTab.addEventListener("click", () => setAuthMode("login"));
authRegisterTab.addEventListener("click", () => setAuthMode("register"));

authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  authError.textContent = "";

  if (state.authMode === "register" && authPassword.value !== authConfirmPassword.value) {
    authError.textContent = "两次输入的密码不一致";
    return;
  }

  authSubmit.disabled = true;
  const endpoint = state.authMode === "register" ? "/api/auth/register" : "/api/auth/login";
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: authUsername.value.trim(),
        password: authPassword.value,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const validationMessage = Array.isArray(data.detail)
        ? data.detail.map((item) => item.msg).filter(Boolean).join("；")
        : data.detail;
      throw new Error(validationMessage || "操作失败");
    }

    state.user = data;
    if (localStorage.getItem(threadStorageKey())) {
      restoreConversation();
    } else {
      resetConversation();
    }
    updateAccountButton();
    hideAuth();
    statusText.textContent = "NBA Chat 在线";
    authPassword.value = "";
    authConfirmPassword.value = "";
  } catch (error) {
    authError.textContent = error.message;
  } finally {
    authSubmit.disabled = false;
  }
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  submitMessage(input.value);
});

input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 160)}px`;
});

document.querySelectorAll("[data-prompt]").forEach((button) => {
  button.addEventListener("click", () => submitMessage(button.dataset.prompt));
});

document.querySelector("#new-chat").addEventListener("click", () => {
  resetConversation();
  input.focus();
});

checkHealth();

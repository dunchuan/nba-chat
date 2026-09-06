const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const sendButton = document.querySelector("#send");
const stopButton = document.querySelector("#stop");
const chat = document.querySelector("#chat");
const workspace = document.querySelector(".workspace");
const intro = document.querySelector("#intro");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");
const accountActions = document.querySelector("#account-actions");
const accountUsername = document.querySelector("#account-username");
const logoutButton = document.querySelector("#logout-button");
const authPanel = document.querySelector("#auth-panel");
const authForm = document.querySelector("#auth-form");
const authError = document.querySelector("#auth-error");
const authUsername = document.querySelector("#auth-username");
const authPassword = document.querySelector("#auth-password");
const authConfirmPassword = document.querySelector("#auth-confirm-password");
const authConfirmGroup = document.querySelector("#auth-confirm-group");
const authLoginTab = document.querySelector("#auth-login-tab");
const authRegisterTab = document.querySelector("#auth-register-tab");
const authSubmit = document.querySelector("#auth-submit");
const sidebarNewChatButton = document.querySelector("#sidebar-new-chat");
const conversationList = document.querySelector("#conversation-list");
const clearConversationsButton = document.querySelector("#clear-conversations");
const clearConversationsModal = document.querySelector("#clear-conversations-modal");
const clearConversationsCancel = document.querySelector("#clear-conversations-cancel");
const clearConversationsConfirm = document.querySelector("#clear-conversations-confirm");
const renameConversationModal = document.querySelector("#rename-conversation-modal");
const renameConversationInput = document.querySelector("#rename-conversation-input");
const renameConversationCancel = document.querySelector("#rename-conversation-cancel");
const renameConversationSave = document.querySelector("#rename-conversation-save");
const deleteConversationModal = document.querySelector("#delete-conversation-modal");
const deleteConversationCancel = document.querySelector("#delete-conversation-cancel");
const deleteConversationConfirm = document.querySelector("#delete-conversation-confirm");
const appLayout = document.querySelector(".app-layout");
const sidebarToggle = document.querySelector("#sidebar-toggle");
const mobileSidebarToggle = document.querySelector("#mobile-sidebar-toggle");
const sidebarScrim = document.querySelector("#sidebar-scrim");
const appNotice = document.querySelector("#app-notice");
let touchStartX = 0;
let touchStartY = 0;
let trackingSidebarSwipe = false;
let noticeTimer = null;

const state = {
  threadId: "",
  messages: [],
  busy: false,
  controller: null,
  user: null,
  authStatus: "loading",
  authMode: "login",
  registrationEnabled: true,
  conversations: [],
  renamingThreadId: "",
  deletingThreadId: "",
  pendingRecoveryTimer: null,
  conversationRuntime: new Map(),
};

function threadStorageKey() {
  return state.user ? `nba-chat-thread-${state.user.id}` : "nba-chat-thread";
}

function notify(message) {
  if (!appNotice) return;
  appNotice.textContent = message;
  appNotice.hidden = false;
  if (noticeTimer) window.clearTimeout(noticeTimer);
  noticeTimer = window.setTimeout(() => {
    appNotice.hidden = true;
  }, 3000);
}

function pendingStorageKey(threadId = state.threadId) {
  return state.user && threadId ? `nba-chat-pending-${state.user.id}-${threadId}` : "";
}

function markPendingMessage(threadId) {
  const key = pendingStorageKey(threadId);
  if (!key) return;
  localStorage.setItem(key, JSON.stringify({ threadId, startedAt: Date.now() }));
}

function getPendingMessage(threadId = state.threadId) {
  const key = pendingStorageKey(threadId);
  if (!key) return null;
  try {
    const pending = JSON.parse(localStorage.getItem(key) || "null");
    if (!pending?.threadId || Date.now() - Number(pending.startedAt) > 15 * 60 * 1000) {
      localStorage.removeItem(key);
      return null;
    }
    return pending;
  } catch {
    localStorage.removeItem(key);
    return null;
  }
}

function clearPendingMessage(threadId = state.threadId) {
  const key = pendingStorageKey(threadId);
  if (!key) return;
  localStorage.removeItem(key);
}

function clearAllPendingMessages() {
  if (!state.user) return;
  const prefix = `nba-chat-pending-${state.user.id}-`;
  for (let index = localStorage.length - 1; index >= 0; index -= 1) {
    const key = localStorage.key(index);
    if (key?.startsWith(prefix)) localStorage.removeItem(key);
  }
}

function getConversationRuntime(threadId = state.threadId) {
  if (!state.conversationRuntime.has(threadId)) {
    state.conversationRuntime.set(threadId, {
      busy: false,
      stopping: false,
      controller: null,
      answer: "",
      pendingArticle: null,
    });
  }
  return state.conversationRuntime.get(threadId);
}

function hasBusyConversation() {
  return Array.from(state.conversationRuntime.values()).some((runtime) => runtime.busy);
}

function updateComposerState() {
  const runtime = getConversationRuntime();
  sendButton.disabled = runtime.busy;
  stopButton.hidden = !runtime.busy;
  stopButton.disabled = runtime.stopping;
  stopButton.textContent = runtime.stopping ? "停止中…" : "停止";
}

function isAuthenticated() {
  return state.authStatus === "authenticated";
}

function isAppReady() {
  return state.authStatus === "authenticated" || state.authStatus === "anonymous";
}

function applyAuthState(status, user = null) {
  state.authStatus = status;
  state.user = user;
  const appReady = isAppReady();
  const authenticated = isAuthenticated();
  document.querySelector(".shell")?.classList.toggle("auth-ready", appReady);
  authPanel.hidden = appReady;
  accountActions.hidden = !authenticated;
  accountUsername.textContent = authenticated ? user.username : "";
  updateSidebarControls();
}

function updateSidebarControls() {
  const enabled = isAuthenticated();
  if (!enabled) setMobileSidebarOpen(false);
  [sidebarToggle, mobileSidebarToggle].forEach((button) => {
    if (!button) return;
    button.disabled = !enabled;
    button.style.display = enabled ? "" : "none";
    button.setAttribute("aria-disabled", String(!enabled));
  });
}

function setSidebarCollapsed(collapsed, persistPreference = true) {
  appLayout?.classList.toggle("sidebar-collapsed", collapsed);
  if (sidebarToggle) {
    const label = collapsed ? "展开侧栏" : "收起侧栏";
    sidebarToggle.setAttribute("aria-label", label);
    sidebarToggle.setAttribute("title", label);
  }
  if (persistPreference) localStorage.setItem("nba-chat-sidebar-collapsed", String(collapsed));
}

function setMobileSidebarOpen(open) {
  appLayout?.classList.toggle("mobile-sidebar-open", open);
  if (mobileSidebarToggle) {
    const label = open ? "关闭会话历史" : "打开会话历史";
    mobileSidebarToggle.textContent = open ? "‹" : "›";
    mobileSidebarToggle.hidden = false;
    mobileSidebarToggle.style.display = open ? "none" : "";
    mobileSidebarToggle.setAttribute("aria-label", label);
    mobileSidebarToggle.setAttribute("title", label);
  }
}

function conversationTitle(messages) {
  const firstQuestion = messages.find((message) => message.role === "user" && message.content)?.content;
  return firstQuestion ? String(firstQuestion).replace(/\s+/g, " ").trim() : "新对话";
}

function formatConversationTime(updatedAt) {
  const elapsed = Date.now() - Number(updatedAt || 0);
  if (elapsed < 60_000) return "刚刚";
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)} 分钟前`;
  if (elapsed < 86_400_000) return "今天";
  return new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(new Date(updatedAt));
}

function renderConversationList() {
  if (!conversationList) return;
  conversationList.replaceChildren();
  if (!state.conversations.length) {
    const empty = document.createElement("p");
    empty.className = "conversation-empty";
    empty.textContent = "开始一个新对话后，会话将显示在这里。";
    conversationList.append(empty);
    return;
  }

  state.conversations.forEach((conversation) => {
    const item = document.createElement("div");
    item.className = "conversation-item";
    item.classList.toggle("active", conversation.id === state.threadId);

    const selectButton = document.createElement("button");
    selectButton.type = "button";
    selectButton.className = "conversation-item-main";
    selectButton.dataset.threadId = conversation.id;
    selectButton.innerHTML = `<span class="conversation-item-title"></span><span class="conversation-item-time"></span>`;
    selectButton.querySelector(".conversation-item-title").textContent = conversation.title;
    selectButton.querySelector(".conversation-item-time").textContent = formatConversationTime(conversation.updatedAt);
    selectButton.addEventListener("click", () => selectConversation(conversation.id));

    const renameButton = document.createElement("button");
    renameButton.type = "button";
    renameButton.className = "conversation-rename";
    renameButton.setAttribute("aria-label", "重命名对话");
    renameButton.setAttribute("title", "重命名对话");
    renameButton.textContent = "✎";
    renameButton.addEventListener("click", () => openRenameConversationModal(conversation.id));

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "conversation-delete";
    deleteButton.setAttribute("aria-label", "删除对话");
    deleteButton.setAttribute("title", "删除对话");
    deleteButton.textContent = "×";
    deleteButton.addEventListener("click", () => openDeleteConversationModal(conversation.id));

    item.append(selectButton, renameButton, deleteButton);
    conversationList.append(item);
  });
}

async function loadConversations() {
  const response = await fetch("/api/conversations");
  if (!response.ok) throw new Error("无法加载历史对话");
  const data = await response.json();
  state.conversations = (data.conversations || []).map((conversation) => ({
    id: conversation.thread_id,
    title: conversation.title,
    updatedAt: Number(conversation.updated_at) * 1000,
  }));
  renderConversationList();
}

function persist() {
  // Visible messages are persisted by the server during /api/chat. The browser
  // only keeps the selected thread ID as a UI preference.
  renderConversationList();
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
  chat.replaceChildren();
  intro.hidden = false;
  updateComposerState();
  renderConversationList();
}

async function restoreConversation() {
  await loadConversations();
  state.threadId = localStorage.getItem(threadStorageKey()) || newThreadId();
  const selected = state.conversations.find((item) => item.id === state.threadId);
  state.messages = [];
  localStorage.setItem(threadStorageKey(), state.threadId);
  chat.replaceChildren();
  if (selected) {
    await loadConversationMessages(selected.id);
  } else {
    intro.hidden = false;
  }
  renderConversationList();
  recoverPendingMessage(selected?.id);
}

function recoverPendingMessage(threadId) {
  if (!threadId) return;
  const runtime = getConversationRuntime(threadId);
  if (runtime.busy) {
    const article = addMessage("assistant", runtime.answer || "正在思考…", false);
    article.classList.add("pending");
    runtime.pendingArticle = article;
    return;
  }
  const pending = getPendingMessage(threadId);
  const selectedConversation = state.conversations.find((conversation) => conversation.id === threadId);
  const recentlyUpdated = selectedConversation && Date.now() - selectedConversation.updatedAt < 15 * 60 * 1000;
  const lastMessageIsUser = state.messages.at(-1)?.role === "user";
  if ((!pending || pending.threadId !== threadId) && !(recentlyUpdated && lastMessageIsUser)) return;
  if (state.messages.some((message) => message.role === "assistant")) {
    clearPendingMessage(threadId);
    return;
  }
  const article = addMessage("assistant", "正在思考…", false);
  article.classList.add("pending");
  runtime.pendingArticle = article;
  pollPendingMessage(threadId, article);
}

function pollPendingMessage(threadId, article) {
  if (state.pendingRecoveryTimer) window.clearTimeout(state.pendingRecoveryTimer);
  const poll = async () => {
    if (!isAuthenticated() || state.threadId !== threadId || !article.isConnected) return;
    try {
      const response = await fetch(`/api/conversations/${encodeURIComponent(threadId)}`);
      if (response.status === 404) {
        clearPendingMessage(threadId);
        return;
      }
      if (!response.ok) throw new Error("pending conversation unavailable");
      const data = await response.json();
      if (data.messages?.some((message) => message.role === "assistant")) {
        clearPendingMessage(threadId);
        getConversationRuntime(threadId).pendingArticle = null;
        await loadConversationMessages(threadId);
        await loadConversations();
        return;
      }
      state.pendingRecoveryTimer = window.setTimeout(poll, 2000);
    } catch {
      state.pendingRecoveryTimer = window.setTimeout(poll, 3000);
    }
  };
  state.pendingRecoveryTimer = window.setTimeout(poll, 1500);
}

async function loadConversationMessages(threadId) {
  const response = await fetch(`/api/conversations/${encodeURIComponent(threadId)}`);
  if (!response.ok) throw new Error("无法加载该对话");
  const data = await response.json();
  state.messages = data.messages || [];
  chat.replaceChildren();
  state.messages.forEach(({ role, content }) => addMessage(role, content, false));
  intro.hidden = state.messages.length > 0;
}

async function selectConversation(threadId) {
  if (threadId === state.threadId) return;
  const selected = state.conversations.find((item) => item.id === threadId);
  if (!selected) return;
  state.threadId = selected.id;
  localStorage.setItem(threadStorageKey(), state.threadId);
  try {
    await loadConversationMessages(threadId);
    recoverPendingMessage(threadId);
    updateComposerState();
    renderConversationList();
    scrollToLatest("auto");
  } catch (error) {
    console.error(error);
  }
}

function openClearConversationsModal() {
  if (!clearConversationsModal) return;
  if (hasBusyConversation()) {
    notify("正在生成回答，请等待完成后再删除对话");
    return;
  }
  if (!state.conversations.length) {
    notify("当前没有可删除的对话");
    return;
  }
  clearConversationsModal.hidden = false;
  clearConversationsCancel?.focus();
}

function closeClearConversationsModal() {
  if (!clearConversationsModal) return;
  clearConversationsModal.hidden = true;
  clearConversationsButton?.focus();
}

function openRenameConversationModal(threadId) {
  if (!renameConversationModal || getConversationRuntime(threadId).busy) return;
  const conversation = state.conversations.find((item) => item.id === threadId);
  if (!conversation) return;
  state.renamingThreadId = threadId;
  renameConversationInput.value = conversation.title;
  renameConversationModal.hidden = false;
  requestAnimationFrame(() => {
    renameConversationInput?.focus();
    renameConversationInput?.select();
  });
}

function closeRenameConversationModal() {
  if (!renameConversationModal) return;
  renameConversationModal.hidden = true;
  state.renamingThreadId = "";
}

async function saveConversationRename() {
  const title = renameConversationInput?.value.trim();
  if (!state.renamingThreadId || !title) return;
  const conversation = state.conversations.find((item) => item.id === state.renamingThreadId);
  if (!conversation) return;
  const response = await fetch(`/api/conversations/${encodeURIComponent(state.renamingThreadId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) return;
  conversation.title = title;
  closeRenameConversationModal();
  renderConversationList();
}

async function clearAllConversations() {
  const response = await fetch("/api/conversations", { method: "DELETE" });
  if (!response.ok) {
    notify("清空对话失败，请稍后重试");
    return;
  }
  clearAllPendingMessages();
  state.conversations = [];
  closeClearConversationsModal();
  resetConversation();
}

function openDeleteConversationModal(threadId) {
  if (!deleteConversationModal) return;
  if (getConversationRuntime(threadId).busy) {
    notify("正在生成回答，请等待完成后再删除对话");
    return;
  }
  state.deletingThreadId = threadId;
  deleteConversationModal.hidden = false;
  deleteConversationCancel?.focus();
}

function closeDeleteConversationModal() {
  if (!deleteConversationModal) return;
  deleteConversationModal.hidden = true;
  state.deletingThreadId = "";
}

async function deleteSelectedConversation() {
  const threadId = state.deletingThreadId;
  if (!threadId) return;
  const response = await fetch(`/api/conversations/${encodeURIComponent(threadId)}`, { method: "DELETE" });
  if (!response.ok) {
    notify("删除对话失败，请稍后重试");
    return;
  }
  clearPendingMessage(threadId);
  closeDeleteConversationModal();
  if (threadId === state.threadId) resetConversation();
  await loadConversations();
}

function scrollToLatest(behavior = "smooth") {
  const scroll = () => {
    workspace.scrollTo({
      top: workspace.scrollHeight,
      behavior,
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
    const sectionLabel = /^\*\*(.+?[：:])\*\*$/.exec(line.trim());
    if (sectionLabel) {
      while (output.length && output[output.length - 1] === "") output.pop();
      output.push(`<h4 class="section-label">${escapeHtml(sectionLabel[1])}</h4>`);
      index += 1;
      continue;
    }
    const teamHeading = /^(?:##|###)\s+/.exec(line);
    let tableStart = index + 1;
    while (tableStart < lines.length && !lines[tableStart].trim()) tableStart += 1;
    if (teamHeading && tableStart + 1 < lines.length && lines[tableStart].trim().startsWith("|") && /^\s*\|?\s*:?-{3,}/.test(lines[tableStart + 1])) {
      const heading = escapeHtml(line.replace(/^#{2,3}\s+/, ""));
      const rows = [];
      index = tableStart;
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        const cells = lines[index].trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
        if (!cells.every((cell) => /^:?-{3,}:?$/.test(cell))) rows.push(cells);
        index += 1;
      }
      if (rows.length) {
        const table = `<table><thead><tr>${rows[0].map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr></thead><tbody>${rows.slice(1).map((row) => `<tr>${row.map((cell) => `<td>${renderInlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
        output.push(`<section class="team-card"><h3>${heading}</h3><div class="table-scroll">${table}</div></section>`);
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
  return output.join("\n")
    .replace(/(<li>.*<\/li>\n?)+/g, (list) => `<ul>${list}</ul>`)
    .replace(/(<\/(?:table|section)>)\s*(<h4 class="section-label">)/g, "$1$2")
    .replace(/(<\/h4>)\s*(<ul>)/g, "$1$2");
}

function addMessage(role, content, save = true, webSearchUsed = false, gameDataUsed = false, playerDataUsed = false, nbaApiGameUsed = false) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  if (role === "assistant") {
    const identity = document.createElement("div");
    identity.className = "assistant-identity";
    identity.setAttribute("aria-label", "NBA 数据助手");
    article.append(identity);
  }

  const text = document.createElement("div");
  text.className = "message-text";
  text.innerHTML = role === "assistant" ? renderMarkdown(content) : escapeHtml(content);

  article.append(text);
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

function markGenerationStopped(article, threadId, answer = "") {
  if (!article?.isConnected) return;
  const text = article.querySelector(".message-text");
  if (text && !answer) text.textContent = "已停止生成";
  article.classList.remove("pending", "error");
  article.classList.add("stopped");
  clearPendingMessage(threadId);
  if (answer && !article.querySelector(".generation-status")) {
    const status = document.createElement("div");
    status.className = "generation-status";
    status.textContent = "已停止生成";
    article.append(status);
  }
  if (article.querySelector(".regenerate-message")) return;

  const regenerateButton = document.createElement("button");
  regenerateButton.type = "button";
  regenerateButton.className = "regenerate-message";
  regenerateButton.textContent = "重新生成";
  regenerateButton.addEventListener("click", () => {
    const originalMessage = [...state.messages]
      .reverse()
      .find((message) => message.role === "user" && message.content)?.content;
    if (!originalMessage) return;
    article.remove();
    submitMessage(originalMessage, { regenerate: true });
  });
  article.append(regenerateButton);
}

function setAuthMode(mode) {
  state.authMode = mode === "register" && state.registrationEnabled ? "register" : "login";
  const registering = state.authMode === "register";
  authLoginTab.classList.toggle("active", !registering);
  authRegisterTab.classList.toggle("active", registering);
  authLoginTab.setAttribute("aria-selected", String(!registering));
  authRegisterTab.setAttribute("aria-selected", String(registering));
  authSubmit.textContent = registering ? "创建账号" : "登录";
  authConfirmGroup.hidden = !registering;
  authConfirmPassword.required = registering;
  authPassword.autocomplete = registering ? "new-password" : "current-password";
  authError.textContent = "";
}

function showAuth(mode = "login", focusInput = false) {
  // Health checks may call this repeatedly while the service is starting.
  // Avoid rewriting the form on every poll: DOM text updates reset DevTools
  // selections and make the login screen appear to flicker.
  const nextMode = mode === "register" && state.registrationEnabled ? "register" : "login";
  const wasHidden = authPanel.hidden;
  applyAuthState("unauthenticated");
  if (state.authMode !== nextMode) setAuthMode(nextMode);
  if (focusInput && wasHidden) authUsername.focus();
}

async function loadUser() {
  const response = await fetch("/api/auth/me");
  if (!response.ok) return false;
  return await response.json();
}

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    state.registrationEnabled = data.registration_enabled !== false;
    authRegisterTab.hidden = !state.registrationEnabled;
    statusDot.classList.toggle("ready", data.agent_ready);
    if (!data.database_ready) {
      showAuth("login", false);
      statusText.textContent = data.status === "error" ? "服务初始化失败" : "正在启动…";
      window.setTimeout(checkHealth, 800);
      return;
    }
    const user = data.auth_required ? await loadUser() : { id: "guest", username: "guest" };
    if (!user) {
      showAuth();
      statusText.textContent = "请先登录";
      return;
    }
    state.user = user;
    await restoreConversation();
    applyAuthState(data.auth_required ? "authenticated" : "anonymous", user);
    statusText.textContent = data.agent_ready ? "NBA Chat 在线" : "等待配置";
  } catch {
    statusText.textContent = "正在唤醒";
  }
}

async function submitMessage(message, options = {}) {
  const threadId = state.threadId;
  const runtime = getConversationRuntime(threadId);
  const regenerate = options.regenerate === true;
  if (runtime.busy || !message.trim()) return;
  const normalizedMessage = message.trim();
  runtime.busy = true;
  runtime.stopping = false;
  runtime.answer = "";
  input.value = "";
  input.style.height = "auto";
  updateComposerState();
  runtime.controller = new AbortController();
  if (!regenerate) addMessage("user", normalizedMessage);
  markPendingMessage(threadId);

  const pending = addMessage("assistant", "正在思考…", false);
  pending.classList.add("pending");
  runtime.pendingArticle = pending;
  scrollToLatest();

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: runtime.controller.signal,
    body: JSON.stringify({ message: normalizedMessage, thread_id: threadId, regenerate }),
    });
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      if (response.status === 409 && errorData.detail === "conversation_busy") {
        throw new Error("该对话正在生成回答，请等待当前回答完成。");
      }
      if (response.status === 409 && errorData.detail === "regenerate_unavailable") {
        throw new Error("当前消息没有可重新生成的回答。");
      }
      throw new Error(errorData.detail || "请求失败");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let answer = "";
    let metadata = {};
    let cancelled = false;
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
          runtime.answer = answer;
          if (runtime.pendingArticle?.isConnected) {
            runtime.pendingArticle.querySelector(".message-text").innerHTML = renderMarkdown(answer);
            if (state.threadId === threadId) scrollToLatest();
          }
        } else if (event.type === "metadata") {
          metadata = event;
        } else if (event.type === "error") {
          throw new Error(event.message || "请求失败");
        } else if (event.type === "cancelled") {
          cancelled = true;
        }
      }
      if (done) break;
    }
    if (buffer.trim()) {
      const event = JSON.parse(buffer);
      if (event.type === "metadata") metadata = event;
    }
    if (cancelled) {
      markGenerationStopped(runtime.pendingArticle, threadId, answer);
      return;
    }
    if (runtime.pendingArticle?.isConnected) runtime.pendingArticle.remove();
    runtime.pendingArticle = null;
    clearPendingMessage(threadId);
    if (state.threadId === threadId) {
      addMessage("assistant", metadata.answer || answer, true, metadata.web_search_used, metadata.game_data_used, metadata.player_data_used, metadata.nba_api_game_used);
    }
    await loadConversations();
    if (state.threadId === threadId) scrollToLatest();
  } catch (error) {
    if (error.name === "AbortError") {
      if (runtime.stopping) markGenerationStopped(runtime.pendingArticle, threadId, answer);
      return;
    }
    clearPendingMessage(threadId);
    if (runtime.pendingArticle?.isConnected) {
      runtime.pendingArticle.querySelector(".message-text").textContent = error.message;
      runtime.pendingArticle.classList.remove("pending");
      runtime.pendingArticle.classList.add("error");
    }
  } finally {
    runtime.busy = false;
    runtime.stopping = false;
    runtime.controller = null;
    if (state.threadId === threadId) {
      updateComposerState();
      input.focus();
    }
  }
}

stopButton.addEventListener("click", async () => {
  const threadId = state.threadId;
  const runtime = getConversationRuntime(threadId);
  if (!runtime.busy || runtime.stopping) return;
  runtime.stopping = true;
  updateComposerState();
  try {
    const response = await fetch(`/api/conversations/${encodeURIComponent(threadId)}/cancel`, { method: "POST" });
    if (!response.ok) throw new Error("停止生成失败");
    runtime.controller?.abort();
  } catch (error) {
    runtime.stopping = false;
    updateComposerState();
    notify(error.message || "停止生成失败");
  }
});

logoutButton.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  applyAuthState("unauthenticated");
  state.messages = [];
  chat.replaceChildren();
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
    await restoreConversation();
    applyAuthState("authenticated", data);
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

function startNewConversation() {
  resetConversation();
  setMobileSidebarOpen(false);
  input.focus();
}

document.querySelector("#new-chat")?.addEventListener("click", startNewConversation);
sidebarNewChatButton?.addEventListener("click", startNewConversation);

clearConversationsButton?.addEventListener("click", openClearConversationsModal);
clearConversationsCancel?.addEventListener("click", closeClearConversationsModal);
clearConversationsConfirm?.addEventListener("click", clearAllConversations);
renameConversationCancel?.addEventListener("click", closeRenameConversationModal);
renameConversationSave?.addEventListener("click", saveConversationRename);
renameConversationInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") saveConversationRename();
});
renameConversationModal?.addEventListener("click", (event) => {
  if (event.target === renameConversationModal) closeRenameConversationModal();
});
deleteConversationCancel?.addEventListener("click", closeDeleteConversationModal);
deleteConversationConfirm?.addEventListener("click", deleteSelectedConversation);
deleteConversationModal?.addEventListener("click", (event) => {
  if (event.target === deleteConversationModal) closeDeleteConversationModal();
});
clearConversationsModal?.addEventListener("click", (event) => {
  if (event.target === clearConversationsModal) closeClearConversationsModal();
});
sidebarToggle?.addEventListener("click", () => {
  if (!isAuthenticated()) return;
  if (window.matchMedia("(max-width: 620px)").matches) {
    setMobileSidebarOpen(false);
    return;
  }
  setSidebarCollapsed(!appLayout?.classList.contains("sidebar-collapsed"));
});
mobileSidebarToggle?.addEventListener("click", () => {
  if (!isAuthenticated()) return;
  setMobileSidebarOpen(!appLayout?.classList.contains("mobile-sidebar-open"));
});
sidebarScrim?.addEventListener("click", () => {
  setMobileSidebarOpen(false);
});

document.addEventListener("touchstart", (event) => {
  if (!isAuthenticated() || !window.matchMedia("(max-width: 620px)").matches) return;
  const sidebarOpen = appLayout?.classList.contains("mobile-sidebar-open");
  const touch = event.touches[0];
  if (!touch) return;
  touchStartX = touch.clientX;
  touchStartY = touch.clientY;
  trackingSidebarSwipe = true;
}, { passive: true });

document.addEventListener("touchend", (event) => {
  if (!trackingSidebarSwipe) return;
  trackingSidebarSwipe = false;
  if (!isAuthenticated() || !window.matchMedia("(max-width: 620px)").matches) return;
  const touch = event.changedTouches[0];
  if (!touch) return;
  const deltaX = touch.clientX - touchStartX;
  const deltaY = Math.abs(touch.clientY - touchStartY);
  if (Math.abs(deltaX) < 60 || Math.abs(deltaX) < deltaY * 1.25) return;
  const sidebarOpen = appLayout?.classList.contains("mobile-sidebar-open");
  if (!sidebarOpen && deltaX > 0) setMobileSidebarOpen(true);
  if (sidebarOpen && deltaX < 0) setMobileSidebarOpen(false);
}, { passive: true });

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (!renameConversationModal?.hidden) closeRenameConversationModal();
  if (!deleteConversationModal?.hidden) closeDeleteConversationModal();
  if (!clearConversationsModal?.hidden) closeClearConversationsModal();
});

setSidebarCollapsed(localStorage.getItem("nba-chat-sidebar-collapsed") === "true", false);
setMobileSidebarOpen(false);
applyAuthState("loading");
checkHealth();

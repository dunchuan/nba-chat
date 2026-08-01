const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const sendButton = document.querySelector("#send");
const chat = document.querySelector("#chat");
const intro = document.querySelector("#intro");
const statusDot = document.querySelector("#status-dot");
const statusText = document.querySelector("#status-text");

const state = {
  threadId: localStorage.getItem("pocket-agent-thread") || crypto.randomUUID(),
  messages: JSON.parse(localStorage.getItem("pocket-agent-messages") || "[]"),
  busy: false,
};

localStorage.setItem("pocket-agent-thread", state.threadId);

function persist() {
  localStorage.setItem("pocket-agent-messages", JSON.stringify(state.messages));
}

function addMessage(role, content, save = true) {
  const article = document.createElement("article");
  article.className = `message ${role}`;

  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "user" ? "你" : "Pocket Agent";

  const text = document.createElement("div");
  text.className = "message-text";
  text.textContent = content;

  article.append(label, text);
  chat.append(article);
  intro.hidden = true;
  article.scrollIntoView({ behavior: "smooth", block: "end" });

  if (save) {
    state.messages.push({ role, content });
    persist();
  }
  return article;
}

state.messages.forEach(({ role, content }) => addMessage(role, content, false));

async function checkHealth() {
  try {
    const response = await fetch("/api/health");
    const data = await response.json();
    statusDot.classList.toggle("ready", data.agent_ready);
    statusText.textContent = data.agent_ready ? "Agent 在线" : "等待配置";
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
  addMessage("user", message.trim());

  const pending = addMessage("assistant", "正在思考…", false);
  pending.classList.add("pending");

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message.trim(), thread_id: state.threadId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "请求失败");
    pending.remove();
    addMessage("assistant", data.answer);
  } catch (error) {
    pending.querySelector(".message-text").textContent = error.message;
    pending.classList.remove("pending");
    pending.classList.add("error");
  } finally {
    state.busy = false;
    sendButton.disabled = false;
    input.focus();
  }
}

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
  state.threadId = crypto.randomUUID();
  state.messages = [];
  localStorage.setItem("pocket-agent-thread", state.threadId);
  persist();
  chat.replaceChildren();
  intro.hidden = false;
  input.focus();
});

checkHealth();


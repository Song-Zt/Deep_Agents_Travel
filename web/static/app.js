/* 旅行助手前端：会话管理 + SSE 流式对话 + 工具调用展示 */

const state = {
  sessionId: null,
  sending: false,
  sessions: [],
};

const els = {
  sessionList: document.getElementById("session-list"),
  messages: document.getElementById("messages"),
  emptyState: document.getElementById("empty-state"),
  title: document.getElementById("chat-title"),
  status: document.getElementById("status"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  composer: document.getElementById("composer"),
  newSession: document.getElementById("new-session"),
  connDot: document.getElementById("conn-dot"),
  connText: document.getElementById("conn-text"),
};

/* ---------------- 基础工具 ---------------- */

function el(tag, className) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  return node;
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function renderInline(text) {
  return text
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(
      /\[([^\]]+)\]\((https?:[^)\s]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener">$1</a>'
    );
}

/* 轻量 Markdown：标题、列表、代码块、加粗、行内代码、链接 */
function renderMarkdown(text) {
  const lines = escapeHtml(text).split("\n");
  const html = [];

  let inCode = false;
  let codeLines = [];
  let listType = null;

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  for (const line of lines) {
    if (/^```[\w-]*\s*$/.test(line)) {
      if (inCode) {
        html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
        codeLines = [];
        inCode = false;
      } else {
        closeList();
        inCode = true;
      }
      continue;
    }

    if (inCode) {
      codeLines.push(line);
      continue;
    }

    if (!line.trim()) {
      closeList();
      continue;
    }

    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }

    if (/^\s*[-*+]\s+/.test(line)) {
      if (listType !== "ul") {
        closeList();
        html.push("<ul>");
        listType = "ul";
      }
      html.push(`<li>${renderInline(line.replace(/^\s*[-*+]\s+/, ""))}</li>`);
      continue;
    }

    if (/^\s*\d+[.、)]\s+/.test(line)) {
      if (listType !== "ol") {
        closeList();
        html.push("<ol>");
        listType = "ol";
      }
      html.push(`<li>${renderInline(line.replace(/^\s*\d+[.、)]\s+/, ""))}</li>`);
      continue;
    }

    if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) {
      closeList();
      html.push("<hr>");
      continue;
    }

    closeList();
    html.push(`<p>${renderInline(line)}</p>`);
  }

  if (inCode) {
    html.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
  }

  closeList();

  return html.join("");
}

function isNearBottom() {
  const box = els.messages;
  return box.scrollHeight - box.scrollTop - box.clientHeight < 120;
}

function scrollToBottom(force = false) {
  if (force || isNearBottom()) {
    els.messages.scrollTop = els.messages.scrollHeight;
  }
}

function setStatus(text, busy = false) {
  els.status.textContent = text;
  els.status.classList.toggle("busy", busy);
}

function hideEmptyState() {
  if (els.emptyState && els.emptyState.parentNode) {
    els.emptyState.remove();
  }
}

function showEmptyState() {
  hideEmptyState();

  const wrapper = el("div", "empty-state");
  wrapper.id = "empty-state";
  wrapper.innerHTML = `
    <div class="empty-mark">✦</div>
    <h2>想去哪儿玩？</h2>
    <p>试试问我：</p>
    <div class="suggestions">
      <button class="suggestion" type="button">推荐几个北京经典景点</button>
      <button class="suggestion" type="button">从故宫到天坛怎么走？</button>
      <button class="suggestion" type="button">上海玩三天大概要花多少钱？</button>
    </div>
  `;

  els.messages.appendChild(wrapper);
  els.emptyState = wrapper;
  bindSuggestions(wrapper);
}

function bindSuggestions(root) {
  root.querySelectorAll(".suggestion").forEach((button) => {
    button.addEventListener("click", () => {
      els.input.value = button.textContent.trim();
      autoResize();
      updateSendState();
      els.composer.requestSubmit();
    });
  });
}

/* ---------------- 会话列表 ---------------- */

async function requestJson(url, options) {
  const response = await fetch(url, options);

  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    payload = null;
  }

  if (!response.ok) {
    const message = payload && payload.error ? payload.error : `请求失败（${response.status}）`;
    throw new Error(message);
  }

  return payload ? payload.data : null;
}

async function loadSessions() {
  try {
    const sessions = await requestJson("/api/sessions");
    state.sessions = sessions || [];
    renderSessions();
    setConnection(true);
  } catch (error) {
    setConnection(false);
  }
}

function renderSessions() {
  els.sessionList.innerHTML = "";

  if (!state.sessions.length) {
    const hint = el("div", "session-item-meta");
    hint.style.padding = "8px 10px";
    hint.textContent = "还没有历史会话";
    els.sessionList.appendChild(hint);
    return;
  }

  for (const session of state.sessions) {
    const item = el(
      "button",
      "session-item" + (session.session_id === state.sessionId ? " active" : "")
    );
    item.type = "button";

    const main = el("div", "session-item-main");
    const title = el("div", "session-item-title");
    title.textContent = session.title || "新会话";
    title.title = session.title || "";

    const meta = el("div", "session-item-meta");
    meta.textContent = `${session.message_count} 条消息 · ${formatTime(session.updated_at)}`;

    main.append(title, meta);

    const remove = el("button", "session-delete");
    remove.type = "button";
    remove.textContent = "×";
    remove.title = "删除会话";
    remove.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteSession(session.session_id);
    });

    item.append(main, remove);
    item.addEventListener("click", () => openSession(session.session_id));

    els.sessionList.appendChild(item);
  }
}

function formatTime(value) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  const sameDay = date.toDateString() === now.toDateString();

  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  if (sameDay) return `${hours}:${minutes}`;

  return `${date.getMonth() + 1}/${date.getDate()}`;
}

async function openSession(sessionId) {
  if (state.sending) return;

  try {
    const data = await requestJson(`/api/sessions/${sessionId}`);

    state.sessionId = sessionId;
    els.title.textContent = titleOf(data) || "会话";
    setStatus("就绪");

    renderHistory(data.messages || []);
    renderSessions();
    setConnection(true);
  } catch (error) {
    setStatus(error.message);
  }
}

function titleOf(data) {
  const first = (data.messages || []).find((item) => item.role === "user");
  return first ? first.content.slice(0, 40) : "新会话";
}

function renderHistory(messages) {
  els.messages.innerHTML = "";

  if (!messages.length) {
    showEmptyState();
    return;
  }

  for (const message of messages) {
    if (message.role === "user") {
      appendUserMessage(message.content);
    } else {
      const view = createAssistantMessage();
      view.content.innerHTML = renderMarkdown(message.content);
      view.bubble.classList.remove("streaming");
    }
  }

  scrollToBottom(true);
}

async function deleteSession(sessionId) {
  if (!window.confirm("删除这个会话？")) return;

  try {
    await requestJson(`/api/sessions/${sessionId}`, { method: "DELETE" });

    if (state.sessionId === sessionId) {
      startNewSession();
    }

    await loadSessions();
  } catch (error) {
    setStatus(error.message);
  }
}

function startNewSession() {
  state.sessionId = null;
  els.title.textContent = "新会话";
  setStatus("就绪");
  els.messages.innerHTML = "";
  showEmptyState();
  renderSessions();
  els.input.focus();
}

/* ---------------- 消息渲染 ---------------- */

function appendUserMessage(text) {
  hideEmptyState();

  const message = el("div", "message user");

  const avatar = el("div", "avatar");
  avatar.textContent = "我";

  const wrap = el("div", "bubble-wrap");
  const bubble = el("div", "bubble");
  bubble.textContent = text;

  wrap.appendChild(bubble);
  message.append(avatar, wrap);
  els.messages.appendChild(message);

  scrollToBottom();
}

function createAssistantMessage() {
  hideEmptyState();

  const message = el("div", "message assistant");

  const avatar = el("div", "avatar");
  avatar.textContent = "✦";

  const wrap = el("div", "bubble-wrap");

  const trace = el("details", "trace");
  trace.open = true;
  trace.style.display = "none";

  const summary = el("summary", "");
  const traceLabel = el("span", "");
  traceLabel.textContent = "执行过程";
  summary.append(traceLabel);

  const traceBody = el("div", "trace-body");
  trace.append(summary, traceBody);

  const bubble = el("div", "bubble streaming");
  bubble.innerHTML = '<p class="pending">正在思考…</p>';

  wrap.append(trace, bubble);
  message.append(avatar, wrap);
  els.messages.appendChild(message);

  return {
    message,
    wrap,
    trace,
    traceLabel,
    traceBody,
    bubble,
    content: bubble,
    text: "",
    toolRows: {},
    stepCount: 0,
    hasContent: false,
  };
}

function addTraceItem(view, className, icon, name, detail) {
  view.trace.style.display = "";

  const row = el("div", `trace-item ${className}`);
  row.innerHTML = `
    <span class="icon">${escapeHtml(icon)}</span>
    <span class="name">${escapeHtml(name)}</span>
    <span class="args"></span>
    <span class="meta"></span>
  `;

  if (detail) {
    const args = row.querySelector(".args");
    args.textContent = detail;
    args.title = detail;
  }

  view.traceBody.appendChild(row);
  return row;
}

function addToolStart(view, data) {
  const row = addTraceItem(
    view,
    "running",
    "◌",
    data.tool || "tool",
    data.arguments || ""
  );

  row.querySelector(".meta").textContent = "调用中";

  if (!view.toolRows[data.tool]) {
    view.toolRows[data.tool] = [];
  }

  view.toolRows[data.tool].push(row);
}

function addToolEnd(view, data) {
  const queue = view.toolRows[data.tool] || [];
  const row = queue.shift();

  if (!row) return;

  const failed = data.success === false;

  row.classList.remove("running");
  row.classList.add(failed ? "fail" : "ok");

  row.querySelector(".icon").textContent = failed ? "✕" : "✓";

  const parts = [];
  if (data.summary) parts.push(data.summary);
  if (typeof data.duration_ms === "number") parts.push(`${data.duration_ms} ms`);

  row.querySelector(".meta").textContent = parts.join(" · ");
}

function setBubbleText(view, text) {
  view.text = text;

  const atBottom = isNearBottom();

  view.bubble.innerHTML = renderMarkdown(text) + '<span class="cursor"></span>';

  if (atBottom) scrollToBottom(true);
}

function finishBubble(view, finalText) {
  const text = finalText != null ? finalText : view.text;

  view.bubble.classList.remove("streaming");
  view.bubble.innerHTML = text
    ? renderMarkdown(text)
    : '<p class="pending">没有返回内容。</p>';

  scrollToBottom();
}

/* ---------------- SSE ---------------- */

function createSseParser(handle) {
  let buffer = "";

  return {
    push(chunk) {
      buffer += chunk.replace(/\r\n/g, "\n");

      let index;
      while ((index = buffer.indexOf("\n\n")) !== -1) {
        const block = buffer.slice(0, index);
        buffer = buffer.slice(index + 2);

        if (block.trim()) {
          parseBlock(block, handle);
        }
      }
    },
    flush() {
      if (buffer.trim()) {
        parseBlock(buffer, handle);
        buffer = "";
      }
    },
  };
}

function parseBlock(block, handle) {
  let eventName = "message";
  const dataLines = [];

  for (const line of block.split("\n")) {
    if (line.startsWith(":")) continue;

    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }

  if (!dataLines.length) return;

  let data = {};
  try {
    data = JSON.parse(dataLines.join("\n"));
  } catch (error) {
    data = { text: dataLines.join("\n") };
  }

  handle(eventName, data);
}

/* ---------------- 发送对话 ---------------- */

async function sendMessage(text) {
  if (state.sending || !text.trim()) return;

  state.sending = true;
  updateSendState();
  setStatus("处理中…", true);

  appendUserMessage(text);
  els.input.value = "";
  autoResize();

  const view = createAssistantMessage();
  scrollToBottom(true);

  let finalAnswer = null;
  let finished = false;
  let streamError = null;

  const handle = (name, data) => {
    switch (name) {
      case "session":
        if (data.session_id) {
          if (!state.sessionId) {
            els.title.textContent = text.slice(0, 40);
          }
          state.sessionId = data.session_id;
        }
        break;

      case "stage":
        view.stepCount += 1;
        setStatus(data.label || "处理中…", true);
        addTraceItem(view, "stage", "·", data.label || data.stage || "阶段", "");
        break;

      case "rewritten":
        addTraceItem(
          view,
          "stage",
          "↻",
          "理解问题",
          data.resolved || ""
        );
        break;

      case "classified":
        addTraceItem(
          view,
          "stage",
          "◇",
          "任务类型",
          `${data.task_type || ""}${data.reason ? " · " + data.reason : ""}`
        );
        break;

      case "tool":
        if (data.status === "start") {
          addToolStart(view, data);
        } else {
          addToolEnd(view, data);
        }
        scrollToBottom();
        break;

      case "subtask_done":
        addTraceItem(
          view,
          data.success ? "ok" : "fail",
          data.success ? "✓" : "✕",
          data.task || "子任务",
          data.summary || ""
        );
        scrollToBottom();
        break;

      case "delta":
        if (!view.hasContent) {
          view.hasContent = true;
          view.text = "";
        }
        setBubbleText(view, view.text + (data.text || ""));
        break;

      case "done":
        finalAnswer = data.answer != null ? data.answer : null;
        finished = true;

        if (!data.success) {
          setStatus("部分任务失败");
        } else {
          setStatus("就绪");
        }
        break;

      case "error":
        streamError = data.message || "执行失败";
        break;

      default:
        break;
    }
  };

  const parser = createSseParser(handle);

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId,
        message: text,
      }),
    });

    if (!response.ok || !response.body) {
      let message = `请求失败（${response.status}）`;
      try {
        const payload = await response.json();
        if (payload && payload.error) message = payload.error;
      } catch (error) {
        /* ignore */
      }
      throw new Error(message);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");

    while (true) {
      const { value, done } = await reader.read();

      if (done) break;

      parser.push(decoder.decode(value, { stream: true }));
    }

    parser.flush();
  } catch (error) {
    streamError = error.message || String(error);
  } finally {
    if (streamError && !finished) {
      const partial = view.text ? renderMarkdown(view.text) : "";

      view.bubble.classList.remove("streaming");
      view.bubble.innerHTML =
        partial +
        `<p class="pending">出错了：${escapeHtml(streamError)}</p>`;

      addTraceItem(view, "fail", "✕", "错误", streamError);

      setStatus("出错");
    } else {
      finishBubble(view, finalAnswer);
    }

    state.sending = false;
    updateSendState();

    loadSessions();
  }
}

/* ---------------- 输入框 ---------------- */

function autoResize() {
  els.input.style.height = "auto";
  els.input.style.height = `${Math.min(els.input.scrollHeight, 180)}px`;
}

function updateSendState() {
  els.send.disabled = state.sending || !els.input.value.trim();
}

function setConnection(online) {
  els.connDot.classList.toggle("online", online);
  els.connDot.classList.toggle("offline", !online);
  els.connText.textContent = online ? "服务已连接" : "服务未连接";
}

/* ---------------- 初始化 ---------------- */

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();

  const text = els.input.value.trim();

  if (!text) return;

  sendMessage(text);
});

els.input.addEventListener("input", () => {
  autoResize();
  updateSendState();
});

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    els.composer.requestSubmit();
  }
});

els.newSession.addEventListener("click", () => {
  if (state.sending) return;
  startNewSession();
});

bindSuggestions(document);
autoResize();
updateSendState();
loadSessions();

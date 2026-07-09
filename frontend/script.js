// ============================================================================
// CONFIG — locked to the exact schemas in app/models.py
// ============================================================================
// ChatRequest  = { messages: [{role, content}] }
// ChatResponse = { reply: str, recommendations: [{name, url, test_type}], end_of_conversation: bool }
const CONFIG = {
  // Default backend URL. Overridden at runtime by the "Endpoint" panel,
  // which saves to localStorage so you don't have to edit this file per-deploy.
  // DEFAULT_API_BASE: "http://localhost:8000",
  DEFAULT_API_BASE = "/api",

  // Maps a Recommendation.test_type letter code (from the catalog) to a
  // human-readable label shown on each rec card. SHL's public test_type
  // keys: A, B, C, D, E, K, P, S. Unknown codes fall back to the raw letter.
  TEST_TYPE_LABELS: {
    A: "Ability",
    B: "Biodata",
    C: "Competencies",
    D: "Development",
    E: "Assessment Exercise",
    K: "Knowledge",
    P: "Personality",
    S: "Simulation",
  },

  // Keys must match the --tt-* custom properties defined in style.css.
  TEST_TYPE_COLOR_VARS: {
    A: "--tt-a",
    B: "--tt-b",
    C: "--tt-c",
    D: "--tt-d",
    E: "--tt-e",
    K: "--tt-k",
    P: "--tt-p",
    S: "--tt-s",
  },
};

// ============================================================================
// State
// ============================================================================
let apiBase = localStorage.getItem("shl_api_base") || CONFIG.DEFAULT_API_BASE;
// Only ever read from/written to this browser's localStorage — never
// hardcoded here. Stays empty if the backend has AUTH_ENABLED=false
// (the default), so nothing changes for anyone who hasn't set up auth.
let apiKey = localStorage.getItem("shl_api_key") || "";
let history = []; // [{role: "user"|"assistant", content: "..."}]

const els = {
  chatLog: document.getElementById("chatLog"),
  form: document.getElementById("composerForm"),
  input: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  statusDot: document.getElementById("statusDot"),
  statusLabel: document.getElementById("statusLabel"),
  configToggle: document.getElementById("configToggle"),
  configPanel: document.getElementById("configPanel"),
  configSave: document.getElementById("configSave"),
  apiBaseInput: document.getElementById("apiBaseInput"),
  apiKeyInput: document.getElementById("apiKeyInput"),
  quickRow: document.getElementById("quickRow"),
};

els.apiBaseInput.value = apiBase;
els.apiKeyInput.value = apiKey;

// Shared by every fetch() call to the backend. Only adds the header at
// all if a key has actually been configured, so requests to a backend
// with AUTH_ENABLED=false are completely unaffected.
function authHeaders() {
  return apiKey ? { "X-API-Key": apiKey } : {};
}

// ============================================================================
// Health check
// ============================================================================
async function checkHealth() {
  els.statusDot.className = "status-dot";
  els.statusLabel.textContent = "checking";
  try {
    const res = await fetch(`${apiBase.replace(/\/$/, "")}/health`, {
      method: "GET",
      headers: authHeaders(),
    });
    if (res.status === 401) {
      els.statusDot.classList.add("down");
      els.statusLabel.textContent = "needs key";
    } else if (res.ok) {
      els.statusDot.classList.add("ok");
      els.statusLabel.textContent = "online";
    } else {
      throw new Error("bad status");
    }
  } catch (e) {
    els.statusDot.classList.add("down");
    els.statusLabel.textContent = "offline";
  }
}

// ============================================================================
// Config panel
// ============================================================================
els.configToggle.addEventListener("click", () => {
  els.configPanel.hidden = !els.configPanel.hidden;
});
els.configSave.addEventListener("click", () => {
  const val = els.apiBaseInput.value.trim();
  if (!val) return;
  apiBase = val;
  localStorage.setItem("shl_api_base", apiBase);

  apiKey = els.apiKeyInput.value.trim();
  if (apiKey) {
    localStorage.setItem("shl_api_key", apiKey);
  } else {
    localStorage.removeItem("shl_api_key");
  }

  checkHealth();
});

// ============================================================================
// Quick-start chips
// ============================================================================
els.quickRow.addEventListener("click", (e) => {
  const btn = e.target.closest(".quick-chip");
  if (!btn) return;
  els.input.value = btn.dataset.fill;
  autoGrow();
  els.input.focus();
});

// ============================================================================
// Textarea auto-grow + enter-to-send
// ============================================================================
function autoGrow() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 140) + "px";
}
els.input.addEventListener("input", autoGrow);
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    els.form.requestSubmit();
  }
});

// ============================================================================
// Rendering helpers
// ============================================================================
function scrollToBottom() {
  els.chatLog.scrollTop = els.chatLog.scrollHeight;
}

function appendUserMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-user";
  wrap.innerHTML = `<div class="msg-bubble"></div>`;
  wrap.querySelector(".msg-bubble").textContent = text;
  els.chatLog.appendChild(wrap);
  scrollToBottom();
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderRecommendationsHtml(recommendations) {
  if (!Array.isArray(recommendations) || recommendations.length === 0) return "";
  const cards = recommendations.map((rec) => {
    const name = rec.name || "Untitled assessment";
    const url = rec.url || "";
    const code = (rec.test_type || "").charAt(0).toUpperCase();
    const typeLabel = CONFIG.TEST_TYPE_LABELS[code] || rec.test_type || "";
    const colorVar = CONFIG.TEST_TYPE_COLOR_VARS[code];
    const style = colorVar ? ` style="--rec-color: var(${colorVar})"` : "";
    const nameHtml = url
      ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(name)}</a>`
      : escapeHtml(name);
    return `
      <div class="rec-card"${style}>
        <div class="rec-card-top">
          <span class="rec-name">${nameHtml}</span>
          ${typeLabel ? `<span class="rec-type">${escapeHtml(typeLabel)}</span>` : ""}
        </div>
      </div>`;
  }).join("");
  return `<div class="rec-list">${cards}</div>`;
}

// Renders LLM reply text as markdown -> HTML. Falls back to plain
// escaped text if marked/DOMPurify somehow failed to load (e.g. CDN
// blocked in a locked-down network) so a reply is never silently
// dropped just because formatting isn't available.
function renderReplyHtml(reply) {
  const text = reply || "(empty reply)";
  if (typeof marked === "undefined" || typeof DOMPurify === "undefined") {
    return escapeHtml(text);
  }
  const rawHtml = marked.parse(text);
  return DOMPurify.sanitize(rawHtml);
}

function appendAssistantMessage({ reply, recommendations, end_of_conversation }) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-assistant";
  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";
  bubble.innerHTML = `<div class="msg-text markdown-body"></div>${renderRecommendationsHtml(recommendations)}`;
  bubble.querySelector(".msg-text").innerHTML = renderReplyHtml(reply);
  wrap.appendChild(bubble);
  els.chatLog.appendChild(wrap);
  scrollToBottom();

  if (end_of_conversation) {
    showConversationEnded();
  }
}

// Resets the client-side conversation without a full page reload. Since
// the backend is stateless (the whole `history` array is sent fresh on
// every call), "starting over" is just clearing that array — no reason
// to make the user reload the page to get there.
function startNewConversation() {
  history = [];
  els.chatLog.innerHTML = `
    <div class="msg msg-system">
      <div class="msg-bubble">
        <p>Tell me who you're hiring for &mdash; role, level, and any must-have skills or constraints (language, remote/on-site, seniority). I'll ask if I need one more detail, then shortlist real SHL assessments. You can also say things like "compare X and Y" or "remove the second one, add a coding test."</p>
      </div>
    </div>`;
  els.input.disabled = false;
  els.sendBtn.disabled = false;
  els.input.placeholder = "Describe the role, or ask to compare / refine…";
  els.input.focus();
}

function showConversationEnded() {
  const endWrap = document.createElement("div");
  endWrap.className = "msg msg-system";
  endWrap.innerHTML = `
    <div class="msg-bubble">
      <p>This conversation has ended.</p>
      <button type="button" class="primary-btn" id="newConvoBtn" style="margin-top: 8px;">Start new conversation</button>
    </div>`;
  els.chatLog.appendChild(endWrap);
  scrollToBottom();
  document.getElementById("newConvoBtn").addEventListener("click", startNewConversation);
  els.input.disabled = true;
  els.sendBtn.disabled = true;
  els.input.placeholder = "Conversation ended — click above to start a new one";
}

function appendErrorMessage(text) {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-assistant msg-error";
  wrap.innerHTML = `<div class="msg-bubble"></div>`;
  wrap.querySelector(".msg-bubble").textContent = text;
  els.chatLog.appendChild(wrap);
  scrollToBottom();
}

function showTyping() {
  const wrap = document.createElement("div");
  wrap.className = "msg msg-assistant typing-bubble";
  wrap.id = "typingIndicator";
  wrap.innerHTML = `<div class="msg-bubble"><span class="typing-dot"></span><span class="typing-dot"></span><span class="typing-dot"></span></div>`;
  els.chatLog.appendChild(wrap);
  scrollToBottom();
}
function hideTyping() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

// ============================================================================
// Response parsing — expects exactly the ChatResponse schema from models.py
// ============================================================================
function parseResponse(data) {
  if (typeof data !== "object" || data === null) {
    // Backend returned something that isn't valid JSON per the schema.
    return { reply: String(data), recommendations: [], end_of_conversation: false };
  }
  return {
    reply: typeof data.reply === "string" ? data.reply : "(malformed response: missing 'reply')",
    recommendations: Array.isArray(data.recommendations) ? data.recommendations : [],
    end_of_conversation: Boolean(data.end_of_conversation),
  };
}

// ============================================================================
// Send message
// ============================================================================
async function sendMessage(userText) {
  appendUserMessage(userText);
  history.push({ role: "user", content: userText });
  showTyping();
  els.sendBtn.disabled = true;

  // Send the full conversation so far (stateless backend, per your approach doc).
  // ChatRequest = { messages: [{role, content}] }
  const payload = { messages: history };

  try {
    const res = await fetch(`${apiBase.replace(/\/$/, "")}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(payload),
    });

    if (res.status === 401) {
      throw new Error(
        "This backend requires an API key. Open the Endpoint panel and enter it."
      );
    }

    if (!res.ok) {
      const bodyText = await res.text().catch(() => "");
      throw new Error(`Server responded ${res.status}${bodyText ? `: ${bodyText.slice(0, 200)}` : ""}`);
    }

    const data = await res.json().catch(async () => await res.text());
    hideTyping();
    const parsed = parseResponse(data);
    appendAssistantMessage(parsed);
    history.push({ role: "assistant", content: parsed.reply || "" });
  } catch (err) {
    hideTyping();
    appendErrorMessage(
      `Couldn't reach the backend at ${apiBase}. ${err.message || err}. ` +
      `Check the Endpoint panel and confirm CORS is enabled on the server.`
    );
  } finally {
    els.sendBtn.disabled = false;
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = els.input.value.trim();
  if (!text) return;
  els.input.value = "";
  autoGrow();
  sendMessage(text);
});

// ============================================================================
// Init
// ============================================================================
checkHealth();


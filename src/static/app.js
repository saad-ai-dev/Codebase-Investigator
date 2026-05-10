const state = {
  session: null,
  busy: false,
};

const elements = {
  sessionForm: document.getElementById("session-form"),
  repoUrl: document.getElementById("repo-url"),
  startSessionButton: document.getElementById("start-session-button"),
  sessionFeedback: document.getElementById("session-feedback"),
  sessionOverview: document.getElementById("session-overview"),
  questionForm: document.getElementById("question-form"),
  questionInput: document.getElementById("question-input"),
  askButton: document.getElementById("ask-button"),
  conversationFeed: document.getElementById("conversation-feed"),
  busyPill: document.getElementById("busy-pill"),
  sampleQuestions: document.querySelectorAll(".sample-question"),
};

function boot() {
  elements.sessionForm.addEventListener("submit", handleCreateSession);
  elements.questionForm.addEventListener("submit", handleAskQuestion);
  elements.questionInput.addEventListener("keydown", handleComposerKeydown);

  elements.sampleQuestions.forEach((button) => {
    button.addEventListener("click", () => {
      elements.questionInput.value = button.dataset.question || "";
      elements.questionInput.focus();
    });
  });

  const initialSessionId = window.location.hash.replace(/^#/, "");
  if (initialSessionId) {
    loadSession(initialSessionId);
  }
}

async function loadSession(sessionId) {
  setBusy(true, "Loading");
  clearFeedback();
  try {
    const response = await fetch(`/api/session/${encodeURIComponent(sessionId)}`);
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not load session.");
    }
    state.session = payload;
    elements.repoUrl.value = payload.repo.url;
    render();
    setFeedback(`Loaded ${payload.repo.owner}/${payload.repo.repo}.`, "success");
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function handleCreateSession(event) {
  event.preventDefault();
  const target = elements.repoUrl.value.trim();
  if (!target) {
    setFeedback("Paste a public GitHub repository URL first.", "error");
    return;
  }

  setBusy(true, "Opening");
  clearFeedback();
  try {
    const response = await fetch("/api/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "Could not open repository.");
    }
    state.session = payload;
    window.location.hash = payload.session_id;
    render();
    setFeedback(`Ready: ${payload.repo.owner}/${payload.repo.repo}`, "success");
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    setBusy(false);
  }
}

async function handleAskQuestion(event) {
  event.preventDefault();
  if (!state.session) {
    setFeedback("Open a repository first.", "error");
    return;
  }

  const question = elements.questionInput.value.trim();
  if (!question) {
    setFeedback("Ask a concrete question first.", "error");
    return;
  }

  setBusy(true, "Investigating");
  clearFeedback();
  try {
    const response = await fetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.session.session_id,
        question,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || "The investigator could not answer that question.");
    }
    state.session.turn_count = payload.session.turn_count;
    state.session.turns = [...state.session.turns, payload.turn];
    elements.questionInput.value = "";
    render();
    scrollConversationToBottom();
  } catch (error) {
    setFeedback(error.message, "error");
  } finally {
    setBusy(false);
  }
}

function handleComposerKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    if (!elements.askButton.disabled) {
      elements.questionForm.requestSubmit();
    }
  }
}

function render() {
  renderSessionOverview();
  renderConversation();
  elements.questionInput.disabled = !state.session || state.busy;
  elements.askButton.disabled = !state.session || state.busy;
  elements.startSessionButton.disabled = state.busy;
}

function renderSessionOverview() {
  if (!state.session) {
    elements.sessionOverview.className = "session-overview empty-state";
    elements.sessionOverview.textContent = "Paste a repository URL to start the investigation.";
    return;
  }

  const repo = state.session.repo;
  const repoLabel = `${repo.owner}/${repo.repo}`;
  const branch = repo.ref ? `Ref: ${escapeHtml(repo.ref)}` : "Default branch";
  const subpath = repo.subpath ? repo.subpath : "Whole repository";

  elements.sessionOverview.className = "session-overview";
  elements.sessionOverview.innerHTML = `
    <div class="session-summary-grid">
      <div class="summary-topline">
        <div class="summary-title">
          <p class="eyebrow">Current Repository</p>
          <h2>${escapeHtml(repoLabel)}</h2>
        </div>
        <span class="pill neutral">${state.session.turn_count} turn${state.session.turn_count === 1 ? "" : "s"}</span>
      </div>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="eyebrow">Source</span>
          <div class="meta-copy">${escapeHtml(repo.url)}</div>
        </div>
        <div class="summary-item">
          <span class="eyebrow">Scope</span>
          <div class="meta-copy">${escapeHtml(branch)} · ${escapeHtml(subpath)}</div>
        </div>
        <div class="summary-item">
          <span class="eyebrow">Session ID</span>
          <div class="meta-code">${escapeHtml(state.session.session_id)}</div>
        </div>
      </div>
    </div>
  `;
}

function renderConversation() {
  if (!state.session || !state.session.turns.length) {
    elements.conversationFeed.className = "conversation-feed empty-state";
    elements.conversationFeed.textContent =
      "Open a repository, then ask a question. Each answer will include the result, verification status, and attached evidence.";
    return;
  }

  elements.conversationFeed.className = "conversation-feed";
  elements.conversationFeed.innerHTML = state.session.turns.map(renderTurnCard).join("");
}

function renderTurnCard(turn) {
  const openQuestions = renderOpenQuestions(turn.answer.open_questions);
  const snippetCount = turn.snippets.length;
  const claimCount = turn.answer.claims.length;

  return `
    <article class="turn-card" id="turn-${turn.turn_number}">
      <div class="turn-topline">
        <div>
          <div class="turn-label">Turn ${turn.turn_number}</div>
          <div class="turn-meta">${formatTimestamp(turn.timestamp)}</div>
        </div>
        <div class="status-row">
          <span class="pill ${turn.verifier.verdict}">${formatVerdictLabel(turn.verifier.verdict)} verifier</span>
          <span class="pill ${turn.audit.verdict}">${formatVerdictLabel(turn.audit.verdict)} audit</span>
        </div>
      </div>

      <section class="question-block">
        <div class="block-label">Question</div>
        <p class="question-text">${escapeHtml(turn.question)}</p>
      </section>

      <section class="answer-block">
        <div class="block-label">Answer</div>
        <div class="message-answer">${renderTextBlocks(turn.rendered_answer)}</div>
      </section>

      ${openQuestions}

      <details class="detail-block">
        <summary>
          <div class="detail-header">
            <span class="detail-summary">Audit and evidence</span>
            <span class="meta-code">${snippetCount} snippet${snippetCount === 1 ? "" : "s"} · ${claimCount} claim${claimCount === 1 ? "" : "s"}</span>
          </div>
        </summary>
        <div class="detail-content">
          <section class="detail-section">
            <div class="detail-section-head">
              <h4>Verifier</h4>
              <span class="pill ${turn.verifier.verdict}">${formatVerdictLabel(turn.verifier.verdict)}</span>
            </div>
            <div class="detail-text">${renderIssueList(turn.verifier.issues, "No programmatic issues were detected.")}</div>
          </section>

          <section class="detail-section">
            <div class="detail-section-head">
              <h4>Independent audit</h4>
              <span class="pill ${turn.audit.verdict}">${formatVerdictLabel(turn.audit.verdict)}</span>
            </div>
            <div class="detail-text">
              <div>${escapeHtml(turn.audit.summary)}</div>
              ${renderFindingList(turn.audit.findings, turn.audit.missing_checks)}
            </div>
          </section>

          <section class="detail-section">
            <div class="detail-section-head">
              <h4>Claims</h4>
            </div>
            ${renderClaimList(turn.answer.claims)}
          </section>

          <section class="detail-section">
            <div class="detail-section-head">
              <h4>Evidence snippets</h4>
            </div>
            ${renderSnippets(turn.snippets)}
          </section>
        </div>
      </details>
    </article>
  `;
}

function renderOpenQuestions(openQuestions) {
  if (!openQuestions || !openQuestions.length) {
    return "";
  }
  return `
    <section class="detail-section">
      <div class="detail-section-head">
        <h4>Open questions</h4>
      </div>
      <div class="open-question-list">
        ${openQuestions.map((question) => `<div class="open-question-item">${escapeHtml(question)}</div>`).join("")}
      </div>
    </section>
  `;
}

function renderIssueList(issues, emptyText) {
  if (!issues || !issues.length) {
    return `<div>${escapeHtml(emptyText)}</div>`;
  }
  return `
    <div class="issue-list">
      ${issues
        .map(
          (issue) => `
        <div class="issue-item">
          <div class="detail-section-head">
            <strong class="severity-${escapeHtml(issue.severity)}">${escapeHtml(issue.severity)}</strong>
            ${issue.claim_id ? `<span class="meta-code">${escapeHtml(issue.claim_id)}</span>` : ""}
          </div>
          <div>${escapeHtml(issue.message)}</div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

function renderFindingList(findings, missingChecks) {
  const findingHtml =
    findings && findings.length
      ? `
        <div class="finding-list">
          ${findings
            .map(
              (finding) => `
            <div class="finding-item">
              <div class="detail-section-head">
                <strong class="severity-${escapeHtml(finding.severity)}">${escapeHtml(finding.title)}</strong>
                <span class="meta-code">${escapeHtml(finding.severity)}</span>
              </div>
              <div>${escapeHtml(finding.detail)}</div>
            </div>
          `
            )
            .join("")}
        </div>
      `
      : "<div>No reviewer findings.</div>";

  const missingHtml =
    missingChecks && missingChecks.length
      ? `
        <div class="open-question-list">
          ${missingChecks.map((item) => `<div class="open-question-item">${escapeHtml(item)}</div>`).join("")}
        </div>
      `
      : "";

  return `${findingHtml}${missingHtml}`;
}

function renderClaimList(claims) {
  if (!claims || !claims.length) {
    return "<div>No structured claims recorded.</div>";
  }
  return `
    <div class="claim-list">
      ${claims
        .map(
          (claim) => `
        <div class="claim-item">
          <div class="detail-section-head">
            <strong>${escapeHtml(claim.claim_id)}</strong>
            <span class="meta-code">${escapeHtml(claim.kind)}</span>
          </div>
          <div>${escapeHtml(claim.statement)}</div>
          <div class="turn-meta">
            ${claim.snippet_ids.length ? `Snippets: ${escapeHtml(claim.snippet_ids.join(", "))}` : "No supporting snippets recorded."}
          </div>
        </div>
      `
        )
        .join("")}
    </div>
  `;
}

function renderSnippets(snippets) {
  if (!snippets || !snippets.length) {
    return "<div>No snippets captured for this turn.</div>";
  }
  return `
    <div class="snippet-list">
      ${snippets
        .map(
          (snippet) => `
        <article class="snippet-item">
          <div class="detail-section-head">
            <strong>${escapeHtml(snippet.snippet_id)}</strong>
            <span class="meta-code">${escapeHtml(snippet.label)}</span>
          </div>
          <div class="turn-meta">${escapeHtml(snippet.reason)}</div>
          <pre>${escapeHtml(snippet.text)}</pre>
        </article>
      `
        )
        .join("")}
    </div>
  `;
}

function renderTextBlocks(text) {
  const lines = text.split(/\n/);
  const parts = [];
  let paragraph = [];
  let listItems = [];

  function flushParagraph() {
    if (paragraph.length) {
      parts.push(`<p>${escapeHtml(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  }

  function flushList() {
    if (listItems.length) {
      parts.push(`<ul>${listItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`);
      listItems = [];
    }
  }

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }
    if (trimmed.startsWith("- ")) {
      flushParagraph();
      listItems.push(trimmed.slice(2));
      return;
    }
    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();
  return parts.join("");
}

function scrollConversationToBottom() {
  elements.conversationFeed.scrollTop = elements.conversationFeed.scrollHeight;
}

function setBusy(isBusy, label = "Working") {
  state.busy = isBusy;
  elements.busyPill.classList.toggle("hidden", !isBusy);
  elements.busyPill.className = isBusy ? "pill neutral" : "pill hidden";
  elements.busyPill.textContent = label;
  render();
}

function setFeedback(message, kind) {
  elements.sessionFeedback.textContent = message;
  elements.sessionFeedback.className = `feedback ${kind}`;
}

function clearFeedback() {
  elements.sessionFeedback.textContent = "";
  elements.sessionFeedback.className = "feedback";
}

function formatVerdictLabel(verdict) {
  return verdict.toUpperCase();
}

function formatTimestamp(timestamp) {
  try {
    return new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(timestamp));
  } catch {
    return timestamp;
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

boot();

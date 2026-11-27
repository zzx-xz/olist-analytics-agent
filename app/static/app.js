const conversation = document.querySelector("#conversation");
const form = document.querySelector("#question-form");
const input = document.querySelector("#question");
const sendButton = document.querySelector("#send");
const notice = document.querySelector("#notice");
const suggestions = document.querySelectorAll(".suggestions button");
let sessionId = localStorage.getItem("olist-agent-session");

function escapeHtml(value) {
  return value.replace(/[&<>"']/g, function (character) {
    return {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[character];
  });
}

function renderInlineMarkdown(value) {
  return value.split(/(`[^`]*`)/g).map(function (part) {
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      return "<code>" + escapeHtml(part.slice(1, -1)) + "</code>";
    }
    return escapeHtml(part)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\n/g, "<br>");
  }).join("");
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map(function (cell) {
    return cell.trim();
  });
}

function isTableSeparator(line) {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every(function (cell) {
    return /^:?-{3,}:?$/.test(cell);
  });
}

function renderMarkdown(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let index = 0;
  let listType = null;

  function closeList() {
    if (listType) {
      blocks.push("</" + listType + ">");
      listType = null;
    }
  }

  function isBlockStart(line, nextLine) {
    return !line.trim()
      || /^\s*#{1,3}\s/.test(line)
      || /^\s*```/.test(line)
      || /^\s*[-*]\s+/.test(line)
      || /^\s*\d+\.\s+/.test(line)
      || /^\s*\|/.test(line) && nextLine !== undefined && isTableSeparator(nextLine)
      || /^\s*-{3,}\s*$/.test(line);
  }

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      closeList();
      index += 1;
      continue;
    }

    if (/^\s*```/.test(line)) {
      closeList();
      index += 1;
      const codeLines = [];
      while (index < lines.length && !/^\s*```/.test(lines[index])) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push("<pre><code>" + escapeHtml(codeLines.join("\n")) + "</code></pre>");
      continue;
    }

    if (/^\s*\|/.test(line) && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      closeList();
      const headers = splitTableRow(line);
      index += 2;
      const rows = [];
      while (index < lines.length && /^\s*\|/.test(lines[index])) {
        rows.push(splitTableRow(lines[index]));
        index += 1;
      }
      const head = headers.map(function (cell) {
        return "<th>" + renderInlineMarkdown(cell) + "</th>";
      }).join("");
      const body = rows.map(function (row) {
        const cells = headers.map(function (_header, cellIndex) {
          return "<td>" + renderInlineMarkdown(row[cellIndex] || "") + "</td>";
        }).join("");
        return "<tr>" + cells + "</tr>";
      }).join("");
      blocks.push("<div class=\"table-wrap\"><table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table></div>");
      continue;
    }

    const heading = line.match(/^\s*(#{1,3})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      blocks.push("<h" + level + ">" + renderInlineMarkdown(heading[2]) + "</h" + level + ">");
      index += 1;
      continue;
    }

    const unordered = line.match(/^\s*[-*]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+\.\s+(.+)$/);
    if (unordered || ordered) {
      const nextType = unordered ? "ul" : "ol";
      if (listType !== nextType) {
        closeList();
        listType = nextType;
        blocks.push("<" + listType + ">");
      }
      blocks.push("<li>" + renderInlineMarkdown((unordered || ordered)[1]) + "</li>");
      index += 1;
      continue;
    }

    if (/^\s*-{3,}\s*$/.test(line)) {
      closeList();
      blocks.push("<hr>");
      index += 1;
      continue;
    }

    closeList();
    const paragraph = [line];
    index += 1;
    while (index < lines.length && !isBlockStart(lines[index], lines[index + 1])) {
      paragraph.push(lines[index]);
      index += 1;
    }
    blocks.push("<p>" + renderInlineMarkdown(paragraph.join("\n")) + "</p>");
  }

  closeList();
  return blocks.join("");
}

function clearEmptyState() {
  const empty = conversation.querySelector(".empty-state");
  if (empty) empty.remove();
}

function addMessage(role, text, trace) {
  clearEmptyState();
  const article = document.createElement("article");
  article.className = "message " + role;
  const badge = document.createElement("div");
  badge.className = "message-badge";
  badge.textContent = role === "user" ? "你" : "AI";
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-label";
  label.textContent = role === "user" ? "你的问题" : "分析结果";
  const content = document.createElement("div");
  content.className = "message-content";
  if (role === "assistant") {
    content.innerHTML = renderMarkdown(text);
  } else {
    content.textContent = text;
  }
  body.append(label, content);

  if (trace && trace.length) {
    const details = document.createElement("details");
    details.className = "evidence";
    const summary = document.createElement("summary");
    summary.textContent = "查看执行过程与 SQL 依据";
    const pre = document.createElement("pre");
    pre.textContent = trace.map(function (step) {
      const result = step.result || {};
      const parts = ["工具：" + step.tool];
      if (step.arguments && step.arguments.sql) parts.push("SQL：\n" + step.arguments.sql);
      if (result.row_count !== undefined) {
        parts.push("返回行数：" + result.row_count + (result.truncated ? "（已截断）" : ""));
      }
      if (step.error) parts.push("错误：" + step.error);
      return parts.join("\n");
    }).join("\n\n");
    details.append(summary, pre);
    body.append(details);
  }

  article.append(badge, body);
  conversation.append(article);
  conversation.scrollTop = conversation.scrollHeight;
}

async function restoreSession() {
  if (!sessionId) return;
  try {
    const response = await fetch("/sessions/" + encodeURIComponent(sessionId));
    if (!response.ok) {
      localStorage.removeItem("olist-agent-session");
      sessionId = null;
      return;
    }
    const data = await response.json();
    (data.messages || []).forEach(function (message) {
      addMessage(message.role, message.content);
    });
  } catch {
    notice.textContent = "暂时无法恢复上次会话；你仍可以开始新对话。";
  }
}

form.addEventListener("submit", async function (event) {
  event.preventDefault();
  const question = input.value.trim();
  if (!question) return;
  addMessage("user", question);
  input.value = "";
  sendButton.disabled = true;
  sendButton.textContent = "分析中…";
  notice.textContent = "正在读取指标口径并查询数据";

  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, session_id: sessionId }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "请求失败");
    sessionId = data.session_id;
    localStorage.setItem("olist-agent-session", sessionId);
    addMessage("assistant", data.answer || "没有生成回答。", data.tool_trace);
    notice.textContent = "回答已生成；展开执行过程可核对 SQL。";
  } catch (error) {
    addMessage("assistant", "暂时无法完成查询：" + error.message);
    notice.textContent = "检查模型配置、服务状态和本地数据库后重试。";
  } finally {
    sendButton.disabled = false;
    sendButton.innerHTML = '发送 <span>↑</span>';
    input.focus();
  }
});

suggestions.forEach(function (button) {
  button.addEventListener("click", function () {
    input.value = button.textContent;
    input.focus();
  });
});

input.addEventListener("keydown", function (event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

restoreSession();

document.querySelectorAll(".pick").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".pick").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    setSelectedTeam(btn.dataset.team);
  });
});

document.getElementById("init-random").addEventListener("click", () => {
  if (!confirm("确认随机生成新任务并重置棋盘？")) return;
  apiPost("/api/init", { mode: "random" }).then(res => {
    if (!res.ok) alert(res.error || "初始化失败");
  });
});

document.getElementById("end-game").addEventListener("click", () => {
  if (!confirm("确认结束游戏并结算？")) return;
  apiPost("/api/end", {});
});

document.getElementById("export-log").addEventListener("click", async () => {
  const button = document.getElementById("export-log");
  button.disabled = true;
  try {
    const r = await fetch("/api/events/export?save=1");
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) throw new Error(j.error || `服务器错误 (${r.status})`);
    alert("日志已保存到:\n" + j.path);
  } catch (e) {
    alert("导出失败: " + e.message);
  } finally {
    button.disabled = false;
  }
});

// ===== Canvas 2D 比赛截图 =====
// 不依赖 DOM 克隆 / html2canvas / 字体加载：直接用状态数据绘制
// 品牌标题 + 比分板 + 三角棋盘，输出完全可控。

const SHOT_CELL_W = 140;
const SHOT_CELL_H = 118;
const SHOT_GAP_X = 8;
const SHOT_GAP_Y = 8;
const SHOT_PAD = 24;

function shotWrapText(ctx, text, maxWidth, fontBase, maxLines) {
  let font = fontBase;
  for (let size = parseFloat(fontBase); size >= 8; size -= 0.5) {
    const f = font.replace(/\d+(\.\d+)?px/, size + "px");
    ctx.font = f;
    const lines = [];
    let cur = "";
    for (const ch of text) {
      if (ctx.measureText(cur + ch).width > maxWidth && cur) {
        lines.push(cur);
        cur = ch;
        if (lines.length >= maxLines) break;
      } else {
        cur += ch;
      }
    }
    if (lines.length < maxLines && cur) lines.push(cur);
    if (lines.length <= maxLines) return { lines, font: f };
  }
  return { lines: [text], font: fontBase };
}

function shotDrawCell(ctx, cell, x, y) {
  const w = SHOT_CELL_W;
  const h = SHOT_CELL_H;
  let bg = "#141414";
  let border = "#333333";
  let textColor = "#f5f5f5";
  let alpha = 1;

  if (cell.is_energy) {
    bg = "#1a1500";
    border = "#b45309";
    textColor = "#fbbf24";
  } else if (cell.owner === "defender") {
    bg = "#0c1a2e";
    border = "#3b82f6";
    textColor = "#60a5fa";
  } else if (cell.owner === "attacker") {
    border = "#ef4444";
    textColor = "#f87171";
    if (cell.activated) bg = "#2a0a0a";
    else {
      bg = "#141414";
      border = "#3a2020";
      textColor = "#8a5050";
      alpha = 0.5;
    }
  }

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = bg;
  ctx.fillRect(x, y, w, h);
  ctx.strokeStyle = border;
  ctx.lineWidth = 2;
  ctx.strokeRect(x + 1, y + 1, w - 2, h - 2);

  if (cell.is_energy) {
    ctx.font = "16px 'Microsoft YaHei', Arial, sans-serif";
    ctx.fillStyle = textColor;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText("能源", x + w / 2, y + h / 2);
    ctx.restore();
    return;
  }

  // 已激活攻击方：左上角金色方块标记
  if (cell.owner === "attacker" && cell.activated) {
    ctx.fillStyle = "#fbbf24";
    ctx.fillRect(x + 4, y + 4, 8, 8);
  }

  // 右上角分数
  ctx.textAlign = "right";
  ctx.textBaseline = "top";
  ctx.font = "bold 15px 'Consolas', monospace";
  ctx.fillStyle = "#fbbf24";
  ctx.fillText(String(cell.total_score), x + w - 8, y + 6);
  if (cell.owner === "attacker" && cell.activated && cell.energy_bonus > 0) {
    ctx.font = "bold 11px 'Consolas', monospace";
    ctx.fillStyle = "#22d3ee";
    ctx.fillText(`(+${cell.energy_bonus})`, x + w - 8, y + 22);
  }

  // 歌名 / 难度 / 任务
  const innerX = x + 10;
  const innerW = w - 20;
  const songText = cell.song_name || cell.difficulty_label || `CHAOS ${cell.diff_score}`;
  const song = shotWrapText(ctx, songText, innerW, "14px 'Microsoft YaHei', Arial, sans-serif", 2);
  ctx.font = song.font;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillStyle = textColor;
  let cursorY = y + 30;
  for (const line of song.lines) {
    ctx.fillText(line, x + w / 2, cursorY);
    cursorY += 16;
  }
  ctx.font = "14px 'Microsoft YaHei', Arial, sans-serif";
  ctx.fillStyle = textColor;
  ctx.fillText(cell.difficulty_label || `CHAOS ${cell.diff_score}`, x + w / 2, cursorY + 6);
  const task = shotWrapText(ctx, cell.task_name || "-", innerW, "bold 11px 'Microsoft YaHei', Arial, sans-serif", 2);
  ctx.font = task.font;
  ctx.fillStyle = "#c9c9c9";
  let taskY = cursorY + 26;
  for (const line of task.lines) {
    ctx.fillText(line, x + w / 2, taskY);
    taskY += 13;
  }
  ctx.restore();
}

function shotFormatTime(elapsed) {
  const e = Math.max(0, elapsed);
  const mm = Math.floor(e);
  const ss = Math.floor((e - mm) * 60);
  return `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
}

async function captureScreenshot() {
  const res = await fetch("/api/state");
  if (!res.ok) throw new Error("获取比赛状态失败");
  const state = await res.json();
  const board = state.board || [];

  const rows = [];
  for (let layer = 1; layer <= 6; layer++) {
    const start = (layer * (layer - 1)) / 2;
    rows.push(board.slice(start, start + layer));
  }
  rows.push(board.slice(21, 27));

  const rowWidth = (n) => n * SHOT_CELL_W + (n - 1) * SHOT_GAP_X;
  const canvasW = rowWidth(6) + SHOT_PAD * 2;
  const brandH = 66;
  const scoreH = 196;
  const boardH = rows.reduce((acc, row) => acc + SHOT_CELL_H + SHOT_GAP_Y, 0) + SHOT_GAP_Y + SHOT_PAD * 2;
  const canvasH = brandH + scoreH + boardH;

  const canvas = document.createElement("canvas");
  canvas.width = canvasW * 2;
  canvas.height = canvasH * 2;
  const ctx = canvas.getContext("2d");
  ctx.scale(2, 2);
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, canvasW, canvasH);

  // 品牌
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.font = "bold 32px 'Microsoft YaHei', Arial, sans-serif";
  ctx.fillStyle = "#f5f5f5";
  ctx.fillText("萌新杯", SHOT_PAD, 26);
  ctx.font = "16px 'Microsoft YaHei', Arial, sans-serif";
  ctx.fillStyle = "#fbbf24";
  ctx.fillText("赛时控制器", SHOT_PAD, 52);

  // 比分板
  const scoreY0 = brandH;
  const scores = state.scores || { defender: 0, attacker: 0 };
  const leftX = SHOT_PAD;
  const rightX = canvasW - SHOT_PAD;
  ctx.font = "14px 'Microsoft YaHei', Arial, sans-serif";
  ctx.fillStyle = "#888888";
  ctx.textAlign = "left";
  ctx.fillText("防守方", leftX, scoreY0 + 24);
  ctx.textAlign = "right";
  ctx.fillText("攻击方", rightX, scoreY0 + 24);
  ctx.font = "bold 66px Arial, sans-serif";
  ctx.textAlign = "left";
  ctx.fillStyle = "#60a5fa";
  ctx.fillText(String(Math.round(scores.defender)), leftX, scoreY0 + 86);
  ctx.textAlign = "right";
  ctx.fillStyle = "#f87171";
  ctx.fillText(String(Math.round(scores.attacker)), rightX, scoreY0 + 86);

  // 计时器
  ctx.textAlign = "center";
  ctx.font = "bold 44px 'Consolas', Arial, monospace";
  ctx.fillStyle = "#fbbf24";
  const timerText = shotFormatTime(state.elapsed || 0);
  ctx.fillText(timerText, canvasW / 2, scoreY0 + 66);
  ctx.font = "13px 'Microsoft YaHei', Arial, sans-serif";
  ctx.fillStyle = "#555555";
  const limit = state.time_limit || 25;
  ctx.fillText(`/ ${shotFormatTime(limit)}`, canvasW / 2, scoreY0 + 96);
  const barW = 220;
  const barH = 4;
  const barX = (canvasW - barW) / 2;
  const barY = scoreY0 + 118;
  ctx.fillStyle = "#1c1c1c";
  ctx.fillRect(barX, barY, barW, barH);
  const pct = Math.min((state.elapsed || 0) / limit, 1);
  ctx.fillStyle = "#fbbf24";
  ctx.fillRect(barX, barY, barW * pct, barH);

  // 棋盘
  let y = scoreY0 + scoreH + SHOT_PAD;
  for (const row of rows) {
    const rw = rowWidth(row.length);
    let x = (canvasW - rw) / 2;
    for (const cell of row) {
      shotDrawCell(ctx, cell, x, y);
      x += SHOT_CELL_W + SHOT_GAP_X;
    }
    y += SHOT_CELL_H + SHOT_GAP_Y;
  }

  const ts = new Date().toISOString().replace(/[-:T.]/g, "").slice(0, 14);
  const dataURL = canvas.toDataURL("image/png");
  const r = await fetch("/api/screenshot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ image: dataURL, filename: `screenshot_${ts}.png` }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok || !j.ok) throw new Error(j.error || `服务器错误 (${r.status})`);
  return j;
}

window.captureScreenshot = captureScreenshot;

document.getElementById("screenshot").addEventListener("click", async () => {
  const button = document.getElementById("screenshot");
  button.disabled = true;
  try {
    const j = await captureScreenshot();
    alert("截图已保存到:\n" + j.path);
  } catch (e) {
    alert("截图失败: " + e.message);
  } finally {
    button.disabled = false;
  }
});



document.getElementById("l1-cancel-btn").addEventListener("click", () => {
  document.getElementById("l1-modal").classList.add("hidden");
  pendingL1 = null;
});

document.getElementById("l1-confirm-btn").addEventListener("click", () => {
  const score = parseInt(document.getElementById("l1-score").value);
  const tp = parseFloat(document.getElementById("l1-tp").value);
  if (isNaN(score)) { alert("请输入分数"); return; }
  const team = pendingL1 ? pendingL1.team : null;
  document.getElementById("l1-modal").classList.add("hidden");
  document.getElementById("l1-score").value = "";
  document.getElementById("l1-tp").value = "";
  pendingL1 = null;
  if (team) {
    apiPost("/api/occupy", { cell_id: 0, team, score, tp: isNaN(tp) ? null : tp });
  }
});

function renderPanel(state) {
  document.getElementById("defender-score").textContent = Math.round(state.scores.defender);
  document.getElementById("attacker-score").textContent = Math.round(state.scores.attacker);
  renderTimer(state.elapsed, state.time_limit || 25);

  const l1 = state.l1;
  const l1El = document.getElementById("l1-status");
  if (l1.holder) {
    const holderCn = l1.holder === "defender" ? "防守方" : "攻击方";
    const holderColor = l1.holder === "defender" ? "var(--defender-bright)" : "var(--attacker-bright)";
    const tpStr = (l1.high_tp !== null && l1.high_tp !== undefined) ? ` · tp${l1.high_tp}` : "";
    l1El.innerHTML = `<b style="color:${holderColor}">${holderCn}</b><br>${l1.high_score.toLocaleString()}${tpStr}`;
  } else {
    l1El.textContent = "未占领";
  }

  const phaseEl = document.getElementById("game-phase");
  const bannerEl = document.getElementById("winner-banner");
  const boardArea = document.getElementById("board-area");
  if (!state.started) {
    phaseEl.textContent = "未开始 · 点击随机开局";
    bannerEl.textContent = "";
    boardArea.classList.remove("victory-flash");
  } else if (state.game_over) {
    if (state.win_type === "top") {
      phaseEl.textContent = "顶端直胜";
      bannerEl.textContent = "谐律崩解 · 攻击方获胜";
      boardArea.classList.add("victory-flash");
    } else {
      phaseEl.textContent = "计时结束";
      const w = state.winner;
      bannerEl.textContent = w === "draw" ? "平局" : (w === "defender" ? "防守方获胜" : "攻击方获胜");
    }
  } else {
    phaseEl.textContent = "进行中";
    bannerEl.textContent = "";
    boardArea.classList.remove("victory-flash");
  }
}

function renderTimer(elapsed, limit) {
  const e = Math.min(elapsed, limit);
  const mm = Math.floor(e);
  const ss = Math.floor((e - mm) * 60);
  document.getElementById("timer-display").textContent =
    `${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`;
  const pct = Math.min(e / limit * 100, 100);
  const fill = document.getElementById("timer-fill");
  fill.style.width = pct + "%";
  if (pct < 60) fill.style.background = "var(--gold)";
  else if (pct < 85) fill.style.background = "#f59e0b";
  else fill.style.background = "var(--attacker)";
}

window.renderPanel = renderPanel;
window.renderTimer = renderTimer;

setInterval(async () => {
  try {
    const r = await fetch("/api/tick");
    const j = await r.json();
    renderTimer(j.elapsed, j.time_limit || 25);
    if (j.game_over && !window._lastGameOver) {
      window._lastGameOver = true;
      fetch("/api/state").then(r => r.json()).then(s => { window.renderPanel(s); });
    } else if (!j.game_over) {
      window._lastGameOver = false;
    }
  } catch (e) {}
}, 1000);

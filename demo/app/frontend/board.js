const LAYER_SIZES = [1, 2, 3, 4, 5, 6];
const ENERGY_COUNT = 6;

function getLayerAndIndex(id) {
  if (id >= 21) return [7, id - 21];
  let start = 0;
  for (let layer = 1; layer <= 6; layer++) {
    const size = LAYER_SIZES[layer - 1];
    if (id < start + size) return [layer, id - start];
    start += size;
  }
  return [1, 0];
}

const pyramidEl = document.getElementById("pyramid");
let cellElements = {};
let boardState = [];
let hoverId = -1;
let selectedTeam = null;
let pendingL1 = null;

function buildPyramid() {
  pyramidEl.innerHTML = "";
  cellElements = {};

  // L1 能量线：独立于 L1 格正上方的一行（与 L1 方格同宽、水平对齐），
  // 内含能量格点 + 攻击方等待进度条；不占用格子内部空间，避免遮挡歌名/难度/任务
  const l1Line = document.createElement("div");
  l1Line.className = "l1-energy-line";
  l1Line.id = "l1-energy-line";
  l1Line.innerHTML =
    '<div class="l1-pips"></div>' +
    '<div class="l1-timer"><div class="l1-timer-fill" id="l1-timer-fill"></div></div>';
  pyramidEl.appendChild(l1Line);

  for (let layer = 1; layer <= 6; layer++) {
    const row = document.createElement("div");
    row.className = "pyramid-row";
    row.dataset.layer = layer;
    const size = LAYER_SIZES[layer - 1];
    for (let i = 0; i < size; i++) {
      const id = layer * (layer - 1) / 2 + i;
      const cell = createCellEl(id);
      row.appendChild(cell);
      cellElements[id] = cell;
    }
    pyramidEl.appendChild(row);
  }

  const energyRow = document.createElement("div");
  energyRow.className = "pyramid-row";
  for (let i = 0; i < ENERGY_COUNT; i++) {
    const cell = createCellEl(21 + i);
    energyRow.appendChild(cell);
    cellElements[21 + i] = cell;
  }
  pyramidEl.appendChild(energyRow);
}

function createCellEl(id) {
  const el = document.createElement("div");
  el.className = "cell";
  el.dataset.id = id;
  el.addEventListener("click", () => onCellClick(id));
  el.addEventListener("mouseenter", () => { hoverId = id; updateHover(); if (window.onCellHover) window.onCellHover(id); });
  el.addEventListener("mouseleave", () => { hoverId = -1; updateHover(); if (window.onCellHover) window.onCellHover(-1); });
  return el;
}

function updateHover() {
  Object.values(cellElements).forEach(el => el.classList.remove("hover-active"));
  if (hoverId >= 0 && cellElements[hoverId]) cellElements[hoverId].classList.add("hover-active");
}

function renderBoard() {
  for (let id = 0; id < 27; id++) {
    const el = cellElements[id];
    const cell = boardState[id];
    if (!el || !cell) continue;

    el.className = "cell";
    if (cell.is_energy) {
      el.classList.add("energy");
      el.innerHTML = `<div class="cell-diff">能源</div>`;
      continue;
    }

    if (cell.owner === "defender") el.classList.add("owner-defender");
    else if (cell.owner === "attacker") {
      el.classList.add("owner-attacker");
      if (cell.activated) el.classList.add("activated");
    }
    if (cell.from_encirclement) el.classList.add("from-encirclement");

    const songEl = cell.song_name ? `<div class="cell-song">${cell.song_name}</div>` : "";
    const diffLabel = cell.difficulty_label || ("CHAOS " + cell.diff_score);
    const taskShort = cell.task_name || "-";
    const bonusTag = (cell.owner === "attacker" && cell.activated && cell.energy_bonus > 0)
      ? `<span class="cell-bonus">(+${cell.energy_bonus})</span>` : "";
    // L1 格内部只渲染正常内容（歌名/难度/任务/分数）；
    // 能量格点行与等待进度条独立于格子上方（见 updateL1Line）
    el.innerHTML = `
      <div class="cell-score">${cell.total_score}${bonusTag}</div>
      ${songEl}
      <div class="cell-diff">${diffLabel}</div>
      <div class="cell-task">${taskShort}</div>
    `;
  }
  updateL1Line();
}

// 更新 L1 能量线：格点数量 = 能量目标（10），攻击方持有时显示等待进度条
function updateL1Line() {
  const line = document.getElementById("l1-energy-line");
  if (!line) return;
  const e = window._l1Energy || { value: 0, target: 10, holder: null, progress: 0 };
  const target = Math.max(1, e.target || 10);
  const pipsEl = line.querySelector(".l1-pips");
  let pips = "";
  for (let i = 0; i < target; i++) {
    pips += `<span class="l1-pip${i < (e.value || 0) ? " on" : ""}" title="能量 ${i + 1}/${target}"></span>`;
  }
  pipsEl.innerHTML = pips;
  const timerEl = line.querySelector(".l1-timer");
  const holderIsAtk = e.holder === "attacker";
  timerEl.classList.toggle("show", holderIsAtk);
  if (holderIsAtk) timerEl.title = "攻击方持有 L1 · 距下次 +1 能量";
  const fill = document.getElementById("l1-timer-fill");
  if (fill) fill.style.width = Math.round((e.progress || 0) * 100) + "%";
}

function onCellClick(id) {
  if (id >= 21) return;
  if (!selectedTeam) { alert("请先在顶部选择阵营"); return; }

  if (selectedTeam === "clear") {
    apiPost("/api/cancel", { cell_id: id });
    return;
  }

  if (id === 0) {
    pendingL1 = { team: selectedTeam };
    document.getElementById("l1-modal").classList.remove("hidden");
    document.getElementById("l1-score").focus();
    return;
  }

  apiPost("/api/occupy", { cell_id: id, team: selectedTeam });
}

function refreshState() {
  fetch("/api/state").then(r => r.json()).then(s => {
    window.setBoardState(s.board);
    window.renderPanel(s);
  }).catch(() => {});
}

document.getElementById("import-songs").addEventListener("click", () => {
  document.getElementById("songs-modal").classList.remove("hidden");
  document.getElementById("songs-json").focus();
});

document.getElementById("songs-confirm-btn").addEventListener("click", () => {
  const textarea = document.getElementById("songs-json");
  let data;
  try {
    data = JSON.parse(textarea.value);
  } catch (e) {
    alert("JSON 格式错误: " + e.message);
    return;
  }
  apiPost("/api/songs", data).then(res => {
    if (res.ok) {
      alert("导入成功：" + res.count + " 首");
      document.getElementById("songs-modal").classList.add("hidden");
      textarea.value = "";
      refreshState();
    } else {
      alert(res.error || "导入失败");
    }
  });
});

document.getElementById("songs-cancel-btn").addEventListener("click", () => {
  document.getElementById("songs-modal").classList.add("hidden");
  document.getElementById("songs-json").value = "";
});

buildPyramid();

// 自适应缩放：空间不足时整体等比缩小，保证金字塔完整可见
function fitPyramid() {
  const area = document.getElementById("board-area");
  const pyramid = document.getElementById("pyramid");
  if (!area || !pyramid) return;
  // 临时去掉缩放测自然尺寸
  pyramid.style.transform = "none";
  pyramid.style.transformOrigin = "top center";
  const natH = pyramid.offsetHeight;
  const natW = pyramid.offsetWidth;
  const availW = area.clientWidth - 8;
  const availH = area.clientHeight - 8;
  const scale = Math.min(1, availW / natW, availH / natH);
  pyramid.style.transform = `scale(${scale})`;
  // 缩放后容器占位高度 = 自然高度 × scale（transform 不改变布局占位，用 margin 修正居中）
  pyramid.style.margin = "auto";
  pyramid.style.minHeight = `${natH * scale}px`;
  pyramid.style.minWidth = `${natW * scale}px`;
}

window.addEventListener("resize", fitPyramid);
window.fitPyramid = fitPyramid;
// 页面加载后先适配一次（等字体/布局稳定）
setTimeout(fitPyramid, 100);
setTimeout(fitPyramid, 400);

window.renderBoard = () => {
  renderBoard();
  fitPyramid();
};
window.setBoardState = (board) => {
  boardState = board;
  // 渲染由 renderPanel 触发：先写入 window._l1Energy 再 renderBoard，
  // 保证 L1 能量线首帧即用最新值（避免用默认值闪一帧）。
};
window.getSelectedTeam = () => selectedTeam;
window.setSelectedTeam = (t) => { selectedTeam = t; };
window.getBoardState = () => boardState;

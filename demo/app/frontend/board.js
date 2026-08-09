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
let encircledSet = new Set();
let hoverId = -1;
let selectedTeam = null;
let pendingL1 = null;

function buildPyramid() {
  pyramidEl.innerHTML = "";
  cellElements = {};

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
    if (encircledSet.has(id)) el.classList.add("encircled");

    const songEl = cell.song_name ? `<div class="cell-song">${cell.song_name}</div>` : "";
    const diffLabel = cell.difficulty_label || ("CHAOS " + cell.diff_score);
    const taskShort = cell.task_name || "-";
    const bonusTag = (cell.owner === "attacker" && cell.activated && cell.energy_bonus > 0)
      ? `<span class="cell-bonus">(+${cell.energy_bonus})</span>` : "";
    el.innerHTML = `
      <div class="cell-score">${cell.total_score}${bonusTag}</div>
      ${songEl}
      <div class="cell-diff">${diffLabel}</div>
      <div class="cell-task">${taskShort}</div>
    `;
  }
}

function onCellClick(id) {
  if (id >= 21) return;
  if (!selectedTeam) { alert("请先在顶部选择阵营"); return; }

  if (id === 0) {
    pendingL1 = { team: selectedTeam };
    document.getElementById("l1-modal").classList.remove("hidden");
    document.getElementById("l1-score").focus();
    return;
  }

  if (selectedTeam === "clear") {
    apiPost("/api/cancel", { cell_id: id });
  } else {
    apiPost("/api/occupy", { cell_id: id, team: selectedTeam });
  }
}

function refreshState() {
  fetch("/api/state").then(r => r.json()).then(s => {
    window.setBoardState(s.board, s.encircled);
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

window.renderBoard = renderBoard;
window.setBoardState = (board, encircled) => {
  boardState = board;
  encircledSet = new Set(encircled);
  window.encircledSet = encircledSet;
  renderBoard();
  fitPyramid();
};
window.encircledSet = encircledSet;
window.getSelectedTeam = () => selectedTeam;
window.setSelectedTeam = (t) => { selectedTeam = t; };
window.getBoardState = () => boardState;

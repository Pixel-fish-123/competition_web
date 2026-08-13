function renderEvents(events) {
  const list = document.getElementById("event-list");
  list.innerHTML = "";
  events.forEach((ev, idx) => {
    const li = document.createElement("li");
    if (idx === 0) li.classList.add("new");
    let color = "var(--text-dim)";
    if (ev.type === "occupy") color = "var(--text)";
    else if (ev.type === "encircle") color = "var(--defender-bright)";
    else if (ev.type === "l1") color = "var(--gold)";
    else if (ev.type === "victory") color = "var(--gold)";
    else if (ev.type === "system") color = "var(--text-mute)";
    li.style.color = color;
    li.textContent = `[${ev.time}] ${ev.text}`;
    list.appendChild(li);
  });
}

window.onCellHover = function (id) {
  const detail = document.getElementById("cell-detail");
  const board = window.getBoardState();
  if (id < 0 || !board[id]) {
    detail.textContent = "悬停查看";
    return;
  }
  const cell = board[id];
  const [layer, idx] = getLayerAndIndex(id);
  let ownerCn = "未占领";
  let ownerColor = "var(--text-mute)";
  if (cell.owner === "defender") { ownerCn = "防守方"; ownerColor = "var(--defender-bright)"; }
  else if (cell.owner === "attacker") {
    ownerCn = cell.activated ? "攻击方 · 已激活" : "攻击方 · 未激活";
    ownerColor = cell.activated ? "var(--attacker-bright)" : "var(--text-mute)";
  }

  const diffLabel = cell.difficulty_label || ("CHAOS " + cell.diff_score);
  const songLine = cell.song_name ? `<div style="color:var(--text);font-weight:600">${cell.song_name}</div>` : "";
  const bonusLine = (cell.owner === "attacker" && cell.activated && cell.energy_bonus > 0)
    ? `<br>能源加成: <b style="color:var(--bonus)">+${cell.energy_bonus}</b>` : "";
  detail.innerHTML = `
    <b style="color:var(--gold)">L${layer} · 格${idx}</b> ${cell.is_energy ? "· 能源" : ""}<br>
    ${songLine}
    ${diffLabel}<br>
    任务: ${cell.task_name || "-"}<br>
    分: ${cell.diff_score} (+${cell.task_bonus}) = <b style="color:var(--gold)">${cell.total_score}</b>${bonusLine}<br>
    <b style="color:${ownerColor}">${ownerCn}</b>
  `;
};

function onState(state) {
  window.setBoardState(state.board);
  window.renderPanel(state);
  renderEvents(state.events);
}

connectWS(onState);

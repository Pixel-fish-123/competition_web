const WS_URL = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws";
let ws = null;
let stateCache = null;

function connectWS(onState) {
  ws = new WebSocket(WS_URL);
  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "state_update") {
      stateCache = msg;
      onState(msg);
    }
  };
  ws.onclose = () => {
    setTimeout(() => connectWS(onState), 1500);
  };
  ws.onerror = () => { try { ws.close(); } catch (e) {} };
}

async function apiPost(path, body) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

// Zatím prázdné
// Tady později přibude:
// - WebSocket
// - render dat
// - mapování panel → watcher
const ws = new WebSocket("ws://localhost:8000/ws");

ws.onopen = () => {
  console.log("WS connected");
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  const panelId = data.panel + "-content";
  const el = document.getElementById(panelId);
  if (el) {
    el.textContent = data.text;
  }
};

ws.onclose = () => {
  console.log("WS disconnected");
};

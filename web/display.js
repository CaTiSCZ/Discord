// Připojení k serveru (Socket.io si samo zjistí adresu, pokud běží na stejném portu)
const socket = io(); 

socket.on("connect", () => {
  console.log("Socket.io connected");
});

// Zpracování nové zprávy (odpovídá tvému ws.onmessage)
socket.on("new_message", (data) => {
  // Předpokládáme, že v data.panel posíláš "panel-a" nebo "panel-b"
  // Pokud tam posíláš čísla, stačí v configu nastavit ID panelu správně
  const panelId = data.panel + "-content";
  const el = document.getElementById(panelId);
  
    // Formatter posílá pole řádků (data.lines), spojíme je do textu
    if (el) {
        const lines = Array.isArray(data.lines) ? data.lines : [];
        el.innerHTML = lines.join("\n");
    } else {
        console.warn("Element with ID " + panelId + " not found.");
  }
});
socket.on("new_image", (data) => {
  // Předpokládáme, že v data.panel posíláš "panel-a" nebo "panel-b"
  // Pokud tam posíláš čísla, stačí v configu nastavit ID panelu správně
  const panelId = data.panel + "-content";
  const imgElement = document.getElementById(panelId);
  if (!imgElement) return;
  
    if (data.url && data.url.trim() !== "") {
        imgElement.src = data.url;
        imgElement.onload = () => {
            imgElement.classList.add("visible");
        };
        imgElement.onerror = () => {
            console.log("Image failed to load:", data.url);
        };
    } else {
        // Schování obrázku
        imgElement.classList.remove("visible");
        // Vymazat src až po doznění animace (0.3s v CSS)
        setTimeout(() => { 
            if (!imgElement.classList.contains("visible")) {
                imgElement.src = ""; 
            }
        }, 350); 
    }
});

// Zpracování vymazání (clear_messages)
socket.on("clear_messages", (data) => {
  const panelId = data.panel + "-content";
  const el = document.getElementById(panelId);
  if (el) {
    el.innerHTML = "";
  }
});

socket.on("disconnect", () => {
  console.log("Socket.io disconnected");
});

socket.on("init_layout", (config) => {
    console.log("Loading layout from server:", config);
    if (!config || !config.panels) return;

    for (const [id, settings] of Object.entries(config.panels)) {
        const el = document.getElementById(id);
        if (el) {
            el.style.left = settings.x + "px";
            el.style.top = settings.y + "px";
            
            // Pokud je to textový panel, najdeme i content-area
            const content = document.getElementById(id + "-content");
            if (content) {
                if (settings.font_size) content.style.fontSize = settings.font_size + "px";
                if (settings.color) content.style.color = settings.color;
                if (settings.bold !== undefined) content.style.fontWeight = settings.bold ? "bold" : "normal";
                if (settings.italic !== undefined) content.style.fontStyle = settings.italic ? "italic" : "normal";
            }
        }
    }
});
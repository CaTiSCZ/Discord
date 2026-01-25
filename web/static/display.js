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
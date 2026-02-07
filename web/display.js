
const originalLog = console.log;
const originalError = console.error;
const originalWarn = console.warn;

function logToPython(level, msg) {
    if (typeof socket !== 'undefined' && socket && socket.connected) {
        socket.emit("js_log", { 
            level: level, 
            message: msg
        });
    } 
}

console.log = function(...args) {
    const msg = args.join(' ');
    originalLog.apply(console, args); // Pořád vypíše do konzole prohlížeče
    logToPython("INFO", msg); // Pošle do GUI bota
};

// 4. Přepsání console.error
console.error = function(...args) {
    const msg = args.join(' ');
    originalError.apply(console, args);
    logToPython("ERROR", msg);
};

// 5. Globální odchytávání chyb (Syntax error, Reference error atd.)
window.onerror = function(message, source, lineno, colno, error) {
    const fullMsg = `FATAL ERROR: ${message} (${source}:${lineno}:${colno})`;
    logToPython("ERROR", fullMsg);
    return false; // Necháme chybu probublat i dál
};


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
            console.warn("Image failed to load:", data.url);
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
    const globalStyle = config.global_style || {};

    for (const [id, settings] of Object.entries(config.panels)) {
        const el = document.getElementById(id);
        const content = document.getElementById(id + "-content");
        if (!el || !content) continue;

        // Geometrie
        el.style.left = settings.x + "px";
        el.style.top = settings.y + "px";
        if (settings.auto_size) {
            // Režim maximální velikosti (přizpůsobí se obsahu)
            el.style.width = "auto";
            el.style.height = "auto";
            el.style.maxWidth = settings.width + "px";
            el.style.maxHeight = settings.height + "px";
            // Volitelné: přidat display: inline-block nebo table, aby se šířka smrskla na text
            el.style.display = "inline-block"; 
        } else {
            // Fixní režim
            el.style.width = settings.width + "px";
            el.style.height = settings.height + "px";
            el.style.maxWidth = "none";
            el.style.maxHeight = "none";
            el.style.display = "block";
        }

        // Základní text (priorita: panel -> globální -> CSS default)
        content.style.fontFamily = settings.font_family || globalStyle.font_family || "inherit";
        content.style.fontSize = (settings.font_size || globalStyle.font_size || 24) + "px";
        content.style.color = settings.color || globalStyle.color || "#ffffff";

        // Pomocná funkce pro vytažení barvy/velikosti tagu
        const getStyle = (tag, prop, unit = '', s, g) => {
            const val = s[`${tag}_${prop}`] || g[`${tag}_${prop}`];
            if (!val) return "";
            return prop === 'color' ? `color: ${val} !important;` : `font-size: ${val}${unit} !important;`;
        };
        
        // Dynamické barvy pro tagy (přidáme CSS pravidla přímo do elementu)
        let styleTag = el.querySelector('style');
        if (!styleTag) {
            styleTag = document.createElement('style');
            el.appendChild(styleTag);
        }

        

        // Zapíšeme CSS pravidla specifická pro tento panel
        styleTag.innerHTML = `
            #${id}-content b { ${getStyle('b', 'color', '', settings, globalStyle)} ${getStyle('b', 'size', 'px', settings, globalStyle)} }
            #${id}-content i { ${getStyle('i', 'color', '', settings, globalStyle)} ${getStyle('i', 'size', 'px', settings, globalStyle)} }
            #${id}-content u { ${getStyle('u', 'color', '', settings, globalStyle)} ${getStyle('u', 'size', 'px', settings, globalStyle)} }
            #${id}-content s { ${getStyle('s', 'color', '', settings, globalStyle)} ${getStyle('s', 'size', 'px', settings, globalStyle)} }
        `;
    }
});
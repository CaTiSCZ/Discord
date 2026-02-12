
const originalLog = console.log;
const originalError = console.error;
const originalWarn = console.warn;

function logToPython(level, msg) {
    try {
        if (typeof socket !== 'undefined' && socket && socket.connected) {
            socket.emit("js_log", { 
                level: level, 
                message: msg
            });
        } 
    } catch (e) {
        console.warn("Socket not ready for logging yet.");
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
let globalConfig = {}; // Schováme si config pro pozdější použití

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
        if (globalConfig.panels && globalConfig.panels[data.panel]) {
            applyBackground(data.panel, globalConfig.panels[data.panel]);
        }
    } else {
        console.warn("Element with ID " + panelId + " not found.");
  }
});
socket.on("new_image", (data) => {
  // Předpokládáme, že v data.panel posíláš "panel-a" nebo "panel-b"
  // Pokud tam posíláš čísla, stačí v configu nastavit ID panelu správně
  const panelId = data.panel + "-content";
  const imgElement = document.getElementById(panelId);
  if (!imgElement) return console.warn("Element with ID " + panelId + " not found.");
  
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
    if (globalConfig.panels && globalConfig.panels[data.panel]) {
            applyBackground(data.panel, globalConfig.panels[data.panel]);
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


// Univerzální funkce pro nastavení stylu jednoho panelu
function applyBackground(id, settings) {
    const el = document.getElementById(id);
    const content = document.getElementById(`${id}-content`);
    if (!el || !content) return;

    const globalStyle = globalConfig.global_style || {};
    
    const hasContent = content.innerHTML && content.innerHTML.trim() !== "";
    el.style.backgroundColor = "transparent";
    
    if (hasContent) {
        // Barva a Průhlednost
        const bgColor = settings.bg_color || globalStyle.bg_color || "transparent";
        const bgOpacity = (settings.bg_color_opacity !== undefined) ? settings.bg_color_opacity : 
                          (globalStyle.bg_color_opacity !== undefined ? globalStyle.bg_color_opacity : 1.0);

        content.style.backgroundColor = setBgColor(bgColor, bgOpacity);
        content.style.padding = settings.is_image ? "0px" : "10px";
        content.style.display = "inline-block";

    } else {
        // Pokud není obsah, panel musí být neviditelný
        content.style.backgroundColor = "transparent";
        content.style.padding = "0px";
        content.style.display = "none";
    }
}
    

function applyPanelStyle(id, settings) {
    const el = document.getElementById(id);
    const content = document.getElementById(`${id}-content`);
    if (!el || !content) return;

    const globalStyle = globalConfig.global_style || {};
    
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
    if (settings.is_image) {
        
        img = el.querySelector("img");

        // Centrování obrázku v panelu
        if (settings.center_content) {
            content.style.display = "flex";
            content.style.justifyContent = "center";
            content.style.alignItems = "center";
        } else {
            content.style.display = "block";
        }

        // Stylování samotného <img> tagu
        img.style.objectFit = settings.img_fit || "contain";
        img.style.width = "100%";
        img.style.height = "100%";
        
        if (settings.img_opacity !== undefined && settings.img_opacity !== "") {
            img.style.opacity = settings.img_opacity;
        } else {
            img.style.opacity = "1";
        }
        
    } else {
        
        if (settings.center_content) {
            el.style.display = "flex";
            el.style.flexDirection = "column";
            el.style.justifyContent = "center";
            el.style.alignItems = "center";
            el.style.textAlign = "center"; // Pro případ více řádků
            content.style.textAlign = "center";
        } else {
            content.style.justifyContent = "unset";
            content.style.alignItems = "unset";
            content.style.textAlign = "left";
        }
        content.style.width = "auto"; 
        content.style.display = "inline-block";
        // Základní textové styly
        content.style.fontFamily = settings.font_family || globalStyle.font_family || "inherit";
        content.style.fontSize = (settings.font_size || globalStyle.font_size || 24) + "px";
        content.style.color = settings.text_color || globalStyle.text_color || "#ffffff";
        
        // Tagy (b, i, u, s) - ponecháme tvou logiku se styleTagem
        let styleTag = el.querySelector('style');
        if (!styleTag) {
            styleTag = document.createElement('style');
            el.appendChild(styleTag);
        }
        
        const getStyle = (tag, prop, unit = '', s, g) => {
            const val = s[`${tag}_${prop}`] || g[`${tag}_${prop}`];
            return val ? (prop === 'color' ? `color: ${val} !important;` : `font-size: ${val}${unit} !important;`) : "";
        };

        styleTag.innerHTML = `
            #${id}-content b { ${getStyle('b', 'color', '', settings, globalStyle)} ${getStyle('b', 'size', 'px', settings, globalStyle)} }
            #${id}-content i { ${getStyle('i', 'color', '', settings, globalStyle)} ${getStyle('i', 'size', 'px', settings, globalStyle)} }
            #${id}-content u { ${getStyle('u', 'color', '', settings, globalStyle)} ${getStyle('u', 'size', 'px', settings, globalStyle)} }
            #${id}-content s { ${getStyle('s', 'color', '', settings, globalStyle)} ${getStyle('s', 'size', 'px', settings, globalStyle)} }
        `;
    }

    
}

// Při načtení layoutu
socket.on("init_layout", (config) => {
    if (!config || !config.panels) return;
    console.log("Loading layout from server:", config);
    globalConfig = config; // Uložíme do globální proměnné
    for (const [id, settings] of Object.entries(config.panels)) {
        applyBackground(id, settings);
        applyPanelStyle(id, settings);
    }
});

// KLÍČOVÁ ZMĚNA: Při každé zprávě znovu aplikovat styl
socket.on("update_panel", (data) => {
    const content = document.getElementById(`${data.id}-content`);
    if (content) {
        content.innerHTML = data.content;
        // Počkáme zlomek sekundy a zaktualizujeme barvu pozadí podle nového obsahu
        if (globalConfig.panels && globalConfig.panels[data.id]) {
            applyBackground(data.id, globalConfig.panels[data.id]);
        }
    }
});

function setBgColor( hexColor, opacity) {
    if (!hexColor || hexColor === "transparent") return "transparent";
    let r = 0, g = 0, b = 0;
    if (hexColor.startsWith('#')) {
        r = parseInt(hexColor.slice(1, 3), 16);
        g = parseInt(hexColor.slice(3, 5), 16);
        b = parseInt(hexColor.slice(5, 7), 16);
    }
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}
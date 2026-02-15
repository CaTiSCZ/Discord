
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


// Zpracování nové zprávy (odpovídá tvému ws.onmessage)
socket.on("new_message", (data) => {
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
    const panelId = data.panel + "-content";
    const imgElement = document.getElementById(panelId);
    const settings = (globalConfig.panels && globalConfig.panels[data.panel]) || {};
    let opacity = (settings.img_opacity !== undefined && settings.img_opacity !== "") 
                        ? parseFloat(settings.img_opacity) 
                        : 1.0;
    opacity = isNaN(opacity) ? 1.0 : Math.min(Math.max(opacity, 0), 1);

    if (!imgElement) return console.warn("Element with ID " + panelId + " not found.");
    imgElement.onload = () => {
                imgElement.style.opacity = opacity; 
                imgElement.classList.add("visible");
                if (globalConfig.panels && globalConfig.panels[data.panel]) {
                    applyBackground(data.panel, globalConfig.panels[data.panel]);
                } 
            };
    imgElement.onerror = () => {
            console.warn("Image failed to load:", data.url);
            if (globalConfig.panels && globalConfig.panels[data.panel]) {
                applyBackground(data.panel, globalConfig.panels[data.panel]);
            } 
        };   
        
        
    if (data.url && data.url.trim() !== "") {
        imgElement.src = data.url;
    } else {
        imgElement.classList.remove("visible");
        imgElement.onload = null;
        imgElement.onerror = null;
        setTimeout(() => { 
            if (!imgElement.classList.contains("visible")) {
                imgElement.src = ""; 
                if (globalConfig.panels && globalConfig.panels[data.panel]) {
                    applyBackground(data.panel, globalConfig.panels[data.panel]);
                } 
            }
        }, 350); 
    }
     
});
let globalConfig = {}; // Schováme si config pro pozdější použití
socket.on("init_layout", (config) => {
    if (!config || !config.panels) return;
    console.log("Loading layout from server:", config);
    globalConfig = config; // Uložíme do globální proměnné
    for (const [id, settings] of Object.entries(config.panels)) {
        applyBackground(id, settings);
        applyPanelStyle(id, settings);
    }
});

socket.on("disconnect", () => {
  console.log("Socket.io disconnected");
});

function applyBackground(id, settings) {
    const el = document.getElementById(id);
    const content = document.getElementById(`${id}-content`);
    if (!el || !content) return;
    const globalStyle = globalConfig.global_style || {};
    const isImage = settings.is_image;
    const hasContent = isImage 
        ? (content.src && !content.src.endsWith('/') && content.getAttribute('src') !== "")
        : (content.innerHTML.trim() !== "");
    el.style.backgroundColor = "transparent";
    if (hasContent) {
        // Barva a Průhlednost
        const bgColor = settings.bg_color || globalStyle.bg_color || "transparent";
        const bgOpacity = (settings.bg_color_opacity !== undefined) ? settings.bg_color_opacity : 
                          (globalStyle.bg_color_opacity !== undefined ? globalStyle.bg_color_opacity : 1.0);
        content.style.backgroundColor = setBgColor(bgColor, bgOpacity);
        content.style.padding = settings.is_image ? "0px" : "10px";
        
    } else {
        // Pokud není obsah, panel musí být neviditelný
        content.style.backgroundColor = "transparent";
        content.style.padding = "0px";
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
    el.style.zIndex = settings.z_index !== undefined ? settings.z_index : 1;
    if (settings.auto_size) {
        // Režim maximální velikosti (přizpůsobí se obsahu)
        el.style.width = "auto";
        el.style.height = "auto";
        el.style.maxWidth = settings.width + "px";
        el.style.maxHeight = settings.height + "px";
    } else {
        // Fixní režim
        el.style.width = settings.width + "px";
        el.style.height = settings.height + "px";
        el.style.maxWidth = "none";
        el.style.maxHeight = "none";
    }
    el.style.flexDirection = "column";
    el.style.display = "flex";
    if (settings.center_content) {
            el.style.justifyContent = "center";
            el.style.alignItems = "center";
        } else {
            el.style.justifyContent = "flex-start";
            el.style.alignItems = "flex-start";
        }
    if (settings.is_image) {
        const img = el.querySelector("img");
        if (!img) return;
        img.style.display = "block";
        img.style.objectFit = settings.img_fit || "contain";
        img.style.width = "100%";
        img.style.height = "100%";
        img.style.objectPosition = settings.center_content ? "center" : "left top";
        

    } else {
        if (settings.center_content) {
            el.style.textAlign = "center"; // Pro případ více řádků
            content.style.textAlign = "center";
        } else {
            el.style.textAlign = "left"; // Zarovnání doleva pro celý panel
            content.style.textAlign = "left";
        }
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

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

socket.on("init_layout", (config) => {
    if (!config || !config.panels) return;
    console.log("Loading layout from server:", config);
    globalConfig = config; // Uložíme do globální proměnné
    for (const [id, settings] of Object.entries(config.panels)) {
        applyPanelStyle(id, settings);
    }
});

// Zpracování nové zprávy (odpovídá tvému ws.onmessage)
socket.on("new_message", (data) => {
    const contentEl = document.getElementById(`${data.panel}-content`);
    // Formatter posílá pole řádků (data.lines), spojíme je do textu
    if (contentEl) {
        if (!data.messages || data.messages.length === 0) {
            contentEl.innerHTML = "";
            contentEl.style.display = "none";
            return;
        }
        const settings = (globalConfig.panels && globalConfig.panels[data.panel]) || {};
        contentEl.style.display = "inline-block";
        contentEl.innerHTML = data.messages.map(msg => {
            return addAuthor(msg);
        }).join("<br>");
        requestAnimationFrame(() => fitText(data.panel));
    } else {
        console.warn("Element with ID " + data.panel + " not found.");
    }
});

socket.on("new_image", (data) => {
    const el = document.getElementById(data.panel);
    const imgEl = document.getElementById(`${data.panel}-content`);
    if (!imgEl) {
        console.warn("Element with ID " + data.panel + " not found."); 
        return;
    }
    if (!data.url || data.url.trim() === "") {
        imgEl.style.display = "none"
        el.style.display = "none"

        imgElement.classList.remove("visible");
    } else {
        imgEl.classList.add("visible");
        imgEl.src = data.url;
        imgEl.style.display = "block"
        el.style.display = "block"
    }
     
});

socket.on("disconnect", () => {
  console.log("Socket.io disconnected");
});

function addAuthor(msgData) {
    let text = Array.isArray(msgData.content) ? msgData.content.join("<br>") : msgData.content;
    let showAuthor = false;
    const mode = msgData.show_author;
    const isBot = msgData.is_bot || false;
    if (mode === "both") showAuthor = true;
    else if (mode === "bot" && isBot) showAuthor = true;
    else if (mode === "human" && !isBot) showAuthor = true;

    if (showAuthor && msgData.author) {
        return `<b class = "author-name">${msgData.author}:</b><br> ${text}`;
    }
    return text;
}

function fitText(panelId) {
    const el = document.getElementById(panelId);
    const contentEl = document.getElementById(`${panelId}-content`);
    if (!el || !contentEl || !globalConfig.panels[panelId]) return;

    const data = globalConfig.panels[panelId];
    const global = globalConfig.global_style;
    const baseFontSize = data.font_size || global.font_size || 30;
    const minFontSize = baseFontSize * 0.75;

    let currentFontSize = baseFontSize;
    contentEl.style.fontSize = `${currentFontSize}px`;

    // Pokud obsah přetéká (výšku nebo šířku), zmenšuj dokud to jde
    while (
        (contentEl.scrollHeight > el.offsetHeight || contentEl.scrollWidth > el.offsetWidth) &&
        currentFontSize > minFontSize
    ) {
        currentFontSize -= 1;
        contentEl.style.fontSize = `${currentFontSize}px`;
    }
}

function applyPanelStyle(id, settings) {
    const el = document.getElementById(id);
    const contentEl = document.getElementById(`${id}-content`);
    
    if (!el || !contentEl) return;
    const globalStyle = globalConfig.global_style || {};
    const bgColor = settings.bg_color || globalStyle.bg_color || "transparent";
    const bgOpacity = settings.bg_color_opacity || globalStyle.bg_color_opacity || 1.0;
    const isCentered = settings.center_content || false
    // Geometrie
    el.style.left = settings.x + "px";
    el.style.top = settings.y + "px";
    el.style.width = settings.width + "px";
    el.style.height = settings.height + "px";
    el.style.zIndex = settings.z_index !== undefined ? settings.z_index : 1;

    el.style.justifyContent = isCentered ? 'center' : 'flex-start';
    el.style.alignItems = isCentered ? 'center' : 'flex-start';
    

    if (settings.is_image) {
        const img = el.querySelector("img");
        if (!img) return;
        el.style.backgroundColor = hexToRgba(bgColor, bgOpacity); // Pozadí vyplní celý panel
        contentEl.style.backgroundColor = "transparent";
        img.style.objectFit = settings.img_fit || "contain";
        let opacity = (settings.img_opacity !== undefined && settings.img_opacity !== "") 
                        ? parseFloat(settings.img_opacity) 
                        : 1.0;
        opacity = isNaN(opacity) ? 1.0 : Math.min(Math.max(opacity, 0), 1);
        img.style.opacity = opacity; 
    } else {
        if (settings.column_width) {
            contentEl.style.columnWidth = `${settings.column_width}px`; 
            contentEl.style.columnGap = `${settings.column_spaceing || 20}px`;
            contentEl.style.width = "fit-content";
        } else {
            contentEl.style.columnWidth = "auto";
            contentEl.style.width = "100%";
        }
        
        contentEl.style.backgroundColor = hexToRgba(bgColor, bgOpacity);
        el.style.backgroundColor = "transparent";
        // Základní textové styly
        contentEl.style.textAlign = isCentered ? 'center' : 'left';
        contentEl.style.fontFamily = settings.font_family || globalStyle.font_family || "inherit";
        contentEl.style.fontSize = (settings.font_size || globalStyle.font_size || 24) + "px";
        contentEl.style.color = settings.text_color || globalStyle.text_color || "#ffffff";
        
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

function hexToRgba( hexColor, opacity) {
    if (!hexColor || hexColor === "transparent") return "transparent";
    let r = 0, g = 0, b = 0;
    if (hexColor.startsWith('#')) {
        r = parseInt(hexColor.slice(1, 3), 16);
        g = parseInt(hexColor.slice(3, 5), 16);
        b = parseInt(hexColor.slice(5, 7), 16);
    }
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}
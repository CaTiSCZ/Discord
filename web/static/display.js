// Připojení k serveru (Socket.io si samo zjistí adresu, pokud běží na stejném portu)
const socket = io(); 

socket.on("connect", () => {
  console.log("Socket.io connected");
});

socket.on("new_message", (data) => {
    console.log("Data received:", data);
    const el = document.getElementById(data.panel + "-content");
    if (!el) return;

    let allLines = [];

    // 1. Hlavička
    if (data.config && data.config.header_text && data.config.header_text.trim() !== "") {
        allLines.push(`<span>${data.config.header_text.toUpperCase()}</span>`);
    }

    // 2. Zpracování zpráv do řádků (identické s tvým Python formatterem)
    data.messages.forEach(msg => {
        let linesContent = [];

        if (msg.is_avrae && msg.embeds.length > 0) {
            // --- TADY JE KOPIE TVÉHO process_roll ---
            const emb = msg.embeds[0];
            const title = emb.title || "";
            const desc = emb.description || "";

            // 1. Větev: Multirolly, Advantage, Disadvantage
            if (title.includes("Adv") || title.includes("Dis") || title.includes("Roll")) {
                linesContent.push(title.toUpperCase()); // Tvůj format: upper()
                emb.fields.forEach(f => {
                    // Odstranění zpětných apostrofů a "Result: "
                    const val = f.value.replace(/`|Result: /g, "");
                    linesContent.push(`${f.name}: ${val}`);
                });
            } 
            // 2. Větev: Jednoduchý hod s poznámkou nebo bez
            else {
                // Hledání poznámky za dvojtečkou (např. "Aragorn: Stealth")
                const noteMatch = title.match(/:\s*(.*)/);
                const note = noteMatch ? noteMatch[1] : "";
                
                // Vytažení výsledku z popisu (desc)
                const resultMatch = desc.match(/Result:\s*(.*)/);
                const result = resultMatch 
                    ? resultMatch[1].replace(/`/g, "") 
                    : desc.replace(/`/g, "");
                
                if (note) linesContent.push(note.toUpperCase());
                linesContent.push(`RESULT: ${result}`);
            }
        } else {
            // Běžná zpráva
            if (msg.content) {
                linesContent = msg.content.split(/\r?\n/);
            }
        }

        // --- LOGIKA SHOW_AUTHOR_MODE ---
        const authorPrefix = `${msg.author}: `;
        const indent = " ".repeat(authorPrefix.length);

        linesContent.forEach((rawLine, idx) => {
            let currentPrefix = "";
            
            // Rozhodnutí o prefixu podle tvého show_author_mode (name/both/none)
            if (data.config.show_author === "name" || data.config.show_author === "both") {
                currentPrefix = (idx === 0) ? authorPrefix : indent;
            }

            // WrapLine teď vezme tenhle prefix a k němu přilepí text, 
            // přičemž hlídá, aby celková délka nepřesáhla max_width.
            const wrapped = wrapText(rawLine, data.config.max_width, currentPrefix);
            allLines = allLines.concat(wrapped);
        });
    });

    // 3. Rozdělení do sloupců
    let columnsHtml = "";
    for (let i = 0; i < allLines.length; i += data.config.max_rows_per_column) {
        const slice = allLines.slice(i, i + data.config.max_rows_per_column);
        columnsHtml += `<div class="column">${slice.join('\n')}</div>`;
    }
    el.innerHTML = columnsHtml;
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

function parseMarkdown(text) {
    if (!text) return "";
    return text
        .replace(/\*\*\*(.*?)\*\*\*/g, '<b><i>$1</i></b>')
        .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
        .replace(/\*(.*?)\*/g, '<i>$1</i>')
        .replace(/__(.*?)__/g, '<u>$1</u>')
        .replace(/~~(.*?)~~/g, '<s>$1</s>');
}

function wrapText(text, maxWidth, prefix) {
    if (!text && prefix) return [`<span>${prefix}</span>`];
    if (!text) return [];

    let words = text.split(' ');
    let lines = [];
    let currentLine = prefix;

    words.forEach(word => {
        let testLine = currentLine + (currentLine.length > prefix.length ? " " : "") + word;
        if (testLine.length <= maxWidth) {
            currentLine = testLine;
        } else {
            lines.push(`<span>${parseMarkdown(currentLine)}</span>`);
            currentLine = " ".repeat(prefix.length) + word;
        }
    });
    lines.push(`<span>${parseMarkdown(currentLine)}</span>`);
    return lines;
}


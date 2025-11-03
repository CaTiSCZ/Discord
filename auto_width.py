import obspython as obs
import os
from dotenv import load_dotenv
import html
import re

load_dotenv("personal_data.env")
# --- Nastavení ---
file_path = os.getenv("FILE_PATH", "rolls.txt")   # ⚠️ změň cestu na svůj HTML nebo TXT soubor
source_name = "rolls_view"          # ⚠️ přesně tak, jak se jmenuje Browser Source v OBS

min_width = 650                       # px, minimální šířka
chars_per_min_width = 38              # počet znaků odpovídající min_width
px_per_char = 18                      # kolik pixelů přidat na každý další znak
update_interval = 1.0                 # sekundy mezi kontrolami
max_width = 2000                      # horní limit šířky (ochrana)

def script_description():
    return "Automaticky mění šířku Browser Source podle délky obsahu HTML souboru."

def script_properties():
    props = obs.obs_properties_create()
    obs.obs_properties_add_path(props, "file_path", "Cesta k HTML/TXT souboru", obs.OBS_PATH_FILE, "*.html;*.txt", None)
    obs.obs_properties_add_text(props, "source_name", "Název OBS zdroje", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_int(props, "min_width", "Minimální šířka (px)", 100, 4000, 10)
    obs.obs_properties_add_int(props, "chars_per_min_width", "Počet znaků při minimální šířce", 1, 200, 1)
    obs.obs_properties_add_int(props, "px_per_char", "Pixely na znak", 1, 100, 1)
    obs.obs_properties_add_float(props, "update_interval", "Interval kontroly (s)", 0.5, 30.0, 0.5)
    obs.obs_properties_add_int(props, "max_width", "Maximální šířka (px)", 100, 8000, 10)
    return props

def script_update(settings):
    global file_path, source_name, min_width, chars_per_min_width, px_per_char, update_interval, max_width
    file_path = obs.obs_data_get_string(settings, "file_path")
    source_name = obs.obs_data_get_string(settings, "source_name")
    min_width = obs.obs_data_get_int(settings, "min_width")
    chars_per_min_width = obs.obs_data_get_int(settings, "chars_per_min_width")
    px_per_char = obs.obs_data_get_int(settings, "px_per_char")
    update_interval = obs.obs_data_get_double(settings, "update_interval")
    max_width = obs.obs_data_get_int(settings, "max_width")
    obs.timer_remove(update_source_width)
    if file_path and source_name:
        obs.timer_add(update_source_width, int(update_interval * 1000))

def get_visible_length_from_html(text):
    """Najde nejdelší viditelný řádek v těle HTML (ignoruje tagy a entity)."""
    text = text.lstrip('\ufeff').strip()

    # 🔸 extrahuj pouze obsah mezi <body> a </body>
    match = re.search(r"<body[^>]*>(.*?)</body>", text, re.DOTALL | re.IGNORECASE)
    if match:
        text = match.group(1)

    # odstraníme všechny HTML tagy
    clean = re.sub(r"<[^>]+>", "", text)
    clean = html.unescape(clean)

    # rozdělíme po řádcích
    lines = [line.strip() for line in clean.splitlines() if line.strip()]
    max_len = max((len(line) for line in lines), default=0)
    return max_len


def update_source_width():
    if not os.path.exists(file_path):
        return

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        visible_len = get_visible_length_from_html(content)
    except Exception as e:
        print("Chyba čtení souboru:", e)
        return

    # Výpočet nové šířky
    extra_chars = max(0, visible_len - chars_per_min_width)
    new_width = min_width + extra_chars * px_per_char
    new_width = min(new_width, max_width)

    # Nastavení šířky OBS Browser Source
    source = obs.obs_get_source_by_name(source_name)
    if source is not None:
        settings = obs.obs_source_get_settings(source)
        obs.obs_data_set_int(settings, "width", new_width)
        obs.obs_source_update(source, settings)
        obs.obs_data_release(settings)
        obs.obs_source_release(source)
        print(f"[auto_width] Nastavena šířka {new_width}px (znaků: {visible_len})")
    else:
        print(f"[auto_width] Nenalezen zdroj: {source_name}")

def script_unload():
    obs.timer_remove(update_source_width)

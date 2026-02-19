import os, re, json, hashlib
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

MINERVA_URL = "https://www.falloutbuilds.com/fo76/minerva/"
NUKE_URL    = "https://www.falloutbuilds.com/fo76/nuke-codes/"

MINERVA_WEBHOOK = os.environ["MINERVA_WEBHOOK"]
NUKE_WEBHOOK    = os.environ["NUKE_WEBHOOK"]
INCLUDE_SOURCE_LINK = os.environ.get("INCLUDE_SOURCE_LINK", "0") == "1"
ALWAYS_POST = os.environ.get("ALWAYS_POST", "1") == "1"

STATE_FILE = "state.json"

def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def post(webhook, content):
    r = requests.post(webhook, json={"content": content}, timeout=20)
    r.raise_for_status()

def render_page_html(url: str) -> str:
    """Loads the page like a real browser so countdown/items render, bypassing most 403 rules."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        # Let client-side widgets (countdown) render
        page.wait_for_timeout(2500)
        html = page.content()
        browser.close()
        return html

def pick_first_match(text, patterns):
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(0)
    return None

def extract_minerva_details(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)

    # Sale number: catches "Sale #23" or "Minerva Sale 23"
    sale = None
    m = re.search(r"(Sale\s*#?\s*\d+|Minerva\s*Sale\s*#?\s*\d+)", text, re.IGNORECASE)
    if m:
        sale = re.sub(r"\s+", " ", m.group(0)).replace("Minerva ", "").strip()

    # Location: common words
    location = None
    for loc in ["Fort Atlas", "Foundation", "Crater"]:
        if re.search(rf"\b{re.escape(loc)}\b", text, re.IGNORECASE):
            location = loc
            break

    # Countdown: try common countdown clues
    # If the site uses a real “countdown” element, it often has id/class containing countdown/timer.
    countdown = None
    countdown_el = soup.find(attrs={"id": re.compile("countdown|timer", re.IGNORECASE)}) \
                   or soup.find(attrs={"class": re.compile("countdown|timer", re.IGNORECASE)})
    if countdown_el:
        countdown = countdown_el.get_text(" ", strip=True)

    # Fallback: look for lines that smell like "Time remaining"
    if not countdown:
        for line in text.splitlines():
            if re.search(r"(time\s*remaining|ends?\s*in|countdown)", line, re.IGNORECASE):
                countdown = line.strip()
                break

    # Items: we aim for a UL/OL list near an "Items" heading,
    # but without seeing the DOM we do a robust heuristic:
    items = []
    # 1) Prefer any list that appears after an "Items" / "Inventory" / "For Sale" header
    headers = soup.find_all(["h1","h2","h3","h4"])
    target_header = None
    for h in headers:
        t = h.get_text(" ", strip=True).lower()
        if any(k in t for k in ["items", "inventory", "for sale", "sale items"]):
            target_header = h
            break

    if target_header:
        # walk forward for first ul/ol
        nxt = target_header.find_next(["ul","ol"])
        if nxt:
            for li in nxt.find_all("li"):
                it = li.get_text(" ", strip=True)
                if it:
                    items.append(it)

    # 2) Fallback: grab bullet-like lines containing "Plan:" "Mod:" etc
    if not items:
        for line in text.splitlines():
            if re.search(r"^(Plan|Mod|Recipe|Armor|Weapon)\b[:\-]", line, re.IGNORECASE):
                items.append(line.strip())

    # Keep list sane
    items = [re.sub(r"\s+", " ", i) for i in items]
    items = list(dict.fromkeys(items))  # de-dupe preserving order
    items = items[:40]

    return {
        "sale": sale,
        "location": location,
        "countdown": countdown,
        "items": items
    }

def build_minerva_message(d: dict) -> str:
    sale_txt = d["sale"] or "Sale (number not detected)"
    loc_txt = d["location"] or "Unknown"
    cd_txt = d["countdown"] or "Countdown not detected"

    lines = [f"🧳 **Minerva — {sale_txt}**",
             f"📍 **Location**: {loc_txt}",
             f"⏳ **Time remaining**: {cd_txt}",
             "",
             f"🛒 **Items ({sale_txt})**"]

    if d["items"]:
        for it in d["items"]:
            lines.append(f"• {it}")
    else:
        lines.append("• (Could not extract item list — page layout changed)")

    if INCLUDE_SOURCE_LINK:
        lines.append("")
        lines.append(f"Source: {MINERVA_URL}")

    return "\n".join(lines)

def extract_nukes(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    matches = re.findall(r"\b(Alpha|Bravo|Charlie)\b[^\d]*(\d{4})[^\d]*(\d{4})", text, re.IGNORECASE)
    lines = ["🚀 **Fallout 76 — Weekly Nuke Codes**"]
    if matches:
        for silo, a, b in matches[:3]:
            lines.append(f"**{silo.title()}**: `{a} {b}`")
    else:
        lines.append("Could not detect codes (page format changed).")
    if INCLUDE_SOURCE_LINK:
        lines.append(f"Source: {NUKE_URL}")
    return "\n".join(lines)

def main():
    state = load_state()

    # Minerva
    m_html = render_page_html(MINERVA_URL)
    m_data = extract_minerva_details(m_html)
    m_msg = build_minerva_message(m_data)
    m_hash = sha(m_msg)

    if ALWAYS_POST or state.get("minerva") != m_hash:
        post(MINERVA_WEBHOOK, m_msg)
        state["minerva"] = m_hash

    # Nukes (also render to avoid 403)
    n_html = render_page_html(NUKE_URL)
    n_msg = extract_nukes(n_html)
    n_hash = sha(n_msg)

    if ALWAYS_POST or state.get("nukes") != n_hash:
        post(NUKE_WEBHOOK, n_msg)
        state["nukes"] = n_hash

    save_state(state)

if __name__ == "__main__":
    main()

import os
import time
import requests
from playwright.sync_api import sync_playwright

MINERVA_URL = "https://www.falloutbuilds.com/fo76/minerva/"
NUKE_URL    = "https://www.falloutbuilds.com/fo76/nuke-codes/"

MINERVA_WEBHOOK = os.environ.get("MINERVA_WEBHOOK", "").strip()
NUKE_WEBHOOK    = os.environ.get("NUKE_WEBHOOK", "").strip()

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

def require_webhook(name: str, url: str):
    if not url or not url.startswith("http"):
        raise SystemExit(f"{name} secret is missing/invalid (must start with https://)")

def post_image(webhook: str, content: str, image_path: str):
    # Discord webhook upload (multipart/form-data)
    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        data = {"content": content[:1900]}
        r = requests.post(webhook, data=data, files=files, timeout=90)
        r.raise_for_status()

def screenshot_page(url: str, out_png: str, tries: int = 3) -> str:
    """
    Render page like a browser and screenshot it.
    IMPORTANT: Do NOT wait for 'networkidle' (can hang forever on modern sites).
    We wait for DOMContentLoaded and then sleep a few seconds for JS widgets.
    Retries handle slow/temporary hiccups.
    """
    last_err = None

    for attempt in range(1, tries + 1):
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    user_agent=USER_AGENT,
                    locale="en-US",
                    timezone_id="America/Chicago",
                    viewport={"width": 1365, "height": 768},
                )
                page = context.new_page()

                # Faster + less fragile load condition
                page.goto(url, wait_until="domcontentloaded", timeout=90000)

                # Give countdown timers / dynamic lists time to render
                page.wait_for_timeout(9000)

                # If the page is super long, full_page helps capture item lists
                page.screenshot(path=out_png, full_page=True)

                browser.close()
                return out_png

        except Exception as e:
            last_err = e
            # small backoff then retry
            if attempt < tries:
                time.sleep(3 * attempt)
            else:
                break

    raise SystemExit(f"Failed to screenshot {url} after {tries} tries. Last error: {last_err}")

def main():
    require_webhook("MINERVA_WEBHOOK", MINERVA_WEBHOOK)
    require_webhook("NUKE_WEBHOOK", NUKE_WEBHOOK)

    # Minerva
    minerva_png = screenshot_page(MINERVA_URL, "minerva.png", tries=3)
    post_image(
        MINERVA_WEBHOOK,
        "🧳 **Minerva — FalloutBuilds (current sale / full list)**",
        minerva_png
    )

    # Nuke codes
    nukes_png = screenshot_page(NUKE_URL, "nukes.png", tries=3)
    post_image(
        NUKE_WEBHOOK,
        "🚀 **Fallout 76 — Weekly Nuke Codes (FalloutBuilds)**",
        nukes_png
    )

if __name__ == "__main__":
    main()

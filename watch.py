import os
import requests
from playwright.sync_api import sync_playwright

MINERVA_URL = "https://www.falloutbuilds.com/fo76/minerva/"
NUKE_URL    = "https://www.falloutbuilds.com/fo76/nuke-codes/"

MINERVA_WEBHOOK = os.environ.get("MINERVA_WEBHOOK", "").strip()
NUKE_WEBHOOK    = os.environ.get("NUKE_WEBHOOK", "").strip()

def require_webhook(name: str, url: str):
    if not url or not url.startswith("http"):
        raise SystemExit(f"{name} secret is missing/invalid (must start with https://)")

def screenshot_page(url: str, out_png: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page.set_viewport_size({"width": 1365, "height": 768})

        # Render like a real browser (handles timers / JS-built lists)
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)

        page.screenshot(path=out_png, full_page=True)
        browser.close()
        return out_png

def post_image(webhook: str, content: str, image_path: str):
    # Discord webhook file upload: multipart/form-data
    with open(image_path, "rb") as f:
        files = {"file": (os.path.basename(image_path), f, "image/png")}
        data = {"content": content[:1900]}
        r = requests.post(webhook, data=data, files=files, timeout=90)
        r.raise_for_status()

def main():
    # Fail fast with a clear message if secrets are wrong
    require_webhook("MINERVA_WEBHOOK", MINERVA_WEBHOOK)
    require_webhook("NUKE_WEBHOOK", NUKE_WEBHOOK)

    # Minerva screenshot + post
    minerva_png = screenshot_page(MINERVA_URL, "minerva.png")
    post_image(
        MINERVA_WEBHOOK,
        "🧳 **Minerva — FalloutBuilds (current sale / full list)**",
        minerva_png
    )

    # Nuke codes screenshot + post
    nukes_png = screenshot_page(NUKE_URL, "nukes.png")
    post_image(
        NUKE_WEBHOOK,
        "🚀 **Fallout 76 — Weekly Nuke Codes (FalloutBuilds)**",
        nukes_png
    )

if __name__ == "__main__":
    main()

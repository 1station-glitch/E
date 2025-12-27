from playwright.sync_api import sync_playwright

def run_playwright():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # headless: GitHub Actions
        page = browser.new_page()
        page.goto("https://example.com")
        title = page.title()
        print(f"Title of the page is: {title}")
        browser.close()

if __name__ == "__main__":
    run_playwright()

"""Check hosted WASM startup without SQL, Temporal, runner or OIDC login."""
from urllib.parse import urlsplit


def main():
    from playwright.sync_api import sync_playwright, expect

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            # Exception only for the fixed localhost development certificate.
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            failures = []
            errors = []

            def is_asset(url):
                path = urlsplit(url).path
                return path.startswith(("/_framework/", "/_content/")) or path == "/app.css"

            def response_received(response):
                if is_asset(response.url) and response.status >= 400:
                    failures.append((urlsplit(response.url).path, response.status))

            page.on("response", response_received)
            page.on("requestfailed", lambda request: failures.append(
                (urlsplit(request.url).path, "network")) if is_asset(request.url) else None)
            page.on("pageerror", lambda error: errors.append(type(error).__name__))
            try:
                page.goto("https://localhost:8443/", wait_until="domcontentloaded")
                expect(page.get_by_role("heading", name="Задачи разработки", exact=True)).to_be_visible(timeout=60000)
                css = context.request.get("https://localhost:8443/app.css")
                assert css.status == 200 and "text/css" in css.headers.get("content-type", "")
                assert not failures and not errors, "WASM asset or startup errors"
                print("Hosted WASM startup and CSS: PASS (anonymous; no business operations)")
            finally:
                for path, status in failures:
                    print(f"Asset failed: {status} {path}")
        finally:
            browser.close()


if __name__ == "__main__":
    main()

"""Opt-in real browser/platform test. Run with fake runner on the local test stack."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://localhost:8443"


def main():
    from playwright.sync_api import sync_playwright, expect
    settings = json.loads((ROOT / ".local/test-settings.json").read_text())
    if settings["runner"]["mode"] != "fake":
        raise RuntimeError("Smoke requires fake runner settings")
    credentials = json.loads((ROOT / ".local/test-infra/credentials.json").read_text())
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # Trust exception confined to this isolated browser context/dev self-signed cert.
        def login(user):
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.goto(BASE + "/login")
            page.locator("#username").fill(user)
            page.locator("#password").fill(credentials[user])
            page.locator("#kc-login").click()
            page.wait_for_url(BASE + "/", timeout=30000)
            return context, page
        try:
            owner, page = login("developer")
            # Hosted WASM must be served by the API origin, not a separate dev server.
            loader = owner.request.get(BASE + "/_framework/blazor.webassembly.js")
            assert loader.status == 200 and "text/html" not in loader.headers.get("content-type", "")
            page.get_by_label("Репозиторий").select_option("11111111-1111-4111-8111-111111111111")
            page.get_by_label("Commit", exact=True).fill("a" * 40)
            page.get_by_label("Что нужно изменить").fill("Local fake smoke test; no model call")
            page.get_by_role("button", name="Запустить", exact=True).click()
            page.wait_for_url(re.compile(r"/runs/[0-9a-f-]+$"), timeout=30000)
            run_url = page.url
            run_id = run_url.rsplit("/", 1)[1]
            expect(page.locator("strong").filter(has_text="SUCCEEDED")).to_be_visible(timeout=90000)
            page.reload()
            expect(page.get_by_role("link", name="Скачать описание результата")).to_be_visible(timeout=15000)
            view = owner.request.get(BASE + "/api/v1/runs/" + run_id)
            assert view.status == 200
            artifacts = view.json()["artifacts"]
            summary = next(a for a in artifacts if a["kind"] == "summary")
            result = owner.request.get(BASE + summary["downloadUrl"])
            assert result.status == 200 and "Fake runner completed" in result.text()
            other, _ = login("other")
            assert other.request.get(BASE + "/api/v1/runs/" + run_id).status == 404
            assert other.request.get(BASE + summary["downloadUrl"]).status == 404
            other.close(); owner.close()
            print("PASS: OIDC login, UI start, Temporal/fake runner completion, reload, artifact, cross-owner denial.")
            print("Run: " + run_url)
        finally:
            browser.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Do not persist browser state, credentials, traces or form contents.
        print(f"Local smoke FAILED ({type(exc).__name__}). Check services and fake runner.", file=sys.stderr)
        sys.exit(1)

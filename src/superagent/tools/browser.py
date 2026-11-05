import asyncio
from typing import Any, Dict, Optional

from playwright.async_api import async_playwright
from selectolax.lexbor import LexborHTMLParser
from sqlalchemy.ext.asyncio import AsyncSession

from superagent.context.engine import ContextEngine
from superagent.tools.registry import registry


def clean_html_to_text(html_content: str) -> str:
    """Extracts clean text content from HTML, stripping scripts, styles, and extra whitespace."""
    tree = LexborHTMLParser(html_content)
    for tag in tree.css("script, style, nav, footer, header, svg, iframe"):
        tag.decompose()

    text = tree.body.text(separator="\n", strip=True) if tree.body else ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


@registry.register(
    name="fetch_webpage",
    description="Fetches a webpage URL using stealth browser execution, extracts clean text content, and spills the full text to disk if it exceeds token budget.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The target webpage URL (e.g., https://example.com)",
            }
        },
        "required": ["url"],
    },
)
async def fetch_webpage(
    url: str,
    session: AsyncSession,
    task_id: str,
    context_engine: ContextEngine,
    **kwargs,
) -> str:
    """Navigates to a URL using Playwright with native anti-bot evasions."""
    try:
        async with async_playwright() as p:
            # Stealth launch options to conceal headless Chromium signatures
            browser = await p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-position=0,0",
                    "--ignore-certificate-errors",
                    "--disable-extensions",
                ],
            )

            # Create realistic context
            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
            )

            # Mask navigator.webdriver flag natively prior to page load
            await context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                window.navigator.chrome = {
                    runtime: {}
                };
                Object.defineProperty(navigator, 'languages', {
                    get: () => ['en-US', 'en']
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
            """)

            page = await context.new_page()

            try:
                await page.goto(url, timeout=25000, wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)  # Allow JS hydration
            except Exception:
                pass  # Fallback if wait condition times out

            content = await page.content()
            title = await page.title()
            await browser.close()

        clean_text = clean_html_to_text(content)

        if (
            not clean_text.strip()
            or "Access Denied" in clean_text
            or "Cloudflare" in clean_text
        ):
            return (
                f"Page Title: {title}\n"
                "Notice: The site blocked the connection (Bot protection / Cloudflare challenge / Login required)."
            )

        if len(clean_text) > 3000:
            artifact_id = await context_engine.spill_content(
                session=session,
                task_id=task_id,
                title=f"Webpage: {title or url}",
                content=clean_text,
                mime_type="text/plain",
            )
            snippet = clean_text[:1500]
            return (
                f"Page Title: {title}\n"
                f"Content spilled to disk (Artifact ID: {artifact_id}).\n"
                f"Page Content Snippet:\n{snippet}\n..."
            )

        return f"Page Title: {title}\n\nContent:\n{clean_text}"

    except Exception as e:
        return f"Error fetching webpage '{url}': {str(e)}"

"""Web fetch tool for retrieving text content from web pages."""

from __future__ import annotations

import httpx
from html.parser import HTMLParser
from typing import Any

from nanobot.agent.tools.base import Tool, tool_parameters
from nanobot.agent.tools.schema import StringSchema, tool_parameters_schema


class HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text_parts: list[str] = []
        self.tag_stack: list[str] = []
        self.ignore_tags = {"script", "style", "head", "meta", "link", "noscript", "iframe", "svg"}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tag_stack.append(tag)
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "br", "tr"}:
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self.tag_stack:
            try:
                idx = len(self.tag_stack) - 1 - self.tag_stack[::-1].index(tag)
                self.tag_stack = self.tag_stack[:idx]
            except ValueError:
                pass
        if tag in {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "div", "tr"}:
            if self.text_parts and not self.text_parts[-1].endswith("\n"):
                self.text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if any(ignored in self.tag_stack for ignored in self.ignore_tags):
            return
        cleaned = data.strip()
        if cleaned:
            if self.text_parts and not self.text_parts[-1].endswith(("\n", " ", "\t")):
                self.text_parts.append(" ")
            self.text_parts.append(cleaned)

    def get_text(self) -> str:
        text = "".join(self.text_parts)
        lines = [line.strip() for line in text.splitlines()]
        non_empty_lines: list[str] = []
        for line in lines:
            if line:
                non_empty_lines.append(line)
            elif non_empty_lines and non_empty_lines[-1] != "":
                non_empty_lines.append("")
        return "\n".join(non_empty_lines).strip()


@tool_parameters(
    tool_parameters_schema(
        url=StringSchema(
            "The HTTP or HTTPS URL to fetch content from.",
            min_length=1,
        ),
        required=["url"],
    )
)
class WebFetchTool(Tool):
    """Retrieve and clean text content from a public webpage URL."""

    @classmethod
    def create(cls, ctx: Any) -> WebFetchTool:
        return cls()

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return (
            "Fetch the text content of a public webpage. "
            "Cleans up HTML tags and script/style tags to extract readable content."
        )

    async def execute(self, url: str, **kwargs: Any) -> str:
        if not url.startswith(("http://", "https://")):
            return "Error: Invalid URL. Must start with http:// or https://"
        
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                
                content_type = response.headers.get("content-type", "").lower()
                if "text/html" in content_type:
                    parser = HTMLTextExtractor()
                    parser.feed(response.text)
                    text = parser.get_text()
                else:
                    text = response.text
                
                if len(text) > 15000:
                    text = text[:15000] + "\n... [Content truncated due to size limits] ..."
                return text
        except httpx.HTTPStatusError as exc:
            return f"Error: HTTP {exc.response.status_code} error fetching URL: {exc}"
        except httpx.RequestError as exc:
            return f"Error: Network error fetching URL: {exc}"
        except Exception as exc:
            return f"Error: Unexpected error: {exc}"

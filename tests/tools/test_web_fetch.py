import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from nanobot.agent.tools.web_fetch import WebFetchTool, HTMLTextExtractor

def test_html_text_extractor() -> None:
    html = """
    <html>
        <head>
            <title>Ignored</title>
            <style>body { color: red; }</style>
            <script>alert(1);</script>
        </head>
        <body>
            <h1>Heading 1</h1>
            <p>Paragraph text here. <strong>Bold</strong> inline.</p>
            <div>
                <ul>
                    <li>Item 1</li>
                    <li>Item 2</li>
                </ul>
            </div>
        </body>
    </html>
    """
    extractor = HTMLTextExtractor()
    extractor.feed(html)
    text = extractor.get_text()
    
    assert "Heading 1" in text
    assert "Paragraph text here." in text
    assert "Bold" in text
    assert "Item 1" in text
    assert "Item 2" in text
    assert "Ignored" not in text
    assert "alert" not in text


@pytest.mark.asyncio
async def test_web_fetch_tool_success() -> None:
    tool = WebFetchTool()
    
    html_content = "<html><body><h1>Welcome to PTIT</h1><p>Test</p></body></html>"
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = html_content
    mock_response.headers = {"content-type": "text/html"}
    mock_response.raise_for_status = MagicMock()
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_class:
        mock_class.return_value.__aenter__.return_value = mock_client
        
        result = await tool.execute(url="https://ptit.edu.vn/")
        
        assert "Welcome to PTIT" in result
        assert "Test" in result
        mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_web_fetch_tool_http_error() -> None:
    tool = WebFetchTool()
    
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 404
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=mock_response
    )
    
    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    
    with patch("httpx.AsyncClient") as mock_class:
        mock_class.return_value.__aenter__.return_value = mock_client
        
        result = await tool.execute(url="https://ptit.edu.vn/notfound")
        
        assert "Error: HTTP 404" in result


@pytest.mark.asyncio
async def test_web_fetch_tool_invalid_url() -> None:
    tool = WebFetchTool()
    result = await tool.execute(url="invalid-url")
    assert "Error: Invalid URL" in result

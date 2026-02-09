"""URL content loader for knowledge table embedding."""

from typing import Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

# Maximum content size: 50MB
MAX_CONTENT_SIZE = 50 * 1024 * 1024


async def load_url_content(url: str, timeout: int = 30) -> Tuple[str, str]:
    """
    Fetch and extract text content from URL.

    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds

    Returns:
        Tuple of (content_text, filename_identifier)

    Raises:
        httpx.HTTPError: If the URL cannot be fetched
        ValueError: If URL is invalid or content exceeds size limit
    """
    try:
        async with httpx.AsyncClient(limits=httpx.Limits(max_connections=1)) as client:
            response = await client.get(
                url,
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "JamAIBase/1.0"},
            )
            response.raise_for_status()

            # Check Content-Length header before full download
            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    size = int(content_length)
                    if size > MAX_CONTENT_SIZE:
                        raise ValueError(
                            f"Content size ({size} bytes) exceeds maximum allowed ({MAX_CONTENT_SIZE} bytes)"
                        )
                except ValueError:
                    pass  # If conversion fails, proceed with download

    except httpx.InvalidURL as e:
        raise ValueError(f"Invalid URL: {url}") from e
    except httpx.HTTPError as e:
        raise ValueError(f"Failed to fetch URL: {str(e)}") from e

    soup = BeautifulSoup(response.content, "html.parser")

    # Remove noise
    for tag in soup(["script", "style", "meta", "link"]):
        tag.decompose()

    content = soup.get_text(separator="\n", strip=True)

    # Validate extracted content is not empty
    if not content or len(content.strip()) < 10:
        raise ValueError("URL content is empty or too short")

    # Use domain as filename-like identifier
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    filename = f"{domain}_content.txt"

    return content, filename

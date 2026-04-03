"""drawio/url_utils.py - Shareable URL generation.
Windows-safe: ASCII only.
"""

import base64
import logging
import zlib

logger = logging.getLogger(__name__)


def get_shareable_url(xml_content, github_raw_url=None):
    """Generate a draw.io shareable URL.

    Args:
        xml_content: draw.io XML string.
        github_raw_url: Optional raw GitHub URL where the .drawio file
            will be hosted (e.g. raw.githubusercontent.com/org/repo/main/path.drawio).
            When provided, generates a cleaner ?url= link.

    Returns:
        Shareable app.diagrams.net URL string.
    """
    if github_raw_url:
        import urllib.parse

        return "https://app.diagrams.net/?url=" + urllib.parse.quote(github_raw_url, safe="")
    return _encode_drawio_url(xml_content)


def _encode_drawio_url(xml):
    """Encode XML as draw.io URL fragment (#H format).

    Encoding steps (matching draw.io JavaScript):
        1. URL-encode the XML string
        2. Raw deflate compress (zlib with wbits=-15 equivalent)
        3. Base64 encode
        4. URL-encode the base64 string
        5. Prefix with https://app.diagrams.net/#H

    Returns:
        Full shareable URL string.
    """
    try:
        import urllib.parse

        url_encoded = urllib.parse.quote(xml, safe="")
        # zlib compress then strip 2-byte header + 4-byte checksum = raw deflate
        compressed = zlib.compress(url_encoded.encode("utf-8"))
        raw_deflate = compressed[2:-4]
        b64 = base64.b64encode(raw_deflate).decode("ascii")
        return "https://app.diagrams.net/#H" + urllib.parse.quote(b64, safe="")
    except Exception as exc:
        logger.warning("Could not encode draw.io URL: %s", exc)
        return "https://app.diagrams.net/"

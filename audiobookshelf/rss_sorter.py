"""Audiobookshelf RSS chronological-order proxy.

Use RSS_UPSTREAM_ORIGIN for the internal Audiobookshelf service.
Only /feed/<UUID> requests are proxied; arbitrary upstream URLs are forbidden.
"""
import email.utils
import os
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

ORIGIN = os.environ.get("RSS_UPSTREAM_ORIGIN", "http://audiobookshelf.audiobookshelf.svc.cluster.local")
ITEM_PATH = re.compile(r"^/feed/[0-9a-fA-F-]{36}/?$")
MAX_BYTES = 16 * 1024 * 1024


def publication_date(item):
    raw = item.findtext("pubDate")
    if not raw:
        return None
    try:
        value = email.utils.parsedate_to_datetime(raw)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, IndexError):
        return None


def sort_feed(data):
    """Stable newest-first sorting; undated episodes remain at the end."""
    root = ET.fromstring(data)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("RSS channel missing")
    items = channel.findall("item")
    # Python's sort is stable, preserving feed order for ties and undated items.
    items.sort(key=lambda item: publication_date(item) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if items:
        # Preserve the position of the first item relative to non-item channel metadata.
        first_index = list(channel).index(channel.find("item"))
        for item in items:
            channel.remove(item)
        for index, item in enumerate(items):
            channel.insert(first_index + index, item)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if not ITEM_PATH.fullmatch(path):
            self.send_error(404)
            return
        try:
            request = urllib.request.Request(ORIGIN.rstrip("/") + path, headers={"Accept": "application/rss+xml"})
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status != 200:
                    raise ValueError("Unexpected upstream response")
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("RSS feed too large")
            output = sort_feed(raw)
        except (urllib.error.URLError, TimeoutError, ValueError, ET.ParseError) as exc:
            self.log_error("Upstream RSS error: %s", type(exc).__name__)
            self.send_error(502, "Upstream RSS unavailable")
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml; charset=utf-8")
        self.send_header("Cache-Control", "private, max-age=180")
        self.send_header("Content-Length", str(len(output)))
        self.end_headers()
        self.wfile.write(output)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()

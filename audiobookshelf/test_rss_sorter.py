"""Podsort regression tests. Install FastAPI and httpx to run API tests."""
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

from rss_sorter import app, sort_feed, SLUG


class FeedSortingTests(unittest.TestCase):
    def test_more_than_fifty_valid_dates(self):
        items = "".join(
            f"<item><guid>{i}</guid><pubDate>{(i % 28) + 1:02d} Jan 2026 00:00:00 GMT</pubDate>"
            f"<enclosure url='https://example.test/{i}.wav'/></item>" for i in range(60)
        )
        root = ET.fromstring(sort_feed(f"<rss><channel>{items}</channel></rss>".encode()))
        self.assertEqual(len(root.findall("./channel/item")), 60)
        dates = [i.findtext("pubDate") for i in root.findall("./channel/item")]
        self.assertEqual(dates[0], "28 Jan 2026 00:00:00 GMT")
        self.assertEqual(dates[-1], "01 Jan 2026 00:00:00 GMT")
        self.assertEqual(len({i.find("enclosure").get("url") for i in root.findall("./channel/item")}), 60)

    def test_custom_slug(self):
        self.assertTrue(SLUG.fullmatch("my-podcast_2026"))
        self.assertFalse(SLUG.fullmatch("../api/users"))

    def test_homepage_discovery(self):
        from fastapi.testclient import TestClient
        with patch("rss_sorter.discover_feeds", return_value=[{"slug": "my-podcast", "title": "<Podcast>"}]):
            response = TestClient(app).get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/feed/my-podcast", response.text)
        self.assertIn("&lt;Podcast&gt;", response.text)

    def test_feed_endpoint(self):
        from fastapi.testclient import TestClient
        xml = b"<rss><channel><item><guid>old</guid><pubDate>01 Jan 2026 00:00:00 GMT</pubDate></item><item><guid>new</guid><pubDate>02 Jan 2026 00:00:00 GMT</pubDate></item></channel></rss>"
        with patch("rss_sorter.fetch", return_value=xml):
            response = TestClient(app).get("/feed/my-podcast")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([i.findtext("guid") for i in ET.fromstring(response.content).findall("./channel/item")], ["new", "old"])


if __name__ == "__main__":
    unittest.main()

"""Regression tests: run with python -m unittest discover -s audiobookshelf -p 'test_*.py'."""
import unittest
import xml.etree.ElementTree as ET

from rss_sorter import sort_feed


class FeedSortingTests(unittest.TestCase):
    def test_newest_first_and_stable_ties(self):
        dates = ["Fri, 04 Jul 2025 00:00:00 GMT", "Wed, 14 Oct 2026 08:00:00 GMT", "Fri, 04 Jul 2025 00:00:00 GMT", "Tue, 13 Oct 2026 09:00:00 GMT"]
        items = "".join(f"<item><guid>{i}</guid><pubDate>{date}</pubDate><enclosure url='https://example.test/{i}.wav'/></item>" for i, date in enumerate(dates))
        root = ET.fromstring(sort_feed(f"<rss><channel><title>Podcast</title>{items}</channel></rss>".encode()))
        self.assertEqual([i.findtext("guid") for i in root.findall("./channel/item")], ["1", "3", "0", "2"])
        self.assertEqual([i.find("enclosure").get("url") for i in root.findall("./channel/item")], ["https://example.test/1.wav", "https://example.test/3.wav", "https://example.test/0.wav", "https://example.test/2.wav"])

    def test_more_than_fifty(self):
        items = "".join(f"<item><guid>{i}</guid><pubDate>{i+1:02d} Jan 2026 00:00:00 GMT</pubDate></item>" for i in range(60))
        # Invalid dates sort to the end, without dropping any items.
        root = ET.fromstring(sort_feed(f"<rss><channel>{items}</channel></rss>".encode()))
        self.assertEqual(len(root.findall("./channel/item")), 60)

    def test_undated_last(self):
        xml = b"<rss><channel><item><guid>missing</guid></item><item><guid>dated</guid><pubDate>Wed, 14 Oct 2026 00:00:00 GMT</pubDate></item></channel></rss>"
        root = ET.fromstring(sort_feed(xml))
        self.assertEqual([i.findtext("guid") for i in root.findall("./channel/item")], ["dated", "missing"])


if __name__ == "__main__":
    unittest.main()

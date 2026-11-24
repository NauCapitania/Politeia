"""Public RSS feeds of news outlets. Stores headline, link, date and a short excerpt; never the full article."""

import html
import re
from email.utils import parsedate_to_datetime

from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from connectors.base.http import SourceAccessError
from connectors.base.protocol import Batch, Connector, Issue, NewsRecord, RawResponse, Ref
from connectors.news.politics import POLITICS_TOPIC, is_political_news, topics_for

EXCERPT_CHARS = 320
TAG_RE = re.compile(r"<[^>]+>")


def _text(el, tag: str) -> str | None:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _categories(item) -> tuple[str, ...]:
    return tuple(c.text for c in item.findall("category") if c.text)


def rss_categories(payload: str | None) -> dict[str, tuple[str, ...]]:
    if not payload:
        return {}
    try:
        root = ElementTree.fromstring(payload)
    except (DefusedXmlException, ElementTree.ParseError, ValueError):
        return {}
    return {link: _categories(item) for item in root.iter("item") if (link := _text(item, "link"))}


def clean_excerpt(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", value))).strip()
    if len(text) <= EXCERPT_CHARS:
        return text or None
    return text[:EXCERPT_CHARS].rsplit(" ", 1)[0] + "…"


class NewsConnector(Connector):
    id = "news-rss"
    version = "0.1.0"
    scopes = ("news",)

    def fetch(self, scope: str) -> Batch:
        if scope != "news":
            raise ValueError(f"unknown scope {scope}")
        batch = Batch(scope=scope)
        for feed in self.config.get("feeds", []):
            try:
                resp = self.client.get(feed["url"], accept="application/rss+xml, application/xml;q=0.9, */*;q=0.5")
                batch.add_raw(RawResponse(resp, "rss_feed", feed["id"]))
            except SourceAccessError as exc:
                batch.issues.append(Issue("warning", "feed_unavailable", str(exc), {"feed": feed["id"]}))
        return batch

    def normalize(self, batch: Batch) -> Batch:
        feeds = {f["id"]: f for f in self.config.get("feeds", [])}
        seen: set[str] = set()
        for idx, raw in enumerate(batch.raw):
            feed = feeds.get(raw.source_record_key or "", {"id": raw.source_record_key, "outlet": "?"})
            try:
                root = ElementTree.fromstring(raw.response.content)
            except ElementTree.ParseError as exc:
                batch.issues.append(Issue("warning", "malformed_feed", str(exc), {"feed": feed["id"]}, raw=idx))
                continue
            for i, item in enumerate(root.iter("item")):
                title, link = _text(item, "title"), _text(item, "link")
                if not title or not link or link in seen:
                    continue
                outlet = feed["outlet"]
                aggregated = feed.get("aggregator")
                if aggregated:
                    outlet = _text(item, "source") or outlet
                    title = re.sub(rf"\s+-\s+{re.escape(outlet)}$", "", title)
                title = html.unescape(title)
                excerpt = None if aggregated else clean_excerpt(_text(item, "description"))
                topics = topics_for(f"{title} {excerpt or ''}")
                categories = _categories(item)
                if not is_political_news(link, title, excerpt, feed["id"], topics=topics, categories=categories):
                    continue
                seen.add(link)
                if not is_political_news(link, title, excerpt, feed["id"], topics=topics):
                    topics.append(POLITICS_TOPIC)
                published = None
                if pub := _text(item, "pubDate"):
                    try:
                        published = parsedate_to_datetime(pub)
                    except (TypeError, ValueError):
                        published = None
                batch.news.append(NewsRecord(
                    url=link, title=title, outlet=outlet, feed=feed["id"],
                    ref=Ref(idx, f"$.rss.channel.item[{i}]"), excerpt=excerpt, published_at=published,
                    topics=topics,
                ))
        return batch

    def validate(self, batch: Batch) -> Batch:
        if batch.raw and not batch.news:
            batch.issues.append(Issue("warning", "no_items", "feeds returned no items"))
        return batch

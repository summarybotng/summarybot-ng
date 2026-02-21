"""
RSS 2.0 and Atom 1.0 feed generator for Discord summaries.
"""

import hashlib
from datetime import datetime
from typing import List, Optional
from xml.etree.ElementTree import Element, SubElement, tostring, register_namespace
from xml.dom import minidom

from ..models.summary import SummaryResult
from ..models.feed import FeedConfig, FeedType

# Register namespace prefixes to avoid duplicate/ns0 declarations
register_namespace('atom', 'http://www.w3.org/2005/Atom')
register_namespace('dc', 'http://purl.org/dc/elements/1.1/')


class FeedGenerator:
    """Generates RSS 2.0 and Atom 1.0 feeds from summaries."""

    def __init__(self, base_url: str, dashboard_url: Optional[str] = None):
        """Initialize feed generator.

        Args:
            base_url: Base URL for the API (e.g., https://summarybot-ng.fly.dev)
            dashboard_url: Base URL for the dashboard (e.g., https://summarybot-ng.fly.dev)
        """
        self.base_url = base_url.rstrip('/')
        self.dashboard_url = (dashboard_url or base_url).rstrip('/')

    def generate(
        self,
        summaries: List[SummaryResult],
        feed_config: FeedConfig,
        guild_name: str,
        channel_name: Optional[str] = None
    ) -> str:
        """Generate feed content based on feed type.

        Args:
            summaries: List of summaries to include in feed
            feed_config: Feed configuration
            guild_name: Name of the Discord guild
            channel_name: Name of the specific channel (if channel-specific feed)

        Returns:
            XML string of the feed
        """
        if feed_config.feed_type == FeedType.ATOM:
            return self.generate_atom(summaries, feed_config, guild_name, channel_name)
        return self.generate_rss(summaries, feed_config, guild_name, channel_name)

    def generate_rss(
        self,
        summaries: List[SummaryResult],
        feed_config: FeedConfig,
        guild_name: str,
        channel_name: Optional[str] = None
    ) -> str:
        """Generate RSS 2.0 XML feed.

        Args:
            summaries: List of summaries to include
            feed_config: Feed configuration
            guild_name: Name of the Discord guild
            channel_name: Name of the channel (if channel-specific)

        Returns:
            RSS 2.0 XML string
        """
        # Build feed title and description
        title = feed_config.title or self._default_title(guild_name, channel_name)
        description = feed_config.description or self._default_description(guild_name, channel_name)

        # Create root element
        # Note: namespace declarations are added automatically via register_namespace
        # when we use Clark notation ({namespace}element) for namespaced elements
        rss = Element('rss', {'version': '2.0'})

        channel = SubElement(rss, 'channel')

        # Channel metadata
        SubElement(channel, 'title').text = title
        SubElement(channel, 'link').text = self._get_dashboard_link(feed_config)
        SubElement(channel, 'description').text = description
        SubElement(channel, 'language').text = 'en-us'
        SubElement(channel, 'generator').text = 'SummaryBot-NG'

        # Last build date
        if summaries:
            last_build = max(s.created_at for s in summaries)
            SubElement(channel, 'lastBuildDate').text = self._format_rss_date(last_build)

        # Self-reference link for Atom compatibility
        atom_link = SubElement(channel, '{http://www.w3.org/2005/Atom}link', {
            'href': feed_config.get_feed_url(self.base_url),
            'rel': 'self',
            'type': 'application/rss+xml'
        })

        # Add items
        for summary in summaries[:feed_config.max_items]:
            self._add_rss_item(channel, summary, feed_config, channel_name)

        return self._prettify_xml(rss)

    def generate_atom(
        self,
        summaries: List[SummaryResult],
        feed_config: FeedConfig,
        guild_name: str,
        channel_name: Optional[str] = None
    ) -> str:
        """Generate Atom 1.0 XML feed.

        Args:
            summaries: List of summaries to include
            feed_config: Feed configuration
            guild_name: Name of the Discord guild
            channel_name: Name of the channel (if channel-specific)

        Returns:
            Atom 1.0 XML string
        """
        # Build feed title and description
        title = feed_config.title or self._default_title(guild_name, channel_name)
        subtitle = feed_config.description or self._default_description(guild_name, channel_name)

        # Create root element
        feed = Element('feed', {'xmlns': 'http://www.w3.org/2005/Atom'})

        # Feed metadata
        SubElement(feed, 'title').text = title
        SubElement(feed, 'subtitle').text = subtitle
        SubElement(feed, 'id').text = f"urn:summarybot:feed:{feed_config.id}"
        SubElement(feed, 'generator').text = 'SummaryBot-NG'

        # Links
        SubElement(feed, 'link', {
            'href': self._get_dashboard_link(feed_config),
            'rel': 'alternate',
            'type': 'text/html'
        })
        SubElement(feed, 'link', {
            'href': feed_config.get_feed_url(self.base_url),
            'rel': 'self',
            'type': 'application/atom+xml'
        })

        # Updated timestamp
        if summaries:
            updated = max(s.created_at for s in summaries)
            SubElement(feed, 'updated').text = self._format_atom_date(updated)
        else:
            SubElement(feed, 'updated').text = self._format_atom_date(datetime.utcnow())

        # Author
        author = SubElement(feed, 'author')
        SubElement(author, 'name').text = 'SummaryBot'

        # Add entries
        for summary in summaries[:feed_config.max_items]:
            self._add_atom_entry(feed, summary, feed_config, channel_name)

        return self._prettify_xml(feed)

    def _add_rss_item(
        self,
        channel: Element,
        summary: SummaryResult,
        feed_config: FeedConfig,
        channel_name: Optional[str]
    ) -> None:
        """Add an RSS item element for a summary."""
        item = SubElement(channel, 'item')

        # Title
        item_title = self._format_item_title(summary, channel_name)
        SubElement(item, 'title').text = item_title

        # Link to dashboard
        link = f"{self.dashboard_url}/guilds/{summary.guild_id}/summaries/{summary.id}"
        SubElement(item, 'link').text = link

        # GUID (permanent identifier)
        guid = SubElement(item, 'guid', {'isPermaLink': 'false'})
        guid.text = f"summarybot:summary:{summary.id}"

        # Publication date
        SubElement(item, 'pubDate').text = self._format_rss_date(summary.created_at)

        # Description/content
        content = self._format_content(summary, feed_config.include_full_content)
        SubElement(item, 'description').text = content

        # Category
        SubElement(item, 'category').text = 'Discord Summary'

        # Dublin Core creator (channel name)
        if channel_name or (summary.context and summary.context.channel_name):
            creator_name = channel_name or summary.context.channel_name
            dc_creator = SubElement(item, '{http://purl.org/dc/elements/1.1/}creator')
            dc_creator.text = f"#{creator_name}"

    def _add_atom_entry(
        self,
        feed: Element,
        summary: SummaryResult,
        feed_config: FeedConfig,
        channel_name: Optional[str]
    ) -> None:
        """Add an Atom entry element for a summary."""
        entry = SubElement(feed, 'entry')

        # ID (permanent identifier)
        SubElement(entry, 'id').text = f"urn:summarybot:summary:{summary.id}"

        # Title
        item_title = self._format_item_title(summary, channel_name)
        SubElement(entry, 'title').text = item_title

        # Link
        link = f"{self.dashboard_url}/guilds/{summary.guild_id}/summaries/{summary.id}"
        SubElement(entry, 'link', {'href': link, 'rel': 'alternate', 'type': 'text/html'})

        # Timestamps
        SubElement(entry, 'updated').text = self._format_atom_date(summary.created_at)
        SubElement(entry, 'published').text = self._format_atom_date(summary.created_at)

        # Author
        author = SubElement(entry, 'author')
        SubElement(author, 'name').text = 'SummaryBot'

        # Content
        content = self._format_content(summary, feed_config.include_full_content)
        content_elem = SubElement(entry, 'content', {'type': 'html'})
        content_elem.text = content

        # Summary (short excerpt)
        summary_text = summary.summary_text[:200] + '...' if len(summary.summary_text) > 200 else summary.summary_text
        SubElement(entry, 'summary').text = summary_text

        # Category
        SubElement(entry, 'category', {'term': 'discord-summary', 'label': 'Discord Summary'})

    def _format_content(self, summary: SummaryResult, full_content: bool) -> str:
        """Format summary content for feed entry."""
        if not full_content:
            # Return excerpt only
            excerpt = summary.summary_text[:500]
            if len(summary.summary_text) > 500:
                excerpt += '...'
            return f"<p>{self._escape_html(excerpt)}</p>"

        # Build full HTML content
        parts = []

        # Main summary
        parts.append(f"<h3>Summary</h3>")
        parts.append(f"<p>{self._escape_html(summary.summary_text)}</p>")

        # Key points
        if summary.key_points:
            parts.append("<h4>Key Points</h4><ul>")
            for point in summary.key_points[:10]:
                parts.append(f"<li>{self._escape_html(point)}</li>")
            parts.append("</ul>")

        # Action items
        if summary.action_items:
            parts.append("<h4>Action Items</h4><ul>")
            for item in summary.action_items[:10]:
                assignee = f" ({item.assignee})" if item.assignee else ""
                parts.append(f"<li>{self._escape_html(item.description)}{assignee}</li>")
            parts.append("</ul>")

        # Metadata
        parts.append("<hr/>")
        parts.append(f"<p><small>Messages: {summary.message_count} | ")
        if summary.context:
            parts.append(f"Participants: {summary.context.total_participants} | ")
        parts.append(f"Generated: {summary.created_at.strftime('%Y-%m-%d %H:%M UTC')}</small></p>")

        return ''.join(parts)

    def _format_item_title(self, summary: SummaryResult, channel_name: Optional[str]) -> str:
        """Format the title for a feed item."""
        name = channel_name
        if not name and summary.context:
            name = summary.context.channel_name
        if not name:
            name = "channel"

        date_str = summary.created_at.strftime('%b %d, %Y')
        return f"Summary: #{name} - {date_str}"

    def _default_title(self, guild_name: str, channel_name: Optional[str]) -> str:
        """Generate default feed title."""
        if channel_name:
            return f"{guild_name} - #{channel_name} Summaries"
        return f"{guild_name} Summaries"

    def _default_description(self, guild_name: str, channel_name: Optional[str]) -> str:
        """Generate default feed description."""
        if channel_name:
            return f"AI-generated summaries from #{channel_name} in {guild_name}"
        return f"AI-generated summaries from {guild_name} Discord server"

    def _get_dashboard_link(self, feed_config: FeedConfig) -> str:
        """Get link to dashboard for this feed's guild."""
        return f"{self.dashboard_url}/guilds/{feed_config.guild_id}"

    def _format_rss_date(self, dt: datetime) -> str:
        """Format datetime for RSS 2.0 (RFC 822)."""
        return dt.strftime('%a, %d %b %Y %H:%M:%S +0000')

    def _format_atom_date(self, dt: datetime) -> str:
        """Format datetime for Atom 1.0 (ISO 8601)."""
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    def _escape_html(self, text: str) -> str:
        """Escape HTML special characters."""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def _prettify_xml(self, elem: Element) -> str:
        """Convert Element to pretty-printed XML string."""
        rough_string = tostring(elem, encoding='unicode')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent="  ", encoding=None)

    @staticmethod
    def generate_etag(feed_id: str, summaries: List[SummaryResult]) -> str:
        """Generate ETag for caching.

        Args:
            feed_id: The feed identifier
            summaries: List of summaries in the feed

        Returns:
            ETag string (without quotes)
        """
        content = f"{feed_id}:{len(summaries)}"
        if summaries:
            latest = max(s.created_at for s in summaries)
            content += f":{latest.isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()

    @staticmethod
    def get_last_modified(summaries: List[SummaryResult]) -> datetime:
        """Get Last-Modified timestamp from summaries.

        Args:
            summaries: List of summaries

        Returns:
            Datetime of the most recent summary, or current time if empty
        """
        if summaries:
            return max(s.created_at for s in summaries)
        return datetime.utcnow()

"""
Message processing models for Discord and WhatsApp messages.

Supports multi-source message handling per ADR-002/003.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import re

from .base import BaseModel


class SourceType(str, Enum):
    """Data source types for messages (ADR-002)."""
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"  # Future
    TELEGRAM = "telegram"  # Future


class MessageType(Enum):
    """Message types (Discord numeric + WhatsApp string types)."""
    # Discord types (numeric)
    DEFAULT = 0
    RECIPIENT_ADD = 1
    RECIPIENT_REMOVE = 2
    CALL = 3
    CHANNEL_NAME_CHANGE = 4
    CHANNEL_ICON_CHANGE = 5
    PINS_ADD = 6
    GUILD_MEMBER_JOIN = 7
    REPLY = 19
    SLASH_COMMAND = 20
    THREAD_STARTER_MESSAGE = 21
    # WhatsApp types (ADR-002) - use high numbers to avoid collision
    WHATSAPP_TEXT = 100
    WHATSAPP_MEDIA = 101
    WHATSAPP_VOICE = 102
    WHATSAPP_FORWARDED = 103
    WHATSAPP_LOCATION = 104
    WHATSAPP_CONTACT = 105
    WHATSAPP_POLL = 106


class AttachmentType(Enum):
    """Attachment types."""
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


@dataclass
class CodeBlock(BaseModel):
    """Represents a code block in a message."""
    language: Optional[str]
    code: str
    start_line: int
    end_line: int
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lang = self.language or ""
        return f"```{lang}\n{self.code}\n```"


@dataclass
class MessageMention(BaseModel):
    """Represents a mention in a message."""
    type: str  # "user", "role", "channel", "everyone", "here"
    id: Optional[str]  # User/role/channel ID
    name: str  # Display name
    raw: str  # Original mention text


@dataclass
class MessageReference(BaseModel):
    """Represents a reference to another message (reply/quote)."""
    message_id: str
    channel_id: str
    guild_id: Optional[str]
    author_name: str
    content_preview: str  # First 100 chars of referenced message
    
    def to_markdown(self) -> str:
        """Convert to markdown format."""
        return f"> **{self.author_name}**: {self.content_preview}"


@dataclass 
class AttachmentInfo(BaseModel):
    """Information about a message attachment."""
    id: str
    filename: str
    size: int
    url: str
    proxy_url: str
    type: AttachmentType
    content_type: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    description: Optional[str] = None
    
    @classmethod
    def from_discord_attachment(cls, attachment) -> 'AttachmentInfo':
        """Create from Discord attachment object."""
        # Determine attachment type from content type or filename
        attachment_type = AttachmentType.UNKNOWN
        content_type = getattr(attachment, 'content_type', None)
        
        if content_type:
            if content_type.startswith('image/'):
                attachment_type = AttachmentType.IMAGE
            elif content_type.startswith('video/'):
                attachment_type = AttachmentType.VIDEO
            elif content_type.startswith('audio/'):
                attachment_type = AttachmentType.AUDIO
            else:
                attachment_type = AttachmentType.DOCUMENT
        
        return cls(
            id=str(attachment.id),
            filename=attachment.filename,
            size=attachment.size,
            url=attachment.url,
            proxy_url=attachment.proxy_url,
            type=attachment_type,
            content_type=content_type,
            width=getattr(attachment, 'width', None),
            height=getattr(attachment, 'height', None),
            description=getattr(attachment, 'description', None)
        )
    
    def get_summary_text(self) -> str:
        """Get a summary text for the attachment."""
        type_emoji = {
            AttachmentType.IMAGE: "🖼️",
            AttachmentType.VIDEO: "🎥",
            AttachmentType.AUDIO: "🔊",
            AttachmentType.DOCUMENT: "📄",
            AttachmentType.UNKNOWN: "📎"
        }
        
        size_mb = self.size / (1024 * 1024)
        size_text = f"{size_mb:.1f}MB" if size_mb >= 1 else f"{self.size // 1024}KB"
        
        return f"{type_emoji[self.type]} {self.filename} ({size_text})"


@dataclass
class ThreadInfo(BaseModel):
    """Information about thread context."""
    thread_id: str
    thread_name: str
    parent_channel_id: str
    starter_message_id: Optional[str]
    is_archived: bool = False
    participant_count: int = 0
    message_count: int = 0
    
    def to_summary_text(self) -> str:
        """Get summary text for thread info."""
        status = "🗃️ Archived" if self.is_archived else "💬 Active"
        return f"Thread: {self.thread_name} ({status}, {self.message_count} messages, {self.participant_count} participants)"


@dataclass
class ProcessedMessage(BaseModel):
    """Processed message with cleaned and extracted content.

    Supports both Discord and WhatsApp sources per ADR-002.
    """
    id: str
    author_name: str
    author_id: str
    content: str
    timestamp: datetime
    message_type: MessageType = MessageType.DEFAULT
    thread_info: Optional[ThreadInfo] = None
    attachments: List[AttachmentInfo] = field(default_factory=list)
    references: List[MessageReference] = field(default_factory=list)
    mentions: List[MessageMention] = field(default_factory=list)
    code_blocks: List[CodeBlock] = field(default_factory=list)
    embeds_count: int = 0
    reactions_count: int = 0
    is_edited: bool = False
    is_pinned: bool = False
    # Channel context for multi-channel summaries
    channel_id: Optional[str] = None
    channel_name: Optional[str] = None
    # ADR-002: Multi-source support
    source_type: SourceType = SourceType.DISCORD
    # WhatsApp-specific fields (ADR-002)
    is_forwarded: bool = False
    is_deleted: bool = False
    reply_to_id: Optional[str] = None
    phone_number: Optional[str] = None  # WhatsApp sender phone (anonymized in prompts)
    
    def clean_content(self) -> str:
        """Get cleaned content without mentions, formatting, etc.

        Source-aware cleaning per ADR-002.
        """
        if not self.content:
            return ""

        if self.source_type == SourceType.WHATSAPP:
            return self._clean_whatsapp_content()
        return self._clean_discord_content()

    def _clean_discord_content(self) -> str:
        """Clean Discord-specific formatting."""
        content = self.content

        # Remove Discord mentions (keep the name part)
        content = re.sub(r'<@!?(\d+)>', r'@user', content)
        content = re.sub(r'<@&(\d+)>', r'@role', content)
        content = re.sub(r'<#(\d+)>', r'#channel', content)

        # Remove custom emojis but keep the name
        content = re.sub(r'<a?:[a-zA-Z0-9_]+:(\d+)>', r':emoji:', content)

        # Clean up extra whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        return content

    def _clean_whatsapp_content(self) -> str:
        """Clean WhatsApp-specific formatting (ADR-002)."""
        content = self.content

        # Remove WhatsApp bold markers (*text* -> text) but preserve content
        content = re.sub(r'\*([^*]+)\*', r'\1', content)
        # Remove WhatsApp italic markers (_text_ -> text)
        content = re.sub(r'_([^_]+)_', r'\1', content)
        # Remove WhatsApp strikethrough (~text~ -> text)
        content = re.sub(r'~([^~]+)~', r'\1', content)

        # Remove zero-width characters common in WhatsApp
        content = content.replace('\u200e', '').replace('\u200f', '')
        content = content.replace('\u200b', '')  # Zero-width space

        # Clean up extra whitespace
        content = re.sub(r'\s+', ' ', content).strip()

        return content
    
    def extract_code_blocks(self) -> List[CodeBlock]:
        """Extract code blocks from message content."""
        if not self.content:
            return []
        
        code_blocks = []
        lines = self.content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            # Look for code block start
            if line.startswith('```'):
                language = line[3:].strip() or None
                start_line = i
                code_lines = []
                
                i += 1
                while i < len(lines) and not lines[i].startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                
                if i < len(lines):  # Found closing ```
                    code_blocks.append(CodeBlock(
                        language=language,
                        code='\n'.join(code_lines),
                        start_line=start_line,
                        end_line=i
                    ))
            
            i += 1
        
        return code_blocks
    
    def get_mentions(self) -> List[str]:
        """Extract mention IDs from content."""
        if not self.content:
            return []
        
        mentions = []
        
        # User mentions
        user_mentions = re.findall(r'<@!?(\d+)>', self.content)
        mentions.extend(user_mentions)
        
        # Role mentions  
        role_mentions = re.findall(r'<@&(\d+)>', self.content)
        mentions.extend(role_mentions)
        
        # Channel mentions
        channel_mentions = re.findall(r'<#(\d+)>', self.content)
        mentions.extend(channel_mentions)
        
        return list(set(mentions))  # Remove duplicates
    
    def has_substantial_content(self) -> bool:
        """Check if message has substantial content worth summarizing."""
        if not self.content:
            return len(self.attachments) > 0  # Attachments count as content
        
        cleaned = self.clean_content()
        
        # Too short
        if len(cleaned) < 10:
            return False
        
        # Only mentions/emojis
        if re.match(r'^[@#:][^a-zA-Z]*$', cleaned):
            return False
        
        # Has meaningful text
        word_count = len([w for w in cleaned.split() if len(w) > 2])
        return word_count >= 3
    
    def get_content_summary(self, max_length: int = 100) -> str:
        """Get a summary of the message content."""
        if not self.content and not self.attachments:
            return "[Empty message]"
        
        parts = []
        
        if self.content:
            cleaned = self.clean_content()
            if len(cleaned) > max_length:
                cleaned = cleaned[:max_length] + "..."
            parts.append(cleaned)
        
        if self.attachments:
            attachment_summaries = [att.get_summary_text() for att in self.attachments]
            parts.extend(attachment_summaries)
        
        if self.code_blocks:
            parts.append(f"[{len(self.code_blocks)} code block(s)]")
        
        if self.embeds_count > 0:
            parts.append(f"[{self.embeds_count} embed(s)]")
        
        return " | ".join(parts)
    
    def to_summary_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for summarization context."""
        return {
            "author": self.author_name,
            "timestamp": self.timestamp.isoformat(),
            "content": self.clean_content(),
            "attachments": len(self.attachments),
            "code_blocks": len(self.code_blocks),
            "thread": self.thread_info.thread_name if self.thread_info else None,
            "references": len(self.references),
            "substantial": self.has_substantial_content()
        }
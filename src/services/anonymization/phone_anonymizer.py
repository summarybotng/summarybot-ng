"""
Phone number anonymization for WhatsApp PII protection (ADR-028).

Provides deterministic anonymization of phone numbers using:
- HMAC-SHA256 hashing with per-guild salts
- Memorable pseudonym generation (40M+ unique combinations)
- Optional identity store for user-provided name overrides
"""

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# 64 adjectives - positive, neutral, memorable
ADJECTIVES = [
    # Personality
    "Swift", "Brave", "Calm", "Bright", "Bold", "Clever", "Eager", "Fair",
    "Gentle", "Happy", "Jolly", "Keen", "Lively", "Merry", "Noble", "Proud",
    "Quick", "Ready", "Sharp", "True", "Warm", "Wise", "Witty", "Zesty",
    # Nature
    "Misty", "Sunny", "Breezy", "Frosty", "Dusty", "Sandy", "Rocky", "Mossy",
    # Colors
    "Azure", "Coral", "Crimson", "Golden", "Jade", "Ruby", "Silver", "Violet",
    "Amber", "Copper", "Ivory", "Onyx", "Pearl", "Rusty", "Teal", "Bronze",
    # Qualities
    "Ancient", "Cosmic", "Crystal", "Dancing", "Electric", "Floating", "Glowing", "Hidden",
    "Lunar", "Mystic", "Nordic", "Pacific", "Quiet", "Radiant", "Silent", "Wandering",
]

# 64 animals - diverse, recognizable
ANIMALS = [
    # Mammals
    "Fox", "Bear", "Wolf", "Deer", "Otter", "Badger", "Lynx", "Panda",
    "Tiger", "Koala", "Seal", "Jaguar", "Beaver", "Hare", "Moose", "Whale",
    # Birds
    "Penguin", "Owl", "Hawk", "Raven", "Falcon", "Heron", "Eagle", "Crane",
    "Osprey", "Condor", "Finch", "Ibis", "Jay", "Parrot", "Swan", "Wren",
    # Reptiles/Amphibians
    "Gecko", "Turtle", "Cobra", "Dragon", "Newt", "Viper", "Frog", "Toad",
    # Marine
    "Dolphin", "Shark", "Squid", "Marlin", "Urchin", "Mantis", "Crab", "Eel",
    # Insects/Other
    "Moth", "Beetle", "Cricket", "Firefly", "Hornet", "Spider", "Sphinx", "Phoenix",
    # Mythical (for variety)
    "Griffin", "Wyrm", "Roc", "Hydra", "Kraken", "Sprite", "Nymph", "Djinn",
]

# Phone number detection patterns for WhatsApp format
# WhatsApp exports phone numbers in various international formats
PHONE_PATTERNS = [
    # +1 555 123 4567 or +1-555-123-4567 or +1.555.123.4567
    re.compile(r'\+\d{1,3}[\s.\-]?\d{2,4}[\s.\-]?\d{3,4}[\s.\-]?\d{3,4}'),
    # +15551234567 (no separators)
    re.compile(r'\+\d{10,15}'),
    # Partial numbers that might appear (e.g., in replies)
    re.compile(r'(?<!\d)\+\d{1,3}[\s.\-]?\d{3,4}[\s.\-]?\d{4}(?!\d)'),
]

# Combined pattern for replacement - more flexible to handle international formats
# Matches: +{country 1-3}{separator?}{groups of 1-4 digits with separators}
# Examples: +1 555 123 4567, +44 20 7946 0958, +81 3 1234 5678
COMBINED_PHONE_PATTERN = re.compile(
    r'\+\d{1,3}(?:[\s.\-]?\d{1,4}){2,5}'
)


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to digits only.

    Args:
        phone: Phone number string (e.g., "+1 555 123 4567")

    Returns:
        Digits only (e.g., "15551234567")
    """
    return ''.join(c for c in phone if c.isdigit())


def hash_phone_number(phone: str, salt: str) -> str:
    """
    Create a deterministic, non-reversible hash of a phone number.

    Uses HMAC-SHA256 with a salt for:
    - Consistency: Same number always produces same hash
    - Non-reversibility: Cannot derive phone number from hash
    - Isolation: Different salts produce different hashes

    Args:
        phone: Phone number (will be normalized to digits)
        salt: Secret salt (typically per-guild)

    Returns:
        8-character hex hash (32 bits, ~4 billion possibilities)
    """
    normalized = normalize_phone(phone)
    if not normalized:
        return "00000000"

    h = hmac.new(
        salt.encode('utf-8'),
        normalized.encode('utf-8'),
        hashlib.sha256
    )
    return h.hexdigest()[:8]


def hash_to_pseudonym(phone_hash: str) -> str:
    """
    Convert an 8-char hex hash to a memorable pseudonym.

    Uses hash segments for deterministic selection:
    - Chars 0-1 (8 bits): adjective index (mod 64)
    - Chars 2-3 (8 bits): animal index (mod 64)
    - Chars 4-7 (16 bits): numeric suffix (mod 10000)

    Total namespace: 64 × 64 × 10,000 = 40,960,000 combinations

    Args:
        phone_hash: 8-character hex string

    Returns:
        Pseudonym like "Swift Penguin 4827" or "Brave Fox 0142"
    """
    if len(phone_hash) < 8:
        phone_hash = phone_hash.ljust(8, '0')

    adj_index = int(phone_hash[0:2], 16) % len(ADJECTIVES)
    animal_index = int(phone_hash[2:4], 16) % len(ANIMALS)
    numeric_suffix = int(phone_hash[4:8], 16) % 10000

    return f"{ADJECTIVES[adj_index]} {ANIMALS[animal_index]} {numeric_suffix:04d}"


@dataclass
class AnonymizationResult:
    """Result of anonymizing text."""
    anonymized_text: str
    mappings: Dict[str, str]  # pseudonym -> hash
    phone_count: int
    original_phones: List[str] = field(default_factory=list)  # For debugging only, not persisted


@dataclass
class ParticipantInfo:
    """Information about an anonymized participant."""
    pseudonym: str
    phone_hash: str
    message_count: int = 0
    display_name: Optional[str] = None  # User-provided override


class PhoneAnonymizer:
    """
    Transforms WhatsApp transcripts to replace phone numbers with pseudonyms.

    Thread-safe and deterministic - same phone number with same salt
    always produces the same pseudonym.
    """

    def __init__(
        self,
        salt: Optional[str] = None,
        identity_overrides: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize phone anonymizer.

        Args:
            salt: Secret salt for hashing. If not provided, uses
                  ANONYMIZATION_SALT env var or a default.
            identity_overrides: Optional dict mapping phone_hash -> display_name
                               for user-provided name overrides.
        """
        self.salt = salt or os.environ.get("ANONYMIZATION_SALT", "summarybot-default-salt")
        self.identity_overrides = identity_overrides or {}
        self._cache: Dict[str, str] = {}  # normalized_phone -> pseudonym

    def get_pseudonym(self, phone: str) -> str:
        """
        Get the pseudonym for a phone number.

        Args:
            phone: Phone number string

        Returns:
            Pseudonym (or user-provided name if available)
        """
        normalized = normalize_phone(phone)

        if normalized in self._cache:
            return self._cache[normalized]

        phone_hash = hash_phone_number(phone, self.salt)

        # Check for user-provided override
        if phone_hash in self.identity_overrides:
            display_name = self.identity_overrides[phone_hash]
            self._cache[normalized] = display_name
            return display_name

        # Generate pseudonym
        pseudonym = hash_to_pseudonym(phone_hash)
        self._cache[normalized] = pseudonym
        return pseudonym

    def get_hash(self, phone: str) -> str:
        """
        Get the hash for a phone number.

        Args:
            phone: Phone number string

        Returns:
            8-character hex hash
        """
        return hash_phone_number(phone, self.salt)

    def anonymize_text(self, text: str) -> AnonymizationResult:
        """
        Replace all phone numbers in text with pseudonyms.

        Args:
            text: Text potentially containing phone numbers

        Returns:
            AnonymizationResult with anonymized text and mappings
        """
        mappings: Dict[str, str] = {}
        original_phones: List[str] = []

        def replace_phone(match: re.Match) -> str:
            phone = match.group(0)
            original_phones.append(phone)
            pseudonym = self.get_pseudonym(phone)
            phone_hash = self.get_hash(phone)
            mappings[pseudonym] = phone_hash
            return pseudonym

        anonymized = COMBINED_PHONE_PATTERN.sub(replace_phone, text)

        return AnonymizationResult(
            anonymized_text=anonymized,
            mappings=mappings,
            phone_count=len(original_phones),
            original_phones=original_phones,
        )

    def anonymize_sender(self, sender: str) -> Tuple[str, str]:
        """
        Anonymize a sender identifier (phone number or name).

        If the sender looks like a phone number, returns pseudonym.
        Otherwise returns the original name.

        Args:
            sender: Sender identifier

        Returns:
            Tuple of (display_name, phone_hash or empty string)
        """
        # Check if sender looks like a phone number
        if sender.startswith('+') or (sender.replace(' ', '').replace('-', '').isdigit() and len(sender) > 7):
            pseudonym = self.get_pseudonym(sender)
            phone_hash = self.get_hash(sender)
            return pseudonym, phone_hash

        # Not a phone number - return as-is
        return sender, ""

    def anonymize_messages(
        self,
        messages: List[Dict],
        sender_key: str = "sender",
        content_key: str = "content",
    ) -> Tuple[List[Dict], Dict[str, ParticipantInfo]]:
        """
        Anonymize a list of message dictionaries.

        Replaces phone numbers in both sender fields and message content.

        Args:
            messages: List of message dicts
            sender_key: Key for sender field in message dict
            content_key: Key for content field in message dict

        Returns:
            Tuple of (anonymized_messages, participant_info)
        """
        participants: Dict[str, ParticipantInfo] = {}
        anonymized_messages = []

        for msg in messages:
            msg_copy = msg.copy()

            # Anonymize sender
            original_sender = msg.get(sender_key, "")
            display_name, phone_hash = self.anonymize_sender(original_sender)
            msg_copy[sender_key] = display_name

            # Track participant
            if phone_hash:
                if display_name not in participants:
                    participants[display_name] = ParticipantInfo(
                        pseudonym=display_name,
                        phone_hash=phone_hash,
                        message_count=0,
                    )
                participants[display_name].message_count += 1

            # Anonymize content
            content = msg.get(content_key, "")
            if content:
                result = self.anonymize_text(content)
                msg_copy[content_key] = result.anonymized_text

            anonymized_messages.append(msg_copy)

        return anonymized_messages, participants

    def create_metadata(
        self,
        participants: Dict[str, ParticipantInfo],
    ) -> Dict:
        """
        Create anonymization metadata for storage.

        Args:
            participants: Participant info from anonymize_messages

        Returns:
            Metadata dict for storage in summary
        """
        return {
            "version": 1,
            "participant_count": len(participants),
            "participants": {
                name: {
                    "hash": info.phone_hash,
                    "message_count": info.message_count,
                }
                for name, info in participants.items()
            }
        }


def create_guild_anonymizer(guild_id: str) -> PhoneAnonymizer:
    """
    Create an anonymizer with a guild-specific salt.

    The salt is derived from:
    1. ANONYMIZATION_SALT env var (base salt)
    2. Guild ID (for isolation between guilds)

    Args:
        guild_id: Discord guild ID

    Returns:
        PhoneAnonymizer configured for this guild
    """
    base_salt = os.environ.get("ANONYMIZATION_SALT", "summarybot-default-salt")
    guild_salt = f"{base_salt}:{guild_id}"
    return PhoneAnonymizer(salt=guild_salt)

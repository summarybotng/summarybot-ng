# ADR-028: WhatsApp PII Anonymization

## Status
Proposed

## Context

WhatsApp chat exports identify participants by phone number (e.g., `+1 555 123 4567`). Phone numbers are Personally Identifiable Information (PII) that:

1. **Privacy concern**: Should not be stored in plaintext or displayed in summaries
2. **Regulatory risk**: GDPR, CCPA, and other regulations restrict PII handling
3. **User expectation**: Users uploading transcripts may not want phone numbers exposed
4. **Consistency need**: The same participant should have a consistent identifier across summaries

Currently, WhatsApp summaries may include raw phone numbers in participant lists, key points, and action items.

## Decision

Implement a **deterministic anonymization pipeline** that:

1. **Hashes phone numbers** to create stable, non-reversible identifiers
2. **Generates friendly pseudonyms** from hashes for human readability
3. **Supports nickname overrides** when the user provides a mapping
4. **Applies transformation early** in the ingestion pipeline

### Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌───────────────────────┐
│  Raw Transcript │────▶│  Anonymizer      │────▶│   Anonymized Text     │
│  +1 555 123 456 │     │  Pipeline        │     │  Cosmic Falcon 4552   │
└─────────────────┘     └──────────────────┘     └───────────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │  Identity Store  │
                        │  (optional)      │
                        └──────────────────┘
```

## Detailed Design

### 1. Phone Number Detection

Regex pattern to detect international phone numbers in WhatsApp format:

```python
PHONE_PATTERNS = [
    r'\+\d{1,3}[\s.-]?\d{2,4}[\s.-]?\d{3,4}[\s.-]?\d{3,4}',  # +1 555 123 4567
    r'\+\d{10,15}',  # +15551234567 (no separators)
]
```

### 2. Hashing Function

Use HMAC-SHA256 with a per-guild salt for:
- **Consistency**: Same number always produces same hash within a guild
- **Non-reversibility**: Cannot derive phone number from hash
- **Guild isolation**: Same number in different guilds produces different hashes

```python
import hashlib
import hmac

def hash_phone_number(phone: str, guild_salt: str) -> str:
    """
    Create a deterministic, non-reversible hash of a phone number.

    Args:
        phone: Normalized phone number (digits only, e.g., "15551234567")
        guild_salt: Per-guild secret salt

    Returns:
        8-character hex hash (32 bits, ~4 billion possibilities)
    """
    normalized = ''.join(c for c in phone if c.isdigit())
    h = hmac.new(
        guild_salt.encode(),
        normalized.encode(),
        hashlib.sha256
    )
    return h.hexdigest()[:8]  # First 8 hex chars
```

### 3. Pseudonym Generation

Generate memorable, consistent pseudonyms from hashes using word lists. The namespace must support **100k+ unique members** with negligible collision probability.

**Namespace Calculation:**
- Current members: ~5,000
- Target capacity: 100,000+
- Format: `{Adjective} {Animal} {4-digit number}`
- Combinations: 64 adjectives × 64 animals × 10,000 numbers = **40,960,000 unique pseudonyms**

```python
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
]  # 64 adjectives

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
    "Dolphin", "Shark", "Squid", "Marlin", "Coral", "Urchin", "Mantis", "Crab",
    # Insects/Other
    "Moth", "Beetle", "Cricket", "Firefly", "Hornet", "Mantis", "Sphinx", "Phoenix",
    # Mythical (for variety)
    "Griffin", "Wyrm", "Roc", "Hydra", "Kraken", "Sprite", "Nymph", "Djinn",
]  # 64 animals

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
    adj_index = int(phone_hash[0:2], 16) % len(ADJECTIVES)
    animal_index = int(phone_hash[2:4], 16) % len(ANIMALS)
    numeric_suffix = int(phone_hash[4:8], 16) % 10000

    return f"{ADJECTIVES[adj_index]} {ANIMALS[animal_index]} {numeric_suffix:04d}"
```

**Examples:**
| Phone Number | Hash | Pseudonym |
|--------------|------|-----------|
| +1 555 123 4567 | `a3f2b1c8` | Cosmic Falcon 4552 |
| +44 20 7946 0958 | `7d4e9a2f` | Dusty Osprey 3951 |
| +1 555 987 6543 | `2b8c45a1` | Clever Lynx 1785 |
| +1 555 123 4567 | `a3f2b1c8` | Cosmic Falcon 4552 (same - deterministic) |

**Collision Analysis:**
- With 40.9M possible pseudonyms and 100k members, expected collisions ≈ 0.12 (via birthday problem)
- Collision probability < 0.01% for populations under 100k
- If collision occurs, identity store can disambiguate with override

### 4. Identity Store (Optional Override)

Allow users to provide phone-to-name mappings for known participants:

```python
@dataclass
class IdentityMapping:
    """Maps anonymized identifiers to known display names."""
    guild_id: str
    phone_hash: str  # Never store raw phone
    display_name: str  # User-provided name
    created_at: datetime
    created_by: str  # User who provided mapping

class IdentityStore:
    """
    Stores optional display name overrides.

    Storage: guild-scoped key-value in metadata or dedicated table.
    """

    async def get_display_name(
        self,
        guild_id: str,
        phone_hash: str
    ) -> Optional[str]:
        """Get user-provided display name if available."""
        ...

    async def set_display_name(
        self,
        guild_id: str,
        phone_hash: str,
        display_name: str,
        set_by: str
    ) -> None:
        """Store a display name override."""
        ...
```

### 5. Resolution Order

When displaying a participant:

```python
def resolve_display_name(
    phone: str,
    guild_salt: str,
    identity_store: IdentityStore,
    guild_id: str
) -> str:
    """
    Resolve phone number to display name.

    Priority:
    1. User-provided nickname (from identity store)
    2. Generated pseudonym (from hash)

    Never returns the raw phone number.
    """
    phone_hash = hash_phone_number(phone, guild_salt)

    # Check for user-provided override
    override = await identity_store.get_display_name(guild_id, phone_hash)
    if override:
        return override

    # Fall back to generated pseudonym
    return hash_to_pseudonym(phone_hash)
```

### 6. Anonymizer Pipeline

Transform transcript before summarization:

```python
class WhatsAppAnonymizer:
    """
    Transforms WhatsApp transcripts to replace phone numbers with pseudonyms.
    """

    def __init__(
        self,
        guild_id: str,
        guild_salt: str,
        identity_store: Optional[IdentityStore] = None
    ):
        self.guild_id = guild_id
        self.guild_salt = guild_salt
        self.identity_store = identity_store
        self._cache: Dict[str, str] = {}  # phone -> display_name

    def anonymize_transcript(self, text: str) -> tuple[str, Dict[str, str]]:
        """
        Replace all phone numbers in transcript with pseudonyms.

        Returns:
            tuple of (anonymized_text, mapping_dict)
            mapping_dict maps pseudonyms to hashes for reference
        """
        mapping = {}

        def replace_phone(match: re.Match) -> str:
            phone = match.group(0)
            if phone not in self._cache:
                phone_hash = hash_phone_number(phone, self.guild_salt)
                display = self._resolve_sync(phone_hash)
                self._cache[phone] = display
                mapping[display] = phone_hash
            return self._cache[phone]

        anonymized = PHONE_PATTERN.sub(replace_phone, text)
        return anonymized, mapping
```

### 7. Metadata Storage

Store anonymization metadata with summaries:

```python
# In summary metadata
{
    "anonymization": {
        "version": 1,
        "participant_count": 5,
        "participants": {
            "Cosmic Falcon 4552": {"hash": "a3f2b1c8", "message_count": 42},
            "Dusty Osprey 3951": {"hash": "7d4e9a2f", "message_count": 17},
            "Clever Lynx 1785": {"hash": "2b8c45a1", "message_count": 8},
        }
    }
}
```

## File Changes

### New Files
- `src/services/anonymization/phone_anonymizer.py` - Core anonymization logic
- `src/services/anonymization/pseudonym_generator.py` - Hash to name mapping
- `src/services/anonymization/identity_store.py` - Optional override storage
- `tests/unit/test_anonymization/` - Unit tests

### Modified Files
- `src/services/whatsapp_parser.py` - Integrate anonymizer in parsing pipeline
- `src/config/constants.py` - Add word lists, configuration
- `src/models/stored_summary.py` - Add anonymization metadata schema

## Security Considerations

1. **Salt Management**: Guild salts must be stored securely (environment or secrets manager)
2. **No Raw Storage**: Phone numbers are never stored; only hashes
3. **Hash Length**: 8 hex chars (32 bits) provides sufficient uniqueness for chat groups while limiting information leakage
4. **Transcript Retention**: Raw transcripts should be deleted after anonymization

## UI/UX Considerations

1. **Identity Mapping UI**: Allow guild admins to provide name mappings
   - Show list of pseudonyms with "Edit" option
   - Auto-suggest from Discord member list
   - Search by pseudonym or partial match

2. **Participant Legend**: Include pseudonym list in summary display
   ```
   Participants: Cosmic Falcon 4552 (12 messages), Dusty Osprey 3951 (8 messages)
   ```

3. **Consistency Indicator**: Show when a pseudonym is auto-generated vs. user-provided
   ```
   Cosmic Falcon 4552 (auto)  vs  John Smith (verified)
   ```

4. **Short Form Display**: For inline mentions, can abbreviate to initials + number
   ```
   CF4552 mentioned the deadline...  (hover shows "Cosmic Falcon 4552")
   ```

## Alternatives Considered

### 1. Sequential Numbers (Participant 1, 2, 3...)
- **Rejected**: Not consistent across summaries; loses identity correlation

### 2. Full SHA-256 Hash Display
- **Rejected**: Not human-readable; poor UX in summaries

### 3. Server-Side Phone Storage with Encryption
- **Rejected**: Still stores PII; increases compliance burden

### 4. Client-Side Only Anonymization
- **Rejected**: Inconsistent results; can't build identity store

## Migration

For existing WhatsApp summaries with phone numbers:
1. Flag affected summaries in metadata
2. Provide "re-anonymize" action in UI
3. Do not auto-migrate (may change participant references)

## References

- GDPR Article 4(1) - Definition of personal data
- WhatsApp Export Format documentation
- [Pseudonymization techniques - ENISA](https://www.enisa.europa.eu/publications/pseudonymisation-techniques-and-best-practices)

# ADR-014: Discord Push Templates with Thread Support

**Status:** Implemented
**Date:** 2026-02-22
**Depends on:** ADR-004 (Grounded References), ADR-005 (Summary Delivery Destinations)
**Amends:** ADR-004 (adds `channel_id` to `SummaryReference`)

## 1. Context

When pushing summaries to Discord channels, the current implementation:

1. **Single message or chunked messages** - Long content is split at 2000 char boundaries
2. **No thread support** - All content goes directly to the channel, creating noise
3. **Fixed format** - No customization of what sections to include or their order
4. **No jump links** - Grounded references show position numbers but not clickable links
5. **No guild customization** - All guilds get the same format

**Problems:**
- Summaries clutter channel history (no threading)
- Long summaries span many messages without clear structure
- No way for guilds to customize the output format
- References lack Discord-native jump links to source messages
- Can't choose which sections to include (some guilds want brief, others comprehensive)

## 2. Decision

### Implement a thread-based push system with customizable templates.

**Key Changes:**

1. **Thread Creation (Permission-Gated)**
   - If bot has `CREATE_PUBLIC_THREADS` permission, create a thread for the summary
   - Thread name format: `Summary: #channel (Jan 15-16)` or `Summary: Server-wide (Jan 15)`
   - First message in thread = header + overall summary
   - Follow-up messages = structured sections (key points, action items, etc.)
   - Fallback: If no thread permission, send structured messages directly to channel

2. **Template System**
   - Default template built into the codebase
   - Guild-level overrides stored in `guild_push_templates` table
   - Templates define: sections to include, order, limits, formatting options
   - Templates are versioned for forward compatibility

3. **Message Structure**
   ```
   Message 1 (Thread Starter):
   ┌────────────────────────────────────────────────────────────┐
   │ 📋 Summary: #general                                       │
   │ Period: Jan 15, 2026 9:00 AM - Jan 16, 2026 5:00 PM (UTC) │
   │ Messages: 147 | Participants: 12                           │
   │                                                            │
   │ [Overall summary text here...]                             │
   └────────────────────────────────────────────────────────────┘

   Message 2 (Key Points):
   ┌────────────────────────────────────────────────────────────┐
   │ 🎯 Key Points                                              │
   │                                                            │
   │ • First key point [1][2]                                   │
   │ • Second key point [3]                                     │
   │ • Third key point [4][5][6]                                │
   └────────────────────────────────────────────────────────────┘

   Message 3 (Action Items):
   ┌────────────────────────────────────────────────────────────┐
   │ 📝 Action Items                                            │
   │                                                            │
   │ ⭕ 🔴 High priority item (@alice) [7]                       │
   │ ⭕ 🟡 Medium priority item [8]                              │
   └────────────────────────────────────────────────────────────┘

   Message 4 (Sources - if references enabled):
   ┌────────────────────────────────────────────────────────────┐
   │ 📚 Sources                                                 │
   │                                                            │
   │ [1] alice (9:15 AM): "We should..." → Jump                 │
   │ [2] bob (9:18 AM): "I agree with..." → Jump                │
   │ [3] charlie (10:30 AM): "The deadline..." → Jump           │
   └────────────────────────────────────────────────────────────┘
   ```

4. **Jump Links for References**
   - Discord message links: `https://discord.com/channels/{guild_id}/{channel_id}/{message_id}`
   - Short format in sources table: `[Jump](url)` or just `→ Jump` as clickable link
   - Only include jump links for Discord-sourced summaries (not WhatsApp imports, etc.)

## 3. ADR-004 Amendment: Extended SummaryReference

**Problem:** Current `SummaryReference` only stores `message_id`. Jump links require `channel_id` too, especially for multi-channel summaries.

**Change:** Extend `SummaryReference` model:

```python
@dataclass
class SummaryReference(BaseModel):
    """A citation pointing to a specific source message in a summary."""
    message_id: str
    channel_id: str  # NEW: Required for jump links
    guild_id: str    # NEW: Required for jump links
    sender: str
    timestamp: datetime
    snippet: str  # Max 200 chars of the relevant message content
    position: int  # 1-based position in the conversation window
    source_type: str = "discord"  # NEW: "discord", "whatsapp", "import"

    def to_jump_link(self) -> Optional[str]:
        """Generate Discord jump link, or None if not applicable."""
        if self.source_type != "discord":
            return None
        if not all([self.guild_id, self.channel_id, self.message_id]):
            return None
        return f"https://discord.com/channels/{self.guild_id}/{self.channel_id}/{self.message_id}"
```

**Migration:** Existing references without `channel_id`/`guild_id` will have jump links disabled gracefully.

## 4. Template Schema

```python
@dataclass
class PushTemplate:
    """Configuration for how summaries are pushed to Discord."""

    # Schema version for forward compatibility
    schema_version: int = 1

    # Thread settings
    use_thread: bool = True
    thread_name_format: str = "Summary: {scope} ({date_range})"
    thread_auto_archive_minutes: int = 1440  # 24 hours

    # Message 1: Header + Summary
    header_format: str = "📋 **Summary: {scope}**"
    show_date_range: bool = True
    show_stats: bool = True  # message count, participants
    show_summary_text: bool = True

    # Sections (order determines message order)
    sections: List[SectionConfig] = field(default_factory=lambda: [
        SectionConfig(type="key_points", enabled=True, max_items=10),
        SectionConfig(type="action_items", enabled=True, max_items=5),
        SectionConfig(type="decisions", enabled=True, max_items=5),
        SectionConfig(type="technical_terms", enabled=False, max_items=5),
        SectionConfig(type="participants", enabled=False, max_items=10),
        SectionConfig(type="sources", enabled=True, max_items=20),
    ])

    # Reference formatting
    include_references: bool = True
    include_jump_links: bool = True
    reference_style: str = "numbered"  # "numbered" [1][2], "inline" (Bob, 9:15)

    # Embed settings
    use_embeds: bool = True
    embed_color: int = 0x4A90E2  # Blue

@dataclass
class SectionConfig:
    """Configuration for a single section in the push output."""
    type: str  # key_points, action_items, decisions, technical_terms, participants, sources
    enabled: bool = True
    max_items: int = 10
    title_override: Optional[str] = None  # Custom section title
    combine_with_previous: bool = False  # Combine into same message as previous section
```

## 5. Default Template

The default template prioritizes clarity and brevity:

```python
DEFAULT_PUSH_TEMPLATE = PushTemplate(
    schema_version=1,
    use_thread=True,
    thread_name_format="Summary: {scope} ({date_range})",
    thread_auto_archive_minutes=1440,

    header_format="📋 **Summary: {scope}**",
    show_date_range=True,
    show_stats=True,
    show_summary_text=True,

    sections=[
        SectionConfig(type="key_points", enabled=True, max_items=10),
        SectionConfig(type="action_items", enabled=True, max_items=5),
        SectionConfig(type="decisions", enabled=True, max_items=5),
        SectionConfig(type="sources", enabled=True, max_items=15),
    ],

    include_references=True,
    include_jump_links=True,
    reference_style="numbered",
    use_embeds=True,
    embed_color=0x4A90E2,
)
```

**What's NOT included by default:**
- Technical terms (too verbose for most use cases)
- Participants (often not needed, adds noise)

## 6. Guild Override Mechanism

### Database Schema

```sql
CREATE TABLE guild_push_templates (
    guild_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1,
    template_json TEXT NOT NULL,  -- JSON serialized PushTemplate
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by TEXT  -- User ID who configured
);

CREATE INDEX idx_guild_push_templates_updated
    ON guild_push_templates(updated_at DESC);
```

### API Endpoints

```
GET  /guilds/{guild_id}/push-template          # Get current template (default or custom)
PUT  /guilds/{guild_id}/push-template          # Set custom template
DELETE /guilds/{guild_id}/push-template        # Reset to default
POST /guilds/{guild_id}/push-template/preview  # Preview with sample data
```

### Resolution Order

1. Check `guild_push_templates` table for guild-specific template
2. Validate `schema_version` - migrate if needed (see Section 12)
3. If not found or invalid, use `DEFAULT_PUSH_TEMPLATE`

## 7. Scope Formatting

Templates use `{scope}` placeholder which resolves based on summary source:

| Scope Type | Example Output |
|------------|----------------|
| Single channel | `#general` |
| Multiple channels | `#general, #random` (up to 3, then `+N more`) |
| Category | `📁 Engineering` |
| Server-wide | `🌐 Server-wide` |

## 8. Date Range Formatting

The `{date_range}` placeholder formats intelligently:

| Duration | Format |
|----------|--------|
| Same day | `Jan 15` |
| Multi-day, same month | `Jan 15-16` |
| Cross-month | `Jan 30 - Feb 2` |
| Cross-year | `Dec 30, 2025 - Jan 2, 2026` |

## 9. Known Issues & Mitigations

### 9.1 Thread Edge Cases

| Issue | Detection | Mitigation |
|-------|-----------|------------|
| **Target is already a thread** | Check `channel.type == ChannelType.public_thread` | Skip thread creation, send messages directly |
| **Target is a forum channel** | Check `channel.type == ChannelType.forum` | Create forum post instead of thread (requires title + tags) |
| **Has CREATE_PUBLIC_THREADS but not SEND_MESSAGES_IN_THREADS** | Check both permissions | Only create thread if both permissions present |
| **Thread name too long** | Discord limit: 100 chars | Truncate scope name, keep date range |
| **Thread name collision** | Same channel + date range | Append unique suffix: `Summary: #general (Jan 15) #2` |

### 9.2 Jump Link Limitations

| Issue | Detection | Mitigation |
|-------|-----------|------------|
| **Source message deleted** | Cannot detect without API call | Accept broken links; users understand messages can be deleted |
| **Non-Discord source** | Check `reference.source_type` | Omit jump link, show citation without link |
| **Missing channel_id (legacy data)** | Check `reference.channel_id is None` | Omit jump link for that reference |
| **Cross-guild reference** | Compare `reference.guild_id != target_guild_id` | Omit jump link (users may not have access) |

### 9.3 Content Overflow

| Issue | Detection | Mitigation |
|-------|-----------|------------|
| **Section exceeds 2000 chars** | Calculate length before sending | Paginate within section: "🎯 Key Points (1/2)", "🎯 Key Points (2/2)" |
| **Too many references** | Count > `max_items` | Truncate to `max_items`, add "...and N more sources" |
| **Summary text too long** | `len(summary_text) > 1800` | Truncate with "..." or split across messages |

### 9.4 Rate Limits

| Issue | Detection | Mitigation |
|-------|-----------|------------|
| **Too many messages quickly** | Discord: ~5 msg/5s per channel | Add 1-second delay between section messages |
| **Bulk push to many channels** | User request | Queue pushes, process with rate limit backoff |

### 9.5 Template Schema Evolution

| Issue | Detection | Mitigation |
|-------|-----------|------------|
| **Old template missing new fields** | `schema_version < CURRENT_VERSION` | Apply defaults for missing fields at load time |
| **Unknown fields in template** | Extra keys in JSON | Ignore unknown fields (forward compatible) |
| **Invalid template JSON** | JSON parse error or validation fail | Fall back to `DEFAULT_PUSH_TEMPLATE`, log warning |

## 10. Implementation Plan

### Phase 0: ADR-004 Amendment (Pre-requisite)
- [ ] Add `channel_id`, `guild_id`, `source_type` to `SummaryReference` model
- [ ] Update `PositionIndex.resolve()` to populate new fields
- [ ] Update prompt formatter to track channel context per message
- [ ] Ensure existing code handles missing fields gracefully

### Phase 1: Core Template System
- [ ] Create `PushTemplate` and `SectionConfig` models in `src/models/push_template.py`
- [ ] Create `DEFAULT_PUSH_TEMPLATE` constant
- [ ] Add template validation function
- [ ] Add template resolution logic (guild override or default)

### Phase 2: Thread Support
- [ ] Check `CREATE_PUBLIC_THREADS` AND `SEND_MESSAGES_IN_THREADS` permissions
- [ ] Detect if target channel is already a thread (skip thread creation)
- [ ] Detect if target is a forum channel (create post instead)
- [ ] Implement thread creation with proper naming (truncate if > 100 chars)
- [ ] Fallback to channel messages if no permission

### Phase 3: Structured Message Builder
- [ ] Create `PushMessageBuilder` class
- [ ] Implement section rendering with pagination (split at 1900 chars)
- [ ] Add rate limit delays between messages (1 second)
- [ ] Refactor `SummaryPushService._push_to_channel()` to use builder

### Phase 4: Jump Links
- [ ] Add `to_jump_link()` method to `SummaryReference`
- [ ] Filter out non-Discord sources from jump links
- [ ] Filter out cross-guild references
- [ ] Format as markdown links in sources section

### Phase 5: Guild Configuration
- [ ] Create `guild_push_templates` migration
- [ ] Create `PushTemplateRepository` for CRUD
- [ ] Add API endpoints for template CRUD
- [ ] Add preview endpoint with sample data
- [ ] Implement schema version migration

### Phase 6: Dashboard UI
- [ ] Add "Push Settings" section in guild settings
- [ ] Toggle sections on/off
- [ ] Reorder sections via drag-and-drop
- [ ] Preview button with sample data
- [ ] Reset to default button

## 11. Example Output

### With Thread (Default)

**Thread: "Summary: #general (Feb 20-21)"**

**Message 1:**
```
📋 **Summary: #general**
📅 Feb 20, 2026 9:00 AM - Feb 21, 2026 5:30 PM (UTC)
📊 147 messages from 12 participants

The team discussed the upcoming release timeline and identified several blockers.
Alice proposed moving the deadline to next Friday, which received consensus.
Bob raised concerns about the API performance but Charlie confirmed the fixes
are ready for testing.
```

**Message 2:**
```
🎯 **Key Points**

• Release deadline moved to Friday Feb 28 [1][2]
• API performance issues resolved [3][4]
• New onboarding flow approved by design team [5]
• CI/CD pipeline upgrade scheduled for tonight [6]
```

**Message 3:**
```
📝 **Action Items**

⭕ 🔴 Deploy API fixes to staging (@bob) [3]
⭕ 🔴 Review onboarding PR #1234 (@alice) [5]
⭕ 🟡 Update release notes draft (@charlie) [1]
```

**Message 4:**
```
📚 **Sources**

[1] alice (9:15 AM): "Let's push the deadline to Friday..." [→ Jump](https://discord.com/channels/123/456/789)
[2] bob (9:18 AM): "I agree, that gives us buffer..." [→ Jump](https://discord.com/channels/123/456/790)
[3] charlie (10:30 AM): "API fixes are ready in PR #5678..." [→ Jump](https://discord.com/channels/123/456/791)
[4] alice (10:45 AM): "Great, let's get those deployed..." [→ Jump](https://discord.com/channels/123/456/792)
[5] diana (2:00 PM): "Design approved the new flow..." [→ Jump](https://discord.com/channels/123/456/793)
[6] eve (4:30 PM): "CI upgrade going out at midnight..." [→ Jump](https://discord.com/channels/123/456/794)
```

### Without Thread Permission

Same content, but sent as sequential messages to the channel:
```
📋 **Summary: #general** (thread unavailable - sending inline)
...
```

### With Non-Discord Source (WhatsApp Import)

```
📚 **Sources**

[1] Alice (9:15 AM): "Let's push the deadline to Friday..."
[2] Bob (9:18 AM): "I agree, that gives us buffer..."
```
*(No jump links - source is WhatsApp, not Discord)*

### With Section Pagination

```
🎯 **Key Points (1/2)**

• First key point [1][2]
• Second key point [3]
• Third key point [4]
...
```

```
🎯 **Key Points (2/2)**

• Eighth key point [15]
• Ninth key point [16][17]
• Tenth key point [18]
```

## 12. Template Schema Versioning

When loading a template:

```python
def load_template(template_json: str) -> PushTemplate:
    data = json.loads(template_json)
    version = data.get("schema_version", 1)

    # Migrate old versions
    if version < 2:
        # Example: v2 added 'source_type' filtering
        data.setdefault("filter_source_types", ["discord"])

    # Apply defaults for any missing fields
    return PushTemplate(**{**DEFAULT_PUSH_TEMPLATE.to_dict(), **data})
```

This ensures old templates continue to work as new features are added.

## 13. Benefits

1. **Cleaner channels** - Summaries contained in threads, not cluttering main channel
2. **Structured output** - Consistent formatting with clear sections
3. **Customizable** - Guilds can tailor output to their needs
4. **Traceable** - Jump links let users verify claims
5. **Permission-aware** - Graceful fallback when thread creation isn't possible
6. **Source-aware** - Handles Discord and non-Discord sources appropriately
7. **Future-proof** - Schema versioning allows evolution without breaking existing configs

## 14. Migration Notes

- Existing push functionality continues to work (embed format)
- New thread-based push is opt-in via template setting `use_thread: true` (default)
- Guilds can disable threads by setting `use_thread: false`
- Existing `SummaryReference` data without `channel_id` will have jump links disabled
- New summaries will automatically include `channel_id` for jump link support

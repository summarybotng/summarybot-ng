# ADR-046: Channel Permission-Aware Summary Visibility

**Status:** Proposed
**Date:** 2026-04-12
**Related:** ADR-041 (Soft-Fail Channel Permissions), ADR-045 (Audit Logging)

---

## 1. Context

### The Problem

Discord has a rich permission system where channels can have restricted visibility:
- **Private channels**: Only visible to specific roles (e.g., `#staff-only`, `#moderators`)
- **Category permissions**: Channels inherit from category with optional overrides
- **Role-based access**: Different roles see different channels

**Current SummaryBot behavior:**
- Any guild member who logs into the dashboard can view ALL summaries for that guild
- No checking whether the user has Discord access to the source channel(s)
- Summaries from `#staff-only` are visible to regular members in the dashboard

**This creates a privacy/security gap:**

```
Discord: User cannot see #staff-only channel
Dashboard: User CAN see summary of #staff-only channel
Result: Information leak
```

### Real-World Scenarios

1. **Staff Channel Leak**
   - Admin creates a daily summary schedule for `#staff-discussions`
   - Regular member logs into dashboard
   - Member reads summaries of private staff conversations

2. **Multi-Channel Summary**
   - Schedule covers entire guild (50 channels)
   - 5 channels are private/sensitive
   - Summary includes content from all 50 channels
   - Non-privileged user sees content they shouldn't

3. **Historical Access Change**
   - User was a moderator, could access `#mod-logs`
   - User is demoted, loses `#mod-logs` access in Discord
   - User can still see old summaries of `#mod-logs` in dashboard

4. **Webhook/Feed Delivery**
   - Summary pushed to `#public-announcements` channel
   - Contains content from `#internal-planning`
   - Anyone in the guild can now read internal planning discussions

---

## 2. Design Considerations

### 2.1 What Discord Permissions Mean

Discord permissions are complex:

```
Permission Check for Channel Access:
1. Is user a member of the guild?
2. Does user have "View Channel" permission?
   - Check @everyone role permissions
   - Check user's role permissions
   - Check channel-specific overrides
   - Check category permissions (if inheriting)
3. For reading history: "Read Message History" permission
```

### 2.2 Dashboard vs Discord Identity

The dashboard has its own identity layer:

| Discord | Dashboard |
|---------|-----------|
| Discord User ID | Same (via OAuth) |
| Guild Member | JWT contains guild IDs |
| Roles | NOT stored in JWT |
| Channel permissions | NOT checked |

**Key insight**: The dashboard knows WHO the user is but not WHAT they can access within a guild.

### 2.3 Performance Considerations

**Checking permissions at view time:**
```
User requests summaries → For each summary → For each source channel →
Query Discord API → Check user permissions → Filter results
```

- Discord API has rate limits (~50 req/sec)
- Each permission check requires API call
- Guild with 100 summaries × 5 channels = 500 API calls
- **Unacceptable latency and rate limit risk**

**Caching options:**
- Cache channel permissions per user: Stale quickly, high memory
- Cache at request time with TTL: Still many API calls initially
- Pre-sync on login: Heavy login, still stale

---

## 3. Decision Options

### Option A: Real-Time Discord Permission Checking

**How it works:**
- On summary list/view, check Discord API for each source channel
- Filter out summaries where user lacks channel access
- Cache results briefly (5 min TTL)

**Pros:**
- Always accurate
- Respects permission changes immediately
- Leverages Discord's permission model

**Cons:**
- Performance: Many API calls per request
- Rate limits: May hit Discord rate limits under load
- Complexity: Permission checking is non-trivial
- Availability: Dashboard depends on Discord API

**Verdict:** Not recommended for MVP due to performance.

---

### Option B: Store Permission Snapshot with Summary

**How it works:**
- When summary is created, record which roles had access to source channels
- Store as metadata: `{"required_roles": ["mod", "admin"], "restricted": true}`
- On view, check if user's roles (from Discord OAuth) intersect

**Problem:** Dashboard JWT doesn't include user's roles per guild.

**Enhanced approach:**
- Fetch user's guild roles on login and store in JWT
- Check role intersection on summary access

**Pros:**
- Fast queries (no API calls at view time)
- Deterministic access control

**Cons:**
- Roles fetched at login time may be stale
- Storage overhead per summary
- Complex role intersection logic
- Doesn't handle permission override changes

**Verdict:** Possible but adds significant complexity.

---

### Option C: Channel Sensitivity Configuration

**How it works:**
- Admin marks channels as "sensitive" in SummaryBot config
- Summaries from sensitive channels require admin dashboard role
- Simple boolean: `channel.is_sensitive = true`

```yaml
# Guild config
sensitive_channels:
  - "123456789012345678"  # #staff-only
  - "234567890123456789"  # #moderators

# Or by category
sensitive_categories:
  - "345678901234567890"  # Staff category
```

**Pros:**
- Simple to implement
- Fast (config lookup, not API call)
- Admin has explicit control
- Clear mental model

**Cons:**
- Manual configuration per guild
- Doesn't auto-sync with Discord permissions
- Admin might forget to mark sensitive channels
- New private channels aren't auto-protected

**Verdict:** Good balance of simplicity and protection.

---

### Option D: Summary-Level Privacy Flag

**How it works:**
- Each summary has a visibility setting: `public`, `admin_only`, `restricted`
- Set automatically based on source channels, or manually
- Schedules inherit a default visibility level

```python
class StoredSummary:
    visibility: Literal["public", "admin_only", "role_restricted"]
    required_roles: Optional[List[str]] = None  # For role_restricted
```

**Pros:**
- Per-summary granularity
- Can be set manually for edge cases
- Clear access rules

**Cons:**
- More metadata to store
- Need UI for setting visibility
- Doesn't auto-detect from Discord

**Verdict:** Good for explicit control, combine with Option C.

---

### Option E: Accept Current Behavior (Document as Intentional)

**Rationale:**
- Guild membership implies trust
- If someone is in the guild, they're trusted with guild info
- Admins shouldn't summarize truly sensitive channels
- Principle: Don't summarize what you wouldn't share

**Mitigations:**
- Document this behavior clearly
- Warn when creating schedules for private channels
- Audit log who viewed what summaries

**Pros:**
- No implementation needed
- Simple mental model
- Follows "don't create sensitive summaries" principle

**Cons:**
- Easy to accidentally leak information
- Doesn't match Discord's permission model
- Compliance/privacy concerns for some organizations

**Verdict:** Acceptable short-term, but should add protections.

---

## 4. Recommendation

**Implement a phased approach combining Options C, D, and E:**

### Phase 1: Documentation & Warnings (Immediate)
- Document that summaries are visible to all guild members
- Add warning when scheduling summaries for restricted channels
- Log summary views in audit trail (ADR-045)

### Phase 2: Channel Sensitivity Config (Short-term)
- Add `sensitive_channels` config per guild
- Summaries from sensitive channels require admin role
- Auto-detect private channels as sensitive (bot lacks access = probably private)

### Phase 3: Summary Visibility Control (Medium-term)
- Add visibility field to summaries/schedules
- Default: `public` (current behavior)
- Option: `admin_only` for sensitive schedules
- UI to manage visibility

### Phase 4: Discord Permission Sync (Long-term, Optional)
- On login, fetch user's roles for each guild
- Store in JWT with reasonable TTL
- Enable role-based access matching
- Cache permission checks with background refresh

---

## 5. Phase 1 Implementation

### 5.1 Documentation Update

Add to user-facing docs:
> **Privacy Note:** Summaries are visible to all guild members who can access the dashboard.
> Avoid creating summaries of sensitive channels unless you intend to share that content
> with your entire community.

### 5.2 Schedule Creation Warning

When creating/editing a schedule, check if target channels are private:

```python
async def check_channel_privacy(guild: discord.Guild, channel_ids: List[str]) -> List[dict]:
    """Check if any channels appear to be private/restricted."""
    warnings = []
    for channel_id in channel_ids:
        channel = guild.get_channel(int(channel_id))
        if channel:
            # Check if @everyone can view the channel
            everyone_role = guild.default_role
            perms = channel.permissions_for(everyone_role)
            if not perms.view_channel:
                warnings.append({
                    "channel_id": channel_id,
                    "channel_name": channel.name,
                    "warning": "This channel is not visible to @everyone. "
                              "Summaries will be visible to all dashboard users."
                })
    return warnings
```

```tsx
// Frontend warning
{privateChannelWarnings.length > 0 && (
  <Alert variant="warning">
    <AlertTriangle className="h-4 w-4" />
    <AlertTitle>Privacy Notice</AlertTitle>
    <AlertDescription>
      This schedule includes {privateChannelWarnings.length} private channel(s).
      Summaries will be visible to all guild members in the dashboard, not just
      those with channel access in Discord.
      <ul className="mt-2 list-disc list-inside">
        {privateChannelWarnings.map(w => (
          <li key={w.channel_id}>#{w.channel_name}</li>
        ))}
      </ul>
    </AlertDescription>
  </Alert>
)}
```

### 5.3 Audit Logging

Log summary views (integrates with ADR-045):

```python
# When summary is viewed
await audit_service.log(
    event_type="summary.viewed",
    category=AuditEventCategory.ACCESS,
    user_id=user["sub"],
    guild_id=guild_id,
    resource_type="summary",
    resource_id=summary_id,
    details={
        "source_channels": summary.source_channel_ids,
        "contains_private_channels": has_private_channels,
    }
)
```

---

## 6. Phase 2 Implementation

### 6.1 Guild Config Extension

```python
@dataclass
class GuildConfig:
    # ... existing fields ...

    # ADR-046: Channel sensitivity
    sensitive_channels: List[str] = field(default_factory=list)
    sensitive_categories: List[str] = field(default_factory=list)
    auto_mark_private_sensitive: bool = True  # Auto-detect private channels
```

### 6.2 Summary Filtering

```python
async def filter_summaries_by_access(
    summaries: List[StoredSummary],
    user: dict,
    guild_config: GuildConfig,
) -> List[StoredSummary]:
    """Filter summaries based on channel sensitivity config."""
    is_admin = is_guild_admin(user, guild_config.guild_id)

    if is_admin:
        return summaries  # Admins see everything

    sensitive_set = set(guild_config.sensitive_channels)

    filtered = []
    for summary in summaries:
        # Check if any source channel is sensitive
        source_channels = set(summary.source_channel_ids)
        if source_channels.isdisjoint(sensitive_set):
            filtered.append(summary)
        # else: skip - contains sensitive channel content

    return filtered
```

### 6.3 Auto-Detection of Private Channels

```python
async def detect_private_channels(guild: discord.Guild) -> List[str]:
    """Detect channels that are not visible to @everyone."""
    everyone_role = guild.default_role
    private_channels = []

    for channel in guild.channels:
        if isinstance(channel, discord.TextChannel):
            perms = channel.permissions_for(everyone_role)
            if not perms.view_channel:
                private_channels.append(str(channel.id))

    return private_channels
```

---

## 7. Database Changes

### Phase 2 Schema

```sql
-- Add to guild_configs table (or JSON config)
ALTER TABLE guild_configs ADD COLUMN sensitive_channels TEXT;  -- JSON array
ALTER TABLE guild_configs ADD COLUMN sensitive_categories TEXT;  -- JSON array

-- Or if using JSON config, add to schema:
-- sensitive_channels: string[]
-- sensitive_categories: string[]
```

### Phase 3 Schema

```sql
-- Add visibility to stored_summaries
ALTER TABLE stored_summaries ADD COLUMN visibility TEXT DEFAULT 'public';
-- Values: 'public', 'admin_only', 'role_restricted'

ALTER TABLE stored_summaries ADD COLUMN required_roles TEXT;
-- JSON array of role IDs for 'role_restricted' visibility

CREATE INDEX idx_stored_summaries_visibility ON stored_summaries(visibility);
```

---

## 8. Migration Considerations

### Existing Summaries

- All existing summaries default to `visibility: public` (current behavior)
- Admins can retroactively mark sensitive summaries as `admin_only`
- No automatic migration - too risky to auto-restrict

### Existing Schedules

- Existing schedules continue working as before
- Optionally show one-time warning about private channels
- New schedules get the warning UI

---

## 9. Consequences

### Positive
- Clear privacy model for summary visibility
- Admins warned about private channel implications
- Audit trail of who viewed what
- Flexible configuration for different guild needs
- Graceful migration path from current behavior

### Negative
- Additional configuration burden on admins
- Not perfect sync with Discord permissions
- Summaries may be over-restricted or under-restricted
- Storage and filtering overhead in Phase 2+

### Neutral
- Behavior change requires user education
- Some guilds may prefer current open behavior
- Trade-off between simplicity and precision

---

## 10. Alternatives Considered

### Discord Slash Command Permissions
Use Discord's slash command permission system to control who can view summaries via bot commands.
**Rejected:** Dashboard is separate from Discord bot; doesn't solve web UI access.

### Per-User Summary Generation
Generate summaries on-demand, only including channels the requesting user can access.
**Rejected:** Defeats purpose of scheduled summaries; high compute cost; no caching.

### Separate Dashboard Per Channel
Create isolated dashboard views per channel, like separate "mini-apps".
**Rejected:** Poor UX; defeats purpose of unified dashboard.

---

## 11. Open Questions

1. **Multi-channel summaries with mixed sensitivity:**
   - If 9/10 channels are public and 1 is sensitive, is the summary sensitive?
   - Recommendation: Yes, any sensitive source makes summary sensitive

2. **Category-level sensitivity:**
   - Should marking a category as sensitive auto-include all channels?
   - Recommendation: Yes, with channel-level overrides

3. **Webhook/feed delivery:**
   - Should sensitive summaries be blocked from push to public channels?
   - Recommendation: Yes, warn when scheduling delivery to public channels

4. **Archive summaries:**
   - Apply same rules to archive/retrospective summaries?
   - Recommendation: Yes, they contain the same content

---

## 12. References

- [Discord Permission System](https://discord.com/developers/docs/topics/permissions)
- ADR-041: Soft-Fail Channel Permissions (bot-side access handling)
- ADR-045: Audit Logging System (tracking who views summaries)
- GDPR Article 25: Data Protection by Design

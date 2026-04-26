# ADR-066: Platform-Agnostic Architecture

## Status
Proposed

## Context

SummaryBot NG was originally built as a Discord bot. As we've added support for WhatsApp (ADR-027), Slack (ADR-043), and plan to add more platforms, the Discord-centric architecture creates friction:

1. **Terminology**: "guild" is Discord-specific; other platforms use "workspace", "team", "group"
2. **Authentication**: OAuth is Discord-only; each platform needs its own auth flow
3. **Data Models**: `guild_id` is hardcoded everywhere; difficult to query cross-platform
4. **User Identity**: Users are identified by Discord IDs; no unified identity
5. **Channel Concept**: "Channel" means different things on different platforms
6. **Message Format**: Discord embeds vs. WhatsApp text vs. Slack blocks

### Current State

| Component | Current | Problem |
|-----------|---------|---------|
| Auth | Discord OAuth only | Can't login without Discord |
| Primary ID | `guild_id` | Discord-specific terminology |
| User model | `discord_user_id` | No cross-platform identity |
| Scheduling | Discord channels | Other platforms have different structures |
| Wiki | Keyed by `guild_id` | Tied to Discord concept |

---

## Decision

Introduce a **platform-agnostic abstraction layer** that unifies concepts across platforms while preserving platform-specific capabilities.

### Core Concept: Workspace

Replace "guild" with "workspace" as the universal container:

```
┌─────────────────────────────────────────────────────────────┐
│                        WORKSPACE                             │
│  (Previously "Guild" - now platform-agnostic)               │
├─────────────────────────────────────────────────────────────┤
│  id: UUID                                                    │
│  name: string                                                │
│  owner_id: UUID (User)                                       │
│  created_at: datetime                                        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │             PLATFORM CONNECTIONS                     │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │    │
│  │  │ Discord │ │WhatsApp │ │  Slack  │ │Telegram │   │    │
│  │  │guild:123│ │group:abc│ │team:xyz │ │chat:789 │   │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                    MEMBERS                           │    │
│  │  User 1 (Discord + Slack)                           │    │
│  │  User 2 (WhatsApp only)                             │    │
│  │  User 3 (All platforms)                             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Model Changes

### Phase 1: Add Workspace Layer (Non-Breaking)

```sql
-- New unified workspace table
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,  -- UUID
    name TEXT NOT NULL,
    description TEXT,
    owner_user_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    settings TEXT DEFAULT '{}',  -- JSON workspace settings
    FOREIGN KEY (owner_user_id) REFERENCES users(id)
);

-- Platform connections (one workspace can have multiple platforms)
CREATE TABLE workspace_connections (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    platform TEXT NOT NULL,  -- discord, whatsapp, slack, telegram
    platform_id TEXT NOT NULL,  -- guild_id, group_id, team_id, etc.
    platform_name TEXT,  -- Display name from platform
    connected_at TEXT NOT NULL DEFAULT (datetime('now')),
    connected_by TEXT NOT NULL,  -- User who connected
    status TEXT DEFAULT 'active',  -- active, disconnected, error
    credentials TEXT,  -- Encrypted platform-specific credentials
    metadata TEXT DEFAULT '{}',  -- Platform-specific metadata
    UNIQUE (platform, platform_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Unified user table
CREATE TABLE users (
    id TEXT PRIMARY KEY,  -- UUID
    display_name TEXT NOT NULL,
    email TEXT,
    avatar_url TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT,
    settings TEXT DEFAULT '{}'
);

-- User platform identities (one user can have multiple platform accounts)
CREATE TABLE user_identities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    platform_user_id TEXT NOT NULL,
    platform_username TEXT,
    verified_at TEXT,
    UNIQUE (platform, platform_user_id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Workspace membership
CREATE TABLE workspace_members (
    workspace_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'member',  -- owner, admin, member
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (workspace_id, user_id),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### Phase 2: Migrate Existing Data

```sql
-- Create workspaces from existing guilds
INSERT INTO workspaces (id, name, owner_user_id, created_at)
SELECT
    'ws-' || guild_id,
    name,
    owner_id,
    created_at
FROM guilds;

-- Create workspace connections for Discord guilds
INSERT INTO workspace_connections (id, workspace_id, platform, platform_id, platform_name)
SELECT
    'wc-discord-' || guild_id,
    'ws-' || guild_id,
    'discord',
    guild_id,
    name
FROM guilds;

-- Add workspace_id column to existing tables
ALTER TABLE stored_summaries ADD COLUMN workspace_id TEXT;
UPDATE stored_summaries SET workspace_id = 'ws-' || guild_id;

ALTER TABLE wiki_pages ADD COLUMN workspace_id TEXT;
UPDATE wiki_pages SET workspace_id = 'ws-' || guild_id;

-- Etc for all guild_id tables...
```

### Phase 3: Update Foreign Keys

```sql
-- Create indexes on new workspace_id columns
CREATE INDEX idx_stored_summaries_workspace ON stored_summaries(workspace_id);
CREATE INDEX idx_wiki_pages_workspace ON wiki_pages(workspace_id);

-- Eventually: Remove guild_id columns (breaking change)
-- ALTER TABLE stored_summaries DROP COLUMN guild_id;
```

---

## Authentication Changes

### Multi-Provider Authentication

```python
class AuthProvider(Enum):
    DISCORD = "discord"
    SLACK = "slack"
    GOOGLE = "google"
    EMAIL = "email"  # Magic link

class AuthService:
    """Unified authentication supporting multiple providers."""

    async def login(self, provider: AuthProvider, credentials: dict) -> AuthResult:
        """Authenticate via any supported provider."""
        handler = self._get_handler(provider)
        platform_user = await handler.authenticate(credentials)

        # Find or create unified user
        user = await self._find_or_create_user(provider, platform_user)

        # Create session with workspace access
        workspaces = await self._get_user_workspaces(user.id)
        return AuthResult(user=user, workspaces=workspaces, token=self._create_jwt(user))

    async def link_identity(self, user_id: str, provider: AuthProvider, credentials: dict):
        """Link additional platform identity to existing user."""
        handler = self._get_handler(provider)
        platform_user = await handler.authenticate(credentials)
        await self._create_identity(user_id, provider, platform_user)
```

### JWT Structure Update

```python
# Current JWT payload
{
    "sub": "discord_user_id",  # Discord-specific
    "guilds": ["123", "456"],  # Discord term
    "guild_roles": {...}
}

# New JWT payload
{
    "sub": "user_uuid",  # Universal user ID
    "workspaces": ["ws-abc", "ws-def"],  # Platform-agnostic
    "workspace_roles": {"ws-abc": "admin", "ws-def": "member"},
    "identities": {  # Linked platform accounts
        "discord": "123456789",
        "slack": "U12345"
    }
}
```

---

## API Changes

### URL Structure

```
# Current (Discord-centric)
/api/v1/guilds/{guild_id}/summaries
/api/v1/guilds/{guild_id}/wiki/pages

# New (Platform-agnostic)
/api/v2/workspaces/{workspace_id}/summaries
/api/v2/workspaces/{workspace_id}/wiki/pages

# Platform-specific operations
/api/v2/workspaces/{workspace_id}/connections/{connection_id}/channels
/api/v2/workspaces/{workspace_id}/connections/{connection_id}/sync
```

### Backwards Compatibility

```python
# v1 routes continue to work, translate guild_id to workspace_id
@router.get("/guilds/{guild_id}/summaries")
async def list_summaries_v1(guild_id: str):
    """Legacy endpoint - translates to workspace."""
    workspace_id = await translate_guild_to_workspace(guild_id)
    return await list_summaries_v2(workspace_id)
```

---

## Platform Adapter Pattern

```python
class PlatformAdapter(ABC):
    """Abstract adapter for chat platforms."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return platform identifier (discord, slack, whatsapp, telegram)."""
        ...

    @abstractmethod
    async def fetch_messages(
        self,
        connection: WorkspaceConnection,
        channel_id: str,
        since: datetime,
    ) -> List[NormalizedMessage]:
        """Fetch messages from platform, return in normalized format."""
        ...

    @abstractmethod
    async def list_channels(
        self,
        connection: WorkspaceConnection,
    ) -> List[NormalizedChannel]:
        """List available channels/chats/groups."""
        ...

    @abstractmethod
    async def send_message(
        self,
        connection: WorkspaceConnection,
        channel_id: str,
        content: MessageContent,
    ) -> bool:
        """Send message to platform channel."""
        ...

class DiscordAdapter(PlatformAdapter):
    platform_name = "discord"
    # ... Discord-specific implementation

class SlackAdapter(PlatformAdapter):
    platform_name = "slack"
    # ... Slack-specific implementation

class WhatsAppAdapter(PlatformAdapter):
    platform_name = "whatsapp"
    # ... WhatsApp-specific implementation
```

---

## Normalized Message Model

```python
@dataclass
class NormalizedMessage:
    """Platform-agnostic message representation."""
    id: str
    workspace_id: str
    connection_id: str
    channel_id: str
    channel_name: str

    # Author
    author_id: str  # Platform-specific
    author_name: str
    author_avatar: Optional[str]

    # Content
    content: str
    timestamp: datetime

    # Metadata
    platform: str  # discord, slack, whatsapp
    platform_message_id: str  # Original platform ID
    reply_to: Optional[str]  # Parent message ID
    attachments: List[Attachment] = field(default_factory=list)
    reactions: List[Reaction] = field(default_factory=list)

    # Platform-specific extras
    metadata: Dict[str, Any] = field(default_factory=dict)
```

---

## Migration Strategy

### Phase 1: Foundation (2-3 weeks)
1. Create workspace/user tables
2. Add workspace_id columns (nullable)
3. Implement AuthService with Discord + email
4. Keep v1 API working, add v2 alongside

### Phase 2: Data Migration (1 week)
1. Backfill workspace_id on all tables
2. Create workspace_connections for Discord guilds
3. Migrate user data to unified users table

### Phase 3: Feature Parity (2-3 weeks)
1. Update frontend to use workspace terminology
2. Add workspace management UI
3. Implement platform connection flow
4. Update scheduling to use connections

### Phase 4: New Platforms (Ongoing)
1. Add Slack adapter with OAuth
2. Add email/magic link login
3. Consider SSO (Google, Microsoft)

### Phase 5: Cleanup (1 week)
1. Deprecate v1 API
2. Remove guild_id columns
3. Update documentation

---

## UI/UX Changes

### Terminology Updates

| Old (Discord) | New (Universal) |
|--------------|-----------------|
| Guild | Workspace |
| Server | Workspace |
| Guild Settings | Workspace Settings |
| Join Guild | Join Workspace |
| Guild Members | Workspace Members |
| Channel | Channel (but context varies) |

### New Screens

1. **Workspace Selector** - Choose workspace at login
2. **Workspace Settings** - Manage connections, members, settings
3. **Connect Platform** - OAuth flow for new platform
4. **Link Identity** - Connect additional platform accounts to profile

---

## Consequences

### Positive
- True multi-platform support without platform-specific hacks
- Users can have unified identity across platforms
- Single workspace can aggregate from multiple platforms
- Cleaner API design
- Better separation of concerns

### Negative
- Significant migration effort
- Temporary complexity during transition
- Need to maintain v1 API for compatibility
- More complex auth flow

### Risks
- Data migration errors could lose guild associations
- Performance impact from extra joins
- Breaking changes for API consumers

### Mitigations
- Extensive testing of migration scripts
- Add indexes on workspace_id early
- Maintain v1 API until v2 is stable
- Feature flags for gradual rollout

---

## Implementation Priority

```
HIGH PRIORITY (Do First):
├── Workspace + User tables
├── workspace_id column migration
├── Email/magic link auth
└── v2 API endpoints (parallel to v1)

MEDIUM PRIORITY (After Foundation):
├── Platform adapter pattern
├── Frontend terminology updates
├── Workspace management UI
└── Slack OAuth integration

LOW PRIORITY (Nice to Have):
├── SSO providers (Google, Microsoft)
├── Cross-workspace search
├── Workspace templates
└── v1 API deprecation
```

---

## Open Questions

1. **Identity Linking**: How to handle when user links a platform account already associated with different user?
2. **Workspace Creation**: Auto-create from first platform connection, or require explicit creation?
3. **Cross-Platform Summaries**: Can one summary span messages from multiple platforms?
4. **Billing**: Will workspaces have separate billing from platforms?

---

## References

- [ADR-027: WhatsApp Integration](./ADR-027-whatsapp-integration.md)
- [ADR-043: Slack Integration](./ADR-043-slack-workspace-integration.md)
- [ADR-051: Platform Abstraction](./ADR-051-platform-abstraction.md)

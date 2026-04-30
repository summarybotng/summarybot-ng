# ADR-078: Platform-Agnostic UX Design

## Status
Proposed

## Context

SummaryBot has evolved from a Discord-only bot to a multi-platform system supporting:
- **Discord** - Real-time bot integration
- **WhatsApp** - Zip file import via retrospectives
- **Slack** - OAuth workspace integration (ADR-043)
- **Telegram** - Planned

However, the UI remains heavily Discord-centric, creating several UX problems:

### Current Issues

1. **Terminology Bias**
   - Routes use `/guilds` (Discord term) not `/workspaces`
   - "Servers" label throughout (Discord term)
   - "Guild" in component names: `GuildLayout`, `GuildSidebar`, `GuildDashboard`

2. **Hidden Platform Features**
   - WhatsApp import buried in Retrospectives > Import (not discoverable)
   - Slack workspaces in separate page, not integrated with main navigation
   - Channels page shows only Discord channels, ignoring WhatsApp/Slack

3. **Discord-Specific UI Elements**
   - Channel prefix `#` hardcoded (Discord convention)
   - Channel types: "voice", "forum" (Discord-only concepts)
   - Member counts displayed (not applicable to WhatsApp)
   - "Categories" concept (Discord-only, Slack has none)

4. **Inconsistent Platform Treatment**
   - Discord: First-class, real-time integration
   - Slack: Secondary, requires separate OAuth flow
   - WhatsApp: Hidden, import-only, no dedicated section

5. **Misleading Marketing Copy**
   - Landing page: "Never Miss What Matters in **Discord**"
   - Footer: "Made with ❤️ for Discord communities"
   - Excludes mention of WhatsApp/Slack capabilities

## Decision

### 1. Unified Workspace Model

Replace Discord-centric "Guild" concept with platform-agnostic "Workspace":

```typescript
interface Workspace {
  id: string;
  name: string;
  platform: "discord" | "slack" | "whatsapp" | "telegram";
  icon_url?: string;

  // Platform-specific metadata (optional)
  discord?: { guild_id: string; member_count: number; };
  slack?: { workspace_id: string; domain: string; };
  whatsapp?: { phone_number: string; };
}
```

### 2. Navigation Restructure

#### Current (Discord-Centric)
```
/guilds
  /guilds/:id/dashboard
  /guilds/:id/channels      ← Discord only
  /guilds/:id/summaries
  /guilds/:id/schedules
  /guilds/:id/wiki
  /guilds/:id/settings

/slack                      ← Separate section
/retrospectives             ← WhatsApp hidden here
```

#### Proposed (Platform-Agnostic)
```
/workspaces
  /workspaces/:id/dashboard
  /workspaces/:id/sources   ← All platforms: channels, chats, imports
  /workspaces/:id/summaries
  /workspaces/:id/schedules
  /workspaces/:id/wiki
  /workspaces/:id/settings
  /workspaces/:id/connect   ← Add new sources (Discord, Slack, WhatsApp)

/connect                    ← Global connection hub
  /connect/discord
  /connect/slack
  /connect/whatsapp
  /connect/telegram
```

### 3. Unified Sources Page

Replace "Channels" with "Sources" showing all connected platforms:

```
┌─────────────────────────────────────────────────────────────┐
│ Sources                                        [+ Add Source]│
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 🎮 Discord                              [12 channels]   │ │
│ │ ├─ #general                    ✓ Enabled    Daily 9am  │ │
│ │ ├─ #engineering                ✓ Enabled    Daily 9am  │ │
│ │ ├─ #random                     ○ Disabled              │ │
│ │ └─ [Show all 12 channels...]                           │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 💬 WhatsApp                              [3 imports]    │ │
│ │ ├─ Family Chat (2024-01-15)    ✓ Imported   Archived   │ │
│ │ ├─ Work Group (2024-02-20)     ✓ Imported   Archived   │ │
│ │ └─ [+ Import WhatsApp Chat]                            │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 📱 Slack (Acme Corp)                     [8 channels]   │ │
│ │ ├─ #general                    ✓ Enabled    Weekly     │ │
│ │ ├─ #engineering                ✓ Enabled    Daily      │ │
│ │ └─ [Connect more channels...]                          │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ 🔗 Connect New Source                                   │ │
│ │   [Discord]  [Slack]  [WhatsApp]  [Telegram]           │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 4. WhatsApp Import Discoverability

**Problem:** Users don't know to go to Retrospectives > Import for WhatsApp.

**Solutions:**

#### 4.1 Prominent Entry Points
- Add "Sources" page with WhatsApp section (see above)
- Dashboard card: "Import WhatsApp Chat" with drag-drop zone
- Landing page: Feature WhatsApp alongside Discord

#### 4.2 Import Flow Improvements
```
Current:  Retrospectives > Import > Select WhatsApp file
Proposed: Sources > WhatsApp > [+ Import Chat] > Drag & drop
          OR: Dashboard > Quick Actions > Import WhatsApp
          OR: /connect/whatsapp > Import flow
```

#### 4.3 Onboarding Wizard
For new users, show platform selection:
```
┌─────────────────────────────────────────────────────────────┐
│ Welcome to SummaryBot! What would you like to summarize?   │
│                                                             │
│   [🎮 Discord Server]     [📱 Slack Workspace]              │
│   Real-time bot           OAuth integration                │
│                                                             │
│   [💬 WhatsApp Chat]      [✈️ Telegram Group]               │
│   Import zip export       Coming soon                      │
└─────────────────────────────────────────────────────────────┘
```

### 5. Terminology Standardization

| Current (Discord) | Proposed (Agnostic) | Context |
|-------------------|---------------------|---------|
| Guild | Workspace | Top-level container |
| Server | Workspace | User-facing label |
| Channel | Source / Channel | Platform-aware |
| `#channel-name` | Platform-specific prefix | `#` Discord, none for WhatsApp |
| Member count | (omit for non-Discord) | Platform-specific |
| Category | Group (if applicable) | Discord-only concept |
| Voice channel | (omit for non-Discord) | Discord-only |
| Forum channel | (omit for non-Discord) | Discord-only |

### 6. Component Refactoring

#### 6.1 Rename Components
```
GuildLayout      → WorkspaceLayout
GuildSidebar     → WorkspaceSidebar
GuildDashboard   → WorkspaceDashboard
GuildDetail      → WorkspaceDetail
useGuild         → useWorkspace
useGuilds        → useWorkspaces
```

#### 6.2 Platform-Aware Components
```typescript
// Platform-aware channel display
function SourceItem({ source }: { source: Source }) {
  const prefix = {
    discord: "#",
    slack: "#",
    whatsapp: "",
    telegram: "",
  }[source.platform];

  const icon = {
    discord: <Hash />,
    slack: <Hash />,
    whatsapp: <MessageCircle />,
    telegram: <Send />,
  }[source.platform];

  return (
    <div className="flex items-center gap-2">
      {icon}
      <span>{prefix}{source.name}</span>
    </div>
  );
}
```

#### 6.3 Platform Context
```typescript
const PlatformContext = createContext<{
  platform: Platform;
  features: PlatformFeatures;
}>({ platform: "discord", features: defaultFeatures });

// Usage in components
function ScopeSelector() {
  const { features } = usePlatform();

  return (
    <>
      {features.hasCategories && <CategorySelect />}
      {features.hasChannelTypes && <ChannelTypeFilter />}
      <ChannelSelect />
    </>
  );
}
```

### 7. Landing Page Updates

#### Current
> "Never Miss What Matters in **Discord**"
> "SummaryBot uses AI to summarize your Discord channels..."

#### Proposed
> "Never Miss What Matters in Your **Conversations**"
> "SummaryBot uses AI to summarize Discord, Slack, and WhatsApp conversations..."

**Feature Grid:**
```
┌──────────────────┬──────────────────┬──────────────────┐
│ 🎮 Discord       │ 📱 Slack          │ 💬 WhatsApp      │
│                  │                  │                  │
│ Real-time bot    │ OAuth connect    │ Import exports   │
│ Auto-summaries   │ Channel select   │ Chat archives    │
│ Wiki generation  │ Scheduled sync   │ Full history     │
│                  │                  │                  │
│ [Add to Discord] │ [Connect Slack]  │ [Import Chat]    │
└──────────────────┴──────────────────┴──────────────────┘
```

### 8. Settings Page Platform Sections

Replace single "Discord Server" card with platform tabs:

```
┌─────────────────────────────────────────────────────────────┐
│ Connected Platforms                                         │
├─────────────────────────────────────────────────────────────┤
│ [Discord] [Slack] [WhatsApp]                                │
├─────────────────────────────────────────────────────────────┤
│ Discord Connection                          [✓ Connected]  │
│ ├─ Server: My Server                                        │
│ ├─ Server ID: 123456789                                     │
│ ├─ Members: 1,234                                           │
│ ├─ Channels: 45 (12 enabled)                                │
│ └─ [Refresh] [Disconnect]                                   │
├─────────────────────────────────────────────────────────────┤
│ Slack Connection                            [○ Not Connected]│
│ └─ [Connect Slack Workspace]                                │
├─────────────────────────────────────────────────────────────┤
│ WhatsApp Imports                            [3 chats]       │
│ ├─ Family Chat (imported 2024-01-15)                        │
│ ├─ Work Group (imported 2024-02-20)                         │
│ └─ [Import New Chat]                                        │
└─────────────────────────────────────────────────────────────┘
```

### 9. URL Structure Migration

#### Phase 1: Add New Routes (Backward Compatible)
```typescript
// Support both old and new routes
<Route path="/guilds/:id/*" element={<WorkspaceLayout />} />
<Route path="/workspaces/:id/*" element={<WorkspaceLayout />} />
```

#### Phase 2: Redirect Old Routes
```typescript
// Redirect /guilds to /workspaces
<Route path="/guilds/*" element={<Navigate to="/workspaces" replace />} />
```

### 10. Error Messages & Toast Updates

| Current | Proposed |
|---------|----------|
| "Channel list refreshed from Discord" | "Sources refreshed" |
| "Server list updated from Discord" | "Workspaces updated" |
| "Guild not found" | "Workspace not found" |
| "No servers found. Make sure SummaryBot is added to your Discord servers." | "No workspaces found. Connect Discord, Slack, or import WhatsApp chats to get started." |

### 11. Platform Badge Consistency

```typescript
const platformBadges = {
  discord: { icon: <Gamepad2 />, color: "indigo", label: "Discord" },
  slack: { icon: <Slack />, color: "purple", label: "Slack" },
  whatsapp: { icon: <MessageCircle />, color: "green", label: "WhatsApp" },
  telegram: { icon: <Send />, color: "blue", label: "Telegram" },
};

// Consistent badge rendering across all views
function PlatformBadge({ platform }: { platform: Platform }) {
  const { icon, color, label } = platformBadges[platform];
  return (
    <Badge variant="outline" className={`bg-${color}-50 text-${color}-700`}>
      {icon} {label}
    </Badge>
  );
}
```

## Implementation Phases

### Phase 1: Quick Wins (No Breaking Changes)
- [ ] Add WhatsApp import card to Dashboard
- [ ] Update landing page copy to be multi-platform
- [ ] Add "Sources" link in sidebar (alongside Channels)
- [ ] Update error messages and toasts
- [ ] Add platform badges to all summary cards

### Phase 2: Navigation Restructure
- [ ] Create unified Sources page
- [ ] Add /connect hub for new integrations
- [ ] Implement platform tabs in Settings
- [ ] Add onboarding platform selector

### Phase 3: Terminology Migration
- [ ] Rename components (Guild → Workspace)
- [ ] Update route structure with backward compat
- [ ] Migrate type definitions
- [ ] Update all UI labels

### Phase 4: Full Platform Parity
- [ ] Platform-aware channel rendering
- [ ] Platform feature flags (categories, channel types)
- [ ] Unified scheduling across platforms
- [ ] Cross-platform wiki ingestion

## Consequences

### Positive
- Better discoverability for WhatsApp and Slack features
- Clearer mental model for multi-platform users
- Easier onboarding for non-Discord users
- Foundation for adding Telegram, Teams, etc.
- More accurate marketing of capabilities

### Negative
- URL changes may break bookmarks (mitigated by redirects)
- Component renames require codebase-wide updates
- Some Discord-specific features need conditional rendering
- Documentation and help text needs comprehensive update

## Files Requiring Changes

### High Priority (User-Facing)
- `src/frontend/src/pages/Landing.tsx` - Marketing copy
- `src/frontend/src/pages/Channels.tsx` → `Sources.tsx`
- `src/frontend/src/pages/GuildDashboard.tsx` - Add WhatsApp card
- `src/frontend/src/components/layout/GuildSidebar.tsx` - Navigation

### Medium Priority (Structure)
- `src/frontend/src/App.tsx` - Route definitions
- `src/frontend/src/types/index.ts` - Type definitions
- `src/frontend/src/pages/Guilds.tsx` → `Workspaces.tsx`
- `src/frontend/src/pages/Settings.tsx` - Platform sections

### Lower Priority (Consistency)
- All components using "Guild" terminology
- Toast messages in hooks
- Error messages in components

## Metrics for Success

- WhatsApp import usage increases 3x after Sources page launch
- Slack connection rate increases after prominent placement
- User surveys show improved understanding of multi-platform capabilities
- Support tickets about "where is WhatsApp import" decrease

## References
- ADR-006: Retrospective Summary Archive (WhatsApp import)
- ADR-043: Slack Workspace Integration
- ADR-067: Platform-Aware Source Titles

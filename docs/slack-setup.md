does # Slack Integration Setup Guide

This guide covers how to create and configure a Slack App for SummaryBot integration.

For architecture details, see [ADR-043: Slack Workspace Integration](./adr/ADR-043-slack-workspace-integration-feasibility.md).

---

## Prerequisites

Before starting, ensure you have:

- **Slack workspace admin access** - Required to install apps
- **SummaryBot deployment URL** - Your dashboard must be publicly accessible (HTTPS required)
- **Discord guild configured** - Slack workspaces link to Discord guilds for access control

---

## 1. Create Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App**
3. Select **From scratch**
4. Configure:
   - **App Name**: `SummaryBot`
   - **Workspace**: Select your development workspace
5. Click **Create App**

Save the following from **Basic Information** > **App Credentials**:
- Client ID
- Client Secret
- Signing Secret

---

## 2. Configure OAuth & Permissions

Navigate to **OAuth & Permissions** in the sidebar.

### Redirect URLs

Add your OAuth callback URL:

```
{BASE_URL}/api/slack/callback
```

Replace `{BASE_URL}` with your deployment URL (e.g., `https://summarybot.example.com`).

### Bot Token Scopes

SummaryBot supports two scope tiers. Add scopes based on your needs:

#### Public-Only Tier (Recommended for most users)

| Scope | Purpose |
|-------|---------|
| `channels:history` | Read public channel messages |
| `channels:read` | List public channels |
| `users:read` | Get user display names |
| `team:read` | Get workspace info |
| `reactions:read` | Read message reactions |

#### Full Access Tier (Private channels, DMs)

Add these **in addition** to public scopes:

| Scope | Purpose |
|-------|---------|
| `groups:history` | Read private channel messages |
| `groups:read` | List private channels |
| `im:history` | Read direct messages |
| `im:read` | List DMs |
| `mpim:history` | Read group DMs |
| `mpim:read` | List group DMs |
| `files:read` | Access shared files |

> **Security Note**: Full access scopes enable reading private conversations. Summaries of private channels are restricted to workspace admins in the dashboard.

---

## 3. Configure Event Subscriptions

Navigate to **Event Subscriptions** in the sidebar.

### Enable Events

Toggle **Enable Events** to On.

### Request URL

Enter your events webhook URL:

```
{BASE_URL}/api/slack/events
```

Slack will send a verification challenge. Your server must respond with the challenge value.

### Subscribe to Bot Events

Add these bot events:

**Message Events**:
- `message.channels` - Messages in public channels
- `message.groups` - Messages in private channels (requires full access)
- `message.im` - Direct messages (requires full access)
- `message.mpim` - Group DMs (requires full access)

**Reaction Events**:
- `reaction_added`
- `reaction_removed`

**Membership Events**:
- `member_joined_channel`
- `member_left_channel`

**App Lifecycle Events**:
- `app_uninstalled`
- `tokens_revoked`

Click **Save Changes**.

---

## 4. Environment Variables

Add these environment variables to your SummaryBot deployment:

```bash
# Required
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret
SLACK_SIGNING_SECRET=your-signing-secret

# Optional
SLACK_REDIRECT_URI=https://summarybot.example.com/api/slack/callback
```

### Where to find credentials

| Variable | Location |
|----------|----------|
| `SLACK_CLIENT_ID` | Basic Information > App Credentials > Client ID |
| `SLACK_CLIENT_SECRET` | Basic Information > App Credentials > Client Secret |
| `SLACK_SIGNING_SECRET` | Basic Information > App Credentials > Signing Secret |

---

## 5. Install to Workspace

### Option A: Install via Slack App Management

1. Go to **Install App** in the sidebar
2. Click **Install to Workspace**
3. Review and authorize the requested permissions
4. The Bot User OAuth Token is stored automatically via the OAuth flow

### Option B: Install via SummaryBot Dashboard

1. Log in to SummaryBot dashboard
2. Navigate to **Settings** > **Integrations** > **Slack**
3. Click **Add Slack Workspace**
4. Select scope tier (Public or Full)
5. Authorize in Slack
6. Select channels to track

---

## 6. Link Workspace to Discord Guild

After installation, link the Slack workspace to a Discord guild:

1. In SummaryBot dashboard, go to the workspace settings
2. Select the Discord guild to link
3. Confirm the link

This enables:
- Discord guild members to view Slack summaries
- Unified access control via Discord roles
- Cross-platform summary digests

---

## 7. Testing the Integration

### Verify Connection

1. Go to **Settings** > **Slack** in the dashboard
2. Confirm workspace appears with status "Connected"
3. Check that channels are listed

### Verify Events

1. Post a message in a tracked Slack channel
2. Check SummaryBot logs for incoming event
3. Verify message appears in channel history

### Test Summary Generation

1. Select a Slack channel in the dashboard
2. Click **Generate Summary**
3. Verify summary content includes Slack messages

---

## 8. Troubleshooting

### Events URL Verification Failed

**Symptom**: Slack shows "URL didn't respond with the challenge"

**Solutions**:
1. Verify your server is accessible at the events URL
2. Check the endpoint returns the challenge value in the response body
3. Ensure HTTPS certificate is valid

### OAuth Callback Error

**Symptom**: "Invalid redirect URI" error during installation

**Solutions**:
1. Verify redirect URL in Slack app matches exactly
2. Include protocol (`https://`)
3. No trailing slash unless configured that way

### Missing Messages

**Symptom**: Messages not appearing in history

**Solutions**:
1. Check bot is a member of the channel
2. Verify correct scopes for channel type (public vs private)
3. Check event subscriptions are enabled

### Signature Verification Failed

**Symptom**: 401 errors in logs

**Solutions**:
1. Verify `SLACK_SIGNING_SECRET` matches app credentials
2. Check server clock is synchronized (timestamps validated within 5 minutes)

### Rate Limiting

**Symptom**: Slow data fetching, 429 errors

**Solutions**:
1. Slack API has strict rate limits (Tier 2: 20 req/min for history)
2. Initial sync of large workspaces may take several minutes
3. Consider upgrading to Slack Enterprise for higher limits

---

## API Endpoints Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/slack/install` | POST | Generate OAuth install URL |
| `/api/slack/callback` | GET | OAuth callback handler |
| `/api/slack/events` | POST | Events API webhook |
| `/api/slack/workspaces` | GET | List connected workspaces |
| `/api/slack/workspaces/{id}` | GET | Workspace details |
| `/api/slack/workspaces/{id}` | DELETE | Disconnect workspace |
| `/api/slack/workspaces/{id}/channels` | GET | List channels |
| `/api/slack/workspaces/{id}/sync` | POST | Sync channels/users |
| `/api/slack/status` | GET | Integration status |

---

## Security Considerations

- **Token Encryption**: Bot tokens are encrypted at rest
- **Signature Verification**: All incoming webhooks are verified using the signing secret
- **Scope Minimization**: Request only necessary scopes
- **Audit Logging**: All access to private channel summaries is logged
- **Slack Connect**: Cross-organization channels are blocked by default

For detailed security architecture, see [ADR-043 Section 8](./adr/ADR-043-slack-workspace-integration-feasibility.md#8-security-architecture).

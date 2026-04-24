# Slack Integration Setup (ADR-043)

This guide explains how to set up Slack OAuth integration for SummaryBot.

## Prerequisites

- A Slack workspace where you have admin permissions
- Access to the Fly.io deployment secrets

## 1. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Enter app name (e.g., "SummaryBot") and select your workspace
4. Click **Create App**

## 2. Configure OAuth Scopes

Navigate to **OAuth & Permissions** in the sidebar.

### Bot Token Scopes

Add the following scopes based on your needs:

#### Public Tier (Recommended)
| Scope | Description |
|-------|-------------|
| `channels:history` | Read messages in public channels |
| `channels:read` | List public channels |
| `users:read` | Get user info (names, avatars) |
| `team:read` | Get workspace info |
| `reactions:read` | Read emoji reactions |

#### Full Tier (Private channel access)
All public scopes plus:
| Scope | Description |
|-------|-------------|
| `groups:history` | Read private channel messages |
| `groups:read` | List private channels |
| `im:history` | Read DM history |
| `im:read` | List DMs |
| `mpim:history` | Read group DM history |
| `mpim:read` | List group DMs |
| `files:read` | Access shared files |

### Redirect URL

Add your OAuth callback URL:
```
https://summarybot-ng.fly.dev/api/v1/slack/callback
```

For local development:
```
http://localhost:8000/api/v1/slack/callback
```

## 3. Get Credentials

From **Basic Information** page, copy:
- **Client ID**
- **Client Secret**
- **Signing Secret**

## 4. Set Environment Variables

### Production (Fly.io)

```bash
flyctl secrets set SLACK_CLIENT_ID=your-client-id
flyctl secrets set SLACK_CLIENT_SECRET=your-client-secret
flyctl secrets set SLACK_REDIRECT_URI=https://summarybot-ng.fly.dev/api/v1/slack/callback
flyctl secrets set SLACK_SIGNING_SECRET=your-signing-secret
```

### Local Development

Add to your `.env` file:
```env
SLACK_CLIENT_ID=your-client-id
SLACK_CLIENT_SECRET=your-client-secret
SLACK_REDIRECT_URI=http://localhost:8000/api/v1/slack/callback
SLACK_SIGNING_SECRET=your-signing-secret
```

## 5. Connect a Workspace

1. Go to the SummaryBot dashboard
2. Navigate to **Slack Workspaces**
3. Click **Connect Workspace**
4. Select the Discord server to link
5. Choose access level (Public or Full)
6. Click **Continue to Slack**
7. Authorize the app in Slack

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/slack/status` | GET | Check if Slack is configured |
| `/api/v1/slack/install` | POST | Get OAuth install URL |
| `/api/v1/slack/callback` | GET | OAuth callback handler |
| `/api/v1/slack/workspaces` | GET | List connected workspaces |
| `/api/v1/slack/workspaces/{id}` | GET | Get workspace details |
| `/api/v1/slack/workspaces/{id}` | DELETE | Disconnect workspace |
| `/api/v1/slack/workspaces/{id}/sync` | POST | Sync channels/users |
| `/api/v1/slack/workspaces/{id}/channels` | GET | List workspace channels |

## Troubleshooting

### "Slack Integration Not Configured"
- Verify all four environment variables are set
- Restart the application after setting secrets

### "Could not start OAuth flow"
- Check that `SLACK_CLIENT_ID` and `SLACK_CLIENT_SECRET` are correct
- Verify `SLACK_REDIRECT_URI` matches exactly what's configured in Slack

### "Invalid redirect_uri"
- Ensure the redirect URI in Slack app settings matches `SLACK_REDIRECT_URI` exactly
- Check for trailing slashes or protocol mismatches (http vs https)

### OAuth callback errors
- `invalid_state`: OAuth state expired (try again within 10 minutes)
- `access_denied`: User cancelled the authorization
- `invalid_scope`: Scopes not enabled in Slack app settings

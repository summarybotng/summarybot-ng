# Testing Auth Bypass

This document describes how to enable test authentication bypass for the dashboard API, allowing automated testing without requiring Discord OAuth.

## Overview

The dashboard API supports a test authentication bypass that can be enabled via environment variables. When enabled, you can authenticate API requests using a secret key header instead of Discord OAuth tokens.

**⚠️ Security Warning**: Only enable this in development/testing environments. Never enable in production.

## Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `TEST_AUTH_SECRET` | Secret key that enables test auth bypass | `my_test_secret_12345` |
| `TEST_GUILD_ID` | Guild ID the test user has access to | `1234567890123456789` |

### Enabling the Bypass

1. Set the environment variables before starting the API:

```bash
export TEST_AUTH_SECRET="your_secret_key_here"
export TEST_GUILD_ID="your_test_guild_id"
```

2. Start the API server as normal.

3. Make requests using the `X-Test-Auth-Key` header:

```bash
curl -H "X-Test-Auth-Key: your_secret_key_here" \
     http://localhost:8000/api/guilds/your_test_guild_id/stored-summaries
```

## Usage Examples

### List Stored Summaries

```bash
curl -H "X-Test-Auth-Key: $TEST_AUTH_SECRET" \
     "http://localhost:8000/api/guilds/$TEST_GUILD_ID/stored-summaries"
```

### Get Summary Details

```bash
curl -H "X-Test-Auth-Key: $TEST_AUTH_SECRET" \
     "http://localhost:8000/api/guilds/$TEST_GUILD_ID/stored-summaries/SUMMARY_ID"
```

### Regenerate Summary

```bash
curl -X POST \
     -H "X-Test-Auth-Key: $TEST_AUTH_SECRET" \
     -H "Content-Type: application/json" \
     -d '{"perspective": "developer", "summary_length": "detailed"}' \
     "http://localhost:8000/api/guilds/$TEST_GUILD_ID/stored-summaries/SUMMARY_ID/regenerate"
```

### Regenerate Options

The regenerate endpoint accepts an optional JSON body with these fields:

| Field | Values | Description |
|-------|--------|-------------|
| `model` | `claude-sonnet-4-20250514`, `claude-3-5-sonnet-20241022`, `claude-3-5-haiku-20241022` | Model to use |
| `summary_length` | `brief`, `detailed`, `comprehensive` | Summary length |
| `perspective` | `general`, `developer`, `marketing`, `executive`, `support` | Summary perspective |

If no options are provided, the original settings are used.

## Running the E2E Test Script

A Python test script is provided at `tests/test_regeneration_e2e.py`:

```bash
# Full test suite
TEST_AUTH_SECRET=your_secret TEST_GUILD_ID=your_guild_id \
  python tests/test_regeneration_e2e.py

# Test specific summary
TEST_AUTH_SECRET=your_secret TEST_GUILD_ID=your_guild_id \
  python tests/test_regeneration_e2e.py --summary-id YOUR_SUMMARY_ID

# Just health check
TEST_AUTH_SECRET=your_secret TEST_GUILD_ID=your_guild_id \
  python tests/test_regeneration_e2e.py --health
```

## Running Playwright Browser Tests

Frontend E2E tests are in `src/frontend/tests/`:

```bash
cd src/frontend

# Run unit tests (no server needed)
npx playwright test tests/unit-metadata.spec.ts

# Run full E2E tests (requires dev server)
npm run dev &  # Start dev server first
npx playwright test tests/regeneration.spec.ts
```

## How It Works

The bypass is implemented in `src/dashboard/auth.py` in the `get_current_user()` function:

1. Checks if `TEST_AUTH_SECRET` environment variable is set
2. If set, looks for `X-Test-Auth-Key` header in the request
3. If the header value matches `TEST_AUTH_SECRET`, returns a mock user object
4. The mock user has access to the guild specified by `TEST_GUILD_ID`

```python
# Mock user returned when bypass is active
{
    "sub": "test_user_id",
    "username": "test_user",
    "avatar": None,
    "guilds": [TEST_GUILD_ID],
    "iat": <current_time>,
    "exp": <current_time + 24h>,
}
```

## Troubleshooting

### 401 Unauthorized

- Verify `TEST_AUTH_SECRET` environment variable is set on the server
- Verify the `X-Test-Auth-Key` header value matches exactly
- Check that the API server was restarted after setting env vars

### 403 Forbidden

- Verify `TEST_GUILD_ID` matches the guild ID in your request URL
- The test user only has access to the guild specified by `TEST_GUILD_ID`

### Bypass Not Working

- Ensure the env var is set _before_ starting the server
- Check server logs for any auth-related errors
- Verify you're hitting the correct API endpoint

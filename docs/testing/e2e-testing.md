# E2E Testing Guide

This document describes the end-to-end testing approach for SummaryBot NG.

## Overview

E2E tests use [Playwright](https://playwright.dev/) to verify both API endpoints and UI functionality against deployed environments.

## Test Categories

### 1. API Tests (Automated)

API tests verify backend functionality using the `X-Test-Auth-Key` header for authentication bypass. These run without requiring Discord OAuth.

**Requirements:**
- `ENVIRONMENT=testing` must be set on the deployment
- `TEST_AUTH_SECRET` must be configured

**Running API Tests:**

```bash
cd src/frontend

# Against deployed site
BASE_URL=https://summarybot-ng.fly.dev \
TEST_AUTH_KEY=<your-test-auth-secret> \
TEST_GUILD_ID=1283874310720716890 \
npx playwright test --grep "API:"
```

### 2. UI Tests (Manual)

Full UI tests require Discord OAuth authentication which cannot be automated without mocking. These are marked as `test.skip` with manual testing steps documented.

**Manual Testing Checklist:**

1. Log in to the dashboard via Discord OAuth
2. Navigate to the feature under test
3. Follow the documented steps in the skipped test
4. Record results

## Test Auth Bypass

The test authentication bypass allows API testing without Discord OAuth:

```typescript
// In Playwright test
const response = await request.get(`${baseUrl}/api/v1/guilds/${guildId}/feeds`, {
  headers: { 'X-Test-Auth-Key': process.env.TEST_AUTH_KEY }
});
```

**Security Notes:**
- Only enabled when `ENVIRONMENT` is `development`, `test`, `testing`, or `ci`
- Never enabled in production
- Two levels: `TEST_AUTH_SECRET` (user) and `TEST_AUTH_ADMIN_SECRET` (admin)

## Feed Preview Tests

Located in: `src/frontend/tests/feed-preview.spec.ts`

Tests the ADR-037 Phase 4 feed preview feature:

| Test | Type | Description |
|------|------|-------------|
| API: feed list returns feeds with criteria | Automated | Verifies feed listing with filter criteria |
| API: feed preview returns filtered summaries | Automated | Verifies preview endpoint returns filtered items |
| API: RSS feed returns filtered content | Automated | Verifies RSS output is properly filtered |
| UI: feed preview sheet opens on click | Manual | Verifies UI interaction (requires OAuth) |

## Running All Tests

```bash
cd src/frontend

# Run all Playwright tests
npx playwright test

# Run with visible browser
npx playwright test --headed

# Run specific test file
npx playwright test tests/feed-preview.spec.ts

# Generate HTML report
npx playwright test --reporter=html
npx playwright show-report
```

## CI/CD Integration

Tests can be integrated into CI pipelines:

```yaml
- name: Run E2E Tests
  env:
    BASE_URL: https://summarybot-ng.fly.dev
    TEST_AUTH_KEY: ${{ secrets.TEST_AUTH_SECRET }}
    TEST_GUILD_ID: "1283874310720716890"
  run: |
    cd src/frontend
    npx playwright install chromium
    npx playwright test --grep "API:"
```

## Screenshots

Screenshots are saved to `src/frontend/test-results/` on test failures or when explicitly captured:

```typescript
await page.screenshot({ path: 'test-results/my-screenshot.png', fullPage: true });
```

## Adding New Tests

1. Create test file in `src/frontend/tests/` with `.spec.ts` extension
2. Use `test.describe` to group related tests
3. Mark UI tests requiring OAuth as `test.skip` with manual steps
4. Add API tests using the request fixture for backend verification

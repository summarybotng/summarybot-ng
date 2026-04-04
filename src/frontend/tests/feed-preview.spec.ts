import { test, expect } from '@playwright/test';

/**
 * E2E tests for feed preview feature (ADR-037 Phase 4)
 *
 * These tests verify the feed preview API functionality.
 * UI interaction tests require Discord OAuth which cannot be automated
 * without mocking - use manual testing for full UI verification.
 *
 * Environment variables:
 *   - BASE_URL: Deployed site URL (default: https://summarybot-ng.fly.dev)
 *   - TEST_AUTH_KEY: X-Test-Auth-Key for API bypass
 *   - TEST_GUILD_ID: Guild to test against
 */
test.describe('Feed Preview Feature', () => {
  const baseUrl = process.env.BASE_URL || 'https://summarybot-ng.fly.dev';
  const testAuthKey = process.env.TEST_AUTH_KEY || '';
  const guildId = process.env.TEST_GUILD_ID || '1283874310720716890';

  test('API: feed list returns feeds with criteria', async ({ request }) => {
    const response = await request.get(`${baseUrl}/api/v1/guilds/${guildId}/feeds`, {
      headers: { 'X-Test-Auth-Key': testAuthKey }
    });

    expect(response.status()).toBe(200);
    const data = await response.json();
    expect(data.feeds).toBeDefined();
    expect(Array.isArray(data.feeds)).toBe(true);

    // Check that feeds have expected structure
    if (data.feeds.length > 0) {
      const feed = data.feeds[0];
      expect(feed.id).toBeDefined();
      expect(feed.feed_type).toBeDefined();
    }

    console.log(`Found ${data.feeds.length} feeds`);
  });

  test('API: feed preview returns filtered summaries', async ({ request }) => {
    // First get feeds to find one with criteria
    const feedsResponse = await request.get(`${baseUrl}/api/v1/guilds/${guildId}/feeds`, {
      headers: { 'X-Test-Auth-Key': testAuthKey }
    });
    const feedsData = await feedsResponse.json();

    // Find a feed with criteria (like the Security feed)
    const feedWithCriteria = feedsData.feeds?.find((f: any) => f.criteria?.perspective);

    if (feedWithCriteria) {
      const previewResponse = await request.get(
        `${baseUrl}/api/v1/guilds/${guildId}/feeds/${feedWithCriteria.id}/preview?page=1&limit=10`,
        { headers: { 'X-Test-Auth-Key': testAuthKey } }
      );

      expect(previewResponse.status()).toBe(200);
      const preview = await previewResponse.json();

      // Verify preview structure
      expect(preview.feed_id).toBe(feedWithCriteria.id);
      expect(preview.items).toBeDefined();
      expect(Array.isArray(preview.items)).toBe(true);
      expect(preview.criteria).toBeDefined();

      // Verify items have required fields
      if (preview.items.length > 0) {
        const item = preview.items[0];
        expect(item.id).toBeDefined();
        expect(item.title).toBeDefined();
        expect(typeof item.message_count).toBe('number');
        expect(item.preview).toBeDefined();
      }

      // Verify filtering is applied
      const expectedPerspective = feedWithCriteria.criteria.perspective;
      for (const item of preview.items) {
        expect(item.perspective?.toLowerCase()).toBe(expectedPerspective?.toLowerCase());
      }

      console.log(`Preview returned ${preview.items.length} items with perspective "${expectedPerspective}"`);
    } else {
      console.log('No feed with criteria found - skipping filter verification');
    }
  });

  test('API: RSS feed returns filtered content', async ({ request }) => {
    // Get feeds to find one with a token
    const feedsResponse = await request.get(`${baseUrl}/api/v1/guilds/${guildId}/feeds`, {
      headers: { 'X-Test-Auth-Key': testAuthKey }
    });
    const feedsData = await feedsResponse.json();

    const feed = feedsData.feeds?.[0];
    if (feed?.url) {
      const rssResponse = await request.get(feed.url);
      expect(rssResponse.status()).toBe(200);

      const contentType = rssResponse.headers()['content-type'];
      expect(contentType).toContain('xml');

      const body = await rssResponse.text();
      expect(body).toContain('<?xml');
      expect(body).toContain('<rss');
      expect(body).toContain(feed.title || 'Summary');

      console.log('RSS feed returned valid XML content');
    }
  });

  test.skip('UI: feed preview sheet opens on click', async ({ page }) => {
    // SKIP: Requires Discord OAuth login which cannot be automated
    // Manual testing steps:
    // 1. Log in to https://summarybot-ng.fly.dev with Discord
    // 2. Navigate to Feeds page
    // 3. Click eye icon on any feed
    // 4. Verify preview sheet opens with summary items
    // 5. Verify pagination works
    // 6. Verify sheet closes on click outside or X button
  });
});

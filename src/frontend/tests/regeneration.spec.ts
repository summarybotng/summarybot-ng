/**
 * E2E test for summary regeneration functionality.
 *
 * This test uses a mock API to test the frontend without requiring
 * the actual backend to be running.
 *
 * Run with: npx playwright test tests/regeneration.spec.ts
 */

import { test, expect, type Page } from '@playwright/test';

// Test configuration
const TEST_GUILD_ID = process.env.TEST_GUILD_ID || '1234567890';
const API_BASE = '/api';

// Mock data
const mockSummary = {
  id: '12abe9ef-a6c3-49bc-b152-7a2a84481aeb',
  title: 'Test Summary',
  guild_id: TEST_GUILD_ID,
  source_channel_ids: ['123456'],
  created_at: new Date().toISOString(),
  is_pinned: false,
  is_archived: false,
  tags: [],
  summary_text: 'This is a test summary with some content about discussions.',
  key_points: ['Point 1', 'Point 2', 'Point 3'],
  action_items: [
    { text: 'Do something', priority: 'high', assignee: 'User1' },
  ],
  participants: [
    { user_id: 'u1', display_name: 'User1', message_count: 10 },
  ],
  message_count: 50,
  start_time: new Date(Date.now() - 86400000).toISOString(),
  end_time: new Date().toISOString(),
  metadata: {
    model_used: 'claude-3-5-sonnet-20241022',
    summary_length: 'detailed',
    perspective: 'general',
    tokens_used: 1500,
    input_tokens: 1000,
    output_tokens: 500,
    generation_time_ms: 5000,
    grounded: true,
    reference_count: 5,
  },
  has_references: true,
  references: [
    { id: 1, author: 'User1', timestamp: new Date().toISOString(), content: 'Test message' },
  ],
  source: 'scheduled',
  source_content: '[2024-01-01 10:00] User1: Hello world',
  prompt_system: 'You are a summarization assistant.',
  prompt_user: 'Summarize the following conversation.',
};

const mockSummaryList = {
  items: [mockSummary],
  total: 1,
  page: 1,
  limit: 20,
};

// Setup mock API routes
async function setupMockApi(page: Page) {
  // Mock stored summaries list
  await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSummaryList),
      });
    } else {
      await route.continue();
    }
  });

  // Mock summary detail
  await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/${mockSummary.id}`, async (route) => {
    if (route.request().method() === 'GET') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockSummary),
      });
    } else {
      await route.continue();
    }
  });

  // Mock regenerate endpoint
  await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/${mockSummary.id}/regenerate`, async (route) => {
    const body = route.request().postDataJSON();
    console.log('Regenerate request body:', body);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        task_id: 'regen_test123',
        status: 'processing',
      }),
    });
  });

  // Mock calendar endpoint
  await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/calendar/**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ days: {} }),
    });
  });

  // Mock guilds endpoint
  await page.route('**/api/guilds', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([{
        id: TEST_GUILD_ID,
        name: 'Test Guild',
        icon: null,
        channels: [{ id: '123456', name: 'general', type: 0 }],
        member_count: 100,
        summary_count: 1,
      }]),
    });
  });

  // Mock guild detail
  await page.route(`**/api/guilds/${TEST_GUILD_ID}`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: TEST_GUILD_ID,
        name: 'Test Guild',
        icon: null,
        channels: [{ id: '123456', name: 'general', type: 0 }],
        member_count: 100,
        summary_count: 1,
      }),
    });
  });

  // Mock auth/me endpoint
  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        user: {
          id: 'test_user',
          username: 'TestUser',
          avatar: null,
        },
        guilds: [TEST_GUILD_ID],
      }),
    });
  });
}

test.describe('Summary Detail Sheet', () => {
  test.beforeEach(async ({ page }) => {
    await setupMockApi(page);
  });

  test('should display summary details correctly', async ({ page }) => {
    // Navigate to stored summaries page
    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);

    // Wait for the summary card to appear
    await page.waitForSelector('text=Test Summary', { timeout: 10000 });

    // Click on the summary to open detail sheet
    await page.click('text=Test Summary');

    // Wait for detail sheet to open
    await page.waitForSelector('[role="dialog"]', { timeout: 5000 });

    // Verify summary content is displayed
    await expect(page.locator('text=This is a test summary')).toBeVisible();

    // Verify key points are displayed
    await expect(page.locator('text=Point 1')).toBeVisible();
    await expect(page.locator('text=Point 2')).toBeVisible();

    // Verify metadata is displayed
    await expect(page.locator('text=How This Summary Was Generated')).toBeVisible();
    await expect(page.locator('text=detailed')).toBeVisible();
    await expect(page.locator('text=general')).toBeVisible();
  });

  test('should have working copy buttons', async ({ page }) => {
    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');
    await page.waitForSelector('[role="dialog"]');

    // Find and click copy button for summary
    const copyButtons = await page.locator('button:has-text("Copy")').all();
    expect(copyButtons.length).toBeGreaterThan(0);

    // Click the first copy button
    await copyButtons[0].click();

    // Verify it shows "Copied" feedback
    await expect(page.locator('text=Copied')).toBeVisible({ timeout: 2000 });
  });

  test('should open regenerate dialog', async ({ page }) => {
    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');
    await page.waitForSelector('[role="dialog"]');

    // Click regenerate button
    await page.click('button:has-text("Regenerate")');

    // Verify regenerate dialog opens
    await expect(page.locator('text=Regenerate Summary')).toBeVisible();
    await expect(page.locator('text=Customize regeneration settings')).toBeVisible();

    // Verify options dropdowns are present
    await expect(page.locator('text=Model')).toBeVisible();
    await expect(page.locator('text=Summary Length')).toBeVisible();
    await expect(page.locator('text=Perspective')).toBeVisible();
  });

  test('should submit regenerate request with options', async ({ page }) => {
    let regenerateRequestBody: any = null;

    // Intercept regenerate request to capture body
    await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/${mockSummary.id}/regenerate`, async (route) => {
      regenerateRequestBody = route.request().postDataJSON();
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          task_id: 'regen_test123',
          status: 'processing',
        }),
      });
    });

    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');
    await page.waitForSelector('[role="dialog"]');

    // Open regenerate dialog
    await page.click('button:has-text("Regenerate")');
    await page.waitForSelector('text=Regenerate Summary');

    // Select a perspective
    await page.click('text=Use original perspective');
    await page.click('text=Developer');

    // Click regenerate in dialog
    await page.locator('[role="dialog"] button:has-text("Regenerate")').last().click();

    // Verify request was made with options
    await page.waitForTimeout(1000);
    expect(regenerateRequestBody).toEqual({
      perspective: 'developer',
    });
  });

  test('should display all metadata fields', async ({ page }) => {
    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');
    await page.waitForSelector('[role="dialog"]');

    // Check for extended metadata fields
    const metadataSection = page.locator('text=How This Summary Was Generated').locator('..');

    // These should be visible based on the mock data
    await expect(page.locator('text=Input Tokens')).toBeVisible();
    await expect(page.locator('text=Output Tokens')).toBeVisible();
    await expect(page.locator('text=Generation Time')).toBeVisible();
    await expect(page.locator('text=Grounded')).toBeVisible();
    await expect(page.locator('text=References')).toBeVisible();
  });

  test('should show View Generation Details', async ({ page }) => {
    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');
    await page.waitForSelector('[role="dialog"]');

    // Click on View Generation Details
    await page.click('text=View Generation Details');

    // Verify prompts are shown
    await expect(page.locator('text=Source Messages')).toBeVisible();
    await expect(page.locator('text=System Prompt')).toBeVisible();
    await expect(page.locator('text=User Prompt')).toBeVisible();
  });
});

test.describe('Error Handling', () => {
  test('should handle missing metadata gracefully', async ({ page }) => {
    // Setup mock with minimal metadata
    const minimalSummary = {
      ...mockSummary,
      metadata: {
        summary_length: 'detailed',
        // Missing most fields
      },
    };

    await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/${mockSummary.id}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(minimalSummary),
      });
    });

    await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [minimalSummary], total: 1 }),
      });
    });

    await setupMockApi(page);

    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');

    // Should not crash - verify basic content loads
    await expect(page.locator('text=This is a test summary')).toBeVisible();
  });

  test('should handle null summary_text', async ({ page }) => {
    const nullTextSummary = {
      ...mockSummary,
      summary_text: null,
    };

    await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries/${mockSummary.id}`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(nullTextSummary),
      });
    });

    await page.route(`**/api/guilds/${TEST_GUILD_ID}/stored-summaries`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [nullTextSummary], total: 1 }),
      });
    });

    await setupMockApi(page);

    await page.goto(`/guilds/${TEST_GUILD_ID}/summaries`);
    await page.waitForSelector('text=Test Summary');
    await page.click('text=Test Summary');

    // Should not crash
    await page.waitForSelector('[role="dialog"]');
  });
});

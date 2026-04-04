import { test, expect } from '@playwright/test';

test('debug feed preview locally', async ({ page }) => {
  // Capture console errors with full details
  page.on('console', msg => {
    if (msg.type() === 'error') {
      console.log('BROWSER ERROR:', msg.text());
      msg.args().forEach(async (arg, i) => {
        try {
          const val = await arg.jsonValue();
          console.log(`  arg[${i}]:`, val);
        } catch {}
      });
    }
  });

  page.on('pageerror', err => {
    console.log('PAGE ERROR:', err.message);
    console.log('STACK:', err.stack);
  });

  // Navigate to local dev server
  await page.goto('http://localhost:8080');
  await page.waitForLoadState('networkidle');

  // Inject auth
  const authData = {"state":{"token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2MDUwNjE0NDQwMzUxNDk4NDUiLCJ1c2VybmFtZSI6Im1hcnRpbmNsZWF2ZXIuIiwiYXZhdGFyIjoiZjhhYTNhMDUwODIyNDA3NGI4NDM0NTk2YWJlZDc0YjkiLCJndWlsZHMiOlsiOTMyMzM2NDU1MDI2NjM4ODQ4IiwiMTI4Mzg3NDMxMDcyMDcxNjg5MCIsIjEzOTkzODY5MjgyMDk0NjE0MjgiLCIxNDIwMTg4NzUwMzk0MTY3NDQ3Il0sImd1aWxkX3JvbGVzIjp7IjkzMjMzNjQ1NTAyNjYzODg0OCI6ImFkbWluIiwiMTI4Mzg3NDMxMDcyMDcxNjg5MCI6ImFkbWluIiwiMTM5OTM4NjkyODIwOTQ2MTQyOCI6Im93bmVyIiwiMTQyMDE4ODc1MDM5NDE2NzQ0NyI6ImFkbWluIn0sImlhdCI6MTc3NTM0MzcxMSwiZXhwIjoxNzc1NDMwMTExfQ.ztm1N6rPi58BaGRe_fZSOpyB0PIPTbNr0gbUQ4tpILE","user":{"id":"605061444035149845","username":"martincleaver.","avatar_url":"https://cdn.discordapp.com/avatars/605061444035149845/f8aa3a0508224074b8434596abed74b9.png"},"guilds":[{"id":"932336455026638848","name":"FRC 2609 - Beaverworx","icon_url":"https://cdn.discordapp.com/icons/932336455026638848/a_d13cb36bff47c58c6d24e9aa3265e455.png","role":"admin"},{"id":"1283874310720716890","name":"Agentics Foundation","icon_url":"https://cdn.discordapp.com/icons/1283874310720716890/30da3e8b1c6bdbe49d612bc998f7e2f9.png","role":"admin"},{"id":"1399386928209461428","name":"Guelph.Dev","icon_url":null,"role":"owner"},{"id":"1420188750394167447","name":"Goose Goose Duck FRC team 11227","icon_url":"https://cdn.discordapp.com/icons/1420188750394167447/3d7101319e1b4c19c8f4f05034109b4e.png","role":"admin"}]},"version":0};

  await page.evaluate((data) => {
    localStorage.setItem('summarybot-auth', JSON.stringify(data));
  }, authData);

  // Navigate to feeds page
  await page.goto('http://localhost:8080/guilds/1283874310720716890/feeds');
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(2000);

  // Look for the preview (eye) button and click it
  // First find any buttons with Eye icon
  const buttons = await page.locator('button').all();
  console.log(`Found ${buttons.length} buttons`);

  // Click the first icon button (likely preview)
  const iconButtons = page.locator('button').filter({ has: page.locator('svg') });
  const iconCount = await iconButtons.count();
  console.log(`Found ${iconCount} icon buttons`);

  if (iconCount > 0) {
    // Click the first one (should be preview/eye)
    await iconButtons.first().click();
    await page.waitForTimeout(3000);
  }

  // Take a screenshot
  await page.screenshot({ path: 'test-results/local-debug.png', fullPage: true });
});

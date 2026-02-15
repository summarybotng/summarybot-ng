#!/usr/bin/env node
/**
 * UI Driver Script for SummaryBot Dashboard
 *
 * Usage:
 *   node scripts/ui-driver.js screenshot <url> [output.png]
 *   node scripts/ui-driver.js click <url> <selector>
 *   node scripts/ui-driver.js type <url> <selector> <text>
 *   node scripts/ui-driver.js navigate <url>
 *   node scripts/ui-driver.js eval <url> <js-expression>
 */

const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SCREENSHOTS_DIR = '/workspaces/summarybot-ng/screenshots';
const BASE_URL = process.env.APP_URL || 'https://summarybot-ng.fly.dev';
const AUTH_FILE = '/workspaces/summarybot-ng/scripts/.ui-auth.json';

// Ensure screenshots directory exists
if (!fs.existsSync(SCREENSHOTS_DIR)) {
  fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true });
}

// Load saved auth state
function loadAuthState() {
  try {
    if (fs.existsSync(AUTH_FILE)) {
      return JSON.parse(fs.readFileSync(AUTH_FILE, 'utf-8'));
    }
  } catch (e) {
    console.log('No saved auth state');
  }
  return null;
}

// Save auth state
function saveAuthState(state) {
  fs.writeFileSync(AUTH_FILE, JSON.stringify(state, null, 2));
  console.log('Auth state saved');
}

async function createBrowser() {
  return await chromium.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });
}

async function createAuthenticatedPage(browser) {
  const page = await browser.newPage();
  const authState = loadAuthState();

  if (authState && authState.token) {
    // Navigate to base URL first to set localStorage
    await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });

    // Inject auth state into localStorage
    await page.evaluate((state) => {
      localStorage.setItem('summarybot-auth', JSON.stringify({
        state: {
          token: state.token,
          user: state.user,
          guilds: state.guilds || []
        },
        version: 0
      }));
    }, authState);

    console.log(`Authenticated as: ${authState.user?.username || 'unknown'}`);
  }

  return page;
}

async function screenshot(url, outputPath) {
  const browser = await createBrowser();
  const page = await createAuthenticatedPage(browser);

  try {
    const fullUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
    console.log(`Navigating to: ${fullUrl}`);

    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });
    await page.waitForTimeout(1000); // Wait for animations

    const filename = outputPath || `screenshot-${Date.now()}.png`;
    const filepath = path.join(SCREENSHOTS_DIR, filename);

    await page.screenshot({ path: filepath, fullPage: true });
    console.log(`Screenshot saved: ${filepath}`);

    // Also output page title and URL
    const title = await page.title();
    console.log(`Page title: ${title}`);
    console.log(`Final URL: ${page.url()}`);

    return filepath;
  } finally {
    await browser.close();
  }
}

async function click(url, selector) {
  const browser = await createBrowser();
  const page = await createAuthenticatedPage(browser);

  try {
    const fullUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });

    console.log(`Clicking: ${selector}`);
    await page.click(selector);
    await page.waitForTimeout(1000);

    const filepath = path.join(SCREENSHOTS_DIR, `after-click-${Date.now()}.png`);
    await page.screenshot({ path: filepath, fullPage: true });
    console.log(`Screenshot after click: ${filepath}`);

    return filepath;
  } finally {
    await browser.close();
  }
}

async function type(url, selector, text) {
  const browser = await createBrowser();
  const page = await createAuthenticatedPage(browser);

  try {
    const fullUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });

    console.log(`Typing "${text}" into: ${selector}`);
    await page.fill(selector, text);
    await page.waitForTimeout(500);

    const filepath = path.join(SCREENSHOTS_DIR, `after-type-${Date.now()}.png`);
    await page.screenshot({ path: filepath, fullPage: true });
    console.log(`Screenshot after typing: ${filepath}`);

    return filepath;
  } finally {
    await browser.close();
  }
}

async function navigate(url) {
  const browser = await createBrowser();
  const page = await createAuthenticatedPage(browser);

  try {
    const fullUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
    console.log(`Navigating to: ${fullUrl}`);

    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });

    // Get page info
    const title = await page.title();
    const pageUrl = page.url();

    // Get visible text content summary
    const bodyText = await page.evaluate(() => {
      const body = document.body;
      return body ? body.innerText.slice(0, 2000) : '';
    });

    // Get all buttons and links
    const elements = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button')).map(b => ({
        type: 'button',
        text: b.innerText.trim().slice(0, 50),
        disabled: b.disabled
      }));
      const links = Array.from(document.querySelectorAll('a[href]')).map(a => ({
        type: 'link',
        text: a.innerText.trim().slice(0, 50),
        href: a.getAttribute('href')
      }));
      return [...buttons.slice(0, 20), ...links.slice(0, 20)];
    });

    const filepath = path.join(SCREENSHOTS_DIR, `nav-${Date.now()}.png`);
    await page.screenshot({ path: filepath, fullPage: true });

    console.log(`\n=== Page Info ===`);
    console.log(`Title: ${title}`);
    console.log(`URL: ${pageUrl}`);
    console.log(`Screenshot: ${filepath}`);
    console.log(`\n=== Interactive Elements ===`);
    elements.forEach(el => {
      if (el.text) {
        console.log(`  [${el.type}] ${el.text}${el.href ? ` -> ${el.href}` : ''}${el.disabled ? ' (disabled)' : ''}`);
      }
    });
    console.log(`\n=== Page Content Preview ===`);
    console.log(bodyText.slice(0, 1000) + (bodyText.length > 1000 ? '...' : ''));

    return filepath;
  } finally {
    await browser.close();
  }
}

async function evalJs(url, expression) {
  const browser = await createBrowser();
  const page = await createAuthenticatedPage(browser);

  try {
    const fullUrl = url.startsWith('http') ? url : `${BASE_URL}${url}`;
    await page.goto(fullUrl, { waitUntil: 'networkidle', timeout: 30000 });

    console.log(`Evaluating: ${expression}`);
    const result = await page.evaluate(expression);
    console.log(`Result:`, result);

    return result;
  } finally {
    await browser.close();
  }
}

async function setAuth(token, username) {
  // Decode JWT to extract user info (basic parsing)
  let user = { username: username || 'user' };
  try {
    const payload = JSON.parse(Buffer.from(token.split('.')[1], 'base64').toString());
    user = {
      id: payload.sub,
      username: payload.username || username || 'user',
      guilds: payload.guilds || []
    };
  } catch (e) {
    console.log('Could not decode JWT, using provided username');
  }

  const authState = {
    token,
    user,
    guilds: user.guilds || []
  };

  saveAuthState(authState);
  console.log(`Auth configured for user: ${user.username}`);
  console.log(`Guilds: ${user.guilds?.length || 0}`);
}

async function clearAuth() {
  if (fs.existsSync(AUTH_FILE)) {
    fs.unlinkSync(AUTH_FILE);
    console.log('Auth cleared');
  } else {
    console.log('No auth to clear');
  }
}

async function showAuth() {
  const authState = loadAuthState();
  if (authState) {
    console.log('Current auth state:');
    console.log(`  User: ${authState.user?.username || 'unknown'}`);
    console.log(`  User ID: ${authState.user?.id || 'unknown'}`);
    console.log(`  Guilds: ${authState.guilds?.length || 0}`);
    console.log(`  Token: ${authState.token?.slice(0, 20)}...`);
  } else {
    console.log('Not authenticated');
  }
}

async function loginWithDevToken(username) {
  const apiUrl = `${BASE_URL}/api/v1/auth/dev-token`;
  console.log(`Requesting dev token from: ${apiUrl}`);

  try {
    const response = await fetch(apiUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username || 'UIDriver',
        user_id: '999999999999999999'
      })
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      if (response.status === 403) {
        console.error('Dev auth is not enabled on the server.');
        console.error('Set DEV_AUTH_ENABLED=true environment variable on the server.');
        return false;
      }
      console.error(`Failed to get dev token: ${response.status}`, error);
      return false;
    }

    const data = await response.json();
    const authState = {
      token: data.token,
      user: {
        id: data.user.id,
        username: data.user.username,
        avatar_url: data.user.avatar_url
      },
      guilds: data.guilds.map(g => g.id)
    };

    saveAuthState(authState);
    console.log(`\nAuthenticated successfully!`);
    console.log(`  User: ${data.user.username}`);
    console.log(`  User ID: ${data.user.id}`);
    console.log(`  Guilds: ${data.guilds.length}`);
    data.guilds.forEach(g => console.log(`    - ${g.id}: ${g.name}`));
    return true;
  } catch (error) {
    console.error('Failed to connect:', error.message);
    return false;
  }
}

// Main CLI
const [,, command, ...args] = process.argv;

(async () => {
  try {
    switch (command) {
      case 'screenshot':
        await screenshot(args[0] || '/', args[1]);
        break;
      case 'click':
        await click(args[0], args[1]);
        break;
      case 'type':
        await type(args[0], args[1], args.slice(2).join(' '));
        break;
      case 'navigate':
      case 'nav':
        await navigate(args[0] || '/');
        break;
      case 'eval':
        await evalJs(args[0], args.slice(1).join(' '));
        break;
      case 'auth':
        if (args[0] === 'clear') {
          await clearAuth();
        } else if (args[0] === 'show') {
          await showAuth();
        } else if (args[0] === 'login') {
          await loginWithDevToken(args[1]);
        } else if (args[0]) {
          await setAuth(args[0], args[1]);
        } else {
          await showAuth();
        }
        break;
      default:
        console.log(`
UI Driver for SummaryBot Dashboard

Commands:
  screenshot <url> [output.png]  - Take a screenshot
  navigate <url>                 - Navigate and analyze page
  click <url> <selector>         - Click an element
  type <url> <selector> <text>   - Type into an input
  eval <url> <js-expression>     - Evaluate JavaScript
  auth login [username]          - Login using dev-token endpoint (requires DEV_AUTH_ENABLED=true on server)
  auth <token> [username]        - Set auth token manually
  auth show                      - Show current auth state
  auth clear                     - Clear saved auth

Examples:
  node scripts/ui-driver.js auth login               # Auto-login via dev-token
  node scripts/ui-driver.js screenshot /
  node scripts/ui-driver.js navigate /guilds/123/archive
  node scripts/ui-driver.js click / "button:has-text('Login')"
`);
    }
  } catch (error) {
    console.error('Error:', error.message);
    process.exit(1);
  }
})();

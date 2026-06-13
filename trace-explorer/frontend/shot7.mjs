import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:5173');
await page.waitForTimeout(5000);

await page.locator('input[placeholder*="Search"]').fill('read');
await page.waitForTimeout(500);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_search2.png', clip: { x: 0, y: 130, width: 1120, height: 500 } });

// click a "read" tool span
await page.locator('button[title="read"]').first().click();
await page.waitForTimeout(500);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_tool.png', clip: { x: 1120, y: 0, width: 480, height: 700 } });

await browser.close();

import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:5173');
await page.waitForTimeout(5000);

// click on row 9's bar
await page.locator('button[title*="19.09s"]').first().click();
await page.waitForTimeout(500);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_detail.png', fullPage: false });

// type a search query
await page.locator('input[placeholder*="Search"]').fill('read');
await page.waitForTimeout(500);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_search.png', fullPage: false });

await browser.close();

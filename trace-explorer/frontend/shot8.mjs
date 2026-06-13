import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:5173');
await page.waitForTimeout(5000);

await page.mouse.click(348, 197);
await page.waitForTimeout(300);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_collapse.png', clip: { x: 0, y: 130, width: 1120, height: 300 } });

await page.mouse.click(150, 243); // second session row
await page.waitForTimeout(1000);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot_session2.png', clip: { x: 0, y: 0, width: 1120, height: 500 } });

await browser.close();

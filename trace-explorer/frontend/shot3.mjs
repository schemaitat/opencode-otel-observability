import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:5173');
await page.waitForTimeout(5000);
// click zoom-in button several times
const zoomInBtn = page.locator('button[title="Zoom in"]');
for (let i = 0; i < 12; i++) {
  await zoomInBtn.click();
}
await page.waitForTimeout(500);
await page.screenshot({ path: '/Users/andre/projects/opencode-otel-observability/.tmp/screenshot3.png', fullPage: false });
await browser.close();

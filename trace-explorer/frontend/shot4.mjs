import { chromium } from 'playwright-core';
const browser = await chromium.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' });
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
await page.goto('http://localhost:5173');
await page.waitForTimeout(5000);

const getWidth = async () => page.evaluate(() => {
  const bars = document.querySelectorAll('[title*="880ms"], [title*="852ms"]');
  return Array.from(document.querySelectorAll('button')).filter(b => b.title && b.title.includes('ms')).map(b => b.style.width);
});

console.log('before', await getWidth());
const zoomInBtn = page.locator('button[title="Zoom in"]');
await zoomInBtn.click();
await page.waitForTimeout(300);
console.log('after 1 click', await getWidth());
await browser.close();

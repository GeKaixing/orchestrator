import { chromium } from 'playwright-core'
import path from 'node:path'

const browser = await chromium.launch({
  executablePath: path.join('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'),
  headless: true
})
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } })
const errors = []
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()) })

await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForSelector('text=达人总数', { timeout: 30000 })

const views = [
  ['RAG', 'RAG 知识库服务'],
  ['微信', '微信 Agent'],
  ['微信小店', '微信小店 Agent']
]

for (const [navText, expected] of views) {
  await page.evaluate((t) => {
    const el = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes(t))
    el?.click()
  }, navText)
  await page.waitForSelector(`text=${expected}`, { timeout: 10000 })
  await new Promise((r) => setTimeout(r, 800))
  const ok = await page.evaluate((e) => document.body.innerText.includes(e), expected)
  console.log(`nav "${navText}" -> "${expected}": ${ok ? 'OK' : 'FAIL'}`)
}

const navBtns = await page.evaluate(() =>
  [...document.querySelectorAll('[data-slot="button"]')]
    .map((b) => b.textContent?.trim())
    .filter((t) => t && t.length < 8)
)
console.log('sidebar nav items: ' + JSON.stringify(navBtns))
console.log('errors: ' + errors.length)
for (const e of errors) console.log(e)

await browser.close()
process.exit(0)

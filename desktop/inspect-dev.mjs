import { chromium } from 'playwright-core'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const chrome = '/c/Program Files/Google/Chrome/Application/chrome.exe'.replace(/^\/([a-z])/, (_m, l) => l.toUpperCase() + ':').replace(/\//g, '\\')
// fix path: /c/... -> C:\...
const exe = path.join('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe')

const browser = await chromium.launch({ executablePath: exe, headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 820 } })
const errors = []
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
page.on('console', (m) => { if (m.type() === 'error') errors.push('console.error: ' + m.text()) })

await page.goto('http://localhost:5173/', { waitUntil: 'domcontentloaded' })
await page.waitForSelector('text=达人总数', { timeout: 30000 })

const pick = async (sel) => page.evaluate((s) => {
  const el = document.querySelector(s)
  if (!el) return null
  const cs = getComputedStyle(el)
  return { bg: cs.backgroundColor, color: cs.color, border: cs.borderColor }
}, sel)

async function sample(name, sel) {
  const v = await pick(sel)
  console.log(`${name}: ${JSON.stringify(v)}`)
}

console.log('=== 监控面板 ===')
await sample('body', 'body')
await sample('brand-title', '.text-primary.font-semibold')
await sample('nav-active(监控面板)', '[data-slot="button"].bg-secondary')
const statColors = await page.evaluate(() =>
  [...document.querySelectorAll('.text-2xl')].map((el) => getComputedStyle(el).color)
)
console.log('stat-card number colors: ' + JSON.stringify(statColors))
const badgeColors = await page.evaluate(() =>
  [...document.querySelectorAll('[data-slot="badge"]')].map((el) => getComputedStyle(el).color)
)
console.log('stage badge colors: ' + JSON.stringify(badgeColors))

console.log('=== 工作流 ===')
await page.evaluate(() => { const el = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('工作流')); el?.click() })
await page.waitForSelector('text=启动任务', { timeout: 10000 })
await new Promise((r) => setTimeout(r, 800))
const btnDefs = [
  ['启动任务(primary)', '启动任务'],
  ['停止任务(destructive)', '停止任务'],
  ['自动回复(secondary)', '自动回复一轮']
]
for (const [name, t] of btnDefs) {
  const v = await page.evaluate((text) => {
    const el = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes(text))
    if (!el) return null
    const cs = getComputedStyle(el)
    return { bg: cs.backgroundColor, color: cs.color }
  }, t)
  console.log(`${name}: ${JSON.stringify(v)}`)
}

console.log('=== errors (' + errors.length + ') ===')
for (const e of errors) console.log(e)

await browser.close()
process.exit(0)

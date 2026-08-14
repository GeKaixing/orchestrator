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

await page.evaluate(() => {
  const el = [...document.querySelectorAll('button')].find((b) => b.textContent?.includes('RAG'))
  el?.click()
})
await page.waitForSelector('text=RAG 知识库服务', { timeout: 10000 })
await new Promise((r) => setTimeout(r, 1200))

const body = await page.evaluate(() => document.body.innerText)
console.log('RAG view contains 启动: ' + body.includes('启动'))
console.log('RAG view contains 部署说明: ' + body.includes('部署说明'))
console.log('RAG view contains RECRUIT_SKIP_AGENTS: ' + body.includes('RECRUIT_SKIP_AGENTS'))
console.log('nav RAG item present: ' + await page.evaluate(() =>
  [...document.querySelectorAll('[data-slot="button"]')].some((b) => b.textContent?.includes('RAG'))))
console.log('errors: ' + errors.length)
for (const e of errors) console.log(e)

await browser.close()
process.exit(0)

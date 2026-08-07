import { chromium } from 'playwright'

const BASE = 'http://localhost:5173'
const browser = await chromium.launch({
  executablePath: 'C:/Users/Lenovo/AppData/Local/ms-playwright/chromium-1234/chrome-win64/chrome.exe',
  args: ['--no-sandbox'],
})
const page = await browser.newPage({ viewport: { width: 1500, height: 900 } })
page.on('pageerror', (err) => console.log('PAGEERROR:', String(err).slice(0, 300)))
page.on('console', (m) => { if (m.type() === 'error') console.log('CONSOLE:', m.text().slice(0, 200)) })

await page.goto(BASE + '/notes')
await page.evaluate(() => localStorage.setItem('token', 'dev-token'))
await page.goto(BASE + '/notes')
await page.waitForTimeout(1800)

// 1. 通过前端按钮上传文章解析
const btn = page.locator('button', { hasText: '上传文章解析' })
console.log('上传按钮存在:', await btn.count() > 0)
await page.locator('input[type=file]').first().setInputFiles('../rag_article.md')
await page.waitForTimeout(4000)

// 2. 应自动切到思维导图 tab 并渲染
const activeTab = await page.locator('.notes-tab.active').innerText()
console.log('当前激活 tab:', activeTab.trim())
const mmCanvas = await page.locator('.wmm-canvas canvas').count()
console.log('思维导图 canvas:', mmCanvas > 0)
await page.waitForTimeout(1200)
await page.screenshot({ path: 's_mindmap2.png' })

// 3. 笔记列表应包含两篇文章
await page.locator('.notes-tab', { hasText: '全部' }).click()
await page.waitForTimeout(800)
const hasAgent = await page.locator('.note-card', { hasText: '大模型 Agent 实战指南' }).count()
const hasRag = await page.locator('.note-card', { hasText: 'RAG 检索增强生成实战' }).count()
console.log('笔记列表: Agent文章=', hasAgent > 0, 'RAG文章=', hasRag > 0)

await browser.close()
console.log('DONE')

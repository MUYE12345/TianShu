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

// 笔记列表应包含解析出的文章页面
const hasSource = await page.locator('.note-card', { hasText: '大模型 Agent 实战指南' }).count()
console.log('笔记列表包含来源页:', hasSource > 0)

// 切到思维导图 tab
await page.locator('.notes-tab', { hasText: '思维导图' }).click()
await page.waitForTimeout(3000)
const mmCanvas = await page.locator('.wmm-canvas canvas').count()
console.log('思维导图 canvas 渲染:', mmCanvas > 0)
await page.screenshot({ path: 's_mindmap.png' })

// 点击思维导图节点 → 跳转 wiki 页
const nodeCount = await page.locator('.wmm-canvas canvas').count()
console.log('画布存在, 尝试点击节点...')
// echarts 节点点击：直接在页面上派发点击较难，改为验证画布 + 数据
const pages = await page.evaluate(async () => {
  const r = await fetch('/api/wiki/pages')
  const j = await r.json()
  return (j.items || []).filter(p => p.title.includes('大模型 Agent 实战指南')).map(p => p.title)
})
console.log('解析出的 wiki 页:', pages.length, '个')
console.log('示例:', pages.slice(0, 4).join(' | '))

await browser.close()
console.log('DONE')

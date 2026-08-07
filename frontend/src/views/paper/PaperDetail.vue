<template>
  <div v-loading="loading" class="paper-page">
    <!-- ===== 顶栏 ===== -->
    <header class="pp-top">
      <button class="pp-back" @click="$router.push('/paper')">‹ 论文解析</button>
      <div class="pp-info">
        <h1 class="pp-title">{{ paper.title || '论文详情' }}</h1>
        <p v-if="paper.authors?.length" class="pp-authors">{{ paper.authors.join(', ') }}</p>
      </div>
      <span class="chip" :class="statusChip">{{ statusText }}</span>
      <div class="pp-actions">
        <button class="btn-primary" :disabled="parsing" @click="startParse">
          {{ parsing ? '解析中…' : '✦ AI 解析' }}
        </button>
      </div>
    </header>

    <!-- ===== AI 章节解读（手风琴） ===== -->
    <section v-if="analysis.length" class="pp-analysis panel">
      <div class="pa-head">AI 论文解读</div>
      <el-collapse>
        <el-collapse-item v-for="a in analysis" :key="a.title">
          <template #title><span class="pa-title">{{ a.title }}</span></template>
          <div class="pa-text">{{ a.analysis }}</div>
        </el-collapse-item>
      </el-collapse>
    </section>

    <!-- ===== 双栏对照阅读器（魔搭式：左侧真实 PDF + 段落框，点击同步翻译） ===== -->
    <section v-if="pages.length" class="pp-reader">
      <!-- 左栏：PDF 页面原图 + 段落框 -->
      <div ref="leftPane" class="pp-pane pp-orig">
        <div class="pane-head">
          <span class="pane-title">原文（PDF 原样）</span>
          <span class="pane-sub">{{ pages.length }} 页 · 点击段落框查看翻译</span>
          <span class="pane-zoom">
            <button title="缩小" @click="pageZoom = Math.max(460, pageZoom - 100)">−</button>
            <button title="适应宽度" @click="pageZoom = 760">适应</button>
            <button title="放大" @click="pageZoom = Math.min(1800, pageZoom + 100)">＋</button>
          </span>
        </div>
        <div class="pane-body">
          <div v-for="pg in pages" :key="pg.page_num" class="pp-page">
            <div class="pp-page-num">第 {{ pg.page_num }} 页</div>
            <div v-if="pg.image_url" class="pp-page-img" :style="{ width: pageZoom + 'px' }"
                 :ref="el => onPageImg(el, pg.page_num)">
              <img :src="pg.image_url" :alt="'第' + pg.page_num + '页'" loading="lazy" />
              <div v-for="(b, i) in pg.para_boxes" :key="i" class="pp-box"
                   :class="{ active: isActivePara(pg.page_num, i) }"
                   :style="boxStyle(pg.page_num, b)"
                   @mouseenter="setActive(pg.page_num, i, false)" @click="setActive(pg.page_num, i, true)">
                <span v-if="isActivePara(pg.page_num, i)" class="pp-box-idx">{{ i + 1 }}</span>
              </div>
            </div>
            <div v-else class="pp-page-text">
              <div v-for="(pt, i) in pageParasOf(pg.page_num)" :key="i" class="para" :class="{ active: isActivePara(pg.page_num, i) }"
                   @mouseenter="setActive(pg.page_num, i, false)" @click="setActive(pg.page_num, i, true)">
                <span class="para-no">{{ i + 1 }}</span>
                <div class="para-text">{{ pt.en }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="pp-divider"></div>

      <!-- 右栏：逐段翻译 -->
      <div ref="rightPane" class="pp-pane pp-trans">
        <div class="pane-head">
          <span class="pane-title">翻译 · 解读</span>
          <span class="pane-sub">点击左侧段落框，翻译自动定位</span>
        </div>
        <div class="pane-body">
          <div v-for="(para, gi) in allParas" :key="gi" class="para trans" :class="{ active: isActivePara(para.page, para.idx) }"
               :data-page="para.page" :data-idx="para.idx"
               @mouseenter="setActive(para.page, para.idx, false)" @click="setActive(para.page, para.idx, true)">
            <span class="para-no">{{ para.page }}-{{ para.idx + 1 }}</span>
            <div class="para-text" v-if="para.zh">{{ para.zh }}</div>
            <div class="para-text untrans translating" v-else-if="para.translating">
              <span class="untrans-badge">正在翻译…</span><span class="tr-dots"><i></i><i></i><i></i></span>
            </div>
            <div class="para-text untrans" v-else><span class="untrans-badge">未翻译·原文</span>{{ para.en }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 图表解读 ===== -->
    <section v-if="figures.length" class="pp-figures panel">
      <div class="pf-head">图表解读</div>
      <div class="pf-grid">
        <div v-for="fig in figures" :key="fig.id" class="pf-card">
          <p class="pf-caption">{{ fig.caption || '未命名图' }}</p>
          <div class="pf-img-wrap" v-if="figImg(fig.image_path)">
            <img :src="figImg(fig.image_path)" class="pf-img" :alt="fig.caption" />
          </div>
          <p class="pf-text">{{ fig.llm_explanation || '等待 AI 解读…' }}</p>
        </div>
      </div>
    </section>

    <el-empty v-if="!loading && pages.length === 0" description="上传论文后等待解析…" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const loading = ref(true)
const parsing = ref(false)
const paper = ref({})
const pages = ref([])
const figures = ref([])
const analysis = ref([])

const leftPane = ref(null)
const rightPane = ref(null)
const activePara = ref(null)  // {page, idx}

function figImg(path) {
  if (!path) return ''
  if (/^https?:\/\//.test(path)) return path
  if (path.startsWith('/')) return path
  return '/static/' + path.replace(/^[\\/]/, '')
}

const statusChip = computed(() => {
  const s = paper.value.status || 'pending'
  return s === 'parsed' ? 'chip-green' : s === 'error' ? 'chip-pink' : 'chip-blue'
})
const statusText = computed(() => {
  const s = paper.value.status || 'pending'
  return s === 'pending' ? '⏳ 等待处理' : s === 'ocr_done' ? '📄 OCR 完成' : s === 'parsed' ? '✅ 解析完成' : '❌ 错误'
})

/** 把一页文本切成段落：空行分界，长行兜底 */
function splitParas(text) {
  if (!text) return []
  const paras = []
  let cur = ''
  for (const raw of text.split('\n')) {
    const line = raw.trim()
    if (!line) {
      if (cur) { paras.push(cur); cur = '' }
      continue
    }
    cur += (cur ? ' ' : '') + line
    if (cur.length > 260) { paras.push(cur); cur = '' }
  }
  if (cur) paras.push(cur)
  return paras
}

/** 每页段落：优先用段落框（魔搭式），无框则回退文本切分；翻译按索引配对 */
function pageParasOf(pageNum) {
  const pg = pages.value.find(p => p.page_num === pageNum)
  if (!pg) return []
  const boxes = pg.para_boxes || []
  let enList
  if (boxes.length) enList = boxes.map(b => b.text)
  else enList = splitParas(pg.ocr_text || '')
  const zh = splitParas(pg.translated_text || '')
  const isTranslating = translatingPages.value.has(pageNum)
  return enList.map((en, i) => ({
    page: pageNum, idx: i, en,
    zh: zh[i] || '',
    translating: isTranslating && !zh[i],
    box: boxes[i] || null,
  }))
}

/** 全部页段落（右栏渲染用） */
const allParas = computed(() => {
  const out = []
  for (const pg of pages.value) out.push(...pageParasOf(pg.page_num))
  return out
})
const totalParas = computed(() => allParas.value.length)

function isActivePara(page, idx) {
  return !!(activePara.value && activePara.value.page === page && activePara.value.idx === idx)
}

/** 选中段落；scrollRight=true 时把右侧翻译滚动到对应段 */
function setActive(page, idx, scrollRight) {
  activePara.value = { page, idx }
  if (scrollRight) scrollRightTo(page, idx)
}

function scrollRightTo(page, idx) {
  if (!rightPane.value) return
  const el = rightPane.value.querySelector(`[data-page="${page}"][data-idx="${idx}"]`)
  if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
}

// 段落框：后端返回图片尺寸，换算成百分比定位（不依赖图片加载时机）
function boxStyle(pageNum, b) {
  const pg = pages.value.find(p => p.page_num === pageNum)
  if (!pg || !pg.img_w || !pg.img_h) return {}
  return {
    left: (b.x0 / pg.img_w * 100) + '%',
    top: (b.y0 / pg.img_h * 100) + '%',
    width: Math.max(0.3, (b.x1 - b.x0) / pg.img_w * 100) + '%',
    height: Math.max(0.3, (b.y1 - b.y0) / pg.img_h * 100) + '%',
  }
}

// ── 页面缩放 ──
const pageZoom = ref(760)

// ── 动态翻译：只翻左栏可视区最顶上的未翻译页，翻完自动接下一页 ──
const translatingPages = ref(new Set())
const skipTranslate = ref(new Set())  // 翻译失败/无内容的页，避免无限重试
let inFlight = 0
const pageObservers = {}
const MAX_INFLIGHT = 2

function onPageImg(el, pageNum) {
  if (!el) return
  el.dataset.page = String(pageNum)
  if (pageObservers[pageNum]) { pageObservers[pageNum].disconnect(); pageObservers[pageNum] = null }
  const obs = new IntersectionObserver((entries) => {
    if (entries[0] && entries[0].isIntersecting) requestTopmost()
  }, { root: leftPane.value, rootMargin: '120px' })
  obs.observe(el)
  pageObservers[pageNum] = obs
}

function topmostVisiblePage() {
  const pane = leftPane.value
  if (!pane) return null
  const rp = pane.getBoundingClientRect()
  let best = null, bestTop = Infinity
  for (const el of pane.querySelectorAll('.pp-page-img')) {
    const r = el.getBoundingClientRect()
    if (r.bottom > rp.top && r.top < rp.bottom) {
      const top = Math.max(r.top, rp.top)
      if (top < bestTop) { bestTop = top; best = parseInt(el.dataset.page, 10) }
    }
  }
  return best
}

function requestTopmost() {
  if (inFlight >= MAX_INFLIGHT) return
  const pn = topmostVisiblePage()
  if (pn == null) return
  const pg = pages.value.find(p => p.page_num === pn)
  if (!pg || (pg.translated_text || '').trim()) return
  if (skipTranslate.value.has(pn)) return  // 失败/无内容页不再重试
  if (translatingPages.value.has(pn)) return
  translatingPages.value = new Set([...translatingPages.value, pn])
  inFlight++
  doTranslate(pn).finally(() => { inFlight--; requestTopmost() })
}

async function doTranslate(pageNum) {
  try {
    const { data } = await request.post(`/api/paper/${route.params.id}/pages/${pageNum}/translate`)
    const pg = pages.value.find(p => p.page_num === pageNum)
    if (pg && data && data.translated_text) {
      pg.translated_text = data.translated_text
    } else if (data && data.error) {
      // 该页无可翻译内容或翻译失败：标记跳过，避免无限重试
      skipTranslate.value = new Set([...skipTranslate.value, pageNum])
    }
  } catch {
    skipTranslate.value = new Set([...skipTranslate.value, pageNum])
  }
  const s = new Set(translatingPages.value)
  s.delete(pageNum)
  translatingPages.value = s
}

onMounted(async () => {
  try {
    const [p, ps, figs] = await Promise.all([
      request.get('/api/paper/' + route.params.id),
      request.get('/api/paper/' + route.params.id + '/pages').catch(() => []),
      request.get('/api/paper/' + route.params.id + '/figures').catch(() => []),
    ])
    paper.value = p
    pages.value = ps || []
    figures.value = figs || []
    // 已解析过：自动载入缓存的章节解读
    if (p?.status === 'parsed') await loadAnalysis()
  } catch {
    ElMessage.error('加载论文详情失败')
  }
  loading.value = false
})

async function loadAnalysis() {
  try {
    const resp = await fetch('/api/paper/' + route.params.id + '/parsed')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    analysis.value = []
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'section') {
              analysis.value.push({ title: data.title, analysis: data.analysis })
            }
          } catch {}
        }
      }
    }
  } catch { /* 静默 */ }
}

const startParse = async () => {
  parsing.value = true
  analysis.value = []
  try {
    const resp = await fetch('/api/paper/' + route.params.id + '/parsed')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'section') {
              analysis.value.push({ title: data.title, analysis: data.analysis })
            }
          } catch {}
        }
      }
    }
    ElMessage.success('解析完成')
  } catch {
    ElMessage.error('需配置 API Key 或 API 不可用')
  }
  parsing.value = false
}
</script>

<style scoped>
.paper-page { padding: 4px 4px 24px; display: flex; flex-direction: column; gap: 16px; }

/* 顶栏 */
.pp-top { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.pp-back {
  border: none; background: var(--accent-soft); color: var(--text-primary);
  padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.pp-back:hover { filter: brightness(.97); }
.pp-info { flex: 1; min-width: 0; }
.pp-title { font-size: 22px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.pp-authors { font-size: 12px; color: var(--text-tertiary); margin: 4px 0 0; }
.pp-actions { display: flex; gap: 8px; }

/* AI 解读 */
.pp-analysis { padding: 16px 20px; }
.pa-head { font-size: 14px; font-weight: 700; margin-bottom: 6px; }
.pa-title { font-size: 13px; font-weight: 600; }
.pa-text { white-space: pre-wrap; line-height: 1.7; font-size: 13px; color: var(--text-secondary); }

/* 双栏阅读器 */
.pp-reader {
  display: flex; height: calc(100vh - 220px); min-height: 420px;
  border-radius: 20px; overflow: hidden;
  background: linear-gradient(155deg, var(--bg-card) 0%, var(--bg-subtle) 100%);
  border: 1px solid var(--border-light); box-shadow: var(--shadow-card);
}
.pp-divider { width: 1px; background: var(--border-input); flex-shrink: 0; margin: 48px 0; height: calc(100% - 96px); }
.pp-pane { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow: auto; }
.pane-head {
  position: sticky; top: 0; z-index: 2;
  display: flex; align-items: center; gap: 8px;
  padding: 12px 18px; background: var(--bg-card);
  border-bottom: 1px solid var(--border-light);
  backdrop-filter: blur(8px);
}
.pane-title { font-size: 13px; font-weight: 700; }
.pane-sub { font-size: 11px; color: var(--text-muted); margin-right: auto; }
.pane-zoom { display: inline-flex; gap: 4px; flex-shrink: 0; }
.pane-zoom button {
  border: 1px solid var(--border-input); background: var(--bg-subtle); color: var(--text-secondary);
  border-radius: 8px; padding: 2px 8px; font-size: 12px; cursor: pointer; line-height: 1.4;
}
.pane-zoom button:hover { background: var(--accent-soft); color: var(--text-primary); }
.pane-body { padding: 14px 18px 40px; }

/* PDF 页面图 + 段落框（魔搭式） */
.pp-page { margin-bottom: 18px; }
.pp-page-num { font-size: 11px; font-weight: 600; color: var(--text-tertiary); margin: 2px 0 6px; font-family: var(--font-mono); }
.pp-page-img { position: relative; width: 100%; margin: 0 auto; border: 1px solid var(--border-light); border-radius: 10px; overflow: hidden; background: #fff; }
.pp-page-img img { display: block; width: 100%; height: auto; }
.pp-box {
  position: absolute; border: 1px solid rgba(59, 110, 245, .45); background: rgba(59, 110, 245, .06);
  border-radius: 3px; cursor: pointer; transition: background .15s, border-color .15s;
}
.pp-box:hover { background: rgba(59, 110, 245, .14); }
.pp-box.active { background: rgba(59, 110, 245, .2); border-color: var(--primary); border-width: 1.5px; }
.pp-box-idx {
  position: absolute; top: -7px; left: -7px; width: 16px; height: 16px; border-radius: 50%;
  background: var(--primary); color: #fff; font-size: 10px; font-weight: 700;
  display: grid; place-items: center; font-family: var(--font-mono);
}
.pp-page-text { border: 1px solid var(--border-light); border-radius: 10px; padding: 4px 8px; }

/* 正在翻译动画 */
.pp-trans .para-text.translating { display: flex; align-items: center; gap: 10px; color: var(--text-tertiary); }
.tr-dots { display: inline-flex; gap: 4px; }
.tr-dots i { width: 6px; height: 6px; border-radius: 50%; background: var(--tz-blue); animation: pulse 1.4s infinite; }
.tr-dots i:nth-child(2) { animation-delay: .2s; }
.tr-dots i:nth-child(3) { animation-delay: .4s; }

.para { display: flex; gap: 10px; padding: 10px 8px; border-radius: 12px; transition: background .15s; border-left: 2px solid transparent; }
.para.active { background: var(--bg-hover); border-left-color: var(--tz-blue); }
.para.trans.active { border-left-color: var(--tz-green); }
.para-no {
  flex-shrink: 0; width: 22px; height: 22px; border-radius: 6px;
  display: grid; place-items: center; font-size: 10px; font-weight: 700;
  background: var(--bg-hover); color: var(--text-tertiary); margin-top: 2px;
  font-family: var(--font-mono);
}
.para.active .para-no { background: var(--bg-card); color: var(--text-secondary); box-shadow: var(--shadow-soft); }
.para-text { font-size: 13.5px; line-height: 1.75; color: var(--text-primary); white-space: pre-wrap; min-width: 0; }
.pp-trans .para-text { color: var(--text-secondary); }
.pp-trans .para-text.untrans { color: var(--text-muted); opacity: .82; }
.untrans-badge {
  display: inline-block; font-size: 10px; font-weight: 600; color: var(--text-tertiary);
  background: var(--bg-hover); border-radius: 999px; padding: 1px 8px; margin-right: 8px; vertical-align: middle;
}
.para-missing { font-size: 12px; color: var(--text-muted); font-style: italic; }

/* 图表 */
.pp-figures { padding: 16px 20px; }
.pf-head { font-size: 14px; font-weight: 700; margin-bottom: 12px; }
.pf-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
.pf-card { border: 1px solid var(--border-light); border-radius: 14px; padding: 12px; background: var(--bg-card); }
.pf-caption { font-size: 12px; font-weight: 600; margin: 0 0 8px; }
.pf-img-wrap { border-radius: 10px; overflow: hidden; margin-bottom: 8px; background: #fff; }
.pf-img { width: 100%; display: block; }
.pf-text { font-size: 12px; color: var(--text-secondary); line-height: 1.6; margin: 0; white-space: pre-wrap; }
</style>

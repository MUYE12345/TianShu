<template>
  <div class="artifact-preview">
    <!-- 网页报告 / PDF：iframe 直接渲染 -->
    <iframe v-if="artifact.kind === 'html'" :src="artifact.url" class="ap-frame" title="网页报告" />

    <!-- PPT：按 # 一级标题拆成幻灯片卡片（模板决定底色） -->
    <div v-else-if="artifact.kind === 'ppt'" class="ap-slides" :class="'tpl-' + (artifact.template === '商务深色' ? 'dark' : artifact.template === '科技渐变' ? 'tech' : 'white')">
      <div v-for="(s, i) in slides" :key="i" class="ap-slide">
        <div class="ap-slide-title">{{ s.title }}</div>
        <div class="ap-slide-body" v-html="renderMd(s.body)" />
      </div>
    </div>

    <!-- 思维导图：Markdown 标题 → 缩进树 -->
    <div v-else-if="artifact.kind === 'mindmap'" class="ap-mindmap">
      <div v-for="(n, i) in flatTree" :key="i" class="ap-tree-row" :style="{ paddingLeft: (n.depth * 18) + 'px' }">
        <span class="ap-tree-dot" :class="{ root: n.depth === 0 }"></span>
        <span class="ap-tree-text">{{ n.text }}</span>
      </div>
    </div>

    <!-- 时间轴：JSON 节点 → 竖向时间轴（设计稿 img_32） -->
    <div v-else-if="artifact.kind === 'timeline'" class="ap-timeline">
      <div v-for="(n, i) in timelineNodes" :key="i" class="tl-node">
        <div class="tl-rail"><span class="tl-dot"></span><span v-if="i < timelineNodes.length - 1" class="tl-line"></span></div>
        <div class="tl-card">
          <div class="tl-date">{{ n.date }}</div>
          <div class="tl-title">{{ n.title }}</div>
          <div v-if="n.detail" class="tl-detail">{{ n.detail }}</div>
        </div>
      </div>
      <div v-if="!timelineNodes.length" class="ap-md" v-html="renderMd(artifact.markdown || '（时间轴数据解析失败）')" />
    </div>

    <!-- 简报 / 其他 markdown：直接渲染 -->
    <div v-else class="ap-md" v-html="renderMd(artifact.markdown || '')" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  artifact: { type: Object, required: true },
})

// 时间轴节点：拉取产物 JSON 文件解析
const timelineNodes = ref([])
onMounted(async () => {
  if (props.artifact.kind !== 'timeline') return
  try {
    const res = await fetch(props.artifact.url)
    const text = await res.text()
    const parsed = JSON.parse(text)
    if (Array.isArray(parsed)) timelineNodes.value = parsed
  } catch { timelineNodes.value = [] }
})

const md = new MarkdownIt({ html: true, linkify: true, typographer: true, breaks: true })

function renderMd(text) {
  if (!text) return ''
  return md.render(text)
}

// PPT 拆分：以 `# ` 开头的为页标题
const slides = computed(() => {
  const mdText = props.artifact.markdown || props.artifact.prompt || ''
  const parts = mdText.split(/^# /m).filter(p => p.trim())
  if (parts.length === 0) return []
  return parts.map(p => {
    const lines = p.split('\n')
    return { title: lines[0].trim(), body: lines.slice(1).join('\n') }
  })
})

// 思维导图：解析标题层级 → 扁平化（depth, text），避免递归组件
const flatTree = computed(() => {
  const lines = (props.artifact.markdown || '').split('\n')
  const root = { text: props.artifact.title || '思维导图', depth: 0 }
  const result = []
  const stack = [{ level: 0, node: root }]
  for (const line of lines) {
    const m = line.match(/^(#{1,4})\s+(.*)/)
    if (!m) continue
    const level = m[1].length
    while (stack.length > 1 && stack[stack.length - 1].level >= level) stack.pop()
    const node = { text: m[2].trim(), depth: stack[stack.length - 1].node.depth + 1 }
    result.push(node)
    stack.push({ level, node })
  }
  return [root, ...result]
})
</script>

<style scoped>
.artifact-preview { min-height: 100px; }
.ap-frame { width: 100%; height: 560px; border: 1px solid var(--border); border-radius: 8px; background: #fff; }
.ap-md { font-size: 14px; line-height: 1.8; color: var(--text-primary); }
.ap-md :deep(p) { margin: 0.5em 0; }
.ap-md :deep(h1), .ap-md :deep(h2), .ap-md :deep(h3) { margin: 12px 0 6px; }
.ap-md :deep(pre) { background: var(--bg-subtle); padding: 10px; border-radius: 6px; overflow-x: auto; }
.ap-md :deep(code) { background: var(--bg-subtle); padding: 1px 5px; border-radius: 4px; }
.ap-md :deep(a) { color: var(--primary); }

.ap-slides { display: flex; flex-direction: column; gap: 12px; }
.ap-slide { border: 1px solid var(--border); border-radius: 14px; padding: 22px 26px; background: var(--bg-card); aspect-ratio: 16 / 8.2; overflow: hidden; }
.ap-slide-title { font-size: 18px; font-weight: 700; margin-bottom: 10px; color: var(--text-primary); letter-spacing: -0.01em; }
.ap-slide-body { font-size: 13px; line-height: 1.7; color: var(--text-secondary); }
.tpl-dark .ap-slide { background: #212121; border-color: #212121; }
.tpl-dark .ap-slide-title { color: #ffffff; }
.tpl-dark .ap-slide-body { color: rgba(255, 255, 255, .78); }
.tpl-tech .ap-slide { background: linear-gradient(150deg, #182044, #232c5c); border-color: #182044; }
.tpl-tech .ap-slide-title { color: #ebf0ff; }
.tpl-tech .ap-slide-body { color: rgba(235, 240, 255, .8); }

/* 时间轴 */
.ap-timeline { padding: 8px 0; }
.tl-node { display: flex; gap: 12px; }
.tl-rail { display: flex; flex-direction: column; align-items: center; width: 12px; flex-shrink: 0; }
.tl-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--tz-green); margin-top: 5px; box-shadow: 0 0 0 3px var(--tz-green-soft); }
.tl-line { flex: 1; width: 2px; background: var(--border-input); margin: 4px 0; }
.tl-card { padding-bottom: 18px; min-width: 0; }
.tl-date { font-size: 11px; font-weight: 700; color: var(--tz-green-ink); font-family: var(--font-mono); }
.tl-title { font-size: 13px; font-weight: 600; margin-top: 3px; color: var(--text-primary); }
.tl-detail { font-size: 12px; color: var(--text-tertiary); margin-top: 3px; line-height: 1.6; }

.ap-mindmap { padding: 8px 0; display: flex; flex-direction: column; gap: 6px; }
.ap-tree-row { display: flex; align-items: center; gap: 8px; }
.ap-tree-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--primary); flex-shrink: 0;
}
.ap-tree-dot.root { width: 10px; height: 10px; background: var(--primary-dark); }
.ap-tree-text { font-size: 13px; color: var(--text-primary); }
</style>

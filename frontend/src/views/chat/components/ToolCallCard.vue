<template>
  <div class="tool-call-wrapper" :class="['tool-type-' + toolType, 'status-' + toolCall.status]">
    <!-- 头部行（可点击折叠） -->
    <div class="tool-header" @click="toggleExpand">
      <div class="tool-header-left">
        <span class="tool-icon" :style="{ color: typeConfig.color, background: typeConfig.bg }" v-html="typeConfig.icon"></span>
        <span class="tool-name">{{ toolCall.name }}</span>
        <span class="tool-status-badge" :class="toolCall.status">
          <template v-if="toolCall.status === 'running'">
            <span class="running-dot"></span>
            执行中
          </template>
          <template v-else-if="toolCall.status === 'done'">✓ 完成</template>
          <template v-else>✕ 错误</template>
        </span>
      </div>
      <div class="tool-header-right">
        <span class="tool-type-label">{{ typeConfig.label }}</span>
        <svg
          class="expand-icon" :class="{ rotated: isExpanded }"
          width="12" height="12" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
    </div>

    <!-- 可展开详情 -->
    <transition name="expand">
      <div v-show="isExpanded" class="tool-details">
        <!-- 输入参数 -->
        <div v-if="hasArgs" class="detail-section">
          <div class="detail-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 3 21 3 21 8"/><line x1="4" y1="20" x2="21" y2="3"/><polyline points="21 16 21 21 16 21"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="4" y1="4" x2="9" y2="9"/></svg>
            输入参数
          </div>
          <div class="detail-body">
            <pre class="detail-pre">{{ formattedArgs }}</pre>
          </div>
        </div>
        <!-- 执行结果 -->
        <div v-if="hasResult" class="detail-section">
          <div class="detail-label">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="21 12 15 12 12 21 9 3 6 12 3 12"/></svg>
            执行结果
          </div>
          <div class="detail-body result-body">
            <pre class="detail-pre">{{ formattedResult }}</pre>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  toolCall: { type: Object, required: true },
  expanded: { type: Boolean, default: null }
})

const emit = defineEmits(['update:expanded'])

// ── 工具类型分类（带 inline SVG 图标） ──
const typeConfigMap = {
  search: {
    color: '#409EFF', bg: 'rgba(64,158,255,0.10)',
    label: '搜索',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>'
  },
  file: {
    color: '#67C23A', bg: 'rgba(103,194,58,0.10)',
    label: '文件',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>'
  },
  code: {
    color: '#E6A23C', bg: 'rgba(230,162,60,0.10)',
    label: '代码',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>'
  },
  image: {
    color: '#9B59B6', bg: 'rgba(155,89,182,0.10)',
    label: '图片',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>'
  },
  content: {
    color: '#00BCD4', bg: 'rgba(0,188,212,0.10)',
    label: '内容',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>'
  },
  knowledge: {
    color: '#FF9800', bg: 'rgba(255,152,0,0.10)',
    label: '知识',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>'
  },
  other: {
    color: '#909399', bg: 'rgba(144,147,153,0.10)',
    label: '工具',
    icon: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
  }
}

function classifyToolType(name) {
  const n = (name || '').toLowerCase()
  if (/search|web|baidu|bing|google|fetch|crawl|http|url|scrape/i.test(n)) return 'search'
  if (/file|read|write|create|delete|fs|dir|folder|rename|move|copy|path/i.test(n)) return 'file'
  if (/code|shell|bash|python|execute|run|terminal|sh|cmd|powershell|script/i.test(n)) return 'code'
  if (/image|screenshot|vision|ocr|picture|photo|screen|capture/i.test(n)) return 'image'
  if (/news|paper|arxiv|article|rss|daily/i.test(n)) return 'content'
  if (/wiki|note|knowledge|graph|mind/i.test(n)) return 'knowledge'
  return 'other'
}

const toolType = computed(() => classifyToolType(props.toolCall.name))
const typeConfig = computed(() => typeConfigMap[toolType.value])

// ── 展开状态 ──
const internalExpanded = ref(props.toolCall.status === 'running' || props.toolCall.status === 'error')

const isExpanded = computed(() => {
  if (props.expanded !== null) return props.expanded
  return internalExpanded.value
})

watch(() => props.toolCall.status, (status) => {
  if (status === 'running' || status === 'error') {
    internalExpanded.value = true
  }
})

function toggleExpand() {
  internalExpanded.value = !isExpanded.value
  emit('update:expanded', internalExpanded.value)
}

// ── 格式化 ──
const hasArgs = computed(() => {
  const a = props.toolCall.args
  return a !== null && a !== undefined && a !== ''
})

const hasResult = computed(() => {
  const r = props.toolCall.result
  return r !== null && r !== undefined && r !== ''
})

const formattedArgs = computed(() => {
  const a = props.toolCall.args
  if (!a) return ''
  if (typeof a === 'string') return a
  try { return JSON.stringify(a, null, 2) } catch { return String(a) }
})

const formattedResult = computed(() => {
  const r = props.toolCall.result
  if (!r) return ''
  if (typeof r === 'string') return r
  try { return JSON.stringify(r, null, 2) } catch { return String(r) }
})
</script>

<style scoped>
.tool-call-wrapper {
  margin: 6px 0 6px 44px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  overflow: hidden;
  transition: all 0.2s;
  border-left: 3px solid #909399;
}
.tool-call-wrapper:hover {
  box-shadow: 0 1px 6px rgba(0,0,0,0.04);
}
.tool-call-wrapper.tool-type-search  { border-left-color: #409EFF; }
.tool-call-wrapper.tool-type-file    { border-left-color: #67C23A; }
.tool-call-wrapper.tool-type-code    { border-left-color: #E6A23C; }
.tool-call-wrapper.tool-type-image   { border-left-color: #9B59B6; }
.tool-call-wrapper.tool-type-content { border-left-color: #00BCD4; }
.tool-call-wrapper.tool-type-knowledge { border-left-color: #FF9800; }

html.dark .tool-call-wrapper {
  border-color: #2a2a48;
  background: #151528;
}

.tool-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
  transition: background 0.15s;
}
.tool-header:hover {
  background: var(--bg-subtle);
}
.tool-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.tool-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.tool-icon {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.tool-icon :deep(svg) {
  stroke: currentColor;
}

.tool-name {
  font-weight: 500;
  font-size: 13px;
  color: var(--text-primary);
  transition: color 0.15s;
  word-break: break-all;
}
.tool-header:hover .tool-name {
  color: var(--primary);
}

.tool-status-badge {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.tool-status-badge.running {
  background: #eff6ff;
  color: #3b82f6;
}
.tool-status-badge.done {
  background: #f0fdf4;
  color: #22c55e;
}
.tool-status-badge.error {
  background: #fef2f2;
  color: #ef4444;
}
html.dark .running { background: rgba(59,130,246,0.15); }
html.dark .done { background: rgba(34,197,94,0.15); }
html.dark .error { background: rgba(239,68,68,0.15); }

.running-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #3b82f6;
  animation: dotPulse 1.2s ease-in-out infinite;
}
@keyframes dotPulse {
  0%, 100% { opacity: 0.4; transform: scale(0.8); }
  50% { opacity: 1; transform: scale(1); }
}

.tool-type-label {
  font-size: 10px;
  color: var(--text-tertiary);
  background: var(--bg-subtle);
  padding: 2px 6px;
  border-radius: 4px;
  font-weight: 500;
  letter-spacing: 0.3px;
}

.expand-icon {
  color: #bbb;
  transition: transform 0.25s;
}
.expand-icon.rotated {
  transform: rotate(180deg);
}

/* ── 详情 ── */
.tool-details {
  border-top: 1px solid var(--border-light);
  padding: 8px 12px 10px;
}
.detail-section {
  margin-bottom: 8px;
}
.detail-section:last-child {
  margin-bottom: 0;
}
.detail-label {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 4px;
  font-weight: 500;
}
.detail-body {
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  max-height: 180px;
  overflow-y: auto;
  padding: 8px 10px;
}
.detail-body.result-body {
  background: #f0f9eb;
  border-color: #e1f3d8;
}
html.dark .detail-body.result-body {
  background: rgba(34,197,94,0.06);
  border-color: rgba(34,197,94,0.15);
}
.detail-pre {
  margin: 0;
  font-family: var(--font-mono, 'Cascadia Code', 'Fira Code', 'Consolas', monospace);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── 展开动画 ── */
.expand-enter-active, .expand-leave-active {
  transition: all 0.2s ease;
  overflow: hidden;
}
.expand-enter-from, .expand-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.expand-enter-to, .expand-leave-from {
  opacity: 1;
  max-height: 400px;
}
</style>

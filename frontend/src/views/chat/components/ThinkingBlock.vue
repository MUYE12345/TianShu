<template>
  <div v-if="steps && steps.length > 0" class="thinking-block-wrapper" :class="{ 'is-streaming': streaming }">
    <!-- 折叠头部 -->
    <div class="thinking-header" @click="open = !open">
      <div class="thinking-header-left">
        <span class="thinking-indicator" :class="{ active: streaming }">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
        </span>
        <span class="thinking-title">思考过程</span>
        <span class="thinking-count">{{ steps.length }} 步</span>
      </div>
      <div class="thinking-header-right">
        <svg
          class="collapse-arrow" :class="{ rotated: open }"
          width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
          stroke-linecap="round" stroke-linejoin="round"
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </div>
    </div>

    <!-- 时间线主体 -->
    <transition name="collapse">
      <div v-show="open" class="thinking-body">
        <div class="timeline">
          <div
            v-for="(step, idx) in steps"
            :key="step.id || idx"
            class="timeline-item"
            :class="['step-' + (step.type || 'think')]"
          >
            <div class="timeline-dot" :style="{ background: getStepColor(step.type) }">
              <component :is="getStepIcon(step.type)" />
            </div>
            <div class="timeline-content">
              <span class="step-type-label" :style="{ color: getStepColor(step.type) }">{{ getStepLabel(step.type) }}</span>
              <span class="step-text">{{ step.content }}</span>
            </div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, markRaw } from 'vue'

defineProps({
  steps: { type: Array, default: () => [] },
  title: { type: String, default: '思考过程' },
  streaming: { type: Boolean, default: false }
})

// 默认折叠（类 tianzhi2 风格：仅显示标题栏，点击展开）
const open = ref(false)

// ── 步骤类型定义 ──
const stepStyles = {
  plan:         { color: '#409EFF', label: '规划', icon: 'plan' },
  think:        { color: '#E6A23C', label: '思考', icon: 'think' },
  agent_start:  { color: '#909399', label: '智能体', icon: 'agent' },
  agent_result: { color: '#67C23A', label: '完成', icon: 'done' },
  tool:         { color: '#9B59B6', label: '工具', icon: 'tool' }
}

function getStepColor(type) { return stepStyles[type]?.color || '#909399' }
function getStepLabel(type) { return stepStyles[type]?.label || '步骤' }

// 图标组件（使用内联 SVG 避免依赖 Element Plus 图标）
const iconMap = {
  plan: markRaw({
    template: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>'
  }),
  think: markRaw({
    template: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.52-1.08A2.5 2.5 0 0 1 5 12.5 2.5 2.5 0 0 1 6.5 10a2.5 2.5 0 0 1 3-2.48V4.5A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 1 17 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.52-1.08A2.5 2.5 0 0 1 10 12.5 2.5 2.5 0 0 1 11.5 10a2.5 2.5 0 0 1 3-2.48V4.5A2.5 2.5 0 0 1 14.5 2Z"/></svg>'
  }),
  agent: markRaw({
    template: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="5"/><path d="M3 21v-2a7 7 0 0 1 7-7h4a7 7 0 0 1 7 7v2"/></svg>'
  }),
  done: markRaw({
    template: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>'
  }),
  tool: markRaw({
    template: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>'
  })
}

function getStepIcon(type) {
  const name = stepStyles[type]?.icon || 'think'
  const comp = iconMap[name]
  if (!comp) return 'span'
  return comp
}
</script>

<style scoped>
.thinking-block-wrapper {
  margin: 0 0 6px 0;
  width: 100%;
  border: 1px solid #e8e0f0;
  border-radius: 12px;
  background: #faf8ff;
  overflow: hidden;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.thinking-block-wrapper.is-streaming {
  border-color: #c4b5e3;
  box-shadow: 0 0 0 1px rgba(167,139,207,0.1);
}

html.dark .thinking-block-wrapper {
  background: #14142a;
  border-color: #2a2a48;
}
html.dark .thinking-block-wrapper.is-streaming {
  border-color: #5a4a8a;
}

.thinking-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  cursor: pointer;
  user-select: none;
  background: #f5f0ff;
  border-bottom: 1px solid #e8e0f0;
  transition: background 0.15s;
}
.thinking-header:hover {
  background: #efe8ff;
}
html.dark .thinking-header {
  background: #1a1a34;
  border-bottom-color: #2a2a48;
}
html.dark .thinking-header:hover {
  background: #1f1f3a;
}

.thinking-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.thinking-header-right {
  display: flex;
  align-items: center;
}

.thinking-indicator {
  display: flex;
  color: #8b5cf6;
  transition: all 0.3s;
}
.thinking-indicator.active {
  animation: thinkPulse 1.5s ease-in-out infinite;
  color: #7c3aed;
}
@keyframes thinkPulse {
  0%, 100% { opacity: 0.5; transform: scale(1); }
  50% { opacity: 1; transform: scale(1.1); }
}

.thinking-title {
  font-weight: 600;
  font-size: 13px;
  color: #6d4fa8;
}
html.dark .thinking-title {
  color: #a78bcf;
}

.thinking-count {
  font-size: 11px;
  color: #9ca3af;
  background: #e8e0f0;
  padding: 1px 7px;
  border-radius: 8px;
}
html.dark .thinking-count {
  background: #2a2a48;
  color: #8b8ba8;
}

.collapse-arrow {
  color: #9ca3af;
  transition: transform 0.25s;
}
.collapse-arrow.rotated {
  transform: rotate(180deg);
}

/* ── 主体 ── */
.thinking-body {
  padding: 10px 14px 6px;
}

.timeline {
  position: relative;
  padding-left: 20px;
}
.timeline::before {
  content: '';
  position: absolute;
  left: 6px;
  top: 8px;
  bottom: 8px;
  width: 2px;
  background: #e5d9f5;
  border-radius: 1px;
}
html.dark .timeline::before {
  background: #2a2a48;
}

.timeline-item {
  display: flex;
  gap: 10px;
  padding-bottom: 10px;
  position: relative;
}
.timeline-item:last-child {
  padding-bottom: 4px;
}

.timeline-dot {
  position: absolute;
  left: -18px;
  top: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  z-index: 1;
  flex-shrink: 0;
}
.timeline-dot :deep(svg) {
  width: 8px;
  height: 8px;
  stroke: #fff;
  stroke-width: 2.5;
}

.timeline-content {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  flex-wrap: wrap;
}

.step-type-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  flex-shrink: 0;
}

.step-text {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
}

/* ── 折叠动画 ── */
.collapse-enter-active, .collapse-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}
.collapse-enter-from, .collapse-leave-to {
  opacity: 0;
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
}
.collapse-enter-to, .collapse-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>

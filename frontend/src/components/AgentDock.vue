<template>
  <aside
    :class="['agent-dock', `agent-dock--${position}`, { 'agent-dock--collapsed': collapsed }]"
    @mouseenter="collapsed = false"
    @mouseleave="collapsed = true"
  >
    <!-- Dock header -->
    <div class="dock-header" :title="$t?.agent?.dock?.title || '智能体'">
      <el-icon :size="18"><Robot /></el-icon>
      <transition name="dock-fade">
        <span v-show="!collapsed" class="dock-label">智能体</span>
      </transition>
    </div>

    <div class="dock-divider" />

    <!-- Agent icons -->
    <nav class="dock-nav">
      <div
        v-for="agent in visibleAgents"
        :key="agent.id"
        :class="[
          'dock-item',
          { 'dock-item--active': activeAgentId === agent.id },
          { 'dock-item--disabled': !agent.enabled },
        ]"
        :title="agent.name"
        @click="handleSelect(agent)"
      >
        <div class="dock-icon">
          <span class="dock-icon-text">{{ getInitial(agent.name) }}</span>
          <span :class="['dock-status', agent.enabled ? 'dock-status--online' : 'dock-status--offline']" />
        </div>
        <transition name="dock-fade">
          <span v-show="!collapsed" class="dock-label dock-label--name">{{ agent.name }}</span>
        </transition>
      </div>
    </nav>

    <!-- Dock footer -->
    <div class="dock-footer">
      <div class="dock-divider" />
      <div
        class="dock-item dock-item--manage"
        title="管理智能体"
        @click="handleManage"
      >
        <el-icon :size="18"><Setting /></el-icon>
        <transition name="dock-fade">
          <span v-show="!collapsed" class="dock-label">管理</span>
        </transition>
      </div>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Robot, Setting } from '@element-plus/icons-vue'

const props = defineProps({
  agents: { type: Array, default: () => [] },
  activeAgentId: { type: [Number, String], default: null },
  position: { type: String, default: 'right' }, // 'left' | 'right'
  collapsedByDefault: { type: Boolean, default: true },
})

const emit = defineEmits(['select', 'manage'])

const router = useRouter()
const collapsed = ref(props.collapsedByDefault)

const visibleAgents = computed(() => {
  return props.agents.filter((a) => a.enabled)
})

function getInitial(name) {
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
}

function handleSelect(agent) {
  emit('select', agent)
}

function handleManage() {
  emit('manage')
  router.push('/agent')
}
</script>

<style scoped>
.agent-dock {
  position: fixed;
  top: 50%;
  transform: translateY(-50%);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 8px 6px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border-light, #e4e7ed);
  border-radius: 12px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  transition: width 0.25s ease, padding 0.25s ease, transform 0.25s ease, opacity 0.25s ease;
  width: auto;
  min-width: 44px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.agent-dock--left {
  left: 8px;
}

.agent-dock--right {
  right: 8px;
}

.agent-dock--collapsed {
  padding: 8px 6px;
  cursor: pointer;
}

.agent-dock:hover {
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.15);
}

/* ── Header ── */
.dock-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  color: var(--primary, #409eff);
  font-weight: 600;
  font-size: 12px;
  width: 100%;
  user-select: none;
}

.dock-divider {
  width: 80%;
  height: 1px;
  background: var(--border-light, #e4e7ed);
  margin: 2px 0;
}

/* ── Nav ── */
.dock-nav {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
}

/* ── Item ── */
.dock-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s, transform 0.15s;
  width: 100%;
  color: var(--text-secondary, #909399);
  white-space: nowrap;
  overflow: hidden;
}

.dock-item:hover {
  background: var(--primary-light, #ecf5ff);
  color: var(--primary, #409eff);
  transform: scale(1.02);
}

.dock-item--active {
  background: var(--primary-light, #ecf5ff);
  color: var(--primary, #409eff);
}

.dock-item--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.dock-item--manage {
  margin-top: 2px;
  color: var(--text-secondary, #909399);
  font-size: 12px;
}

.dock-item--manage:hover {
  color: var(--primary, #409eff);
}

/* ── Icon ── */
.dock-icon {
  position: relative;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-light, #ecf5ff);
  color: var(--primary, #409eff);
  flex-shrink: 0;
  font-weight: 700;
  font-size: 13px;
  transition: background 0.2s;
}

.dock-item:hover .dock-icon {
  background: var(--primary, #409eff);
  color: #fff;
}

.dock-item--active .dock-icon {
  background: var(--primary, #409eff);
  color: #fff;
}

.dock-icon-text {
  line-height: 1;
  user-select: none;
}

/* ── Status dot ── */
.dock-status {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 2px solid var(--bg-card, #fff);
  transition: background 0.2s;
}

.dock-status--online {
  background: #67c23a;
}

.dock-status--offline {
  background: #c0c4cc;
}

/* ── Label ── */
.dock-label {
  font-size: 12px;
  line-height: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
}

.dock-label--name {
  font-weight: 500;
}

/* ── Transitions ── */
.dock-fade-enter-active,
.dock-fade-leave-active {
  transition: opacity 0.2s ease;
}

.dock-fade-enter-from,
.dock-fade-leave-to {
  opacity: 0;
}

/* ── Dark mode compatibility ── */
html.dark .agent-dock {
  background: var(--bg-card);
  border-color: var(--border-light);
}

html.dark .dock-item:hover {
  background: rgba(79, 110, 247, 0.15);
}

html.dark .dock-item--active {
  background: rgba(79, 110, 247, 0.2);
}

html.dark .dock-icon {
  background: rgba(79, 110, 247, 0.2);
}

html.dark .dock-item:hover .dock-icon,
html.dark .dock-item--active .dock-icon {
  background: var(--primary);
}
</style>

<template>
  <div class="detail-panel">
    <!-- Header -->
    <div class="panel-header">
      <div class="panel-header-info">
        <div class="panel-title-row">
          <el-icon :size="18" :color="agent.enabled ? 'var(--primary)' : 'var(--text-secondary)'">
            <UserFilled />
          </el-icon>
          <h3 class="panel-title">{{ agent.name }}</h3>
          <el-tag
            :type="agent.enabled ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ agent.enabled ? '已启用' : '已停用' }}
          </el-tag>
        </div>
        <p class="panel-desc">{{ agent.description || '暂无描述' }}</p>
      </div>
      <div class="panel-actions">
        <el-button text type="primary" size="small" :icon="Setting" @click="$emit('config', agent)">
          配置
        </el-button>
        <el-button text type="danger" size="small" :icon="Delete" @click="$emit('delete', agent)">
          删除
        </el-button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        :class="['tab-btn', { 'tab-btn--active': activeTab === tab.key }]"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Tab Content -->
    <div class="panel-body">
      <!-- Overview Tab -->
      <div v-if="activeTab === 'overview'" class="tab-content">
        <section class="info-section">
          <div class="info-row">
            <span class="info-label">分类</span>
            <span class="info-value">
              <el-tag v-if="agent.category" size="small" type="warning" effect="plain">
                {{ agent.category }}
              </el-tag>
              <span v-else class="text-muted">未设置</span>
            </span>
          </div>
        </section>

        <section class="info-section">
          <h4 class="section-title">模型配置</h4>
          <div class="info-row">
            <span class="info-label">模型</span>
            <span class="info-value model-name">{{ agent.model || 'deepseek-chat' }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">温度</span>
            <span class="info-value">{{ agent.temperature ?? 0.7 }}</span>
          </div>
        </section>

        <section v-if="agent.systemPrompt" class="info-section">
          <h4 class="section-title">系统提示词</h4>
          <pre class="prompt-preview">{{ agent.systemPrompt }}</pre>
        </section>
      </div>

      <!-- Info Tab -->
      <div v-if="activeTab === 'info'" class="tab-content">
        <section class="info-section">
          <div class="info-row">
            <span class="info-label">ID</span>
            <code class="info-value agent-id">{{ agent.id }}</code>
          </div>
          <div class="info-row">
            <span class="info-label">状态</span>
            <span class="info-value">
              <el-tag :type="agent.enabled ? 'success' : 'info'" size="small" effect="plain">
                {{ agent.enabled ? '已启用' : '已停用' }}
              </el-tag>
            </span>
          </div>
          <div class="info-row">
            <span class="info-label">创建时间</span>
            <span class="info-value">{{ agent.created_at || '—' }}</span>
          </div>
        </section>
      </div>

      <!-- Usage Tab -->
      <div v-if="activeTab === 'usage'" class="tab-content">
        <section class="info-section">
          <h4 class="section-title">使用统计</h4>
          <div class="stats-grid">
            <div class="mini-stat">
              <span class="mini-stat-value">—</span>
              <span class="mini-stat-label">今日对话</span>
            </div>
            <div class="mini-stat">
              <span class="mini-stat-value">—</span>
              <span class="mini-stat-label">总对话数</span>
            </div>
            <div class="mini-stat">
              <span class="mini-stat-value">—</span>
              <span class="mini-stat-label">Token 消耗</span>
            </div>
          </div>
          <p class="hint-text">统计数据需要后端支持</p>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { UserFilled, Setting, Delete } from '@element-plus/icons-vue'

const props = defineProps({
  agent: { type: Object, required: true },
})

defineEmits(['config', 'delete', 'refresh'])

const activeTab = ref('overview')

const tabs = [
  { key: 'overview', label: '概览' },
  { key: 'info', label: '详情' },
  { key: 'usage', label: '使用' },
]
</script>

<style scoped>
.detail-panel {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.panel-header {
  padding: 16px;
  border-bottom: 1px solid var(--border-light);
}

.panel-header-info {
  margin-bottom: 10px;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.panel-title {
  font-size: 15px;
  font-weight: 700;
  margin: 0;
}

.panel-desc {
  font-size: 12.5px;
  color: var(--text-secondary);
  line-height: 1.5;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.panel-actions {
  display: flex;
  gap: 4px;
}

/* ═══ Tabs ═══ */
.panel-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 16px 0;
  border-bottom: 1px solid var(--border-light);
  overflow-x: auto;
}

.tab-btn {
  padding: 6px 12px;
  font-size: 12px;
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 6px 6px 0 0;
  transition: all 0.15s;
  white-space: nowrap;
  font-weight: 500;
}

.tab-btn:hover {
  color: var(--text-primary);
  background: var(--primary-light);
}

.tab-btn--active {
  color: var(--primary);
  font-weight: 600;
  background: var(--primary-light);
}

/* ═══ Body ═══ */
.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.info-section {
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 12px;
}

.info-section:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 8px 0;
  color: var(--text-primary);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
}

.info-label {
  font-size: 12.5px;
  color: var(--text-secondary);
}

.info-value {
  font-size: 12.5px;
  color: var(--text-primary);
  font-weight: 500;
}

.model-name {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
}

.agent-id {
  font-size: 11px;
  background: var(--primary-light);
  padding: 2px 6px;
  border-radius: 4px;
  color: var(--primary);
}

.prompt-preview {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 10px;
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}

.text-muted {
  color: var(--text-tertiary);
}

.hint-text {
  font-size: 12px;
  color: var(--text-tertiary);
  margin: 8px 0 0 0;
  text-align: center;
}

/* ═══ Mini Stats ═══ */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.mini-stat {
  text-align: center;
  padding: 10px 6px;
  background: var(--bg-subtle);
  border-radius: 6px;
  border: 1px solid var(--border-light);
}

.mini-stat-value {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.mini-stat-label {
  font-size: 11px;
  color: var(--text-secondary);
}
</style>

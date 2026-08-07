<template>
  <div class="news-page">
    <!-- 4源 Tab -->
    <el-tabs v-model="activeTab" @tab-change="fetchNews" class="news-tabs">
      <el-tab-pane v-for="tab in sources" :key="tab.key" :label="tab.label" :name="tab.key">
        <div v-loading="loading">
          <!-- ===== 今日热点摘要 ===== -->
          <el-card v-if="hotSummary" class="hot-summary-card" shadow="hover">
            <div class="hot-summary-content" v-html="renderSummary(hotSummary.summary)" />
            <div v-if="hotSummary.items && hotSummary.items.length > 0" class="hot-summary-footer">
              <span class="hot-source-tag">{{ hotSummary.source_title }}</span>
              <span class="hot-total">{{ hotSummary.total }} 条新闻</span>
            </div>
          </el-card>
          <el-card v-else-if="!loading" class="hot-summary-card" shadow="hover">
            <div class="hot-summary-empty">暂无今日热点，下拉查看新闻列表</div>
          </el-card>

          <!-- 文章列表 -->
          <div v-if="newsList.length > 0" class="news-list">
            <div v-for="item in newsList" :key="item.id" class="news-item">
              <a :href="item.url" target="_blank" class="news-title">{{ item.title }}</a>
              <div class="news-meta">
                <el-tag size="small" :type="sourceTag(item.source)" effect="plain" round>{{ item.source }}</el-tag>
                <span class="news-time">{{ item.published_at }}</span>
              </div>
              <p class="news-desc">{{ item.summary || item.ai_summary || '' }}</p>
            </div>
          </div>
          <el-empty v-if="!loading && newsList.length===0" description="暂无新闻" />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import request from '../../utils/request'

const activeTab = ref('deep_tech')
const loading = ref(false)
const newsList = ref([])
const hotSummary = ref(null)

const sources = [
  { key: 'deep_tech', label: '🔬 深科技' },
  { key: 'machine_heart', label: '🧠 机器之心' },
  { key: 'qbitai', label: '⚡ 量子位' },
  { key: 'aiera', label: '🌐 新智元' },
]

const sourceTag = (s) => {
  const m = { deep_tech: 'info', machine_heart: 'success', qbitai: 'warning', aiera: 'info' }
  return m[s] || 'info'
}

function renderSummary(text) {
  if (!text) return ''
  // 将 Markdown 风格的换行转为 HTML
  let html = text
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  return html
}

const fetchNews = async () => {
  loading.value = true
  hotSummary.value = null
  try {
    const source = activeTab.value

    // 并行获取新闻列表 + 热点摘要
    const [newsRes, hotRes] = await Promise.allSettled([
      request.get('/api/news/daily', { params: { source, size: 20 } }),
      request.get('/api/news/daily/hot-summary', { params: { source } }),
    ])

    if (newsRes.status === 'fulfilled') {
      newsList.value = newsRes.value.items || []
    }

    if (hotRes.status === 'fulfilled' && hotRes.value?.summary) {
      hotSummary.value = {
        summary: hotRes.value.summary,
        source_title: hotRes.value.source_title || source,
        total: hotRes.value.total || 0,
        items: hotRes.value.items || [],
      }
    }
  } catch {}
  loading.value = false
}

onMounted(fetchNews)
</script>

<style scoped>
.news-page { }
.news-tabs { margin-top: 0; }

/* 热点摘要卡片 */
.hot-summary-card {
  margin-bottom: 16px;
  border-left: 4px solid #f59e0b;
  border-radius: 8px;
}
.hot-summary-content {
  font-size: 14px;
  line-height: 1.8;
  color: var(--text-primary);
  white-space: pre-wrap;
}
.hot-summary-content :deep(br) { margin-bottom: 6px; }
.hot-summary-content :deep(strong) { color: var(--text-primary); }
.hot-summary-footer {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 12px;
}
.hot-source-tag {
  background: #fef3c7;
  color: #92400e;
  padding: 2px 10px;
  border-radius: 12px;
  font-weight: 500;
}
.hot-total { color: var(--text-tertiary); }
.hot-summary-empty {
  color: var(--text-tertiary);
  font-size: 13px;
  text-align: center;
  padding: 12px;
}

/* 新闻列表 */
.news-list { margin-top: 4px; }
.news-item {
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  transition: background 0.15s;
}
.news-item:hover { background: var(--bg-subtle); margin: 0 -8px; padding: 14px 8px; border-radius: 6px; }
.news-title {
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
  font-size: 15px;
  line-height: 1.5;
  display: block;
}
.news-title:hover { color: var(--primary); }
.news-meta { margin-top: 6px; display: flex; align-items: center; gap: 8px; }
.news-time { font-size: 12px; color: var(--text-tertiary); }
.news-desc { margin: 6px 0 0; font-size: 13px; color: var(--text-secondary); line-height: 1.5; }

/* 暗色适配 */
html.dark .hot-source-tag {
  background: rgba(245,158,11,0.15);
  color: #fbbf24;
}
</style>

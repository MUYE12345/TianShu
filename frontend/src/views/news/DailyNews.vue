<template>
  <div class="news-page">
    <!-- ===== 页头 ===== -->
    <header class="news-top">
      <div>
        <h1 class="news-head-title">每日新闻</h1>
        <p class="news-head-sub">聚合深科技、机器之心、量子位、新智元四大来源，AI 提炼今日焦点速览</p>
      </div>
      <button class="btn-primary" @click="fetchNews">🔄 刷新</button>
    </header>

    <!-- ===== 来源 Tab ===== -->
    <el-tabs v-model="activeTab" @tab-change="fetchNews" class="news-tabs">
      <el-tab-pane v-for="tab in sources" :key="tab.key" :label="tab.label" :name="tab.key">
        <div v-loading="loading">
          <!-- ===== 今日热点摘要 banner ===== -->
          <section v-if="hotSummary" class="hot-banner">
            <div class="hot-banner-top">
              <span class="hot-banner-label">🔥 今日热点</span>
              <span v-if="hotSummary.source_title" class="hot-source-chip">{{ hotSummary.source_title }}</span>
            </div>
            <div class="hot-banner-content" v-html="renderSummary(hotSummary.summary)" />
            <div v-if="hotSummary.items && hotSummary.items.length > 0" class="hot-banner-foot">
              共 {{ hotSummary.total }} 条新闻
            </div>
          </section>
          <section v-else-if="!loading" class="hot-banner hot-banner-empty">
            <span class="hot-banner-emoji">☕</span>
            <span>暂无今日热点，下拉查看新闻列表</span>
          </section>

          <!-- ===== 新闻卡片网格 ===== -->
          <div v-if="newsList.length > 0" class="news-grid">
            <article v-for="item in newsList" :key="item.id" class="news-item">
              <a :href="item.url" target="_blank" class="news-title">{{ item.title }}</a>
              <div class="news-meta">
                <el-tag size="small" :type="sourceTag(item.source)" effect="plain" round>{{ item.source }}</el-tag>
                <span class="news-time">{{ item.published_at }}</span>
              </div>
              <p class="news-desc">{{ item.summary || item.ai_summary || '' }}</p>
            </article>
          </div>

          <!-- ===== 空状态 ===== -->
          <div v-if="!loading && newsList.length === 0" class="news-empty">
            <div class="news-empty-emoji">📭</div>
            <div class="news-empty-text">该来源暂时还没有新闻</div>
            <button class="btn-primary" @click="fetchNews">🔄 刷新试试</button>
          </div>
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
  // 先转义 HTML 再替换 Markdown 风格标记, 防止外部文本注入脚本
  let html = String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
  html = html
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
.news-page { padding: 4px 4px 24px; }

/* ===== 页头 ===== */
.news-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 18px; }
.news-head-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.news-head-sub { font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0; max-width: 560px; }
.news-tabs { margin-top: 0; }

/* ===== 今日热点 banner（柔和渐变） ===== */
.hot-banner {
  position: relative; overflow: hidden;
  border-radius: 24px; padding: 18px 24px; margin-bottom: 20px;
  background: linear-gradient(115deg, var(--tz-yellow-soft), var(--tz-pink-soft));
  border: 1px solid var(--border-light);
}
.hot-banner-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.hot-banner-label { font-size: 14px; font-weight: 700; font-family: var(--font-display); }
.hot-source-chip {
  padding: 3px 12px; border-radius: 999px;
  background: var(--bg-card); color: var(--tz-yellow-ink);
  font-size: 11px; font-weight: 600; box-shadow: var(--shadow-sm);
}
.hot-banner-content { font-size: 13px; line-height: 1.8; color: var(--text-primary); white-space: pre-wrap; }
.hot-banner-content :deep(br) { margin-bottom: 6px; }
.hot-banner-content :deep(strong) { color: var(--text-primary); }
.hot-banner-foot {
  margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light);
  font-size: 11px; color: var(--text-tertiary);
}
.hot-banner-empty {
  display: flex; align-items: center; gap: 10px;
  padding: 14px 24px; color: var(--text-tertiary); font-size: 13px;
}
.hot-banner-emoji { font-size: 18px; }

/* ===== 新闻卡片网格 ===== */
.news-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 16px;
}
.news-item {
  display: flex; flex-direction: column;
  padding: 16px 18px;
  border: 1px solid var(--border-light); border-radius: var(--radius-lg);
  background: var(--bg-card); box-shadow: var(--shadow-soft);
  transition: all .2s;
}
.news-item:hover { box-shadow: var(--shadow); transform: translateY(-2px); border-color: var(--border); }
.news-title {
  font-size: 15px; font-weight: 600; line-height: 1.5; color: var(--text-primary);
  text-decoration: none;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  transition: color .15s;
}
.news-title:hover { color: var(--accent); }
.news-meta { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.news-time { font-size: 11px; color: var(--text-muted); }
.news-desc {
  margin: 10px 0 0; font-size: 12px; line-height: 1.6; color: var(--text-tertiary);
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  flex: 1;
}

/* ===== 空状态 ===== */
.news-empty { text-align: center; padding: 48px 0 32px; color: var(--text-tertiary); }
.news-empty-emoji { font-size: 40px; margin-bottom: 10px; }
.news-empty-text { font-size: 13px; margin-bottom: 16px; }
</style>

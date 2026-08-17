<template>
  <div class="news-page">
    <!-- ===== 页头 ===== -->
    <header class="news-top">
      <div>
        <h1 class="news-head-title">时事新闻</h1>
        <p class="news-head-sub">第一热点、国际、科技、政事四大栏目，AI 摘要一屏掌握当日要闻</p>
      </div>
      <button class="btn-primary" @click="fetchNews">🔄 刷新</button>
    </header>

    <!-- ===== 栏目 Tab ===== -->
    <el-tabs v-model="activeSection" @tab-change="fetchNews" class="news-tabs">
      <el-tab-pane label="📌 第一热点" name="diyikandian" />
      <el-tab-pane label="🌍 国际" name="guoji" />
      <el-tab-pane label="🔬 科技" name="technology" />
      <el-tab-pane label="🏛️ 政事" name="zhengshi" />
    </el-tabs>

    <!-- ===== 栏目要点 banner ===== -->
    <section v-if="summary" class="news-summary">
      <div class="news-summary-top">
        <span class="chip chip-purple">✨ 要点速览</span>
      </div>
      <p class="news-summary-text">{{ summary }}</p>
    </section>

    <!-- ===== 新闻卡片网格 ===== -->
    <div v-loading="loading">
      <div v-if="newsList.length > 0" class="news-grid">
        <article v-for="item in newsList" :key="item.id" class="news-item">
          <a :href="item.url" target="_blank" class="news-title">{{ item.title }}</a>
          <div class="news-meta">
            <span class="news-time">🕒 {{ item.published_at }}</span>
          </div>
          <p class="news-desc">{{ item.summary }}</p>
        </article>
      </div>

      <!-- ===== 空状态 ===== -->
      <div v-if="!loading && newsList.length === 0" class="news-empty">
        <div class="news-empty-emoji">📭</div>
        <div class="news-empty-text">该栏目暂时还没有新闻</div>
        <button class="btn-primary" @click="fetchNews">🔄 刷新试试</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const activeSection = ref('diyikandian')
const newsList = ref([])
const summary = ref('')
const loading = ref(false)

const fetchNews = async () => {
  loading.value = true
  try {
    const res = await request.get('/api/news/current', { params: { section: activeSection.value, size: 20 } })
    newsList.value = res.items || []
    summary.value = newsList.value.length > 0 ? (newsList.value[0].ai_summary || '') : ''
  } catch (e) {
    ElMessage.error('加载时事新闻失败: ' + (e.response?.data?.detail || e.message))
  }
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

/* ===== 要点 banner（柔和渐变） ===== */
.news-summary {
  border-radius: 24px; padding: 18px 24px; margin-bottom: 20px;
  background: linear-gradient(115deg, var(--tz-purple-soft), var(--tz-blue-soft));
  border: 1px solid var(--border-light);
}
.news-summary-top { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.news-summary-text { margin: 0; font-size: 13px; line-height: 1.8; color: var(--text-primary); white-space: pre-wrap; }

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

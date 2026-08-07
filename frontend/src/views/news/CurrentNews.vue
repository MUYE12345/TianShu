<template>
  <div>
    <el-card v-if="summary" style="margin-bottom:16px">
      <template #header><span><el-icon><Clock /></el-icon> {{ activeSection }} 要点</span></template>
      <p style="white-space:pre-wrap;color:var(--text-primary)">{{ summary }}</p>
    </el-card>

    <el-tabs v-model="activeSection" @tab-change="fetchNews">
      <el-tab-pane label="📌 第一热点" name="diyikandian" />
      <el-tab-pane label="🌍 国际" name="guoji" />
      <el-tab-pane label="🔬 科技" name="technology" />
      <el-tab-pane label="🏛️ 政事" name="zhengshi" />
    </el-tabs>

    <div v-loading="loading">
      <div v-for="item in newsList" :key="item.id" class="news-item">
        <a :href="item.url" target="_blank" class="news-title">{{ item.title }}</a>
        <div class="news-time">{{ item.published_at }}</div>
        <p class="news-desc">{{ item.summary }}</p>
      </div>
      <el-empty v-if="!loading && newsList.length===0" description="暂无新闻" />
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
.news-item {
  padding: 14px;
  border-bottom: 1px solid var(--border);
}
.news-title {
  font-weight: 500;
  color: var(--text-primary);
  text-decoration: none;
  font-size: 15px;
  line-height: 1.5;
  display: block;
}
.news-title:hover { color: var(--primary); }
.news-time {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.news-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
</style>

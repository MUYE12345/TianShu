<template>
  <el-card v-loading="loading" :element-loading-text="'加载中...'">
    <template #header>
      <div style="display:flex;align-items:center;gap:12px">
        <el-button text @click="$router.back()">
          <el-icon><ArrowLeft /></el-icon> 返回
        </el-button>
        <el-tag v-if="news.source" :type="tagType" size="small">{{ news.source }}</el-tag>
      </div>
    </template>

    <div v-if="!loading && news.title">
      <h2 style="margin:0 0 8px;color:var(--text-primary)">{{ news.title }}</h2>
      <p style="color:var(--text-tertiary);font-size:13px;margin-bottom:16px">{{ news.published_at || '' }}</p>

      <el-divider />

      <!-- AI摘要 -->
      <el-card v-if="news.ai_summary" shadow="hover" class="summary-card">
        <template #header>
          <span><el-icon><MagicStick /></el-icon> AI摘要</span>
        </template>
        <p class="summary-text">{{ news.ai_summary }}</p>
      </el-card>

      <!-- 正文 -->
      <div class="content-text">
        {{ news.content || news.summary || '暂无内容' }}
      </div>

      <!-- 原文链接 -->
      <div style="margin-top:20px">
        <el-button type="primary" link @click="openUrl(news.url)">
          <el-icon><Link /></el-icon> 查看原文
        </el-button>
      </div>
    </div>

    <el-empty v-if="!loading && !news.title" description="新闻不存在" />
  </el-card>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const route = useRoute()
const news = ref({})
const loading = ref(true)

const tagMap = { deep_tech: '', machine_heart: 'success', qbitai: 'warning', aiera: 'info', bjnews: 'danger' }
const tagType = computed(() => tagMap[news.value.source] || '')

onMounted(async () => {
  try {
    const res = await request.get(`/api/news/daily/${route.params.id}`)
    news.value = res
  } catch (e) {
    ElMessage.error('加载新闻详情失败')
  }
  loading.value = false
})

const openUrl = (url) => { if (url) window.open(url, '_blank') }
</script>

<style scoped>
.summary-card {
  margin-bottom: 16px;
  background: var(--primary-light);
}
.summary-text {
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--text-primary);
}
.content-text {
  white-space: pre-wrap;
  line-height: 1.8;
  font-size: 15px;
  color: var(--text-primary);
}
</style>

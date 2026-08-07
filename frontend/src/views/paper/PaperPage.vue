<template>
  <el-card>
    <template #header>
      <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">
        <span><el-icon><Document /></el-icon> 论文解析</span>
        <el-input v-model="searchQuery" placeholder="搜索论文标题或作者" style="max-width:280px" clearable
          @keyup.enter="searchArxiv" />
        <el-button type="primary" @click="searchArxiv" :loading="searching">
          <el-icon><Search /></el-icon> arXiv搜索
        </el-button>
        <el-upload :action="uploadUrl" :on-success="onUpload" :show-file-list="false" accept=".pdf" :before-upload="beforeUpload">
          <el-button type="success" :loading="uploading">
            <el-icon><Upload /></el-icon> {{ uploading ? '上传中...' : '上传PDF' }}
          </el-button>
        </el-upload>
      </div>
    </template>

    <div v-if="arxivResults.length > 0">
      <h4>arXiv搜索结果</h4>
      <div v-for="p in arxivResults" :key="p.title" class="paper-card" @click="openUrl(p.pdf_url)">
        <h3 class="arxiv-title">{{ p.title }}</h3>
        <p class="arxiv-authors">{{ (p.authors||[]).join(', ').slice(0,100) }}</p>
        <p class="arxiv-summary">{{ (p.summary||'').slice(0,200) }}...</p>
        <el-text type="info" size="small">{{ p.published }}</el-text>
      </div>
    </div>

    <h4 style="margin-top:20px">已解析论文</h4>
    <el-table :data="papers" v-loading="loading" stripe style="width:100%">
      <el-table-column label="标题" min-width="220">
        <template #default="{row}">
          <span class="paper-title-link" @click="$router.push('/paper/'+row.id)">{{ row.title }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="source" label="来源" width="80" />
      <el-table-column prop="pages" label="页数" width="60" />
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{row}">
          <el-tag v-if="row.status==='parsed'" type="success" size="small">✅ 已解析</el-tag>
          <el-tag v-else-if="row.status==='ocr_processing'" type="warning" size="small">⏳ 解析中</el-tag>
          <el-tag v-else type="info" size="small">📄 待解析</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180">
        <template #default="{row}">
          <el-button v-if="row.status==='pending'" size="small" type="primary" @click="startOcr(row)">🔍 解析</el-button>
          <el-button v-if="row.status==='parsed' || row.status==='ocr_done'" size="small" @click="$router.push('/paper/'+row.id)">查看</el-button>
          <el-button size="small" type="danger" @click="deletePaper(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && papers.length===0 && arxivResults.length===0" description="搜索arXiv或上传PDF" />
  </el-card>
</template>

<script setup>
import { ref } from 'vue'
import request from '../../utils/request'
import { ElMessage } from 'element-plus'

const searchQuery = ref('')
const searching = ref(false)
const loading = ref(false)
const uploading = ref(false)
const arxivResults = ref([])
const papers = ref([])
const uploadUrl = '/api/paper/upload'

const searchArxiv = async () => {
  if (!searchQuery.value) return
  searching.value = true
  try {
    const res = await request.post('/api/paper/search', { query: searchQuery.value })
    arxivResults.value = res || []
  } catch { ElMessage.warning('arXiv搜索暂不可用, 请稍后重试') }
  searching.value = false
}
const beforeUpload = () => { uploading.value = true; return true }
const onUpload = (res) => { uploading.value = false; ElMessage.success('上传成功'); papers.value.unshift(res) }

const startOcr = async (row) => {
  row.status = 'ocr_processing'
  try {
    const res = await request.post('/api/paper/'+row.id+'/ocr')
    ElMessage.success(res.message || 'OCR已启动')
  } catch { ElMessage.error('OCR启动失败'); row.status = 'pending' }
}

const deletePaper = async (id) => {
  try { await request.delete('/api/paper/'+id); papers.value=papers.value.filter(p=>p.id!==id); ElMessage.success('已删除') }
  catch { ElMessage.error('删除失败') }
}

// 页面加载时获取论文列表
import { onMounted } from 'vue'
onMounted(async () => {
  try {
    const res = await request.get('/api/paper/list')
    papers.value = res || []
  } catch (e) {
    ElMessage.warning('加载论文列表失败: ' + (e.response?.data?.detail || e.message))
  }
})
const openUrl = (url) => window.open(url, '_blank')
</script>

<style scoped>
.paper-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.paper-card:hover {
  border-color: var(--primary);
  background: var(--bg-subtle);
}
.paper-title-link { cursor: pointer; color: var(--text-primary); font-weight: 500; }
.paper-title-link:hover { color: var(--primary); text-decoration: underline; }
.arxiv-title {
  margin: 0;
  color: var(--primary);
  font-size: 15px;
}
.arxiv-authors {
  margin: 4px 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.arxiv-summary {
  font-size: 13px;
  color: var(--text-primary);
}
</style>

<template>
  <div class="kb-page">
    <!-- ===== 页头（与知识库同款设计语言） ===== -->
    <header class="kb-top">
      <div>
        <h1 class="kb-title">论文解析</h1>
        <p class="kb-desc">上传 PDF 或从 arXiv 检索论文，自动识别正文与段落，支持逐段翻译与 AI 章节解读</p>
      </div>
      <div class="top-actions">
        <el-input ref="searchRef" v-model="searchQuery" placeholder="搜索论文标题或作者" clearable class="top-search"
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
    </header>

    <!-- ===== arXiv 搜索结果 ===== -->
    <section v-if="arxivResults.length > 0" class="arx-section">
      <div class="section-bar">
        <span class="section-title">arXiv 搜索结果</span>
        <span class="section-sub">共 {{ arxivResults.length }} 条 · 点击卡片在新窗口打开原文</span>
      </div>
      <div class="arx-grid">
        <div v-for="p in arxivResults" :key="p.title" class="arx-card" @click="openUrl(p.pdf_url)">
          <div class="arx-title">{{ p.title }}</div>
          <div class="arx-authors">{{ (p.authors||[]).join(', ').slice(0,100) }}</div>
          <div class="arx-summary">{{ (p.summary||'').slice(0,200) }}...</div>
          <div class="arx-meta">
            <span class="chip chip-blue">arXiv</span>
            <span>{{ p.published }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 已解析论文 ===== -->
    <section class="paper-section">
      <div class="section-bar">
        <span class="section-title">已解析论文</span>
        <span class="section-sub">共 {{ papers.length }} 篇</span>
      </div>

      <div v-loading="loading" class="paper-grid">
        <div v-for="p in papers" :key="p.id" class="paper-card" @click="$router.push('/paper/'+p.id)">
          <div class="pc-top">
            <span class="pc-icon ft-pdf">PDF</span>
            <div class="pc-main">
              <div class="pc-title">{{ p.title }}</div>
              <div class="pc-meta">
                <span class="chip" :class="p.source === 'arxiv' ? 'chip-blue' : 'chip-green'">{{ p.source === 'arxiv' ? 'arXiv' : '本地上传' }}</span>
                <span>📄 {{ p.pages || 0 }} 页</span>
                <span class="pc-date">{{ (p.created_at || '').slice(0, 10) }}</span>
              </div>
            </div>
          </div>
          <div class="pc-footer" @click.stop>
            <span v-if="p.status==='parsed'" class="chip chip-green">✅ 已解析</span>
            <span v-else-if="p.status==='ocr_processing'" class="chip chip-blue">⏳ 解析中</span>
            <span v-else-if="p.status==='error'" class="chip chip-pink">❌ 解析失败</span>
            <span v-else class="chip chip-purple">📄 待解析</span>
            <div class="pc-actions">
              <el-button v-if="p.status==='pending' || p.status==='error'" size="small" type="primary" @click="startOcr(p)">🔍 解析</el-button>
              <el-button v-if="p.status==='parsed' || p.status==='ocr_done'" size="small" @click="$router.push('/paper/'+p.id)">查看</el-button>
              <el-button size="small" type="danger" @click="deletePaper(p.id)">删除</el-button>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!loading && papers.length===0 && arxivResults.length===0" class="kb-empty">
          <div class="kb-empty-emoji">📄</div>
          <div class="kb-empty-text">还没有解析论文，搜索 arXiv 或上传 PDF 开始吧</div>
          <button class="btn-primary" @click="$refs.searchRef && $refs.searchRef.focus()">＋ 去搜索 / 上传</button>
        </div>
      </div>
    </section>
  </div>
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
.kb-page { padding: 4px 4px 24px; }

/* ── 页头（对齐知识库 .kb-top） ── */
.kb-top { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 18px; }
.kb-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.kb-desc { font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0; max-width: 560px; }
.top-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.top-search { width: 230px; }

/* ── 分区标题 ── */
.section-bar { display: flex; align-items: baseline; gap: 10px; margin-bottom: 14px; }
.section-title { font-size: 15px; font-weight: 700; }
.section-sub { font-size: 11px; color: var(--text-muted); }

/* ── arXiv 搜索结果卡片 ── */
.arx-section { margin-bottom: 26px; }
.arx-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.arx-card {
  border: 1px solid var(--border-light); border-radius: var(--radius-lg);
  background: var(--bg-card); box-shadow: var(--shadow-soft);
  padding: 14px 16px; cursor: pointer; transition: all .2s;
}
.arx-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }
.arx-title {
  font-size: 13.5px; font-weight: 700; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.arx-authors {
  font-size: 11.5px; color: var(--text-tertiary); margin-top: 6px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.arx-summary {
  font-size: 12px; color: var(--text-secondary); margin-top: 6px; line-height: 1.6;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.arx-meta { display: flex; align-items: center; gap: 8px; margin-top: 10px; font-size: 11px; color: var(--text-muted); }

/* ── 已解析论文卡片网格（对齐知识库 .kb-grid） ── */
.paper-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; }
.paper-card {
  display: flex; flex-direction: column; gap: 12px;
  border: 1px solid var(--border-light); border-radius: var(--radius-lg);
  background: var(--bg-card); box-shadow: var(--shadow-soft);
  padding: 16px; cursor: pointer; transition: all .2s;
}
.paper-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }

.pc-top { display: flex; gap: 12px; align-items: flex-start; }
.pc-icon {
  flex-shrink: 0; width: 42px; height: 42px; border-radius: 12px;
  display: grid; place-items: center; color: var(--text-on-accent);
  font-size: 10px; font-weight: 800; letter-spacing: 0.02em;
  box-shadow: var(--shadow-soft);
}
.pc-main { flex: 1; min-width: 0; }
.pc-title {
  font-size: 14px; font-weight: 700; line-height: 1.5;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.pc-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 11px; color: var(--text-secondary); margin-top: 8px; }
.pc-date { color: var(--text-muted); }

.pc-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding-top: 10px; margin-top: auto; border-top: 1px solid var(--border-light);
}
.pc-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

/* ── 空状态（对齐知识库 .kb-empty） ── */
.kb-empty { grid-column: 1 / -1; text-align: center; padding: 48px 0; color: var(--text-tertiary); }
.kb-empty-emoji { font-size: 40px; margin-bottom: 10px; }
.kb-empty-text { font-size: 13px; margin-bottom: 16px; }
</style>

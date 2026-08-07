<template>
  <div class="notes-page">
    <header class="notes-top">
      <div>
        <h1 class="notes-title">Wiki 笔记</h1>
        <p class="notes-desc">笔记、概念、来源与项目页面</p>
      </div>
      <div class="notes-actions">
        <el-input v-model="searchQ" placeholder="搜索笔记…" clearable size="small" style="width: 200px" />
        <button class="btn-outline" @click="fileInput?.click()">📥 上传文章解析</button>
        <button class="btn-primary" @click="showCreate = true">＋ 新建笔记</button>
        <input ref="fileInput" type="file" style="display:none"
               accept=".pdf,.doc,.docx,.md,.txt,.markdown,.xlsx,.xls,.pptx,.html" @change="analyzeUpload" />
      </div>
    </header>

    <div class="notes-tabs">
      <div class="notes-tab" :class="{ active: activeTab === 'all' }" @click="activeTab = 'all'">全部</div>
      <div class="notes-tab" :class="{ active: activeTab === 'note' }" @click="activeTab = 'note'">📝 笔记</div>
      <div class="notes-tab" :class="{ active: activeTab === 'concept' }" @click="activeTab = 'concept'">💡 概念</div>
      <div class="notes-tab" :class="{ active: activeTab === 'source' }" @click="activeTab = 'source'">📎 来源</div>
      <div class="notes-tab" :class="{ active: activeTab === 'project' }" @click="activeTab = 'project'">📁 项目</div>
      <div class="notes-tab" :class="{ active: activeTab === 'graph' }" @click="activeTab = 'graph'">🕸 图谱</div>
      <div class="notes-tab" :class="{ active: activeTab === 'mindmap' }" @click="activeTab = 'mindmap'">🧠 思维导图</div>
    </div>

    <WikiMindMap v-if="activeTab === 'mindmap'" />
    <KnowledgeGraph v-else-if="activeTab === 'graph'" />

    <div v-else v-loading="loading" class="notes-grid">
      <div v-for="p in filteredPages" :key="p.slug" class="note-card" @click="router.push('/wiki/' + p.slug)">
        <div class="note-cover" :style="{ background: coverColor(p.type) }">
          <span class="note-emoji">{{ typeEmoji(p.type) }}</span>
        </div>
        <div class="note-body">
          <div class="note-type">{{ typeLabel(p.type) }}</div>
          <div class="note-title">{{ p.title }}</div>
          <div class="note-desc">{{ (p.body || '').slice(0, 60) }}</div>
          <div class="note-footer">
            <span class="note-tags">
              <el-tag v-for="t in (p.tags || []).slice(0, 2)" :key="t" size="small" round>{{ t }}</el-tag>
            </span>
            <span class="note-time">{{ (p.created || '').slice(0, 10) }}</span>
          </div>
        </div>
      </div>
      <el-empty v-if="!loading && filteredPages.length === 0" :image-size="60" description="暂无笔记" />
    </div>

    <el-dialog v-model="showCreate" title="新建笔记" width="480px">
      <el-form label-position="top">
        <el-form-item label="标题"><el-input v-model="form.title" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.type" style="width:100%">
            <el-option label="笔记" value="note" /><el-option label="概念" value="concept" />
            <el-option label="来源" value="source" /><el-option label="项目" value="project" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容"><el-input v-model="form.content" type="textarea" :rows="4" /></el-form-item>
        <el-form-item label="标签"><el-input v-model="form.tags" placeholder="逗号分隔" /></el-form-item>
      </el-form>
      <template #footer>
        <button class="btn-ghost" @click="showCreate = false">取消</button>
        <button class="btn-primary" :disabled="!form.title.trim()" @click="createPage">创建</button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import KnowledgeGraph from '../../components/wiki/KnowledgeGraph.vue'
import WikiMindMap from '../../components/wiki/WikiMindMap.vue'

const router = useRouter()
const fileInput = ref(null)
const pages = ref([])
const loading = ref(false)
const searchQ = ref('')
const activeTab = ref('all')
const showCreate = ref(false)
const form = ref({ title: '', content: '', type: 'note', tags: '' })

const filteredPages = computed(() => {
  let list = pages.value
  if (activeTab.value !== 'all') list = list.filter(p => p.type === activeTab.value)
  if (searchQ.value) {
    const q = searchQ.value.toLowerCase()
    list = list.filter(p => (p.title || '').toLowerCase().includes(q))
  }
  return list
})

function typeLabel(t) {
  return { note: '笔记', concept: '概念', source: '来源', project: '项目', news: '新闻', task: '任务', idea: '想法' }[t] || t
}
function typeEmoji(t) {
  return { note: '📝', concept: '💡', source: '📎', project: '📁', news: '📰', task: '✅', idea: '✨' }[t] || '📄'
}
function coverColor(t) {
  const m = { note: 'var(--tz-blue-soft)', concept: 'var(--tz-yellow-soft)', source: 'var(--tz-green-soft)', project: 'var(--tz-purple-soft)', news: 'var(--tz-pink-soft)', task: 'var(--tz-blue-soft)', idea: 'var(--tz-purple-soft)' }
  return m[t] || 'var(--bg-subtle)'
}

async function loadPages() {
  loading.value = true
  try {
    const res = await axios.get('/api/wiki/pages')
    pages.value = res.data?.items || res.data || []
  } catch (e) {
    ElMessage.error('加载笔记失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function createPage() {
  try {
    const params = new URLSearchParams({ title: form.value.title, content: form.value.content, page_type: form.value.type })
    if (form.value.tags) params.set('tags', form.value.tags)
    await axios.post('/api/wiki/pages?' + params.toString())
    showCreate.value = false
    form.value = { title: '', content: '', type: 'note', tags: '' }
    await loadPages()
    ElMessage.success('笔记创建成功')
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

// 上传文章 → 解析为 wiki（根来源页 + 章节子页）
const analyzing = ref(false)
async function analyzeUpload(e) {
  const file = e.target.files?.[0]
  e.target.value = ''
  if (!file) return
  analyzing.value = true
  const fd = new FormData()
  fd.append('file', file)
  try {
    const { data } = await axios.post('/api/wiki/analyze', fd)
    const msg = data?.created
      ? `解析完成，创建 ${data.created} 个 wiki 页面（1 个来源 + ${data.children?.length || 0} 个章节）`
      : '解析完成'
    ElMessage.success(msg)
    await loadPages()
    activeTab.value = 'mindmap'
  } catch (err) {
    ElMessage.error('解析失败: ' + (err.response?.data?.detail || err.message))
  } finally {
    analyzing.value = false
  }
}

onMounted(loadPages)
</script>

<style scoped>
.notes-page { padding: 4px 4px 24px; }
.notes-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.notes-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.notes-desc { font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0; }
.notes-actions { display: flex; gap: 8px; align-items: center; }

.notes-tabs { display: flex; gap: 4px; margin-bottom: 16px; background: var(--bg-subtle); padding: 3px; border-radius: 999px; width: fit-content; }
.notes-tab { padding: 5px 14px; border-radius: 999px; cursor: pointer; font-size: 12px; transition: all .15s; color: var(--text-secondary); }
.notes-tab:hover { color: var(--text-primary); }
.notes-tab.active { background: var(--bg-card); color: var(--text-primary); font-weight: 600; box-shadow: var(--shadow-soft); }

.notes-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px; }
.note-card {
  border: 1px solid var(--border-light); border-radius: var(--radius-lg); overflow: hidden;
  cursor: pointer; transition: all .2s; background: var(--bg-card); box-shadow: var(--shadow-soft);
}
.note-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }
.note-cover { height: 80px; display: flex; align-items: center; justify-content: center; }
.note-emoji { font-size: 28px; }
.note-body { padding: 12px 14px; }
.note-type { font-size: 10px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.note-title { font-size: 14px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note-desc { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.note-footer { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.note-tags { display: flex; gap: 4px; }
.note-time { font-size: 11px; color: var(--text-muted); }
</style>

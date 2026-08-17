<template>
  <div class="kb-page">
    <!-- ===== 页头（设计稿 img_01） ===== -->
    <header class="kb-top">
      <div>
        <h1 class="kb-title">知识库</h1>
        <p class="kb-desc">知识沉淀与产出工作台——上传一份来源文档，对话提问，一键生成网页 / 思维导图 / PPT / 简报</p>
      </div>
      <button class="btn-primary" @click="openCreate">＋ 创建知识库</button>
    </header>

    <!-- ===== 全部知识（只读共享区） ===== -->
    <section class="all-kb">
      <div class="all-kb-text">
        <div class="all-kb-title">全部知识</div>
        <div class="all-kb-desc">所有创建与被共享的知识库都会汇入这里，仅承担使用功能，不承担编辑。</div>
        <div class="all-kb-meta">共 {{ notebooks.length }} 个知识库 · {{ totalSources }} 份来源</div>
      </div>
      <div class="all-kb-icons">
        <span v-for="(ic, i) in floatingIcons" :key="i" class="all-kb-icon" :class="ic.cls" :style="ic.style">{{ ic.emoji }}</span>
      </div>
    </section>

    <!-- ===== 主题知识库 ===== -->
    <section class="topic-kb">
      <div class="topic-bar">
        <span class="topic-label">主题知识</span>
        <el-input v-model="searchQ" placeholder="搜索知识库…" clearable size="small" style="width: 180px" />
        <el-select v-model="sortBy" size="small" style="width: 120px">
          <el-option label="最近更新" value="updated" />
          <el-option label="最早创建" value="created" />
          <el-option label="名称" value="name" />
        </el-select>
      </div>

      <div v-loading="loading" class="kb-grid">
        <div v-for="kb in filteredKbs" :key="kb.id" class="kb-card" @click="goKb(kb)">
          <div class="kb-card-cover">
            <KbCover :cover="kb.cover" />
            <!-- 悬浮管理按钮（设计稿 img_05） -->
            <div class="kb-card-actions" @click.stop>
              <span class="kb-act" title="知识库设置" @click="openSettings(kb)">⚙</span>
            </div>
            <div class="kb-card-hoverbar" @click.stop>
              <span class="hover-pill" @click="goAddSource(kb)">＋ 添加来源</span>
              <span class="hover-pill" @click="openSettings(kb)">编辑信息</span>
              <span class="hover-pill danger" @click="openDelete(kb)">删除</span>
            </div>
          </div>
          <div class="kb-card-body">
            <div class="kb-card-title">
              {{ kb.title }}
              <!-- 角色标识: 共享给我的显示角色, 自己的不显示 -->
              <el-tag v-if="kb.my_role === 'admin'" size="small" type="danger" effect="plain" style="margin-left:6px">管理员</el-tag>
              <el-tag v-else-if="kb.my_role === 'editor'" size="small" type="warning" effect="plain" style="margin-left:6px">编辑</el-tag>
              <el-tag v-else-if="kb.my_role === 'viewer'" size="small" type="info" effect="plain" style="margin-left:6px">查看</el-tag>
            </div>
            <div class="kb-card-desc">{{ kb.description || '暂无简介' }}</div>
            <div class="kb-card-meta">
              <span>📄 {{ kb.source_count || 0 }} 来源</span>
              <span>🗂 {{ artifactCount(kb) }} 产物</span>
              <span v-if="kb.owner_name" class="kb-owner">👤 {{ kb.owner_name }}</span>
            </div>
            <div class="kb-card-date">{{ (kb.created_at || '').slice(0, 10) }}</div>
          </div>
        </div>
        <div v-if="!loading && filteredKbs.length === 0" class="kb-empty">
          <div class="kb-empty-emoji">🗂</div>
          <div class="kb-empty-text">还没有主题知识库</div>
          <button class="btn-primary" @click="openCreate">＋ 创建知识库</button>
        </div>
      </div>
    </section>

    <!-- ===== 创建知识库（设计稿 img_03/04） ===== -->
    <el-dialog v-model="showCreate" title="创建知识库" width="460px" :close-on-click-modal="false">
      <div class="create-cover">
        <KbCover :cover="kbForm.cover" />
        <button class="change-cover" @click="showCoverPicker = !showCoverPicker">🖽 换封面</button>
      </div>
      <div v-if="showCoverPicker" class="cover-picker">
        <div class="cover-picker-title">选择封面</div>
        <div class="cover-grid">
          <div v-for="c in KB_COVERS" :key="c.id" class="cover-opt" :class="{ active: kbForm.cover === c.id }" @click="kbForm.cover = c.id">
            <KbCover :cover="c.id" />
            <span v-if="kbForm.cover === c.id" class="cover-check">✓</span>
          </div>
        </div>
      </div>
      <el-input v-model="kbForm.title" maxlength="20" placeholder="知识库名称，比如：竞品分析" style="margin-top: 14px" />
      <el-input v-model="kbForm.description" placeholder="一句话简介（可选）" maxlength="500" style="margin-top: 10px" />
      <template #footer>
        <button class="btn-ghost" @click="showCreate = false">取消</button>
        <button class="btn-primary" :disabled="!kbForm.title.trim()" @click="createKb">创建</button>
      </template>
    </el-dialog>

    <!-- ===== 设置 / 删除 ===== -->
    <KbSettingsDialog v-model="showSettings" :kb="currentKb" @save="saveSettings" @request-delete="openDelete(currentKb); showSettings = false" />
    <DeleteKbDialog v-model="showDelete" :kb="currentKb" @confirm="doDelete" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import KbCover from '../../components/wiki/KbCover.vue'
import { KB_COVERS } from '../../components/wiki/covers.js'
import KbSettingsDialog from '../../components/wiki/KbSettingsDialog.vue'
import DeleteKbDialog from '../../components/wiki/DeleteKbDialog.vue'

const router = useRouter()
const notebooks = ref([])
const artifactCounts = ref({})
const loading = ref(false)
const searchQ = ref('')
const sortBy = ref('updated')

const showCreate = ref(false)
const showCoverPicker = ref(false)
const showSettings = ref(false)
const showDelete = ref(false)
const currentKb = ref(null)
const kbForm = ref({ title: '', description: '', cover: 'cover-1' })

const totalSources = computed(() => notebooks.value.reduce((s, n) => s + (n.source_count || 0), 0))

const filteredKbs = computed(() => {
  let list = [...notebooks.value]
  if (searchQ.value) {
    const q = searchQ.value.toLowerCase()
    list = list.filter(k => (k.title || '').toLowerCase().includes(q))
  }
  if (sortBy.value === 'updated') list.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''))
  else if (sortBy.value === 'created') list.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''))
  else list.sort((a, b) => (a.title || '').localeCompare(b.title || '', 'zh'))
  return list
})

// 全部知识 banner 上的漂浮文件图标
const floatingIcons = [
  { emoji: '📄', cls: 'ft-doc', style: 'top: 6px; left: 8px; transform: rotate(-6deg)' },
  { emoji: '📊', cls: 'ft-xls', style: 'top: 34px; left: 78px; transform: rotate(4deg)' },
  { emoji: 'PDF', cls: 'ft-pdf', style: 'top: 2px; left: 150px; transform: rotate(3deg)' },
  { emoji: '📽', cls: 'ft-ppt', style: 'top: 40px; left: 216px; transform: rotate(-4deg)' },
  { emoji: 'MD', cls: 'ft-md', style: 'top: 8px; left: 288px; transform: rotate(5deg)' },
  { emoji: '🌐', cls: 'ft-html', style: 'top: 36px; left: 352px; transform: rotate(-3deg)' },
]

function artifactCount(kb) { return artifactCounts.value[kb.id] ?? 0 }
function goKb(kb) { router.push('/wiki/' + kb.id) }
function goAddSource(kb) { router.push('/wiki/' + kb.id + '?add=1') }
function openCreate() { showCreate.value = true; showCoverPicker.value = false; kbForm.value = { title: '', description: '', cover: 'cover-1' } }
function openSettings(kb) { currentKb.value = kb; showSettings.value = true }
function openDelete(kb) { currentKb.value = kb; showDelete.value = true }

async function loadKbs() {
  loading.value = true
  try {
    const res = await axios.get('/api/knowledge/notebooks')
    notebooks.value = res.data?.items || []
    // 产物数（并发拉取）
    const counts = {}
    await Promise.allSettled(notebooks.value.map(async n => {
      const r = await axios.get(`/api/knowledge/notebooks/${n.id}/artifacts`)
      counts[n.id] = r.data?.total || 0
    }))
    artifactCounts.value = counts
  } catch (e) {
    ElMessage.error('加载知识库失败: ' + (e.response?.data?.detail || e.message))
  } finally { loading.value = false }
}

async function createKb() {
  try {
    await axios.post('/api/knowledge/notebooks', kbForm.value)
    showCreate.value = false
    ElMessage.success('知识库创建成功')
    await loadKbs()
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function saveSettings(form) {
  try {
    await axios.put(`/api/knowledge/notebooks/${currentKb.value.id}`, form)
    showSettings.value = false
    ElMessage.success('已保存')
    await loadKbs()
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function doDelete() {
  try {
    await axios.delete(`/api/knowledge/notebooks/${currentKb.value.id}`)
    showDelete.value = false
    ElMessage.success('知识库已删除')
    await loadKbs()
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(loadKbs)
</script>

<style scoped>
.kb-page { padding: 4px 4px 24px; }
.kb-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px; }
.kb-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin: 0; font-family: var(--font-display); }
.kb-desc { font-size: 12px; color: var(--text-tertiary); margin: 6px 0 0; max-width: 560px; }

/* 全部知识 banner */
.all-kb {
  position: relative; overflow: hidden;
  border-radius: 24px; padding: 20px 26px;
  background: linear-gradient(115deg, var(--tz-purple-soft), var(--tz-blue-soft));
  border: 1px solid var(--border-light);
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 26px;
}
.all-kb-title { font-size: 16px; font-weight: 700; }
.all-kb-desc { font-size: 12px; color: var(--text-secondary); margin-top: 6px; max-width: 520px; }
.all-kb-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 10px; }
.all-kb-icons { position: relative; width: 400px; height: 84px; flex-shrink: 0; }
.all-kb-icon {
  position: absolute; width: 40px; height: 40px; border-radius: 10px;
  display: grid; place-items: center; font-size: 15px; font-weight: 700; color: #fff;
  box-shadow: var(--shadow-soft);
}

/* 主题知识 */
.topic-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.topic-label { font-size: 14px; font-weight: 700; margin-right: auto; }

.kb-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }
.kb-card {
  border: 1px solid var(--border-light); border-radius: var(--radius-lg); overflow: hidden;
  cursor: pointer; transition: all .2s; background: var(--bg-card);
  box-shadow: var(--shadow-soft);
}
.kb-card:hover { box-shadow: var(--shadow); transform: translateY(-2px); }
.kb-card-cover { position: relative; height: 110px; }
.kb-card-actions { position: absolute; top: 8px; right: 8px; opacity: 0; transition: opacity .15s; z-index: 2; }
.kb-card:hover .kb-card-actions { opacity: 1; }
.kb-act {
  width: 30px; height: 30px; border-radius: 10px; background: rgba(255,255,255,.92);
  display: grid; place-items: center; cursor: pointer; font-size: 14px;
  box-shadow: var(--shadow-soft); color: var(--text-secondary);
}
.kb-act:hover { color: var(--text-primary); }
.kb-card-hoverbar {
  position: absolute; left: 0; right: 0; bottom: 0; padding: 8px 10px;
  display: flex; gap: 6px; justify-content: center;
  background: linear-gradient(180deg, transparent, rgba(20, 20, 30, .45));
  opacity: 0; transition: opacity .18s; z-index: 2;
}
.kb-card:hover .kb-card-hoverbar { opacity: 1; }
.hover-pill {
  padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 600;
  background: rgba(255, 255, 255, .94); color: var(--text-primary); cursor: pointer;
  transition: transform .12s;
}
.hover-pill:hover { transform: scale(1.05); }
.hover-pill.danger { color: var(--danger); }

.kb-card-body { padding: 12px 14px 14px; }
.kb-card-title { font-size: 14px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-card-desc { font-size: 12px; color: var(--text-tertiary); margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-card-meta { display: flex; gap: 12px; font-size: 11px; color: var(--text-secondary); margin-top: 10px; }
.kb-owner { margin-left: auto; color: var(--text-tertiary); }
.kb-card-date { font-size: 11px; color: var(--text-muted); margin-top: 10px; padding-top: 8px; border-top: 1px solid var(--border-light); }

.kb-empty { grid-column: 1 / -1; text-align: center; padding: 40px 0; color: var(--text-tertiary); }
.kb-empty-emoji { font-size: 40px; margin-bottom: 10px; }
.kb-empty-text { font-size: 13px; margin-bottom: 16px; }

/* 创建弹窗封面 */
.create-cover { position: relative; height: 120px; border-radius: 16px; overflow: hidden; }
.change-cover {
  position: absolute; top: 10px; right: 10px;
  padding: 5px 12px; border-radius: 999px; border: none;
  background: rgba(255, 255, 255, .94); font-size: 12px; font-weight: 600;
  cursor: pointer; box-shadow: var(--shadow-soft); color: var(--text-primary);
}
.cover-picker { margin-top: 12px; background: var(--bg-subtle); border-radius: 16px; padding: 12px; }
.cover-picker-title { font-size: 12px; font-weight: 600; margin-bottom: 10px; }
.cover-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.cover-opt { position: relative; height: 56px; border-radius: 12px; overflow: hidden; cursor: pointer; border: 2px solid transparent; }
.cover-opt.active { border-color: var(--accent); }
.cover-opt :deep(.kb-cover-emoji) { font-size: 22px; }
.cover-check { position: absolute; right: 5px; top: 5px; width: 16px; height: 16px; border-radius: 50%; background: var(--bg-card); font-size: 10px; display: grid; place-items: center; z-index: 2; }
</style>

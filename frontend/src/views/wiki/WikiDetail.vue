<template>
  <!-- ===== 知识库四栏工作台（设计稿 img_08 起） ===== -->
  <div v-if="kb" class="wd-root">
    <!-- 顶栏 -->
    <header class="wd-top">
      <button class="wd-back" @click="goBack">‹ 知识库</button>
      <span class="wd-title">{{ kb.title }}</span>
      <span class="wd-counts">{{ sources.length }} 份来源 · {{ artifacts.length }} 个产物</span>
      <div class="wd-top-actions">
        <button v-if="selectedSources.length" class="wd-clear" @click="selectedSources = []">✕ 清除全部选中</button>
        <button class="wd-hist" @click="showHistory = true">🕘 历史记录</button>
        <button class="wd-hist" @click="openSettings">⚙ 设置</button>
      </div>
    </header>

    <div class="wd-cols">
      <!-- ── 列1：知识库切换 ── -->
      <aside class="wd-col wd-kbs">
        <div class="col-head">
          <input v-model="kbSearch" class="col-search" placeholder="搜索知识库…" />
        </div>
        <div class="kbs-list">
          <div v-for="n in kbList" :key="n.id" class="kbs-item" :class="{ active: n.id === kb.id }" @click="switchKb(n)">
            <span class="kbs-dot" :class="n.cover || ''">{{ coverEmoji(n.cover) }}</span>
            <div class="kbs-info">
              <div class="kbs-name">{{ n.title }}</div>
              <div class="kbs-meta">{{ n.source_count || 0 }} 来源</div>
            </div>
          </div>
        </div>
      </aside>

      <!-- ── 列2：来源 ── -->
      <aside class="wd-col wd-sources">
        <div class="col-head">
          <span class="col-title">来源</span>
          <span class="col-spacer"></span>
          <button class="src-select-toggle" :class="{ on: selectMode }" :title="selectMode ? '退出选择' : '选择文档聚焦问答'" @click="selectMode = !selectMode">☑</button>
          <button v-if="canEdit" class="btn-primary src-add" @click="showAdd = true">＋ 添加</button>
        </div>
        <div class="src-list">
          <div v-for="s in filteredSources" :key="s.id" class="src-item"
               :class="{ selected: isSelected(s), failed: s.status === 'failed' }"
               @click="selectMode && s.status === 'parsed' ? toggleSelect(s) : (s.status === 'parsed' ? openSourceTab(s) : null)">
            <span v-if="selectMode && s.status === 'parsed'" class="src-check" :class="{ on: isSelected(s) }">{{ isSelected(s) ? '✓' : '' }}</span>
            <span class="src-icon" :class="fileTypeInfo(s.ext).cls">{{ fileTypeInfo(s.ext).label.slice(0, 3) }}</span>
            <div class="src-info">
              <div class="src-name">{{ s.filename }}</div>
              <div class="src-meta">
                <template v-if="s.status === 'parsed'">{{ formatSize(s.size) }}</template>
                <template v-else-if="s.status === 'failed'">
                  <el-popover :content="s.parse_error || '解析失败'" placement="right" :width="260" trigger="hover">
                    <template #reference><span class="src-err">解析失败 · 原因</span></template>
                  </el-popover>
                </template>
                <template v-else><span class="src-parsing">解析中…</span></template>
              </div>
            </div>
            <span class="src-actions" @click.stop>
              <span v-if="s.status === 'parsed'" class="src-act" title="预览" @click="openSourceTab(s)">👁</span>
              <span class="src-act" title="下载原件" @click="downloadSource(s)">⬇</span>
              <span v-if="canEdit" class="src-act danger" title="删除" @click="deleteSource(s.id)">✕</span>
            </span>
          </div>
          <div v-if="sources.length === 0" class="src-empty">
            <div class="src-empty-icon">📚</div>
            <p>资料随查扔进来</p>
            <p class="src-empty-sub">PDF、Word、表格、粘贴的文本——导入后就能对话提问、一键生成网页 / 导图 / PPT。</p>
          </div>
        </div>
      </aside>

      <!-- ── 列3：对话 / 预览 ── -->
      <section class="wd-col wd-chat">
        <div class="chat-tabs">
          <div class="chat-tab" :class="{ active: !previewTab }" @click="previewTab = null">对话</div>
          <div v-if="previewTab" class="chat-tab preview active">
            {{ previewTab.kind === 'source' ? previewTab.data.filename : previewTab.data.label + ' · ' + previewTab.data.title }}
            <span class="tab-x" @click="previewTab = null">✕</span>
          </div>
        </div>

        <!-- 预览态 -->
        <div v-if="previewTab" class="chat-preview">
          <div class="preview-topbar">
            <button class="btn-ghost" @click="previewTab = null">‹ 返回对话</button>
            <span class="preview-spacer"></span>
            <button v-if="previewTab.kind === 'source'" class="btn-outline" @click="downloadSource(previewTab.data)">下载原件</button>
            <a v-if="previewTab.kind === 'artifact' && previewTab.data.kind === 'ppt'" class="btn-outline"
               :href="`/api/knowledge/notebooks/${kid}/artifacts/${previewTab.data.id}/pptx`">下载 PPTX</a>
            <a v-if="previewTab.kind === 'artifact'" class="btn-outline" :href="previewTab.data.url" :download="previewTab.data.filename">下载文件</a>
          </div>
          <SourcePreviewDialog v-if="previewTab.kind === 'source'" :model-value="true" :inline="true" :kid="kid" :source="previewTab.data" @update:model-value="previewTab = null" />
          <ArtifactPreview v-else :artifact="previewTab.data" />
        </div>

        <!-- 对话态 -->
        <template v-else>
          <div class="chat-msgs" ref="chatRef">
            <div v-if="chatMsgs.length === 0" class="chat-empty">
              <div class="kb-illustration">⌨️</div>
              <template v-if="parsedSources.length === 0">
                <p class="ce-main">先添加几份来源——PDF、Word、粘贴的文本都可以。</p>
                <button class="btn-outline" @click="showAdd = true">知识库空空的，请先添加知识来源</button>
              </template>
              <template v-else>
                <p class="ce-main">已就绪 <b>{{ parsedSources.length }}</b> 份来源。直接提问，回答带可溯源的引用。</p>
                <div class="chat-suggestions">
                  <div class="sugg-chip" v-for="(q, qi) in suggestedQuestions" :key="qi" @click="quickChat(q)">{{ q }}</div>
                </div>
              </template>
            </div>
            <div v-for="(m, i) in chatMsgs" :key="i" class="chat-msg" :class="m.role">
              <template v-if="m.role === 'user'">
                <div class="cm-bubble user">{{ m.content }}</div>
              </template>
              <template v-else>
                <div class="cm-ai">
                  <div v-if="m.steps?.length" class="cm-steps">
                    <span v-for="(s, si) in m.steps" :key="si" class="cm-step">{{ stepChipText(s) }}</span>
                  </div>
                  <div v-if="m.citations?.length" class="cm-citations">
                    <span class="cc-label">引用</span>
                    <span v-for="(c, ci) in m.citations" :key="ci" class="cc-chip"
                          :title="(c.section || '') + (c.score ? ' · 相关度 ' + Number(c.score).toFixed(3) : '')"
                          @click="citationClick(c)">{{ c.title }}{{ c.section ? ' · ' + c.section : '' }}</span>
                  </div>
                  <div v-if="m.streaming && !m.content" class="dot-pulse"><span></span><span></span><span></span></div>
                  <div v-else class="cm-md" v-html="renderMd(m.content)"></div>
                </div>
              </template>
            </div>
          </div>

          <!-- 选中聚焦条（PRD 选中提示之一） -->
          <div v-if="selectedSources.length" class="focus-strip">
            <span class="fs-label">本次对话聚焦 {{ selectedSources.length }} 份文档：</span>
            <el-tag v-for="s in selectedSources" :key="s.id" closable size="small" round @close="unselectSource(s)">{{ s.filename }}</el-tag>
            <button class="fs-clear" @click="selectedSources = []">清除</button>
          </div>
          <div v-else-if="parsedSources.length" class="focus-strip idle">
            对话默认针对全部文档，也可以缩小来源范围聚焦问答。
            <button class="fs-clear" @click="selectMode = true">选择文档</button>
          </div>

          <div class="composer-shell chat-composer">
            <textarea v-model="chatInput" class="composer-input" rows="1"
                      :placeholder="parsedSources.length ? '直接提问，回答带可溯源的引用…' : '先添加来源，再开始提问…'"
                      @keydown.enter.exact.prevent="sendChat"></textarea>
            <div class="composer-bar">
              <button class="composer-attach" title="添加来源" @click="showAdd = true">📎</button>
              <span class="composer-spacer"></span>
              <button v-if="streaming" class="composer-stop" title="终止回答" @click="stopChat">■</button>
              <button v-else class="composer-send" :disabled="!chatInput.trim()" @click="sendChat">↑</button>
            </div>
          </div>
        </template>
      </section>

      <!-- ── 列4：产出 ── -->
      <aside class="wd-col wd-artifacts" :class="{ disabled: parsedSources.length === 0 }">
        <div class="col-head"><span class="col-title">产物</span></div>
        <div v-if="canEdit" class="art-grid">
          <div class="art-card" @click="openGenerate('html')"><span class="art-icon ft-md">🌐</span><div class="art-name">网页</div><div class="art-desc">自动生成美观报告</div></div>
          <div class="art-card" @click="openGenerate('mindmap')"><span class="art-icon ft-xls">🧠</span><div class="art-name">思维导图</div><div class="art-desc">萃取结构化全景图</div></div>
          <div class="art-card" @click="openGenerate('ppt')"><span class="art-icon ft-ppt">📽</span><div class="art-name">PPT</div><div class="art-desc">可演示的幻灯片</div></div>
          <div class="art-card" @click="openGenerate('brief')"><span class="art-icon ft-xls" style="background:linear-gradient(135deg,#eccb6a,#d9a83b)">📋</span><div class="art-name">简报</div><div class="art-desc">摘要要点快读</div></div>
        </div>
        <div v-if="canEdit" class="art-chips">
          <span class="chip" @click="openGenerate('timeline')">＋ 时间轴</span>
        </div>
        <p class="art-note">生成的网页 / 导图 / PPT，和对话里保存的笔记，都收纳在这里。</p>

        <div class="art-list">
          <div v-for="a in artifacts" :key="a.id" class="art-item" @click="openArtifactTab(a)">
            <span class="art-item-icon">{{ { html: '🌐', mindmap: '🧠', ppt: '📽', brief: '📋', timeline: '📅' }[a.kind] || '📄' }}</span>
            <div class="art-item-info">
              <div class="art-item-name">{{ a.label }} · {{ a.title }}</div>
              <div class="art-item-time">{{ relativeTime(a.created_at) }}</div>
            </div>
            <span class="src-actions" @click.stop>
              <a v-if="a.kind === 'ppt'" class="src-act" title="下载 pptx" :href="`/api/knowledge/notebooks/${kid}/artifacts/${a.id}/pptx`"></a>
              <span v-if="canEdit" class="src-act danger" title="删除" @click="deleteArtifact(a.id)">✕</span>
            </span>
          </div>
        </div>
      </aside>
    </div>

    <!-- ===== 弹窗们 ===== -->
    <SourceAddDialog v-model="showAdd" :upload="uploadOne" :text="addText" />
    <KbSettingsDialog v-model="showSettings" :kb="kb" @save="saveSettings" @request-delete="showDelete = true" @transfered="loadAll" />
    <DeleteKbDialog v-model="showDelete" :kb="kb" @confirm="doDelete" />
    <ChatHistoryDrawer v-model="showHistory" :kid="kid" @select="loadChatSession" />

    <!-- 生成产物（设计稿 img_26/29：风格卡片 + 指令） -->
    <el-dialog v-model="showGenerate" :title="'生成' + genLabel" width="520px">
      <div class="gen-section">
        <el-select v-model="genSourceIds" multiple collapse-tags filterable style="width:100%" placeholder="依据来源：默认全部已解析来源">
          <el-option v-for="s in parsedSources" :key="s.id" :label="s.filename" :value="s.id" />
        </el-select>
      </div>
      <div v-if="genKind === 'mindmap'" class="gen-section">
        <div class="gen-label">导图类型</div>
        <div class="gen-cards">
          <div v-for="t in ['概括', '时间线', '对比', '结构']" :key="t" class="gen-card" :class="{ active: genMindmapType === t }" @click="genMindmapType = t">
            <div class="gen-card-title">{{ t }}</div>
          </div>
        </div>
      </div>
      <div v-if="genKind === 'html'" class="gen-section">
        <div class="gen-label">网页风格</div>
        <div class="gen-cards">
          <div v-for="t in ['简约白', '商务米色', '科技蓝紫', '深色专业']" :key="t" class="gen-card" :class="{ active: genStyle === t }" @click="genStyle = t">
            <div class="gen-card-title">{{ t }}</div>
          </div>
        </div>
      </div>
      <div v-if="genKind === 'ppt'" class="gen-section">
        <div class="gen-label">PPT 模板</div>
        <div class="gen-cards">
          <div v-for="t in ['简约白', '商务深色', '科技渐变']" :key="t" class="gen-card" :class="{ active: genTemplate === t }" @click="genTemplate = t">
            <div class="gen-card-title">{{ t }}</div>
          </div>
        </div>
      </div>
      <div class="gen-section">
        <div class="gen-label">生成指令（可选）</div>
        <el-input v-model="genInstruction" type="textarea" :rows="2" placeholder="例如：重点突出技术路线与结论" />
      </div>
      <template #footer>
        <button class="btn-ghost" @click="showGenerate = false">取消</button>
        <button class="btn-primary" :disabled="generating" @click="runGenerate">{{ generating ? '生成中…' : '开始生成' }}</button>
      </template>
    </el-dialog>
  </div>

  <!-- ===== Wiki 笔记详情（slug 兜底） ===== -->
  <div v-else-if="wikiPage" class="note-detail">
    <header class="nd-head">
      <button class="wd-back" @click="router.push('/notes')">‹ Wiki 笔记</button>
      <span class="nd-title">{{ wikiPage.title }}</span>
      <span class="col-spacer"></span>
      <button class="btn-outline" @click="toggleEdit">{{ editMode ? '取消编辑' : '编辑' }}</button>
      <button class="btn-danger" style="padding: 6px 14px" @click="deleteWiki">删除</button>
    </header>
    <div class="nd-body">
      <MarkdownEditor v-if="editMode" v-model="editContent" />
      <div v-else class="wiki-content cm-md" v-html="wikiRendered"></div>
      <button v-if="editMode" class="btn-primary" style="margin-top: 12px" @click="saveWiki">保存</button>
    </div>
  </div>

  <!-- 加载中 / 不存在 -->
  <div v-else class="note-detail">
    <header class="nd-head"><button class="wd-back" @click="goBack">‹ 返回</button><span class="nd-title">{{ loading ? '加载中…' : '页面不存在' }}</span></header>
    <div style="padding: 60px 0"><el-empty :image-size="60" :description="loading ? '加载中' : '页面不存在或已删除'" /></div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import MarkdownEditor from '../../components/MarkdownEditor.vue'
import MarkdownIt from 'markdown-it'
import ArtifactPreview from '../../components/wiki/ArtifactPreview.vue'
import ChatHistoryDrawer from '../../components/wiki/ChatHistoryDrawer.vue'
import SourcePreviewDialog from '../../components/wiki/SourcePreviewDialog.vue'
import SourceAddDialog from '../../components/wiki/SourceAddDialog.vue'
import KbSettingsDialog from '../../components/wiki/KbSettingsDialog.vue'
import DeleteKbDialog from '../../components/wiki/DeleteKbDialog.vue'
import { KB_COVERS, fileTypeInfo, formatSize } from '../../components/wiki/covers.js'
import { safeRender } from '../../utils/sanitize.js'

const route = useRoute()
const router = useRouter()
const kid = computed(() => route.params.id)

const loading = ref(true)
const kb = ref(null)
const kbList = ref([])
const kbSearch = ref('')
const sources = ref([])
const artifacts = ref([])

// 对话
const chatMsgs = ref([])
const chatInput = ref('')
const streaming = ref(false)
const currentChatId = ref(null)
const abortRef = ref(null)
const chatRef = ref(null)

// 选中聚焦
const selectMode = ref(false)
const selectedSources = ref([])

// 预览 tab：{kind:'source'|'artifact', data}
const previewTab = ref(null)

// 弹窗
const showAdd = ref(false)
const showSettings = ref(false)
const showDelete = ref(false)
const showHistory = ref(false)
const showGenerate = ref(false)

// 生成
const generating = ref(false)
const genKind = ref('html')
const genSourceIds = ref([])
const genMindmapType = ref('概括')
const genStyle = ref('简约白')
const genTemplate = ref('简约白')
const genInstruction = ref('')
const genLabel = computed(() => ({ html: '网页', mindmap: '思维导图', ppt: 'PPT', brief: '简报', timeline: '时间轴' }[genKind.value] || ''))

const md = new MarkdownIt({ html: true, linkify: true })
function renderMd(text) { return safeRender(md, text || '') }

// wiki 笔记兜底
const wikiPage = ref(null)
const editMode = ref(false)
const editContent = ref('')
const wikiRendered = computed(() => safeRender(md, wikiPage.value?.content || ''))

const parsedSources = computed(() => sources.value.filter(s => s.status === 'parsed'))
const filteredSources = computed(() => sources.value)

// 权限: 编辑及以上可上传/删除来源/生成产物/设置
const myRole = computed(() => kb.value?.my_role || 'viewer')
const canEdit = computed(() => ['admin', 'editor'].includes(myRole.value))
const isAdmin = computed(() => myRole.value === 'admin')

// PRD 3.2.6 推荐问题三条规则
const suggestedQuestions = computed(() => {
  const list = parsedSources.value
  const qs = []
  if (list.length >= 1) qs.push('这些资料的核心观点是什么？')
  if (list.length >= 1) {
    const first = list[0]?.filename?.replace(/\.[^.]+$/, '')
    if (first) qs.push(`「${first}」讲了什么？`)
  }
  if (list.length >= 2) qs.push('这几份资料之间有什么关联或分歧？')
  return qs
})

function coverEmoji(cover) { return (KB_COVERS.find(c => c.id === cover) || {}).emoji || '📚' }
function isSelected(s) { return selectedSources.value.some(x => x.id === s.id) }
function toggleSelect(s) { isSelected(s) ? unselectSource(s) : selectedSources.value.push(s) }
function unselectSource(s) { selectedSources.value = selectedSources.value.filter(x => x.id !== s.id) }

function relativeTime(ts) {
  if (!ts) return ''
  const diff = Date.now() - new Date(ts).getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 172800000) return '昨天'
  const d = new Date(ts)
  return `${d.getMonth() + 1}-${d.getDate()}`
}

function goBack() { router.push('/wiki') }
function switchKb(n) { if (n.id !== kid.value) router.push('/wiki/' + n.id) }
function openSettings() { showSettings.value = true }

// ── 数据加载 ──
async function loadAll() {
  loading.value = true
  try {
    const { data } = await axios.get('/api/knowledge/notebooks')
    kbList.value = data.items || []
    kb.value = kbList.value.find(n => n.id === kid.value) || null
    if (kb.value) {
      const s = await axios.get(`/api/knowledge/notebooks/${kid.value}/sources`)
      sources.value = s.data.items || []
      await loadArtifacts()
    } else {
      await loadWikiPage(kid.value)
    }
  } catch {
    await loadWikiPage(kid.value)
  }
  loading.value = false
  startPollingIfParsing()
}

async function loadWikiPage(slug) {
  try {
    const { data } = await axios.get(`/api/wiki/pages/${slug}`)
    if (data && !data.error) { wikiPage.value = data; editContent.value = data.content || '' }
  } catch { /* 页面不存在 */ }
}

async function loadArtifacts() {
  try {
    const { data } = await axios.get(`/api/knowledge/notebooks/${kid.value}/artifacts`)
    artifacts.value = data.items || []
  } catch { artifacts.value = [] }
}

// 解析中状态轮询（后端异步解析）
let pollTimer = null
function startPollingIfParsing() {
  stopPolling()
  if (sources.value.some(s => s.status === 'parsing')) {
    pollTimer = setInterval(async () => {
      try {
        const s = await axios.get(`/api/knowledge/notebooks/${kid.value}/sources`)
        sources.value = s.data.items || []
        if (!sources.value.some(x => x.status === 'parsing')) stopPolling()
      } catch { stopPolling() }
    }, 3000)
  }
}
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null } }
onBeforeUnmount(stopPolling)

watch(kid, () => {
  kb.value = null; wikiPage.value = null; chatMsgs.value = []
  selectedSources.value = []; previewTab.value = null; currentChatId.value = null
  loadAll()
})

// ── 来源操作 ──
async function uploadOne(file) {
  const fd = new FormData(); fd.append('file', file)
  await axios.post(`/api/knowledge/notebooks/${kid.value}/sources`, fd)
  const s = await axios.get(`/api/knowledge/notebooks/${kid.value}/sources`)
  sources.value = s.data.items || []
  startPollingIfParsing()
}

async function addText({ title, content }) {
  await axios.post(`/api/knowledge/notebooks/${kid.value}/sources/text`, { title, content })
  const s = await axios.get(`/api/knowledge/notebooks/${kid.value}/sources`)
  sources.value = s.data.items || []
}

async function deleteSource(sid) {
  try {
    await axios.delete(`/api/knowledge/notebooks/${kid.value}/sources/${sid}`)
    selectedSources.value = selectedSources.value.filter(x => x.id !== sid)
    const s = await axios.get(`/api/knowledge/notebooks/${kid.value}/sources`)
    sources.value = s.data.items || []
  } catch (e) { ElMessage.error('删除失败: ' + e.message) }
}

function downloadSource(s) { window.open(`/api/knowledge/notebooks/${kid.value}/sources/${s.id}/download`, '_blank') }
function openSourceTab(s) { previewTab.value = { kind: 'source', data: s } }
function openArtifactTab(a) { previewTab.value = { kind: 'artifact', data: a } }

// ── 对话(SSE 流式 + 块级引用) ──
const STEP_LABEL = { rewrite: '改写查询', graph: '图谱关联', grade: '评估检索', reflect: '反思补充' }
function stepChipText(s) {
  if (s.stage === 'rewrite') return s.text ? `改写: ${s.text}` : '改写查询'
  if (s.stage === 'graph') return `图谱命中 ${s.sources || 0} 个关联来源`
  if (s.stage === 'grade') return `评估: ${s.verdict === 'ok' ? '检索充分' : s.verdict === 'low' ? '沾边待补' : '未命中,重检中'}`
  if (s.stage === 'reflect') return '反思补充'
  return STEP_LABEL[s.stage] || s.stage
}
function citationClick(c) {
  const s = sources.value.find(x => x.filename === c.title)
  if (s) openSourceTab(s)
}

async function sendChat() {
  if (!chatInput.value.trim() || streaming.value) return
  const text = chatInput.value
  chatMsgs.value.push({ role: 'user', content: text })
  // 占位 assistant 消息, 流式填充内容 + agent 过程步骤
  const asstMsg = { role: 'assistant', content: '', citations: [], steps: [], streaming: true }
  chatMsgs.value.push(asstMsg)
  chatInput.value = ''; streaming.value = true
  nextTick(() => chatRef.value?.scrollTo({ top: 99999 }))
  const controller = new AbortController()
  abortRef.value = controller
  try {
    // 历史只发已完成的轮次(过滤占位 assistant)
    const history = chatMsgs.value
      .filter(m => m.role === 'user' || (m.role === 'assistant' && !m.streaming))
      .map(m => ({ role: m.role, content: m.content }))
    const resp = await fetch(`/api/knowledge/notebooks/${kid.value}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('token') ? { Authorization: `Bearer ${localStorage.getItem('token')}` } : {}),
      },
      body: JSON.stringify({
        messages: history,
        sourceIds: selectedSources.value.length ? selectedSources.value.map(s => s.id) : null,
        chatId: currentChatId.value,
      }),
      signal: controller.signal,
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        let ev
        try { ev = JSON.parse(line.slice(6)) } catch { continue }
        if (ev.type === 'meta') {
          currentChatId.value = ev.chat_id
          asstMsg.citations = ev.citations || []
        } else if (ev.type === 'citations') {
          asstMsg.citations = ev.citations || []
        } else if (ev.type === 'agent') {
          asstMsg.steps.push(ev)
        } else if (ev.type === 'token') {
          asstMsg.content += ev.text || ''
          nextTick(() => chatRef.value?.scrollTo({ top: 99999, behavior: 'smooth' }))
        } else if (ev.type === 'done') {
          asstMsg.content = ev.final_response || asstMsg.content
        } else if (ev.type === 'error') {
          asstMsg.content = ev.message || '回答失败'
        }
      }
    }
  } catch (e) {
    const aborted = e.name === 'AbortError' || e.code === 'ERR_CANCELED'
    const tail = aborted ? '⏹ 已手动终止回答。' : `请求失败: ${e.message}`
    asstMsg.content += asstMsg.content ? '\n\n' + tail : tail
  } finally {
    asstMsg.streaming = false
    streaming.value = false
    abortRef.value = null
    nextTick(() => chatRef.value?.scrollTo({ top: 99999, behavior: 'smooth' }))
  }
}

function stopChat() { abortRef.value?.abort() }
function quickChat(text) { chatInput.value = text; sendChat() }

async function loadChatSession(cid) {
  try {
    const { data } = await axios.get(`/api/knowledge/notebooks/${kid.value}/chats/${cid}`)
    currentChatId.value = cid
    chatMsgs.value = data.messages || []
    previewTab.value = null
    showHistory.value = false
    nextTick(() => chatRef.value?.scrollTo({ top: 99999 }))
  } catch (e) { ElMessage.error('加载历史失败: ' + e.message) }
}

// ── 知识库设置 / 删除 ──
async function saveSettings(form) {
  try {
    await axios.put(`/api/knowledge/notebooks/${kid.value}`, form)
    showSettings.value = false
    ElMessage.success('已保存')
    const { data } = await axios.get('/api/knowledge/notebooks')
    kbList.value = data.items || []
    kb.value = kbList.value.find(n => n.id === kid.value) || kb.value
  } catch (e) { ElMessage.error('保存失败: ' + e.message) }
}

async function doDelete() {
  try {
    await axios.delete(`/api/knowledge/notebooks/${kid.value}`)
    ElMessage.success('知识库已删除')
    router.push('/wiki')
  } catch (e) { ElMessage.error('删除失败: ' + e.message) }
}

// ── 产出 ──
function openGenerate(kind) {
  if (parsedSources.value.length === 0) { ElMessage.warning('请先上传并解析至少一份来源'); return }
  genKind.value = kind
  genSourceIds.value = []
  genInstruction.value = ''
  genMindmapType.value = '概括'
  genStyle.value = '简约白'
  genTemplate.value = '简约白'
  showGenerate.value = true
}

async function runGenerate() {
  generating.value = true
  try {
    const { data } = await axios.post(`/api/knowledge/notebooks/${kid.value}/generate`, {
      kind: genKind.value,
      source_ids: genSourceIds.value.length ? genSourceIds.value : null,
      instruction: genInstruction.value,
      mindmap_type: genMindmapType.value,
      style: genStyle.value,
      template: genTemplate.value,
    })
    if (data && data.degraded) { ElMessage.error(data.error || '生成失败'); return }
    showGenerate.value = false
    await loadArtifacts()
    previewTab.value = { kind: 'artifact', data }
    ElMessage.success('生成完成')
  } catch (e) {
    ElMessage.error('生成失败: ' + (e.response?.data?.detail || e.message))
  }
  generating.value = false
}

async function deleteArtifact(aid) {
  try {
    await axios.delete(`/api/knowledge/notebooks/${kid.value}/artifacts/${aid}`)
    await loadArtifacts()
  } catch (e) { ElMessage.error('删除失败: ' + e.message) }
}

// ── wiki 笔记 ──
function toggleEdit() { editMode.value = !editMode.value; if (editMode.value) editContent.value = wikiPage.value?.content || '' }
async function saveWiki() {
  try {
    const params = new URLSearchParams()
    if (editContent.value) params.set('content', editContent.value)
    params.set('tags', (wikiPage.value.tags || []).join(','))
    await axios.put(`/api/wiki/pages/${wikiPage.value.slug}?` + params.toString())
    editMode.value = false
    await loadWikiPage(wikiPage.value.slug)
    ElMessage.success('保存成功')
  } catch (e) { ElMessage.error('保存失败: ' + e.message) }
}
async function deleteWiki() {
  if (!window.confirm('确认删除该笔记？')) return
  try { await axios.delete(`/api/wiki/pages/${wikiPage.value.slug}`); router.push('/notes') } catch (e) { ElMessage.error('删除失败: ' + e.message) }
}

onMounted(async () => {
  await loadAll()
  if (route.query.add) showAdd.value = true
})
</script>

<style scoped>
.wd-root { display: flex; flex-direction: column; height: 100%; min-height: 0; gap: 12px; }

/* 顶栏 */
.wd-top { display: flex; align-items: center; gap: 12px; flex-shrink: 0; }
.wd-back {
  border: none; background: var(--accent-soft); color: var(--text-primary);
  padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.wd-back:hover { filter: brightness(.97); }
.wd-title { font-size: 16px; font-weight: 700; letter-spacing: -0.01em; }
.wd-counts { font-size: 12px; color: var(--text-tertiary); }
.wd-top-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
.wd-clear { border: none; background: var(--danger-soft); color: var(--danger); padding: 6px 12px; border-radius: 999px; font-size: 11px; font-weight: 600; cursor: pointer; }
.wd-hist { border: none; background: transparent; color: var(--text-secondary); padding: 6px 10px; border-radius: 999px; font-size: 12px; cursor: pointer; }
.wd-hist:hover { background: var(--bg-hover); }

/* 四栏 */
.wd-cols { flex: 1; display: flex; gap: 12px; min-height: 0; }
.wd-col {
  display: flex; flex-direction: column; min-height: 0;
  border-radius: 18px; border: 1px solid var(--border-light);
  background: var(--bg-subtle); overflow: hidden;
}
.wd-kbs { width: 200px; flex-shrink: 0; }
.wd-sources { width: 260px; flex-shrink: 0; }
.wd-chat { flex: 1; min-width: 0; background: linear-gradient(155deg, var(--bg-card) 0%, var(--bg-subtle) 100%); }
.wd-artifacts { width: 290px; flex-shrink: 0; }
.wd-artifacts.disabled .art-grid, .wd-artifacts.disabled .art-chips { opacity: .45; pointer-events: none; }

.col-head { display: flex; align-items: center; gap: 8px; padding: 12px 12px 8px; flex-shrink: 0; }
.col-title { font-size: 13px; font-weight: 700; }
.col-spacer { flex: 1; }
.col-search {
  width: 100%; border: 1px solid var(--border-input); background: var(--bg-card);
  border-radius: 999px; padding: 6px 12px; font-size: 12px; color: var(--text-primary); font-family: inherit;
}
.col-search:focus { outline: none; box-shadow: 0 0 0 3px var(--accent-soft); }

/* 列1 知识库列表 */
.kbs-list { flex: 1; overflow-y: auto; padding: 4px 8px 12px; }
.kbs-item {
  display: flex; gap: 8px; align-items: center; padding: 8px; border-radius: 12px;
  cursor: pointer; transition: background .15s; margin-bottom: 2px;
}
.kbs-item:hover { background: var(--bg-hover); }
.kbs-item.active { background: var(--bg-card); box-shadow: var(--shadow-soft); }
.kbs-dot { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; font-size: 14px; background: var(--tz-purple-soft); flex-shrink: 0; }
.kbs-name { font-size: 12px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kbs-meta { font-size: 10px; color: var(--text-muted); }

/* 列2 来源 */
.src-add { padding: 6px 14px; font-size: 12px; }
.src-select-toggle {
  width: 28px; height: 28px; border-radius: 9px; border: 1px solid var(--border-input);
  background: var(--bg-card); cursor: pointer; font-size: 13px; color: var(--text-tertiary);
}
.src-select-toggle.on { background: var(--accent-soft); color: var(--text-primary); border-color: var(--accent); }
.src-list { flex: 1; overflow-y: auto; padding: 4px 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.src-item {
  display: flex; align-items: center; gap: 8px; padding: 8px; border-radius: 12px;
  background: var(--bg-card); border: 1px solid transparent; cursor: pointer; transition: all .15s;
}
.src-item:hover { border-color: var(--border-input); }
.src-item.selected { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); }
.src-check {
  width: 16px; height: 16px; border-radius: 5px; border: 1.5px solid var(--border-focus);
  display: grid; place-items: center; font-size: 10px; color: #fff; flex-shrink: 0; background: var(--bg-card);
}
.src-check.on { background: var(--accent); border-color: var(--accent); color: var(--text-on-accent); }
html.dark .src-check.on { color: var(--text-on-accent); }
.src-icon {
  width: 30px; height: 30px; border-radius: 8px; color: #fff; flex-shrink: 0;
  display: grid; place-items: center; font-size: 9px; font-weight: 700; letter-spacing: .02em;
}
.src-info { flex: 1; min-width: 0; }
.src-name { font-size: 12px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.src-meta { font-size: 10px; color: var(--text-muted); margin-top: 2px; }
.src-err { color: var(--danger); cursor: help; }
.src-parsing { color: var(--tz-blue-ink); }
.src-actions { display: none; gap: 4px; flex-shrink: 0; }
.src-item:hover .src-actions { display: flex; }
.src-act { cursor: pointer; font-size: 12px; color: var(--text-tertiary); text-decoration: none; }
.src-act:hover { color: var(--text-primary); }
.src-act.danger:hover { color: var(--danger); }
.src-empty { text-align: center; padding: 36px 14px; color: var(--text-tertiary); }
.src-empty-icon { font-size: 34px; margin-bottom: 10px; }
.src-empty p { font-size: 12px; font-weight: 600; margin: 0 0 6px; }
.src-empty-sub { font-weight: 400 !important; color: var(--text-muted); line-height: 1.6; }

/* 列3 对话 */
.chat-tabs { display: flex; gap: 4px; padding: 10px 12px 0; flex-shrink: 0; }
.chat-tab {
  padding: 7px 14px 8px; border-radius: 12px 12px 0 0; font-size: 12px; font-weight: 600;
  color: var(--text-tertiary); cursor: pointer; max-width: 240px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.chat-tab.active { background: var(--bg-card); color: var(--text-primary); box-shadow: var(--shadow-soft); }
.chat-tab .tab-x { margin-left: 6px; color: var(--text-muted); }
.chat-tab .tab-x:hover { color: var(--danger); }

.chat-preview { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--bg-card); padding: 12px 16px 16px; overflow: hidden; }
.preview-topbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-shrink: 0; }
.preview-spacer { flex: 1; }
.chat-preview :deep(.src-preview-body) { flex: 1; min-height: 0; }

.chat-msgs { flex: 1; overflow-y: auto; padding: 16px 20px; min-height: 0; }
.chat-empty { text-align: center; padding: 48px 20px; color: var(--text-tertiary); }
.kb-illustration { font-size: 56px; margin-bottom: 14px; filter: grayscale(.1); }
.ce-main { font-size: 13px; margin: 0 0 14px; }
.ce-main b { color: var(--text-primary); }
.chat-suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
.sugg-chip {
  padding: 7px 14px; border-radius: 999px; border: 1px solid var(--border-input);
  background: var(--bg-card); cursor: pointer; font-size: 12px; color: var(--text-secondary); transition: all .15s;
}
.sugg-chip:hover { border-color: var(--accent); color: var(--text-primary); box-shadow: var(--shadow-soft); }

.chat-msg { margin-bottom: 14px; }
.chat-msg.user { display: flex; justify-content: flex-end; }
.cm-bubble.user {
  max-width: 78%; padding: 9px 14px; border-radius: 16px 16px 4px 16px;
  background: var(--bg-hover); color: var(--text-primary); font-size: 13px; line-height: 1.6; white-space: pre-wrap;
}
.cm-ai { width: 100%; }
.cm-steps { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 6px; }
.cm-step { font-size: 10.5px; color: var(--text-muted); background: var(--chip-bg, rgba(120, 120, 120, 0.08)); border: 1px solid var(--chip-border, rgba(120, 120, 120, 0.18)); border-radius: 999px; padding: 1px 9px; }
.cm-citations { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 6px; }
.cc-label { font-size: 11px; color: var(--text-muted); }
.cc-chip { font-size: 11px; color: var(--accent, #4a6cf7); background: var(--chip-bg, rgba(74, 108, 247, 0.08)); border: 1px solid var(--chip-border, rgba(74, 108, 247, 0.2)); border-radius: 999px; padding: 2px 10px; cursor: pointer; transition: background .15s; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cc-chip:hover { background: var(--chip-bg, rgba(74, 108, 247, 0.16)); }
.cm-md { font-size: 13.5px; line-height: 1.7; color: var(--text-primary); }
.cm-md :deep(h1), .cm-md :deep(h2), .cm-md :deep(h3) { margin: 14px 0 8px; letter-spacing: -0.01em; }
.cm-md :deep(p) { margin: 6px 0; }
.cm-md :deep(code) { padding: 2px 6px; background: var(--md-code-bg); color: var(--md-code-color); border-radius: 5px; font-family: var(--font-mono); font-size: 12px; }
.cm-md :deep(pre) { padding: 12px; background: var(--md-code-bg); border-radius: 12px; overflow-x: auto; }
.cm-md :deep(pre code) { background: none; color: inherit; padding: 0; }
.cm-md :deep(blockquote) { margin: 8px 0; padding: 8px 14px; border-left: 3px solid var(--md-blockquote-border); background: var(--md-blockquote-bg); border-radius: 0 10px 10px 0; color: var(--text-secondary); }
.cm-md :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.cm-md :deep(th), .cm-md :deep(td) { border: 1px solid var(--md-table-border); padding: 6px 10px; font-size: 12px; }
.cm-md :deep(th) { background: var(--md-table-header-bg); }
.cm-md :deep(img) { max-width: 100%; border-radius: 10px; }

/* 聚焦条 */
.focus-strip {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin: 0 16px 8px; padding: 8px 12px; border-radius: 12px;
  background: var(--tz-yellow-soft); color: var(--tz-yellow-ink); font-size: 11px;
}
.focus-strip.idle { background: var(--bg-subtle); color: var(--text-tertiary); }
.fs-label { font-weight: 600; }
.fs-clear { border: none; background: transparent; color: inherit; cursor: pointer; font-size: 11px; text-decoration: underline; }

/* 输入壳 */
.chat-composer {
  margin: 0 16px 14px; border-radius: 20px; background: var(--bg-card);
  border: 1px solid var(--border-light); box-shadow: var(--shadow-soft);
  padding: 10px 14px 8px; flex-shrink: 0;
}
.composer-input {
  width: 100%; border: none; background: transparent; resize: none;
  font-family: inherit; font-size: 13px; color: var(--text-primary); line-height: 1.6;
  max-height: 120px;
}
.composer-input:focus { outline: none; }
.composer-input::placeholder { color: var(--text-muted); }
.composer-bar { display: flex; align-items: center; }
.composer-attach { border: none; background: transparent; cursor: pointer; font-size: 14px; padding: 4px; border-radius: 8px; }
.composer-attach:hover { background: var(--bg-hover); }
.composer-spacer { flex: 1; }
.composer-send {
  width: 30px; height: 30px; border-radius: 50%; border: none; cursor: pointer;
  background: var(--accent-gradient); color: var(--text-on-accent); font-size: 14px; font-weight: 700;
  transition: transform .15s;
}
.composer-send:disabled { opacity: .35; cursor: not-allowed; }
.composer-send:not(:disabled):hover { transform: scale(1.08); }
.composer-stop {
  width: 30px; height: 30px; border-radius: 50%; border: none; cursor: pointer;
  background: var(--danger); color: #fff; font-size: 11px;
}

/* 列4 产物 */
.art-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 4px 12px 0; }
.art-card {
  border-radius: 16px; padding: 14px 12px; cursor: pointer;
  background: var(--bg-card); border: 1px solid var(--border-light); transition: all .18s;
}
.art-card:hover { box-shadow: var(--shadow-soft); transform: translateY(-2px); }
.art-icon {
  width: 34px; height: 34px; border-radius: 10px; display: grid; place-items: center;
  font-size: 15px; margin-bottom: 8px;
}
.art-name { font-size: 12px; font-weight: 700; }
.art-desc { font-size: 10px; color: var(--text-muted); margin-top: 3px; }
.art-chips { display: flex; gap: 6px; padding: 12px 12px 0; }
.art-chips .chip { cursor: pointer; }
.art-note { font-size: 11px; color: var(--text-muted); line-height: 1.6; padding: 10px 14px 0; margin: 0; }
.art-list { flex: 1; overflow-y: auto; padding: 10px 8px 12px; display: flex; flex-direction: column; gap: 6px; }
.art-item {
  display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 12px;
  background: var(--bg-card); border: 1px solid transparent; cursor: pointer; transition: border-color .15s;
}
.art-item:hover { border-color: var(--border-input); }
.art-item-icon { font-size: 16px; flex-shrink: 0; }
.art-item-info { flex: 1; min-width: 0; }
.art-item-name { font-size: 11px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.art-item-time { font-size: 10px; color: var(--text-muted); margin-top: 2px; }

/* 生成弹窗 */
.gen-section { margin-bottom: 14px; }
.gen-label { font-size: 12px; color: var(--text-tertiary); margin-bottom: 8px; }
.gen-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.gen-card {
  border: 1.5px solid var(--border-input); border-radius: 12px; padding: 12px 8px;
  text-align: center; cursor: pointer; transition: all .15s; background: var(--bg-subtle);
}
.gen-card:hover { border-color: var(--border-focus); }
.gen-card.active { border-color: var(--accent); background: var(--accent-soft); }
.gen-card-title { font-size: 12px; font-weight: 600; }

/* 笔记详情 */
.note-detail { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.nd-head { display: flex; align-items: center; gap: 10px; flex-shrink: 0; margin-bottom: 12px; }
.nd-title { font-size: 16px; font-weight: 700; }
.nd-body { flex: 1; overflow-y: auto; background: var(--bg-card); border-radius: 18px; border: 1px solid var(--border-light); padding: 20px 24px; }
.wiki-content { font-size: 13.5px; }
</style>

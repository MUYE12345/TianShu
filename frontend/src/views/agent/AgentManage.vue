<template>
  <div class="agent-layout">
    <!-- 左侧：智能体列表 -->
    <aside class="agent-list-panel">
      <div class="panel-head">
        <h2 class="panel-title">智能体管理</h2>
        <el-button type="primary" :icon="Plus" round size="small" @click="showCreateDialog = true">新建</el-button>
      </div>
      <div class="agent-stats">
        <div class="stat-unit"><span class="stat-val">{{ agents.length }}</span> 全部</div>
        <div class="stat-unit"><span class="stat-val active">{{ enabledCount }}</span> 在线</div>
        <div class="stat-unit"><span class="stat-val muted">{{ agents.length - enabledCount }}</span> 离线</div>
      </div>
      <div class="agent-filter">
        <el-input v-model="query" placeholder="搜索智能体..." clearable :prefix-icon="Search" size="small" />
      </div>
      <el-scrollbar class="agent-scroll">
        <div v-for="agent in filteredAgents" :key="agent.id"
             class="agent-list-item" :class="{ selected: selectedId === agent.id }"
             @click="selectAgent(agent)">
          <div class="ali-avatar" :style="{ background: categoryColor(agent.category) }">{{ agent.name.charAt(0) }}</div>
          <div class="ali-info">
            <div class="ali-name">{{ agent.name }}</div>
            <div class="ali-desc">{{ agent.description || '无描述' }}</div>
          </div>
          <div class="ali-status"><span class="status-dot" :class="agent.enabled ? 'on' : 'off'" /></div>
        </div>
        <el-empty v-if="filteredAgents.length === 0" description="无匹配结果" :image-size="40" />
      </el-scrollbar>
    </aside>

    <!-- 右侧：详情面板 -->
    <div class="agent-detail-panel">
      <div v-if="!selectedAgent" class="detail-empty">
        <div class="empty-icon">🤖</div>
        <p>从左侧选择一个智能体查看详情</p>
      </div>

      <template v-else>
        <!-- 头部 -->
        <div class="detail-header">
          <div class="dh-avatar" :style="{ background: categoryColor(selectedAgent.category) }">{{ selectedAgent.name.charAt(0) }}</div>
          <div class="dh-info">
            <h2>{{ selectedAgent.name }}</h2>
            <p>{{ selectedAgent.description }}</p>
          </div>
          <el-switch v-model="selectedAgent.enabled" @change="toggleAgent(selectedAgent)" />
        </div>
        <div class="detail-tags">
          <el-tag size="small" round>{{ selectedAgent.category }}</el-tag>
          <el-tag size="small" round type="info">{{ selectedAgent.model || '默认模型' }}</el-tag>
          <el-tag size="small" round :type="selectedAgent.enabled ? 'success' : 'danger'">{{ selectedAgent.enabled ? '已启用' : '已停用' }}</el-tag>
        </div>

        <!-- Tab 导航 -->
        <div class="detail-tabs">
          <button v-for="t in tabs" :key="t.key" :class="['tab-btn', { active: activeTab === t.key }]" @click="activeTab = t.key">
            {{ t.label }}
          </button>
        </div>

        <!-- Tab: 基本资料 -->
        <div v-if="activeTab === 'overview'" class="tab-content">
          <el-form label-width="80px" class="detail-form">
            <el-form-item label="名称"><el-input v-model="selectedAgent.name" /></el-form-item>
            <el-form-item label="描述"><el-input v-model="selectedAgent.description" type="textarea" :rows="2" /></el-form-item>
            <el-form-item label="分类">
              <el-select v-model="selectedAgent.category">
                <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
              </el-select>
            </el-form-item>
            <el-form-item label="模型">
              <el-select v-model="selectedAgent.model_id" style="width:100%" placeholder="选择已配置的模型">
                <el-option v-for="m in llmModels" :key="m.id" :label="m.model_name" :value="m.id" />
                <el-option v-if="llmModels.length === 0" label="暂无已配置模型，请先到 设置→模型 中添加" value="0" disabled />
              </el-select>
            </el-form-item>
            <el-form-item label="温度">
              <el-slider v-model="selectedAgent.temperature" :min="0" :max="1" :step="0.1" style="width:200px" />
            </el-form-item>
            <el-form-item label="系统提示">
              <el-input v-model="selectedAgent.systemPrompt" type="textarea" :rows="4" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="saveAgent(selectedAgent)">保存更改</el-button>
              <el-button type="danger" plain @click="deleteAgent(selectedAgent)">删除此智能体</el-button>
            </el-form-item>
          </el-form>
        </div>

        <!-- Tab: 能力配置 -->
        <div v-if="activeTab === 'capabilities'" class="tab-content">
          <div class="cap-section">
            <h3 class="cap-title">🔧 可用工具 <el-tag size="small" round>{{ tools.length }}</el-tag></h3>
            <div class="cap-grid">
              <div v-for="tool in tools" :key="tool.id" class="cap-item" :class="{ enabled: selectedAgent.config?.tools?.includes(tool.id) }"
                   @click="toggleCap('tools', tool.id)">
                <div class="cap-check">{{ selectedAgent.config?.tools?.includes(tool.id) ? '✓' : '' }}</div>
                <div class="cap-info">
                  <div class="cap-name">{{ tool.name || tool.title || tool.id }}</div>
                  <div class="cap-desc">{{ tool.description || '' }}</div>
                </div>
                <el-tag size="small" round :type="tool.category === 'builtin' ? 'success' : 'warning'" effect="plain">{{ tool.category }}</el-tag>
              </div>
            </div>
          </div>

          <div class="cap-section">
            <h3 class="cap-title">🧩 可用技能 <el-tag size="small" round>{{ skills.length }}</el-tag></h3>
            <div class="cap-grid">
              <div v-for="skill in skills" :key="skill.id" class="cap-item" :class="{ enabled: selectedAgent.config?.skills?.includes(skill.id) }"
                   @click="toggleCap('skills', skill.id)">
                <div class="cap-check">{{ selectedAgent.config?.skills?.includes(skill.id) ? '✓' : '' }}</div>
                <div class="cap-info">
                  <div class="cap-name">{{ skill.name || skill.title || skill.id }}</div>
                  <div class="cap-desc">{{ skill.description || '' }}</div>
                </div>
                <el-tag size="small" round effect="plain" v-if="skill.version">v{{ skill.version }}</el-tag>
              </div>
            </div>
          </div>

          <div class="cap-section">
            <h3 class="cap-title">🔗 MCP 工具 <el-tag size="small" round>{{ mcps.length }}</el-tag></h3>
            <div class="cap-grid">
              <div v-for="mcp in mcps" :key="mcp.id" class="cap-item" :class="{ enabled: selectedAgent.config?.mcps?.includes(mcp.id) }"
                   @click="toggleCap('mcps', mcp.id)">
                <div class="cap-check">{{ selectedAgent.config?.mcps?.includes(mcp.id) ? '✓' : '' }}</div>
                <div class="cap-info">
                  <div class="cap-name">{{ mcp.title || mcp.name || mcp.id }}</div>
                  <div class="cap-desc">{{ mcp.description || '' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Tab: 基本资料 (selectedAgent) -->
    </div>

    <!-- 新建智能体对话框 -->
    <el-dialog v-model="showCreateDialog" title="新建智能体" width="480px" destroy-on-close>
      <el-form :model="newAgentForm" label-width="70px">
        <el-form-item label="名称"><el-input v-model="newAgentForm.name" placeholder="输入智能体名称" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="newAgentForm.description" type="textarea" :rows="2" placeholder="简短描述其功能" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="newAgentForm.category" style="width:100%">
            <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            <el-option label="自定义" value="自定义" />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="newAgentForm.model_id" style="width:100%" placeholder="选择已配置的模型">
            <el-option v-for="m in llmModels" :key="m.id" :label="m.model_name" :value="m.id" />
            <el-option v-if="llmModels.length === 0" label="暂无已配置模型，请先到 设置→模型 中添加" value="0" disabled />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Plus, Search } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

const API = '/api/agents'
const agents = ref([])
const selectedId = ref(null)
const query = ref('')
const showCreateDialog = ref(false)
const creating = ref(false)
const activeTab = ref('overview')
const tools = ref([])
const skills = ref([])
const mcps = ref([])
// 模型列表与"设置→模型"共用同一数据源 (/api/models)，保证两边互通
const models = ref([])

const newAgentForm = ref({
  name: '',
  description: '',
  category: '通用',
  model_id: null,
})

const llmModels = computed(() => models.value.filter(m => m.model_type === 'llm' && m.is_active))

const tabs = [
  { key: 'overview', label: '基本资料' },
  { key: 'capabilities', label: '能力与安全' },
]

const loading = ref(false)
const selectedAgent = computed(() => agents.value.find(a => a.id === selectedId.value) || null)
const enabledCount = computed(() => agents.value.filter(a => a.enabled).length)
const categories = computed(() => [...new Set(agents.value.map(a => a.category))])

const filteredAgents = computed(() => {
  let list = agents.value
  if (query.value) {
    const q = query.value.toLowerCase()
    list = list.filter(a => a.name.toLowerCase().includes(q) || a.description?.toLowerCase().includes(q))
  }
  return list
})

async function handleCreate() {
  if (!newAgentForm.value.name.trim()) {
    ElMessage.warning('请输入智能体名称')
    return
  }
  // 未选模型时默认使用第一个已配置的 LLM，避免落到空模型
  if (newAgentForm.value.model_id == null) {
    newAgentForm.value.model_id = llmModels.value[0]?.id || 0
  }
  creating.value = true
  try {
    const { data } = await axios.post(API, newAgentForm.value)
    agents.value.push(data)
    selectedId.value = data.id
    showCreateDialog.value = false
    ElMessage.success('创建成功')
  } catch (e) {
    ElMessage.error('创建失败: ' + (e.response?.data?.detail || e.message))
  }
  creating.value = false
}

function selectAgent(agent) { selectedId.value = agent.id; activeTab.value = 'overview' }

function categoryColor(cat) {
  const m = { '对话': '#7c5cad', '分析': '#a17f29', '数据': '#5a7bb3', '工具': '#3d8047', '自动化': '#b85469', '通用': '#6b6b73' }
  return m[cat] || '#6b6b73'
}

function toggleCap(type, id) {
  const agent = agents.value.find(a => a.id === selectedId.value)
  if (!agent) return
  if (!agent.config) agent.config = {}
  if (!agent.config[type]) agent.config[type] = []
  const idx = agent.config[type].indexOf(id)
  if (idx >= 0) agent.config[type].splice(idx, 1)
  else agent.config[type].push(id)
  saveAgent(agent)
}

async function fetchAgents() {
  loading.value = true
  try {
    const { data } = await axios.get(API)
    agents.value = (data.items || []).map(a => {
      if (typeof a.config === 'string') try { a.config = JSON.parse(a.config) } catch { a.config = {} }
      if (!a.config) a.config = {}
      return a
    })
    if (agents.value.length > 0 && !selectedId.value) selectedId.value = agents.value[0].id
  } catch (e) {
    ElMessage.error('加载智能体失败: ' + (e.response?.data?.detail || e.message))
  }
  loading.value = false
}

async function fetchCapabilities() {
  try {
    const [tRes, sRes, mRes] = await Promise.allSettled([
      axios.get('/api/tool-marketplace'),
      axios.get('/api/skills/marketplace'),
      axios.get('/api/mcp/marketplace'),
    ])
    if (tRes.status === 'fulfilled') tools.value = tRes.value.data?.items || []
    if (sRes.status === 'fulfilled') skills.value = sRes.value.data?.items || []
    if (mRes.status === 'fulfilled') mcps.value = mRes.value.data?.items || []
  } catch {}
}

async function fetchModels() {
  try {
    const { data } = await axios.get('/api/models')
    models.value = Array.isArray(data) ? data : (data.items || [])
  } catch {}
}

async function toggleAgent(agent) {
  try {
    await axios.post(`${API}/${agent.id}/toggle`)
    ElMessage.success(agent.enabled ? '已启用' : '已停用')
  } catch (e) {
    agent.enabled = !agent.enabled
    ElMessage.error('操作失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function saveAgent(agent) {
  try {
    await axios.put(`${API}/${agent.id}`, agent)
    // 同步展示名（模型名来自统一配置列表）
    const m = llmModels.value.find(x => x.id === agent.model_id)
    if (m) agent.model = m.model_name
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error('保存失败: ' + (e.response?.data?.detail || e.message))
  }
}

async function deleteAgent(agent) {
  try {
    await axios.delete(`${API}/${agent.id}`)
    agents.value = agents.value.filter(a => a.id !== agent.id)
    selectedId.value = agents.value[0]?.id || null
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + (e.response?.data?.detail || e.message))
  }
}

onMounted(() => { fetchAgents(); fetchCapabilities(); fetchModels() })
</script>

<style scoped>
.agent-layout { display: flex; height: 100%; background: var(--bg); border-radius: var(--radius-lg); overflow: hidden; }

/* 左侧面板 */
.agent-list-panel { width: 300px; background: var(--bg-card); border-right: 1px solid var(--border); display: flex; flex-direction: column; flex-shrink: 0; }
.panel-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 16px 8px; }
.panel-title { font-size: 16px; font-weight: 600; margin: 0; }
.agent-stats { display: flex; gap: 16px; padding: 8px 16px; font-size: 12px; color: var(--text-tertiary); }
.stat-val { font-weight: 600; font-size: 16px; margin-right: 2px; }
.stat-val.active { color: #67C23A; }
.stat-val.muted { color: var(--text-tertiary); }
.agent-filter { padding: 4px 16px 8px; }
.agent-scroll { flex: 1; padding: 0 8px; }
.agent-list-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 8px; cursor: pointer; transition: all 0.15s; margin-bottom: 2px; }
.agent-list-item:hover { background: var(--sidebar-hover); }
.agent-list-item.selected { background: var(--primary-light); }
.ali-avatar { width: 36px; height: 36px; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 600; font-size: 14px; flex-shrink: 0; }
.ali-info { flex: 1; min-width: 0; }
.ali-name { font-size: 13px; font-weight: 500; }
.ali-desc { font-size: 11px; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 1px; }
.ali-status { flex-shrink: 0; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; display: block; }
.status-dot.on { background: #67C23A; }
.status-dot.off { background: #d1d5db; }

/* 右侧详情 */
.agent-detail-panel { flex: 1; padding: 20px 24px; overflow-y: auto; }
.detail-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-tertiary); }
.detail-empty .empty-icon { font-size: 48px; margin-bottom: 12px; }
.detail-header { display: flex; align-items: center; gap: 16px; margin-bottom: 8px; }
.dh-avatar { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 700; font-size: 16px; flex-shrink: 0; }
.dh-info { flex: 1; }
.dh-info h2 { margin: 0; font-size: 18px; }
.dh-info p { margin: 4px 0 0; font-size: 13px; color: var(--text-secondary); }
.detail-tags { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.detail-tabs { display: flex; gap: 4px; padding: 3px; border-radius: 8px; background: var(--bg-subtle); margin-bottom: 16px; }
.tab-btn { padding: 6px 14px; border-radius: 6px; font-size: 12px; border: none; cursor: pointer; background: transparent; color: var(--text-secondary); transition: all 0.15s; }
.tab-btn.active { background: var(--bg-card); color: var(--text-primary); font-weight: 600; box-shadow: 0 1px 2px rgba(0,0,0,0.06); }
.tab-content { }
.detail-form { max-width: 560px; }

/* 能力网格 */
.cap-section { margin-bottom: 20px; }
.cap-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; margin: 0 0 8px; }
.cap-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 6px; }
.cap-item { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; transition: all 0.15s; }
.cap-item:hover { border-color: var(--primary); }
.cap-item.enabled { background: var(--primary-light); border-color: var(--primary); }
.cap-check { width: 20px; height: 20px; border-radius: 4px; border: 1px solid var(--border); display: grid; place-items: center; font-size: 12px; font-weight: 700; flex-shrink: 0; color: transparent; }
.cap-item.enabled .cap-check { background: var(--primary); border-color: var(--primary); color: #fff; }
.cap-info { flex: 1; min-width: 0; }
.cap-name { font-size: 13px; font-weight: 500; }
.cap-desc { font-size: 11px; color: var(--text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 暗色适配 */
html.dark .status-dot.off { background: #4a4a68; }
html.dark .agent-list-item.selected { background: var(--sidebar-active-bg); }
</style>

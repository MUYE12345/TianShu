<template>
  <div class="model-page">
    <header class="page-head">
      <div>
        <h1>模型管理</h1>
        <p class="desc">管理 AI 模型提供商，为各功能指派默认模型</p>
      </div>
      <el-button type="primary" @click="openAdd">+ 添加模型</el-button>
    </header>

    <!-- 加载/空状态 -->
    <div v-if="loading" class="state-hint">加载中…</div>
    <div v-else-if="models.length === 0" class="state-hint">
      暂无模型配置。点 "+ 添加模型" 开始，或启动后端自动从 .env 导入。
    </div>

    <!-- 模型卡片列表 -->
    <div v-else class="model-list">
      <article v-for="m in models" :key="m.id" class="model-card" :class="{ inactive: !m.is_active }">
        <div class="card-top">
          <div class="card-tags">
            <el-tag size="small" :type="m.is_active ? 'success' : 'info'" effect="plain">
              {{ m.is_active ? '启用' : '停用' }}
            </el-tag>
            <el-tag size="small" effect="plain" type="">{{ m.model_type.toUpperCase() }}</el-tag>
            <el-tag v-if="m.is_default" size="small" type="warning" effect="plain">默认</el-tag>
            <el-tag v-if="m.thinking_mode" size="small" effect="plain" type="">💭 思考</el-tag>
            <el-tag v-if="m.vision_support" size="small" effect="plain" type="">👁 视觉</el-tag>
          </div>
          <div class="card-actions">
            <el-button size="small" @click="testModel(m)">测试</el-button>
            <el-button size="small" @click="toggleModel(m)">{{ m.is_active ? '停用' : '启用' }}</el-button>
            <el-button v-if="!m.is_default && m.model_type === 'llm' && m.is_active" size="small" type="warning" plain @click="setDefault(m)">设为默认</el-button>
            <el-button size="small" @click="openEdit(m)">编辑</el-button>
            <el-button size="small" type="danger" plain @click="deleteModel(m)">删除</el-button>
          </div>
        </div>
        <div class="card-meta">
          <span class="meta-name">{{ m.name }}</span>
          <span class="meta-model">模型：<code>{{ m.model_name }}</code></span>
          <span class="meta-url">API：<code>{{ m.api_base }}</code></span>
          <span class="meta-temp">温度：{{ m.temperature }}</span>
          <span v-if="m.embedding_dimensions" class="meta-dim">维度：{{ m.embedding_dimensions }}</span>
        </div>
      </article>
    </div>

    <!-- 功能指派 -->
    <div v-if="models.length > 0" class="assignment-section">
      <h2>功能指派</h2>
      <p class="desc">为不同功能选择默认使用的模型</p>
      <div class="assignment-grid">
        <label class="assign-item">
          <span>对话模型</span>
          <el-select v-model="assign.chat" placeholder="选择模型" size="small" @change="saveAssign">
            <el-option v-for="m in llmModels" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </label>
        <label class="assign-item">
          <span>审查模型</span>
          <el-select v-model="assign.review" placeholder="选择模型" size="small" @change="saveAssign">
            <el-option label="同对话模型" :value="0" />
            <el-option v-for="m in llmModels" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </label>
        <label class="assign-item">
          <span>嵌入模型</span>
          <el-select v-model="assign.embedding" placeholder="选择模型" size="small" @change="saveAssign">
            <el-option label="无" :value="0" />
            <el-option v-for="m in embeddingModels" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </label>
        <label class="assign-item">
          <span>多模态模型</span>
          <el-select v-model="assign.multimodal" placeholder="选择模型" size="small" @change="saveAssign">
            <el-option label="同对话模型" :value="0" />
            <el-option v-for="m in visionModels" :key="m.id" :label="m.name" :value="m.id" />
          </el-select>
        </label>
      </div>
    </div>

    <!-- 添加/编辑弹窗 -->
    <el-dialog v-model="dialog.visible" :title="dialog.isEdit ? '编辑模型' : '添加模型'" width="520px" destroy-on-close>
      <el-form v-if="dialog.visible" label-position="top" size="small">
        <el-form-item v-if="!dialog.isEdit" label="快速添加（常用模型预设）">
          <el-select v-model="selectedPreset" placeholder="选择后自动填充下方配置，再填 API Key 即可" clearable filterable style="width:100%" @change="applyPreset">
            <el-option v-for="p in presets" :key="p.model_name" :label="p.label" :value="p.model_name" />
          </el-select>
        </el-form-item>
        <el-form-item label="显示名称">
          <el-input v-model="form.name" placeholder="可选，默认同模型名" />
        </el-form-item>
        <el-form-item label="模型类型" required>
          <el-radio-group v-model="form.model_type">
            <el-radio value="llm">LLM（对话）</el-radio>
            <el-radio value="embedding">Embedding（嵌入）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="模型名" required>
          <el-input v-model="form.model_name" placeholder="gpt-4o / deepseek-chat" />
        </el-form-item>
        <el-form-item label="API 地址" required>
          <el-input v-model="form.api_base" placeholder="https://api.openai.com/v1" />
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input v-model="form.api_key" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="温度 ({{ form.temperature }})">
              <el-slider v-model="form.temperature" :min="0" :max="2" :step="0.1" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="最大 Token">
              <el-input-number v-model="form.max_tokens" :min="1024" :max="65536" :step="1024" size="small" controls-position="right" />
            </el-form-item>
          </el-col>
        </el-row>
        <!-- LLM 专属选项 -->
        <template v-if="form.model_type === 'llm'">
          <div class="feature-checks">
            <el-checkbox v-model="form.thinking_mode">思考模式</el-checkbox>
            <template v-if="form.thinking_mode">
              <el-form-item label="思考预算 (tokens)" style="margin-left:16px">
                <el-input-number v-model="form.thinking_budget" :min="1024" :max="32768" :step="1024" size="small" controls-position="right" />
              </el-form-item>
            </template>
            <el-checkbox v-model="form.vision_support">视觉支持</el-checkbox>
          </div>
        </template>
        <!-- Embedding 专属选项 -->
        <el-form-item v-if="form.model_type === 'embedding'" label="向量维度">
          <el-input-number v-model="form.embedding_dimensions" :min="1" :max="8192" size="small" placeholder="留空自动探测" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="dialog.saving" @click="saveModel">{{ dialog.isEdit ? '保存' : '添加' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

// ── State ──
const models = ref([])
const loading = ref(true)
const editingId = ref(null)
const assign = reactive({ chat: null, review: null, embedding: null, multimodal: null })

const dialog = reactive({ visible: false, isEdit: false, saving: false })
const selectedPreset = ref('')

// 常用模型预设：与智能体模型列表互通，快速填充常用配置
const presets = [
  { label: 'DeepSeek Chat', model_name: 'deepseek-chat', provider: 'openai', api_base: 'https://api.deepseek.com/v1', thinking_mode: false, vision_support: false },
  { label: 'DeepSeek Reasoner', model_name: 'deepseek-reasoner', provider: 'openai', api_base: 'https://api.deepseek.com/v1', thinking_mode: true, vision_support: false },
  { label: 'GPT-4o', model_name: 'gpt-4o', provider: 'openai', api_base: 'https://api.openai.com/v1', thinking_mode: false, vision_support: true },
  { label: 'GPT-4o-mini', model_name: 'gpt-4o-mini', provider: 'openai', api_base: 'https://api.openai.com/v1', thinking_mode: false, vision_support: true },
  { label: 'Claude Sonnet 4', model_name: 'claude-sonnet-4', provider: 'anthropic', api_base: 'https://api.anthropic.com', thinking_mode: false, vision_support: true },
  { label: '通义千问 Qwen-Max', model_name: 'qwen-max', provider: 'openai', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', thinking_mode: false, vision_support: false },
  { label: '通义千问 Qwen-Plus', model_name: 'qwen-plus', provider: 'openai', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', thinking_mode: false, vision_support: false },
  { label: '通义千问 Qwen-Flash', model_name: 'qwen-flash', provider: 'openai', api_base: 'https://dashscope.aliyuncs.com/compatible-mode/v1', thinking_mode: false, vision_support: false },
]

function applyPreset(name) {
  const p = presets.find(x => x.model_name === name)
  if (!p) return
  Object.assign(form, emptyForm(), {
    provider: p.provider,
    api_base: p.api_base,
    model_name: p.model_name,
    thinking_mode: p.thinking_mode,
    vision_support: p.vision_support,
  })
  selectedPreset.value = ''
}

const form = reactive({
  name: '', provider: 'openai', model_type: 'llm',
  api_base: '', api_key: '', model_name: '',
  temperature: 0.7, max_tokens: 8192,
  thinking_mode: false, thinking_budget: 4000,
  vision_support: false, embedding_dimensions: null,
})

function emptyForm() {
  return {
    name: '', provider: 'openai', model_type: 'llm',
    api_base: '', api_key: '', model_name: '',
    temperature: 0.7, max_tokens: 8192,
    thinking_mode: false, thinking_budget: 4000,
    vision_support: false, embedding_dimensions: null,
  }
}

// ── Computed ──
const llmModels = computed(() => models.value.filter(m => m.model_type === 'llm' && m.is_active))
const embeddingModels = computed(() => models.value.filter(m => m.model_type === 'embedding' && m.is_active))
const visionModels = computed(() => models.value.filter(m => m.model_type === 'llm' && m.vision_support && m.is_active))

// ── API helpers ──
function authHeaders(extra = {}) {
  const token = localStorage.getItem('token')
  return { ...extra, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}
async function apiGet(path) { const r = await fetch(path, { headers: authHeaders() }); return r.json() }
async function apiPost(path, body) {
  const r = await fetch(path, { method: 'POST', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) })
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
  return r.json()
}
async function apiPut(path, body) {
  const r = await fetch(path, { method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }), body: JSON.stringify(body) })
  if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${r.status}`) }
  return r.json()
}
async function apiDel(path) { await fetch(path, { method: 'DELETE', headers: authHeaders() }) }

async function refresh() {
  loading.value = true
  try {
    models.value = await apiGet('/api/models')
    const defs = await apiGet('/api/models/defaults')
    assign.chat = defs.default_chat_id
    assign.review = defs.default_review_id
    assign.embedding = defs.default_embedding_id
    assign.multimodal = defs.default_multimodal_id
  } catch (e) {
    ElMessage.error('加载失败: ' + e.message)
  }
  loading.value = false
}

// ── Actions ──
function openAdd() {
  editingId.value = null
  Object.assign(form, emptyForm())
  selectedPreset.value = ''
  dialog.isEdit = false
  dialog.visible = true
}

function openEdit(m) {
  editingId.value = m.id
  Object.assign(form, {
    name: m.name, provider: m.provider, model_type: m.model_type,
    api_base: m.api_base, api_key: '', model_name: m.model_name,
    temperature: parseFloat(m.temperature) || 0.7, max_tokens: m.max_tokens,
    thinking_mode: m.thinking_mode, thinking_budget: m.thinking_budget,
    vision_support: m.vision_support, embedding_dimensions: m.embedding_dimensions,
  })
  dialog.isEdit = true
  dialog.visible = true
}

async function saveModel() {
  if (!form.api_base || !form.model_name) {
    ElMessage.warning('API 地址和模型名不能为空')
    return
  }
  dialog.saving = true
  try {
    const body = {
      name: (form.name || form.model_name).trim(),
      provider: form.provider,
      api_base: form.api_base.trim(),
      api_key: form.api_key.trim(),
      model_name: form.model_name.trim(),
      model_type: form.model_type,
      temperature: form.temperature,
      max_tokens: form.max_tokens,
      thinking_mode: form.model_type === 'llm' ? form.thinking_mode : false,
      thinking_budget: form.thinking_budget,
      vision_support: form.model_type === 'llm' ? form.vision_support : false,
      embedding_dimensions: form.model_type === 'embedding' ? form.embedding_dimensions : null,
    }
    if (editingId.value) {
      await apiPut('/api/models/' + editingId.value, body)
      ElMessage.success('模型已更新')
    } else {
      await apiPost('/api/models', body)
      ElMessage.success('模型已创建')
    }
    dialog.visible = false
    await refresh()
  } catch (e) {
    ElMessage.error('保存失败: ' + e.message)
  }
  dialog.saving = false
}

async function toggleModel(m) {
  try {
    await apiPost('/api/models/' + m.id + '/toggle')
    await refresh()
  } catch (e) { ElMessage.error(e.message) }
}

async function setDefault(m) {
  try {
    await apiPost('/api/models/' + m.id + '/set-default')
    await refresh()
    ElMessage.success(m.name + ' 已设为默认')
  } catch (e) { ElMessage.error(e.message) }
}

async function deleteModel(m) {
  try {
    await ElMessageBox.confirm('确定删除模型 "' + m.name + '"?', '确认', { type: 'warning' })
  } catch { return /* 取消 */ }
  try {
    const r = await fetch('/api/models/' + m.id, { method: 'DELETE', headers: authHeaders() })
    if (!r.ok) {
      const e = await r.json().catch(() => ({}))
      throw new Error(e.detail || `HTTP ${r.status}`)
    }
    await refresh()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

async function testModel(m) {
  try {
    const r = await apiPost('/api/models/' + m.id + '/test')
    if (r.status === 'ok') ElMessage.success('连接成功')
    else ElMessage.error(r.message)
  } catch (e) { ElMessage.error('测试失败: ' + e.message) }
}

async function saveAssign() { /* assign 随 refresh 读取 */ }

onMounted(refresh)
</script>

<style scoped>
.model-page { padding: 24px; max-width: 960px; margin: 0 auto; }
.page-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-head h1 { margin: 0; font-size: 20px; font-weight: 700; }
.desc { margin: 4px 0 0; color: var(--text-secondary); font-size: 13px; }
.state-hint { text-align: center; color: var(--text-tertiary); padding: 48px 0; font-size: 13px; }

.model-list { display: flex; flex-direction: column; gap: 12px; }
.model-card {
  border: 1px solid var(--border); border-radius: 12px;
  padding: 14px 16px; background: var(--bg-card);
}
.model-card.inactive { opacity: 0.55; }
.card-top { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.card-tags { display: flex; gap: 6px; flex-wrap: wrap; }
.card-actions { display: flex; gap: 4px; flex-wrap: wrap; }
.card-meta { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: var(--text-secondary); }
.meta-name { font-weight: 600; color: var(--text-primary); }
.meta-model code, .meta-url code { color: var(--text-primary); font-size: 12px; }

.assignment-section { margin-top: 32px; }
.assignment-section h2 { margin: 0; font-size: 16px; font-weight: 600; }
.assignment-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 12px; }
.assign-item { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--text-secondary); }
.feature-checks { display: flex; align-items: center; gap: 8px; padding: 8px 0; }

@media (max-width: 768px) {
  .assignment-grid { grid-template-columns: 1fr; }
  .card-top { flex-direction: column; align-items: flex-start; }
}
</style>

<template>
  <div class="agent-layout">
    <!-- ===== 左侧 Dock (64px) ===== -->
    <aside class="agent-dock">
      <div class="dock-item active" title="AI 问答">
        <span class="dock-icon">💬</span>
      </div>
      <div class="dock-item" title="智能体" @click="$router.push('/agent')">
        <span class="dock-icon">🤖</span>
      </div>
      <div class="dock-item" title="工具市场" @click="$router.push('/tools')">
        <span class="dock-icon">🔧</span>
      </div>
      <div class="dock-spacer" />
      <div class="dock-item" title="设置" @click="$router.push('/settings/model')">
        <span class="dock-icon">⚙️</span>
      </div>
    </aside>

    <!-- ===== 会话列（历史会话，可折叠） ===== -->
    <aside class="session-panel" :class="{ collapsed: !showSessions }">
      <div v-if="showSessions" class="sp-head">
        <span class="sp-title">会话</span>
        <div class="sp-actions">
          <button class="sp-new" title="新建对话" @click="newSession">＋</button>
          <button class="sp-fold" title="折叠会话栏" @click="showSessions = false">‹</button>
        </div>
      </div>
      <div v-if="showSessions" class="sp-list">
        <div v-for="s in sessions" :key="s.id" class="sp-item" :class="{ active: s.id === currentSessionId }" @click="switchSession(s.id)">
          <div class="sp-item-title">{{ s.title }}</div>
          <div class="sp-item-meta">{{ shortTime(s.created_at) }}</div>
          <span class="sp-del" title="删除" @click.stop="deleteSession(s.id)">✕</span>
        </div>
        <div v-if="!sessions.length" class="sp-empty">暂无历史会话</div>
      </div>
      <div v-else class="sp-rail" title="展开会话栏" @click="showSessions = true">
        <span class="sp-rail-text">会话</span>
      </div>
    </aside>

    <!-- ===== 中栏：对话区 ===== -->
    <section class="chat-panel">
      <!-- 头部 -->
      <header class="chat-head">
        <div class="head-left">
          <!-- 智能体选择器 -->
          <el-dropdown trigger="click" @command="selectAgent">
            <span class="agent-pill">
              <span class="ap-avatar" :style="{ background: currentAgentColor }">{{ currentAgent?.name?.charAt(0) || '🤖' }}</span>
              <span class="ap-name">{{ currentAgent?.name || '默认智能体' }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-item v-for="a in agents" :key="a.id" :command="a.id">
                <span class="dropdown-agent">
                  <span class="da-dot" :style="{ background: categoryColor(a.category) }"></span>
                  <span>{{ a.name }}</span>
                  <el-tag v-if="a.enabled" size="small" type="success" effect="plain" style="margin-left:6px">在线</el-tag>
                  <el-tag v-else size="small" type="info" effect="plain" style="margin-left:6px">离线</el-tag>
                </span>
              </el-dropdown-item>
            </template>
          </el-dropdown>
          <span v-if="currentAgent?.model" class="agent-model-tag">{{ currentAgent.model }}</span>
        </div>
        <div class="head-right">
          <el-tooltip content="开启后模型先深度思考再输出回答，推理过程实时展示" placement="bottom">
            <div class="expert-toggle" :class="{ active: thinkingMode }" @click="thinkingMode = !thinkingMode">
              <span class="expert-icon">💡</span>
              <span class="expert-label">思考</span>
              <el-switch v-model="thinkingMode" size="small" style="margin-left:4px" />
            </div>
          </el-tooltip>
          <el-tooltip content="开启后天枢可根据需要创建子智能体协作完成任务" placement="bottom">
            <div class="expert-toggle" :class="{ active: expertMode }" @click="expertMode = !expertMode">
              <span class="expert-icon">🧠</span>
              <span class="expert-label">专家</span>
              <el-switch v-model="expertMode" size="small" style="margin-left:4px" />
            </div>
          </el-tooltip>
        </div>
      </header>

      <!-- 消息区 -->
      <div class="messages-area" ref="messagesRef">
        <!-- 空状态：欢迎屏 -->
        <div v-if="isFresh" class="fresh-hero">
          <div class="hero-avatar">{{ greeting }}, <strong>{{ userName }}</strong></div>
          <h1 class="hero-title">有什么可以帮你的？</h1>
          <div class="hero-suggestions">
            <div class="suggestion-pill" @click="quickChat('今天有什么新闻？')">📰 今日新闻</div>
            <div class="suggestion-pill" @click="quickChat('今天天气怎么样？')">🌤 查天气</div>
            <div class="suggestion-pill" @click="quickChat('帮我检查一下代码')">💻 检查代码</div>
            <div class="suggestion-pill" @click="quickChat('帮我制定学习计划')">📚 学习计划</div>
          </div>
        </div>

        <!-- 对话消息 -->
        <template v-else>
          <transition-group name="msg" tag="div" class="msg-list">
            <div v-for="(msg, idx) in messages" :key="msg.id" class="msg-row" :class="msg.role">
              <template v-if="msg.role === 'assistant'">
                <div class="msg-avatar avi-ai">AI</div>
                <div class="assistant-stack">
                  <!-- 思考过程：紧贴在内容气泡上方，带折叠按钮（类 tianzhi2 展示） -->
                  <ThinkingBlock v-if="msg.thinking && msg.thinking.length" :steps="msg.thinking" />
                  <div class="msg-card">
                    <div class="msg-body" v-html="renderMarkdown(msg.content)" />
                    <div v-if="msg.tokens" class="msg-footer">
                      <span class="msg-stat">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        {{ msg.duration || '?' }}s
                      </span>
                      <span class="msg-stat">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="2" width="20" height="20" rx="4"/><path d="M12 8v8M8 12h8"/></svg>
                        {{ formatTokens(msg.tokens) }}
                      </span>
                      <span v-if="msg.cost" class="msg-stat">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                        ${{ msg.cost }}
                      </span>
                      <span v-if="msg.time" class="msg-stat msg-time">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 8 14"/></svg>
                        {{ msg.time }}
                      </span>
                    </div>
                  </div>
                </div>
              </template>
              <template v-else>
                <div class="msg-card user-card">
                  <div class="msg-body" v-html="renderMarkdown(msg.content)"></div>
                  <div v-if="msg.time" class="msg-footer user-footer">
                    <span class="msg-stat msg-time">{{ msg.time }}</span>
                  </div>
                </div>
                <div class="msg-avatar avi-user">U</div>
              </template>
            </div>
          </transition-group>

          <!-- 工具调用卡片 (在消息之间展示) -->
          <transition-group name="msg" tag="div" class="tool-calls-list">
            <div v-for="tc in toolCalls" :key="tc.id" class="tool-call-wrapper">
              <ToolCallCard :tool-call="tc" />
            </div>
          </transition-group>

          <!-- 思考中气泡 (尚无正式文本时) -->
          <transition name="fade">
            <div v-if="streaming && !streamingText" class="msg-row assistant">
              <div class="msg-avatar avi-ai">AI</div>
              <div class="assistant-stack">
                <ThinkingBlock v-if="thinkingSteps.length > 0" :steps="thinkingSteps" :streaming="true" />
                <div class="msg-card thinking">
                  <div class="thinking-dots"><span></span><span></span><span></span></div>
                </div>
              </div>
            </div>
          </transition>

          <!-- 流式回复 (带打字机效果，思考块紧跟上方) -->
          <transition name="msg">
            <div v-if="streamingText" class="msg-row assistant">
              <div class="msg-avatar avi-ai">AI</div>
              <div class="assistant-stack">
                <ThinkingBlock v-if="thinkingSteps.length > 0" :steps="thinkingSteps" :streaming="true" />
                <div class="msg-card streaming">
                  <div class="msg-body" v-html="renderMarkdown(streamingText)" />
                  <span class="cursor-blink">▍</span>
                </div>
              </div>
            </div>
          </transition>
        </template>

        <div ref="bottomRef" />
      </div>

      <!-- 状态栏 -->
      <transition name="fade">
        <div v-if="statusText" class="status-bar">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>{{ statusText }}</span>
        </div>
      </transition>

      <!-- 输入区 -->
      <div class="composer-area" :class="{ 'composer-hero': isFresh }">
        <div class="composer-shell">
          <div class="composer-main">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="1"
              :placeholder="isFresh ? '输入消息，Enter 发送' : '输入消息，Enter 发送，Shift+Enter 换行'"
              :disabled="streaming"
              @keydown.enter.exact="sendMessage"
              autosize
              class="composer-input"
            />
            <div class="composer-actions">
              <el-button v-if="streaming" type="danger" round @click="stopStream" class="stop-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>
                停止
              </el-button>
              <el-button v-else type="primary" @click="sendMessage" :disabled="!inputText.trim()" class="send-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- ===== 右侧信息面板 ===== -->
    <aside v-if="!isFresh" class="context-panel">
      <div class="panel-card session-info">
        <div class="panel-card-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
          对话信息
        </div>
        <div class="context-stat"><span class="ctx-label">消息数</span><span class="ctx-value">{{ messages.length }}</span></div>
        <div class="context-stat"><span class="ctx-label">Tokens</span><span class="ctx-value">{{ formatTokens(totalTokens) }}</span></div>
        <div class="context-stat"><span class="ctx-label">模式</span><span class="mode-badge" :class="{ expert: expertMode }">{{ expertMode ? '🧠 专家' : '💬 普通' }}</span></div>
      </div>
      <div class="panel-card">
        <div class="panel-card-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="9" x2="15" y2="15"/><line x1="15" y1="9" x2="9" y2="15"/></svg>
          快捷操作
        </div>
        <div class="context-action" @click="newSession">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 5v14M5 12h14"/></svg>
          新建对话
        </div>
        <div class="context-action" @click="clearMessages">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          清空对话
        </div>
      </div>
      <div class="panel-card">
        <div class="panel-card-title">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
          工具调用
        </div>
        <div v-if="toolCalls.length === 0" class="context-empty">暂无工具调用</div>
        <div v-for="tc in toolCalls.slice(-3)" :key="tc.id" class="context-tool-item">
          <span class="cti-name">{{ tc.name }}</span>
          <span class="cti-status" :class="tc.status">{{ tc.status === 'running' ? '⟳' : '✓' }}</span>
        </div>
      </div>
    </aside>
  </div>
</template>

<script>
export default { name: 'ChatPage' }
</script>

<script setup>
import { ref, computed, onMounted, onActivated, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { ArrowDown, Loading } from '@element-plus/icons-vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import MarkdownIt from 'markdown-it'
import ToolCallCard from './components/ToolCallCard.vue'
import ThinkingBlock from './components/ThinkingBlock.vue'

// ── Markdown-it 实例 ─────────────────────────────────────────────
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: true,
})
// 代码高亮（行号 + 语言标签）
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = token.info.trim()
  const code = token.content
  const lines = code.split('\n')
  // 末尾空行不占计数
  if (lines.length > 1 && lines[lines.length - 1] === '') lines.pop()
  const numbered = lines.map((l, i) => `<span class="cl-line">${escapeHtml(l)}</span>`).join('\n')
  return `<div class="cl-block">
    <div class="cl-header">${lang ? `<span class="cl-lang">${escapeHtml(lang)}</span>` : ''}<span class="cl-count">${lines.length} 行</span></div>
    <pre class="cl-pre"><code>${numbered}</code></pre>
  </div>`
}

function escapeHtml(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// ── State ────────────────────────────────────────────────────────
const messages = ref([])
const streamingText = ref('')
const inputText = ref('')
const statusText = ref('')
const streaming = ref(false)
const expertMode = ref(false)
const thinkingMode = ref(false)
const toolCalls = ref([])
const thinkingSteps = ref([])
const sessions = ref([])
const currentSessionId = ref(null)
const showSessions = ref(true)
const messagesRef = ref(null)
const bottomRef = ref(null)
const agents = ref([])
const abortRef = ref(null)
const currentAgentId = ref(null)
const route = useRoute()

// Token 统计
const totalTokens = ref(0)

const currentAgent = computed(() => agents.value.find(a => a.id === currentAgentId.value) || agents.value[0] || null)
const currentAgentColor = computed(() => categoryColor(currentAgent.value?.category))
const isFresh = computed(() => messages.value.length === 0 && !streamingText.value)

const userName = '主人'
const now = new Date()
const hour = now.getHours()
const greeting = hour < 6 ? '晚上好' : hour < 12 ? '早上好' : hour < 18 ? '下午好' : '晚上好'

function categoryColor(cat) {
  const m = { '对话': '#6366f1', '分析': '#f59e0b', '数据': '#3b82f6', '工具': '#10b981', '自动化': '#ec4899', '通用': '#8b5cf6' }
  return m[cat] || '#6b7280'
}

function selectAgent(id) { currentAgentId.value = id }

// 格式化当前时间 HH:mm
function nowTime() {
  const d = new Date()
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

// 格式化 Token
function formatTokens(n) {
  if (!n && n !== 0) return '0'
  if (n < 1000) return String(n)
  return (n / 1000).toFixed(n < 10000 ? 1 : 0) + 'k'
}

// 格式化 Cost
function formatCost(usd) {
  if (!usd && usd !== 0) return ''
  return usd.toFixed(4)
}

function newSession() {
  currentSessionId.value = null
  messages.value = []
  streamingText.value = ''
  toolCalls.value = []
  thinkingSteps.value = []
  totalTokens.value = 0
  localStorage.removeItem('lastChatSessionId')
}

function shortTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  if (isNaN(d.getTime())) return ''
  const hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  return d.toDateString() === new Date().toDateString()
    ? hm
    : `${d.getMonth() + 1}-${d.getDate()} ${hm}`
}

function fmtMsgTime(iso) {
  if (!iso) return nowTime()
  const d = new Date(iso)
  if (isNaN(d.getTime())) return nowTime()
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
}

async function loadSessions() {
  try {
    const { data } = await axios.get('/api/chat/sessions')
    sessions.value = Array.isArray(data) ? data : (data?.items || [])
  } catch {
    sessions.value = []
  }
}

async function switchSession(id) {
  currentSessionId.value = id
  localStorage.setItem('lastChatSessionId', String(id))
  messages.value = []
  streamingText.value = ''
  toolCalls.value = []
  thinkingSteps.value = []
  totalTokens.value = 0
  try {
    const { data } = await axios.get(`/api/chat/sessions/${id}/messages`)
    messages.value = (data || []).map(m => ({
      id: 'msg_' + m.id,
      role: m.role,
      content: m.content,
      time: fmtMsgTime(m.created_at),
    }))
  } catch (e) {
    ElMessage.error('加载会话失败: ' + e.message)
  }
  nextTick(() => bottomRef.value?.scrollIntoView())
}

async function deleteSession(id) {
  try {
    await axios.delete(`/api/chat/sessions/${id}`)
    if (currentSessionId.value === id) newSession()
    await loadSessions()
  } catch (e) {
    ElMessage.error('删除失败: ' + e.message)
  }
}

// 懒建会话：首条消息时才创建，并用首条消息作标题
async function ensureSession(text) {
  if (currentSessionId.value) return currentSessionId.value
  const { data } = await axios.post('/api/chat/sessions')
  currentSessionId.value = data.id
  localStorage.setItem('lastChatSessionId', String(data.id))
  try {
    await axios.put(`/api/sessions/${data.id}`, { title: (text || '').slice(0, 20) })
  } catch { /* 标题失败不阻断 */ }
  await loadSessions()
  return data.id
}

function stopStream() {
  if (abortRef.value) {
    abortRef.value.abort()
    abortRef.value = null
  }
  streaming.value = false
  statusText.value = ''
  if (streamingText.value) {
    messages.value.push({
      role: 'assistant',
      content: streamingText.value,
      id: 'msg_' + Date.now().toString(36),
      time: nowTime(),
    })
    streamingText.value = ''
  }
}

function clearMessages() {
  messages.value = []
  toolCalls.value = []
  thinkingSteps.value = []
  totalTokens.value = 0
}

function quickChat(text) {
  inputText.value = text
  sendMessage()
}

// ── Markdown 渲染（安全过滤） ────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return ''
  const html = md.render(text)
  // 防止 XSS：只允许白名单标签
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .replace(/on\w+\s*=\s*"[^"]*"/gi, '')
    .replace(/on\w+\s*=\s*'[^']*'/gi, '')
}

// ── 发送消息 ──────────────────────────────────────────────────────
async function sendMessage() {
  if (!inputText.value.trim() || streaming.value) return
  const text = inputText.value
  const msgId = 'msg_' + Date.now().toString(36)
  messages.value.push({ role: 'user', content: text, id: msgId, time: nowTime() })
  inputText.value = ''
  streaming.value = true
  statusText.value = '思考中...'
  toolCalls.value = []
  thinkingSteps.value = []

  try {
    const sid = await ensureSession(text)
    const controller = new AbortController()
    abortRef.value = controller
    const resp = await fetch(`/api/chat/sessions/${sid}/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        content: text,
        expert_mode: expertMode.value,
        thinking_mode: thinkingMode.value,
      }),
      signal: controller.signal,
    })

    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`)
    }

    statusText.value = '生成中...'
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let fullText = ''
    let totalInputTokens = 0
    let totalOutputTokens = 0
    let totalCostUSD = 0
    let durationStart = Date.now()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try {
          const event = JSON.parse(line.slice(6))
          const type = event.type

          if (type === 'token') {
            fullText += event.text || ''
            streamingText.value = fullText
          } else if (type === 'thinking') {
            // 仅思考模式开启时展示思考过程
            if (thinkingMode.value) {
              thinkingSteps.value.push({ type: 'think', content: event.text, id: 'th_' + Date.now().toString(36) })
              statusText.value = '深度思考中...'
            }
          } else if (type === 'plan') {
            // 规划过程也仅在思考模式开启时展示
            if (thinkingMode.value) {
              thinkingSteps.value.push({ type: 'plan', content: event.plan, id: 'pl_' + Date.now().toString(36) })
            }
          } else if (type === 'tool_start') {
            toolCalls.value.push({ id: 'tc_' + Date.now().toString(36), name: event.name, status: 'running', args: event.args ?? event.raw_args ?? '' })
          } else if (type === 'tool_result') {
            const tc = toolCalls.value.find(t => t.name === event.name)
            if (tc) {
              tc.status = 'done'
              tc.result = event.result
            }
          } else if (type === 'reflect' || type === 'self_refine') {
            statusText.value = '推理中...'
          } else if (type === 'agent_turn') {
            statusText.value = `[${event.agent}] ${event.status || ''}`
          } else if (type === 'session_state') {
            // 从后端获取真实的 token / cost 数据
            if (event.totalInputTokens !== undefined) totalInputTokens = event.totalInputTokens
            if (event.totalOutputTokens !== undefined) totalOutputTokens = event.totalOutputTokens
            if (event.totalCostUSD !== undefined) totalCostUSD = event.totalCostUSD
            totalTokens.value = totalInputTokens + totalOutputTokens
          } else if (type === 'error') {
            fullText = event.message || '回答失败，请稍后重试'
            streamingText.value = fullText
          }
        } catch {
          // 忽略解析错误
        }
      }
    }

    // 流结束，推入正式消息（思考过程紧贴其上，一并归属本条消息）
    if (fullText) {
      const duration = ((Date.now() - durationStart) / 1000).toFixed(1)
      messages.value.push({
        role: 'assistant',
        content: fullText,
        thinking: [...thinkingSteps.value],
        id: 'msg_' + Date.now().toString(36),
        tokens: totalInputTokens + totalOutputTokens || Math.round(fullText.length * 0.75),
        duration: duration,
        cost: totalCostUSD > 0 ? formatCost(totalCostUSD) : null,
        time: nowTime(),
      })
      thinkingSteps.value = []
    }
  } catch (e) {
    // 降级：后端不可用时简单回复
    if (e.name !== 'AbortError') {
      messages.value.push({
        role: 'assistant',
        content: `（后端暂不可用: ${e.message}）`,
        id: 'msg_' + Date.now().toString(36),
        time: nowTime(),
      })
    }
  }

  streaming.value = false
  streamingText.value = ''
  statusText.value = ''
  thinkingSteps.value = []
  await loadSessions()
  nextTick(() => {
    bottomRef.value?.scrollIntoView({ behavior: 'smooth' })
  })
}

async function loadAgents() {
  try {
    const { data } = await axios.get('/api/agents')
    agents.value = data.items || []
    if (agents.value.length > 0) currentAgentId.value = agents.value[0].id
  } catch {
    // 静默失败
  }
}

onMounted(async () => {
  loadAgents()
  await loadSessions()
  const lastId = localStorage.getItem('lastChatSessionId')
  const target = route.params.sessionId ||
    (lastId && sessions.value.some(s => String(s.id) === lastId) ? lastId : null)
  if (target) { await switchSession(target) } else { newSession() }
})

onActivated(async () => { await loadSessions() })
</script>

<style scoped>
/* ═══════════════════════════════════════════════
   Agent Q&A — 全面升级样式（类 tz2 风格）
   ═══════════════════════════════════════════════ */
.agent-layout {
  display: flex;
  height: 100%;
  background: var(--bg);
  overflow: hidden;
}

/* ── 会话列 ── */
.session-panel {
  width: 208px; background: var(--bg-subtle);
  border-right: 1px solid var(--border-light);
  display: flex; flex-direction: column; flex-shrink: 0; min-width: 0;
  transition: width .25s cubic-bezier(0.22, 1, 0.36, 1);
}
.session-panel.collapsed { width: 30px; }
.sp-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 12px 8px; }
.sp-title { font-size: 11px; font-weight: 700; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .05em; }
.sp-actions { display: flex; gap: 4px; }
.sp-new, .sp-fold {
  width: 24px; height: 24px; border-radius: 8px; border: none;
  background: var(--bg-card); cursor: pointer; color: var(--text-secondary);
  box-shadow: var(--shadow-soft); font-size: 13px; line-height: 1;
}
.sp-new:hover, .sp-fold:hover { background: var(--accent-soft); color: var(--text-primary); }
/* 折叠后的竖向小轨道 */
.sp-rail { flex: 1; display: flex; align-items: center; justify-content: center; cursor: pointer; }
.sp-rail:hover { background: var(--bg-hover); }
.sp-rail-text { writing-mode: vertical-rl; font-size: 11px; font-weight: 700; letter-spacing: .25em; color: var(--text-tertiary); }
.sp-list { flex: 1; overflow-y: auto; padding: 4px 8px 12px; display: flex; flex-direction: column; gap: 4px; }
.sp-item { position: relative; padding: 8px 10px; border-radius: 10px; cursor: pointer; transition: background .15s; }
.sp-item:hover { background: var(--bg-hover); }
.sp-item.active { background: var(--bg-card); box-shadow: var(--shadow-soft); }
.sp-item-title { font-size: 12px; font-weight: 600; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding-right: 16px; }
.sp-item-meta { font-size: 10px; color: var(--text-muted); margin-top: 3px; }
.sp-del {
  position: absolute; top: 7px; right: 7px; width: 18px; height: 18px; border-radius: 6px;
  display: none; place-items: center; font-size: 10px; color: var(--text-muted); cursor: pointer;
}
.sp-item:hover .sp-del { display: grid; }
.sp-del:hover { color: var(--danger); background: var(--danger-soft); }
.sp-empty { padding: 20px 12px; text-align: center; font-size: 12px; color: var(--text-muted); }

/* ── 左侧 Dock ── */
.agent-dock {
  width: 56px;
  background: var(--bg-card);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  gap: 4px;
  flex-shrink: 0;
  z-index: 10;
}
.dock-item {
  width: 40px; height: 40px;
  border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
  font-size: 18px;
  position: relative;
}
.dock-item:hover { background: var(--sidebar-hover); }
.dock-item.active { background: var(--accent-soft); }
.dock-item.active::before {
  content: '';
  position: absolute;
  left: -4px; top: 50%;
  transform: translateY(-50%);
  width: 3px; height: 18px;
  border-radius: 0 3px 3px 0;
  background: var(--primary);
}
.dock-spacer { flex: 1; }

/* ── 中栏：对话 ── */
.chat-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  position: relative;
  background: var(--bg-card);
}

.chat-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  min-height: 52px;
  background: var(--bg-card);
  z-index: 5;
}
.head-left { display: flex; align-items: center; gap: 12px; }
.agent-pill { display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 4px 10px 4px 4px; border-radius: 20px; border: 1px solid var(--border); transition: all .15s; font-size: 13px; }
.agent-pill:hover { border-color: var(--primary); }
.ap-avatar { width: 24px; height: 24px; border-radius: 6px; display: grid; place-items: center; color: #fff; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.ap-name { font-weight: 500; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-model-tag { font-size: 11px; color: var(--text-tertiary); padding: 2px 8px; background: var(--bg-subtle); border-radius: 8px; }
.head-right { display: flex; align-items: center; gap: 4px; }
.expert-toggle { display: flex; align-items: center; gap: 4px; padding: 4px 10px; border-radius: 20px; cursor: pointer; transition: all 0.2s; border: 1px solid var(--border); font-size: 12px; }
.expert-toggle:hover { border-color: var(--primary); background: var(--bg-subtle); }
.expert-toggle.active { background: var(--tz-yellow-soft); border-color: var(--tz-yellow); }
.expert-icon { font-size: 14px; line-height: 1; }
.expert-label { white-space: nowrap; color: var(--text-secondary); font-size: 12px; }
.expert-toggle.active .expert-label { color: var(--tz-yellow-ink); font-weight: 500; }

/* ── 消息区 ── */
.messages-area {
  flex: 1;
  overflow-y: auto;
  padding: 16px 24px;
  scroll-behavior: smooth;
}
.messages-area::-webkit-scrollbar { width: 4px; }
.messages-area::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }
.messages-area::-webkit-scrollbar-thumb:hover { background: #9ca3af; }

.msg-list {
  display: flex;
  flex-direction: column;
}

/* ── 欢迎屏 ── */
.fresh-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 32px 20px 0;
  text-align: center;
  animation: heroFadeIn 0.6s ease-out;
}
@keyframes heroFadeIn {
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
}
.hero-avatar {
  font-size: 18px;
  color: var(--text-secondary);
  margin-bottom: 8px;
  padding: 8px 20px;
  border-radius: 20px;
  background: var(--bg-subtle);
}
.hero-title {
  font-size: 30px;
  font-weight: 700;
  letter-spacing: -0.02em;
  margin-bottom: 32px;
  color: var(--text-primary);
  font-family: var(--font-display);
}
.hero-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-bottom: 0;
}
.suggestion-pill {
  padding: 9px 18px;
  border-radius: 999px;
  background: var(--bg-card);
  border: 1px solid var(--border-input);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
  font-weight: 500;
  color: var(--text-secondary);
  box-shadow: var(--shadow-soft);
}
.suggestion-pill:hover {
  border-color: var(--accent);
  color: var(--text-primary);
  transform: translateY(-1px);
}

/* ── 消息 ── */
.msg-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
  align-items: flex-start;
  animation: msgSlideIn 0.3s ease-out;
}
@keyframes msgSlideIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.msg-row.user { flex-direction: row-reverse; }
.msg-avatar {
  width: 32px; height: 32px;
  border-radius: 8px;
  display: grid; place-items: center;
  font-size: 12px; font-weight: 700;
  flex-shrink: 0;
  letter-spacing: -.5px;
}
.avi-ai {
  background: var(--tz-purple-soft);
  color: var(--tz-purple-ink);
  box-shadow: var(--shadow-soft);
}
.avi-user {
  background: var(--bg-hover);
  color: var(--text-tertiary);
}
.msg-card {
  max-width: 72%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 12px 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.02);
  transition: box-shadow 0.2s;
}
.msg-card:hover {
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.user-card {
  background: var(--bg-hover);
  border-color: transparent;
  border-radius: 16px 16px 4px 16px;
}
.user-card .msg-body { color: var(--text-primary); }

/* ── 助手消息纵向堆叠：思考块紧贴内容气泡上方 ── */
.assistant-stack {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  max-width: 72%;
  min-width: 0;
}
.assistant-stack .msg-card {
  max-width: 100%;
}
.assistant-stack .thinking-block-wrapper {
  margin: 0 0 6px 0;
  width: 100%;
}
.msg-card.streaming {
  border-color: var(--primary);
  box-shadow: 0 0 0 1px var(--primary-light);
}
.msg-card.thinking {
  display: flex; flex-direction: column; gap: 6px;
  padding: 16px 20px; min-width: 100px;
  border-color: #e8ecf4;
}
.msg-body {
  font-size: 14px;
  line-height: 1.7;
  word-break: break-word;
  color: var(--text-primary);
}
.msg-body :deep(p) { margin: 0.5em 0; }
.msg-body :deep(p:first-child) { margin-top: 0; }
.msg-body :deep(p:last-child) { margin-bottom: 0; }
.msg-body :deep(ul), .msg-body :deep(ol) { padding-left: 1.5em; margin: 0.5em 0; }
.msg-body :deep(li) { margin: 0.25em 0; }
.msg-body :deep(blockquote) {
  border-left: 3px solid var(--primary);
  margin: 0.5em 0;
  padding: 4px 12px;
  color: var(--text-secondary);
  background: var(--bg-subtle);
  border-radius: 0 6px 6px 0;
}
.msg-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 0.5em 0;
  font-size: 13px;
}
.msg-body :deep(th), .msg-body :deep(td) {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.msg-body :deep(th) {
  background: var(--bg-subtle);
  font-weight: 600;
}
.msg-body :deep(code:not(.hljs)) {
  background: var(--md-code-bg);
  padding: 1px 5px;
  border-radius: 5px;
  font-size: 13px;
  color: var(--md-code-color);
  font-family: var(--font-mono);
}
.msg-body :deep(a) {
  color: var(--primary);
  text-decoration: none;
}
.msg-body :deep(a:hover) {
  text-decoration: underline;
}
.msg-body :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 8px 0;
}

/* ── 代码块 ── */
.msg-body :deep(.cl-block) {
  margin: 8px 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
  background: #1e1e2e;
}
.msg-body :deep(.cl-header) {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 12px;
  background: #181825;
  border-bottom: 1px solid #313244;
}
.msg-body :deep(.cl-lang) {
  font-size: 11px;
  color: #a6adc8;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.msg-body :deep(.cl-count) {
  font-size: 10px;
  color: #585b70;
}
.msg-body :deep(.cl-pre) {
  margin: 0;
  padding: 12px 16px;
  overflow-x: auto;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
}
.msg-body :deep(.cl-line) {
  display: block;
  color: #cdd6f4;
}
.msg-body :deep(.cl-line::before) {
  content: attr(data-line);
  display: inline-block;
  width: 2em;
  margin-right: 1em;
  color: #585b70;
  text-align: right;
  user-select: none;
}

/* ── 消息底部统计条 ── */
.msg-footer {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--text-tertiary);
  padding-top: 6px;
  border-top: 1px solid var(--border-light);
  flex-wrap: wrap;
}
.user-footer {
  border-top-color: var(--border-light);
  justify-content: flex-end;
}
.user-footer .msg-stat { color: var(--text-tertiary); }
.msg-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.msg-time { opacity: 0.7; }

.cursor-blink {
  color: var(--primary);
  animation: blink 1s step-end infinite;
  font-size: 16px;
  font-weight: 300;
}
@keyframes blink { 50% { opacity: 0 } }

/* ── 思考中气泡 ── */
.thinking-dots { display: flex; gap: 5px; padding: 4px 0; }
.thinking-dots span {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--primary);
  animation: bounce 1.4s infinite;
}
.thinking-dots span:nth-child(2) { animation-delay: .2s; }
.thinking-dots span:nth-child(3) { animation-delay: .4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── 状态栏 ── */
.status-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 20px;
  font-size: 12px;
  color: var(--text-tertiary);
  border-top: 1px solid var(--border);
  background: var(--bg-subtle);
}

/* ── 输入区 ── */
.composer-area {
  padding: 12px 20px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0;
}
.composer-hero {
  /* 在对话容器内水平居中，放在下方合适位置 */
  position: absolute;
  left: 50%;
  bottom: 15%;
  transform: translateX(-50%);
  width: 100%;
  max-width: 680px;
  border-top: none;
  background: transparent;
  padding: 0 20px;
  animation: heroFadeIn 0.8s ease-out;
  z-index: 5;
}

.composer-shell {
  max-width: 720px;
  margin: 0 auto;
  border-radius: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  transition: border-color 0.2s, box-shadow 0.2s;
}
.composer-shell:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(79,110,247,0.08), 0 2px 12px rgba(0,0,0,0.06);
}
.composer-hero .composer-shell {
  background: var(--bg-card);
  border: 1px solid var(--border);
  box-shadow: 0 4px 24px rgba(79,110,247,0.10);
}
.composer-main {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  padding: 8px 8px 8px 16px;
}
.composer-input {
  flex: 1;
}
:deep(.composer-input .el-textarea__inner) {
  border: none !important;
  border-radius: 12px;
  padding: 8px 4px;
  font-size: 14px;
  background: transparent !important;
  box-shadow: none !important;
  resize: none;
}
:deep(.composer-input .el-textarea__inner:focus) {
  box-shadow: none !important;
}
.composer-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.send-btn {
  width: 36px;
  height: 36px;
  padding: 0 !important;
  border-radius: 50% !important;
  display: flex !important;
  align-items: center;
  justify-content: center;
  background: var(--accent-gradient) !important;
  color: var(--text-on-accent) !important;
  border: none !important;
  box-shadow: var(--accent-shadow);
  transition: all 0.15s !important;
}
.send-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.05);
}
.send-btn.is-disabled {
  opacity: 0.4 !important;
}
.stop-btn {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

/* ── 右侧面板 ── */
.context-panel {
  width: 260px;
  background: var(--bg-card);
  border-left: 1px solid var(--border);
  padding: 16px;
  display: flex; flex-direction: column; gap: 12px;
  overflow-y: auto; flex-shrink: 0;
}
.panel-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px;
  background: var(--bg-card);
}
.panel-card.session-info {
  background: var(--bg-subtle);
  border-color: var(--border);
}
.panel-card-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.context-stat {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 5px 0;
}
.ctx-label { color: var(--text-secondary); }
.ctx-value { font-weight: 500; color: var(--text-primary); }
.mode-badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; background: var(--bg-subtle); }
.mode-badge.expert { background: var(--tz-yellow-soft); color: var(--tz-yellow-ink); }
.context-action {
  padding: 8px 0;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}
.context-action:hover {
  color: var(--primary);
}
.context-empty { font-size: 12px; color: var(--text-tertiary); padding: 8px 0; }
.context-tool-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
  font-size: 12px;
}
.cti-name {
  color: var(--text-primary);
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cti-status { font-size: 11px; padding: 1px 6px; border-radius: 999px; }
.cti-status.running { background: var(--tz-blue-soft); color: var(--tz-blue-ink); animation: pulse 1.5s infinite; }
.cti-status.done { background: var(--tz-green-soft); color: var(--tz-green-ink); }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

/* ── 工具调用 ── */
.tool-call-wrapper { margin-bottom: 10px; }
.tool-calls-list { display: flex; flex-direction: column; }

/* ── 过渡动画 ── */
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.msg-enter-active {
  animation: msgSlideIn 0.3s ease-out;
}
.msg-leave-active {
  animation: msgSlideIn 0.2s ease-in reverse;
}

/* ── 暗色适配（Kitro dark：金 accent + 玻璃态） ── */
html.dark .dock-item.active { background: var(--accent-soft); }
html.dark .dock-item.active::before { background: var(--accent); }
html.dark .avi-ai { background: var(--tz-purple-soft); color: var(--tz-purple-ink); }
html.dark .avi-user { background: var(--bg-hover); color: var(--text-tertiary); }
html.dark .user-card { background: var(--bg-hover); }
html.dark .suggestion-pill:hover { background: var(--bg-hover); }
</style>

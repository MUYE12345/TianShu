<template>
  <el-drawer :model-value="modelValue" title="历史记录" size="320px" @update:model-value="v => emit('update:modelValue', v)" @open="load">
    <div v-loading="loading" class="chd-body">
      <div v-for="c in chats" :key="c.id" class="chd-item">
        <div class="chd-main" @click="emit('select', c.id)">
          <div class="chd-title">{{ c.title || '新对话' }}</div>
          <div class="chd-meta">{{ c.message_count }} 条 · {{ relativeTime(c.updated_at) }}</div>
        </div>
        <el-button text size="small" type="danger" @click.stop="remove(c.id)">✕</el-button>
      </div>
      <el-empty v-if="!loading && chats.length === 0" :image-size="50" description="暂无历史对话" />
    </div>
  </el-drawer>
</template>

<script setup>
import { ref, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  kid: { type: String, required: true },
})
const emit = defineEmits(['update:modelValue', 'select'])

const chats = ref([])
const loading = ref(false)

// PRD 时间规则：刚刚 / N分钟前 / N小时前 / 昨天 / M-D
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

async function load() {
  loading.value = true
  try {
    const { data } = await axios.get(`/api/knowledge/notebooks/${props.kid}/chats`)
    chats.value = data.items || []
  } catch {
    chats.value = []
  }
  loading.value = false
}

async function remove(id) {
  try {
    await axios.delete(`/api/knowledge/notebooks/${props.kid}/chats/${id}`)
    chats.value = chats.value.filter(c => c.id !== id)
  } catch { /* ignore */ }
}
</script>

<style scoped>
.chd-body { padding: 0 8px; }
.chd-item {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  transition: background 0.15s;
}
.chd-item:hover { background: var(--bg-subtle); }
.chd-main { flex: 1; min-width: 0; }
.chd-title { font-size: 13px; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chd-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
</style>

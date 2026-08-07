<template>
  <!-- inline 模式：直接渲染内容（嵌入对话列 tab）；否则弹窗 -->
  <div v-if="inline" class="src-preview-body">
    <div v-if="source && source.status === 'failed'" class="spd-error">
      <el-alert type="error" title="解析失败" :description="source.parse_error || '未知错误'" show-icon :closable="false" />
    </div>
    <div v-else-if="source && isFrameExt" class="spd-frame-wrap inline-frame">
      <iframe :src="previewUrl" class="spd-frame" />
    </div>
    <div v-else-if="source" class="spd-text-wrap inline-text" v-loading="textLoading">
      <pre class="spd-text">{{ textContent || '该格式暂不支持预览' }}</pre>
    </div>
    <div v-else class="spd-empty"><el-empty :image-size="40" description="未选择文件" /></div>
  </div>

  <el-dialog v-else :model-value="modelValue" :title="source?.filename || '文件预览'" width="720px" top="6vh"
    @update:model-value="v => emit('update:modelValue', v)">
    <div v-if="source && source.status === 'failed'" class="spd-error">
      <el-alert type="error" title="解析失败" :description="source.parse_error || '未知错误'" show-icon :closable="false" />
    </div>
    <div v-else-if="source && isFrameExt" class="spd-frame-wrap">
      <iframe :src="previewUrl" class="spd-frame" />
    </div>
    <div v-else-if="source" class="spd-text-wrap" v-loading="textLoading">
      <pre class="spd-text">{{ textContent || '该格式暂不支持预览' }}</pre>
    </div>
    <div v-else class="spd-empty"><el-empty :image-size="40" description="未选择文件" /></div>

    <template #footer>
      <a class="spd-dl" :href="downloadUrl" :download="isFrameExt ? undefined : ''" target="_blank" rel="noreferrer">
        <el-button type="primary" plain>下载原文</el-button>
      </a>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  inline: { type: Boolean, default: false },
  kid: { type: String, required: true },
  source: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const textContent = ref('')
const textLoading = ref(false)

const isFrameExt = computed(() => {
  const ext = (props.source?.ext || '').toLowerCase().replace('.', '')
  return ['pdf', 'html', 'htm'].includes(ext)
})

const previewUrl = computed(() =>
  props.source ? `/api/knowledge/notebooks/${props.kid}/sources/${props.source.id}/preview` : '')
const downloadUrl = computed(() =>
  props.source ? `/api/knowledge/notebooks/${props.kid}/sources/${props.source.id}/download` : '')

async function loadText() {
  if (!props.source || isFrameExt.value) return
  textLoading.value = true
  textContent.value = ''
  try {
    const res = await axios.get(previewUrl.value, { responseType: 'text' })
    textContent.value = typeof res.data === 'string' ? res.data : (res.data?.text || '')
  } catch {
    textContent.value = '预览加载失败'
  }
  textLoading.value = false
}

watch(() => [props.modelValue, props.inline, props.source?.id], ([visible, inline]) => {
  if (visible || inline) loadText()
}, { immediate: true })
</script>

<style scoped>
.src-preview-body { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.spd-frame-wrap { height: 60vh; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
.spd-frame-wrap.inline-frame { flex: 1; height: auto; min-height: 0; border: none; border-radius: 12px; }
.spd-frame { width: 100%; height: 100%; border: none; background: #fff; }
.spd-text-wrap { max-height: 60vh; overflow: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--bg-subtle); }
.spd-text-wrap.inline-text { flex: 1; max-height: none; min-height: 0; }
.spd-text { margin: 0; padding: 14px; white-space: pre-wrap; font-size: 13px; line-height: 1.7; color: var(--text-primary); font-family: var(--font-mono); }
.spd-error { padding: 12px 0; }
.spd-empty { padding: 40px 0; }
.spd-dl { display: inline-block; margin-right: 8px; }
</style>

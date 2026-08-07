<template>
  <!-- 添加来源（设计稿 img_10/11）：上传文件 / 粘贴文本 -->
  <el-dialog :model-value="modelValue" @update:model-value="close" title="添加来源" width="520px" :close-on-click-modal="false">
    <div class="add-tabs">
      <div class="add-tab" :class="{ active: tab === 'file' }" @click="tab = 'file'">上传文件</div>
      <div class="add-tab" :class="{ active: tab === 'text' }" @click="tab = 'text'">粘贴文本</div>
    </div>

    <!-- 上传文件 -->
    <div v-show="tab === 'file'">
      <div class="dropzone" :class="{ over: dragOver }" @click="pick" @dragover.prevent="dragOver = true"
           @dragleave="dragOver = false" @drop.prevent="onDrop">
        <div class="dz-icon">⬆</div>
        <div class="dz-main">点击选择或拖拽文件到这里</div>
        <div class="dz-sub">支持 pdf / doc / docx / md / xlsx / pptx / txt 等</div>
      </div>
      <input ref="fileInput" type="file" multiple style="display: none"
             accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.md,.txt,.csv,.json,.html" @change="onPick" />
      <div v-if="files.length" class="file-list">
        <div v-for="(f, i) in files" :key="i" class="file-row">
          <span class="file-name">{{ f.name }}</span>
          <span class="file-size">{{ formatSize(f.size) }}</span>
          <span class="file-x" @click="files.splice(i, 1)">✕</span>
        </div>
      </div>
    </div>

    <!-- 粘贴文本 -->
    <div v-show="tab === 'text'">
      <el-input v-model="textTitle" placeholder="标题（可选）" style="margin-bottom: 10px" />
      <el-input v-model="textContent" type="textarea" :rows="8" placeholder="粘贴任意文本内容，将作为一份来源参与问答与产出…" />
    </div>

    <template #footer>
      <button class="btn-ghost" @click="close(false)">取消</button>
      <button v-if="tab === 'file'" class="btn-primary" :disabled="!files.length || busy" @click="importFiles">
        {{ busy ? '导入中…' : `导入${files.length ? `（${files.length} 份）` : ''}` }}
      </button>
      <button v-else class="btn-primary" :disabled="!textContent.trim() || busy" @click="importText">
        {{ busy ? '导入中…' : '导入' }}
      </button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { formatSize } from './covers.js'

const props = defineProps({ modelValue: Boolean })
const emit = defineEmits(['update:modelValue', 'upload', 'text'])

const tab = ref('file')
const files = ref([])
const dragOver = ref(false)
const busy = ref(false)
const fileInput = ref(null)
const textTitle = ref('')
const textContent = ref('')

watch(() => props.modelValue, (v) => {
  if (v) { files.value = []; tab.value = 'file'; textTitle.value = ''; textContent.value = '' }
})

function close(v = false) { emit('update:modelValue', v) }
function pick() { fileInput.value?.click() }
function onPick(e) { files.value.push(...Array.from(e.target.files || [])); e.target.value = '' }
function onDrop(e) { dragOver.value = false; files.value.push(...Array.from(e.dataTransfer.files || [])) }

async function importFiles() {
  busy.value = true
  try {
    for (const f of files.value) await props.upload?.(f)
    ElMessage.success(`已导入 ${files.value.length} 份来源`)
    close(false)
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally { busy.value = false }
}

async function importText() {
  busy.value = true
  try {
    await props.text?.({ title: textTitle.value, content: textContent.value })
    ElMessage.success('文本来源已导入')
    close(false)
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally { busy.value = false }
}
</script>

<style scoped>
.add-tabs { display: flex; gap: 8px; margin-bottom: 14px; }
.add-tab {
  padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 600;
  cursor: pointer; background: var(--bg-hover); color: var(--text-tertiary); transition: all .15s;
}
.add-tab.active { background: var(--accent-soft); color: var(--text-primary); }

.dropzone {
  border: 1.5px dashed var(--border-input); border-radius: 16px;
  padding: 28px 16px; text-align: center; cursor: pointer; transition: all .2s;
  background: var(--bg-subtle);
}
.dropzone.over, .dropzone:hover { border-color: var(--border-focus); background: var(--bg-hover); }
.dz-icon { font-size: 20px; color: var(--text-tertiary); margin-bottom: 8px; }
.dz-main { font-size: 13px; font-weight: 600; color: var(--text-secondary); }
.dz-sub { font-size: 12px; color: var(--text-muted); margin-top: 6px; }

.file-list { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; max-height: 160px; overflow-y: auto; }
.file-row {
  display: flex; align-items: center; gap: 10px;
  border: 1px solid var(--border-input); border-radius: 10px; padding: 8px 12px;
  background: var(--bg-card);
}
.file-name { flex: 1; font-size: 12px; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.file-size { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }
.file-x { color: var(--text-muted); cursor: pointer; font-size: 12px; flex-shrink: 0; }
.file-x:hover { color: var(--danger); }
</style>

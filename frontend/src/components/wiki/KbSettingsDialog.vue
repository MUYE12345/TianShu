<template>
  <!-- 知识库设置（设计稿 img_06）：基础信息 / 成员设置 双 tab -->
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="知识库设置" width="520px" :close-on-click-modal="false">
    <div class="set-tabs">
      <div class="set-tab" :class="{ active: tab === 'basic' }" @click="tab = 'basic'">基础信息</div>
      <div class="set-tab" :class="{ active: tab === 'member' }" @click="tab = 'member'">成员设置</div>
    </div>

    <div v-show="tab === 'basic'" class="set-body">
      <div class="set-label">名称</div>
      <el-input v-model="form.title" maxlength="20" placeholder="知识库名称（20 字以内）" />
      <div class="set-label">简介</div>
      <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" placeholder="一句话简介（可选，500 字以内）" />
      <div class="set-label">封面</div>
      <div class="cover-grid">
        <div v-for="c in KB_COVERS" :key="c.id" class="cover-opt" :class="{ active: form.cover === c.id }"
             :title="c.label" @click="form.cover = c.id">
          <KbCover :cover="c.id" />
          <span v-if="form.cover === c.id" class="cover-check">✓</span>
        </div>
      </div>
      <div class="set-delete" @click="$emit('requestDelete')">删除知识库</div>
    </div>

    <div v-show="tab === 'member'" class="set-body">
      <div class="member-row">
        <span class="member-avatar">👤</span>
        <div class="member-info">
          <div class="member-name">我（创建者）</div>
          <div class="member-role">拥有者 · 可编辑</div>
        </div>
      </div>
      <div class="member-note">当前为单用户模式，共享成员管理将在多人协作版本提供。所有知识库默认进入「全部知识」供只读浏览。</div>
    </div>

    <template #footer>
      <button class="btn-ghost" @click="$emit('update:modelValue', false)">取消</button>
      <button class="btn-primary" @click="save">保存</button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'
import KbCover from './KbCover.vue'
import { KB_COVERS } from './covers.js'

const props = defineProps({ modelValue: Boolean, kb: Object })
const emit = defineEmits(['update:modelValue', 'save', 'requestDelete'])

const tab = ref('basic')
const form = ref({ title: '', description: '', cover: 'cover-1' })

watch(() => props.modelValue, (v) => {
  if (v && props.kb) {
    form.value = { title: props.kb.title || '', description: props.kb.description || '', cover: props.kb.cover || 'cover-1' }
    tab.value = 'basic'
  }
})

function save() {
  emit('save', { ...form.value })
}
</script>

<style scoped>
.set-tabs { display: flex; gap: 20px; border-bottom: 1px solid var(--border-light); margin-bottom: 16px; }
.set-tab { padding: 6px 2px 10px; font-size: 14px; cursor: pointer; color: var(--text-tertiary); border-bottom: 2px solid transparent; transition: all .15s; }
.set-tab.active { color: var(--text-primary); font-weight: 600; border-bottom-color: var(--accent); }
html.dark .set-tab.active { border-bottom-color: var(--accent); }

.set-body { min-height: 220px; }
.set-label { font-size: 12px; color: var(--text-tertiary); margin: 12px 0 6px; }
.cover-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.cover-opt { position: relative; height: 64px; border-radius: 12px; overflow: hidden; cursor: pointer; border: 2px solid transparent; transition: all .15s; }
.cover-opt:hover { transform: scale(1.03); }
.cover-opt.active { border-color: var(--accent); }
.cover-opt :deep(.kb-cover-emoji) { font-size: 24px; }
.cover-check { position: absolute; right: 6px; top: 6px; width: 18px; height: 18px; border-radius: 50%; background: var(--bg-card); color: var(--text-primary); font-size: 11px; display: grid; place-items: center; box-shadow: var(--shadow-soft); z-index: 2; }

.set-delete { margin-top: 20px; color: var(--danger); font-size: 13px; cursor: pointer; width: fit-content; }
.set-delete:hover { text-decoration: underline; }

.member-row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px; background: var(--bg-subtle); }
.member-avatar { width: 36px; height: 36px; border-radius: 10px; background: var(--bg-card); display: grid; place-items: center; box-shadow: var(--shadow-soft); }
.member-name { font-size: 13px; font-weight: 600; }
.member-role { font-size: 12px; color: var(--text-tertiary); }
.member-note { margin-top: 14px; font-size: 12px; color: var(--text-tertiary); line-height: 1.7; padding: 10px 12px; border-radius: 12px; background: var(--tz-blue-soft); color: var(--tz-blue-ink); }
</style>

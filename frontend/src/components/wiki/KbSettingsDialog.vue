<template>
  <!-- 知识库设置（设计稿 img_06）：基础信息 / 成员设置 双 tab -->
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             title="知识库设置" width="560px" :close-on-click-modal="false">
    <div class="set-tabs">
      <div class="set-tab" :class="{ active: tab === 'basic' }" @click="tab = 'basic'">基础信息</div>
      <div class="set-tab" :class="{ active: tab === 'member' }" @click="switchTab('member')">成员设置</div>
    </div>

    <div v-show="tab === 'basic'" class="set-body">
      <div class="set-label">名称</div>
      <el-input v-model="form.title" maxlength="20" placeholder="知识库名称（20 字以内）" :disabled="!canEdit" />
      <div class="set-label">简介</div>
      <el-input v-model="form.description" type="textarea" :rows="2" maxlength="500" placeholder="一句话简介（可选，500 字以内）" :disabled="!canEdit" />
      <div class="set-label">封面</div>
      <div class="cover-grid">
        <div v-for="c in KB_COVERS" :key="c.id" class="cover-opt" :class="{ active: form.cover === c.id }"
             :title="c.label" @click="canEdit && (form.cover = c.id)">
          <KbCover :cover="c.id" />
          <span v-if="form.cover === c.id" class="cover-check">✓</span>
        </div>
      </div>
      <div v-if="isAdmin" class="set-delete" @click="$emit('requestDelete')">删除知识库（仅管理员）</div>
    </div>

    <div v-show="tab === 'member'" class="set-body">
      <!-- 成员列表 -->
      <div class="member-row" v-for="m in members" :key="m.user_id">
        <span class="member-avatar">👤</span>
        <div class="member-info">
          <div class="member-name">
            {{ m.username || ('用户#' + m.user_id) }}
            <el-tag v-if="m.role === 'admin'" size="small" type="danger" effect="plain">管理员</el-tag>
            <el-tag v-else-if="m.role === 'editor'" size="small" type="warning" effect="plain">编辑</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">查看</el-tag>
          </div>
        </div>
        <div v-if="isAdmin && m.role !== 'admin'" class="member-ops">
          <el-select :model-value="m.role" size="small" style="width: 90px"
                     @change="(r) => changeRole(m, r)">
            <el-option label="编辑" value="editor" />
            <el-option label="查看" value="viewer" />
          </el-select>
          <el-button size="small" text type="danger" @click="removeMember(m)">移除</el-button>
        </div>
      </div>

      <!-- 管理员迁移(仅 admin, 且成员数 > 1) -->
      <div v-if="isAdmin && members.length > 1" class="member-transfer">
        <div class="set-label">转移管理员</div>
        <div class="transfer-row">
          <el-select v-model="transferTarget" size="small" style="flex:1" placeholder="选择新管理员（转移后你降为编辑）">
            <el-option v-for="m in members.filter(x => x.role !== 'admin')" :key="m.user_id"
                       :label="(m.username || ('用户#' + m.user_id))" :value="m.user_id" />
          </el-select>
          <el-button size="small" type="danger" :disabled="!transferTarget" @click="doTransfer">转移</el-button>
        </div>
      </div>

      <!-- 添加成员(仅 admin) -->
      <div v-if="isAdmin" class="member-add">
        <div class="set-label">添加成员</div>
        <div class="transfer-row">
          <el-input v-model.number="addUserId" size="small" placeholder="输入用户 ID" style="flex:1" type="number" />
          <el-select v-model="addRole" size="small" style="width: 90px">
            <el-option label="编辑" value="editor" />
            <el-option label="查看" value="viewer" />
          </el-select>
          <el-button size="small" type="primary" :disabled="!addUserId" @click="addMember">添加</el-button>
        </div>
      </div>

      <div v-if="!isAdmin" class="member-note">你以「{{ myRoleLabel }}」身份访问该知识库。</div>
    </div>

    <template #footer>
      <button class="btn-ghost" @click="$emit('update:modelValue', false)">取消</button>
      <button v-if="tab === 'basic' && canEdit" class="btn-primary" @click="save">保存</button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import KbCover from './KbCover.vue'
import { KB_COVERS } from './covers.js'

const props = defineProps({ modelValue: Boolean, kb: Object })
const emit = defineEmits(['update:modelValue', 'save', 'requestDelete'])

const tab = ref('basic')
const form = ref({ title: '', description: '', cover: 'cover-1' })
const members = ref([])
const transferTarget = ref(null)
const addUserId = ref(null)
const addRole = ref('viewer')

const myRole = computed(() => props.kb?.my_role || 'viewer')
const isAdmin = computed(() => myRole.value === 'admin')
const canEdit = computed(() => ['admin', 'editor'].includes(myRole.value))
const myRoleLabel = computed(() => ({ admin: '管理员', editor: '编辑', viewer: '查看' }[myRole.value] || '查看'))

async function loadMembers() {
  if (!props.kb) return
  try {
    const { data } = await axios.get(`/api/knowledge/notebooks/${props.kb.id}/members`)
    members.value = data.items || []
  } catch { members.value = [] }
}

watch(() => props.modelValue, (v) => {
  if (v && props.kb) {
    form.value = { title: props.kb.title || '', description: props.kb.description || '', cover: props.kb.cover || 'cover-1' }
    tab.value = 'basic'
    transferTarget.value = null
    addUserId.value = null
    loadMembers()
  }
})

function switchTab(t) {
  tab.value = t
  if (t === 'member') loadMembers()
}

function save() {
  emit('save', { ...form.value })
}

async function changeRole(m, role) {
  try {
    await axios.put(`/api/knowledge/notebooks/${props.kb.id}/members/${m.user_id}`, { role })
    ElMessage.success('角色已更新')
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '更新失败')
  }
}

async function removeMember(m) {
  try {
    await axios.delete(`/api/knowledge/notebooks/${props.kb.id}/members/${m.user_id}`)
    ElMessage.success('已移除')
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '移除失败')
  }
}

async function addMember() {
  try {
    await axios.post(`/api/knowledge/notebooks/${props.kb.id}/members`, {
      user_id: addUserId.value, role: addRole.value,
    })
    ElMessage.success('已添加')
    addUserId.value = null
    await loadMembers()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '添加失败')
  }
}

async function doTransfer() {
  if (!transferTarget.value) return
  try {
    await axios.post(`/api/knowledge/notebooks/${props.kb.id}/transfer`, { user_id: transferTarget.value })
    ElMessage.success('管理员已转移，你已降为编辑')
    emit('update:modelValue', false)
    emit('transfered')
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '转移失败')
  }
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

.member-row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 12px; background: var(--bg-subtle); margin-bottom: 8px; }
.member-avatar { width: 36px; height: 36px; border-radius: 10px; background: var(--bg-card); display: grid; place-items: center; box-shadow: var(--shadow-soft); }
.member-info { flex: 1; min-width: 0; }
.member-name { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; }
.member-ops { display: flex; align-items: center; gap: 4px; }
.member-note { margin-top: 14px; font-size: 12px; color: var(--text-tertiary); line-height: 1.7; padding: 10px 12px; border-radius: 12px; background: var(--tz-blue-soft); color: var(--tz-blue-ink); }
.member-transfer, .member-add { margin-top: 16px; }
.transfer-row { display: flex; gap: 8px; align-items: center; }
</style>

<template>
  <!-- 删除知识库（设计稿 img_07）：输入名称完全一致才可确认 -->
  <el-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)"
             :title="`删除知识库「${kb?.title || ''}」`" width="440px" :close-on-click-modal="false">
    <div class="del-warn">
      删除后，该知识库上传的文件、对话记录与全部产出将同步从「全部知识」中清除，且无法恢复。
    </div>
    <div class="del-tip">请输入知识库名称 <b>{{ kb?.title }}</b> 以确认删除：</div>
    <el-input v-model="input" :placeholder="kb?.title || ''" />
    <template #footer>
      <button class="btn-ghost" @click="$emit('update:modelValue', false)">取消</button>
      <button class="btn-danger" :disabled="input !== (kb?.title || '')" @click="confirm">确认删除</button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({ modelValue: Boolean, kb: Object })
const emit = defineEmits(['update:modelValue', 'confirm'])
const input = ref('')

watch(() => props.modelValue, (v) => { if (v) input.value = '' })

function confirm() {
  emit('confirm')
}
</script>

<style scoped>
.del-warn {
  font-size: 13px; color: var(--danger); line-height: 1.7;
  background: var(--danger-soft); border-radius: 12px; padding: 10px 14px;
}
.del-tip { font-size: 12px; color: var(--text-secondary); margin: 14px 0 8px; }
.del-tip b { color: var(--text-primary); }
</style>

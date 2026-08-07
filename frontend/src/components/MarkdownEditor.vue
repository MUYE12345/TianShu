<template>
  <div class="markdown-editor">
    <div class="editor-pane">
      <div class="pane-header">编辑</div>
      <textarea
        class="editor-textarea"
        :value="modelValue"
        @input="onInput"
        placeholder="请输入 Markdown 内容..."
      ></textarea>
    </div>
    <div class="preview-pane">
      <div class="pane-header">预览</div>
      <div class="preview-content" v-html="renderedHtml"></div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import MarkdownIt from 'markdown-it'

const props = defineProps({
  modelValue: { type: String, default: '' }
})
const emit = defineEmits(['update:modelValue'])

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
})

const renderedHtml = computed(() => {
  if (!props.modelValue) return '<p style="color:#999">暂无内容</p>'
  return md.render(props.modelValue)
})

const onInput = (e) => {
  emit('update:modelValue', e.target.value)
}
</script>

<style scoped>
.markdown-editor {
  display: flex;
  height: 450px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.editor-pane,
.preview-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.editor-pane {
  border-right: 1px solid #dcdfe6;
}

.pane-header {
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 600;
  background: #f5f7fa;
  border-bottom: 1px solid #dcdfe6;
  color: #606266;
}

.editor-textarea {
  flex: 1;
  width: 100%;
  padding: 12px;
  border: none;
  outline: none;
  resize: none;
  font-family: 'Courier New', Courier, monospace;
  font-size: 14px;
  line-height: 1.6;
  color: #303133;
  background: #fff;
  box-sizing: border-box;
}

.editor-textarea::placeholder {
  color: #c0c4cc;
}

.preview-content {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.8;
  color: #303133;
  background: #fff;
  box-sizing: border-box;
}

.preview-content :deep(h1),
.preview-content :deep(h2),
.preview-content :deep(h3),
.preview-content :deep(h4) {
  margin-top: 16px;
  margin-bottom: 8px;
  font-weight: 600;
  color: #303133;
}

.preview-content :deep(p) {
  margin-bottom: 8px;
}

.preview-content :deep(code) {
  padding: 2px 6px;
  background: #f5f7fa;
  border-radius: 3px;
  font-family: 'Courier New', Courier, monospace;
  font-size: 13px;
  color: #d63200;
}

.preview-content :deep(pre) {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  overflow-x: auto;
}

.preview-content :deep(pre code) {
  padding: 0;
  background: transparent;
  color: inherit;
}

.preview-content :deep(blockquote) {
  margin: 8px 0;
  padding: 8px 16px;
  border-left: 4px solid #409eff;
  background: #f5f7fa;
  color: #606266;
}

.preview-content :deep(ul),
.preview-content :deep(ol) {
  padding-left: 24px;
  margin-bottom: 8px;
}

.preview-content :deep(a) {
  color: #409eff;
  text-decoration: none;
}

.preview-content :deep(a:hover) {
  text-decoration: underline;
}

.preview-content :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin-bottom: 8px;
}

.preview-content :deep(th),
.preview-content :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 12px;
  text-align: left;
}

.preview-content :deep(th) {
  background: #f5f7fa;
  font-weight: 600;
}

.preview-content :deep(img) {
  max-width: 100%;
  border-radius: 4px;
}

.preview-content :deep(hr) {
  margin: 16px 0;
  border: none;
  border-top: 1px solid #dcdfe6;
}
</style>

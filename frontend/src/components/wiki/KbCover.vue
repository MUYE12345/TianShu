<template>
  <!-- 插画封面：cover-1..6；旧数据色值兜底为纯色背景 + emoji -->
  <div class="kb-cover" :class="isPreset ? preset.id : ''" :style="!isPreset ? { background: cover } : null">
    <span class="kb-cover-deco deco-1"></span>
    <span class="kb-cover-deco deco-2"></span>
    <span class="kb-cover-emoji">{{ isPreset ? preset.emoji : '📚' }}</span>
  </div>
</template>

<script>
export default { name: 'KbCover' }
</script>

<script setup>
import { computed } from 'vue'
import { KB_COVERS } from './covers.js'

const props = defineProps({ cover: { type: String, default: 'cover-1' } })

const preset = computed(() => KB_COVERS.find(c => c.id === props.cover) || KB_COVERS[0])
const isPreset = computed(() => KB_COVERS.some(c => c.id === props.cover))
</script>

<style scoped>
.kb-cover {
  position: relative; width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
  overflow: hidden;
}
.kb-cover-emoji { font-size: 40px; position: relative; z-index: 1; filter: saturate(1.1); }
.kb-cover-deco { position: absolute; border-radius: 50%; opacity: .5; }
.deco-1 { width: 90px; height: 90px; right: -24px; top: -30px; background: rgba(255, 255, 255, .55); }
.deco-2 { width: 56px; height: 56px; left: -14px; bottom: -18px; background: rgba(255, 255, 255, .4); }

/* 六款 pastel 插画底 */
.cover-1 { background: linear-gradient(135deg, #d8f0db, #bfe6c8); }
.cover-2 { background: linear-gradient(135deg, #faecc9, #f6dfae); }
.cover-3 { background: linear-gradient(135deg, #e0e8f4, #cfdcee); }
.cover-4 { background: linear-gradient(135deg, #fce3e8, #f8d3dc); }
.cover-5 { background: linear-gradient(135deg, #ece4f5, #ded0ee); }
.cover-6 { background: linear-gradient(135deg, #ffedd5, #fbdfc0); }
</style>

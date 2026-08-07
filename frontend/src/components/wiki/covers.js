// 知识库插画封面预设（设计稿「选择封面」6 款）
export const KB_COVERS = [
  { id: 'cover-1', emoji: '🧑💻', label: '伏案创作' },
  { id: 'cover-2', emoji: '📈', label: '竞品分析' },
  { id: 'cover-3', emoji: '🤖', label: '智能体' },
  { id: 'cover-4', emoji: '☕', label: '闲暇阅读' },
  { id: 'cover-5', emoji: '🚀', label: '启航' },
  { id: 'cover-6', emoji: '📚', label: '书海' },
]

export function coverPreset(id) {
  return KB_COVERS.find(c => c.id === id) || null
}

// 文件类型 → 图标渐变类 + 显示文字（Kitro 文件图标体系）
export function fileTypeInfo(ext) {
  const e = (ext || '').toLowerCase().replace('.', '')
  if (['html', 'htm'].includes(e)) return { cls: 'ft-html', label: 'HTML' }
  if (['doc', 'docx'].includes(e)) return { cls: 'ft-doc', label: 'DOC' }
  if (['xls', 'xlsx', 'csv'].includes(e)) return { cls: 'ft-xls', label: 'XLS' }
  if (['md', 'markdown', 'txt'].includes(e)) return { cls: 'ft-md', label: 'MD' }
  if (e === 'pdf') return { cls: 'ft-pdf', label: 'PDF' }
  if (['ppt', 'pptx'].includes(e)) return { cls: 'ft-ppt', label: 'PPT' }
  return { cls: 'ft-file', label: (e || 'FILE').toUpperCase().slice(0, 4) }
}

// 文件大小友好显示
export function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

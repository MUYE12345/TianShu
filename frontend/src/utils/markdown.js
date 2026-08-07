/**
 * Markdown 渲染工具
 * 使用 markdown-it 将 Markdown 文本转为 HTML
 */
import MarkdownIt from 'markdown-it'

const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true,
  breaks: false,
})

// 代码高亮扩展
md.renderer.rules.fence = (tokens, idx) => {
  const token = tokens[idx]
  const lang = token.info.trim()
  const code = token.content
  return `<pre class="code-block"><code class="language-${lang || ''}">${escapeHtml(code)}</code></pre>`
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

/**
 * 将 Markdown 文本渲染为 HTML
 */
export function markdownToHtml(text) {
  if (!text) return ''
  return md.render(text)
}

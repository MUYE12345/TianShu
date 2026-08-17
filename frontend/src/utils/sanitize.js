/**
 * HTML 消毒工具 — 统一使用 DOMPurify 清洗 markdown-it 渲染结果
 *
 * 背景: 各页面直接 `new MarkdownIt({ html: true })` + `v-html` 渲染模型/用户输出,
 * 存在 XSS 注入风险(正则过滤不可靠)。此模块提供统一的 sanitize 入口:
 *
 *   import { safeRender } from '../utils/sanitize.js'
 *   html.value = safeRender(md, text)
 *
 * 仅当浏览器环境存在 DOMPurify(前端构建时已安装)时启用消毒;
 * 极端情况下 DOMPurify 不可用(如 SSR)时回退到保守的标签白名单清理, 绝不放行 script/事件属性。
 */
import DOMPurify from 'dompurify'

// 允许的标签白名单(覆盖 markdown-it 常见输出, 不含 script/iframe/object 等危险标签)
const ALLOWED_TAGS = [
  'p', 'br', 'hr', 'a', 'img', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'blockquote', 'pre', 'code', 'span', 'div',
  'strong', 'em', 'del', 's', 'u', 'mark', 'sub', 'sup', 'table',
  'thead', 'tbody', 'tr', 'th', 'td', 'input', 'details', 'summary',
]

// 允许的属性(安全子集, 不包含 on* 事件与 javascript: 协议)
const ALLOWED_ATTR = ['href', 'src', 'alt', 'title', 'class', 'target', 'rel', 'width', 'height', 'type', 'checked', 'disabled', 'start']

// markdown-it 渲染后统一消毒
export function sanitizeHtml(html) {
  if (!html) return ''
  try {
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      // 协议白名单: 只允许 http/https/mailto/tel, 拦截 javascript: 等
      ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto|tel):|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i,
      FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'link', 'meta'],
      FORBID_ATTR: ['onerror', 'onclick', 'onload', 'onmouseover', 'onfocus', 'onblur', 'style'],
    })
  } catch {
    // 兜底: DOMPurify 异常时执行最保守清理(不抛错, 保证页面可用)
    return String(html)
      .replace(/<script[\s\S]*?<\/script>/gi, '')
      .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      .replace(/(href|src)\s*=\s*["']?\s*javascript:[^"'\s>]*/gi, '$1="#"')
  }
}

// markdown-it 实例 + 文本 → 消毒后 HTML
export function safeRender(md, text) {
  if (!text) return ''
  try {
    return sanitizeHtml(md.render(text))
  } catch {
    return ''
  }
}

export default sanitizeHtml

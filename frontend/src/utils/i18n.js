/**
 * i18n Internationalization Utility
 *
 * Simple lightweight translation engine with auto browser language detection.
 * Supports Chinese (zh) and English (en).
 */

import zh from '../locales/zh.json'
import en from '../locales/en.json'

const dictionaries = { zh, en }

const FALLBACK_LOCALE = 'zh'
const STORAGE_KEY = 'app_locale'

let currentLocale = FALLBACK_LOCALE

/**
 * Detect the user's preferred language from the browser.
 * Returns 'zh' for any Chinese variant (zh-CN, zh-TW, etc.), otherwise 'en'.
 */
function detectBrowserLanguage() {
  if (typeof navigator === 'undefined') return FALLBACK_LOCALE

  const lang = navigator.language || navigator.userLanguage || ''
  if (lang.startsWith('zh')) return 'zh'
  return 'en'
}

/**
 * Set the active locale.
 * Persists the choice to localStorage so it survives page reloads.
 * @param {'zh'|'en'} lang
 */
export function setLocale(lang) {
  if (!dictionaries[lang]) {
    console.warn(`[i18n] Unsupported locale "${lang}", falling back to "${FALLBACK_LOCALE}"`)
    currentLocale = FALLBACK_LOCALE
  } else {
    currentLocale = lang
  }
  try {
    localStorage.setItem(STORAGE_KEY, currentLocale)
  } catch {
    // localStorage may be unavailable (private browsing, SSR, etc.)
  }
}

/**
 * Translate a key to the current locale.
 *
 * @param {string} key - Dot-notation key (e.g. "nav.home", "action.save")
 * @param {object} [params] - Optional interpolation values. Use {{paramName}} in translations.
 * @returns {string} Translated string, or the key itself if not found.
 *
 * @example
 * t('nav.home')              // "首页" or "Home"
 * t('greeting', { name: 'Alice' }) // looks up "greeting" key with {{name}} replaced
 */
export function t(key, params) {
  const dict = dictionaries[currentLocale]
  if (!dict) return key

  let value = dict[key]
  if (value === undefined || value === null) {
    // Fallback to English if key missing in current locale
    const fallbackDict = dictionaries.en
    value = fallbackDict?.[key]
  }
  if (value === undefined || value === null) {
    console.warn(`[i18n] Missing translation key: "${key}"`)
    return key
  }

  // Simple {{param}} interpolation
  if (params && typeof value === 'string') {
    return value.replace(/\{\{(\w+)\}\}/g, (_, name) => {
      return params[name] !== undefined ? String(params[name]) : `{{${name}}}`
    })
  }

  return value
}

/**
 * Get the current active locale code.
 * @returns {'zh'|'en'}
 */
export function getLocale() {
  return currentLocale
}

// ---- auto-initialization ----

;(function init() {
  let detected
  try {
    detected = localStorage.getItem(STORAGE_KEY)
  } catch {
    detected = null
  }

  if (detected && dictionaries[detected]) {
    currentLocale = detected
  } else {
    currentLocale = detectBrowserLanguage()
  }
})()

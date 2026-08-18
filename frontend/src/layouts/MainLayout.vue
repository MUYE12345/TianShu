<template>
  <div class="app-shell">
    <!-- ===== 侧边栏（Kitro：透明坐在渐变画布上） ===== -->
    <aside class="app-sidebar" :class="{ collapsed: isCollapse }">
      <div class="sidebar-head">
        <div class="logo-mark">✦</div>
        <span v-show="!isCollapse" class="logo-text">天枢</span>
      </div>

      <nav class="sidebar-nav">
        <div v-for="group in menuGroups" :key="group.label">
          <div class="nav-group" @click="toggleGroup(group.label)">
            <span v-show="!isCollapse" class="nav-group-arrow">{{ expanded[group.label] ? '▾' : '▸' }}</span>
            <span v-show="!isCollapse" class="nav-group-label">{{ group.label }}</span>
          </div>
          <div v-show="expanded[group.label]">
            <div v-for="item in group.items" :key="item.path"
                 class="nav-item" :class="{ active: route.path.startsWith(item.path) }"
                 @click="item.click ? item.click() : $router.push(item.path)">
              <span class="nav-icon" v-html="item.icon"></span>
              <span v-show="!isCollapse" class="nav-label">{{ item.label }}</span>
            </div>
          </div>
        </div>
      </nav>

      <div class="sidebar-foot">
        <div class="nav-item" @click="isCollapse = !isCollapse">
          <span class="nav-icon">{{ isCollapse ? '▸' : '◂' }}</span>
          <span v-show="!isCollapse" class="nav-label">收起</span>
        </div>
      </div>
    </aside>

    <!-- ===== 主区（Kitro 悬浮大圆角卡片） ===== -->
    <div class="app-main">
      <header class="app-topbar">
        <div class="topbar-left">
          <span class="topbar-title">{{ route.meta?.title || '天枢' }}</span>
        </div>
        <div class="topbar-right">
          <button class="tb-btn" @click="toggleDark">{{ isDark ? '☀️' : '🌙' }}</button>
          <button class="tb-btn" @click="refreshData">🔄</button>
          <div class="tb-avatar">👤</div>
        </div>
      </header>

      <main class="app-content">
        <router-view v-slot="{ Component }">
          <KeepAlive include="ChatPage,AgentOrchestration">
            <component :is="Component" />
          </KeepAlive>
        </router-view>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const isCollapse = ref(false)
const isDark = ref(document.documentElement.classList.contains('dark'))

const toggleDark = () => {
  isDark.value = !isDark.value
  document.documentElement.classList.toggle('dark', isDark.value)
  localStorage.setItem('theme', isDark.value ? 'dark' : 'light')
}
const refreshData = () => window.location.reload()

const expanded = reactive({
  '常用': true,
  '智能体': false,
  '扩展': false,
  '系统': false,
})

function toggleGroup(label) {
  expanded[label] = !expanded[label]
}

const menuGroups = [
  {
    label: '常用',
    items: [
      { path: '/chat', icon: '💬', label: 'AI 问答' },
      { path: '/daily-news', icon: '📰', label: '每日新闻' },
      { path: '/current-news', icon: '📡', label: '时事新闻' },
      { path: '/paper', icon: '📄', label: '论文解析' },
      { path: '/wiki', icon: '📝', label: '知识库' },
      { path: '/notes', icon: '📒', label: 'Wiki 笔记' },
      { path: '/plan', icon: '⏰', label: '定时任务' },
    ],
  },
  {
    label: '智能体',
    items: [
      { path: '/agent', icon: '🤖', label: '智能体管理' },
      { path: '/agent-orchestration', icon: '🔀', label: '智能体编排' },
    ],
  },
  {
    label: '扩展',
    items: [
      { path: '/tools', icon: '🛠', label: '工具市场' },
      { path: '/mcp-market', icon: '🔗', label: 'MCP 市场' },
      { path: '/skills-market', icon: '🧩', label: '技能市场' },
    ],
  },
  {
    label: '系统',
    items: [
      { path: '/settings/model', icon: '⚙', label: '设置' },
      { path: '/settings/harness', icon: '🛡', label: '安全围栏' },
    ],
  },
]
</script>

<style scoped>
/* 清新现代骨架：冷调渐变画布上 8px 留白，磨砂玻璃侧栏 + 悬浮主区 */
.app-shell {
  height: 100vh; display: flex; gap: 0;
  background: transparent;
  padding: 8px 8px 8px 0;
}

/* 侧边栏：磨砂玻璃白卡 */
.app-sidebar {
  width: 216px; background: var(--sidebar-bg);
  -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px);
  border: 1px solid var(--border-light); border-radius: 18px;
  display: flex; flex-direction: column;
  transition: width .36s cubic-bezier(0.22, 1, 0.36, 1);
  flex-shrink: 0; overflow: hidden;
  padding: 8px 10px;
  box-shadow: var(--shadow-soft);
}
.app-sidebar.collapsed { width: 64px; }

.sidebar-head {
  display: flex; align-items: center; gap: 10px; padding: 10px 10px 14px;
  flex-shrink: 0;
}
.logo-mark {
  width: 40px; height: 40px; border-radius: 12px;
  display: grid; place-items: center; font-size: 19px; color: #fff;
  background: linear-gradient(135deg, #4f8ef7 0%, #7c5cff 100%);
  box-shadow: 0 8px 18px -6px rgba(79, 142, 247, 0.55);
}
html.dark .logo-mark {
  background: linear-gradient(135deg, #5f8dfc 0%, #8f6bff 100%);
}
.logo-text {
  font-size: 17px; font-weight: 700; letter-spacing: .05em;
  background: linear-gradient(135deg, #4f8ef7 0%, #7c5cff 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text; white-space: nowrap; font-family: var(--font-display);
}
html.dark .logo-text {
  background: linear-gradient(135deg, #7aa8ff 0%, #a78bfa 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  background-clip: text;
}

.sidebar-nav { flex: 1; overflow-y: auto; padding: 0 4px; }

.nav-group {
  display: flex; align-items: center; gap: 4px;
  padding: 12px 10px 5px; cursor: pointer;
  color: var(--text-muted); font-size: 10px; font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase;
}
.nav-group:hover { color: var(--text-tertiary); }
.nav-group-arrow { font-size: 8px; width: 12px; }
.nav-group-label { flex: 1; }

.nav-item {
  display: flex; align-items: center; gap: 10px;
  height: 40px; padding: 0 10px; border-radius: 12px; cursor: pointer;
  transition: background .15s, color .15s, box-shadow .15s;
  color: var(--text-tertiary);
  margin-bottom: 2px; font-size: 13px; font-weight: 500;
}
.nav-item:hover { background: var(--sidebar-hover); color: var(--text-primary); }
.nav-item.active {
  background: var(--sidebar-active-bg);
  color: var(--sidebar-active); font-weight: 600;
}
.app-sidebar.collapsed .nav-item.active {
  background: var(--bg-card); color: var(--sidebar-active);
  box-shadow: 0 6px 14px -6px rgba(79, 142, 247, 0.35), inset 0 0 0 1px rgba(79, 142, 247, 0.18);
}
.nav-icon { font-size: 15px; width: 20px; text-align: center; flex-shrink: 0; line-height: 1; }
.nav-label { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.sidebar-foot { padding: 4px 4px 0; }

/* 主区：大圆角卡(半透明底; 不用 backdrop-filter, 它会破坏 Chromium 的 HTML5 拖放命中) */
.app-main {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
  margin-left: 8px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 18px;
  box-shadow: var(--shadow-card);
  border: 1px solid var(--border-light);
  overflow: hidden;
}
html.dark .app-main { background: rgba(18, 22, 42, 0.94); }

.app-topbar {
  height: 52px; display: flex; align-items: center;
  justify-content: space-between; padding: 0 20px;
  flex-shrink: 0; background: transparent;
  border-bottom: 1px solid var(--border-light);
}
.topbar-left { display: flex; align-items: center; gap: 12px; }
.topbar-title { font-size: 14px; font-weight: 700; letter-spacing: -0.01em; }
.topbar-right { display: flex; align-items: center; gap: 4px; }
.tb-btn {
  width: 32px; height: 32px; border-radius: 10px; border: none;
  background: transparent; cursor: pointer; font-size: 14px;
  display: grid; place-items: center; transition: background .15s;
}
.tb-btn:hover { background: var(--bg-hover); }
.tb-avatar {
  width: 30px; height: 30px; border-radius: 10px;
  display: grid; place-items: center; cursor: pointer;
  background: var(--accent-soft); font-size: 14px; margin-left: 4px;
}
.app-content { flex: 1; overflow: auto; padding: 20px; background: transparent; }
</style>

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    redirect: '/chat',
    children: [
      { path: 'daily-news', name: 'DailyNews', component: () => import('../views/news/DailyNews.vue'),
        meta: { title: '每日新闻', icon: 'Reading', requiresAuth: true } },
      { path: 'daily-news/:id', name: 'DailyNewsDetail', component: () => import('../views/news/NewsDetail.vue'),
        meta: { requiresAuth: true } },
      { path: 'current-news', name: 'CurrentNews', component: () => import('../views/news/CurrentNews.vue'),
        meta: { title: '时事新闻', icon: 'Clock', requiresAuth: true } },
      { path: 'paper', name: 'Paper', component: () => import('../views/paper/PaperPage.vue'),
        meta: { title: '论文解析', icon: 'Document', requiresAuth: true } },
      { path: 'paper/:id', name: 'PaperDetail', component: () => import('../views/paper/PaperDetail.vue'),
        meta: { requiresAuth: true } },
      { path: 'wiki', name: 'Wiki', component: () => import('../views/wiki/WikiPage.vue'),
        meta: { title: '知识库', icon: 'Notebook', requiresAuth: true } },
      { path: 'wiki/:id', name: 'WikiDetail', component: () => import('../views/wiki/WikiDetail.vue'),
        meta: { requiresAuth: true } },
      { path: 'notes', name: 'Notes', component: () => import('../views/wiki/NotesPage.vue'),
        meta: { title: 'Wiki 笔记', icon: 'Notebook', requiresAuth: true } },
      { path: 'chat', name: 'Chat', component: () => import('../views/chat/ChatPage.vue'),
        meta: { title: '问答', icon: 'ChatDotSquare', requiresAuth: true } },
      { path: 'knowledge', redirect: '/wiki',
        meta: { title: '知识库', requiresAuth: true } },
      { path: 'chat/:sessionId', name: 'ChatSession', component: () => import('../views/chat/ChatPage.vue'),
        meta: { requiresAuth: true } },
      { path: 'plan', name: 'DailyPlan', component: () => import('../views/plan/DailyPlan.vue'),
        meta: { title: '定时任务', icon: 'Timer', requiresAuth: true } },
      { path: 'agent', name: 'AgentManage', component: () => import('../views/agent/AgentManage.vue'),
        meta: { title: '智能体管理', icon: 'Robot', requiresAuth: true } },
      { path: 'agent-orchestration', name: 'AgentOrchestration', component: () => import('../views/agent/AgentOrchestration.vue'),
        meta: { title: '智能体编排', icon: 'SetUp', requiresAuth: true } },
      { path: 'tools', name: 'ToolMarket', component: () => import('../components/MarketWrapper.vue'),
        meta: { title: '工具市场', requiresAuth: true } },
      { path: 'mcp-market', name: 'McpMarket', component: () => import('../components/MarketWrapper.vue'),
        meta: { title: 'MCP市场', requiresAuth: true } },
      { path: 'skills-market', name: 'SkillMarket', component: () => import('../components/MarketWrapper.vue'),
        meta: { title: '技能市场', requiresAuth: true } },
      {
        path: 'settings', redirect: '/settings/model',
        meta: { title: '设置', icon: 'Setting', requiresAuth: true }
      },
      { path: 'settings/model', name: 'ModelSettings', component: () => import('../views/settings/ModelSettings.vue'),
        meta: { title: '模型配置', requiresAuth: true } },
      { path: 'settings/push', name: 'PushSettings', component: () => import('../views/settings/PushSettings.vue'),
        meta: { title: '推送配置', requiresAuth: true } },
      { path: 'settings/avatar', name: 'AvatarSettings', component: () => import('../views/settings/AvatarSettings.vue'),
        meta: { title: '桌宠配置', requiresAuth: true } },
      { path: 'settings/mcp', name: 'MCPSettings', component: () => import('../views/settings/MCPSettings.vue'),
        meta: { title: 'MCP工具', requiresAuth: true } },
      { path: 'settings/skills', name: 'SkillSettings', component: () => import('../views/settings/SkillSettings.vue'),
        meta: { title: 'SKILL管理', requiresAuth: true } },
      { path: 'settings/profile', name: 'Profile', component: () => import('../views/settings/Profile.vue'),
        meta: { title: '个人中心', icon: 'User', requiresAuth: true } },
      { path: 'settings/logs', name: 'LogViewer', component: () => import('../views/settings/LogViewer.vue'),
        meta: { title: '日志查看', icon: 'List', requiresAuth: true } },
      { path: 'settings/harness', name: 'HarnessSettings', component: () => import('../views/settings/HarnessSettings.vue'),
        meta: { title: '安全围栏', icon: 'Lock', requiresAuth: true } },
    ]
  },
  { path: '/login', name: 'Login', component: () => import('../views/Login.vue') },
]
const router = createRouter({
  history: createWebHistory(),
  routes,
  // 路由切换时回到顶部，避免从详情页返回列表后停留在原滚动位置造成"卡住"的错觉
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) return savedPosition
    return { top: 0 }
  },
})

// 路由导航守卫：未登录访问需鉴权的页面时自动跳转到登录页
router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  if (to.meta.requiresAuth && !token) {
    return next('/login')
  }
  // 已登录时访问登录页，直接跳回首页
  if (to.path === '/login' && token) {
    return next('/')
  }
  next()
})

export default router

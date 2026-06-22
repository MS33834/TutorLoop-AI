<script setup>
import { onMounted } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useUserStore } from './stores/user.js'
import ErrorBoundary from './components/ErrorBoundary.vue'

const router = useRouter()
const userStore = useUserStore()

onMounted(() => {
  userStore.fetchProfile()
})

function logout() {
  userStore.clearAuth()
  router.push('/')
}
</script>

<template>
  <a href="#main-content" class="skip-link">跳转到主要内容</a>
  <div class="app">
    <header class="header">
      <RouterLink to="/" class="brand" aria-label="TutorLoop AI 首页">
        <span class="brand-logo" aria-hidden="true">TL</span>
        <span class="brand-name">TutorLoop AI</span>
      </RouterLink>
      <nav class="nav" aria-label="主导航">
        <RouterLink to="/" class="nav-link">首页</RouterLink>
        <RouterLink v-if="userStore.isLoggedIn" to="/upload" class="nav-link">上传课程</RouterLink>
        <RouterLink v-if="userStore.isLoggedIn" to="/dashboard" class="nav-link">房间管理</RouterLink>
        <a
          href="https://github.com/MS33834/TutorLoop-AI"
          target="_blank"
          rel="noopener noreferrer"
          class="nav-link"
          aria-label="在 GitHub 上查看 TutorLoop AI 源码（新标签页打开）"
        >GitHub</a>
        <template v-if="userStore.isLoggedIn">
          <span class="nav-user" aria-label="当前登录用户">{{ userStore.user?.username }}</span>
          <button class="nav-link logout" type="button" @click="logout" aria-label="退出登录">退出</button>
        </template>
        <RouterLink v-else to="/login" class="nav-link login">登录</RouterLink>
      </nav>
    </header>
    <main id="main-content" class="main" tabindex="-1">
      <ErrorBoundary>
        <RouterView />
      </ErrorBoundary>
    </main>
    <footer class="footer">
      <p>TutorLoop AI · 多模态自适应学习伙伴</p>
    </footer>
  </div>
</template>

<style>
:root {
  --tl-primary: #2563eb;
  --tl-primary-dark: #1d4ed8;
  --tl-accent: #7c3aed;
  --tl-success: #10b981;
  --tl-warning: #f59e0b;
  --tl-danger: #ef4444;
  --tl-text: #111827;
  --tl-text-secondary: #4b5563;
  --tl-text-muted: #6b7280;
  --tl-bg: #f5f6f8;
  --tl-surface: #ffffff;
  --tl-border: #e5e7eb;
  --tl-radius-sm: 0.5rem;
  --tl-radius: 0.75rem;
  --tl-radius-lg: 1rem;
  --tl-radius-xl: 1.25rem;
  --tl-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  --tl-shadow-lg: 0 10px 30px rgba(0, 0, 0, 0.08);
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
  margin: 0;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  color: #1a1a1a;
  background: #f5f6f8;
  -webkit-font-smoothing: antialiased;
}

:focus-visible {
  outline: 3px solid #2563eb;
  outline-offset: 2px;
  border-radius: 0.25rem;
}

.skip-link {
  position: absolute;
  top: -2.5rem;
  left: 0.75rem;
  z-index: 1000;
  padding: 0.5rem 0.75rem;
  background: var(--tl-primary);
  color: #ffffff;
  text-decoration: none;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 0 0 var(--tl-radius-sm) var(--tl-radius-sm);
  transition: top 0.15s ease;
}

.skip-link:focus {
  top: 0;
  outline: none;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.4);
}

.app {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.header {
  flex-shrink: 0;
  padding: 0.75rem 1rem;
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  text-decoration: none;
  border-radius: var(--tl-radius-sm);
}

.brand-logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5rem;
  background: linear-gradient(135deg, #2563eb, #7c3aed);
  color: #ffffff;
  font-size: 0.8125rem;
  font-weight: 800;
}

.brand-name {
  font-size: 1.125rem;
  font-weight: 700;
  color: #111827;
}

.nav {
  display: flex;
  align-items: center;
  gap: 0.25rem;
  font-size: 0.9375rem;
}

.nav-link {
  color: #374151;
  text-decoration: none;
  padding: 0.375rem 0.625rem;
  border-radius: 0.375rem;
  transition: background 0.15s ease, color 0.15s ease;
  background: none;
  border: none;
  font-size: 0.9375rem;
  cursor: pointer;
}

.nav-link:hover {
  background: #f3f4f6;
  color: #111827;
}

.nav-link.router-link-active {
  color: #1d4ed8;
  background: #eff6ff;
  font-weight: 500;
}

.nav-link.login {
  color: #ffffff;
  background: #2563eb;
}

.nav-link.login:hover {
  background: #1d4ed8;
}

.nav-user {
  padding: 0.375rem 0.625rem;
  color: #4b5563;
  font-size: 0.875rem;
}

.main {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.main:focus {
  outline: none;
}

.footer {
  flex-shrink: 0;
  padding: 0.75rem;
  text-align: center;
  font-size: 0.75rem;
  color: #6b7280;
  background: #ffffff;
  border-top: 1px solid #e5e7eb;
}

.footer p {
  margin: 0;
}

@media (max-width: 480px) {
  .brand-name {
    display: none;
  }
}
</style>

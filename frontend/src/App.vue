<script setup>
import { onMounted, ref } from 'vue'
import { RouterLink, RouterView, useRouter } from 'vue-router'
import { useUserStore } from './stores/user.js'
import ErrorBoundary from './components/ErrorBoundary.vue'

const router = useRouter()
const userStore = useUserStore()
const mobileMenuOpen = ref(false)
const isOnline = ref(navigator.onLine)

onMounted(() => {
  userStore.fetchProfile()
  window.addEventListener('online', () => { isOnline.value = true })
  window.addEventListener('offline', () => { isOnline.value = false })
})

function logout() {
  userStore.clearAuth()
  mobileMenuOpen.value = false
  router.push('/')
}

function closeMobileMenu() {
  mobileMenuOpen.value = false
}
</script>

<template>
  <a href="#main-content" class="skip-link">跳转到主要内容</a>
  <div class="app">
    <div v-if="!isOnline" class="offline-banner" role="status" aria-live="polite">
      网络已断开，部分功能可能不可用
    </div>
    <header class="header">
      <RouterLink to="/" class="brand" aria-label="TutorLoop 首页">
        <span class="brand-logo" aria-hidden="true">TL</span>
        <span class="brand-name">TutorLoop</span>
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
          aria-label="在 GitHub 上查看 TutorLoop 源码（新标签页打开）"
        >GitHub</a>
        <template v-if="userStore.isLoggedIn">
          <span class="nav-user" aria-label="当前登录用户">{{ userStore.user?.username }}</span>
          <button class="nav-link logout" type="button" @click="logout" aria-label="退出登录">退出</button>
        </template>
        <RouterLink v-else to="/login" class="nav-link login">登录</RouterLink>
      </nav>
      <button
        class="menu-toggle"
        type="button"
        aria-label="打开导航菜单"
        aria-expanded="false"
        aria-controls="mobile-nav"
        @click="mobileMenuOpen = !mobileMenuOpen"
      >
        <span class="menu-bar" />
        <span class="menu-bar" />
        <span class="menu-bar" />
      </button>
    </header>
    <nav
      id="mobile-nav"
      class="mobile-nav"
      :class="{ open: mobileMenuOpen }"
      aria-label="移动端导航"
    >
      <RouterLink to="/" class="mobile-nav-link" @click="closeMobileMenu">首页</RouterLink>
      <RouterLink v-if="userStore.isLoggedIn" to="/upload" class="mobile-nav-link" @click="closeMobileMenu">上传课程</RouterLink>
      <RouterLink v-if="userStore.isLoggedIn" to="/dashboard" class="mobile-nav-link" @click="closeMobileMenu">房间管理</RouterLink>
      <a
        href="https://github.com/MS33834/TutorLoop-AI"
        target="_blank"
        rel="noopener noreferrer"
        class="mobile-nav-link"
        @click="closeMobileMenu"
      >GitHub</a>
      <button
        v-if="userStore.isLoggedIn"
        class="mobile-nav-link"
        type="button"
        @click="logout"
      >
        退出（{{ userStore.user?.username }}）
      </button>
      <RouterLink v-else to="/login" class="mobile-nav-link" @click="closeMobileMenu">登录</RouterLink>
    </nav>
    <main id="main-content" class="main" tabindex="-1">
      <ErrorBoundary>
        <RouterView />
      </ErrorBoundary>
    </main>
    <footer class="footer">
      <p>TutorLoop · 让每一次学习都形成闭环</p>
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

.offline-banner {
  flex-shrink: 0;
  padding: 0.5rem 0.75rem;
  text-align: center;
  font-size: 0.8125rem;
  color: #92400e;
  background: #fef3c7;
  border-bottom: 1px solid #fde68a;
}

.menu-toggle {
  display: none;
  flex-direction: column;
  justify-content: center;
  gap: 0.3125rem;
  width: 2.25rem;
  height: 2.25rem;
  padding: 0.375rem;
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-sm);
  background: var(--tl-surface);
  cursor: pointer;
}

.menu-bar {
  display: block;
  height: 0.125rem;
  background: var(--tl-text);
  border-radius: 0.0625rem;
}

.mobile-nav {
  display: none;
  flex-direction: column;
  padding: 0.5rem;
  background: var(--tl-surface);
  border-bottom: 1px solid var(--tl-border);
}

.mobile-nav.open {
  display: flex;
}

.mobile-nav-link {
  padding: 0.75rem 1rem;
  color: var(--tl-text);
  text-decoration: none;
  font-size: 0.9375rem;
  border-radius: var(--tl-radius-sm);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
}

.mobile-nav-link:hover,
.mobile-nav-link.router-link-active {
  background: #eff6ff;
  color: var(--tl-primary);
}

.mobile-nav-link.login {
  background: var(--tl-primary);
  color: var(--tl-surface);
  text-align: center;
}

@media (max-width: 640px) {
  .header {
    padding: 0.625rem 0.75rem;
  }

  .nav {
    display: none;
  }

  .menu-toggle {
    display: flex;
  }
}

@media (max-width: 480px) {
  .brand-name {
    display: none;
  }
}
</style>

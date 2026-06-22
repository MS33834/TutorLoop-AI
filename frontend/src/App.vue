<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app">
    <header class="header">
      <RouterLink to="/" class="brand">
        <span class="brand-logo">TL</span>
        <span class="brand-name">TutorLoop AI</span>
      </RouterLink>
      <nav class="nav">
        <RouterLink to="/" class="nav-link">首页</RouterLink>
        <RouterLink to="/upload" class="nav-link">上传课程</RouterLink>
        <a
          href="https://github.com/MS33834/TutorLoop-AI"
          target="_blank"
          rel="noopener noreferrer"
          class="nav-link"
        >GitHub</a>
      </nav>
    </header>
    <main class="main">
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
  color: #4b5563;
  text-decoration: none;
  padding: 0.375rem 0.625rem;
  border-radius: 0.375rem;
  transition: background 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: #f3f4f6;
  color: #111827;
}

.nav-link.router-link-active {
  color: #2563eb;
  background: #eff6ff;
  font-weight: 500;
}

.main {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.footer {
  flex-shrink: 0;
  padding: 0.75rem;
  text-align: center;
  font-size: 0.75rem;
  color: #9ca3af;
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

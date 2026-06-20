<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>

<template>
  <div class="app">
    <header class="header">
      <h1 class="title">TutorLoop-AI</h1>
      <nav class="nav">
        <RouterLink to="/" class="nav-link">首页</RouterLink>
        <span class="divider">|</span>
        <RouterLink to="/upload" class="nav-link">上传</RouterLink>
      </nav>
    </header>
    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style>
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

.title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #2563eb;
}

.nav {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.9375rem;
}

.nav-link {
  color: #4b5563;
  text-decoration: none;
  padding: 0.25rem 0.375rem;
}

.nav-link.router-link-active {
  color: #2563eb;
  font-weight: 500;
}

.divider {
  color: #d1d5db;
}

.main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>

<script setup>
import ChatView from './views/ChatView.vue'
</script>

<template>
  <div class="app">
    <header class="header">
      <h1 class="title">TutorLoop-AI</h1>
    </header>
    <main class="main">
      <ChatView />
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
  text-align: center;
}

.title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #2563eb;
}

.main {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>

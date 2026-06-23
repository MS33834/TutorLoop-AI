<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <div class="not-found">
    <div class="card">
      <h1 class="title">404</h1>
      <p class="desc">这个页面好像走丢了，回首页继续学习吧</p>
      <button class="btn" type="button" @click="router.push('/')">返回首页</button>
    </div>
  </div>
</template>

<style scoped>
.not-found {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
  padding: 1rem;
}

.card {
  text-align: center;
  padding: 2rem;
  background: #ffffff;
  border-radius: 1rem;
  border: 1px solid #e5e7eb;
  max-width: 22rem;
}

.title {
  margin: 0 0 0.5rem;
  font-size: 4rem;
  font-weight: 800;
  background: linear-gradient(90deg, #2563eb, #7c3aed);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.desc {
  margin: 0 0 1.25rem;
  color: #6b7280;
  font-size: 1rem;
}

.btn {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 0.625rem;
  background: #2563eb;
  color: #ffffff;
  font-size: 0.9375rem;
  cursor: pointer;
}
</style>

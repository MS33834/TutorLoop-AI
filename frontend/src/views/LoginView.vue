<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'
import { useUserStore } from '../stores/user.js'

const router = useRouter()
const userStore = useUserStore()

const mode = ref('login') // 'login' | 'register'
const username = ref('')
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  try {
    const endpoint = mode.value === 'login' ? '/api/auth/login' : '/api/auth/register'
    const body = { username: username.value, password: password.value }
    if (mode.value === 'register' && email.value) {
      body.email = email.value
    }
    const data = await apiFetch(endpoint, {
      method: 'POST',
      body: JSON.stringify(body)
    })
    userStore.setAuth(data.access_token, data.user)
    router.replace('/')
  } catch (err) {
    error.value = err.message || '操作失败'
  } finally {
    loading.value = false
  }
}

function toggleMode() {
  mode.value = mode.value === 'login' ? 'register' : 'login'
  error.value = ''
}
</script>

<template>
  <div class="login">
    <form class="card" @submit.prevent="submit">
      <h1 class="title">{{ mode === 'login' ? '登录' : '注册' }}</h1>
      <p class="subtitle">欢迎回来，继续你的学习闭环</p>

      <label class="field">
        <span>用户名</span>
        <input v-model="username" type="text" autocomplete="username" required />
      </label>

      <label v-if="mode === 'register'" class="field">
        <span>邮箱（可选）</span>
        <input v-model="email" type="email" autocomplete="email" />
      </label>

      <label class="field">
        <span>密码</span>
        <input v-model="password" type="password" autocomplete="current-password" required />
      </label>

      <div v-if="error" class="error">{{ error }}</div>

      <button class="submit" type="submit" :disabled="loading">
        {{ loading ? '请稍候…' : (mode === 'login' ? '登录' : '注册') }}
      </button>

      <p class="switch">
        {{ mode === 'login' ? '还没有账号？' : '已有账号？' }}
        <button type="button" class="link" @click="toggleMode">
          {{ mode === 'login' ? '去注册' : '去登录' }}
        </button>
      </p>
    </form>
  </div>
</template>

<style scoped>
.login {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 70vh;
  padding: 1rem;
}

.card {
  width: 100%;
  max-width: 22rem;
  padding: 2rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-xl);
  box-shadow: var(--tl-shadow);
}

.title {
  margin: 0 0 0.25rem;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--tl-text);
}

.subtitle {
  margin: 0 0 1.25rem;
  font-size: 0.875rem;
  color: var(--tl-text-muted);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-bottom: 0.875rem;
}

.field span {
  font-size: 0.8125rem;
  color: var(--tl-text-secondary);
}

.field input {
  padding: 0.625rem 0.75rem;
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-sm);
  font-size: 0.9375rem;
}

.error {
  margin-bottom: 0.875rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.8125rem;
  color: #b91c1c;
  background: #fee2e2;
  border-radius: var(--tl-radius-sm);
}

.submit {
  width: 100%;
  padding: 0.75rem;
  border: none;
  border-radius: var(--tl-radius-sm);
  background: var(--tl-primary);
  color: var(--tl-surface);
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
}

.submit:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}

.switch {
  margin: 1rem 0 0;
  text-align: center;
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
}

.link {
  background: none;
  border: none;
  color: var(--tl-primary);
  cursor: pointer;
  font-size: 0.8125rem;
}
</style>

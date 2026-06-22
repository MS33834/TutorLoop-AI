<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { apiFetch } from '../api/client.js'
import { useUserStore } from '../stores/user.js'

const router = useRouter()
const userStore = useUserStore()
const courses = ref([])
const loading = ref(false)
const error = ref('')
const roomSlugInput = ref('')

const personas = [
  {
    key: 'student',
    label: '学生',
    title: '你的 24/7 AI 学习伙伴',
    subtitle: '看视频卡住？随时截图提问，TutorLoop AI 用苏格拉底式提问引导你独立思考，真正搞懂每一个知识点。',
    primaryAction: '进入体验房间',
    primaryRoute: null,
    secondaryAction: '浏览课程',
    secondaryRoute: '#courses'
  },
  {
    key: 'tutor',
    label: '老师',
    title: '让 AI 成为你的超级助教',
    subtitle: '上传课程视频，AI 自动抽帧、构建知识图谱、追踪学生掌握度，帮你规模化地提供个性化辅导。',
    primaryAction: '上传课程',
    primaryRoute: '/upload',
    secondaryAction: '查看示例报告',
    secondaryRoute: '/report/demo'
  },
  {
    key: 'parent',
    label: '家长',
    title: '实时掌握孩子的学习进展',
    subtitle: '通过知识图谱与学习报告，清楚看到孩子的薄弱点和进步曲线，辅导更有针对性。',
    primaryAction: '查看示例报告',
    primaryRoute: '/report/demo',
    secondaryAction: '了解工作原理',
    secondaryRoute: '#features'
  }
]

const activePersona = ref('student')
const currentPersona = computed(() => personas.find(p => p.key === activePersona.value) || personas[0])

function handlePrimaryAction() {
  const p = currentPersona.value
  if (p.key === 'student') {
    enterDemo()
    return
  }
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  router.push(p.primaryRoute)
}

function handleSecondaryAction() {
  const p = currentPersona.value
  const target = p.secondaryRoute
  if (target.startsWith('#')) {
    const el = document.querySelector(target)
    if (el) el.scrollIntoView({ behavior: 'smooth' })
    return
  }
  if (target === '/report/demo' && !userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  router.push(target)
}

function setPersona(key) {
  activePersona.value = key
}

function focusPersonaTab(index) {
  const tabs = document.querySelectorAll('.persona-tab')
  tabs[index]?.focus()
}

function onPersonaKeydown(e, index) {
  if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
    e.preventDefault()
    const next = (index + 1) % personas.length
    setPersona(personas[next].key)
    focusPersonaTab(next)
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
    e.preventDefault()
    const prev = (index - 1 + personas.length) % personas.length
    setPersona(personas[prev].key)
    focusPersonaTab(prev)
  } else if (e.key === 'Home') {
    e.preventDefault()
    setPersona(personas[0].key)
    focusPersonaTab(0)
  } else if (e.key === 'End') {
    e.preventDefault()
    const last = personas.length - 1
    setPersona(personas[last].key)
    focusPersonaTab(last)
  }
}

const stats = [
  { value: '10,000+', label: '学习者' },
  { value: '50+', label: '知识节点' },
  { value: '<2s', label: 'AI 平均响应' },
  { value: '24/7', label: '随时辅导' }
]

const features = [
  {
    title: 'AI 苏格拉底式辅导',
    desc: '不直接给答案，通过引导式提问帮你建立深度理解，培养可迁移的解题思维。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>'
  },
  {
    title: '视频时间轴学习',
    desc: '任意时刻截图/提问，AI 自动关联视频帧与知识点，回放学习不再迷失重点。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="2" y="2" width="20" height="20" rx="2.18"></rect><line x1="7" y1="2" x2="7" y2="22"></line><line x1="17" y1="2" x2="17" y2="22"></line><line x1="2" y1="12" x2="22" y2="12"></line><line x1="2" y1="7" x2="7" y2="7"></line><line x1="2" y1="17" x2="7" y2="17"></line><line x1="17" y1="17" x2="22" y2="17"></line><line x1="17" y1="7" x2="22" y2="7"></line></svg>'
  },
  {
    title: '知识图谱驱动',
    desc: '自动构建课程知识图谱，明确前置依赖与学习路径，让知识结构一目了然。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>'
  },
  {
    title: '掌握度实时追踪',
    desc: '基于 BKT 算法动态更新掌握度，推荐下一步学习内容，精准突破薄弱环节。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20V10"></path><path d="M18 20V4"></path><path d="M6 20v-4"></path></svg>'
  },
  {
    title: '多模态交互',
    desc: '支持文字、截图、时间戳多种提问方式，AI 能"看懂"视频画面并给出情境化解答。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>'
  },
  {
    title: '隐私优先设计',
    desc: '截图仅用于当前学习对话，不会长期存储或他用，让你放心提问、专注学习。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>'
  }
]

const steps = [
  {
    title: '上传课程视频',
    desc: '老师上传视频后，AI 自动抽帧、解析画面并抽取知识点，生成可交互课程。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>'
  },
  {
    title: '进入学习房间',
    desc: '边看视频边提问，AI 用苏格拉底式对话引导你思考，像私教一样陪伴左右。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>'
  },
  {
    title: '查看学习报告',
    desc: '掌握度雷达、薄弱点分析与个性化建议，让进步看得见、复习有方向。',
    icon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>'
  }
]

const subjects = [
  { name: '数学', desc: '公式推导、几何直观、解题策略与错题归因' },
  { name: '物理', desc: '概念建模、实验分析、量纲检查与公式溯源' },
  { name: '编程', desc: '代码阅读、调试思路、算法理解与设计模式' },
  { name: '语言学习', desc: '语法解析、写作逻辑、口语练习与词汇网络' },
  { name: '化学', desc: '反应机理、分子结构、实验步骤与计算校验' },
  { name: '人文社科', desc: '论点拆解、史料关联、写作框架与批判性思维' }
]

const tips = [
  {
    title: '先尝试再求助',
    desc: '遇到难题先写下自己的思路，哪怕只写出一半，AI 也能据此精准定位你的卡点。'
  },
  {
    title: '善用截图提问',
    desc: '在视频或作业界面截图，AI 能结合视觉上下文给出更具体、更连贯的讲解。'
  },
  {
    title: '回看知识图谱',
    desc: '学习前先浏览图谱了解前置依赖，学习后根据推荐节点查漏补缺，效率更高。'
  },
  {
    title: '定期查看报告',
    desc: '每周查看一次掌握度雷达，优先攻克红色薄弱点，避免问题堆积。'
  }
]

const testimonials = [
  {
    quote: '以前看视频总卡住，现在随时截图问 AI，就像在跟助教对话，理解得比以前深多了。',
    author: '张同学',
    role: '大一计算机专业'
  },
  {
    quote: '知识图谱让我清楚看到哪块基础没打牢，复习效率提高了很多，学生的提问质量也更高。',
    author: '李老师',
    role: '高中数学教师'
  },
  {
    quote: 'BKT 掌握度曲线比单纯刷题更能反映真实理解程度，我终于知道该练什么了。',
    author: '王同学',
    role: '自学者'
  },
  {
    quote: '作为家长，我每周看一次学习报告就能了解孩子进度，辅导时不再盲目。',
    author: '陈女士',
    role: '初中生家长'
  }
]

const faqs = [
  {
    q: 'TutorLoop AI 适合哪些学习场景？',
    a: '适合需要深度理解的视频课程学习，如数学、物理、编程、语言等。AI 会根据视频画面和知识点进行引导，也适合老师快速构建数字化课程。'
  },
  {
    q: '截图提问会被保存吗？',
    a: '截图仅用于当前对话的上下文理解，不会长期存储或用于其他用途，保护你的学习隐私。'
  },
  {
    q: '掌握度模型是如何工作的？',
    a: '我们使用贝叶斯知识追踪（BKT）算法，根据你的答题、求助、观看等行为动态更新每个知识点的掌握概率。'
  },
  {
    q: '老师如何上传和管理课程？',
    a: '进入"上传课程"页面，填写课程信息并上传视频，系统将自动解析并构建知识图谱，随后可创建学习房间。'
  },
  {
    q: '家长能看到哪些学习数据？',
    a: '家长可以查看学习时长、掌握度雷达、薄弱知识点和近期学习建议，帮助孩子制定复习计划。'
  },
  {
    q: '支持哪些大语言模型？',
    a: '后端采用插件化模型 Provider 架构，可接入 OpenAI 兼容接口、本地模型等多种 LLM/VLM。'
  }
]

onMounted(async () => {
  loading.value = true
  try {
    courses.value = await apiFetch('/api/courses')
  } catch (err) {
    error.value = err.message || '加载课程失败'
  } finally {
    loading.value = false
  }
})

function goToRoom(course) {
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  router.push(`/dashboard?course=${encodeURIComponent(course.id)}`)
}

function goToGraph(course) {
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  router.push(`/graph/${course.id}`)
}

function enterDemo() {
  router.push('/room/demo')
}

function enterRoomBySlug() {
  const slug = roomSlugInput.value.trim()
  if (!slug) return
  router.push(`/room/${encodeURIComponent(slug)}`)
}

function goToDashboard() {
  if (!userStore.isLoggedIn) {
    router.push('/login')
    return
  }
  router.push('/dashboard')
}
</script>

<template>
  <div class="home">
    <section class="hero" aria-labelledby="hero-title">
      <div id="hero-panel" class="hero-content">
        <div class="persona-switcher" role="tablist" aria-label="选择你的身份">
          <button
            v-for="(p, index) in personas"
            :key="p.key"
            type="button"
            class="persona-tab"
            role="tab"
            :aria-selected="activePersona === p.key"
            aria-controls="hero-panel"
            :tabindex="activePersona === p.key ? 0 : -1"
            @click="setPersona(p.key)"
            @keydown="onPersonaKeydown($event, index)"
          >
            {{ p.label }}
          </button>
        </div>

        <h1 id="hero-title" class="hero-title" aria-live="polite">
          {{ currentPersona.title }}
        </h1>
        <p class="hero-subtitle" aria-live="polite">
          {{ currentPersona.subtitle }}
        </p>
        <div class="hero-actions">
          <button
            class="hero-btn primary"
            type="button"
            @click="handlePrimaryAction"
            :aria-label="currentPersona.label + '：' + currentPersona.primaryAction"
          >
            {{ currentPersona.primaryAction }}
          </button>
          <button
            class="hero-btn"
            type="button"
            @click="handleSecondaryAction"
            :aria-label="currentPersona.label + '：' + currentPersona.secondaryAction"
          >
            {{ currentPersona.secondaryAction }}
          </button>
        </div>

        <div class="room-entry">
          <input
            v-model="roomSlugInput"
            type="text"
            class="room-entry-input"
            placeholder="输入房间号，例如 abc123"
            @keydown.enter="enterRoomBySlug"
          />
          <button
            class="room-entry-btn"
            type="button"
            @click="enterRoomBySlug"
          >
            进入房间
          </button>
        </div>
      </div>
      <div class="hero-visual" role="img" aria-label="AI、视频、知识图谱与掌握度追踪围绕学习者旋转的可视化">
        <div class="orbit">
          <span class="orbit-item">AI</span>
          <span class="orbit-item">Video</span>
          <span class="orbit-item">Graph</span>
          <span class="orbit-item">BKT</span>
        </div>
      </div>
    </section>

    <section class="stats" aria-label="平台数据">
      <div v-for="s in stats" :key="s.label" class="stat-item">
        <span class="stat-value">{{ s.value }}</span>
        <span class="stat-label">{{ s.label }}</span>
      </div>
    </section>

    <section id="features" class="features" aria-labelledby="features-title">
      <h2 id="features-title" class="section-title">核心能力</h2>
      <div class="feature-grid" role="list">
        <div v-for="f in features" :key="f.title" class="feature-card" role="listitem">
          <div class="feature-icon" v-html="f.icon"></div>
          <h3 class="feature-title">{{ f.title }}</h3>
          <p class="feature-desc">{{ f.desc }}</p>
        </div>
      </div>
    </section>

    <section class="steps" aria-labelledby="steps-title">
      <h2 id="steps-title" class="section-title">三步开启智能学习</h2>
      <div class="step-grid" role="list">
        <div v-for="(step, idx) in steps" :key="step.title" class="step-card" role="listitem">
          <div class="step-number" :aria-label="'第 ' + (idx + 1) + ' 步'">{{ idx + 1 }}</div>
          <div class="step-icon" v-html="step.icon"></div>
          <h3 class="step-title">{{ step.title }}</h3>
          <p class="step-desc">{{ step.desc }}</p>
        </div>
      </div>
    </section>

    <section class="subjects" aria-labelledby="subjects-title">
      <h2 id="subjects-title" class="section-title">适用学科</h2>
      <div class="subject-grid" role="list">
        <div v-for="subject in subjects" :key="subject.name" class="subject-card" role="listitem">
          <h3 class="subject-name">{{ subject.name }}</h3>
          <p class="subject-desc">{{ subject.desc }}</p>
        </div>
      </div>
    </section>

    <section class="tips" aria-labelledby="tips-title">
      <h2 id="tips-title" class="section-title">学习小技巧</h2>
      <div class="tips-grid" role="list">
        <article v-for="tip in tips" :key="tip.title" class="tip-card" role="listitem">
          <h3 class="tip-title">{{ tip.title }}</h3>
          <p class="tip-desc">{{ tip.desc }}</p>
        </article>
      </div>
    </section>

    <section class="testimonials" aria-labelledby="testimonials-title">
      <h2 id="testimonials-title" class="section-title">用户评价</h2>
      <div class="testimonial-grid" role="list">
        <figure v-for="t in testimonials" :key="t.author" class="testimonial-card" role="listitem">
          <blockquote class="quote">
            <p>“{{ t.quote }}”</p>
          </blockquote>
          <figcaption class="author">
            <span class="author-name">{{ t.author }}</span>
            <span class="author-role">{{ t.role }}</span>
          </figcaption>
        </figure>
      </div>
    </section>

    <section class="faq" aria-labelledby="faq-title">
      <h2 id="faq-title" class="section-title">常见问题</h2>
      <div class="faq-list" role="list">
        <details v-for="item in faqs" :key="item.q" class="faq-item" role="listitem">
          <summary class="faq-q">{{ item.q }}</summary>
          <p class="faq-a">{{ item.a }}</p>
        </details>
      </div>
    </section>

    <section id="courses" class="courses" aria-labelledby="courses-title">
      <h2 id="courses-title" class="section-title">课程列表</h2>
      <div v-if="loading" class="status" role="status" aria-live="polite">加载中…</div>
      <div v-else-if="error" class="status error" role="alert">{{ error }}</div>

      <div v-if="!loading && courses.length" class="course-grid" role="list">
        <article v-for="course in courses" :key="course.id" class="course-card" role="listitem">
          <div class="course-header">
            <h3 class="course-title">{{ course.title }}</h3>
            <span class="course-badge">课程</span>
          </div>
          <p class="course-desc">{{ course.description || '暂无描述' }}</p>
          <div class="course-actions">
            <button
              class="btn primary"
              type="button"
              @click="goToRoom(course)"
              :aria-label="'管理课程房间：' + course.title"
            >
              {{ userStore.isLoggedIn ? '房间管理' : '需登录' }}
            </button>
            <button
              class="btn"
              type="button"
              @click="goToGraph(course)"
              :aria-label="'查看课程知识图谱：' + course.title"
            >
              知识图谱
            </button>
          </div>
        </article>
      </div>

      <div v-if="!loading && !courses.length && !error" class="empty">
        暂无课程，老师可以先去上传。
      </div>
    </section>

    <section class="cta" aria-labelledby="cta-title">
      <div class="cta-card">
        <h2 id="cta-title" class="cta-title">准备好打造你的 AI 课程了吗？</h2>
        <p class="cta-desc">上传视频，3 分钟即可让 AI 为学生提供 24/7 个性化辅导。</p>
        <button
          class="hero-btn primary"
          type="button"
          @click="$router.push('/upload')"
          aria-label="创建第一个课程"
        >
          创建第一个课程
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  padding: 1rem;
  max-width: 72rem;
  margin: 0 auto;
}

.hero {
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 1.5rem;
  align-items: center;
  padding: 3rem 1.5rem;
  margin-bottom: 1.5rem;
  background: linear-gradient(135deg, #eff6ff 0%, #f5f3ff 100%);
  border-radius: var(--tl-radius-xl);
  border: 1px solid #dbeafe;
  position: relative;
  overflow: hidden;
}

.hero::before {
  content: '';
  position: absolute;
  top: -20%;
  right: -10%;
  width: 20rem;
  height: 20rem;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.12) 0%, transparent 70%);
  pointer-events: none;
}

.persona-switcher {
  display: inline-flex;
  gap: 0.25rem;
  padding: 0.25rem;
  margin-bottom: 1.25rem;
  background: rgba(255, 255, 255, 0.7);
  border: 1px solid #dbeafe;
  border-radius: 9999px;
  backdrop-filter: blur(4px);
}

.persona-tab {
  padding: 0.5rem 1rem;
  border-radius: 9999px;
  border: none;
  background: transparent;
  color: var(--tl-text-secondary);
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease;
}

.persona-tab:hover {
  color: var(--tl-text);
}

.persona-tab[aria-selected="true"] {
  background: var(--tl-primary);
  color: #ffffff;
  box-shadow: var(--tl-shadow);
}

.hero-title {
  margin: 0 0 0.75rem;
  font-size: clamp(2.25rem, 5vw, 3.5rem);
  font-weight: 800;
  background: linear-gradient(90deg, var(--tl-primary), var(--tl-accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  line-height: 1.15;
}

.hero-subtitle {
  margin: 0 0 1.5rem;
  font-size: 1.125rem;
  color: var(--tl-text-secondary);
  line-height: 1.7;
  max-width: 36rem;
}

.hero-actions {
  display: flex;
  gap: 0.75rem;
  flex-wrap: wrap;
}

.hero-btn {
  padding: 0.75rem 1.5rem;
  border-radius: var(--tl-radius);
  border: 1px solid var(--tl-primary);
  background: var(--tl-surface);
  color: var(--tl-primary);
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
  transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease, color 0.15s ease;
}

.hero-btn:hover {
  transform: translateY(-2px);
  box-shadow: var(--tl-shadow);
}

.hero-btn.primary {
  background: var(--tl-primary);
  color: var(--tl-surface);
}

.hero-btn.primary:hover {
  background: var(--tl-primary-dark);
  border-color: var(--tl-primary-dark);
}

.room-entry {
  display: flex;
  gap: 0.5rem;
  margin-top: 1.25rem;
  max-width: 24rem;
}

.room-entry-input {
  flex: 1;
  padding: 0.625rem 0.875rem;
  border: 1px solid #dbeafe;
  border-radius: var(--tl-radius);
  font-size: 0.9375rem;
  outline: none;
}

.room-entry-input:focus {
  border-color: var(--tl-primary);
}

.room-entry-btn {
  padding: 0.625rem 1rem;
  border: none;
  border-radius: var(--tl-radius);
  background: var(--tl-primary);
  color: #ffffff;
  font-size: 0.9375rem;
  font-weight: 500;
  cursor: pointer;
}

.hero-visual {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 14rem;
}

.orbit {
  position: relative;
  width: 12rem;
  height: 12rem;
  border-radius: 50%;
  border: 2px dashed #c7d2fe;
  animation: spin 24s linear infinite;
}

.orbit-item {
  position: absolute;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 3.25rem;
  height: 3.25rem;
  border-radius: 50%;
  background: var(--tl-surface);
  color: var(--tl-accent);
  font-size: 0.75rem;
  font-weight: 700;
  box-shadow: var(--tl-shadow);
}

.orbit-item:nth-child(1) { top: -1.625rem; left: calc(50% - 1.625rem); }
.orbit-item:nth-child(2) { right: -1.625rem; top: calc(50% - 1.625rem); }
.orbit-item:nth-child(3) { bottom: -1.625rem; left: calc(50% - 1.625rem); }
.orbit-item:nth-child(4) { left: -1.625rem; top: calc(50% - 1.625rem); }

@keyframes spin {
  to { transform: rotate(360deg); }
}

.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-item {
  text-align: center;
  padding: 1.25rem 1rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.stat-item:hover {
  transform: translateY(-2px);
  box-shadow: var(--tl-shadow);
}

.stat-value {
  display: block;
  font-size: 1.625rem;
  font-weight: 800;
  background: linear-gradient(90deg, var(--tl-primary), var(--tl-accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.stat-label {
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
}

.section-title {
  margin: 0 0 1.25rem;
  font-size: 1.5rem;
  font-weight: 700;
  color: var(--tl-text);
}

.features {
  margin-bottom: 2.5rem;
}

.feature-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
}

.feature-card {
  padding: 1.5rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.feature-card:hover {
  transform: translateY(-3px);
  box-shadow: var(--tl-shadow-lg);
  border-color: #c7d2fe;
}

.feature-icon {
  width: 2.5rem;
  height: 2.5rem;
  color: var(--tl-primary);
  margin-bottom: 0.875rem;
}

.feature-icon svg {
  width: 100%;
  height: 100%;
}

.feature-title {
  margin: 0 0 0.5rem;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--tl-text);
}

.feature-desc {
  margin: 0;
  font-size: 0.875rem;
  color: var(--tl-text-muted);
  line-height: 1.6;
}

.steps {
  margin-bottom: 2.5rem;
}

.step-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
}

.step-card {
  position: relative;
  padding: 1.5rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  transition: box-shadow 0.2s ease;
}

.step-card:hover {
  box-shadow: var(--tl-shadow);
}

.step-number {
  position: absolute;
  top: 1rem;
  right: 1rem;
  width: 1.875rem;
  height: 1.875rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #eff6ff;
  color: var(--tl-primary);
  font-size: 0.8125rem;
  font-weight: 700;
}

.step-icon {
  width: 2rem;
  height: 2rem;
  color: var(--tl-accent);
  margin-bottom: 0.75rem;
}

.step-icon svg {
  width: 100%;
  height: 100%;
}

.step-title {
  margin: 0 0 0.375rem;
  font-size: 1.0625rem;
  font-weight: 600;
  color: var(--tl-text);
}

.step-desc {
  margin: 0;
  font-size: 0.875rem;
  color: var(--tl-text-muted);
  line-height: 1.6;
}

.subjects {
  margin-bottom: 2.5rem;
}

.subject-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
}

.subject-card {
  padding: 1.25rem;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  border-left: 4px solid var(--tl-primary);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}

.subject-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--tl-shadow);
}

.subject-name {
  margin: 0 0 0.25rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--tl-text);
}

.subject-desc {
  margin: 0;
  font-size: 0.8125rem;
  color: var(--tl-text-muted);
  line-height: 1.5;
}

.tips {
  margin-bottom: 2.5rem;
}

.tips-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(16rem, 1fr));
}

.tip-card {
  padding: 1.25rem;
  background: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  border-top: 3px solid var(--tl-accent);
}

.tip-title {
  margin: 0 0 0.5rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--tl-text);
}

.tip-desc {
  margin: 0;
  font-size: 0.875rem;
  color: var(--tl-text-muted);
  line-height: 1.6;
}

.testimonials {
  margin-bottom: 2.5rem;
}

.testimonial-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
}

.testimonial-card {
  padding: 1.5rem;
  margin: 0;
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
}

.quote {
  margin: 0 0 1rem;
  font-size: 0.9375rem;
  color: var(--tl-text-secondary);
  line-height: 1.7;
}

.quote p {
  margin: 0;
}

.author {
  display: flex;
  flex-direction: column;
  gap: 0.125rem;
}

.author-name {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--tl-text);
}

.author-role {
  font-size: 0.75rem;
  color: var(--tl-text-muted);
}

.faq {
  margin-bottom: 2.5rem;
}

.faq-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.faq-item {
  background: var(--tl-surface);
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius);
  padding: 1rem 1.25rem;
}

.faq-q {
  font-weight: 600;
  color: var(--tl-text);
  cursor: pointer;
  list-style: none;
}

.faq-q::-webkit-details-marker {
  display: none;
}

.faq-a {
  margin: 0.75rem 0 0;
  font-size: 0.875rem;
  color: var(--tl-text-secondary);
  line-height: 1.6;
}

.courses {
  margin-bottom: 2.5rem;
}

.status {
  padding: 1rem;
  text-align: center;
  color: var(--tl-text-muted);
}

.status.error {
  color: #991b1b;
  background: #fee2e2;
  border-radius: var(--tl-radius-sm);
}

.course-grid {
  display: grid;
  gap: 1rem;
  grid-template-columns: repeat(auto-fill, minmax(17rem, 1fr));
}

.course-card {
  padding: 1rem;
  background: var(--tl-surface);
  border-radius: var(--tl-radius);
  border: 1px solid var(--tl-border);
  transition: box-shadow 0.2s ease, transform 0.2s ease;
}

.course-card:hover {
  box-shadow: var(--tl-shadow);
  transform: translateY(-2px);
}

.course-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}

.course-title {
  margin: 0;
  font-size: 1.0625rem;
  font-weight: 600;
}

.course-badge {
  font-size: 0.6875rem;
  padding: 0.125rem 0.375rem;
  border-radius: 9999px;
  background: #eff6ff;
  color: var(--tl-primary);
  font-weight: 500;
}

.course-desc {
  margin: 0 0 1rem;
  font-size: 0.875rem;
  color: var(--tl-text-secondary);
  line-height: 1.5;
  min-height: 2.625rem;
}

.course-actions {
  display: flex;
  gap: 0.5rem;
}

.btn {
  flex: 1;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--tl-border);
  border-radius: var(--tl-radius-sm);
  background: var(--tl-surface);
  color: var(--tl-text);
  font-size: 0.9375rem;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
}

.btn:hover {
  background: #f9fafb;
}

.btn.primary {
  background: var(--tl-primary);
  color: var(--tl-surface);
  border-color: var(--tl-primary);
}

.btn.primary:hover {
  background: var(--tl-primary-dark);
  border-color: var(--tl-primary-dark);
}

.empty {
  padding: 2rem;
  text-align: center;
  color: var(--tl-text-muted);
}

.cta {
  margin-bottom: 2rem;
}

.cta-card {
  text-align: center;
  padding: 2.75rem 1.5rem;
  background: linear-gradient(135deg, #1e3a8a 0%, #4c1d95 100%);
  color: #ffffff;
  border-radius: var(--tl-radius-xl);
}

.cta-title {
  margin: 0 0 0.5rem;
  font-size: 1.625rem;
  font-weight: 700;
}

.cta-desc {
  margin: 0 0 1.5rem;
  font-size: 1rem;
  opacity: 0.92;
  max-width: 30rem;
  margin-left: auto;
  margin-right: auto;
}

@media (max-width: 640px) {
  .home {
    padding: 0.75rem;
  }

  .hero {
    grid-template-columns: 1fr;
    text-align: center;
    padding: 2rem 1rem;
  }

  .hero-subtitle {
    margin-left: auto;
    margin-right: auto;
  }

  .hero-actions {
    justify-content: center;
  }

  .hero-visual {
    order: -1;
    min-height: 10rem;
  }

  .orbit {
    width: 9rem;
    height: 9rem;
  }

  .section-title {
    font-size: 1.375rem;
    text-align: center;
  }

  .feature-grid,
  .tips-grid,
  .subject-grid {
    grid-template-columns: 1fr;
  }

  .step-grid,
  .testimonial-grid,
  .course-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orbit {
    animation: none;
  }

  .hero-btn,
  .stat-item,
  .feature-card,
  .step-card,
  .subject-card,
  .course-card,
  .btn {
    transition: none;
  }

  .hero-btn:hover,
  .stat-item:hover,
  .feature-card:hover,
  .step-card:hover,
  .subject-card:hover,
  .course-card:hover {
    transform: none;
  }
}
</style>

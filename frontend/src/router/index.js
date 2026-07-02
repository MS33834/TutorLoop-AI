import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '../stores/user.js'

const HomeView = () => import('../views/HomeView.vue')
const LoginView = () => import('../views/LoginView.vue')
const RoomView = () => import('../views/RoomView.vue')
const UploadView = () => import('../views/UploadView.vue')
const GraphView = () => import('../views/GraphView.vue')
const ReportView = () => import('../views/ReportView.vue')
const TeacherDashboard = () => import('../views/TeacherDashboard.vue')
const ClassReportView = () => import('../views/ClassReportView.vue')
const ForbiddenView = () => import('../views/ForbiddenView.vue')

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: LoginView },
  {
    // 示例报告：无需登录即可预览，必须放在 /report/:courseId 之前以免被参数路由吞掉。
    path: '/report/demo',
    name: 'report-demo',
    component: ReportView,
    props: { courseId: 'demo' }
  },
  {
    path: '/room/:slug',
    name: 'room',
    component: RoomView,
    props: true
  },
  {
    path: '/upload',
    name: 'upload',
    component: UploadView,
    meta: { requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/dashboard',
    name: 'dashboard',
    component: TeacherDashboard,
    meta: { requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/class-report/:courseId',
    name: 'class-report',
    component: ClassReportView,
    props: true,
    meta: { requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/graph/:courseId',
    name: 'graph',
    component: GraphView,
    props: true,
    meta: { requiresAuth: true, requiresTeacher: true }
  },
  {
    path: '/report/:courseId',
    name: 'report',
    component: ReportView,
    props: true,
    meta: { requiresAuth: true }
  },
  {
    path: '/forbidden',
    name: 'forbidden',
    component: ForbiddenView
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('../views/NotFoundView.vue')
  }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

router.beforeEach((to, from, next) => {
  const userStore = useUserStore()

  // Auth-required routes: redirect to login with return path.
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next({ name: 'login', query: { redirect: to.fullPath } })
    return
  }

  // Teacher/admin-only routes: anonymous users go to login; logged-in
  // students/parents land on a dedicated 403 page instead of a silent
  // redirect home (so they understand it's a permission issue, not a bug).
  if (to.meta.requiresTeacher && !userStore.isTeacher) {
    if (!userStore.isLoggedIn) {
      next({ name: 'login', query: { redirect: to.fullPath } })
    } else {
      next({ name: 'forbidden' })
    }
    return
  }

  // Redirect logged-in users away from the login page.
  if (to.name === 'login' && userStore.isLoggedIn) {
    next({ name: 'home' })
    return
  }

  next()
})

export default router

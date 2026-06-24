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

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: LoginView },
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

  // Teacher/admin-only routes: students get redirected to home.
  if (to.meta.requiresTeacher && !userStore.isTeacher) {
    next({ name: 'home' })
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

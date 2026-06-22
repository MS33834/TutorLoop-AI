import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '../stores/user.js'

const HomeView = () => import('../views/HomeView.vue')
const LoginView = () => import('../views/LoginView.vue')
const RoomView = () => import('../views/RoomView.vue')
const UploadView = () => import('../views/UploadView.vue')
const GraphView = () => import('../views/GraphView.vue')
const ReportView = () => import('../views/ReportView.vue')

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/login', name: 'login', component: LoginView },
  {
    path: '/room/:slug',
    name: 'room',
    component: RoomView,
    props: true,
    meta: { requiresAuth: true }
  },
  {
    path: '/upload',
    name: 'upload',
    component: UploadView,
    meta: { requiresAuth: true }
  },
  {
    path: '/graph/:courseId',
    name: 'graph',
    component: GraphView,
    props: true,
    meta: { requiresAuth: true }
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
  if (to.meta.requiresAuth && !userStore.isLoggedIn) {
    next({ name: 'login', query: { redirect: to.fullPath } })
  } else {
    next()
  }
})

export default router

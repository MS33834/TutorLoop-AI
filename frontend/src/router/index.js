import { createRouter, createWebHashHistory } from 'vue-router'

const HomeView = () => import('../views/HomeView.vue')
const RoomView = () => import('../views/RoomView.vue')
const UploadView = () => import('../views/UploadView.vue')
const GraphView = () => import('../views/GraphView.vue')
const ReportView = () => import('../views/ReportView.vue')

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/room/:slug', name: 'room', component: RoomView, props: true },
  { path: '/upload', name: 'upload', component: UploadView },
  { path: '/graph/:courseId', name: 'graph', component: GraphView, props: true },
  { path: '/report/:courseId', name: 'report', component: ReportView, props: true },
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

export default router

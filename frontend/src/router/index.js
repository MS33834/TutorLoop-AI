import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import RoomView from '../views/RoomView.vue'
import UploadView from '../views/UploadView.vue'
import GraphView from '../views/GraphView.vue'

const routes = [
  { path: '/', name: 'home', component: HomeView },
  { path: '/room/:slug', name: 'room', component: RoomView, props: true },
  { path: '/upload', name: 'upload', component: UploadView },
  { path: '/graph/:courseId', name: 'graph', component: GraphView, props: true }
]

const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export default router

import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Competitions from '../views/Competitions.vue'
import Admin from '../views/Admin.vue'
import Profile from '../views/Profile.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/competitions', name: 'competitions', component: Competitions },
    { path: '/admin', name: 'admin', component: Admin },
    { path: '/profile', name: 'profile', component: Profile },
  ],
})

export default router

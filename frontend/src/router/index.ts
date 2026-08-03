import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Competitions from '../views/Competitions.vue'
import Admin from '../views/Admin.vue'
import Profile from '../views/Profile.vue'
import MatchPlay from '../views/MatchPlay.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/competitions', name: 'competitions', component: Competitions },
    { path: '/competitions/:cid/matches/:mid', name: 'match-play', component: MatchPlay },
    { path: '/admin', name: 'admin', component: Admin },
    { path: '/profile', name: 'profile', component: Profile },
  ],
})

export default router

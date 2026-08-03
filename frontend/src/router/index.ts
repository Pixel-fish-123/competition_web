import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Competitions from '../views/Competitions.vue'
import Profile from '../views/Profile.vue'
import MatchPlay from '../views/MatchPlay.vue'
import AdminLayout from '../views/admin/AdminLayout.vue'
import AdminUsers from '../views/admin/Users.vue'
import AdminCompetitions from '../views/admin/Competitions.vue'
import AdminPoints from '../views/admin/Points.vue'
import AdminTraffic from '../views/admin/Traffic.vue'
import AdminPlugins from '../views/admin/Plugins.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/competitions', name: 'competitions', component: Competitions },
    { path: '/competitions/:cid/matches/:mid', name: 'match-play', component: MatchPlay },
    {
      path: '/admin',
      component: AdminLayout,
      redirect: '/admin/users',
      children: [
        { path: 'users', name: 'admin-users', component: AdminUsers },
        { path: 'competitions', name: 'admin-competitions', component: AdminCompetitions },
        { path: 'points', name: 'admin-points', component: AdminPoints },
        { path: 'traffic', name: 'admin-traffic', component: AdminTraffic },
        { path: 'plugins', name: 'admin-plugins', component: AdminPlugins },
      ],
    },
    { path: '/profile', name: 'profile', component: Profile },
  ],
})

// Admin guard: only users with role === 'admin' may access /admin/*.
router.beforeEach(async (to) => {
  if (!to.path.startsWith('/admin')) return true
  const auth = useAuthStore()
  if (!auth.loaded) {
    await auth.fetchMe()
  }
  if (auth.user?.role !== 'admin') {
    return { path: '/' }
  }
  return true
})

export default router

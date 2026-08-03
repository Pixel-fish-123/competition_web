import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Competitions from '../views/Competitions.vue'
import CompetitionDetail from '../views/CompetitionDetail.vue'
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
    { path: '/competitions/:cid', name: 'competition-detail', component: CompetitionDetail },
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
// Profile guard: /profile requires login (todo 22 will generalize auth guards).
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (to.path.startsWith('/admin')) {
    if (!auth.loaded) {
      await auth.fetchMe()
    }
    if (auth.user?.role !== 'admin') {
      return { path: '/' }
    }
    return true
  }
  if (to.path === '/profile') {
    if (!auth.loaded) {
      await auth.fetchMe()
    }
    if (!auth.user) {
      return { path: '/login' }
    }
    return true
  }
  return true
})

export default router

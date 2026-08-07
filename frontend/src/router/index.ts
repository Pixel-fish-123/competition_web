import { createRouter, createWebHistory } from 'vue-router'
import Home from '../views/Home.vue'
import Login from '../views/Login.vue'
import Competitions from '../views/Competitions.vue'
import CompetitionDetail from '../views/CompetitionDetail.vue'
import Profile from '../views/Profile.vue'
import Rankings from '../views/Rankings.vue'
import MatchPlay from '../views/MatchPlay.vue'
import Announcements from '../views/Announcements.vue'
import AnnouncementDetail from '../views/AnnouncementDetail.vue'
import AdminLayout from '../views/admin/AdminLayout.vue'
import AdminUsers from '../views/admin/Users.vue'
import AdminCompetitions from '../views/admin/Competitions.vue'
import AdminPoints from '../views/admin/Points.vue'
import AdminTraffic from '../views/admin/Traffic.vue'
import AdminAnnouncements from '../views/admin/Announcements.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: Home },
    { path: '/login', name: 'login', component: Login },
    { path: '/competitions', name: 'competitions', component: Competitions },
    { path: '/competitions/:cid', name: 'competition-detail', component: CompetitionDetail },
    { path: '/competitions/:cid/matches/:mid', name: 'match-play', component: MatchPlay },
    { path: '/rankings', name: 'rankings', component: Rankings },
    { path: '/announcements', name: 'announcements', component: Announcements },
    { path: '/announcements/:id', name: 'announcement-detail', component: AnnouncementDetail },
    {
      path: '/admin',
      component: AdminLayout,
      redirect: '/admin/users',
      children: [
        { path: 'users', name: 'admin-users', component: AdminUsers },
        { path: 'competitions', name: 'admin-competitions', component: AdminCompetitions },
        { path: 'points', name: 'admin-points', component: AdminPoints },
        { path: 'traffic', name: 'admin-traffic', component: AdminTraffic },
        { path: 'announcements', name: 'admin-announcements', component: AdminAnnouncements },
      ],
    },
    { path: '/profile', name: 'profile', component: Profile, meta: { requiresAuth: true } },
  ],
})

// Global auth guards:
// - /admin/* requires role === 'admin'
// - routes with meta.requiresAuth require login
// - /login redirects to / when already authenticated
router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // Ensure session state is loaded before evaluating guards.
  if (!auth.loaded) {
    await auth.fetchMe()
  }

  // Already logged in → skip the login page.
  if (to.path === '/login' && auth.user) {
    return { path: '/' }
  }

  // Admin guard: only users with role === 'admin' may access /admin/*.
  if (to.path.startsWith('/admin')) {
    if (auth.user?.role !== 'admin') {
      return { path: '/' }
    }
    return true
  }

  // Profile guard: /profile requires login.
  if (to.meta.requiresAuth && !auth.user) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  return true
})

export default router

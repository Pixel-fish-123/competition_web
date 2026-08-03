import { defineStore } from 'pinia'
import http from '../api/http'

export interface AuthUser {
  id: number
  username: string
  email: string
  role: string
  status: string
  created_at: string
}

interface AuthState {
  user: AuthUser | null
  loaded: boolean
}

export const useAuthStore = defineStore('auth', {
  state: (): AuthState => ({
    user: null,
    loaded: false,
  }),
  getters: {
    isRefereeOrAdmin: (state) =>
      state.user?.role === 'referee' || state.user?.role === 'admin',
    isLoggedIn: (state) => state.user !== null,
  },
  actions: {
    async fetchMe(): Promise<AuthUser | null> {
      try {
        const { data } = await http.get<AuthUser>('/auth/me')
        this.user = data
        this.loaded = true
        return data
      } catch {
        this.user = null
        this.loaded = true
        return null
      }
    },
  },
})

import { defineStore } from 'pinia'
import http from '../api/http'

export interface AuthUser {
  id: number
  username: string
  email: string
  nickname: string | null
  qq: string | null
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
    async login(username: string, password: string): Promise<AuthUser> {
      const { data } = await http.post<AuthUser>('/auth/login', {
        username,
        password,
      })
      this.user = data
      this.loaded = true
      return data
    },
    async register(
      username: string,
      email: string,
      password: string,
      nickname?: string,
      qq?: string,
    ): Promise<AuthUser> {
      const body: Record<string, string> = {
        username,
        email,
        password,
      }
      // Optional display nickname: only send when a non-empty value is provided.
      if (nickname) body.nickname = nickname
      if (qq) body.qq = qq
      const { data } = await http.post<AuthUser>('/auth/register', body)
      // Registration auto-logs in (backend sets httpOnly cookie + returns UserOut).
      this.user = data
      this.loaded = true
      return data
    },
    async updateProfile(partial: { nickname?: string; qq?: string }): Promise<AuthUser> {
      const { data } = await http.patch<AuthUser>('/auth/me', partial)
      this.user = data
      return data
    },
    async logout(): Promise<void> {
      try {
        await http.post('/auth/logout')
      } finally {
        this.user = null
        this.loaded = true
      }
    },
  },
})

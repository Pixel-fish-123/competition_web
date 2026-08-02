import axios from 'axios'

// Shared axios instance for the frontend.
// baseURL '/api' is proxied to the backend by Vite (see vite.config.ts).
const http = axios.create({
  baseURL: '/api',
  withCredentials: true,
})

export default http

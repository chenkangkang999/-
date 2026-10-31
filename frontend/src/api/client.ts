import axios from 'axios'

export const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60_000,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

http.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error?.response?.data?.error?.message ?? error.message
    return Promise.reject(new Error(message))
  },
)
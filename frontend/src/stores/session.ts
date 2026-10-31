import { defineStore } from 'pinia'
import { ref } from 'vue'

import { http } from '@/api/client'

interface Profile {
  display_name: string
  sex: string
  allergies: string[]
}

export const useSessionStore = defineStore('session', () => {
  const username = ref('')
  const profile = ref<Profile | null>(null)
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const { data } = await http.get('/accounts/me/')
      username.value = data.username
      profile.value = data.profile
    } finally {
      loading.value = false
    }
  }

  return { username, profile, loading, load }
})
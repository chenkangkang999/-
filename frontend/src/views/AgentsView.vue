<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { http } from '@/api/client'

const agents = ref<Array<{ name: string; description: string }>>([])
const debateEnabled = ref(false)

onMounted(async () => {
  const { data } = await http.get('/agents/')
  agents.value = data.agents
  debateEnabled.value = data.debate_enabled
})
</script>

<template>
  <section>
    <h1>Agent 协作</h1>
    <p class="muted">辩论机制：{{ debateEnabled ? '已开启' : '已关闭' }}</p>
    <div class="grid grid-3" style="margin-top: 16px">
      <article v-for="agent in agents" :key="agent.name" class="card">
        <h2>{{ agent.name }}</h2>
        <p class="muted">{{ agent.description }}</p>
      </article>
    </div>
  </section>
</template>
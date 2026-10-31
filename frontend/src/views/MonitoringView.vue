<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { http } from '@/api/client'

const overview = ref<Record<string, any> | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await http.get('/monitoring/overview/')
    overview.value = data
  } catch (err) {
    error.value = (err as Error).message
  }
})
</script>

<template>
  <section>
    <h1>监控面板</h1>
    <el-alert v-if="error" :title="error" type="error" />
    <div v-if="overview" class="grid grid-3">
      <article class="card">
        <h2>Agent 调用</h2>
        <p>总调用：{{ overview.agents.total }}</p>
        <p>失败：{{ overview.agents.failed }}</p>
      </article>
      <article class="card">
        <h2>延迟</h2>
        <p>平均：{{ Math.round(overview.latency_ms.avg) }} ms</p>
        <p>最大：{{ overview.latency_ms.max }} ms</p>
      </article>
      <article class="card">
        <h2>知识库</h2>
        <p>文档：{{ overview.knowledge.documents }}</p>
        <p>切片：{{ overview.knowledge.chunks }}</p>
      </article>
    </div>
  </section>
</template>
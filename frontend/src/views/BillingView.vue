<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { http } from '@/api/client'

const usage = ref<Record<string, any> | null>(null)
const budget = ref<Record<string, any> | null>(null)

onMounted(async () => {
  const [usageResponse, budgetResponse] = await Promise.all([
    http.get('/billing/usage/'),
    http.get('/billing/budget/'),
  ])
  usage.value = usageResponse.data
  budget.value = budgetResponse.data
})
</script>

<template>
  <section>
    <h1>计费</h1>
    <div class="grid grid-3">
      <article class="card">
        <h2>今日</h2>
        <p>token：{{ usage?.today.tokens ?? 0 }}</p>
        <p>费用：{{ usage?.today.cost ?? '0' }}</p>
      </article>
      <article class="card">
        <h2>累计</h2>
        <p>token：{{ usage?.total.tokens ?? 0 }}</p>
        <p>费用：{{ usage?.total.cost ?? '0' }}</p>
      </article>
      <article class="card">
        <h2>今日预算</h2>
        <p>已用 token：{{ budget?.tokens_used ?? 0 }}</p>
      </article>
    </div>
  </section>
</template>
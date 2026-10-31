<script setup lang="ts">
defineProps<{ steps: Array<{ agent: string; latency_ms: number; error?: string | null }> }>()
</script>

<template>
  <ol class="timeline">
    <li v-for="(step, index) in steps" :key="index" :class="{ failed: step.error }">
      <strong>{{ step.agent }}</strong>
      <span class="muted"> · {{ step.latency_ms }} ms</span>
      <div v-if="step.error" class="muted">失败：{{ step.error }}</div>
    </li>
  </ol>
</template>

<style scoped>
.timeline { padding-left: 20px; margin: 0; }
.timeline .failed { color: var(--danger); }
</style>
<script setup lang="ts">
import { computed } from "vue";
const props = defineProps<{
  soap?: Record<string, unknown> | string | null;
  explanation?: string | null;
  guidance?: unknown;
}>();
const labels: Record<string, string> = {
  S: "主观症状",
  O: "客观信息",
  A: "评估",
  P: "建议计划",
  subjective: "主观症状",
  objective: "客观信息",
  assessment: "评估",
  plan: "建议计划",
};
const entries = computed(() =>
  props.soap && typeof props.soap === "object"
    ? Object.entries(props.soap)
    : [],
);
const readable = (value: unknown) =>
  typeof value === "string"
    ? value
    : Array.isArray(value)
      ? value.join("；")
      : JSON.stringify(value, null, 2);
</script>
<template>
  <div class="soap-panel">
    <div v-for="[key, value] in entries" :key="key" class="soap-item">
      <span>{{ labels[key] || key }}</span>
      <p>{{ readable(value) }}</p>
    </div>
    <p v-if="typeof soap === 'string'" class="preserve">{{ soap }}</p>
    <div v-if="explanation" class="explanation">
      <h4>给你的通俗解释</h4>
      <p class="preserve">{{ explanation }}</p>
    </div>
    <div v-if="guidance">
      <h4>就医指引</h4>
      <p class="preserve">{{ readable(guidance) }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import AppIcon from "./AppIcon.vue";
withDefaults(
  defineProps<{ title?: string; description?: string; compact?: boolean }>(),
  { title: "暂无数据", description: "", compact: false },
);
</script>
<template>
  <div class="empty-state" :class="{ compact }">
    <span class="empty-symbol"><AppIcon name="book" :size="24" /></span
    ><strong>{{ title }}</strong>
    <p v-if="description">{{ description }}</p>
    <slot />
  </div>
</template>

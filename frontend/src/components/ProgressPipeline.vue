<script setup lang="ts">
import type { PipelineStage } from "@/api/learning";
import { learningStatus } from "@/api/learning";
import { statusLabel } from "@/api/types";
defineProps<{ stages: PipelineStage[]; label?: string }>();
const labelFor = (status: string) => ["pending", "running", "completed", "failed", "skipped"].includes(status) ? status === "pending" ? "未开始" : statusLabel(status) : learningStatus(status);
</script>
<template>
  <ol class="progress-pipeline" :aria-label="label || '进度流水线'">
    <li v-for="(stage, index) in stages" :key="stage.id" :class="stage.status">
      <span class="progress-index">{{ String(index + 1).padStart(2, '0') }}</span>
      <div><strong>{{ stage.label }}</strong><span class="progress-state">{{ labelFor(stage.status) }}</span><p v-if="stage.reason">{{ stage.reason }}</p></div>
    </li>
  </ol>
</template>

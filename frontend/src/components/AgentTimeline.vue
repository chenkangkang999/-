<script setup lang="ts">
import { agentLabel, statusLabel, type AgentStep } from "@/api/types";
defineProps<{ steps: AgentStep[] }>();
</script>
<template>
  <ol class="agent-timeline" aria-label="智能体执行步骤">
    <li
      v-for="(step, index) in steps"
      :key="`${step.agent}-${index}`"
      :class="step.status || (step.error ? 'failed' : 'succeeded')"
    >
      <span class="step-dot"></span>
      <div class="step-heading">
        <strong>{{ agentLabel(step.agent) }}</strong
        ><span class="muted">{{
          statusLabel(step.status || (step.error ? "failed" : "succeeded"))
        }}</span>
      </div>
      <small class="muted">{{
        step.latency_ms !== undefined ? `${step.latency_ms} ms` : "等待执行结果"
      }}</small>
      <p v-if="step.error || step.error_code" class="text-danger">
        {{ step.error || step.error_code }}
      </p>
    </li>
  </ol>
</template>

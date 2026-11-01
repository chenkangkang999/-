<script setup lang="ts">
import { computed } from "vue";
import AppIcon from "./AppIcon.vue";
import EvidenceList from "./EvidenceList.vue";
import type { Citation } from "@/api/types";
const props = defineProps<{ audit: Record<string, unknown> }>();
const decision = computed(() =>
  typeof props.audit.decision === "string" ? props.audit.decision : "unknown",
);
const decisions: Record<string, string> = {
  pass: "通过",
  replace: "替换",
  block: "拦截",
};
const severities: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  critical: "极高",
};
const severity = computed(() =>
  typeof props.audit.severity === "string"
    ? severities[props.audit.severity] || props.audit.severity
    : "未提供",
);
const reasons = computed(() =>
  Array.isArray(props.audit.reasons)
    ? props.audit.reasons.filter(
        (reason): reason is string => typeof reason === "string",
      )
    : [],
);
const regulations = computed<Citation[]>(() => {
  if (!Array.isArray(props.audit.regulations)) return [];
  return props.audit.regulations
    .filter((item) => item && typeof item === "object")
    .map((item) => ({
      id: typeof item.id === "string" ? item.id : undefined,
      title:
        [item.title, item.article]
          .filter((value) => typeof value === "string" && value)
          .join(" · ") || "监管条款",
      snippet: typeof item.summary === "string" ? item.summary : undefined,
      source_url:
        typeof item.source_url === "string" ? item.source_url : undefined,
    }));
});
</script>
<template>
  <section class="safety-audit" :class="decision" aria-label="最终安全审核">
    <div class="audit-heading">
      <div>
        <AppIcon name="shield" :size="16" />
        <h3>安全审核</h3>
        <span
          class="pill"
          :class="
            decision === 'block'
              ? 'danger'
              : decision === 'pass'
                ? ''
                : 'neutral'
          "
          >{{ decisions[decision] || "结果未提供" }}</span
        >
      </div>
      <span class="audit-severity">内容审核严重程度：{{ severity }}</span>
    </div>
    <ul v-if="reasons.length" class="audit-reasons">
      <li v-for="(reason, index) in reasons" :key="index">{{ reason }}</li>
    </ul>
    <p v-else class="audit-empty">未提供额外审核说明。</p>
    <details v-if="regulations.length" class="message-evidence" open>
      <summary>监管依据 · {{ regulations.length }} 条</summary>
      <EvidenceList :citations="regulations" />
    </details>
  </section>
</template>
<style scoped>
.safety-audit {
  margin: 18px 0;
  padding: 16px;
  border: 1px solid #e0ede5;
  border-radius: 8px;
  background: #f8fcf9;
}
.safety-audit.block {
  border-color: #efdcd7;
  background: #fefaf8;
}
.safety-audit.replace {
  border-color: #e9e3d7;
  background: #fdfbf7;
}
.audit-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.audit-heading > div {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #658e7c;
}
.audit-heading h3 {
  font-size: 12px;
  font-weight: 550;
}
.audit-heading .pill {
  font-size: 9px;
  padding: 3px 7px;
}
.audit-severity {
  font-size: 10px;
  color: #8b989d;
}
.audit-reasons {
  padding-left: 17px;
  margin: 12px 0 0;
  font-size: 11px;
  line-height: 1.9;
  color: #71818b;
  overflow-wrap: anywhere;
}
.audit-empty {
  margin-top: 12px;
  font-size: 10px;
  color: #95a3ab;
}
.safety-audit :deep(.evidence-item) {
  border-bottom-color: #e8eeea;
}
</style>

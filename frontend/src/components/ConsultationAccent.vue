<script setup lang="ts">
withDefaults(defineProps<{ variant?: "welcome" | "history" }>(), {
  variant: "welcome",
});
</script>

<template>
  <svg
    class="consultation-accent"
    :class="`consultation-accent--${variant}`"
    :viewBox="variant === 'history' ? '0 0 160 90' : '0 0 580 320'"
    fill="none"
    aria-hidden="true"
    focusable="false"
  >
    <g v-if="variant === 'history'" stroke="currentColor" stroke-width="1.3">
      <path d="M14 66c28 0 31-35 60-35s31 28 66 11" />
      <circle cx="14" cy="66" r="4" />
      <circle cx="74" cy="31" r="5" />
      <circle cx="140" cy="42" r="4" />
      <path d="M106 67c0-16 7-29 23-35 2 18-7 29-23 35Zm0 0c-13-2-19-10-19-22 13 0 21 9 19 22Z" />
      <circle cx="34" cy="25" r="1.6" fill="currentColor" stroke="none" />
      <circle cx="147" cy="15" r="1.6" fill="currentColor" stroke="none" />
    </g>
    <g v-else stroke="currentColor" stroke-width="1.2">
      <circle cx="514" cy="60" r="27" stroke-dasharray="2 8" />
      <path d="M459 61h30m52 0h19M514 8v25m0 54v25" />
      <circle cx="459" cy="61" r="3.5" fill="var(--surface)" />
      <circle cx="514" cy="8" r="3.5" fill="var(--surface)" />
      <path d="M17 280c20-2 37-13 48-33m-27 29c-18-1-26-11-26-27 17 1 27 10 26 27Zm13-13c-2-18 4-30 20-38 5 16-2 30-20 38Z" />
      <path d="M17 302h49m-49 0v-10m16 10v-6m16 6v-10m17 10v-6" />
      <circle cx="546" cy="269" r="2" fill="currentColor" stroke="none" />
      <circle cx="558" cy="282" r="2" fill="currentColor" stroke="none" />
      <circle cx="532" cy="285" r="2" fill="currentColor" stroke="none" />
    </g>
  </svg>
</template>

<style scoped>
.consultation-accent {
  position: absolute;
  pointer-events: none;
  user-select: none;
  color: #90ad99;
}
.consultation-accent--history {
  width: min(135px, 75%);
  right: 8px;
  bottom: 13px;
  opacity: 0.2;
}
.consultation-accent--welcome {
  inset: 8px 0;
  width: 100%;
  height: calc(100% - 16px);
  opacity: 0.32;
}
@media (max-width: 560px) {
  .consultation-accent--history { display: none; }
  .consultation-accent--welcome { opacity: 0.2; }
}
</style>

<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 });
const paths: Record<string, string> = {
  home: "M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z",
  chat: "M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-3 3V11.5A8.5 8.5 0 0 1 9.5 3h3a8.5 8.5 0 0 1 8.5 8.5ZM7 10h10M7 14h7",
  agents:
    "M12 3v4M10 3h4M4 8h16v12H4zM1 12h3M20 12h3M8 12h.01M16 12h.01M8 16h8",
  chart: "M3 3v18h18M7 15l4-5 4 3 5-7",
  bill: "M6 3h12v19l-3-2-3 2-3-2-3 2zM9 7h6M9 11h6M9 15h4",
  arrow: "M5 12h14M13 6l6 6-6 6",
  plus: "M12 5v14M5 12h14",
  shield: "M12 2 3 6v6c0 5 9 10 9 10s9-5 9-10V6zM8 12l3 3 5-6",
  pulse: "M2 12h5l3-8 4 16 3-8h5",
  refresh:
    "M20 7v5h-5M4 17v-5h5M5 8a8 8 0 0 1 14-3l1 2M4 17l1 2a8 8 0 0 0 14-3",
  clock: "M12 8v5l3 2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  book: "M12 5C8 2 3 3 2 4v15c3-2 7-2 10 0 3-2 7-2 10 0V4c-3-2-7-2-10 1Zm0 0v14",
  logout: "M9 4H3v16h6M9 12h12M17 8l4 4-4 4",
  send: "m22 2-7 20-4-9L2 9zM11 13 22 2",
  check: "m5 12 4 4L19 6",
};
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.pulse" />
  </svg>
</template>

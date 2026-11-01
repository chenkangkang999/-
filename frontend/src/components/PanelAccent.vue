<template>
  <svg class="panel-accent" viewBox="0 0 150 100" fill="none" aria-hidden="true" focusable="false">
    <circle cx="85" cy="50" r="34" class="accent-halo" />
    <path d="M35 86c19-6 26-20 27-43M54 66c-14-1-22-9-25-19 15 0 24 6 25 19ZM60 53c1-15 9-24 22-28-1 15-8 24-22 28Z" class="accent-leaves" />
    <path d="m81 65 13-21 19 8 10-20" class="accent-connections" />
    <circle cx="81" cy="65" r="3" />
    <circle cx="94" cy="44" r="3" />
    <circle cx="113" cy="52" r="3" />
    <circle cx="123" cy="32" r="3" />
    <path d="M23 78h7m-3.5-3.5v7M119 78h5m-2.5-2.5v5" class="accent-stars" />
    <circle cx="40" cy="31" r="1.5" class="accent-dot" />
    <circle cx="132" cy="63" r="1.5" class="accent-dot" />
  </svg>
</template>

<style scoped>
.panel-accent { width: 140px; height: 94px; color: #8eaf9b; pointer-events: none; user-select: none; }
.panel-accent path,
.panel-accent circle { stroke: currentColor; stroke-width: 1.25; stroke-linecap: round; stroke-linejoin: round; }
.accent-halo { fill: #f0f6ec; stroke: none !important; }
.accent-leaves { fill: #e4efdf; }
.accent-connections { opacity: .75; }
.panel-accent circle:not(.accent-halo) { fill: #fbfdf8; }
.accent-stars,.accent-dot { opacity: .6; }
</style>

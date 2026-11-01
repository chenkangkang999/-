<template>
  <RouterLink to="/" class="brand platform-brand" aria-label="医疗智能体协作平台首页">
    <span class="platform-brand-mark" aria-hidden="true">
      <svg viewBox="0 0 40 40" fill="none" focusable="false">
        <path d="M10.4 10.7a14.3 14.3 0 0 1 19.2 0M33.9 17.5A14.3 14.3 0 0 1 23 33.9M17 33.9A14.3 14.3 0 0 1 6.1 17.5" class="collaboration-ring" />
        <circle cx="7.3" cy="13.4" r="2.3" />
        <circle cx="32.7" cy="13.4" r="2.3" />
        <circle cx="20" cy="34.1" r="2.3" />
        <path d="M20 15.6c-3.6-4.1-9.9 1.2-5.1 6.1L20 26.3l5.1-4.6c4.8-4.9-1.5-10.2-5.1-6.1Z" class="care-heart" />
        <path d="m15.4 19.9 2.5.1 1.3-2.4 1.6 4.2 1.3-1.9h2.5" class="care-pulse" />
      </svg>
    </span>
    <span class="platform-brand-name">医疗智能体协作平台</span>
  </RouterLink>
</template>

<style scoped>
.platform-brand {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  max-width: 100%;
  min-width: 0;
  color: #426f61;
}
.platform-brand-mark {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 41px;
  width: 41px;
  height: 41px;
  border: 1px solid #d8e8de;
  border-radius: 13px;
  background: linear-gradient(145deg, #f1f8f2, #e4f0e8);
}
.platform-brand-mark svg { width: 34px; height: 34px; }
.platform-brand-mark path,
.platform-brand-mark circle { stroke: currentColor; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
.collaboration-ring { opacity: .55; }
.platform-brand-mark circle { fill: #f8fbf5; }
.care-heart { fill: #d4e8db; }
.platform-brand-mark .care-pulse { stroke-width: 1.25; }
.platform-brand-name {
  text-align: center;
  white-space: nowrap;
  line-height: 1.5;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: .5px;
}
.platform-brand:hover .platform-brand-mark { border-color: #aecbbb; }
@media (max-width: 560px) {
  .platform-brand { gap: 7px; }
  .platform-brand-mark { flex-basis: 31px; width: 31px; height: 34px; border-radius: 10px; }
  .platform-brand-mark svg { width: 28px; height: 28px; }
  .platform-brand-name { font-size: 11px; letter-spacing: 0; }
}
</style>

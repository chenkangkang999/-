<script setup lang="ts">
import { useRoute } from 'vue-router'

const route = useRoute()

const navItems = [
  { name: 'home', label: '首页', to: '/' },
  { name: 'consultation', label: '问诊', to: '/consultation' },
  { name: 'agents', label: 'Agent 协作', to: '/agents' },
  { name: 'monitoring', label: '监控', to: '/monitoring' },
  { name: 'billing', label: '计费', to: '/billing' },
]
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="brand">医疗问诊 · 多智能体</div>
      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.name"
          :to="item.to"
          class="nav-link"
          :class="{ active: route.path === item.to }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>

    <main class="app-main">
      <RouterView />
    </main>

    <footer class="app-footer">
      仅供技术演示，内容不构成医疗建议。
    </footer>
  </div>
</template>
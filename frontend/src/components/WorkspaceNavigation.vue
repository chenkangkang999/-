<script setup lang="ts">
import AppIcon from "./AppIcon.vue";
import { workspacePages } from "@/config/workspace";
defineProps<{ activePage?: string }>();
</script>
<template>
  <nav class="workspace-navigation" aria-label="主导航">
    <RouterLink v-for="page in workspacePages" :key="page.name" :to="page.to" class="workspace-nav-link" :class="{ active: activePage === page.name }" :aria-current="activePage === page.name ? 'page' : undefined"><AppIcon :name="page.icon" :size="17" /><span>{{ page.label }}</span></RouterLink>
  </nav>
</template>

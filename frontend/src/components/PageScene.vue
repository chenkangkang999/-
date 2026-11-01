<script setup lang="ts">
import MedicalScene from "./MedicalScene.vue";
import type { PageDefinition } from "@/config/workspace";
defineProps<{ page: PageDefinition }>();
</script>
<template>
  <section class="page-scene" :class="`page-scene-${page.name}`" :style="{ '--scene-position': page.scenePosition }" :aria-labelledby="`scene-title-${page.name}`">
    <div class="page-scene-copy"><span class="scene-page-label">{{ page.label }}</span><h1 :id="`scene-title-${page.name}`">{{ page.title }}</h1><p>{{ page.description }}</p><div class="scene-tags"><span v-for="tag in page.tags" :key="tag">{{ tag }}</span></div></div>
    <MedicalScene :scene="page.name" />
  </section>
</template>

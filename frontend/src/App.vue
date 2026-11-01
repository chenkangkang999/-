<script setup lang="ts">
import DefaultLayout from "@/layouts/DefaultLayout.vue";
import { useRoute } from "vue-router";
const route = useRoute();
</script>
<template>
  <RouterView v-if="route.meta.public" />
  <DefaultLayout v-else />
</template>

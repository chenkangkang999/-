<script setup lang="ts">
import { safeSourceUrl, type Citation } from "@/api/types";
defineProps<{ citations: Citation[] }>();
</script>
<template>
  <div class="evidence-list">
    <article
      v-for="(citation, index) in citations"
      :key="String(citation.chunk_id || index)"
      class="evidence-item"
    >
      <span class="evidence-index">{{ index + 1 }}</span>
      <div>
        <a
          v-if="
            safeSourceUrl(
              citation.source_url || citation.url || citation.source,
            )
          "
          :href="
            safeSourceUrl(
              citation.source_url || citation.url || citation.source,
            )
          "
          target="_blank"
          rel="noopener noreferrer"
          >{{ citation.title || "参考文献" }} ↗</a
        ><strong v-else>{{ citation.title || "参考文献" }}</strong>
        <p v-if="citation.snippet">{{ citation.snippet }}</p>
        <small class="muted"
          >{{ citation.source || citation.source_url || citation.url || citation.document_id || "来源未提供"
          }}<template v-if="citation.chunk_id">
            · 切片 {{ citation.chunk_id }}</template
          ></small
        >
      </div>
    </article>
  </div>
</template>

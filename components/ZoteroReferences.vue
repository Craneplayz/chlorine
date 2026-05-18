<script setup>
import references from '../data/references.json'

function authors(item) {
  if (!item.authors?.length) return 'Unknown author'
  if (item.authors.length === 1) return item.authors[0]
  if (item.authors.length === 2) return `${item.authors[0]} and ${item.authors[1]}`
  return `${item.authors[0]} et al.`
}
</script>

<template>
  <div class="zotero-box">
    <div class="zotero-status">
      <p class="eyebrow">Reference scaffold</p>
      <h3>{{ references.itemCount }} reference{{ references.itemCount === 1 ? '' : 's' }} ready</h3>
      <p>
        Source: <code>{{ references.baseUrl }}</code>
      </p>
      <p>
        Query: <code>{{ references.query || 'all top-level items' }}</code>
      </p>
    </div>

    <ol v-if="references.items?.length" class="reference-list">
      <li v-for="item in references.items" :key="item.key">
        <span class="title">{{ item.title }}</span>
        <span class="meta">{{ authors(item) }} · {{ item.year || 'n.d.' }} · {{ item.publication || item.itemType }}</span>
        <span v-if="item.doi" class="doi">doi: {{ item.doi }}</span>
      </li>
    </ol>

    <div v-else class="empty-state">
      <p>{{ references.message || 'No matching local Zotero items were exported.' }}</p>
      <p>
        Add or export local Zotero items before the final presentation.
      </p>
    </div>
  </div>
</template>

<style scoped>
.zotero-box {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 22px;
  margin-top: 24px;
}

.zotero-status,
.reference-list,
.empty-state {
  border: 1px solid rgba(38, 50, 56, 0.14);
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 12px 30px rgba(38, 50, 56, 0.08);
}

.zotero-status {
  padding: 18px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #607d8b;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

h3 {
  margin: 0 0 14px;
  font-size: 1.16rem;
}

p {
  margin: 0 0 8px;
  color: #455a64;
  font-size: 0.78rem;
  line-height: 1.45;
}

code {
  color: #1f3c5c;
  font-size: 0.72rem;
  white-space: normal;
  word-break: break-word;
}

.reference-list {
  margin: 0;
  padding: 18px 20px 18px 42px;
}

.reference-list li {
  margin-bottom: 12px;
  padding-left: 4px;
}

.title,
.meta,
.doi {
  display: block;
}

.title {
  color: #263238;
  font-size: 0.86rem;
  font-weight: 700;
  line-height: 1.35;
}

.meta,
.doi {
  color: #607d8b;
  font-size: 0.72rem;
  line-height: 1.35;
}

.empty-state {
  padding: 20px;
  display: grid;
  align-content: center;
}
</style>

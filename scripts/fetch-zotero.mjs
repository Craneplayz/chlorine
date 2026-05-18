#!/usr/bin/env node
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'

const root = path.resolve(new URL('..', import.meta.url).pathname)
const outputPath = path.join(root, 'data', 'references.json')
const baseUrl = process.env.ZOTERO_BASE || 'http://127.0.0.1:23119/api/users/0'
const query = process.env.ZOTERO_QUERY ?? 'chlorine pourbaix'
const limit = Number(process.env.ZOTERO_LIMIT || 25)
const excludedTypes = new Set(['attachment', 'annotation', 'note'])

function yearFromDate(date) {
  const match = String(date || '').match(/\d{4}/)
  return match ? match[0] : null
}

function authorName(creator) {
  if (creator.name) return creator.name
  return [creator.firstName, creator.lastName].filter(Boolean).join(' ')
}

function normalizeItem(raw) {
  const data = raw.data || {}
  return {
    key: data.citationKey || raw.key,
    zoteroKey: raw.key,
    itemType: data.itemType,
    title: data.title || 'Untitled',
    authors: (data.creators || [])
      .filter((creator) => creator.creatorType === 'author')
      .map(authorName)
      .filter(Boolean),
    year: yearFromDate(data.date || raw.meta?.parsedDate),
    publication: data.publicationTitle || data.bookTitle || data.websiteTitle || data.publisher || '',
    doi: data.DOI || '',
    url: data.url || raw.links?.alternate?.href || '',
    citationKey: data.citationKey || '',
  }
}

async function writeReferences(payload) {
  await mkdir(path.dirname(outputPath), { recursive: true })
  await writeFile(outputPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8')
}

function makeUrl() {
  const url = new URL(`${baseUrl.replace(/\/$/, '')}/items`)
  url.searchParams.set('limit', String(limit))
  if (query.trim()) url.searchParams.set('q', query.trim())
  return url
}

try {
  const url = makeUrl()
  const response = await fetch(url, {
    headers: {
      Accept: 'application/json',
      'Zotero-API-Version': '3',
    },
  })

  if (!response.ok) {
    throw new Error(`Zotero local API returned ${response.status} ${response.statusText}`)
  }

  const rawItems = await response.json()
  const items = rawItems
    .filter((item) => !excludedTypes.has(item.data?.itemType))
    .map(normalizeItem)
    .filter((item) => item.title && item.title !== 'Untitled')

  const payload = {
    generatedAt: new Date().toISOString(),
    source: 'local-zotero',
    baseUrl,
    query,
    itemCount: items.length,
    items,
    message:
      items.length === 0
        ? 'No matching local Zotero items were exported. Try a broader ZOTERO_QUERY or add relevant items to Zotero.'
        : 'References exported from the local Zotero server.',
  }

  await writeReferences(payload)
  console.log(`Wrote data/references.json with ${items.length} item(s)`)
} catch (error) {
  const payload = {
    generatedAt: new Date().toISOString(),
    source: 'local-zotero',
    baseUrl,
    query,
    itemCount: 0,
    items: [],
    message: `Could not reach local Zotero server: ${error.message}`,
  }
  await writeReferences(payload)
  console.warn(payload.message)
}

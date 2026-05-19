<script setup>
import { useDarkMode } from '@slidev/client'
import { computed, onBeforeUnmount, ref } from 'vue'
import pourbaixData from '../data/chlorine_pourbaix.json'

const width = 760
const height = 430
const margin = { top: 24, right: 32, bottom: 52, left: 60 }
const plotWidth = width - margin.left - margin.right
const plotHeight = height - margin.top - margin.bottom

const pHMin = pourbaixData.axes.pH.min
const pHMax = pourbaixData.axes.pH.max
const eMin = pourbaixData.axes.E.min
const eMax = pourbaixData.axes.E.max
const fallbackTemperatureC =
  pourbaixData.metadata?.defaultTemperatureC ?? pourbaixData.metadata?.temperatureC ?? 25
const temperatureData = (
  pourbaixData.temperatureSlices?.length
    ? pourbaixData.temperatureSlices
    : [
        {
          temperatureC: fallbackTemperatureC,
          nernstFactorV: pourbaixData.metadata?.nernstFactorV,
          compositionModel: pourbaixData.compositionModel,
          slices: pourbaixData.slices,
        },
      ]
).slice().sort((first, second) => first.temperatureC - second.temperatureC)
const temperatureValues = temperatureData.map((entry) => entry.temperatureC)
const temperatureAxis = pourbaixData.axes.temperatureC ?? {}
const temperatureMin = temperatureAxis.min ?? temperatureValues[0] ?? fallbackTemperatureC
const temperatureMax =
  temperatureAxis.max ?? temperatureValues[temperatureValues.length - 1] ?? fallbackTemperatureC
const temperatureStep =
  temperatureAxis.step ?? (temperatureValues[1] - temperatureValues[0] || 1)
const logCMin = pourbaixData.axes.logC?.min ?? -6
const logCMax = pourbaixData.axes.logC?.max ?? 0
const logCStep = 0.1
const temperatureC = ref(fallbackTemperatureC)
const logC = ref(pourbaixData.metadata?.staticLogC ?? -3)
const hovered = ref(null)
const cursorPoint = ref(null)
const displayMode = ref('preset')
const compositionView = ref('percent')
const playingControl = ref(null)
const { isDark } = useDarkMode()
let playbackFrame = null

const playbackDurationMs = 2600

const speciesById = computed(() => {
  return Object.fromEntries(pourbaixData.species.map((species) => [species.id, species]))
})

function xScale(pH) {
  return margin.left + ((pH - pHMin) / (pHMax - pHMin)) * plotWidth
}

function yScale(e) {
  return margin.top + (1 - (e - eMin) / (eMax - eMin)) * plotHeight
}

function pHFromX(x) {
  return pHMin + ((x - margin.left) / plotWidth) * (pHMax - pHMin)
}

function eFromY(y) {
  return eMax - ((y - margin.top) / plotHeight) * (eMax - eMin)
}

function formatPath(points) {
  return points.map((point) => `${xScale(point.pH).toFixed(2)},${yScale(point.E).toFixed(2)}`).join(' ')
}

function pointKey(point) {
  return point.pH.toFixed(4)
}

function activeSegmentsForPoints(activeSegments, points) {
  const pointsByPh = new Map(points.map((point) => [pointKey(point), point]))

  return (activeSegments ?? [])
    .map((segment) => ({
      points: segment.points.map((point) => pointsByPh.get(pointKey(point))).filter(Boolean),
    }))
    .filter((segment) => segment.points.length >= 2)
}

function interpolateBoundary(lowBoundary, highBoundary, t) {
  const points = lowBoundary.points.map((point, index) => ({
    pH: point.pH,
    E: point.E + (highBoundary.points[index].E - point.E) * t,
  }))
  const segmentSource = t < 0.5 ? lowBoundary : highBoundary

  return {
    ...lowBoundary,
    points,
    activeSegments: activeSegmentsForPoints(segmentSource.activeSegments, points),
    activeRegionBoundary: segmentSource.activeRegionBoundary,
  }
}

function interpolateSlices(lower, upper, t, fields = {}) {
  const sliceSource = t < 0.5 ? lower : upper

  return {
    ...sliceSource,
    ...fields,
    boundaries: lower.boundaries.map((boundary, index) =>
      interpolateBoundary(boundary, upper.boundaries[index], t),
    ),
    derivedBoundaries: sliceSource.derivedBoundaries ?? [],
    regions: sliceSource.regions,
  }
}

function sliceForLogC(slices, value) {
  if (value <= slices[0].logC) return slices[0]
  if (value >= slices[slices.length - 1].logC) return slices[slices.length - 1]

  const upperIndex = slices.findIndex((slice) => slice.logC >= value)
  const lower = slices[upperIndex - 1]
  const upper = slices[upperIndex]
  const t = (value - lower.logC) / (upper.logC - lower.logC)

  return interpolateSlices(lower, upper, t, { logC: value })
}

function temperatureBracket(value) {
  if (value <= temperatureData[0].temperatureC) {
    return { lower: temperatureData[0], upper: temperatureData[0], t: 0 }
  }

  const last = temperatureData[temperatureData.length - 1]
  if (value >= last.temperatureC) {
    return { lower: last, upper: last, t: 0 }
  }

  const upperIndex = temperatureData.findIndex((slice) => slice.temperatureC >= value)
  const lower = temperatureData[upperIndex - 1]
  const upper = temperatureData[upperIndex]
  const t = (value - lower.temperatureC) / (upper.temperatureC - lower.temperatureC)

  return { lower, upper, t }
}

const currentTemperaturePayload = computed(() => {
  const { lower, upper, t } = temperatureBracket(temperatureC.value)
  return t < 0.5 ? lower : upper
})

const currentSlice = computed(() => {
  const { lower, upper, t } = temperatureBracket(temperatureC.value)
  const lowerSlice = sliceForLogC(lower.slices, logC.value)

  if (lower === upper) {
    return { ...lowerSlice, temperatureC: lower.temperatureC }
  }

  const upperSlice = sliceForLogC(upper.slices, logC.value)

  return interpolateSlices(lowerSlice, upperSlice, t, {
    logC: logC.value,
    temperatureC: temperatureC.value,
  })
})

const compositionEntries = computed(() => {
  const model = currentTemperaturePayload.value?.compositionModel ?? pourbaixData.compositionModel
  return new Map((model?.species ?? []).map((entry) => [entry.id, entry]))
})

const visibleBoundaries = computed(() => {
  const sliceBoundaries = [
    ...currentSlice.value.boundaries,
    ...(currentSlice.value.derivedBoundaries ?? []),
  ]

  return sliceBoundaries.filter((boundary) => {
    if (boundary.plotBoundary === false) return false
    if (boundary.kind === 'water') return true
    if (!boundary.activeRegionBoundary) return false
    return true
  }).slice().sort((first, second) => Number(!!first.regionReference) - Number(!!second.regionReference))
})

const visibleBoundarySegments = computed(() => {
  return visibleBoundaries.value.flatMap((boundary) => {
    if (boundary.kind === 'water') {
      return [{ id: `${boundary.id}-full`, boundary, points: boundary.points }]
    }

    return (boundary.activeSegments ?? []).map((segment, index) => ({
      id: `${boundary.id}-${index}`,
      boundary,
      points: segment.points,
    }))
  })
})

const theoreticalBoundarySegments = computed(() => {
  if (displayMode.value !== 'allReactions') return []

  return currentSlice.value.boundaries
    .filter((boundary) => {
      return boundary.kind !== 'water'
    })
    .map((boundary) => ({
      id: `theoretical-${boundary.id}`,
      boundary,
      points: boundary.points,
    }))
    .filter((segment) => segment.points?.length >= 2)
})

const activeBoundary = computed(() => hovered.value ?? visibleBoundaries.value[0] ?? null)

const reactionCardBoundaries = computed(() => {
  const seen = new Set()
  const boundaries = [
    ...currentSlice.value.boundaries,
    ...(currentSlice.value.derivedBoundaries ?? []),
  ]

  return boundaries.filter((boundary) => {
    if (!boundary?.id || seen.has(boundary.id)) return false
    seen.add(boundary.id)
    return boundary.label || boundary.equation || boundary.note
  })
})

const regions = computed(() => {
  const sliceRegions = currentSlice.value.regions ?? pourbaixData.regions
  return sliceRegions
})

function regionPoints(region) {
  return region.polygon.map((point) => `${xScale(point.pH)},${yScale(point.E)}`).join(' ')
}

function boundaryDashArray(boundary) {
  if (boundary.kind === 'water') return '7 6'
  if (boundary.kind === 'dominance') return '4 3'
  if (boundary.regionReference) return '8 4 2 4'
  return 'none'
}

function pushChemicalSegment(segments, kind, text) {
  if (!text) return
  const previous = segments[segments.length - 1]
  if (previous?.kind === kind) {
    previous.text += text
  } else {
    segments.push({ kind, text })
  }
}

function isSubscriptDigit(text, index) {
  return /[A-Za-z)]/.test(text[index - 1] ?? '')
}

function isChargeSign(text, index) {
  const previous = text[index - 1] ?? ''
  const next = text[index + 1] ?? ''
  if (!/[A-Za-z0-9)]/.test(previous)) return false
  return next === '' || /[\s/),]/.test(next)
}

function chemicalSegments(text) {
  const normalized = String(text ?? '').replace(/\s*->\s*/g, ' → ')
  const segments = []

  for (let index = 0; index < normalized.length; index += 1) {
    const character = normalized[index]

    if (/\d/.test(character) && isSubscriptDigit(normalized, index)) {
      let digits = character
      while (/\d/.test(normalized[index + 1] ?? '')) {
        index += 1
        digits += normalized[index]
      }
      pushChemicalSegment(segments, 'sub', digits)
    } else if ((character === '+' || character === '-') && isChargeSign(normalized, index)) {
      pushChemicalSegment(segments, 'sup', character)
    } else {
      pushChemicalSegment(segments, 'text', character)
    }
  }

  return segments
}

function svgBaselineShift(kind) {
  if (kind === 'sub') return '-0.35em'
  if (kind === 'sup') return '0.45em'
  return '0'
}

function svgFontSize(kind) {
  return kind === 'text' ? '1em' : '0.7em'
}

function updateCursorPoint(event) {
  const rect = event.currentTarget.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * width
  const y = ((event.clientY - rect.top) / rect.height) * height

  if (
    x < margin.left ||
    x > margin.left + plotWidth ||
    y < margin.top ||
    y > margin.top + plotHeight
  ) {
    cursorPoint.value = null
    return
  }

  cursorPoint.value = {
    pH: pHFromX(x),
    E: eFromY(y),
  }
}

function log10SumExp(values) {
  const maximum = Math.max(...values)
  const total = values.reduce((sum, value) => sum + 10 ** (value - maximum), 0)
  return maximum + Math.log10(total)
}

function totalChlorineLogForLambda(baseAtomLogs, entries, lambda) {
  return log10SumExp(
    baseAtomLogs.map((value, index) => value + entries[index].chlorineCount * lambda),
  )
}

function solveMassBalanceLambda(relativeLogs, entries) {
  const baseAtomLogs = relativeLogs.map(
    (value, index) => Math.log10(entries[index].chlorineCount) + value,
  )
  let lower = -200
  let upper = 200

  for (let index = 0; index < 12 && totalChlorineLogForLambda(baseAtomLogs, entries, lower) > logC.value; index += 1) {
    lower -= 200
  }

  for (let index = 0; index < 12 && totalChlorineLogForLambda(baseAtomLogs, entries, upper) < logC.value; index += 1) {
    upper += 200
  }

  for (let index = 0; index < 90; index += 1) {
    const middle = (lower + upper) / 2
    if (totalChlorineLogForLambda(baseAtomLogs, entries, middle) < logC.value) {
      lower = middle
    } else {
      upper = middle
    }
  }

  return (lower + upper) / 2
}

const compositionRows = computed(() => {
  if (!cursorPoint.value || compositionEntries.value.size === 0) return []

  const entries = pourbaixData.species
    .map((species) => compositionEntries.value.get(species.id))
    .filter(Boolean)
  const relativeLogs = entries.map((entry) => {
    const coefficients = entry.coefficients
    return (
      coefficients.constant +
      coefficients.pH * cursorPoint.value.pH +
      coefficients.E * cursorPoint.value.E +
      coefficients.logC * logC.value
    )
  })
  const lambda = solveMassBalanceLambda(relativeLogs, entries)
  const concentrations = relativeLogs.map(
    (value, index) => 10 ** (value + entries[index].chlorineCount * lambda),
  )
  const molecularTotal = concentrations.reduce((sum, value) => sum + value, 0)
  const concentrationBySpecies = new Map(
    entries.map((entry, index) => [entry.id, concentrations[index]]),
  )

  return pourbaixData.species.map((species) => {
    const concentration = concentrationBySpecies.get(species.id) ?? 0
    return {
      species,
      concentration,
      percent: molecularTotal > 0 ? (concentration / molecularTotal) * 100 : 0,
    }
  })
})

function formatPercent(value) {
  if (value > 0 && value < 0.01) return '<0.01%'
  if (value >= 10) return `${value.toFixed(1)}%`
  return `${value.toFixed(2)}%`
}

function formatConcentration(value) {
  if (!Number.isFinite(value) || value <= 0) return '0'
  if (value >= 0.01 && value < 100) return value.toPrecision(3)
  return value.toExponential(1)
}

function formatTemperature(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '25 °C'
  return `${Number.isInteger(numericValue) ? numericValue.toFixed(0) : numericValue.toFixed(1)} °C`
}

function setPlaybackValue(control, value) {
  if (control === 'logC') {
    logC.value = value
  } else if (control === 'temperatureC') {
    temperatureC.value = value
  }
}

function playbackRange(control) {
  if (control === 'logC') {
    return { start: logCMin, end: logCMax }
  }

  return { start: temperatureMin, end: temperatureMax }
}

function stopPlayback() {
  if (playbackFrame !== null) {
    cancelAnimationFrame(playbackFrame)
    playbackFrame = null
  }
  playingControl.value = null
}

function startPlayback(control) {
  stopPlayback()

  const { start, end } = playbackRange(control)
  const startedAt = performance.now()

  playingControl.value = control
  setPlaybackValue(control, start)

  function tick(now) {
    const progress = Math.min((now - startedAt) / playbackDurationMs, 1)
    setPlaybackValue(control, start + (end - start) * progress)

    if (progress < 1) {
      playbackFrame = requestAnimationFrame(tick)
    } else {
      playbackFrame = null
      playingControl.value = null
      setPlaybackValue(control, end)
    }
  }

  playbackFrame = requestAnimationFrame(tick)
}

function togglePlayback(control) {
  if (playingControl.value === control) {
    stopPlayback()
  } else {
    startPlayback(control)
  }
}

const xTicks = [0, 2, 4, 6, 8, 10, 12, 14]
const yTicks = [-0.8, -0.4, 0, 0.4, 0.8, 1.2, 1.6, 2.0]

onBeforeUnmount(stopPlayback)
</script>

<template>
  <div class="pourbaix-shell" :class="{ 'is-dark': isDark }">
    <div class="diagram-column">
      <div class="chart-panel">
        <svg
          :viewBox="`0 0 ${width} ${height}`"
          preserveAspectRatio="xMidYMin meet"
          role="img"
          aria-label="Interactive chlorine Pourbaix diagram"
          @mousemove="updateCursorPoint"
          @mouseleave="cursorPoint = null"
        >
        <defs>
          <clipPath id="pourbaix-plot-clip">
            <rect
              :x="margin.left"
              :y="margin.top"
              :width="plotWidth"
              :height="plotHeight"
            />
          </clipPath>
        </defs>

        <rect
          :x="margin.left"
          :y="margin.top"
          :width="plotWidth"
          :height="plotHeight"
          class="plot-area"
        />

        <g v-for="tick in xTicks" :key="`x-${tick}`">
          <line
            :x1="xScale(tick)"
            :x2="xScale(tick)"
            :y1="margin.top"
            :y2="margin.top + plotHeight"
            class="grid-line"
            stroke-width="1"
          />
          <text :x="xScale(tick)" :y="height - 20" text-anchor="middle" class="axis-tick">{{ tick }}</text>
        </g>

        <g v-for="tick in yTicks" :key="`y-${tick}`">
          <line
            :x1="margin.left"
            :x2="margin.left + plotWidth"
            :y1="yScale(tick)"
            :y2="yScale(tick)"
            class="grid-line"
            stroke-width="1"
          />
          <text :x="margin.left - 12" :y="yScale(tick) + 4" text-anchor="end" class="axis-tick">
            {{ tick.toFixed(1) }}
          </text>
        </g>

        <g clip-path="url(#pourbaix-plot-clip)">
          <polygon
            v-for="region in regions"
            :key="region.id"
            :points="regionPoints(region)"
            :fill="speciesById[region.species].color"
            opacity="0.18"
          />
          <text
            v-for="region in regions"
            :key="`${region.id}-label`"
            :x="xScale(region.label.pH)"
            :y="yScale(region.label.E)"
            :fill="speciesById[region.species].color"
            class="region-label"
          >
            <tspan
              v-for="(segment, index) in chemicalSegments(speciesById[region.species].label)"
              :key="`${region.id}-formula-${index}`"
              :baseline-shift="svgBaselineShift(segment.kind)"
              :font-size="svgFontSize(segment.kind)"
            >
              {{ segment.text }}
            </tspan>
          </text>

          <polyline
            v-for="segment in theoreticalBoundarySegments"
            :key="segment.id"
            :points="formatPath(segment.points)"
            fill="none"
            :stroke="segment.boundary.color"
            :stroke-width="hovered?.id === segment.boundary.id ? 3 : 1.7"
            stroke-dasharray="1 6"
            stroke-linecap="round"
            opacity="0.62"
            @mouseenter="hovered = segment.boundary"
            @mouseleave="hovered = null"
          />

          <polyline
            v-for="segment in visibleBoundarySegments"
            :key="segment.id"
            :points="formatPath(segment.points)"
            fill="none"
            :stroke="segment.boundary.color"
            :stroke-width="hovered?.id === segment.boundary.id ? 4 : 2.5"
            :stroke-dasharray="boundaryDashArray(segment.boundary)"
            stroke-linecap="round"
            @mouseenter="hovered = segment.boundary"
            @mouseleave="hovered = null"
          />

          <polyline
            v-for="segment in theoreticalBoundarySegments"
            :key="`${segment.id}-hitbox`"
            :points="formatPath(segment.points)"
            class="boundary-hitbox"
            @mouseenter="hovered = segment.boundary"
            @mouseleave="hovered = null"
          />

          <polyline
            v-for="segment in visibleBoundarySegments"
            :key="`${segment.id}-hitbox`"
            :points="formatPath(segment.points)"
            class="boundary-hitbox"
            @mouseenter="hovered = segment.boundary"
            @mouseleave="hovered = null"
          />
        </g>

        <line
          :x1="margin.left"
          :x2="margin.left + plotWidth"
          :y1="margin.top + plotHeight"
          :y2="margin.top + plotHeight"
          class="axis-frame"
          stroke-width="1.5"
        />
        <line
          :x1="margin.left"
          :x2="margin.left"
          :y1="margin.top"
          :y2="margin.top + plotHeight"
          class="axis-frame"
          stroke-width="1.5"
        />

        <text :x="margin.left + plotWidth / 2" :y="height - 2" text-anchor="middle" class="axis-label">pH</text>
        <text
          :x="-margin.top - plotHeight / 2"
          y="16"
          transform="rotate(-90)"
          text-anchor="middle"
          class="axis-label"
        >
          E vs SHE (V)
        </text>
        </svg>
      </div>

      <div class="under-chart-panels">
        <div class="chart-control-card concentration-card">
          <label for="logC">log<sub>10</sub> Total Cl</label>
          <button
            type="button"
            class="play-toggle"
            :class="{ active: playingControl === 'logC' }"
            :aria-label="playingControl === 'logC' ? 'Stop chlorine playback' : 'Play chlorine concentration range'"
            :title="playingControl === 'logC' ? 'Stop' : 'Play log chlorine from -6 to 0'"
            @click="togglePlayback('logC')"
          >
            <svg v-if="playingControl === 'logC'" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="7" y="7" width="10" height="10" rx="1.4" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <path d="M8 5.5v13l10-6.5-10-6.5Z" />
            </svg>
          </button>
          <input
            id="logC"
            v-model.number="logC"
            type="range"
            :min="logCMin"
            :max="logCMax"
            :step="logCStep"
            @input="stopPlayback"
          />
          <output>{{ logC.toFixed(1) }}</output>
        </div>
        <div class="chart-control-card temperature-card">
          <label for="temperatureC">Temp</label>
          <button
            type="button"
            class="play-toggle"
            :class="{ active: playingControl === 'temperatureC' }"
            :aria-label="playingControl === 'temperatureC' ? 'Stop temperature playback' : 'Play temperature range'"
            :title="playingControl === 'temperatureC' ? 'Stop' : 'Play temperature from 0 °C to 100 °C'"
            @click="togglePlayback('temperatureC')"
          >
            <svg v-if="playingControl === 'temperatureC'" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="7" y="7" width="10" height="10" rx="1.4" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <path d="M8 5.5v13l10-6.5-10-6.5Z" />
            </svg>
          </button>
          <input
            id="temperatureC"
            v-model.number="temperatureC"
            type="range"
            :min="temperatureMin"
            :max="temperatureMax"
            :step="temperatureStep"
            @input="stopPlayback"
          />
          <output>{{ formatTemperature(temperatureC) }}</output>
        </div>
      </div>
    </div>

    <aside class="control-panel">
      <button
        type="button"
        class="mode-toggle"
        :class="{ active: displayMode === 'allReactions' }"
        :aria-label="displayMode === 'allReactions' ? 'Switch to preset mode' : 'Switch to all reactions mode'"
        :title="displayMode === 'allReactions' ? 'All reaction lines' : 'Active boundaries only'"
        @click="displayMode = displayMode === 'allReactions' ? 'preset' : 'allReactions'"
      >
        <svg class="mode-icon" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 3 3.8 7.5 12 12l8.2-4.5L12 3Z" />
          <path d="M4.2 11.2 12 15.5l7.8-4.3" />
          <path d="M4.2 15.5 12 19.8l7.8-4.3" />
        </svg>
      </button>

      <div v-if="activeBoundary" class="equation-card">
        <div class="equation-content">
          <p class="equation-title">
            <template
              v-for="(segment, index) in chemicalSegments(activeBoundary.label)"
              :key="`${activeBoundary.id}-title-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
          <p v-if="activeBoundary.equation" class="equation">
            <template
              v-for="(segment, index) in chemicalSegments(activeBoundary.equation)"
              :key="`${activeBoundary.id}-equation-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
          <p class="equation-note">
            <template
              v-for="(segment, index) in chemicalSegments(activeBoundary.note)"
              :key="`${activeBoundary.id}-note-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
        </div>

        <div
          v-for="boundary in reactionCardBoundaries"
          :key="`measure-${boundary.id}`"
          class="equation-content equation-measure"
          aria-hidden="true"
        >
          <p class="equation-title">
            <template
              v-for="(segment, index) in chemicalSegments(boundary.label)"
              :key="`${boundary.id}-measure-title-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
          <p v-if="boundary.equation" class="equation">
            <template
              v-for="(segment, index) in chemicalSegments(boundary.equation)"
              :key="`${boundary.id}-measure-equation-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
          <p class="equation-note">
            <template
              v-for="(segment, index) in chemicalSegments(boundary.note)"
              :key="`${boundary.id}-measure-note-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </p>
        </div>
      </div>

      <div class="composition-card">
        <div class="composition-header">
          <span v-if="cursorPoint" class="coordinate-readout">
            pH {{ cursorPoint.pH.toFixed(2) }} · E {{ cursorPoint.E.toFixed(2) }} V
          </span>
          <span v-else class="coordinate-readout">No plot point</span>
          <button
            type="button"
            class="unit-toggle"
            :aria-label="compositionView === 'percent' ? 'Show molecular concentrations' : 'Show molecular percentages'"
            :title="compositionView === 'percent' ? 'Showing percent; click for concentration' : 'Showing concentration; click for percent'"
            @click="compositionView = compositionView === 'percent' ? 'concentration' : 'percent'"
          >
            {{ compositionView === 'percent' ? '%' : 'conc.' }}
          </button>
        </div>
        <div v-if="cursorPoint" class="composition-list">
          <div v-for="row in compositionRows" :key="row.species.id" class="composition-row">
            <span class="swatch" :style="{ backgroundColor: row.species.color }"></span>
            <span class="composition-label">
              <template
                v-for="(segment, index) in chemicalSegments(row.species.label)"
                :key="`${row.species.id}-composition-${index}`"
              >
                <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
                <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
                <span v-else>{{ segment.text }}</span>
              </template>
            </span>
            <span class="composition-value">
              {{
                compositionView === 'percent'
                  ? formatPercent(row.percent)
                  : formatConcentration(row.concentration)
              }}
            </span>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<style scoped>
.pourbaix-shell {
  --pourbaix-surface: #ffffff;
  --pourbaix-panel-border: rgba(38, 50, 56, 0.14);
  --pourbaix-panel-shadow: 0 12px 30px rgba(38, 50, 56, 0.08);
  --pourbaix-plot-bg: #fbfaf6;
  --pourbaix-plot-border: #cfd8dc;
  --pourbaix-grid: #e6e1d8;
  --pourbaix-frame: #455a64;
  --pourbaix-text: #37474f;
  --pourbaix-text-strong: #111827;
  --pourbaix-text-muted: #607d8b;
  --pourbaix-accent-text: #1f3c5c;
  --pourbaix-accent: #1f78f2;
  --pourbaix-button-bg: #ffffff;
  --pourbaix-button-muted-bg: #eef3f6;
  --pourbaix-card-bg: #f7f9fb;
  --pourbaix-control-track: #e5e7eb;
  --pourbaix-control-thumb: #6b7280;
  --pourbaix-equation-edge: #2f6fba;
  --pourbaix-composition-edge: #6a7a89;
  --pourbaix-swatch-border: rgba(0, 0, 0, 0.12);
  --pourbaix-region-label-halo: #ffffff;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 252px);
  gap: 12px;
  align-items: stretch;
  height: clamp(340px, 48vh, 420px);
  max-height: calc(100vh - 170px);
  margin-top: 8px;
  min-height: 0;
}

.pourbaix-shell.is-dark {
  --pourbaix-surface: #111827;
  --pourbaix-panel-border: rgba(148, 163, 184, 0.26);
  --pourbaix-panel-shadow: 0 14px 34px rgba(0, 0, 0, 0.32);
  --pourbaix-plot-bg: #101820;
  --pourbaix-plot-border: #475569;
  --pourbaix-grid: #334155;
  --pourbaix-frame: #cbd5e1;
  --pourbaix-text: #dbeafe;
  --pourbaix-text-strong: #f8fafc;
  --pourbaix-text-muted: #94a3b8;
  --pourbaix-accent-text: #bfdbfe;
  --pourbaix-accent: #60a5fa;
  --pourbaix-button-bg: #1e293b;
  --pourbaix-button-muted-bg: #172033;
  --pourbaix-card-bg: #172033;
  --pourbaix-control-track: #334155;
  --pourbaix-control-thumb: #cbd5e1;
  --pourbaix-equation-edge: #60a5fa;
  --pourbaix-composition-edge: #94a3b8;
  --pourbaix-swatch-border: rgba(248, 250, 252, 0.34);
  --pourbaix-region-label-halo: #0f172a;
}

.chart-panel,
.control-panel,
.chart-control-card {
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 8px;
  background: var(--pourbaix-surface);
  box-shadow: var(--pourbaix-panel-shadow);
}

.diagram-column {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 8px;
  height: 100%;
  min-height: 0;
}

.chart-panel {
  box-sizing: border-box;
  height: 100%;
  padding: 8px;
  overflow: hidden;
}

.chart-panel svg {
  width: 100%;
  height: 100%;
  display: block;
}

.plot-area {
  fill: var(--pourbaix-plot-bg);
  stroke: var(--pourbaix-plot-border);
}

.grid-line {
  stroke: var(--pourbaix-grid);
}

.axis-frame {
  stroke: var(--pourbaix-frame);
}

.under-chart-panels {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.chart-control-card {
  box-sizing: border-box;
  min-width: 0;
  min-height: 46px;
  padding: 7px 9px;
}

.concentration-card,
.temperature-card {
  display: grid;
  grid-template-columns: max-content 22px minmax(0, 1fr) 52px;
  gap: 7px;
  align-items: center;
}

.control-panel {
  position: relative;
  box-sizing: border-box;
  height: 100%;
  padding: 8px 10px 9px;
  display: flex;
  flex-direction: column;
  gap: 7px;
  overflow: hidden;
}

.mode-toggle {
  display: grid;
  place-items: center;
  align-self: end;
  width: 24px;
  height: 24px;
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 6px;
  background: var(--pourbaix-button-muted-bg);
  color: var(--pourbaix-frame);
  padding: 0;
}

.mode-toggle.active {
  background: var(--pourbaix-button-bg);
  border-color: color-mix(in srgb, var(--pourbaix-accent) 55%, transparent);
  color: var(--pourbaix-accent-text);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--pourbaix-frame) 28%, transparent);
}

.mode-icon {
  width: 15px;
  height: 15px;
  fill: none;
  stroke: currentColor;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 1.9;
}

.control-title,
label {
  margin: 0;
  color: var(--pourbaix-text);
  font-size: 0.66rem;
  font-weight: 700;
  line-height: 1.05;
  white-space: nowrap;
}

label sub {
  bottom: -0.2em;
  font-size: 0.7em;
  line-height: 0;
  position: relative;
  vertical-align: baseline;
}

input[type="range"] {
  appearance: none;
  -webkit-appearance: none;
  background: transparent;
  width: 100%;
  min-width: 0;
  accent-color: var(--pourbaix-accent);
}

input[type="range"]::-webkit-slider-runnable-track {
  height: 6px;
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 999px;
  background: linear-gradient(90deg, var(--pourbaix-accent), var(--pourbaix-control-track));
}

input[type="range"]::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 20px;
  height: 20px;
  margin-top: -8px;
  border: 2px solid var(--pourbaix-surface);
  border-radius: 50%;
  background: var(--pourbaix-control-thumb);
  box-shadow: 0 1px 4px color-mix(in srgb, var(--pourbaix-frame) 38%, transparent);
}

input[type="range"]::-moz-range-track {
  height: 6px;
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 999px;
  background: var(--pourbaix-control-track);
}

input[type="range"]::-moz-range-progress {
  height: 6px;
  border-radius: 999px;
  background: var(--pourbaix-accent);
}

input[type="range"]::-moz-range-thumb {
  width: 18px;
  height: 18px;
  border: 2px solid var(--pourbaix-surface);
  border-radius: 50%;
  background: var(--pourbaix-control-thumb);
  box-shadow: 0 1px 4px color-mix(in srgb, var(--pourbaix-frame) 38%, transparent);
}

.play-toggle {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 50%;
  background: var(--pourbaix-button-bg);
  color: var(--pourbaix-accent-text);
  padding: 0;
  box-shadow: 0 1px 2px color-mix(in srgb, var(--pourbaix-frame) 24%, transparent);
}

.play-toggle.active {
  background: var(--pourbaix-accent);
  border-color: var(--pourbaix-accent);
  color: var(--pourbaix-surface);
}

.play-toggle svg {
  width: 13px;
  height: 13px;
  fill: currentColor;
}

output {
  font-variant-numeric: tabular-nums;
  color: var(--pourbaix-accent-text);
  font-size: 0.62rem;
  font-weight: 700;
  text-align: right;
  white-space: nowrap;
}

.chem-sub,
.chem-sup {
  font-size: 0.68em;
  line-height: 0;
  position: relative;
  vertical-align: baseline;
}

.chem-sub {
  bottom: -0.22em;
}

.chem-sup {
  top: -0.38em;
}

.swatch {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1px solid var(--pourbaix-swatch-border);
}

.equation-card {
  border-left: 3px solid var(--pourbaix-equation-edge);
  background: var(--pourbaix-card-bg);
  box-sizing: border-box;
  display: grid;
  flex: 0 0 auto;
  overflow: hidden;
  padding: 8px 10px 7px;
}

.equation-content {
  grid-area: 1 / 1;
  min-width: 0;
}

.equation-measure {
  pointer-events: none;
  visibility: hidden;
}

.composition-card {
  border-left: 3px solid var(--pourbaix-composition-edge);
  background: var(--pourbaix-card-bg);
  box-sizing: border-box;
  align-self: stretch;
  padding: 7px 10px 8px;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 5px;
  min-height: 0;
  overflow: hidden;
}

.composition-header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) max-content;
  gap: 6px;
  align-items: center;
}

.coordinate-readout {
  color: var(--pourbaix-text-strong);
  font-size: 0.68rem;
  font-variant-numeric: tabular-nums;
  font-weight: 800;
  line-height: 1.15;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.unit-toggle {
  min-width: 38px;
  height: 22px;
  border: 1px solid var(--pourbaix-panel-border);
  border-radius: 5px;
  background: var(--pourbaix-button-bg);
  color: var(--pourbaix-accent-text);
  font-size: 0.62rem;
  font-weight: 800;
  line-height: 1;
  padding: 0 5px;
  box-shadow: 0 1px 2px color-mix(in srgb, var(--pourbaix-frame) 24%, transparent);
}

.composition-list {
  display: grid;
  gap: 4px;
  align-content: start;
  min-height: 0;
  overflow: visible;
}

.composition-row {
  display: grid;
  grid-template-columns: 11px minmax(0, 1fr) max-content;
  gap: 6px;
  align-items: center;
  min-height: 16px;
}

.composition-label {
  min-width: 0;
  overflow: hidden;
  color: var(--pourbaix-text);
  font-size: 0.64rem;
  line-height: 1.15;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.composition-value {
  color: var(--pourbaix-accent-text);
  font-size: 0.64rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  line-height: 1.15;
}

.boundary-hitbox {
  fill: none;
  stroke: transparent;
  stroke-width: 14px;
  pointer-events: stroke;
  cursor: pointer;
}

.equation-title {
  margin: 0 0 4px;
  color: var(--pourbaix-text);
  font-size: 0.72rem;
  font-weight: 700;
  line-height: 1.15;
}

.equation,
.equation-note,
.caption {
  margin: 0;
  font-size: 0.64rem;
  line-height: 1.18;
}

.equation {
  color: var(--pourbaix-accent-text);
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  display: -webkit-box;
  overflow-wrap: anywhere;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.equation-note,
.caption {
  color: var(--pourbaix-text-muted);
  display: -webkit-box;
  overflow-wrap: anywhere;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.axis-tick {
  fill: var(--pourbaix-text-muted);
  font-size: 12px;
}

.axis-label {
  fill: var(--pourbaix-text-strong);
  font-size: 14px;
  font-weight: 700;
}

.region-label {
  font-size: 17px;
  font-weight: 700;
  paint-order: stroke;
  stroke: var(--pourbaix-region-label-halo);
  stroke-width: 3px;
}

@media (max-width: 900px) {
  .pourbaix-shell {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
  }

  .chart-panel {
    aspect-ratio: 760 / 430;
    height: auto;
  }

  .control-panel {
    height: auto;
  }
}
</style>

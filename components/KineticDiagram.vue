<script setup>
import { useDarkMode } from '@slidev/client'
import { computed, onMounted, ref, watch } from 'vue'
import pourbaixData from '../data/chlorine_pourbaix.json'
import kineticModel from '../data/chlorine_kinetic_model.json'

const width = 760
const height = 430
const margin = { top: 24, right: 30, bottom: 52, left: 60 }
const plotWidth = width - margin.left - margin.right
const plotHeight = height - margin.top - margin.bottom

const pHMin = pourbaixData.axes.pH.min
const pHMax = pourbaixData.axes.pH.max
const eMin = pourbaixData.axes.E.min
const eMax = pourbaixData.axes.E.max
const logCAxis = pourbaixData.axes.logC ?? {}
const temperatureAxis = pourbaixData.axes.temperatureC ?? {}
const logCMin = logCAxis.min ?? -6
const logCMax = logCAxis.max ?? 0
const logCStep = 0.1
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
const temperatureMin = temperatureAxis.min ?? temperatureData[0]?.temperatureC ?? fallbackTemperatureC
const temperatureMax =
  temperatureAxis.max ?? temperatureData[temperatureData.length - 1]?.temperatureC ?? fallbackTemperatureC
const temperatureStep =
  temperatureAxis.step ?? (temperatureData[1]?.temperatureC - temperatureData[0]?.temperatureC || 1)
const logTimeAxis = kineticModel.controls?.logTimeSeconds ?? {}
const logTimeMin = logTimeAxis.min ?? 0
const logTimeMax = logTimeAxis.max ?? 7.5
const logTimeStep = logTimeAxis.step ?? 0.05
const defaultLogTime = logTimeAxis.default ?? Math.log10(24 * 60 * 60)
const gridColumns = kineticModel.grid?.pHCount ?? 260
const gridRows = kineticModel.grid?.eCount ?? 220
const pointCount = gridColumns * gridRows
const pHByColumn = Float64Array.from({ length: gridColumns }, (_value, column) => {
  return pHMin + ((column + 0.5) / gridColumns) * (pHMax - pHMin)
})
const eByRow = Float64Array.from({ length: gridRows }, (_value, row) => {
  return eMax - ((row + 0.5) / gridRows) * (eMax - eMin)
})
const xTicks = [0, 2, 4, 6, 8, 10, 12, 14]
const yTicks = [-0.8, -0.4, 0, 0.4, 0.8, 1.2, 1.6, 2.0]
const boundaryIds = ['water_o2_h2o', 'water_h2_h2o', 'ocl_cl', 'clo3_cl', 'clo4_cl']
const fastSpeciesIds = kineticModel.fastSpecies ?? ['cl_minus', 'cl2', 'hocl', 'ocl_minus']
const slowSpeciesIds = kineticModel.slowSpecies ?? ['clo3_minus', 'clo4_minus']
const kineticSpecies =
  kineticModel.kineticSpecies ??
  [...fastSpeciesIds, ...slowSpeciesIds]
    .map((id) => pourbaixData.species.find((species) => species.id === id))
    .filter(Boolean)
const kineticSpeciesIds = kineticSpecies.map((species) => species.id)
const speciesIndexById = new Map(kineticSpeciesIds.map((id, index) => [id, index]))
const speciesById = Object.fromEntries(
  [...pourbaixData.species, ...kineticSpecies].map((species) => [species.id, species]),
)
const rateParameters = Object.fromEntries(
  (kineticModel.slowKinetics ?? []).map((entry) => [entry.species, entry]),
)
const chlorateParameters = rateParameters.clo3_minus ?? {
  boundaryId: 'clo3_cl',
  k0PerSecond: 2.0e-5,
  betaPerVolt: 3.5,
}
const perchlorateParameters = rateParameters.clo4_minus ?? {
  boundaryId: 'clo4_cl',
  k0PerSecond: 2.0e-8,
  betaPerVolt: 5.5,
}
const hoclPka = kineticModel.fastEquilibriumParameters?.hoclPka ?? 7.5
const cl2HydrolysisMidpointPH =
  kineticModel.fastEquilibriumParameters?.cl2HydrolysisMidpointPH ?? 3.3
const redoxSigmoidWidthV =
  kineticModel.fastEquilibriumParameters?.redoxSigmoidWidthV ?? 0.08

const fieldImageHref = ref('')
const logTimeSeconds = ref(defaultLogTime)
const logC = ref(kineticModel.controls?.logC?.default ?? pourbaixData.metadata?.staticLogC ?? -3)
const temperatureC = ref(kineticModel.controls?.temperatureC?.default ?? fallbackTemperatureC)
const cursorPoint = ref(null)
const { isDark } = useDarkMode()

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

  const pH = pHFromX(x)
  const e = eFromY(y)
  const column = Math.min(
    gridColumns - 1,
    Math.max(0, Math.floor(((pH - pHMin) / (pHMax - pHMin)) * gridColumns)),
  )
  const row = Math.min(
    gridRows - 1,
    Math.max(0, Math.floor(((eMax - e) / (eMax - eMin)) * gridRows)),
  )

  cursorPoint.value = {
    pH,
    E: e,
    column,
    row,
    index: row * gridColumns + column,
  }
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
  const normalized = String(text ?? '')
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

function activeTemperaturePayload(value) {
  return temperatureData.reduce((closest, entry) => {
    return Math.abs(entry.temperatureC - value) < Math.abs(closest.temperatureC - value)
      ? entry
      : closest
  }, temperatureData[0])
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

function interpolateSlice(lower, upper, t, fields = {}) {
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

  return interpolateSlice(lower, upper, t, { logC: value })
}

function boundaryById(slice, boundaryId) {
  return slice.boundaries.find((boundary) => boundary.id === boundaryId)
}

function potentialAt(boundary, pH) {
  const points = boundary?.points ?? []
  if (points.length === 0) return Number.NaN
  if (pH <= points[0].pH) return points[0].E
  if (pH >= points[points.length - 1].pH) return points[points.length - 1].E

  const upperIndex = points.findIndex((point) => point.pH >= pH)
  const lower = points[upperIndex - 1]
  const upper = points[upperIndex]
  const t = (pH - lower.pH) / (upper.pH - lower.pH)
  return lower.E + (upper.E - lower.E) * t
}

function boundaryPotentialsByColumn(slice, boundaryId) {
  const boundary = boundaryById(slice, boundaryId)
  return Float64Array.from(pHByColumn, (pH) => potentialAt(boundary, pH))
}

function logistic(value, width) {
  const scaled = Math.max(-60, Math.min(60, value / width))
  return 1 / (1 + Math.exp(-scaled))
}

function logTotalChlorineForLambda(relativeLogs, entries, lambda) {
  let total = 0
  for (let index = 0; index < entries.length; index += 1) {
    const count = entries[index].chlorineCount
    total += count * 10 ** (relativeLogs[index] + count * lambda)
  }
  return Math.log10(total)
}

function solveMassBalanceLambda(relativeLogs, entries, selectedLogC) {
  let lower = -200
  let upper = 200

  for (let index = 0; index < 12 && logTotalChlorineForLambda(relativeLogs, entries, lower) > selectedLogC; index += 1) {
    lower -= 200
  }

  for (let index = 0; index < 12 && logTotalChlorineForLambda(relativeLogs, entries, upper) < selectedLogC; index += 1) {
    upper += 200
  }

  for (let index = 0; index < 54; index += 1) {
    const middle = (lower + upper) / 2
    if (logTotalChlorineForLambda(relativeLogs, entries, middle) < selectedLogC) {
      lower = middle
    } else {
      upper = middle
    }
  }

  return (lower + upper) / 2
}

function buildCompositionEntries(model) {
  return (model?.species ?? []).map((entry) => ({
    ...entry,
    chlorineCount: Number(entry.chlorineCount),
  }))
}

function buildBaseArrays(selectedTemperatureC, selectedLogC) {
  const temperaturePayload = activeTemperaturePayload(selectedTemperatureC)
  const slice = sliceForLogC(temperaturePayload.slices, selectedLogC)
  const compositionEntries = buildCompositionEntries(temperaturePayload.compositionModel)
  const oclBoundaryE = boundaryPotentialsByColumn(slice, 'ocl_cl')
  const clo3BoundaryE = boundaryPotentialsByColumn(slice, chlorateParameters.boundaryId)
  const clo4BoundaryE = boundaryPotentialsByColumn(slice, perchlorateParameters.boundaryId)
  const slowCapacity = new Float32Array(pointCount)
  const perchlorateShare = new Float32Array(pointCount)
  const k3 = new Float32Array(pointCount)
  const k4 = new Float32Array(pointCount)
  const fastAlpha = Object.fromEntries(
    fastSpeciesIds.map((speciesId) => [speciesId, new Float32Array(pointCount)]),
  )
  const relativeLogs = new Array(compositionEntries.length)
  const slowEntryIndexes = {
    clo3_minus: compositionEntries.findIndex((entry) => entry.id === 'clo3_minus'),
    clo4_minus: compositionEntries.findIndex((entry) => entry.id === 'clo4_minus'),
  }
  const logCScale = 10 ** (-selectedLogC)

  for (let row = 0; row < gridRows; row += 1) {
    const e = eByRow[row]
    for (let column = 0; column < gridColumns; column += 1) {
      const index = row * gridColumns + column
      const pH = pHByColumn[column]

      for (let entryIndex = 0; entryIndex < compositionEntries.length; entryIndex += 1) {
        const coefficients = compositionEntries[entryIndex].coefficients
        relativeLogs[entryIndex] =
          coefficients.constant +
          coefficients.pH * pH +
          coefficients.E * e +
          coefficients.logC * selectedLogC
      }

      const lambda = solveMassBalanceLambda(relativeLogs, compositionEntries, selectedLogC)
      const chlorateAlpha =
        slowEntryIndexes.clo3_minus >= 0
          ? compositionEntries[slowEntryIndexes.clo3_minus].chlorineCount *
            10 ** (
              relativeLogs[slowEntryIndexes.clo3_minus] +
              compositionEntries[slowEntryIndexes.clo3_minus].chlorineCount * lambda
            ) *
            logCScale
          : 0
      const perchlorateAlpha =
        slowEntryIndexes.clo4_minus >= 0
          ? compositionEntries[slowEntryIndexes.clo4_minus].chlorineCount *
            10 ** (
              relativeLogs[slowEntryIndexes.clo4_minus] +
              compositionEntries[slowEntryIndexes.clo4_minus].chlorineCount * lambda
            ) *
            logCScale
          : 0
      const capacity = Math.min(1, Math.max(0, chlorateAlpha + perchlorateAlpha))
      slowCapacity[index] = capacity
      perchlorateShare[index] = capacity > 1e-12 ? perchlorateAlpha / capacity : 0

      const activeDrive = logistic(e - oclBoundaryE[column], redoxSigmoidWidthV)
      const cl2Share = 0.35 / (1 + 10 ** (pH - cl2HydrolysisMidpointPH))
      const hoclShare = 1 / (1 + 10 ** (pH - hoclPka))
      fastAlpha.cl_minus[index] = 1 - activeDrive
      fastAlpha.cl2[index] = activeDrive * cl2Share
      fastAlpha.hocl[index] = activeDrive * (1 - cl2Share) * hoclShare
      fastAlpha.ocl_minus[index] = activeDrive * (1 - cl2Share) * (1 - hoclShare)

      const chlorateOverpotential = Math.max(e - clo3BoundaryE[column], 0)
      const perchlorateOverpotential = Math.max(e - clo4BoundaryE[column], 0)
      k3[index] =
        chlorateParameters.k0PerSecond *
        Math.exp(chlorateParameters.betaPerVolt * chlorateOverpotential)
      k4[index] =
        perchlorateParameters.k0PerSecond *
        Math.exp(perchlorateParameters.betaPerVolt * perchlorateOverpotential)
    }
  }

  return {
    key: `${temperaturePayload.temperatureC}:${selectedLogC.toFixed(2)}`,
    temperatureC: temperaturePayload.temperatureC,
    logC: selectedLogC,
    slice,
    fastAlpha,
    slowCapacity,
    perchlorateShare,
    k3,
    k4,
  }
}

function chainFractions(k3, k4, seconds) {
  let fast = Math.exp(-k3 * seconds)
  let chlorate = 0

  if (Math.abs(k4 - k3) < 1e-20) {
    chlorate = k3 * seconds * Math.exp(-k3 * seconds)
  } else {
    chlorate = (k3 / (k4 - k3)) * (Math.exp(-k3 * seconds) - Math.exp(-k4 * seconds))
  }

  let perchlorate = 1 - fast - chlorate
  fast = Math.min(1, Math.max(0, fast))
  chlorate = Math.min(1, Math.max(0, chlorate))
  perchlorate = Math.min(1, Math.max(0, perchlorate))
  const total = fast + chlorate + perchlorate
  if (total > 1) {
    chlorate /= total
    perchlorate /= total
    fast = 1 - chlorate - perchlorate
  }
  return { chlorate, perchlorate }
}

function buildKineticFrame(base, seconds) {
  const classification = new Uint8Array(pointCount)
  const fractionArrays = kineticSpeciesIds.map(() => new Float32Array(pointCount))
  const chlorateIndex = speciesIndexById.get('clo3_minus')
  const perchlorateIndex = speciesIndexById.get('clo4_minus')

  for (let index = 0; index < pointCount; index += 1) {
    const chain = chainFractions(base.k3[index], base.k4[index], seconds)
    const capacity = base.slowCapacity[index]
    const share = base.perchlorateShare[index]
    const perchlorate = Math.min(1, Math.max(0, capacity * chain.perchlorate * share))
    const chlorate = Math.min(
      1,
      Math.max(0, capacity * (chain.chlorate + chain.perchlorate * (1 - share))),
    )
    const fastRemainder = Math.min(1, Math.max(0, 1 - chlorate - perchlorate))
    let bestIndex = 0
    let bestValue = -1

    for (const speciesId of fastSpeciesIds) {
      const speciesIndex = speciesIndexById.get(speciesId)
      if (speciesIndex === undefined) continue
      const value = fastRemainder * base.fastAlpha[speciesId][index]
      fractionArrays[speciesIndex][index] = value
      if (value > bestValue) {
        bestIndex = speciesIndex
        bestValue = value
      }
    }

    if (chlorateIndex !== undefined) {
      fractionArrays[chlorateIndex][index] = chlorate
      if (chlorate > bestValue) {
        bestIndex = chlorateIndex
        bestValue = chlorate
      }
    }

    if (perchlorateIndex !== undefined) {
      fractionArrays[perchlorateIndex][index] = perchlorate
      if (perchlorate > bestValue) {
        bestIndex = perchlorateIndex
      }
    }

    classification[index] = bestIndex
  }

  return {
    base,
    seconds,
    classification,
    fractionArrays,
  }
}

const seconds = computed(() => 10 ** logTimeSeconds.value)
const baseArrays = computed(() => buildBaseArrays(temperatureC.value, logC.value))
const kineticFrame = computed(() => buildKineticFrame(baseArrays.value, seconds.value))
const currentSlice = computed(() => baseArrays.value.slice)
const overlayBoundaries = computed(() => {
  return boundaryIds
    .map((boundaryId) => boundaryById(currentSlice.value, boundaryId))
    .filter((boundary) => boundary?.points?.length >= 2)
})
const labelPositions = computed(() => {
  const counts = new Array(kineticSpeciesIds.length).fill(0)
  const pHSums = new Array(kineticSpeciesIds.length).fill(0)
  const eSums = new Array(kineticSpeciesIds.length).fill(0)
  const minCells = Math.max(60, pointCount * 0.012)

  for (let row = 0; row < gridRows; row += 1) {
    const e = eByRow[row]
    for (let column = 0; column < gridColumns; column += 1) {
      const index = row * gridColumns + column
      const speciesIndex = kineticFrame.value.classification[index]
      counts[speciesIndex] += 1
      pHSums[speciesIndex] += pHByColumn[column]
      eSums[speciesIndex] += e
    }
  }

  return kineticSpeciesIds
    .map((speciesId, index) => {
      if (counts[index] < minCells) return null
      return {
        species: speciesById[speciesId],
        pH: pHSums[index] / counts[index],
        E: eSums[index] / counts[index],
      }
    })
    .filter(Boolean)
})
const hoverRows = computed(() => {
  if (!cursorPoint.value) return []
  return kineticSpeciesIds
    .map((speciesId, speciesIndex) => ({
      species: speciesById[speciesId],
      fraction: kineticFrame.value.fractionArrays[speciesIndex][cursorPoint.value.index] ?? 0,
      dominant: kineticFrame.value.classification[cursorPoint.value.index] === speciesIndex,
    }))
    .sort((first, second) => Number(second.dominant) - Number(first.dominant))
})
const dominantHoverSpecies = computed(() => {
  if (!cursorPoint.value) return null
  const speciesIndex = kineticFrame.value.classification[cursorPoint.value.index]
  return speciesById[kineticSpeciesIds[speciesIndex]]
})

function formatPath(points) {
  return points.map((point) => `${xScale(point.pH).toFixed(2)},${yScale(point.E).toFixed(2)}`).join(' ')
}

function boundaryDashArray(boundary) {
  if (boundary.kind === 'water') return '7 6'
  if (boundary.id === 'clo3_cl') return '3 5'
  if (boundary.id === 'clo4_cl') return '9 4 2 4'
  return '4 4'
}

function hexToRgb(hex) {
  const normalized = hex.replace('#', '')
  return {
    r: parseInt(normalized.slice(0, 2), 16),
    g: parseInt(normalized.slice(2, 4), 16),
    b: parseInt(normalized.slice(4, 6), 16),
  }
}

function mixRgb(foreground, background, amount) {
  return {
    r: Math.round(background.r + (foreground.r - background.r) * amount),
    g: Math.round(background.g + (foreground.g - background.g) * amount),
    b: Math.round(background.b + (foreground.b - background.b) * amount),
  }
}

function drawField() {
  if (typeof document === 'undefined') return

  const canvas = document.createElement('canvas')

  canvas.width = gridColumns
  canvas.height = gridRows
  const context = canvas.getContext('2d')
  if (!context) return

  context.imageSmoothingEnabled = false
  const image = context.createImageData(gridColumns, gridRows)
  const background = hexToRgb(isDark.value ? '#101820' : '#fbfaf6')
  const palette = kineticSpecies.map((species) =>
    mixRgb(hexToRgb(species.color), background, isDark.value ? 0.52 : 0.34),
  )

  for (let index = 0; index < pointCount; index += 1) {
    const color = palette[kineticFrame.value.classification[index]]
    const pixel = index * 4
    image.data[pixel] = color.r
    image.data[pixel + 1] = color.g
    image.data[pixel + 2] = color.b
    image.data[pixel + 3] = 255
  }

  context.putImageData(image, 0, 0)
  fieldImageHref.value = canvas.toDataURL('image/png')
}

function formatTemperature(value) {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '25 C'
  return `${Number.isInteger(numericValue) ? numericValue.toFixed(0) : numericValue.toFixed(1)} C`
}

function formatLogTime(value) {
  return value.toFixed(2)
}

function formatTime(value) {
  if (value < 60) return `${value.toPrecision(2)} s`
  if (value < 3600) return `${(value / 60).toPrecision(2)} min`
  if (value < 86400) return `${(value / 3600).toPrecision(2)} h`
  if (value < 365.25 * 86400) return `${(value / 86400).toPrecision(2)} d`
  return `${(value / (365.25 * 86400)).toPrecision(2)} yr`
}

function formatPercent(value) {
  if (value > 0 && value < 0.0001) return '<0.01%'
  if (value >= 0.1) return `${(value * 100).toFixed(1)}%`
  return `${(value * 100).toFixed(2)}%`
}

function setTimePreset(timeDef) {
  logTimeSeconds.value = Math.min(logTimeMax, Math.max(logTimeMin, Math.log10(timeDef.seconds)))
}

onMounted(drawField)
watch(
  () => [kineticFrame.value, isDark.value],
  () => drawField(),
  { flush: 'post' },
)
</script>

<template>
  <div class="kinetic-shell" :class="{ 'is-dark': isDark }">
    <div class="diagram-column">
      <div class="chart-panel">
        <div class="plot-stack">
          <svg
            :viewBox="`0 0 ${width} ${height}`"
            preserveAspectRatio="xMidYMin meet"
            role="img"
            aria-label="Interactive kinetically constrained chlorine diagram"
            @mousemove="updateCursorPoint"
            @mouseleave="cursorPoint = null"
          >
            <image
              v-if="fieldImageHref"
              :href="fieldImageHref"
              :x="margin.left"
              :y="margin.top"
              :width="plotWidth"
              :height="plotHeight"
              preserveAspectRatio="none"
            />

            <rect
              :x="margin.left"
              :y="margin.top"
              :width="plotWidth"
              :height="plotHeight"
              class="plot-area-frame"
            />

            <g v-for="tick in xTicks" :key="`x-${tick}`">
              <line
                :x1="xScale(tick)"
                :x2="xScale(tick)"
                :y1="margin.top"
                :y2="margin.top + plotHeight"
                class="grid-line"
              />
              <text :x="xScale(tick)" :y="height - 20" text-anchor="middle" class="axis-tick">
                {{ tick }}
              </text>
            </g>

            <g v-for="tick in yTicks" :key="`y-${tick}`">
              <line
                :x1="margin.left"
                :x2="margin.left + plotWidth"
                :y1="yScale(tick)"
                :y2="yScale(tick)"
                class="grid-line"
              />
              <text :x="margin.left - 12" :y="yScale(tick) + 4" text-anchor="end" class="axis-tick">
                {{ tick.toFixed(1) }}
              </text>
            </g>

            <polyline
              v-for="boundary in overlayBoundaries"
              :key="boundary.id"
              :points="formatPath(boundary.points)"
              fill="none"
              :stroke="boundary.color"
              stroke-width="2.35"
              :stroke-dasharray="boundaryDashArray(boundary)"
              stroke-linecap="round"
              class="reference-boundary"
            />

            <text
              v-for="label in labelPositions"
              :key="label.species.id"
              :x="xScale(label.pH)"
              :y="yScale(label.E)"
              :fill="label.species.color"
              class="region-label"
            >
              <tspan
                v-for="(segment, index) in chemicalSegments(label.species.label)"
                :key="`${label.species.id}-label-${index}`"
                :baseline-shift="svgBaselineShift(segment.kind)"
                :font-size="svgFontSize(segment.kind)"
              >
                {{ segment.text }}
              </tspan>
            </text>

            <g v-if="cursorPoint" class="cursor-marker">
              <line
                :x1="xScale(cursorPoint.pH)"
                :x2="xScale(cursorPoint.pH)"
                :y1="margin.top"
                :y2="margin.top + plotHeight"
              />
              <line
                :x1="margin.left"
                :x2="margin.left + plotWidth"
                :y1="yScale(cursorPoint.E)"
                :y2="yScale(cursorPoint.E)"
              />
              <circle :cx="xScale(cursorPoint.pH)" :cy="yScale(cursorPoint.E)" r="4.4" />
            </g>

            <line
              :x1="margin.left"
              :x2="margin.left + plotWidth"
              :y1="margin.top + plotHeight"
              :y2="margin.top + plotHeight"
              class="axis-frame"
            />
            <line
              :x1="margin.left"
              :x2="margin.left"
              :y1="margin.top"
              :y2="margin.top + plotHeight"
              class="axis-frame"
            />
            <text :x="margin.left + plotWidth / 2" :y="height - 2" text-anchor="middle" class="axis-label">
              pH
            </text>
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
      </div>

      <div class="control-grid">
        <div class="chart-control-card time-card">
          <label for="kinetic-log-time">log<sub>10</sub> t</label>
          <input
            id="kinetic-log-time"
            v-model.number="logTimeSeconds"
            type="range"
            :min="logTimeMin"
            :max="logTimeMax"
            :step="logTimeStep"
          />
          <output>{{ formatLogTime(logTimeSeconds) }} / {{ formatTime(seconds) }}</output>
        </div>
        <div class="chart-control-card">
          <label for="kinetic-log-c">log<sub>10</sub> Total Cl</label>
          <input
            id="kinetic-log-c"
            v-model.number="logC"
            type="range"
            :min="logCMin"
            :max="logCMax"
            :step="logCStep"
          />
          <output>{{ logC.toFixed(1) }}</output>
        </div>
        <div class="chart-control-card">
          <label for="kinetic-temperature">Temp</label>
          <input
            id="kinetic-temperature"
            v-model.number="temperatureC"
            type="range"
            :min="temperatureMin"
            :max="temperatureMax"
            :step="temperatureStep"
          />
          <output>{{ formatTemperature(temperatureC) }}</output>
        </div>
      </div>
    </div>

    <aside class="kinetic-panel">
      <div class="time-presets">
        <button
          v-for="timeDef in kineticModel.timeSlices"
          :key="timeDef.label"
          type="button"
          :class="{ active: Math.abs(logTimeSeconds - Math.log10(timeDef.seconds)) < 0.03 }"
          @click="setTimePreset(timeDef)"
        >
          {{ timeDef.label }}
        </button>
      </div>

      <div class="readout-card">
        <p class="readout-title">
          <span v-if="cursorPoint">
            pH {{ cursorPoint.pH.toFixed(2) }} / E {{ cursorPoint.E.toFixed(2) }} V
          </span>
          <span v-else>No plot point</span>
        </p>
        <p class="readout-dominant">
          <span v-if="dominantHoverSpecies">
            Dominant:
            <template
              v-for="(segment, index) in chemicalSegments(dominantHoverSpecies.label)"
              :key="`dominant-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </span>
          <span v-else>{{ formatTime(seconds) }}</span>
        </p>
      </div>

      <div class="fraction-list">
        <div v-for="row in hoverRows" :key="row.species.id" class="fraction-row">
          <span class="swatch" :style="{ backgroundColor: row.species.color }"></span>
          <span class="fraction-label">
            <template
              v-for="(segment, index) in chemicalSegments(row.species.label)"
              :key="`${row.species.id}-fraction-${index}`"
            >
              <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
              <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
              <span v-else>{{ segment.text }}</span>
            </template>
          </span>
          <span class="fraction-value">{{ formatPercent(row.fraction) }}</span>
        </div>
        <div v-if="hoverRows.length === 0" class="legend-list">
          <div v-for="species in kineticSpecies" :key="species.id" class="fraction-row">
            <span class="swatch" :style="{ backgroundColor: species.color }"></span>
            <span class="fraction-label">
              <template
                v-for="(segment, index) in chemicalSegments(species.label)"
                :key="`${species.id}-legend-${index}`"
              >
                <sub v-if="segment.kind === 'sub'" class="chem-sub">{{ segment.text }}</sub>
                <sup v-else-if="segment.kind === 'sup'" class="chem-sup">{{ segment.text }}</sup>
                <span v-else>{{ segment.text }}</span>
              </template>
            </span>
          </div>
        </div>
      </div>

      <p class="warning-note">{{ kineticModel.warning }}</p>
    </aside>
  </div>
</template>

<style scoped>
.kinetic-shell {
  --kinetic-surface: #ffffff;
  --kinetic-border: rgba(38, 50, 56, 0.14);
  --kinetic-shadow: 0 12px 30px rgba(38, 50, 56, 0.08);
  --kinetic-plot-bg: #fbfaf6;
  --kinetic-grid: rgba(93, 101, 110, 0.19);
  --kinetic-frame: #455a64;
  --kinetic-text: #37474f;
  --kinetic-strong: #111827;
  --kinetic-muted: #607d8b;
  --kinetic-card: #f7f9fb;
  --kinetic-track: #e5e7eb;
  --kinetic-thumb: #6b7280;
  --kinetic-cursor: #172554;
  --kinetic-label-halo: #ffffff;
  --kinetic-swatch-border: rgba(0, 0, 0, 0.12);
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 252px);
  gap: 12px;
  align-items: stretch;
  height: clamp(360px, 50vh, 430px);
  max-height: calc(100vh - 160px);
  margin-top: 8px;
  min-height: 0;
  color: var(--kinetic-text);
}

.kinetic-shell.is-dark {
  --kinetic-surface: #111827;
  --kinetic-border: rgba(148, 163, 184, 0.26);
  --kinetic-shadow: 0 14px 34px rgba(0, 0, 0, 0.32);
  --kinetic-plot-bg: #101820;
  --kinetic-grid: rgba(203, 213, 225, 0.18);
  --kinetic-frame: #cbd5e1;
  --kinetic-text: #dbeafe;
  --kinetic-strong: #f8fafc;
  --kinetic-muted: #94a3b8;
  --kinetic-card: #172033;
  --kinetic-track: #334155;
  --kinetic-thumb: #cbd5e1;
  --kinetic-cursor: #dbeafe;
  --kinetic-label-halo: #0f172a;
  --kinetic-swatch-border: rgba(248, 250, 252, 0.34);
}

.diagram-column {
  display: grid;
  grid-template-rows: minmax(0, 1fr) auto;
  gap: 8px;
  min-height: 0;
}

.chart-panel,
.kinetic-panel,
.chart-control-card,
.readout-card,
.time-presets button {
  border: 1px solid var(--kinetic-border);
  border-radius: 8px;
  background: var(--kinetic-surface);
  box-shadow: var(--kinetic-shadow);
}

.chart-panel {
  box-sizing: border-box;
  height: 100%;
  padding: 8px;
  overflow: hidden;
  display: grid;
  place-items: center;
}

.plot-stack {
  position: relative;
  width: 100%;
  height: 100%;
}

.plot-stack svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
}

.plot-area-frame {
  fill: transparent;
  stroke: color-mix(in srgb, var(--kinetic-frame) 28%, transparent);
  stroke-width: 1.2;
}

.grid-line {
  stroke: var(--kinetic-grid);
  stroke-width: 1;
}

.axis-frame {
  stroke: var(--kinetic-frame);
  stroke-width: 1.5;
}

.axis-label,
.axis-tick {
  fill: var(--kinetic-frame);
  font-weight: 650;
}

.axis-label {
  font-size: 15px;
}

.axis-tick {
  font-size: 12px;
}

.reference-boundary {
  opacity: 0.86;
}

.region-label {
  paint-order: stroke;
  stroke: var(--kinetic-label-halo);
  stroke-width: 5px;
  stroke-linejoin: round;
  font-size: 17px;
  font-weight: 800;
  text-anchor: middle;
  dominant-baseline: middle;
}

.cursor-marker line {
  stroke: var(--kinetic-cursor);
  stroke-width: 1.1;
  stroke-dasharray: 3 4;
  opacity: 0.56;
}

.cursor-marker circle {
  fill: var(--kinetic-surface);
  stroke: var(--kinetic-cursor);
  stroke-width: 2;
}

.control-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr) minmax(0, 0.9fr);
  gap: 8px;
}

.chart-control-card {
  box-sizing: border-box;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 72px;
  align-items: center;
  gap: 8px;
  min-width: 0;
  min-height: 46px;
  padding: 7px 9px;
}

.time-card {
  grid-template-columns: max-content minmax(0, 1fr) 112px;
}

.chart-control-card label {
  color: var(--kinetic-strong);
  font-size: 0.72rem;
  font-weight: 700;
  white-space: nowrap;
}

.chart-control-card input[type="range"] {
  min-width: 0;
  accent-color: var(--kinetic-thumb);
}

.chart-control-card output {
  color: var(--kinetic-muted);
  font-size: 0.68rem;
  font-weight: 700;
  text-align: right;
  white-space: nowrap;
}

.kinetic-panel {
  box-sizing: border-box;
  height: 100%;
  padding: 8px 10px 9px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.time-presets {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
}

.time-presets button {
  height: 26px;
  padding: 0;
  color: var(--kinetic-text);
  font-size: 0.68rem;
  font-weight: 750;
}

.time-presets button.active {
  border-color: color-mix(in srgb, #2f6fba 70%, transparent);
  background: color-mix(in srgb, #2f6fba 14%, var(--kinetic-surface));
  color: var(--kinetic-strong);
}

.readout-card {
  box-sizing: border-box;
  padding: 8px 9px;
  background: var(--kinetic-card);
  box-shadow: none;
}

.readout-card p {
  margin: 0;
}

.readout-title {
  color: var(--kinetic-muted);
  font-size: 0.69rem;
  font-weight: 700;
}

.readout-dominant {
  color: var(--kinetic-strong);
  font-size: 0.82rem;
  font-weight: 800;
  line-height: 1.35;
}

.fraction-list {
  min-height: 0;
  overflow: hidden;
  display: grid;
  gap: 4px;
}

.legend-list {
  display: grid;
  gap: 4px;
}

.fraction-row {
  display: grid;
  grid-template-columns: 12px minmax(0, 1fr) max-content;
  align-items: center;
  gap: 6px;
  min-height: 21px;
  color: var(--kinetic-text);
  font-size: 0.72rem;
  font-weight: 700;
}

.legend-list .fraction-row {
  grid-template-columns: 12px minmax(0, 1fr);
}

.swatch {
  width: 10px;
  height: 10px;
  border: 1px solid var(--kinetic-swatch-border);
  border-radius: 50%;
}

.fraction-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.fraction-value {
  color: var(--kinetic-muted);
  font-variant-numeric: tabular-nums;
}

.warning-note {
  margin: auto 0 0;
  padding-top: 6px;
  border-top: 1px solid var(--kinetic-border);
  color: var(--kinetic-muted);
  font-size: 0.59rem;
  font-weight: 650;
  line-height: 1.22;
}

.chem-sub,
.chem-sup {
  font-size: 0.72em;
  line-height: 0;
}

@media (max-width: 900px) {
  .kinetic-shell {
    grid-template-columns: 1fr;
    height: auto;
    max-height: none;
  }

  .chart-panel {
    height: 52vh;
  }

  .kinetic-panel {
    max-height: 230px;
  }
}
</style>

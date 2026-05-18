from __future__ import annotations

import numpy as np

from .chemistry import boundary_points, boundary_potential, boundary_region_species
from .config import (
    ACTIVE_SEGMENT_MAX_BRIDGED_GAP,
    ACTIVE_SEGMENT_SAMPLE_MULTIPLIERS,
    DERIVED_CL2_CL_BOUNDARY_ID,
    GEOMETRY_EPSILON,
    REGION_AREA_MIN,
    REGION_E_STEP,
    SPECIES,
)


def polygon_area(points: list[tuple[float, float]]) -> float:
    if len(points) < 3:
        return 0.0

    area = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        area += x0 * y1 - x1 * y0
    return area / 2

def polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    area = polygon_area(points)
    if abs(area) < GEOMETRY_EPSILON:
        x_values = [point[0] for point in points]
        y_values = [point[1] for point in points]
        return sum(x_values) / len(points), sum(y_values) / len(points)

    cx = 0.0
    cy = 0.0
    for index, (x0, y0) in enumerate(points):
        x1, y1 = points[(index + 1) % len(points)]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross

    factor = 1 / (6 * area)
    return cx * factor, cy * factor

def redox_edges(boundary_defs: list[dict]) -> list[dict]:
    edges = []
    known_species = {species["id"] for species in SPECIES}

    for defn in boundary_defs:
        boundary_species = boundary_region_species(defn)
        if (
            defn.get("kind") == "water"
            or defn.get("regionReference")
            or len(boundary_species) != 2
        ):
            continue
        if any(species not in known_species for species in boundary_species):
            continue
        if boundary_species[0] == boundary_species[1]:
            continue

        edges.append(
            {
                "high": boundary_species[0],
                "low": boundary_species[1],
                "electronCount": float(defn["electronCount"]),
                "definition": defn,
            }
        )

    return edges

def active_region_pairs(
    classification: np.ndarray,
    species_ids: list[str],
) -> set[tuple[str, str]]:
    pairs = set()

    row_pairs = classification[:, :-1] != classification[:, 1:]
    left_rows, left_columns = np.where(row_pairs)
    for row, column in zip(left_rows, left_columns):
        first = species_ids[int(classification[row, column])]
        second = species_ids[int(classification[row, column + 1])]
        pairs.add(tuple(sorted((first, second))))

    column_pairs = classification[:-1, :] != classification[1:, :]
    upper_rows, upper_columns = np.where(column_pairs)
    for row, column in zip(upper_rows, upper_columns):
        first = species_ids[int(classification[row, column])]
        second = species_ids[int(classification[row + 1, column])]
        pairs.add(tuple(sorted((first, second))))

    return pairs

def grid_species_at_point(
    ph: float,
    e: float,
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
) -> str | None:
    if ph < ph_edges[0] or ph >= ph_edges[-1]:
        return None
    if e < e_edges[0] or e >= e_edges[-1]:
        return None

    column = int(np.searchsorted(ph_edges, ph, side="right") - 1)
    row = int(np.searchsorted(e_edges, e, side="right") - 1)
    if row < 0 or row >= classification.shape[0]:
        return None
    if column < 0 or column >= classification.shape[1]:
        return None

    return species_ids[int(classification[row, column])]

def boundary_segment_is_active(
    defn: dict,
    ph: float,
    e: float,
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
) -> bool:
    expected_pair = tuple(sorted(boundary_region_species(defn)))

    for multiplier in ACTIVE_SEGMENT_SAMPLE_MULTIPLIERS:
        delta_e = REGION_E_STEP * multiplier
        upper_species = grid_species_at_point(
            ph, e + delta_e, classification, ph_edges, e_edges, species_ids
        )
        lower_species = grid_species_at_point(
            ph, e - delta_e, classification, ph_edges, e_edges, species_ids
        )
        if upper_species is None or lower_species is None:
            continue
        if tuple(sorted((upper_species, lower_species))) == expected_pair:
            return True

    return False

def segments_from_active_flags(
    points: list[dict[str, float]],
    active_flags: list[bool],
) -> list[dict]:
    segments = []
    start_index: int | None = None

    for index, is_active in enumerate(active_flags):
        if is_active and start_index is None:
            start_index = index
        elif not is_active and start_index is not None:
            segments.append({"points": points[start_index : index + 1]})
            start_index = None

    if start_index is not None:
        segments.append({"points": points[start_index : len(active_flags) + 1]})

    return segments

def bridge_short_inactive_gaps(active_flags: list[bool]) -> list[bool]:
    if ACTIVE_SEGMENT_MAX_BRIDGED_GAP <= 0:
        return active_flags

    bridged_flags = active_flags[:]
    index = 0
    while index < len(active_flags):
        if active_flags[index]:
            index += 1
            continue

        gap_start = index
        while index < len(active_flags) and not active_flags[index]:
            index += 1
        gap_end = index
        gap_length = gap_end - gap_start
        has_active_before = gap_start > 0 and active_flags[gap_start - 1]
        has_active_after = gap_end < len(active_flags) and active_flags[gap_end]
        if (
            has_active_before
            and has_active_after
            and gap_length <= ACTIVE_SEGMENT_MAX_BRIDGED_GAP
        ):
            for gap_index in range(gap_start, gap_end):
                bridged_flags[gap_index] = True

    return bridged_flags

def active_segments_for_boundary(
    defn: dict,
    log_c: float,
    nernst_factor: float,
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
) -> list[dict]:
    region_species = boundary_region_species(defn)
    if defn.get("kind") == "water" or defn.get("plotBoundary") is False:
        return []
    if defn.get("regionReference") or len(region_species) != 2:
        return []
    if region_species[0] == region_species[1]:
        return []

    points = boundary_points(defn, log_c, nernst_factor)
    active_flags = []
    for left_point, right_point in zip(points[:-1], points[1:]):
        ph = (left_point["pH"] + right_point["pH"]) / 2
        e = boundary_potential(defn, ph, log_c, nernst_factor)
        active_flags.append(
            boundary_segment_is_active(
                defn, ph, e, classification, ph_edges, e_edges, species_ids
            )
        )

    active_flags = bridge_short_inactive_gaps(active_flags)
    return segments_from_active_flags(points, active_flags)

def active_segments_for_edges(
    edges: list[dict],
    log_c: float,
    nernst_factor: float,
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
) -> dict[str, list[dict]]:
    return {
        edge["definition"]["id"]: active_segments_for_boundary(
            edge["definition"],
            log_c,
            nernst_factor,
            classification,
            ph_edges,
            e_edges,
            species_ids,
        )
        for edge in edges
    }

def simplify_grid_polygon(vertices: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(vertices) < 3:
        return vertices

    changed = True
    simplified = vertices
    while changed and len(simplified) >= 3:
        changed = False
        next_vertices = []
        for index, vertex in enumerate(simplified):
            previous = simplified[index - 1]
            following = simplified[(index + 1) % len(simplified)]
            if previous[0] == vertex[0] == following[0]:
                changed = True
                continue
            if previous[1] == vertex[1] == following[1]:
                changed = True
                continue
            next_vertices.append(vertex)
        simplified = next_vertices

    return simplified

def simplify_grid_polyline(vertices: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if len(vertices) < 3:
        return vertices

    simplified = [vertices[0]]
    for index in range(1, len(vertices) - 1):
        previous = simplified[-1]
        current = vertices[index]
        following = vertices[index + 1]
        if previous[0] == current[0] == following[0]:
            continue
        if previous[1] == current[1] == following[1]:
            continue
        simplified.append(current)
    simplified.append(vertices[-1])
    return simplified

def boundary_loops(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    row_count, column_count = mask.shape
    edge_starts: dict[tuple[int, int], list[tuple[int, int]]] = {}

    def add_edge(start: tuple[int, int], end: tuple[int, int]) -> None:
        edge_starts.setdefault(start, []).append(end)

    for row in range(row_count):
        for column in range(column_count):
            if not mask[row, column]:
                continue

            if row == 0 or not mask[row - 1, column]:
                add_edge((column, row), (column + 1, row))
            if column == column_count - 1 or not mask[row, column + 1]:
                add_edge((column + 1, row), (column + 1, row + 1))
            if row == row_count - 1 or not mask[row + 1, column]:
                add_edge((column + 1, row + 1), (column, row + 1))
            if column == 0 or not mask[row, column - 1]:
                add_edge((column, row + 1), (column, row))

    loops = []
    while edge_starts:
        start = next(iter(edge_starts))
        current = start
        loop = [start]

        while True:
            ends = edge_starts.get(current)
            if not ends:
                break

            next_vertex = ends.pop()
            if not ends:
                del edge_starts[current]

            current = next_vertex
            if current == start:
                break
            loop.append(current)

        if current == start and len(loop) >= 3:
            loops.append(simplify_grid_polygon(loop))

    return loops

def pair_boundary_grid_edges(
    classification: np.ndarray,
    species_ids: list[str],
    species_pair: tuple[str, str],
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    pair = set(species_pair)
    edges = []

    row_pairs = classification[:, :-1] != classification[:, 1:]
    rows, columns = np.where(row_pairs)
    for row, column in zip(rows, columns):
        first = species_ids[int(classification[row, column])]
        second = species_ids[int(classification[row, column + 1])]
        if {first, second} == pair:
            edges.append(((column + 1, row), (column + 1, row + 1)))

    column_pairs = classification[:-1, :] != classification[1:, :]
    rows, columns = np.where(column_pairs)
    for row, column in zip(rows, columns):
        first = species_ids[int(classification[row, column])]
        second = species_ids[int(classification[row + 1, column])]
        if {first, second} == pair:
            edges.append(((column, row + 1), (column + 1, row + 1)))

    return edges

def ordered_grid_edge(
    start: tuple[int, int],
    end: tuple[int, int],
) -> tuple[tuple[int, int], tuple[int, int]]:
    return tuple(sorted((start, end)))

def polylines_from_grid_edges(
    edges: list[tuple[tuple[int, int], tuple[int, int]]],
) -> list[list[tuple[int, int]]]:
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    unused_edges = set()
    for start, end in edges:
        adjacency.setdefault(start, []).append(end)
        adjacency.setdefault(end, []).append(start)
        unused_edges.add(ordered_grid_edge(start, end))

    def trace_from(start: tuple[int, int]) -> list[tuple[int, int]]:
        current = start
        polyline = [current]
        while True:
            next_vertex = None
            for candidate in adjacency.get(current, []):
                edge = ordered_grid_edge(current, candidate)
                if edge in unused_edges:
                    next_vertex = candidate
                    break
            if next_vertex is None:
                break
            unused_edges.remove(ordered_grid_edge(current, next_vertex))
            current = next_vertex
            polyline.append(current)
            if current == start:
                break
        return polyline

    polylines = []
    starts = sorted(
        vertex for vertex, neighbors in adjacency.items() if len(neighbors) != 2
    )
    for start in starts:
        while any(
            ordered_grid_edge(start, candidate) in unused_edges
            for candidate in adjacency.get(start, [])
        ):
            polyline = trace_from(start)
            if len(polyline) >= 2:
                polylines.append(simplify_grid_polyline(polyline))

    while unused_edges:
        start, _end = next(iter(unused_edges))
        polyline = trace_from(start)
        if len(polyline) >= 2:
            polylines.append(simplify_grid_polyline(polyline))

    return polylines

def grid_polyline_points(
    vertices: list[tuple[int, int]],
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
) -> list[dict[str, float]]:
    return [
        {
            "pH": round(float(ph_edges[column]), 4),
            "E": round(float(e_edges[row]), 4),
        }
        for column, row in vertices
    ]

def derived_dominance_boundaries(
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
) -> list[dict]:
    segments = []
    edges = pair_boundary_grid_edges(
        classification, species_ids, ("cl2", "cl_minus")
    )
    for polyline in polylines_from_grid_edges(edges):
        points = grid_polyline_points(polyline, ph_edges, e_edges)
        if len(points) >= 2:
            segments.append({"points": points})

    return [
        {
            "id": DERIVED_CL2_CL_BOUNDARY_ID,
            "kind": "dominance",
            "label": "Cl2(aq) / Cl- dominance boundary",
            "species": ["cl2", "cl_minus"],
            "regionSpecies": ["cl2", "cl_minus"],
            "color": "#7d5fb2",
            "activeRegionBoundary": bool(segments),
            "activeSegments": segments,
            "note": (
                "Extracted from the alpha-dominance grid; not the direct "
                "Cl2(aq) / Cl- Nernst line."
            ),
        }
    ]

def regions_from_classification(
    classification: np.ndarray,
    ph_edges: np.ndarray,
    e_edges: np.ndarray,
    species_ids: list[str],
    log_c: float,
) -> list[dict]:
    regions = []

    for species_index, species_id in enumerate(species_ids):
        mask = classification == species_index
        if not np.any(mask):
            continue

        for component_index, loop in enumerate(boundary_loops(mask)):
            polygon = [
                (float(ph_edges[column]), float(e_edges[row]))
                for column, row in loop
            ]
            area = abs(polygon_area(polygon))
            if area < REGION_AREA_MIN:
                continue

            centroid = polygon_centroid(polygon)
            regions.append(
                {
                    "id": f"region_{species_id}_{component_index}",
                    "species": species_id,
                    "polygon": [
                        {"pH": round(ph, 4), "E": round(e, 4)}
                        for ph, e in polygon
                    ],
                    "label": {
                        "pH": round(centroid[0], 4),
                        "E": round(centroid[1], 4),
                    },
                    "source": "generated-from-mass-balanced-alpha-grid",
                    "logC": log_c,
                    "area": round(area, 4),
                }
            )

    return regions

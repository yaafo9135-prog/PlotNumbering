# Plot Numbering — QGIS plugin
# Copyright (C) 2026 Hamadu Hudu Yaafo
# This file is part of Plot Numbering.
#
# Plot Numbering is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Plot Numbering is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# LICENSE file for details.

import math


ORDER_MODES = [
    ("north_west", "North → South, then West → East"),
    ("north_east", "North → South, then East → West"),
    ("south_west", "South → North, then West → East"),
    ("south_east", "South → North, then East → West"),
    ("west_north", "West → East, then North → South"),
    ("west_south", "West → East, then South → North"),
    ("east_north", "East → West, then North → South"),
    ("east_south", "East → West, then South → North"),
    ("clockwise", "Clockwise around layer extent"),
    ("grid", "Grid / row-column numbering"),
    ("auto_block_grid", "Automatic Block/Grid — short-side first, continuous blocks"),
    ("interactive", "Interactive start point + direction"),
]


def centroid_xy(feature):
    p = feature.geometry().centroid().asPoint()
    return p.x(), p.y()


def sort_features(features, mode, start_point=None, direction_degrees=0):
    feats = [f for f in features if f.hasGeometry() and not f.geometry().isEmpty()]
    if not feats:
        return []

    if mode == "clockwise":
        cx = sum(centroid_xy(f)[0] for f in feats) / len(feats)
        cy = sum(centroid_xy(f)[1] for f in feats) / len(feats)
        return sorted(
            feats,
            key=lambda f: -math.atan2(centroid_xy(f)[1] - cy,
                                      centroid_xy(f)[0] - cx)
        )

    if mode == "interactive":
        if start_point is None:
            return feats
        sx, sy = start_point
        angle = math.radians(direction_degrees)
        ux, uy = math.cos(angle), math.sin(angle)
        vx, vy = -uy, ux
        def key(f):
            x, y = centroid_xy(f)
            dx, dy = x - sx, y - sy
            along = dx * ux + dy * uy
            across = dx * vx + dy * vy
            return (round(across, 6), along)
        return sorted(feats, key=key)

    if mode == "grid":
        return grid_sort(feats)

    if mode == "auto_block_grid":
        return automatic_block_grid_sort(feats)

    if mode.startswith(("north", "south")):
        south = mode.startswith("south")
        east = mode.endswith("east")
        return sorted(
            feats,
            key=lambda f: (
                (-1 if not south else 1) * centroid_xy(f)[1],
                (-1 if not east else 1) * centroid_xy(f)[0]
            )
        )

    east_primary = mode.startswith("east")
    south_secondary = mode.endswith("south")
    return sorted(
        feats,
        key=lambda f: (
            (-1 if not east_primary else 1) * centroid_xy(f)[0],
            (-1 if not south_secondary else 1) * centroid_xy(f)[1]
        )
    )


def _centroid_records(features):
    """Return lightweight (feature, x, y) records for spatial ordering."""
    records = []
    for f in features:
        try:
            x, y = centroid_xy(f)
            if math.isfinite(x) and math.isfinite(y):
                records.append((f, x, y))
        except Exception:
            continue
    return records


def _nearest_neighbor_distances(records):
    """Estimate each feature's local plot spacing.

    QGIS's spatial index is used when available. A small pure-Python fallback
    keeps the algorithm usable in tests and non-QGIS environments.
    """
    n = len(records)
    if n < 2:
        return [0.0] * n, [[] for _ in records]

    distances = [float("inf")] * n
    neighbors = [[] for _ in records]

    try:
        from qgis.core import QgsSpatialIndex, QgsPointXY
        index = QgsSpatialIndex()
        feature_to_index = {}
        for i, (f, _, _) in enumerate(records):
            index.addFeature(f)
            feature_to_index[f.id()] = i

        for i, (_, x, y) in enumerate(records):
            ids = index.nearestNeighbor(QgsPointXY(x, y), 2)
            best = None
            for fid in ids:
                j = feature_to_index.get(fid)
                if j is None or j == i:
                    continue
                dx = records[j][1] - x
                dy = records[j][2] - y
                d2 = dx * dx + dy * dy
                if best is None or d2 < best[0]:
                    best = (d2, j)
            if best is not None:
                distances[i] = math.sqrt(best[0])
                neighbors[i].append(best[1])
        return distances, neighbors
    except Exception:
        # Fallback for tests or unusual QGIS providers.
        for i, (_, x, y) in enumerate(records):
            best_d2 = float("inf")
            best_j = None
            for j, (_, x2, y2) in enumerate(records):
                if i == j:
                    continue
                dx = x2 - x
                dy = y2 - y
                d2 = dx * dx + dy * dy
                if d2 < best_d2:
                    best_d2 = d2
                    best_j = j
            if best_j is not None:
                distances[i] = math.sqrt(best_d2)
                neighbors[i].append(best_j)
        return distances, neighbors


def _automatic_gap_threshold(distances):
    """Find a robust distance separating plot spacing from block gaps."""
    valid = sorted(d for d in distances if math.isfinite(d) and d > 0)
    if not valid:
        return 0.0
    if len(valid) == 1:
        return valid[0] * 3.0

    # A large jump in nearest-neighbour distances is a strong indication that
    # we crossed from normal plot spacing into a gap between blocks.
    start = max(1, int(len(valid) * 0.05))
    end = min(len(valid) - 1, int(len(valid) * 0.95))
    best_ratio = 0.0
    best_i = None
    for i in range(start, end):
        a = valid[i]
        b = valid[i + 1]
        if a <= 0:
            continue
        ratio = b / a
        if ratio > best_ratio:
            best_ratio = ratio
            best_i = i

    if best_i is not None and best_ratio >= 1.8:
        a = valid[best_i]
        b = valid[best_i + 1]
        return math.sqrt(a * b)

    mid = valid[len(valid) // 2]
    return mid * 3.0


def _connected_components(records, neighbors, distances, threshold):
    """Group plots into spatially connected blocks."""
    n = len(records)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    if threshold <= 0:
        return [[records[i][0]] for i in range(n)]

    for i, near in enumerate(neighbors):
        for j in near:
            if distances[i] <= threshold:
                union(i, j)

    groups = {}
    for i, record in enumerate(records):
        groups.setdefault(find(i), []).append(record)
    return [[r[0] for r in group] for group in groups.values()]


def _pca_axes(features):
    """Return major/minor unit vectors for a block of plot centroids.

    For strongly rectangular blocks the bounding-box aspect ratio is a more
    stable indicator of the block direction than PCA.  PCA can become
    ambiguous for small square/near-square blocks (for example a 2x2 block),
    where tiny numerical differences can rotate the axes diagonally and
    produce an order such as 1,3,2,4.  Use the block geometry first and fall
    back to PCA for genuinely rotated/ambiguous shapes.
    """
    pts = [centroid_xy(f) for f in features]
    if len(pts) < 2:
        return (1.0, 0.0), (0.0, 1.0)

    minx = min(x for x, _ in pts)
    maxx = max(x for x, _ in pts)
    miny = min(y for _, y in pts)
    maxy = max(y for _, y in pts)
    span_x = maxx - minx
    span_y = maxy - miny

    # Strongly rectangular blocks: use the long axis directly.  For an
    # exactly square/near-square block, use a deterministic north/south
    # progression; this matches conventional plot-plan reading and avoids
    # diagonal PCA ambiguity.
    if span_x > span_y * 1.15:
        return (1.0, 0.0), (0.0, -1.0)
    if span_y > span_x * 1.15:
        return (0.0, 1.0), (1.0, 0.0)
    if abs(span_x - span_y) <= max(span_x, span_y, 1e-12) * 0.15:
        return (0.0, 1.0), (1.0, 0.0)

    cx = sum(x for x, _ in pts) / len(pts)
    cy = sum(y for _, y in pts) / len(pts)
    xx = sum((x - cx) ** 2 for x, _ in pts)
    yy = sum((y - cy) ** 2 for _, y in pts)
    xy = sum((x - cx) * (y - cy) for x, y in pts)

    # Principal eigenvector of the 2x2 covariance matrix.
    angle = 0.5 * math.atan2(2.0 * xy, xx - yy)
    ux, uy = math.cos(angle), math.sin(angle)
    # Keep the major axis direction deterministic: prefer east/right, and
    # for a vertical axis prefer north/up.
    if abs(ux) >= abs(uy):
        if ux < 0:
            ux, uy = -ux, -uy
    elif uy < 0:
        ux, uy = -ux, -uy
    vx, vy = -uy, ux
    # Orient the minor axis deterministically so across-axis ordering is
    # stable: +X for mostly-horizontal minor axes, +Y for mostly-vertical.
    if abs(vx) >= abs(vy):
        if vx < 0:
            vx, vy = -vx, -vy
    elif vy < 0:
        vx, vy = -vx, -vy
    return (ux, uy), (vx, vy)


def _axis_direction_from_major(major):
    """Orient the block's major axis in the conventional plan-reading direction.

    For a tall block this is north -> south.  For a wide block this is west ->
    east.  For rotated blocks the dominant component is used, preserving the
    block's own orientation while keeping the start deterministic.
    """
    ux, uy = major
    if abs(uy) >= abs(ux):
        # Tall/mostly vertical: top -> bottom.
        if uy > 0:
            ux, uy = -ux, -uy
    else:
        # Wide/mostly horizontal: left -> right.
        if ux < 0:
            ux, uy = -ux, -uy
    return ux, uy


def _orient_minor_for_plan(major, minor):
    """Orient the short axis so it reads across a plot row/column.

    With the major axis oriented north->south, the short axis points west->east.
    With the major axis oriented west->east, the short axis points north->south
    (i.e. top->bottom).  This is the pattern in the user's reference sketch:

      tall block:  1 2 / 3 4 / 5 6 / 7 8
      wide block:  9 11 13 15 / 10 12 14 16

    The cross-product sign is chosen from the global screen orientation so that
    slightly rotated blocks retain the same visual reading direction.
    """
    mx, my = major
    nx, ny = minor
    if abs(mx) >= abs(my):
        # Major is eastward -> short axis should go southward.
        if ny > 0:
            nx, ny = -nx, -ny
    else:
        # Major is southward -> short axis should go eastward.
        if nx < 0:
            nx, ny = -nx, -ny
    return nx, ny


def _cluster_projected(records, axis):
    """Cluster centroid projections into plot bands along one axis."""
    ax, ay = axis
    vals = []
    for f, x, y in records:
        vals.append((f, x, y, x * ax + y * ay))
    if len(vals) <= 1:
        return [vals]

    vals.sort(key=lambda r: (r[3], r[1], r[2], r[0].id()))

    # Estimate normal centroid spacing.  Within a block the nearest-neighbour
    # distance is a good scale; a fraction of it prevents neighbouring bands
    # from collapsing while allowing irregular parcel shapes.
    nn = []
    for i, (_, x1, y1, _) in enumerate(vals):
        best = float("inf")
        for j, (_, x2, y2, _) in enumerate(vals):
            if i == j:
                continue
            d = math.hypot(x2 - x1, y2 - y1)
            if 0 < d < best:
                best = d
        if math.isfinite(best):
            nn.append(best)
    nn.sort()
    typical = nn[len(nn) // 2] if nn else 1.0
    tolerance = max(typical * 0.38, 1e-9)

    bands = [[vals[0]]]
    for item in vals[1:]:
        mean = sum(r[3] for r in bands[-1]) / len(bands[-1])
        if abs(item[3] - mean) <= tolerance:
            bands[-1].append(item)
        else:
            bands.append([item])
    return bands


def _grid_order_within_block(features):
    """Order a cadastral block using the *short dimension first*.

    This is the key rule from the user's reference drawing.  A 2 x 4 block is
    numbered across the two plots first and then down the four rows:

        1 2
        3 4
        5 6
        7 8

    A 4 x 2 block is numbered down the two plots first and then across the four
    columns:

        9  11  13  15
        10 12  14  16

    In other words, the smaller grid dimension is the inner loop and the larger
    dimension is the outer loop.  This is more faithful to the cadastral plan
    convention than a nearest-neighbour walk or a fixed row-major sort.
    """
    records = _centroid_records(features)
    if len(records) <= 2:
        return [r[0] for r in records]

    major, minor = _pca_axes([r[0] for r in records])

    # Establish a true visual start from the block itself: the plot nearest
    # the global upper-left of the block.  This prevents a rotated block from
    # being numbered in the reverse direction simply because PCA chose the
    # opposite sign for its eigenvector.
    top_y = max(r[2] for r in records)
    top_band_tol = max((max(r[2] for r in records) - min(r[2] for r in records)) * 0.30, 1e-12)
    top_candidates = [r for r in records if top_y - r[2] <= top_band_tol]
    start_record = min(top_candidates or records, key=lambda r: (r[1], -r[2], r[0].id()))

    # Choose the sign of the major axis so the visual start has the smallest
    # outer-axis projection.  Then orient the minor axis so that the same
    # start plot is first within its row/column.  This works for rotated blocks
    # without assuming that their edges are parallel to north/east.
    mx, my = major
    major_vals = [r[1] * mx + r[2] * my for r in records]
    start_major = start_record[1] * mx + start_record[2] * my
    # The start plot must have the smallest outer-axis coordinate.  This sign
    # rule is deliberately based on the actual block rather than on a global
    # north/east assumption, so rotated blocks retain their visual start.
    if start_major > (min(major_vals) + max(major_vals)) * 0.5:
        mx, my = -mx, -my
    major = (mx, my)

    nx, ny = minor
    minor_vals = [r[1] * nx + r[2] * ny for r in records]
    start_minor = start_record[1] * nx + start_record[2] * ny
    if start_minor > (min(minor_vals) + max(minor_vals)) * 0.5:
        nx, ny = -nx, -ny
    minor = (nx, ny)

    # Project and cluster along both axes.  The axis with fewer bands is the
    # short/grid dimension and must be the inner numbering loop.
    major_bands = _cluster_projected(records, major)
    minor_bands = _cluster_projected(records, minor)

    major_count = len(major_bands)
    minor_count = len(minor_bands)

    # If the PCA major/minor labels are ambiguous for a near-square block,
    # compare the number of detected bands.  We still retain a deterministic
    # plan-reading direction.
    if major_count < minor_count:
        # Swap so `outer_axis` represents the long dimension and `inner_axis`
        # the short dimension.
        outer_axis, inner_axis = minor, major
        outer_bands = _cluster_projected(records, outer_axis)
        inner_bands = _cluster_projected(records, inner_axis)
    else:
        outer_axis, inner_axis = major, minor
        outer_bands, inner_bands = major_bands, minor_bands

    # Build the actual ordered groups from the outer bands.  Within each outer
    # band, sort by the inner-axis projection.  For a perfectly regular grid
    # this gives exactly the short-side-first pattern; for irregular blocks it
    # remains stable because each parcel belongs to its nearest visual band.
    ox, oy = outer_axis
    ix, iy = inner_axis

    # Re-cluster using the selected outer axis so the ordering follows the
    # selected dimensions even when the initial PCA labels were swapped.
    outer_records = []
    for f, x, y in records:
        outer_records.append((f, x, y, x * ox + y * oy, x * ix + y * iy))
    outer_records.sort(key=lambda r: (r[3], r[0].id()))

    # Determine a tolerance for outer bands from the selected axis.
    nn_outer = []
    for i, (_, x1, y1, _, _) in enumerate(outer_records):
        best = float("inf")
        for j, (_, x2, y2, _, _) in enumerate(outer_records):
            if i == j:
                continue
            d = math.hypot(x2 - x1, y2 - y1)
            if 0 < d < best:
                best = d
        if math.isfinite(best):
            nn_outer.append(best)
    nn_outer.sort()
    typical = nn_outer[len(nn_outer) // 2] if nn_outer else 1.0
    outer_tol = max(typical * 0.38, 1e-9)

    outer_groups = [[outer_records[0]]]
    for item in outer_records[1:]:
        mean = sum(r[3] for r in outer_groups[-1]) / len(outer_groups[-1])
        if abs(item[3] - mean) <= outer_tol:
            outer_groups[-1].append(item)
        else:
            outer_groups.append([item])

    result = []
    for group in outer_groups:
        group.sort(key=lambda r: (r[4], r[1], -r[2], r[0].id()))
        result.extend(r[0] for r in group)
    return result

def automatic_block_grid_sort(features):
    """Detect spatial blocks and return a natural cadastral/grid order.

    Blocks are discovered from gaps in local plot spacing. Blocks are then
    ordered along the dominant layout direction (west→east for a wider site,
    north→south for a taller site), with ties resolved spatially.
    """
    records = _centroid_records(features)
    if not records:
        return []
    if len(records) <= 2:
        return [r[0] for r in records]

    distances, neighbors = _nearest_neighbor_distances(records)
    threshold = _automatic_gap_threshold(distances)
    blocks = _connected_components(records, neighbors, distances, threshold)

    # Order blocks by spatial continuity rather than by a global X/Y sort.
    # A global sort can finish one block and then jump over several nearby
    # blocks to a distant block.  For cadastral/site-plan numbering the next
    # block should normally be the block immediately adjacent to the one just
    # completed.  We therefore build a nearest-block path.
    centers = []
    for block in blocks:
        xs = [centroid_xy(f)[0] for f in block]
        ys = [centroid_xy(f)[1] for f in block]
        centers.append({
            "block": block,
            "cx": sum(xs) / len(xs),
            "cy": sum(ys) / len(ys),
            "minx": min(xs), "maxx": max(xs),
            "miny": min(ys), "maxy": max(ys),
        })

    if len(centers) == 1:
        return _grid_order_within_block(centers[0]["block"])

    def block_distance(a, b):
        # Use the closest pair of plot centroids.  This is much more useful
        # than center-to-center distance for long cadastral blocks: adjacent
        # blocks then remain adjacent in the numbering sequence.
        best = float("inf")
        for fa in a["block"]:
            ax, ay = centroid_xy(fa)
            for fb in b["block"]:
                bx, by = centroid_xy(fb)
                d2 = (ax - bx) ** 2 + (ay - by) ** 2
                if d2 < best:
                    best = d2
        return math.sqrt(best) if math.isfinite(best) else float("inf")

    # Start at the natural upper-left block.  After that, always continue
    # from the block just numbered to the nearest unnumbered block.  This
    # creates a continuous spatial walk and prevents the old behaviour where
    # the numbering could jump across the site because of a global sort.
    # Pick the natural upper-left starting block.  Do not let a slightly
    # higher block on the far right win merely because its centroid has a
    # larger Y value.  First form a loose top band, then choose the leftmost
    # block in that band.  This matches how site/cadastral plans are normally
    # read while still working when blocks are staggered.
    max_cy = max(c["cy"] for c in centers)
    min_cy = min(c["cy"] for c in centers)
    cy_span = max_cy - min_cy
    top_band = max(cy_span * 0.35, 1e-12)
    top_candidates = [
        i for i, c in enumerate(centers)
        if max_cy - c["cy"] <= top_band
    ]
    start_index = min(
        top_candidates,
        key=lambda i: (centers[i]["cx"], -centers[i]["cy"])
    )

    remaining = set(range(len(centers)))
    current = start_index
    remaining.remove(current)
    block_order = [current]

    while remaining:
        candidates = list(remaining)
        nxt = min(
            candidates,
            key=lambda i: (
                block_distance(centers[current], centers[i]),
                # Stable tie-breakers keep the result deterministic when two
                # blocks are at nearly identical distances.
                -centers[i]["cy"], centers[i]["cx"]
            )
        )
        block_order.append(nxt)
        remaining.remove(nxt)
        current = nxt

    ordered = []
    for index in block_order:
        ordered.extend(_grid_order_within_block(centers[index]["block"]))
    return ordered


def grid_sort(features, tolerance=None):
    feats = list(features)
    if not feats:
        return []

    ys = sorted([centroid_xy(f)[1] for f in feats], reverse=True)
    if tolerance is None:
        xs = [centroid_xy(f)[0] for f in feats]
        ys2 = [centroid_xy(f)[1] for f in feats]
        span_x = max(xs) - min(xs) if len(xs) > 1 else 1
        span_y = max(ys2) - min(ys2) if len(ys2) > 1 else 1
        tolerance = max(span_x, span_y) * 0.03
        tolerance = max(tolerance, 1e-9)

    rows = []
    for f in feats:
        y = centroid_xy(f)[1]
        target = None
        for row in rows:
            if abs(y - row[0]) <= tolerance:
                target = row
                break
        if target is None:
            target = [y, []]
            rows.append(target)
        target[1].append(f)

    rows.sort(key=lambda r: r[0], reverse=True)
    ordered = []
    for _, row in rows:
        row.sort(key=lambda f: centroid_xy(f)[0])
        ordered.extend(row)
    return ordered


def group_by_block(features, block_field):
    groups = {}
    for f in features:
        value = f[block_field] if block_field and block_field in f.fields().names() else None
        key = "" if value is None else str(value)
        groups.setdefault(key, []).append(f)
    return groups

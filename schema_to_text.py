from __future__ import annotations

import re
from typing import Any

from schema import ProblemSchema


def _format_number(value: float | int | None) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _fmt_side_key(k: str) -> str:
    """Convert generic side keys like 'side1' -> 'side 1', leave named keys as-is."""
    m = re.match(r"^side(\d+)$", k)
    return f"side {m.group(1)}" if m else k


def _fmt_angle_key(k: str) -> str:
    """Convert generic angle keys like 'angle1' -> 'angle 1', leave named keys as-is."""
    m = re.match(r"^angle(\d+)$", k)
    return f"angle {m.group(1)}" if m else k


def _describe_triangles(problem: ProblemSchema) -> list[str]:
    lines = []
    if not problem.entities.triangles:
        return lines
    for tri in problem.entities.triangles:
        flags = []
        if getattr(tri, "is_right", False):
            flags.append("right")
        if getattr(tri, "is_equilateral", False):
            flags.append("equilateral")
        if getattr(tri, "is_isosceles", False):
            flags.append("isosceles")

        qualifier = " ".join(flags) + " " if flags else ""
        sentence = f"Let triangle {tri.id} be a {qualifier}triangle"

        clauses = []
        sides = getattr(tri, "sides", None)
        if sides:
            known = {k: v for k, v in sides.items() if v is not None}
            if known:
                side_str = ", ".join(f"{k} = {_format_number(v)}" for k, v in known.items())
                clauses.append(f"with sides {side_str}")

        angles = getattr(tri, "angles", None)
        if angles:
            known = {k: v for k, v in angles.items() if v is not None}
            if known:
                angle_str = ", ".join(f"∠{k} = {_format_number(v)}°" for k, v in known.items())
                clauses.append(f"where {angle_str}")

        if clauses:
            sentence += " " + ", ".join(clauses)
        lines.append(sentence + ".")
    return lines


def _describe_polygons(problem: ProblemSchema) -> list[str]:
    lines = []
    polygons = getattr(problem.entities, "polygons", None)
    if not polygons:
        return lines
    for poly in polygons:
        n_sides = getattr(poly, "n_sides", None)
        shape_name = {3: "triangle", 4: "quadrilateral", 5: "pentagon", 6: "hexagon"}.get(n_sides, "polygon")
        sentence = f"Let {shape_name} {poly.id} be a {n_sides}-sided figure"

        sides = getattr(poly, "sides", None)
        if sides:
            known = {k: v for k, v in sides.items() if v is not None}
            if known:
                side_str = ", ".join(f"{_fmt_side_key(k)} = {_format_number(v)}" for k, v in known.items())
                sentence += f" with {side_str}"

        angles = getattr(poly, "angles", None)
        if angles:
            known = {k: v for k, v in angles.items() if v is not None}
            if known:
                angle_str = ", ".join(f"∠{_fmt_angle_key(k)} = {_format_number(v)}°" for k, v in known.items())
                sentence += f", where {angle_str}"

        lines.append(sentence + ".")
    return lines


def _describe_segments(problem: ProblemSchema) -> list[str]:
    lines = []
    segments = getattr(problem.entities, "segments", None)
    if not segments:
        return lines
    for seg in segments:
        props = []
        if getattr(seg, "is_midsegment", False):
            props.append("midsegment")
        if getattr(seg, "is_altitude", False):
            props.append("altitude")
        if getattr(seg, "is_median", False):
            props.append("median")
        if getattr(seg, "is_angle_bisector", False):
            props.append("angle bisector")

        qualifier = " and ".join(props) + " " if props else ""
        sentence = f"Let segment {seg.id} be a {qualifier}segment"

        clauses = []
        length = getattr(seg, "length", None)
        if length is not None:
            clauses.append(f"with length {_format_number(length)}")
        perp = getattr(seg, "perpendicular_to", None)
        if perp:
            clauses.append(f"perpendicular to {perp}")

        if clauses:
            sentence += " " + ", ".join(clauses)
        lines.append(sentence + ".")
    return lines


def _describe_points(problem: ProblemSchema) -> list[str]:
    lines = []
    points = getattr(problem.entities, "points", None)
    if not points:
        return lines
    for pt in points:
        lies_on = getattr(pt, "lies_on", None)
        is_intersection = getattr(pt, "is_intersection_of", None)
        # Skip bare points whose only role is e.g. dilation center — already named in the relationship
        if not lies_on and not is_intersection:
            continue
        sentence = f"Let point {pt.id} be a point"
        if lies_on:
            sentence += f" on {', '.join(lies_on)}"
        if is_intersection:
            sentence += f" at the intersection of {' and '.join(is_intersection)}"
        lines.append(sentence + ".")
    return lines


def _describe_circles(problem: ProblemSchema) -> list[str]:
    lines = []
    circles = getattr(problem.entities, "circles", None)
    if not circles:
        return lines
    for c in circles:
        sentence = f"Let circle {c.id} be a circle"
        clauses = []
        center = getattr(c, "center", None)
        if center:
            clauses.append(f"centered at {center}")
        radius = getattr(c, "radius", None)
        if radius is not None:
            clauses.append(f"with radius {_format_number(radius)}")
        if clauses:
            sentence += " " + ", ".join(clauses)
        lines.append(sentence + ".")
    return lines


def _describe_relationships(problem: ProblemSchema) -> list[str]:
    lines = []
    for rel in problem.relationships:
        rtype = rel.type.value
        attrs = rel.attributes or {}
        entities = rel.entities

        # --- Similarity ---
        if rtype in ("similar_AA", "similar_SAS", "similar_SSS", "similar_unspecified"):
            criterion = rtype.split("_", 1)[1].upper() if "_" in rtype else ""
            pre = attrs.get("pre_image", entities[0] if entities else "?")
            img = attrs.get("image", entities[1] if len(entities) > 1 else "?")
            sf = attrs.get("scale_factor")
            pairs = attrs.get("congruent_angle_pairs", [])
            desc = f"Triangle {pre} is similar to triangle {img}"
            if criterion and criterion != "UNSPECIFIED":
                desc += f" by {criterion} similarity"
            if sf is not None:
                desc += f" with scale factor {_format_number(sf)}"
            if pairs:
                pair_str = ", ".join(f"{a} ≅ {b}" for a, b in pairs)
                desc += f" (congruent angle pairs: {pair_str})"
            lines.append(desc + ".")

        # --- Dilation ---
        elif rtype == "dilation":
            pre = attrs.get("pre_image", entities[0] if entities else "?")
            img = attrs.get("image", entities[1] if len(entities) > 1 else "?")
            sf = attrs.get("scale_factor")
            center = attrs.get("center")
            desc = f"{pre} is dilated to form {img} with scale factor {_format_number(sf)}"
            if center:
                desc += f", centered at point {center}"
            lines.append(desc + ".")

        # --- Scaled copy ---
        elif rtype in ("scaled_copy", "scaled_copy_unspecified"):
            pre = attrs.get("pre_image", entities[0] if entities else "?")
            img = attrs.get("image", entities[1] if len(entities) > 1 else "?")
            sf = attrs.get("scale_factor")
            desc = f"{img} is a scaled copy of {pre}"
            if sf is not None:
                desc += f" with scale factor {_format_number(sf)}"
            lines.append(desc + ".")

        # --- Proportional segments ---
        elif rtype == "proportional_segments":
            ratio = attrs.get("ratio")
            entity_str = " and ".join(entities)
            lines.append(f"Segments {entity_str} are proportional with ratio {_format_number(ratio)}.")

        # --- Midsegment ---
        elif rtype in ("midsegment_ratio", "midsegment_parallel"):
            seg = entities[0] if entities else "?"
            base = entities[1] if len(entities) > 1 else "?"
            if rtype == "midsegment_ratio":
                lines.append(f"Segment {seg} is a midsegment parallel to {base} and half its length.")
            else:
                lines.append(f"Segment {seg} is parallel to {base}.")

        # --- Triangle proportionality ---
        elif rtype == "triangle_proportionality":
            parallel_side = attrs.get("parallel_side", "?")
            seg1 = attrs.get("segment1", "?")
            seg2 = attrs.get("segment2", "?")
            lines.append(
                f"By the triangle proportionality theorem, a line parallel to {parallel_side} "
                f"divides the other two sides proportionally into segments {seg1} and {seg2}."
            )

        # --- Altitude to hypotenuse ---
        elif rtype == "altitude_to_hypotenuse":
            alt = attrs.get("altitude_id", "?")
            hyp = attrs.get("hypotenuse", "?")
            seg1 = attrs.get("segment1", "?")
            seg2 = attrs.get("segment2", "?")
            lines.append(
                f"Altitude {alt} is drawn to hypotenuse {hyp}, "
                f"dividing it into segments {seg1} and {seg2}."
            )

        # --- Geometric mean (altitude) ---
        elif rtype == "geometric_mean_altitude":
            alt = attrs.get("altitude_id", "?")
            seg1 = attrs.get("segment1", "?")
            seg2 = attrs.get("segment2", "?")
            lines.append(f"Altitude {alt} is the geometric mean of segments {seg1} and {seg2}.")

        # --- Geometric mean (leg) ---
        elif rtype == "geometric_mean_leg":
            leg = attrs.get("leg_id", "?")
            hyp = attrs.get("hypotenuse", "?")
            adj = attrs.get("adjacent_segment", "?")
            lines.append(
                f"Leg {leg} is the geometric mean of hypotenuse {hyp} and adjacent segment {adj}."
            )

        # --- Transversal cut ---
        elif rtype == "transversal_cut":
            t = attrs.get("transversal", "?")
            l1 = attrs.get("line1", "?")
            l2 = attrs.get("line2", "?")
            lines.append(f"Transversal {t} cuts lines {l1} and {l2}.")

        # --- Congruent angles / segments ---
        elif rtype == "congruent_angles":
            ids = attrs.get("ids", entities)
            lines.append(f"Angles {', '.join(ids)} are congruent.")

        elif rtype == "congruent_segments":
            ids = attrs.get("ids", entities)
            lines.append(f"Segments {', '.join(ids)} are congruent.")

        # --- Congruent triangles ---
        elif rtype == "congruent_triangles":
            pre = attrs.get("pre_image", entities[0] if entities else "?")
            img = attrs.get("image", entities[1] if len(entities) > 1 else "?")
            criterion = attrs.get("criterion", "")
            desc = f"Triangle {pre} is congruent to triangle {img}"
            if criterion:
                desc += f" by {criterion}"
            lines.append(desc + ".")

        # --- Collinear dilation ---
        elif rtype == "collinear_dilation":
            center = attrs.get("center", "?")
            pre_pt = attrs.get("pre_image_point", "?")
            img_pt = attrs.get("image_point", "?")
            lines.append(
                f"Points {pre_pt}, {center}, and {img_pt} are collinear, "
                f"with the dilation centered at {center}."
            )

        # --- Supplementary angles ---
        elif rtype == "supplementary_angles":
            a1 = attrs.get("angle1", entities[0] if entities else "?")
            a2 = attrs.get("angle2", entities[1] if len(entities) > 1 else "?")
            lines.append(f"∠{a1} and ∠{a2} are supplementary, meaning they sum to 180°.")

        # --- Complementary angles ---
        elif rtype == "complementary_angles":
            a1 = attrs.get("angle1", entities[0] if entities else "?")
            a2 = attrs.get("angle2", entities[1] if len(entities) > 1 else "?")
            lines.append(f"∠{a1} and ∠{a2} are complementary, meaning they sum to 90°.")

        # --- Vertical angles ---
        elif rtype == "vertical_angles":
            a1 = attrs.get("angle1", entities[0] if entities else "?")
            a2 = attrs.get("angle2", entities[1] if len(entities) > 1 else "?")
            lines.append(f"∠{a1} and ∠{a2} are vertical angles and therefore congruent.")

        # --- Linear pair ---
        elif rtype == "linear_pair":
            a1 = attrs.get("angle1", entities[0] if entities else "?")
            a2 = attrs.get("angle2", entities[1] if len(entities) > 1 else "?")
            lines.append(f"∠{a1} and ∠{a2} form a linear pair, meaning they sum to 180°.")

        # --- Adjacent angles ---
        elif rtype == "adjacent_angles":
            a1 = attrs.get("angle1", "?")
            a2 = attrs.get("angle2", "?")
            vertex = attrs.get("shared_vertex", "?")
            ray = attrs.get("shared_ray", "?")
            lines.append(
                f"∠{a1} and ∠{a2} are adjacent angles sharing vertex {vertex} and ray {ray}."
            )

        # --- Angle bisector ---
        elif rtype == "angle_bisector":
            bisected = attrs.get("bisected_angle", "?")
            ray = attrs.get("ray", "?")
            a1 = attrs.get("angle1", "?")
            a2 = attrs.get("angle2", "?")
            lines.append(
                f"Ray {ray} bisects ∠{bisected}, creating two congruent angles ∠{a1} and ∠{a2}."
            )

        # --- Exterior angle ---
        elif rtype == "exterior_angle":
            ext = attrs.get("exterior_angle", "?")
            r1 = attrs.get("remote_interior_angle1", "?")
            r2 = attrs.get("remote_interior_angle2", "?")
            lines.append(
                f"∠{ext} is an exterior angle of the triangle, equal to the sum of "
                f"the two non-adjacent interior angles ∠{r1} and ∠{r2}."
            )

        # --- Parallel lines + transversal ---
        elif rtype == "parallel_lines_transversal":
            t = attrs.get("transversal", "?")
            l1 = attrs.get("line1", "?")
            l2 = attrs.get("line2", "?")
            desc = f"Lines {l1} and {l2} are parallel and cut by transversal {t}."
            pair_descs = []
            for pair_key, label in [
                ("alternate_interior_pairs", "alternate interior angles"),
                ("alternate_exterior_pairs", "alternate exterior angles"),
                ("corresponding_pairs", "corresponding angles"),
                ("co_interior_pairs", "co-interior angles"),
            ]:
                pairs = attrs.get(pair_key, [])
                if pairs:
                    pair_str = ", ".join(f"∠{a} and ∠{b}" for a, b in pairs)
                    pair_descs.append(f"{label.capitalize()}: {pair_str}")
            if pair_descs:
                desc += " " + "; ".join(pair_descs) + "."
            lines.append(desc)

        # --- Angle sum (triangle) ---
        elif rtype == "angle_sum_triangle":
            tri_id = attrs.get("triangle_id", entities[0] if entities else "?")
            angles = attrs.get("angles", [])
            angle_str = ", ".join(f"∠{a}" for a in angles) if angles else "its interior angles"
            lines.append(f"The interior angles of triangle {tri_id} ({angle_str}) sum to 180°.")

        # --- Angle sum (polygon) ---
        elif rtype == "angle_sum_polygon":
            poly_id = attrs.get("polygon_id", entities[0] if entities else "?")
            n = attrs.get("num_sides", "?")
            interior_sum = attrs.get("interior_sum", "?")
            lines.append(
                f"The interior angles of polygon {poly_id} sum to {_format_number(interior_sum)}°, "
                f"and its exterior angles sum to 360°."
            )

        # --- Fallback ---
        else:
            entity_str = ", ".join(entities) if entities else "unknown entities"
            lines.append(f"There exists a {rtype} relationship among: {entity_str}.")

    return lines


def _describe_target(problem: ProblemSchema) -> str:
    attr = problem.target.attribute
    entity = problem.target.entity
    if "." in attr:
        group, key = attr.split(".", 1)
        if group == "sides":
            return f"Find the length of {_fmt_side_key(key)} in {entity}."
        if group == "angles":
            return f"Find the measure of ∠{_fmt_angle_key(key)} in {entity}."
    if attr == "length":
        return f"Find the length of {entity}."
    if attr == "radius":
        return f"Find the radius of circle {entity}."
    if attr == "is_right":
        return f"Determine whether triangle {entity} is a right triangle."
    if attr == "is_similar":
        return f"Determine whether the given figures are similar."
    if attr == "scale_factor":
        return f"Find the scale factor relating the given figures."
    if attr == "perimeter":
        return f"Find the perimeter of {entity}."
    if attr == "area":
        return f"Find the area of {entity}."
    return f"Find {attr} for {entity}."


def schema_to_problem_text(data: dict[str, Any] | ProblemSchema) -> str:
    """
    Convert a structured geometry schema into a natural-language problem description.
    """
    problem = data if isinstance(data, ProblemSchema) else ProblemSchema(**data)
    parts: list[str] = [
        f"Lesson context: {problem.lesson}.",
        *_describe_triangles(problem),
        *_describe_polygons(problem),
        *_describe_segments(problem),
        *_describe_points(problem),
        *_describe_circles(problem),
        *_describe_relationships(problem),
        _describe_target(problem),
    ]
    return " ".join(parts)
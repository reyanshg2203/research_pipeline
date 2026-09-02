from pydantic import BaseModel
from typing import Optional, Union
from enum import Enum

# Closed finite list of relationship types 
class RelationshipType(str, Enum):
    # Similarity
    SIMILAR_AA = "similar_AA"
    SIMILAR_SAS = "similar_SAS"
    SIMILAR_SSS = "similar_SSS"
    SIMILAR_UNSPECIFIED = "similar_unspecified"
    # Dilation
    DILATION = "dilation"
    SCALED_COPY = "scaled_copy"
    SCALED_COPY_UNSPECIFIED = "scaled_copy_unspecified"
    # Parallel
    PARALLEL_LINES = "parallel_lines"
    PARALLEL_SEGMENTS = "parallel_segments"
    MIDSEGMENT_PARALLEL = "midsegment_parallel"
    TRANSVERSAL_CUT = "transversal_cut"
    # Angle
    VERTICAL_ANGLES = "vertical_angles"
    ADJACENT_ANGLES = "adjacent_angles"
    SUPPLEMENTARY_ANGLES = "supplementary_angles"
    COMPLEMENTARY_ANGLES = "complementary_angles"
    CORRESPONDING_ANGLES = "corresponding_angles"
    ALTERNATE_INTERIOR_ANGLES = "alternate_interior_angles"
    ALTERNATE_EXTERIOR_ANGLES = "alternate_exterior_angles"
    CO_INTERIOR_ANGLES = "co_interior_angles"
    ANGLE_SUM_TRIANGLE = "angle_sum_triangle"
    ANGLE_SUM_POLYGON = "angle_sum_polygon"
    LINEAR_PAIR = "linear_pair"
    ANGLE_BISECTOR = "angle_bisector"
    EXTERIOR_ANGLE = "exterior_angle"
    PARALLEL_LINES_TRANSVERSAL = "parallel_lines_transversal"
    # Proportional segments
    PROPORTIONAL_SEGMENTS = "proportional_segments"
    TRIANGLE_PROPORTIONALITY = "triangle_proportionality"
    MIDSEGMENT_RATIO = "midsegment_ratio"
    MEDIAL_TRIANGLE = "medial_triangle"
    ALTITUDE_TO_HYPOTENUSE = "altitude_to_hypotenuse"
    GEOMETRIC_MEAN_ALTITUDE = "geometric_mean_altitude"
    GEOMETRIC_MEAN_LEG = "geometric_mean_leg"
    # Perpendicularity
    PERPENDICULAR_LINES = "perpendicular_lines"
    PERPENDICULAR_SEGMENTS = "perpendicular_segments"
    ALTITUDE_PERPENDICULAR = "altitude_perpendicular"
    # Congruence
    CONGRUENT_ANGLES = "congruent_angles"
    CONGRUENT_SEGMENTS = "congruent_segments"
    CONGRUENT_TRIANGLES = "congruent_triangles"
    # Dilation-specific point relationships
    COLLINEAR_DILATION = "collinear_dilation"
    CENTER_ON_FIGURE = "center_on_figure"
    CENTER_OFF_FIGURE = "center_off_figure"
    # Intersection
    LINES_INTERSECT = "lines_intersect"
    SEGMENTS_INTERSECT = "segments_intersect"
    POINT_ON_LINE = "point_on_line"
    POINT_INTERIOR = "point_interior"

# =====================================================================
# RELATIONSHIP ATTRIBUTE CONTRACT — the SINGLE SOURCE OF TRUTH
# =====================================================================
# Each relationship type's allowed and required attribute keys live here, and
# ONLY here. Two consumers derive from this table so they can never drift:
#   1. geometry_validator.pl — its allowed_attrs/2 and required_attrs/2 facts
#      are generated from this table (see write_prolog_contract() -> the
#      committed relation_contract.pl, which the validator consults).
#   2. the Haiku repair feedback (pipelines/refine_schema.py) — what the model
#      is told a relationship may/must carry is read straight from here.
# A relationship type ABSENT from this table is UNCONSTRAINED (any attribute
# key is accepted) — this matches the validator, where a missing allowed_attrs
# fact means the attribute-key gate simply does not fire. An entry with
# allowed=[] means the type accepts NO attributes. `attributes` on Relationship
# stays a free-form dict on purpose: P3 must be able to LOAD a flawed schema in
# order to repair it, so the contract is authoritative but not load-blocking.
RELATION_ATTRS: dict[str, dict[str, list[str]]] = {
    "similar_AA":              {"allowed": ["scale_factor", "pre_image", "image", "congruent_angle_pairs"], "required": ["pre_image", "image"]},
    "similar_SAS":             {"allowed": ["scale_factor", "pre_image", "image", "congruent_angle_pairs"], "required": ["pre_image", "image"]},
    "similar_SSS":             {"allowed": ["scale_factor", "pre_image", "image", "congruent_angle_pairs"], "required": ["pre_image", "image"]},
    "similar_unspecified":     {"allowed": ["scale_factor", "pre_image", "image", "congruent_angle_pairs"], "required": ["pre_image", "image"]},
    "dilation":                {"allowed": ["scale_factor", "center", "pre_image", "image"], "required": ["scale_factor", "pre_image", "image"]},
    "scaled_copy":             {"allowed": ["scale_factor", "pre_image", "image"], "required": ["scale_factor", "pre_image", "image"]},
    "scaled_copy_unspecified": {"allowed": ["scale_factor", "pre_image", "image"], "required": ["pre_image", "image"]},
    "proportional_segments":   {"allowed": ["ratio"], "required": []},
    "midsegment_ratio":        {"allowed": ["ratio"], "required": []},
    # medial_triangle(Small, Big): "Small is the medial triangle of Big" (its
    # vertices are the midpoints of Big's sides). Positional [Small, Big]; the
    # half-length relationships are carried by the accompanying midsegment_parallel
    # relationships, so this type itself needs no attributes.
    "medial_triangle":         {"allowed": [], "required": []},
    "triangle_proportionality":{"allowed": ["parallel_side", "segment1", "segment2"], "required": ["parallel_side", "segment1", "segment2"]},
    "altitude_to_hypotenuse":  {"allowed": ["altitude_id", "hypotenuse", "segment1", "segment2"], "required": ["altitude_id", "hypotenuse", "segment1", "segment2"]},
    "geometric_mean_altitude": {"allowed": ["altitude_id", "segment1", "segment2"], "required": ["altitude_id", "segment1", "segment2"]},
    "geometric_mean_leg":      {"allowed": ["leg_id", "hypotenuse", "adjacent_segment"], "required": ["leg_id", "hypotenuse", "adjacent_segment"]},
    "transversal_cut":         {"allowed": ["transversal", "line1", "line2"], "required": ["transversal", "line1", "line2"]},
    "congruent_angles":        {"allowed": ["ids"], "required": []},
    "congruent_segments":      {"allowed": ["ids"], "required": []},
    "congruent_triangles":     {"allowed": ["pre_image", "image", "criterion"], "required": ["pre_image", "image"]},
    "collinear_dilation":      {"allowed": ["center", "pre_image_point", "image_point"], "required": ["center", "pre_image_point", "image_point"]},
    "supplementary_angles":    {"allowed": ["angle1", "angle2", "sum"], "required": []},
    "complementary_angles":    {"allowed": ["angle1", "angle2", "sum"], "required": []},
    "vertical_angles":         {"allowed": ["angle1", "angle2"], "required": []},
    "linear_pair":             {"allowed": ["angle1", "angle2", "sum"], "required": []},
    "adjacent_angles":         {"allowed": ["shared_vertex", "shared_ray", "angle1", "angle2"], "required": []},
    "angle_bisector":          {"allowed": ["bisected_angle", "ray", "angle1", "angle2"], "required": ["bisected_angle"]},
    "exterior_angle":          {"allowed": ["exterior_angle", "remote_interior_angle1", "remote_interior_angle2"], "required": ["exterior_angle", "remote_interior_angle1", "remote_interior_angle2"]},
    "parallel_lines_transversal": {"allowed": ["transversal", "line1", "line2", "alternate_interior_pairs", "alternate_exterior_pairs", "corresponding_pairs", "co_interior_pairs"], "required": ["transversal", "line1", "line2"]},
    "angle_sum_triangle":      {"allowed": ["triangle_id", "angles", "sum"], "required": ["triangle_id"]},
    "angle_sum_polygon":       {"allowed": ["polygon_id", "num_sides", "interior_sum", "exterior_sum"], "required": ["polygon_id", "num_sides"]},
    "parallel_lines":          {"allowed": [], "required": []},
    "parallel_segments":       {"allowed": [], "required": []},
    "midsegment_parallel":     {"allowed": [], "required": []},
    "perpendicular_lines":     {"allowed": [], "required": []},
    "perpendicular_segments":  {"allowed": [], "required": []},
    "altitude_perpendicular":  {"allowed": [], "required": []},
    "center_on_figure":        {"allowed": [], "required": []},
    "center_off_figure":       {"allowed": [], "required": []},
    "lines_intersect":         {"allowed": [], "required": []},
    "segments_intersect":      {"allowed": [], "required": []},
    "point_on_line":           {"allowed": [], "required": []},
    "point_interior":          {"allowed": [], "required": []},
}


def prolog_contract_facts() -> str:
    """Render RELATION_ATTRS as SWI-Prolog allowed_attrs/2 + required_attrs/2
    facts. This is the generator behind relation_contract.pl — regenerate that
    file (python -c 'import schema; schema.write_prolog_contract()') whenever
    RELATION_ATTRS changes, so the validator and this table never diverge."""
    def _list(xs: list[str]) -> str:
        return "[" + ", ".join(xs) + "]"
    lines = [
        "% GENERATED FROM schema.py:RELATION_ATTRS — DO NOT EDIT BY HAND.",
        "% Regenerate with: python -c 'import schema; schema.write_prolog_contract()'",
        "",
    ]
    for t, spec in RELATION_ATTRS.items():
        lines.append(f"allowed_attrs({t}, {_list(spec['allowed'])}).")
    lines.append("")
    for t, spec in RELATION_ATTRS.items():
        if spec["required"]:
            lines.append(f"required_attrs({t}, {_list(spec['required'])}).")
    return "\n".join(lines) + "\n"


def write_prolog_contract(path: str | None = None) -> str:
    """Write relation_contract.pl next to schema.py (repo root). Returns path."""
    import os
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "relation_contract.pl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(prolog_contract_facts())
    return path


def relation_attribute_contract(rel_type: str) -> dict[str, list[str]] | None:
    """The allowed/required attribute spec for a relationship type, or None if
    the type is unconstrained. Used to give Haiku accurate, single-source
    attribute feedback during repair."""
    return RELATION_ATTRS.get(rel_type)


# models for different shapes
class Triangle(BaseModel):
    id: str
    sides: Optional[dict[str, Optional[float]]] = None
    angles: Optional[dict[str, Optional[float]]] = None
    is_right: Optional[bool] = None
    is_isosceles: Optional[bool] = None
    is_equilateral: Optional[bool] = None

class Segment(BaseModel):
    id: str
    length: Optional[float] = None
    parallel_to: Optional[str] = None
    perpendicular_to: Optional[str] = None
    ratio_to: Optional[dict[str, float]] = None
    is_midsegment: Optional[bool] = None
    is_altitude: Optional[bool] = None

class Polygon(BaseModel):
    id: str
    n_sides: int
    sides: Optional[dict[str, Optional[float]]] = None
    angles: Optional[dict[str, Optional[float]]] = None

class Line(BaseModel):
    id: str
    parallel_to: Optional[list[str]] = None
    perpendicular_to: Optional[list[str]] = None

class Point(BaseModel):
    id: str
    lies_on: Optional[list[str]] = None
    is_intersection_of: Optional[list[str]] = None

class Circle(BaseModel):
    id: str
    radius: Optional[float] = None

class Shapes(BaseModel):
    triangles: Optional[list[Triangle]] = None
    segments: Optional[list[Segment]] = None
    polygons: Optional[list[Polygon]] = None
    lines: Optional[list[Line]] = None
    points: Optional[list[Point]] = None
    circles: Optional[list[Circle]] = None

# Attribute value types 
AttributeValue = Union[str, float, bool, list, None]

# Relationship model 
class Relationship(BaseModel):
    type: RelationshipType
    entities: list[str]
    attributes: Optional[dict[str, AttributeValue]] = None

# target value for student (answer) 
class Target(BaseModel):
    entity: str
    attribute: str

# Full problem schema 
class ProblemSchema(BaseModel):
    problem_id: str
    lesson: str
    entities: Shapes
    relationships: list[Relationship]
    target: Target


# Example payload matching `ProblemSchema` (for demos / tests).
EXAMPLE_PROBLEM = {
    "problem_id": "ex-001",
    "lesson": "Similar triangles and dilations",
    "entities": {
        "triangles": [
            {"id": "T1", "sides": {"AB": 3, "BC": 4, "CA": 5}},
            {"id": "T2", "sides": {"DE": None, "EF": 8, "FD": 10}},
        ]
    },
    "relationships": [
        {
            "type": "dilation",
            "entities": ["T1", "T2"],
            "attributes": {
                "pre_image": "T1",
                "image": "T2",
                "scale_factor": 2,
                "center": "O",
            },
        },
        {
            "type": "similar_SSS",
            "entities": ["T1", "T2"],
            "attributes": None,
        },
    ],
    "target": {"entity": "T2", "attribute": "sides.DE"},
}

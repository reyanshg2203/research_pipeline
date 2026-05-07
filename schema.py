from pydantic import BaseModel
from typing import Optional, Union
from enum import Enum

# --- Closed finite list of relationship types ---
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
    # Proportional segments
    PROPORTIONAL_SEGMENTS = "proportional_segments"
    TRIANGLE_PROPORTIONALITY = "triangle_proportionality"
    MIDSEGMENT_RATIO = "midsegment_ratio"
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

# --- Entity models ---
class Triangle(BaseModel):
    id: str
    sides: dict[str, Optional[float]]
    angles: dict[str, Optional[float]]
    is_right: bool
    is_isosceles: bool
    is_equilateral: bool

class Segment(BaseModel):
    id: str
    length: Optional[float]
    parallel_to: Optional[str]
    perpendicular_to: Optional[str]
    ratio_to: Optional[dict[str, float]]  # e.g. {"CD": 0.5} means this segment is half of CD
    is_midsegment: bool
    is_altitude: bool

class Polygon(BaseModel):
    id: str
    n_sides: int
    sides: dict[str, Optional[float]]
    angles: dict[str, Optional[float]]

class Line(BaseModel):
    id: str
    parallel_to: list[str]
    perpendicular_to: list[str]

class Point(BaseModel):
    id: str
    lies_on: list[str]
    is_intersection_of: list[str]

class Circle(BaseModel):
    id: str
    radius: Optional[float]

class Entities(BaseModel):
    triangles: list[Triangle]
    segments: list[Segment]
    polygons: list[Polygon]
    lines: list[Line]
    points: list[Point]
    circles: list[Circle]

# --- Relationship attributes ---
# These are the valid keys inside the attributes dict per relationship type.
# Pydantic allows flexible dicts here; the DSL enforces per-type attribute rules.
AttributeValue = Union[str, float, bool, list, None]

class Relationship(BaseModel):
    type: RelationshipType
    entities: list[str]
    attributes: dict[str, AttributeValue]
    # Common attribute keys by relationship type (enforced by DSL, documented here):
    # dilation: scale_factor (float), center (str or null), pre_image (str), image (str)
    # scaled_copy: scale_factor (float), pre_image (str), image (str)
    # similar_AA/SAS/SSS: scale_factor (float or null), pre_image (str), image (str),
    #                      congruent_angle_pairs (list of [str, str])
    # proportional_segments: ratio (float)
    # midsegment_ratio: ratio always 0.5 (enforced by DSL gate)
    # geometric_mean_altitude: altitude_id (str), segment1 (str), segment2 (str)
    # geometric_mean_leg: leg_id (str), hypotenuse (str), adjacent_segment (str)
    # transversal_cut: transversal (str), line1 (str), line2 (str)

# --- Target model ---
class Target(BaseModel):
    entity: str
    attribute: str

# --- Full problem schema ---
class ProblemSchema(BaseModel):
    problem_id: str
    lesson: str
    entities: Entities
    relationships: list[Relationship]
    target: Target

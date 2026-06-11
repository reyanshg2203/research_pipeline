% =====================================================================
% GEOMETRY PROBLEM SCHEMA VALIDATOR
% Domain: 10th grade similarity unit (lessons 01-10, plus right-triangle
%         and Pythagorean lessons)
%
% Architecture:
%   Layer 0: Facts asserted from the input schema (entity/3, relationship/3,
%            attribute/3, target/2, etc.)
%   Layer 1: Structural gates  — references exist, attributes well-formed
%   Layer 2: Type-compatibility gates — relationships applied to valid shapes
%   Layer 3: Mathematical gates — triangle inequality, Pythagoras, angle sums,
%            scale-factor coherence, invariant enforcement
%   Layer 4: Determinacy gates — target is uniquely solvable, no
%            under-determination
%   Layer 5: Output — collect all error/3 facts and emit feedback
%
% Each gate returns either:
%   pass(GateId)
%   error(GateId, Severity, Message)
%
% Severity is one of: fatal, contradiction, underdetermined, structural, style
% Message is a plain-English string suitable for an LLM repair loop.
% =====================================================================

% Silence style warnings during load. The validator is correct; warnings
% about singleton variables and discontiguous clauses are intentional
% (clauses are grouped by topic, not by predicate).
:- set_prolog_flag(verbose, silent).
:- style_check(-singleton).
:- style_check(-discontiguous).


% ---------------------------------------------------------------------
% LAYER 0 — Schema fact predicates (asserted at load time by the host).
% These are the only predicates the host program must populate.
% ---------------------------------------------------------------------

% Suppress "clauses not together" warnings — these predicates are
% intentionally spread across the file by topic during calibration.
:- discontiguous target_derivable/2.
:- discontiguous gate_check/2.
:- discontiguous allowed_attrs/2.
:- discontiguous required_attrs/2.
:- discontiguous scope/2.

% problem(ProblemId, LessonId)
% entity(Kind, Id)                       -- Kind ∈ {triangle, segment, polygon, line, point, circle}
% triangle_side(TriId, SideKey, Value)   -- Value may be the atom 'unknown' if null
% triangle_angle(TriId, AngleKey, Value)
% triangle_flag(TriId, Flag)             -- Flag ∈ {is_right, is_isosceles, is_equilateral}
% polygon_n_sides(PolyId, N)
% polygon_side(PolyId, SideKey, Value)
% polygon_angle(PolyId, AngleKey, Value)
% segment_length(SegId, Value)
% segment_flag(SegId, Flag)              -- Flag ∈ {is_midsegment, is_altitude}
% segment_parallel_to(SegId, OtherId)
% segment_perpendicular_to(SegId, OtherId)
% segment_ratio_to(SegId, OtherId, Ratio)
% line_parallel_to(LineId, OtherId)
% line_perpendicular_to(LineId, OtherId)
% point_lies_on(PtId, EntityId)
% point_intersection_of(PtId, EntityId)
% circle_radius(CirId, Value)
% relationship(RelIndex, Type, EntityList)
% rel_attr(RelIndex, Key, Value)
% target(EntityId, Attribute)            -- Attribute uses dot notation, e.g. 'sides.AB'


% ---------------------------------------------------------------------
% UTILITY PREDICATES
% ---------------------------------------------------------------------

% Numerical tolerance for float comparison
epsilon(0.0001).

approx_equal(X, Y) :-
    epsilon(E),
    Diff is abs(X - Y),
    Diff < E.

% Known value: not null, not the placeholder 'unknown'
known(V) :- nonvar(V), V \= unknown, V \= null.

unknown(unknown).
unknown(null).

% Naming convention checkers
valid_triangle_id(Id) :-
    atom_codes(Id, Codes),
    length(Codes, 3),
    forall(member(C, Codes), (C >= 0'A, C =< 0'Z)).

valid_polygon_id(Id) :-
    atom_codes(Id, Codes),
    length(Codes, N), N >= 3,
    forall(member(C, Codes), (C >= 0'A, C =< 0'Z)).

valid_segment_id(Id) :-
    atom_codes(Id, Codes),
    length(Codes, 2),
    forall(member(C, Codes), (C >= 0'A, C =< 0'Z)).

valid_point_id(Id) :-
    atom_codes(Id, Codes),
    ( Codes = [C], C >= 0'A, C =< 0'Z
    ; Codes = [C, 0'\'], C >= 0'A, C =< 0'Z
    ).

valid_line_id(Id) :-
    atom_codes(Id, [C]),
    C >= 0'a, C =< 0'z.

valid_circle_id(Id) :-
    atom_codes(Id, [C]),
    C >= 0'a, C =< 0'z.

% Collect the set of allowed attribute keys for each relationship type
allowed_attrs(similar_AA,             [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_SAS,            [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_SSS,            [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_unspecified,    [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(dilation,               [scale_factor, center, pre_image, image]).
allowed_attrs(scaled_copy,            [scale_factor, pre_image, image]).
allowed_attrs(scaled_copy_unspecified,[scale_factor, pre_image, image]).
allowed_attrs(proportional_segments,  [ratio]).
allowed_attrs(midsegment_ratio,       [ratio]).
allowed_attrs(triangle_proportionality,[parallel_side, segment1, segment2]).
allowed_attrs(altitude_to_hypotenuse, [altitude_id, hypotenuse, segment1, segment2]).
allowed_attrs(geometric_mean_altitude,[altitude_id, segment1, segment2]).
allowed_attrs(geometric_mean_leg,     [leg_id, hypotenuse, adjacent_segment]).
allowed_attrs(transversal_cut,        [transversal, line1, line2]).
allowed_attrs(congruent_angles,       [ids]).
allowed_attrs(congruent_segments,     [ids]).
allowed_attrs(congruent_triangles,    [pre_image, image, criterion]).
allowed_attrs(collinear_dilation,     [center, pre_image_point, image_point]).
allowed_attrs(supplementary_angles,   [angle1, angle2, sum]).
allowed_attrs(complementary_angles,   [angle1, angle2, sum]).
allowed_attrs(vertical_angles,        [angle1, angle2]).
allowed_attrs(linear_pair,            [angle1, angle2, sum]).
allowed_attrs(adjacent_angles,        [shared_vertex, shared_ray, angle1, angle2]).
allowed_attrs(angle_bisector,         [bisected_angle, ray, angle1, angle2]).
allowed_attrs(exterior_angle,         [exterior_angle, remote_interior_angle1, remote_interior_angle2]).
allowed_attrs(parallel_lines_transversal,
              [transversal, line1, line2,
               alternate_interior_pairs, alternate_exterior_pairs,
               corresponding_pairs, co_interior_pairs]).
allowed_attrs(angle_sum_triangle,     [triangle_id, angles, sum]).
allowed_attrs(angle_sum_polygon,      [polygon_id, num_sides, interior_sum, exterior_sum]).
allowed_attrs(parallel_lines,         []).
allowed_attrs(parallel_segments,      []).
allowed_attrs(midsegment_parallel,    []).
allowed_attrs(perpendicular_lines,    []).
allowed_attrs(perpendicular_segments, []).
allowed_attrs(altitude_perpendicular, []).
allowed_attrs(center_on_figure,       []).
allowed_attrs(center_off_figure,      []).
allowed_attrs(lines_intersect,        []).
allowed_attrs(segments_intersect,     []).
allowed_attrs(point_on_line,          []).
allowed_attrs(point_interior,         []).

% Required attribute keys per relationship type. These keys MUST be present
% (with a known or null value) in the attributes dictionary; an empty or
% missing attributes block is a structural violation when required keys exist.
required_attrs(dilation,                [scale_factor, pre_image, image]).
required_attrs(scaled_copy,             [scale_factor, pre_image, image]).
required_attrs(scaled_copy_unspecified, [pre_image, image]).
required_attrs(similar_AA,              [pre_image, image]).
required_attrs(similar_SAS,             [pre_image, image]).
required_attrs(similar_SSS,             [pre_image, image]).
required_attrs(similar_unspecified,     [pre_image, image]).
required_attrs(triangle_proportionality,[parallel_side, segment1, segment2]).
required_attrs(altitude_to_hypotenuse,  [altitude_id, hypotenuse, segment1, segment2]).
required_attrs(geometric_mean_altitude, [altitude_id, segment1, segment2]).
required_attrs(geometric_mean_leg,      [leg_id, hypotenuse, adjacent_segment]).
required_attrs(transversal_cut,         [transversal, line1, line2]).
required_attrs(parallel_lines_transversal, [transversal, line1, line2]).
required_attrs(collinear_dilation,      [center, pre_image_point, image_point]).
required_attrs(congruent_triangles,     [pre_image, image]).
required_attrs(angle_bisector,          [bisected_angle]).
required_attrs(exterior_angle,          [exterior_angle, remote_interior_angle1, remote_interior_angle2]).
required_attrs(angle_sum_triangle,      [triangle_id]).
required_attrs(angle_sum_polygon,       [polygon_id, num_sides]).

% Required entity arity per relationship type
relation_arity(similar_AA, 2).
relation_arity(similar_SAS, 2).
relation_arity(similar_SSS, 2).
relation_arity(similar_unspecified, 2).
relation_arity(dilation, 2).
relation_arity(scaled_copy, 2).
relation_arity(scaled_copy_unspecified, 2).
relation_arity(congruent_triangles, 2).
relation_arity(collinear_dilation, 3).
relation_arity(triangle_proportionality, _) :- true.  % variable
relation_arity(supplementary_angles, 2).
relation_arity(complementary_angles, 2).
relation_arity(vertical_angles, 2).
relation_arity(linear_pair, 2).
relation_arity(midsegment_ratio, 2).

% Expected number of corresponding sides + angles for similarity by n_sides
similarity_corresponding_sides_required(N, N).
similarity_corresponding_angles_required(N, K) :- K is N - 1.


% =====================================================================
% LAYER 1 — STRUCTURAL VALIDATION
% =====================================================================

% --- gate_entity_references_exist ---
% Every entity name appearing in a relationship must be declared.
gate_entity_references_exist :-
    findall(error(entity_ref_missing, fatal, Msg),
            ( relationship(RIdx, Type, Entities),
              member(E, Entities),
              \+ entity_known(E),
              format(atom(Msg),
                     "Relationship ~w (index ~w) references entity '~w' which is not declared in entities.",
                     [Type, RIdx, E])
            ),
            Errors),
    assert_errors(Errors).

entity_known(Id) :- entity(_Kind, Id).
entity_known(Id) :- triangle_vertex_of_any(Id).   % implicit vertex
entity_known(Id) :- triangle_side_of_any(Id).     % implicit side
entity_known(Id) :- polygon_vertex_of_any(Id).    % implicit polygon vertex
entity_known(Id) :- polygon_side_of_any(Id).      % implicit polygon side
entity_known(Id) :- implicit_point_to_point_segment(Id).  % segment between two known points
entity_known(Id) :- implicit_altitude_subtriangle(Id).    % sub-triangle from altitude_to_hypotenuse

polygon_vertex_of_any(VId) :-
    entity(polygon, P),
    atom_codes(P, VertexCodes),
    member(C, VertexCodes),
    atom_codes(VId, [C]).

polygon_side_of_any(SId) :-
    entity(polygon, P),
    polygon_implicit_side(P, SId).

% Any two-letter segment ID where both letters are known points
% (declared Points or vertices of declared triangles/polygons).
implicit_point_to_point_segment(SId) :-
    atom_codes(SId, [C1, C2]),
    C1 \= C2,
    atom_codes(P1, [C1]),
    atom_codes(P2, [C2]),
    known_point(P1),
    known_point(P2).

known_point(P) :- entity(point, P).
known_point(P) :- triangle_vertex_of_any(P).
known_point(P) :- polygon_vertex_of_any(P).

% A 3-letter ID is an implicit altitude sub-triangle if:
%   - all three letters are known points
%   - one of the letters is the altitude foot (a declared point lying on
%     the hypotenuse of some triangle)
%   - the other two letters are the apex of the original triangle and one
%     of the two endpoints of the hypotenuse
% Effectively: any 3-letter combination drawn from the original triangle's
% three vertices plus the altitude foot, that forms a valid sub-triangle.
implicit_altitude_subtriangle(Id) :-
    atom_codes(Id, Chars),
    length(Chars, 3),
    forall(member(C, Chars),
           ( atom_codes(P, [C]), known_point(P) )),
    % There must exist an altitude_to_hypotenuse relationship in the schema.
    relationship(_, altitude_to_hypotenuse, _).

triangle_vertex_of_any(VId) :-
    entity(triangle, T),
    atom_codes(T, VertexCodes),
    member(C, VertexCodes),
    atom_codes(VId, [C]).

triangle_side_of_any(SId) :-
    entity(triangle, T),
    atom_codes(T, [A, B, C]),
    member(SId, [AB, BC, CA]),  % naming: pairs of adjacent vertices
    pair_to_atom(A, B, AB),
    pair_to_atom(B, C, BC),
    pair_to_atom(C, A, CA).

pair_to_atom(C1, C2, Atom) :- atom_codes(Atom, [C1, C2]).

% --- gate_attribute_keys_well_formed ---
% Each relationship's attribute dict must use only keys allowed for its type.
gate_attribute_keys_well_formed :-
    findall(error(invalid_attribute_key, structural, Msg),
            ( relationship(RIdx, Type, _),
              allowed_attrs(Type, Allowed),
              rel_attr(RIdx, Key, _),
              \+ member(Key, Allowed),
              format(atom(Msg),
                     "Relationship ~w (index ~w) has unexpected attribute '~w'. Allowed keys: ~w.",
                     [Type, RIdx, Key, Allowed])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_naming_conventions ---
gate_naming_conventions :-
    findall(error(naming_convention, style, Msg),
            ( entity(Kind, Id),
              \+ id_matches_convention(Kind, Id),
              format(atom(Msg),
                     "Entity ~w of kind '~w' violates the naming convention. Expected bare letters (e.g. ABC for triangle, AB for segment, single capital for point).",
                     [Id, Kind])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_no_dot_notation_in_relationship_entities ---
% Dot notation like "ABC.C" or "DEF.F" is reserved for the target attribute
% field (e.g. target.attribute = "angles.C"). Relationship `entities` lists
% must use bare entity ids only. Compound references inside relationships
% break the entity_known check and indicate a schema-spec violation.
gate_no_dot_notation_in_relationship_entities :-
    findall(error(dot_notation_in_relationship, fatal, Msg),
            ( relationship(RIdx, Type, Entities),
              member(E, Entities),
              atom(E),
              atom_codes(E, Codes),
              member(0'., Codes),
              format(atom(Msg),
                     "Relationship ~w (index ~w) uses dot notation '~w' in its entities list. Dot notation is reserved for the target.attribute field. Use bare entity ids in relationships (e.g., 'C' instead of 'ABC.C'), or place compound references in a typed attribute like `ids` for congruent_angles/congruent_segments.",
                     [Type, RIdx, E])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_required_attributes_present ---
% Some relationship types declare keys that MUST be present in their
% attributes dictionary. Firing on missing required keys is more useful
% than firing on the downstream symptoms (entity_ref_missing, scope, etc.).
gate_required_attributes_present :-
    findall(error(missing_required_attribute, structural, Msg),
            ( relationship(RIdx, Type, _),
              required_attrs(Type, Required),
              member(Key, Required),
              \+ rel_attr(RIdx, Key, _),
              format(atom(Msg),
                     "Relationship ~w (index ~w) is missing required attribute '~w'. ~w requires attributes: ~w.",
                     [Type, RIdx, Key, Type, Required])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_hypotenuse_is_longest_side ---
% When an altitude_to_hypotenuse relationship designates a segment as the
% hypotenuse, that segment must be the longest side of the triangle it
% belongs to. The hypotenuse of a right triangle is, by definition, the
% side opposite the right angle, which is also the longest side.
gate_hypotenuse_is_longest_side :-
    findall(error(hypotenuse_not_longest, contradiction, Msg),
            ( relationship(RIdx, altitude_to_hypotenuse, _),
              rel_attr(RIdx, hypotenuse, HypId),
              entity(triangle, T),
              triangle_implicit_side(T, HypId),
              triangle_side(T, HypId, HypV), known(HypV),
              triangle_side(T, OtherKey, OtherV), known(OtherV),
              OtherKey \= HypId,
              OtherV > HypV,
              format(atom(Msg),
                     "altitude_to_hypotenuse (index ~w) designates ~w as the hypotenuse of triangle ~w, but side ~w (length ~w) is longer than ~w (length ~w). The hypotenuse must be the longest side of the right triangle.",
                     [RIdx, HypId, T, OtherKey, OtherV, HypId, HypV])
            ),
            Errors),
    assert_errors(Errors).

id_matches_convention(triangle, Id) :- valid_triangle_id(Id).
id_matches_convention(polygon, Id)  :- valid_polygon_id(Id).
id_matches_convention(segment, Id)  :- valid_segment_id(Id).
id_matches_convention(point, Id)    :- valid_point_id(Id).
id_matches_convention(line, Id)     :- valid_line_id(Id).
id_matches_convention(circle, Id)   :- valid_circle_id(Id).

% --- gate_relation_arity ---
gate_relation_arity :-
    findall(error(wrong_entity_count, structural, Msg),
            ( relationship(RIdx, Type, Entities),
              relation_arity(Type, Expected),
              integer(Expected),
              length(Entities, Actual),
              Actual \= Expected,
              format(atom(Msg),
                     "Relationship ~w (index ~w) expects ~w entities but has ~w: ~w.",
                     [Type, RIdx, Expected, Actual, Entities])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_orphan_entities ---
% Entities declared but referenced in no relationship and not the target.
gate_orphan_entities :-
    findall(error(orphan_entity, style, Msg),
            ( entity(Kind, Id),
              Kind \= triangle, Kind \= polygon, Kind \= circle,
              \+ entity_used(Id),
              format(atom(Msg),
                     "Entity '~w' (~w) is declared but never used in any relationship or as the target. Consider removing it.",
                     [Id, Kind])
            ),
            Errors),
    assert_errors(Errors).

entity_used(Id) :- relationship(_, _, Es), member(Id, Es).
entity_used(Id) :- rel_attr(_, _, Id).
entity_used(Id) :- target(Id, _).

% --- gate_disconnected_figures ---
% If two or more shape entities of similar kind are declared but no
% relationship connects them, the problem cannot be about comparing them.
% A pedagogically sound multi-figure problem must declare at least one
% relationship that references multiple figures.
gate_disconnected_figures :-
    findall(error(figures_not_connected, structural, Msg),
            ( comparable_figure_pairs(F1, F2),
              \+ relationship_connects(F1, F2),
              format(atom(Msg),
                     "Entities ~w and ~w are both declared as ~w but no relationship connects them. A multi-figure problem must declare at least one relationship (dilation, similarity, scaled_copy, congruence, etc.) that links them.",
                     [F1, F2, comparable_kind(F1)])
            ),
            Errors0),
    list_to_set(Errors0, Errors),
    assert_errors(Errors).

% Generate unordered pairs (F1, F2) where F1 @< F2 and both are the same
% comparable shape kind (triangles compared with triangles, polygons with
% polygons, circles with circles). Segments and points/lines are not
% "compared" in the same pedagogical sense.
comparable_figure_pairs(F1, F2) :-
    entity(Kind, F1), entity(Kind, F2),
    member(Kind, [triangle, polygon, circle]),
    F1 @< F2.

comparable_kind(F) :- entity(triangle, F), !.
comparable_kind(F) :- entity(polygon, F), !.
comparable_kind(F) :- entity(circle, F), !.

% Two entities are "connected" if some relationship has both in its
% entities list, or one is referenced in an attribute of a relationship
% involving the other.
relationship_connects(F1, F2) :-
    relationship(_, _, Es),
    member(F1, Es), member(F2, Es).
relationship_connects(F1, F2) :-
    relationship(RIdx, _, Es),
    member(F1, Es),
    rel_attr(RIdx, _, F2).
relationship_connects(F1, F2) :-
    relationship(RIdx, _, Es),
    member(F2, Es),
    rel_attr(RIdx, _, F1).

% --- gate_polygon_angle_sum_consistency ---
% Independently of whether an angle_sum_polygon relationship is declared,
% if a polygon's interior angles are all declared with known values, they
% must sum to (n-2) × 180°.
gate_polygon_angle_sum_consistency :-
    findall(error(polygon_interior_angle_sum_violation, contradiction, Msg),
            ( entity(polygon, P),
              polygon_n_sides(P, N),
              findall(V, (polygon_angle(P, _, V), known(V)), Vs),
              length(Vs, N),  % all n angles declared
              sumlist(Vs, Sum),
              Expected is (N - 2) * 180,
              \+ approx_equal(Sum, Expected),
              format(atom(Msg),
                     "Polygon ~w (n=~w) has interior angles ~w that sum to ~w°, but an ~w-sided polygon's interior angles must sum to ~w°.",
                     [P, N, Vs, Sum, N, Expected])
            ),
            Errors),
    assert_errors(Errors).


% =====================================================================
% LAYER 2 — TYPE COMPATIBILITY (COMPREHENSIVE SCOPE FILTERING)
%
% Principle: every relationship type has a declared scope — the set of
% entity-kind tuples it can validly apply to. A relationship applied
% outside its scope is a fatal type error.
%
% Direction 1 — Relationship-to-shape filtering:
%   triangle_proportionality cannot apply to a polygon, circle, segment,
%   point, or line. It only applies to (triangle, segment, segment, ...).
%
% Direction 2 — Shape-to-relationship filtering:
%   A circle cannot be involved in a triangle-specific relationship
%   (Pythagorean, AA/SAS/SSS, altitude_to_hypotenuse, midsegment,
%   triangle_proportionality, etc.).
%   A polygon (n>3) cannot be involved in a triangle-specific relationship.
%   A point cannot have a length, side, or angle measured on it.
%   A segment cannot be tested for angle sum.
%
% The scope/2 predicate is the single source of truth. It encodes which
% kinds are valid in which positions for each relationship type. The
% positional list uses tags:
%   triangle | polygon | segment | point | line | circle
%   any_figure        -- any closed 2-D shape (triangle, polygon, circle)
%   any_polygonal     -- triangle or polygon (not circle)
%   any_2d            -- any of the above
%   any               -- truly any entity (rare; only for generic intersection)
% =====================================================================

% --- Relationship scope declarations ---
% scope(RelType, PositionalKindList)

% Similarity — strictly triangle-on-triangle for AA/SAS/SSS theorems.
scope(similar_AA,             [triangle, triangle]).
scope(similar_SAS,            [triangle, triangle]).
scope(similar_SSS,            [triangle, triangle]).
% Generic similarity allows any-figure-on-any-figure, but kinds must match.
scope(similar_unspecified,    [any_figure, any_figure]).

% Dilation can act on any figure (segment, triangle, polygon, circle).
scope(dilation,               [any_2d, any_2d]).
scope(scaled_copy,            [any_2d, any_2d]).
scope(scaled_copy_unspecified,[any_2d, any_2d]).

% Parallel relationships
scope(parallel_lines,         [line, line]).
scope(parallel_segments,      [segment, segment]).
scope(midsegment_parallel,    [segment, segment]).
scope(transversal_cut,        [line, line, line]).
scope(parallel_lines_transversal, [line, line, line]).

% Angle relationships — entities are angle identifiers (treated as points
% or angle labels). The "shared" angle entities are typically referenced
% by attribute name rather than positional, so we permit any.
scope(vertical_angles,        [any, any]).
scope(adjacent_angles,        [any, any]).
scope(supplementary_angles,   [any, any]).
scope(complementary_angles,   [any, any]).
scope(corresponding_angles,   [any, any]).
scope(alternate_interior_angles, [any, any]).
scope(alternate_exterior_angles, [any, any]).
scope(co_interior_angles,     [any, any]).
scope(linear_pair,            [any, any]).
scope(angle_bisector,         [any, any]).
scope(exterior_angle,         [any, any, any]).

% Angle sums are shape-specific
scope(angle_sum_triangle,     [triangle]).
scope(angle_sum_polygon,      [polygon]).

% Proportional segments — strictly segments
scope(proportional_segments,  [segment, segment]).
scope(midsegment_ratio,       [segment, segment]).

% Triangle-specific theorems — first entity MUST be a triangle.
% Remaining entities are typically segments or points.
scope(triangle_proportionality,  [triangle, segment, segment]).
scope(altitude_to_hypotenuse,    [triangle, segment, segment, segment]).
scope(geometric_mean_altitude,   [triangle, segment, segment]).
scope(geometric_mean_leg,        [triangle, segment, segment]).

% Perpendicularity
scope(perpendicular_lines,    [line, line]).
scope(perpendicular_segments, [segment, segment]).
scope(altitude_perpendicular, [segment, segment]).

% Congruence
scope(congruent_angles,       [list_of_any]).
scope(congruent_segments,     [list_of_segments]).
scope(congruent_triangles,    [triangle, triangle]).

% Dilation-specific point relationships
scope(collinear_dilation,     [point, point, point]).
scope(center_on_figure,       [point, any_figure]).
scope(center_off_figure,      [point, any_figure]).

% Intersection
scope(lines_intersect,        [line, line]).
scope(segments_intersect,     [segment, segment]).
scope(point_on_line,          [point, any_linear]).
scope(point_interior,         [point, any_figure]).

% --- Implicit-aware entity recognition ---
% Mirrors entity_known/1 from Layer 1. A 'point' can be an explicitly declared
% point OR a vertex of a declared triangle/polygon. A 'segment' can be declared
% OR a side of a triangle/polygon OR a segment between two known points.
% Without this, the scope gate rejects relationships referencing implicit
% vertices (A, B, C) and implicit sides (AC) that were never separately declared.

is_point_entity(E)   :- known_point(E).

is_segment_entity(E) :- entity(segment, E).
is_segment_entity(E) :- triangle_side_of_any(E).
is_segment_entity(E) :- polygon_side_of_any(E).
is_segment_entity(E) :- implicit_point_to_point_segment(E).

% --- Kind-compatibility predicate ---
% kind_satisfies(EntityId, ExpectedKindTag)

kind_satisfies(_, any) :- !.
kind_satisfies(_, list_of_any) :- !.

kind_satisfies(E, list_of_segments) :- !,
    is_segment_entity(E).

kind_satisfies(E, any_figure) :- !,
    ( entity(triangle, E)
    ; entity(polygon, E)
    ; entity(circle, E)
    ).

kind_satisfies(E, any_polygonal) :- !,
    ( entity(triangle, E)
    ; entity(polygon, E)
    ).

kind_satisfies(E, any_2d) :- !,
    ( entity(triangle, E)
    ; entity(polygon, E)
    ; entity(circle, E)
    ; is_segment_entity(E)
    ).

kind_satisfies(E, any_linear) :- !,
    ( entity(line, E)
    ; is_segment_entity(E)
    ).

kind_satisfies(E, point)   :- !, is_point_entity(E).
kind_satisfies(E, segment) :- !, is_segment_entity(E).

kind_satisfies(E, Kind) :-
    entity(Kind, E).



% --- gate_relation_scope ---
% Combined check: every relationship's entities must satisfy its scope.
gate_relation_scope :-
    findall(error(scope_violation, fatal, Msg),
            ( relationship(RIdx, Type, Entities),
              scope(Type, ExpectedKinds),
              \+ scope_matches(Entities, ExpectedKinds),
              describe_scope_violation(Type, Entities, ExpectedKinds, Detail),
              format(atom(Msg),
                     "Relationship ~w (index ~w) is out of scope: ~w. Expected kinds ~w; got entities ~w.",
                     [Type, RIdx, Detail, ExpectedKinds, Entities])
            ),
            Errors),
    assert_errors(Errors).

% Variadic scopes (lists) — applies to all entities in the list
scope_matches(Entities, [list_of_any]) :- !,
    forall(member(E, Entities), entity(_, E)).
scope_matches(Entities, [list_of_segments]) :- !,
    forall(member(E, Entities), is_segment_entity(E)).   % was: entity(segment, E)

% Positional scopes — entity count must match expected count
scope_matches(Entities, ExpectedKinds) :-
    length(Entities, N),
    length(ExpectedKinds, N),
    scope_matches_positional(Entities, ExpectedKinds).

scope_matches_positional([], []).
scope_matches_positional([E | Es], [K | Ks]) :-
    kind_satisfies(E, K),
    scope_matches_positional(Es, Ks).

% Friendly diagnostics
describe_scope_violation(Type, Entities, Expected, Detail) :-
    ( length(Entities, N), length(Expected, M), N \= M ->
        format(atom(Detail),
               "wrong number of entities (got ~w, expected ~w for ~w)",
               [N, M, Type])
    ; first_kind_mismatch(Entities, Expected, MismatchE, MismatchK),
      entity(ActualK, MismatchE) ->
        format(atom(Detail),
               "entity '~w' is a ~w but ~w expects a ~w in that position",
               [MismatchE, ActualK, Type, MismatchK])
    ; format(atom(Detail), "kind mismatch", [])
    ).

first_kind_mismatch([E | _], [K | _], E, K) :-
    \+ kind_satisfies(E, K), !.
first_kind_mismatch([_ | Es], [_ | Ks], E, K) :-
    first_kind_mismatch(Es, Ks, E, K).


% --- gate_shape_relevance ---
% Reverse direction: for each shape kind, verify no relationship outside
% its valid set is applied to it. This catches "polygon used in triangle
% relationship" even when scope/2 might not have caught it (e.g. when the
% relationship type uses 'any').

% valid_relationships_for(Kind, ListOfRelTypes)
valid_relationships_for(triangle, [
    similar_AA, similar_SAS, similar_SSS, similar_unspecified,
    dilation, scaled_copy, scaled_copy_unspecified,
    triangle_proportionality, altitude_to_hypotenuse,
    geometric_mean_altitude, geometric_mean_leg,
    angle_sum_triangle, congruent_triangles,
    center_on_figure, center_off_figure, point_interior
]).

valid_relationships_for(polygon, [
    similar_unspecified,
    dilation, scaled_copy, scaled_copy_unspecified,
    angle_sum_polygon,
    center_on_figure, center_off_figure, point_interior
]).

valid_relationships_for(circle, [
    similar_unspecified,
    dilation, scaled_copy, scaled_copy_unspecified,
    center_on_figure, center_off_figure, point_interior
]).

valid_relationships_for(segment, [
    parallel_segments, midsegment_parallel, midsegment_ratio,
    proportional_segments, perpendicular_segments, altitude_perpendicular,
    congruent_segments, segments_intersect,
    triangle_proportionality, altitude_to_hypotenuse,
    geometric_mean_altitude, geometric_mean_leg,
    dilation, scaled_copy, scaled_copy_unspecified,
    point_on_line
]).

valid_relationships_for(line, [
    parallel_lines, transversal_cut, parallel_lines_transversal,
    perpendicular_lines, lines_intersect, point_on_line
]).

valid_relationships_for(point, [
    collinear_dilation, center_on_figure, center_off_figure,
    point_on_line, point_interior,
    % angle relationships reference points/angles as identifiers
    vertical_angles, adjacent_angles, supplementary_angles,
    complementary_angles, corresponding_angles,
    alternate_interior_angles, alternate_exterior_angles,
    co_interior_angles, linear_pair, angle_bisector, exterior_angle
]).

gate_shape_relevance :-
    findall(error(shape_relationship_mismatch, fatal, Msg),
            ( relationship(RIdx, Type, Entities),
              member(E, Entities),
              entity(Kind, E),
              valid_relationships_for(Kind, ValidTypes),
              \+ member(Type, ValidTypes),
              format(atom(Msg),
                     "Relationship ~w (index ~w) cannot apply to ~w '~w'. A ~w can only appear in relationships of type: ~w.",
                     [Type, RIdx, Kind, E, Kind, ValidTypes])
            ),
            Errors),
    assert_errors(Errors).


% --- gate_attribute_kind_consistency ---
% Attribute values that reference entities must point to entities of the
% appropriate kind for the attribute's role. E.g., dilation.center must
% be a point; similar_AA.pre_image must be a triangle.

attribute_kind_expectation(dilation, center, point).
attribute_kind_expectation(dilation, pre_image, any_2d).
attribute_kind_expectation(dilation, image, any_2d).
attribute_kind_expectation(scaled_copy, pre_image, any_2d).
attribute_kind_expectation(scaled_copy, image, any_2d).
attribute_kind_expectation(similar_AA, pre_image, triangle).
attribute_kind_expectation(similar_AA, image, triangle).
attribute_kind_expectation(similar_SAS, pre_image, triangle).
attribute_kind_expectation(similar_SAS, image, triangle).
attribute_kind_expectation(similar_SSS, pre_image, triangle).
attribute_kind_expectation(similar_SSS, image, triangle).
attribute_kind_expectation(similar_unspecified, pre_image, any_figure).
attribute_kind_expectation(similar_unspecified, image, any_figure).
attribute_kind_expectation(congruent_triangles, pre_image, triangle).
attribute_kind_expectation(congruent_triangles, image, triangle).
attribute_kind_expectation(triangle_proportionality, parallel_side, segment).
attribute_kind_expectation(triangle_proportionality, segment1, segment).
attribute_kind_expectation(triangle_proportionality, segment2, segment).
attribute_kind_expectation(altitude_to_hypotenuse, altitude_id, segment).
attribute_kind_expectation(altitude_to_hypotenuse, hypotenuse, segment).
attribute_kind_expectation(altitude_to_hypotenuse, segment1, segment).
attribute_kind_expectation(altitude_to_hypotenuse, segment2, segment).
attribute_kind_expectation(geometric_mean_altitude, altitude_id, segment).
attribute_kind_expectation(geometric_mean_altitude, segment1, segment).
attribute_kind_expectation(geometric_mean_altitude, segment2, segment).
attribute_kind_expectation(geometric_mean_leg, leg_id, segment).
attribute_kind_expectation(geometric_mean_leg, hypotenuse, segment).
attribute_kind_expectation(geometric_mean_leg, adjacent_segment, segment).
attribute_kind_expectation(transversal_cut, transversal, line).
attribute_kind_expectation(transversal_cut, line1, line).
attribute_kind_expectation(transversal_cut, line2, line).
attribute_kind_expectation(parallel_lines_transversal, transversal, line).
attribute_kind_expectation(parallel_lines_transversal, line1, line).
attribute_kind_expectation(parallel_lines_transversal, line2, line).
attribute_kind_expectation(collinear_dilation, center, point).
attribute_kind_expectation(collinear_dilation, pre_image_point, point).
attribute_kind_expectation(collinear_dilation, image_point, point).
attribute_kind_expectation(angle_sum_triangle, triangle_id, triangle).
attribute_kind_expectation(angle_sum_polygon, polygon_id, polygon).

gate_attribute_kind_consistency :-
    findall(error(attribute_kind_mismatch, fatal, Msg),
            ( relationship(RIdx, Type, _),
              rel_attr(RIdx, Key, Value),
              atom(Value),
              attribute_kind_expectation(Type, Key, ExpectedKind),
              entity(ActualKind, Value),
              \+ kind_satisfies(Value, ExpectedKind),
              format(atom(Msg),
                     "Relationship ~w (index ~w) attribute '~w' expects a ~w but got ~w '~w'.",
                     [Type, RIdx, Key, ExpectedKind, ActualKind, Value])
            ),
            Errors),
    assert_errors(Errors).

% =====================================================================
% LAYER 3 — MATHEMATICAL VALIDATION
% =====================================================================

% --- gate_positive_lengths ---
gate_positive_lengths :-
    findall(error(non_positive_length, contradiction, Msg),
            ( ( triangle_side(T, K, V), known(V), V =< 0,
                format(atom(Msg),
                       "Triangle ~w side ~w = ~w is non-positive. All side lengths must be > 0.",
                       [T, K, V])
              ; polygon_side(P, K, V), known(V), V =< 0,
                format(atom(Msg),
                       "Polygon ~w side ~w = ~w is non-positive.",
                       [P, K, V])
              ; segment_length(S, V), known(V), V =< 0,
                format(atom(Msg),
                       "Segment ~w length = ~w is non-positive.",
                       [S, V])
              ; circle_radius(C, V), known(V), V =< 0,
                format(atom(Msg),
                       "Circle ~w radius = ~w is non-positive.",
                       [C, V])
              )
            ),
            Errors),
    assert_errors(Errors).

% --- gate_angle_range ---
gate_angle_range :-
    findall(error(angle_out_of_range, contradiction, Msg),
            ( ( triangle_angle(T, K, V), known(V), (V =< 0 ; V >= 180),
                format(atom(Msg),
                       "Triangle ~w angle ~w = ~w° is outside the valid range (0°, 180°).",
                       [T, K, V])
              ; polygon_angle(P, K, V), known(V), (V =< 0 ; V >= 360),
                format(atom(Msg),
                       "Polygon ~w angle ~w = ~w° is outside the valid range.",
                       [P, K, V])
              )
            ),
            Errors),
    assert_errors(Errors).

% --- gate_triangle_angle_sum ---
% If all 3 angles are known, they must sum to 180°.
gate_triangle_angle_sum :-
    findall(error(angle_sum_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_angle(T, K1, V1), triangle_angle(T, K2, V2), triangle_angle(T, K3, V3),
              K1 @< K2, K2 @< K3,
              known(V1), known(V2), known(V3),
              Sum is V1 + V2 + V3,
              \+ approx_equal(Sum, 180),
              format(atom(Msg),
                     "Triangle ~w angles (~w=~w°, ~w=~w°, ~w=~w°) sum to ~w°, not 180°.",
                     [T, K1, V1, K2, V2, K3, V3, Sum])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_triangle_inequality ---
% If all 3 sides are known, each must be less than the sum of the other two.
gate_triangle_inequality :-
    findall(error(triangle_inequality_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_three_sides(T, S1, S2, S3, V1, V2, V3),
              known(V1), known(V2), known(V3),
              \+ triangle_inequality_holds(V1, V2, V3),
              format(atom(Msg),
                     "Triangle ~w sides (~w=~w, ~w=~w, ~w=~w) violate the triangle inequality. Each side must be less than the sum of the other two.",
                     [T, S1, V1, S2, V2, S3, V3])
            ),
            Errors),
    assert_errors(Errors).

triangle_three_sides(T, S1, S2, S3, V1, V2, V3) :-
    triangle_side(T, S1, V1),
    triangle_side(T, S2, V2),
    triangle_side(T, S3, V3),
    S1 @< S2, S2 @< S3.

triangle_inequality_holds(A, B, C) :-
    A + B > C, B + C > A, A + C > B.

% --- gate_pythagorean ---
% If triangle is flagged is_right and all 3 sides are known, must satisfy a²+b²=c².
gate_pythagorean :-
    findall(error(pythagorean_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_right),
              triangle_three_sides(T, _S1, _S2, _S3, V1, V2, V3),
              known(V1), known(V2), known(V3),
              max_list([V1, V2, V3], Hyp),
              select(Hyp, [V1, V2, V3], [A, B]),
              HypSq is Hyp * Hyp,
              LegSumSq is A * A + B * B,
              \+ approx_equal(HypSq, LegSumSq),
              format(atom(Msg),
                     "Triangle ~w is declared right, but sides (~w, ~w, ~w) fail a²+b²=c². Got ~w² + ~w² = ~w but ~w² = ~w.",
                     [T, V1, V2, V3, A, B, LegSumSq, Hyp, HypSq])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_pythagorean_classification ---
% Converse: if all 3 sides known AND is_right flag is EXPLICITLY declared,
% check it matches the classification. If the flag is absent, the gate is silent —
% absence is not a claim.
gate_pythagorean_classification :-
    findall(error(right_flag_inconsistent, contradiction, Msg),
            ( entity(triangle, T),
              triangle_three_sides(T, _, _, _, V1, V2, V3),
              known(V1), known(V2), known(V3),
              triangle_right_flag_declared(T, Declared),
              max_list([V1, V2, V3], Hyp),
              select(Hyp, [V1, V2, V3], [A, B]),
              HypSq is Hyp * Hyp,
              LegSumSq is A * A + B * B,
              ( approx_equal(HypSq, LegSumSq) -> Actually = right
              ; HypSq > LegSumSq              -> Actually = obtuse
              ;                                  Actually = acute
              ),
              ( Declared == true,  Actually \= right
              ; Declared == false, Actually == right
              ),
              format(atom(Msg),
                     "Triangle ~w side lengths (~w, ~w, ~w) classify it as ~w, which conflicts with is_right = ~w.",
                     [T, V1, V2, V3, Actually, Declared])
            ),
            Errors),
    assert_errors(Errors).

% True iff is_right is explicitly declared (either true or false) on T.
triangle_right_flag_declared(T, true) :- triangle_flag(T, is_right).
triangle_right_flag_declared(T, false) :- triangle_flag(T, is_not_right).

% --- gate_equilateral_consistency ---
gate_equilateral_consistency :-
    findall(error(equilateral_inconsistent, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_equilateral),
              triangle_three_sides(T, S1, S2, S3, V1, V2, V3),
              known(V1), known(V2), known(V3),
              \+ (approx_equal(V1, V2), approx_equal(V2, V3)),
              format(atom(Msg),
                     "Triangle ~w is declared equilateral but sides (~w=~w, ~w=~w, ~w=~w) are not all equal.",
                     [T, S1, V1, S2, V2, S3, V3])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_isosceles_consistency ---
gate_isosceles_consistency :-
    findall(error(isosceles_inconsistent, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_isosceles),
              triangle_three_sides(T, _, _, _, V1, V2, V3),
              known(V1), known(V2), known(V3),
              \+ ( approx_equal(V1, V2)
                 ; approx_equal(V2, V3)
                 ; approx_equal(V1, V3) ),
              format(atom(Msg),
                     "Triangle ~w is declared isosceles but no two sides among (~w, ~w, ~w) are equal.",
                     [T, V1, V2, V3])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_right_angle_flag_consistency ---
% If a triangle has an explicitly declared 90° angle, is_right should be true.
% Conversely, if is_right is declared true, at least one angle should be 90°
% (when angles are declared at all).
gate_right_angle_flag_consistency :-
    findall(error(right_flag_missing_for_90_angle, structural, Msg),
            ( entity(triangle, T),
              triangle_angle(T, K, 90),
              \+ triangle_flag(T, is_right),
              format(atom(Msg),
                     "Triangle ~w has angle ~w = 90° but is_right is not declared as true. When an explicit 90° angle is present, is_right should be set accordingly.",
                     [T, K])
            ),
            Errors1),
    findall(error(right_flag_without_90_angle, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_right),
              findall(V, triangle_angle(T, _, V), Vs),
              length(Vs, N), N >= 1,
              forall(member(V, Vs), V \= 90),
              format(atom(Msg),
                     "Triangle ~w is declared is_right = true but none of its declared angles is 90° (declared angles: ~w).",
                     [T, Vs])
            ),
            Errors2),
    append(Errors1, Errors2, Errors),
    assert_errors(Errors).

% --- gate_law_of_cosines_consistency ---
% For every triangle with all 3 sides known AND at least 1 angle known,
% verify the Law of Cosines: cos(C) = (a² + b² - c²) / (2ab),
% where c is the side opposite angle C and a, b are the other two sides.
%
% In a triangle ABC, angle A is opposite side BC, angle B is opposite AC,
% angle C is opposite AB. We use vertex-to-opposite-side mapping:
%   angle X ↔ side made of the two letters of ABC that are NOT X.
gate_law_of_cosines_consistency :-
    findall(error(law_of_cosines_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_three_sides(T, _, _, _, _, _, _),
              all_three_sides_known(T, A, B, C),
              triangle_angle(T, AngleKey, AngleDeg),
              known(AngleDeg),
              opposite_side_length(T, AngleKey, OppLen, Side1Len, Side2Len),
              OppLen = C, Side1Len = A, Side2Len = B,  % bind for clarity
              cos_from_angle(AngleDeg, CosA),
              Denom is 2 * Side1Len * Side2Len,
              Denom > 0,
              CosFromSides is (Side1Len * Side1Len + Side2Len * Side2Len - OppLen * OppLen) / Denom,
              \+ approx_equal(CosA, CosFromSides),
              ImpliedDeg is acos(CosFromSides) * 180 / pi,
              format(atom(Msg),
                     "Triangle ~w fails the Law of Cosines: angle ~w is declared as ~w° but the side lengths imply it must be ~2f° (cos = ~3f from sides vs cos = ~3f from angle).",
                     [T, AngleKey, AngleDeg, ImpliedDeg, CosFromSides, CosA])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_law_of_sines_consistency ---
% For every triangle, if 2+ (angle, opposite-side) pairs are known,
% they must satisfy a/sin(A) = b/sin(B) = c/sin(C).
gate_law_of_sines_consistency :-
    findall(error(law_of_sines_violation, contradiction, Msg),
            ( entity(triangle, T),
              law_of_sines_pair(T, AngleKey1, AngleDeg1, OppLen1),
              law_of_sines_pair(T, AngleKey2, AngleDeg2, OppLen2),
              AngleKey1 @< AngleKey2,
              Sin1 is sin(AngleDeg1 * pi / 180),
              Sin2 is sin(AngleDeg2 * pi / 180),
              Sin1 > 0, Sin2 > 0,
              Ratio1 is OppLen1 / Sin1,
              Ratio2 is OppLen2 / Sin2,
              \+ approx_equal(Ratio1, Ratio2),
              format(atom(Msg),
                     "Triangle ~w fails the Law of Sines: side opposite angle ~w is ~w with angle ~w° (ratio ~2f), but side opposite angle ~w is ~w with angle ~w° (ratio ~2f). These ratios must be equal.",
                     [T, AngleKey1, OppLen1, AngleDeg1, Ratio1, AngleKey2, OppLen2, AngleDeg2, Ratio2])
            ),
            Errors),
    assert_errors(Errors).

% --- Helper: extract all three known sides in a canonical (A, B, C) order ---
all_three_sides_known(T, A, B, C) :-
    triangle_side(T, S1, A), known(A),
    triangle_side(T, S2, B), known(B),
    triangle_side(T, S3, C), known(C),
    S1 @< S2, S2 @< S3.

% --- Helper: given an angle key in a triangle, return the opposite side length
% and the two adjacent side lengths.
% In triangle XYZ:
%   angle X ↔ side YZ (opposite)
%   angle Y ↔ side XZ (opposite)
%   angle Z ↔ side XY (opposite)
opposite_side_length(T, AngleKey, OppLen, Adj1, Adj2) :-
    atom_codes(T, [V1, V2, V3]),
    atom_codes(AngleKey, [VA]),
    member(VA, [V1, V2, V3]),
    % The opposite side is made from the two vertices that are not VA.
    select(VA, [V1, V2, V3], [Other1, Other2]),
    opposite_side_id(Other1, Other2, OppId),
    adjacent_side_ids(VA, Other1, Other2, AdjId1, AdjId2),
    triangle_side(T, OppId, OppLen), known(OppLen),
    triangle_side(T, AdjId1, Adj1), known(Adj1),
    triangle_side(T, AdjId2, Adj2), known(Adj2).

% Try both orderings of the two non-vertex letters since side keys may be
% written either way (e.g. "BC" or "CB"; convention is alphabetical but
% we accept both for robustness).
opposite_side_id(V1, V2, Id) :-
    ( pair_to_atom(V1, V2, Id), triangle_side(_, Id, _)
    ; pair_to_atom(V2, V1, Id), triangle_side(_, Id, _)
    ).

adjacent_side_ids(Vertex, Other1, Other2, AdjId1, AdjId2) :-
    ( pair_to_atom(Vertex, Other1, AdjId1), triangle_side(_, AdjId1, _)
    ; pair_to_atom(Other1, Vertex, AdjId1), triangle_side(_, AdjId1, _)
    ),
    ( pair_to_atom(Vertex, Other2, AdjId2), triangle_side(_, AdjId2, _)
    ; pair_to_atom(Other2, Vertex, AdjId2), triangle_side(_, AdjId2, _)
    ).

cos_from_angle(Deg, Cos) :-
    Cos is cos(Deg * pi / 180).

% A (side, angle) pair where the angle is given and its opposite side is known.
law_of_sines_pair(T, AngleKey, AngleDeg, OppLen) :-
    triangle_angle(T, AngleKey, AngleDeg), known(AngleDeg),
    opposite_side_length(T, AngleKey, OppLen, _, _).

% --- gate_scale_factor_matches_declared_sides ---
% For any scaling relationship (dilation, scaled_copy, similarity) with a
% declared scale factor AND at least one corresponding-side pair both known,
% verify image_side = pre_image_side × scale_factor.
% When the math doesn't match, surface both the predicted image value
% (from the declared scale factor) and the implied scale factor (from the
% declared image value) so the caller can see which one was likely intended.
gate_scale_factor_matches_declared_sides :-
    findall(error(scale_factor_mismatch, contradiction, Msg),
            ( relationship(RIdx, Type, _),
              scaling_relationship_type(Type),
              rel_attr(RIdx, pre_image, Pre),
              rel_attr(RIdx, image, Img),
              rel_attr(RIdx, scale_factor, K), known(K),
              scaling_corresponding_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV),
              known(PreV), known(ImgV),
              Expected is PreV * K,
              \+ approx_equal(Expected, ImgV),
              Implied is ImgV / PreV,
              format(atom(Msg),
                     "Relationship ~w (index ~w): ~w.~w = ~w with scale factor ~w predicts ~w.~w = ~w, but ~w.~w is declared as ~w. The declared pair implies scale factor ~3f.",
                     [Type, RIdx, Pre, PreSide, PreV, K, Img, ImgSide, Expected, Img, ImgSide, ImgV, Implied])
            ),
            Errors),
    assert_errors(Errors).

scaling_relationship_type(dilation).
scaling_relationship_type(scaled_copy).
scaling_relationship_type(scaled_copy_unspecified).
scaling_relationship_type(similar_AA).
scaling_relationship_type(similar_SAS).
scaling_relationship_type(similar_SSS).
scaling_relationship_type(similar_unspecified).

% Unified corresponding-side iterator across triangles, polygons, segments, circles.
scaling_corresponding_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV) :-
    entity(triangle, Pre), entity(triangle, Img),
    corresponding_side_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV).
scaling_corresponding_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV) :-
    entity(polygon, Pre), entity(polygon, Img),
    polygon_corresponding_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV).
scaling_corresponding_pair(Pre, Img, length, length, PreV, ImgV) :-
    entity(segment, Pre), entity(segment, Img),
    segment_length(Pre, PreV),
    segment_length(Img, ImgV).
scaling_corresponding_pair(Pre, Img, radius, radius, PreV, ImgV) :-
    entity(circle, Pre), entity(circle, Img),
    circle_radius(Pre, PreV),
    circle_radius(Img, ImgV).

% --- gate_scale_factor_positive ---
gate_scale_factor_positive :-
    findall(error(non_positive_scale_factor, contradiction, Msg),
            ( relationship(RIdx, Type, _),
              member(Type, [dilation, scaled_copy, similar_AA, similar_SAS, similar_SSS]),
              rel_attr(RIdx, scale_factor, K), known(K), K =< 0,
              format(atom(Msg),
                     "Relationship ~w (index ~w) has scale factor ~w. Scale factors must be > 0.",
                     [Type, RIdx, K])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_scale_factor_consistency_across_pairs ---
% When a dilation/scaled_copy/similarity has multiple corresponding-side pairs
% with both endpoints known, the implied scale factor must be the same for
% every pair. This catches inconsistent scalings whether or not scale_factor
% is declared.
gate_scale_factor_consistency_across_pairs :-
    findall(error(scale_factor_inconsistent_across_pairs, contradiction, Msg),
            ( relationship(RIdx, Type, _),
              member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                            similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
              rel_attr(RIdx, pre_image, Pre),
              rel_attr(RIdx, image, Img),
              known_corresponding_pairs(Pre, Img, Pairs),
              length(Pairs, N), N >= 2,
              \+ all_pairs_same_ratio(Pairs),
              format_pair_ratios(Pairs, PairStr),
              format(atom(Msg),
                     "Relationship ~w (index ~w) has multiple corresponding-side pairs that imply different scale factors: ~w. All pairs must yield the same ratio.",
                     [Type, RIdx, PairStr])
            ),
            Errors),
    assert_errors(Errors).

% Collect all (PreSide, ImgSide, PreV, ImgV) tuples where both values are known.
known_corresponding_pairs(Pre, Img, Pairs) :-
    ( entity(triangle, Pre), entity(triangle, Img) ->
        findall(pair(PS, IS, PV, IV),
                ( corresponding_side_pair(Pre, Img, PS, IS, PV, IV),
                  known(PV), known(IV) ),
                Pairs0)
    ; entity(polygon, Pre), entity(polygon, Img) ->
        findall(pair(PS, IS, PV, IV),
                ( polygon_corresponding_pair(Pre, Img, PS, IS, PV, IV),
                  known(PV), known(IV) ),
                Pairs0)
    ; Pairs0 = []
    ),
    list_to_set(Pairs0, Pairs).

polygon_corresponding_pair(Pre, Img, PreKey, ImgKey, PreV, ImgV) :-
    findall(K-V, polygon_side(Pre, K, V), PreList),
    findall(K-V, polygon_side(Img, K, V), ImgList),
    nth0(N, PreList, PreKey-PreV),
    nth0(N, ImgList, ImgKey-ImgV).

all_pairs_same_ratio([_]).
all_pairs_same_ratio([pair(_, _, P1, I1), pair(_, _, P2, I2) | Rest]) :-
    P1 > 0, P2 > 0,
    R1 is I1 / P1,
    R2 is I2 / P2,
    approx_equal(R1, R2),
    all_pairs_same_ratio([pair(_, _, P2, I2) | Rest]).

format_pair_ratios([], "").
format_pair_ratios([pair(PS, IS, PV, IV) | Rest], Out) :-
    ( PV > 0 -> R is IV / PV ; R = undefined ),
    format(atom(First), "~w/~w = ~w/~w (~3f)", [IS, PS, IV, PV, R]),
    format_pair_ratios(Rest, RestStr),
    ( RestStr == "" -> Out = First
    ; atom_concat(First, ", ", Tmp), atom_concat(Tmp, RestStr, Out)
    ).

corresponding_side_pair(Pre, Img, PreSide, ImgSide, PreV, ImgV) :-
    entity(triangle, Pre), entity(triangle, Img),
    triangle_side(Pre, PreSide, PreV),
    triangle_side(Img, ImgSide, ImgV),
    side_position_match(Pre, PreSide, Img, ImgSide).

% Side position: in triangle ABC, side AB is position 1, BC is 2, CA is 3.
side_position_match(T1, S1, T2, S2) :-
    side_position(T1, S1, P),
    side_position(T2, S2, P).

side_position(T, Side, Pos) :-
    atom_codes(T, [A, B, C]),
    pair_to_atom(A, B, S1), pair_to_atom(B, C, S2), pair_to_atom(C, A, S3),
    nth1(Pos, [S1, S2, S3], Side).

% --- gate_similarity_corresponding_pairs ---
% For an n-sided polygon, similarity requires n corresponding sides and n-1 angles.
gate_similarity_corresponding_pairs :-
    findall(error(insufficient_similarity_evidence, underdetermined, Msg),
            ( relationship(_RIdx, Type, [E1, E2]),
              member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
              entity(polygon, E1), entity(polygon, E2),
              polygon_n_sides(E1, N),
              similarity_corresponding_sides_required(N, NeedSides),
              similarity_corresponding_angles_required(N, NeedAngles),
              count_corresponding_sides(E1, E2, GivenSides),
              count_corresponding_angles(E1, E2, GivenAngles),
              GivenSides < NeedSides,
              GivenAngles < NeedAngles,
              format(atom(Msg),
                     "Similarity between polygons ~w and ~w (n=~w) requires ~w corresponding sides and ~w corresponding angles. Only ~w sides and ~w angles are given. Similarity is under-determined.",
                     [E1, E2, N, NeedSides, NeedAngles, GivenSides, GivenAngles])
            ),
            Errors),
    assert_errors(Errors).

count_corresponding_sides(P1, P2, Count) :-
    findall(K, ( polygon_side(P1, K, V1), known(V1),
                 polygon_side(P2, K, V2), known(V2) ), Ks),
    length(Ks, Count).

count_corresponding_angles(P1, P2, Count) :-
    findall(K, ( polygon_angle(P1, K, V1), known(V1),
                 polygon_angle(P2, K, V2), known(V2) ), Ks),
    length(Ks, Count).

% --- gate_aa_similarity_two_pairs ---
% similar_AA requires at least TWO pairs of congruent angles to establish
% similarity. The pairs may be declared explicitly in congruent_angle_pairs,
% OR they may be derivable: if a triangle has 2 angles known (or its angle
% sum is explicitly invoked), the third angle is determined, and any matching
% angles between the two triangles count as a congruent pair.
gate_aa_similarity_two_pairs :-
    findall(error(aa_underspecified, underdetermined, Msg),
            ( relationship(RIdx, similar_AA, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              ( rel_attr(RIdx, congruent_angle_pairs, Pairs) -> true ; Pairs = [] ),
              length(Pairs, NDeclared),
              count_derivable_congruent_angle_pairs(T1, T2, NDerived),
              TotalKnown is max(NDeclared, NDerived),
              TotalKnown < 2,
              format(atom(Msg),
                     "similar_AA (relationship ~w) requires at least 2 congruent angle pairs between ~w and ~w. Currently ~w pair(s) explicit + ~w derivable via Triangle Angle Sum. Either declare more angles on each triangle, declare more congruent_angle_pairs, or use a different similarity criterion.",
                     [RIdx, T1, T2, NDeclared, NDerived])
            ),
            Errors),
    assert_errors(Errors).

% Count congruent angle pairs derivable from declared angles (including those
% inferred via the Triangle Angle Sum when 2+ angles are declared on a triangle).
count_derivable_congruent_angle_pairs(T1, T2, N) :-
    triangle_all_angles_resolved(T1, A1List),
    triangle_all_angles_resolved(T2, A2List),
    findall(1,
            ( member(_-V1, A1List), known(V1),
              member(_-V2, A2List), known(V2),
              approx_equal(V1, V2)
            ),
            Ones),
    length(Ones, N).

% Returns the list of (key-value) pairs for all three angles of a triangle,
% with values resolved via Triangle Angle Sum when exactly 2 of 3 are known.
triangle_all_angles_resolved(T, Resolved) :-
    findall(K-V, triangle_angle(T, K, V), Raw),
    length(Raw, 3),
    findall(K-V, (member(K-V, Raw), known(V)), Known),
    length(Known, NumKnown),
    ( NumKnown == 3 ->
        Resolved = Raw
    ; NumKnown == 2 ->
        member(MissingK-_Unknown, Raw), \+ ( member(MissingK-MV, Known), known(MV) ),
        findall(KV, member(_-KV, Known), KnownVs),
        sumlist(KnownVs, S),
        Missing is 180 - S,
        select(MissingK-_, Raw, Rest),
        Resolved = [MissingK-Missing | Rest]
    ; triangle_flag(T, is_equilateral) ->
        findall(K-60, member(K-_, Raw), Resolved)
    ; Resolved = Raw
    ).

% --- gate_sss_similarity_three_sides ---
gate_sss_similarity_three_sides :-
    findall(error(sss_underspecified, underdetermined, Msg),
            ( relationship(RIdx, similar_SSS, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              count_known_sides(T1, K1),
              count_known_sides(T2, K2),
              ( K1 < 3 ; K2 < 3 ),
              format(atom(Msg),
                     "similar_SSS (relationship ~w) between ~w and ~w requires all 3 sides known on both triangles. Currently ~w has ~w known sides and ~w has ~w.",
                     [RIdx, T1, T2, T1, K1, T2, K2])
            ),
            Errors),
    assert_errors(Errors).

count_known_sides(T, N) :-
    findall(K, (triangle_side(T, K, V), known(V)), Ks),
    length(Ks, N).

% --- gate_sas_similarity_complete ---
% SAS needs 2 sides + included angle on both triangles.
gate_sas_similarity_complete :-
    findall(error(sas_underspecified, underdetermined, Msg),
            ( relationship(RIdx, similar_SAS, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              count_known_sides(T1, K1),
              count_known_sides(T2, K2),
              count_known_angles(T1, A1),
              count_known_angles(T2, A2),
              ( K1 < 2 ; K2 < 2 ; A1 < 1 ; A2 < 1 ),
              format(atom(Msg),
                     "similar_SAS (relationship ~w) requires 2 sides + 1 included angle on each triangle. ~w has ~w sides/~w angles; ~w has ~w sides/~w angles.",
                     [RIdx, T1, K1, A1, T2, K2, A2])
            ),
            Errors),
    assert_errors(Errors).

% Count known angles, including those implicit from triangle flags:
%   - is_equilateral implies all three angles are 60° (so 3 known)
%   - is_isosceles implies one pair of angles is equal (so at least 1 known
%     relational angle, but no specific values; we count as 0 explicit
%     unless combined with another fact)
% Count known angles, including those implicit from triangle flags:
%   - is_equilateral implies all three angles are 60° (so 3 known)
%   - is_right implies one angle is 90° (so +1 to the explicit count, unless
%     a declared angle already equals 90°)
%   - is_isosceles implies one pair of angles is equal but no specific values;
%     does not contribute to the count of known specific angles.
count_known_angles(T, N) :-
    findall(K, (triangle_angle(T, K, V), known(V)), Explicit),
    length(Explicit, Ne),
    findall(V, (triangle_angle(T, _, V), known(V), V =:= 90), Right90s),
    length(Right90s, NumExplicit90),
    ( triangle_flag(T, is_equilateral) ->
        N = 3
    ; triangle_flag(T, is_right), NumExplicit90 == 0 ->
        N is Ne + 1
    ; N = Ne
    ).

% --- gate_invariant_constants ---
% Enforce the "always" values from the prompt spec.
gate_invariant_constants :-
    findall(error(invariant_violation, contradiction, Msg),
            ( ( relationship(RIdx, supplementary_angles, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg),
                       "supplementary_angles (relationship ~w) declares sum=~w; it must always be 180.",
                       [RIdx, V])
              ; relationship(RIdx, complementary_angles, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 90),
                format(atom(Msg),
                       "complementary_angles (relationship ~w) declares sum=~w; it must always be 90.",
                       [RIdx, V])
              ; relationship(RIdx, linear_pair, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg),
                       "linear_pair (relationship ~w) declares sum=~w; it must always be 180.",
                       [RIdx, V])
              ; relationship(RIdx, midsegment_ratio, _),
                rel_attr(RIdx, ratio, V), known(V), \+ approx_equal(V, 0.5),
                format(atom(Msg),
                       "midsegment_ratio (relationship ~w) declares ratio=~w; it must always be 0.5.",
                       [RIdx, V])
              ; relationship(RIdx, angle_sum_triangle, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg),
                       "angle_sum_triangle (relationship ~w) declares sum=~w; it must always be 180.",
                       [RIdx, V])
              ; relationship(RIdx, angle_sum_polygon, _),
                rel_attr(RIdx, exterior_sum, V), known(V), \+ approx_equal(V, 360),
                format(atom(Msg),
                       "angle_sum_polygon (relationship ~w) declares exterior_sum=~w; it must always be 360.",
                       [RIdx, V])
              )
            ),
            Errors),
    assert_errors(Errors).

% --- gate_polygon_interior_sum ---
% Interior sum of n-sided polygon = (n-2) * 180.
gate_polygon_interior_sum :-
    findall(error(polygon_interior_sum_wrong, contradiction, Msg),
            ( relationship(RIdx, angle_sum_polygon, _),
              rel_attr(RIdx, num_sides, N), known(N),
              rel_attr(RIdx, interior_sum, S), known(S),
              Expected is (N - 2) * 180,
              \+ approx_equal(S, Expected),
              format(atom(Msg),
                     "Polygon with ~w sides has interior angle sum (n-2)*180 = ~w°, not ~w°.",
                     [N, Expected, S])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_vacuous_angle_sum_relationship ---
% An angle_sum_triangle relationship contributes information only when at
% least 2 of the triangle's 3 angles are independently declared, allowing
% the third to be derived. With fewer than 2 known angles, the relationship
% restates the universal truth that angles sum to 180° without constraining
% anything; pedagogically it is dead weight.
% Similarly, angle_sum_polygon contributes only when n-1 angles are declared.
gate_vacuous_angle_sum_relationship :-
    findall(error(vacuous_angle_sum_relationship, structural, Msg),
            ( relationship(RIdx, angle_sum_triangle, _),
              rel_attr(RIdx, triangle_id, T),
              entity(triangle, T),
              count_explicit_known_angles(T, NA),
              NA < 2,
              format(atom(Msg),
                     "angle_sum_triangle (index ~w) is declared for triangle ~w but only ~w angle(s) are independently known. The relationship adds no constraint unless at least 2 angles are declared, allowing the third to be derived.",
                     [RIdx, T, NA])
            ),
            Errors1),
    findall(error(vacuous_angle_sum_relationship, structural, Msg),
            ( relationship(RIdx, angle_sum_polygon, _),
              rel_attr(RIdx, polygon_id, P),
              entity(polygon, P),
              polygon_n_sides(P, N),
              count_explicit_known_polygon_angles(P, NA),
              Needed is N - 1,
              NA < Needed,
              format(atom(Msg),
                     "angle_sum_polygon (index ~w) is declared for polygon ~w (n=~w) but only ~w angle(s) are independently known. The relationship adds no constraint unless at least ~w angles are declared, allowing the last to be derived.",
                     [RIdx, P, N, NA, Needed])
            ),
            Errors2),
    append(Errors1, Errors2, Errors),
    assert_errors(Errors).

count_explicit_known_angles(T, N) :-
    findall(K, (triangle_angle(T, K, V), known(V)), Ks),
    length(Ks, N).

count_explicit_known_polygon_angles(P, N) :-
    findall(K, (polygon_angle(P, K, V), known(V)), Ks),
    length(Ks, N).

% --- gate_midsegment_consistency ---
% A midsegment must be parallel to a side of the triangle and half its length.
gate_midsegment_consistency :-
    findall(error(midsegment_inconsistent, contradiction, Msg),
            ( entity(segment, S),
              segment_flag(S, is_midsegment),
              segment_parallel_to(S, Side),
              segment_length(S, SV), known(SV),
              ( triangle_side(_, Side, BV)
              ; segment_length(Side, BV)
              ),
              known(BV),
              \+ approx_equal(SV, BV / 2),
              format(atom(Msg),
                     "Segment ~w is declared a midsegment parallel to ~w; midsegment length should be half of ~w (=~w), but is declared ~w.",
                     [S, Side, BV, BV/2, SV])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_altitude_to_hypotenuse_consistency ---
% The two segments must sum to the hypotenuse.
gate_altitude_to_hypotenuse_consistency :-
    findall(error(altitude_split_inconsistent, contradiction, Msg),
            ( relationship(RIdx, altitude_to_hypotenuse, _),
              rel_attr(RIdx, hypotenuse, Hyp),
              rel_attr(RIdx, segment1, Seg1),
              rel_attr(RIdx, segment2, Seg2),
              segment_or_side_length(Hyp, HV),
              segment_or_side_length(Seg1, V1),
              segment_or_side_length(Seg2, V2),
              known(HV), known(V1), known(V2),
              Sum is V1 + V2,
              \+ approx_equal(Sum, HV),
              format(atom(Msg),
                     "altitude_to_hypotenuse: segments ~w (~w) and ~w (~w) should sum to hypotenuse ~w (~w), got ~w.",
                     [Seg1, V1, Seg2, V2, Hyp, HV, Sum])
            ),
            Errors),
    assert_errors(Errors).

segment_or_side_length(Id, V) :- segment_length(Id, V).
segment_or_side_length(Id, V) :- triangle_side(_, Id, V).

% --- gate_collinear_dilation_consistency ---
% Center, pre-image point, image point must be collinear with image = center + k*(pre - center).
gate_collinear_dilation_consistency :-
    findall(error(collinear_dilation_inconsistent, contradiction, Msg),
            ( relationship(RIdx, collinear_dilation, _),
              rel_attr(RIdx, center, C),
              rel_attr(RIdx, pre_image_point, PreP),
              rel_attr(RIdx, image_point, ImgP),
              find_companion_dilation_scale(C, PreP, ImgP, K),
              K =< 0,
              format(atom(Msg),
                     "collinear_dilation with center ~w, pre-image point ~w, image point ~w has non-positive companion scale factor ~w.",
                     [C, PreP, ImgP, K])
            ),
            Errors),
    assert_errors(Errors).

% Look up scale factor from a sibling dilation relationship if available.
find_companion_dilation_scale(C, _, _, K) :-
    relationship(_, dilation, _Es),
    rel_attr(RIdx2, center, C),
    relationship(RIdx2, dilation, _),
    rel_attr(RIdx2, scale_factor, K), known(K).
find_companion_dilation_scale(_, _, _, 1).  % default fallback

% --- gate_collinear_dilation_center_matches_parent ---
% Every collinear_dilation declared alongside a parent dilation must share
% the parent's center. The two cannot disagree on where the dilation is
% centered.
gate_collinear_dilation_center_matches_parent :-
    findall(error(collinear_dilation_center_mismatch, contradiction, Msg),
            ( relationship(RIdx, collinear_dilation, _),
              rel_attr(RIdx, center, CDCenter),
              relationship(ParentIdx, dilation, _),
              rel_attr(ParentIdx, center, ParentCenter), known(ParentCenter),
              CDCenter \= ParentCenter,
              format(atom(Msg),
                     "collinear_dilation (index ~w) declares center ~w but the parent dilation (index ~w) declares center ~w. The center must be shared across both relationships.",
                     [RIdx, CDCenter, ParentIdx, ParentCenter])
            ),
            Errors),
    assert_errors(Errors).

% --- gate_point_position_consistency ---
% A point that is declared as the image of another point under a dilation
% centered at C lies on the line through C and the pre-image point (i.e.,
% on segment from C to the pre-image). If the schema also asserts that
% the image point lies on a DIFFERENT segment that does not pass through
% both C and the pre-image, the two claims are contradictory.
gate_point_position_consistency :-
    findall(error(point_position_inconsistent, contradiction, Msg),
            ( relationship(_, collinear_dilation, _Es),
              rel_attr(CDIdx, center, C),
              rel_attr(CDIdx, pre_image_point, PreP),
              rel_attr(CDIdx, image_point, ImgP),
              relationship(CDIdx, collinear_dilation, _),
              % ImgP claims to lie on some segment SegId
              point_lies_on(ImgP, SegId),
              % SegId must contain the line through C and PreP for the claim
              % to be consistent. Express this as: SegId must include both C
              % and PreP as endpoints, OR ImgP must be a known midpoint /
              % endpoint of a segment that runs along ray C->PreP.
              \+ segment_contains_dilation_ray(SegId, C, PreP),
              format(atom(Msg),
                     "Point ~w is declared the image of ~w under dilation centered at ~w (so ~w must lie on segment ~w~w), but the schema also asserts ~w lies on segment ~w which does not contain the ray from ~w through ~w.",
                     [ImgP, PreP, C, ImgP, C, PreP, ImgP, SegId, C, PreP])
            ),
            Errors),
    assert_errors(Errors).

% A segment "contains the dilation ray from C through PreP" iff the segment
% is between C and PreP themselves (the segment's two endpoints are exactly
% C and PreP, in either order).
segment_contains_dilation_ray(SegId, C, PreP) :-
    atom_codes(SegId, [V1, V2]),
    atom_codes(C, [V1]),  % first letter is C
    atom_codes(PreP, [V2]).
segment_contains_dilation_ray(SegId, C, PreP) :-
    atom_codes(SegId, [V1, V2]),
    atom_codes(C, [V2]),  % second letter is C
    atom_codes(PreP, [V1]).


% =====================================================================
% LAYER 4 — DETERMINACY (UNDER-DETERMINATION DETECTION)
% =====================================================================

% --- gate_target_belongs_to_entity ---
% The side/angle key in the target must actually be a side/angle of the
% target entity. Asking for "EFGH.sides.BC" when EFGH's sides are
% {EF, FG, GH, HE} is a structural error, not an under-determination.
gate_target_belongs_to_entity :-
    target(Entity, AttrSpec),
    parse_attr(AttrSpec, Group, Key),
    ( Group == sides ; Group == angles ),
    \+ key_belongs_to_entity(Entity, Group, Key),
    valid_keys_for(Entity, Group, ValidKeys),
    format(atom(Msg),
           "Target ~w.~w references ~w '~w' which is not declared on entity ~w. Valid ~w of ~w are: ~w.",
           [Entity, AttrSpec, Group, Key, Entity, Group, Entity, ValidKeys]),
    assert_error(error(target_key_not_on_entity, fatal, Msg)).
gate_target_belongs_to_entity.

key_belongs_to_entity(E, sides, K)  :- triangle_side(E, K, _).
key_belongs_to_entity(E, sides, K)  :- polygon_side(E, K, _).
key_belongs_to_entity(E, angles, K) :- triangle_angle(E, K, _).
key_belongs_to_entity(E, angles, K) :- polygon_angle(E, K, _).
% Implicit triangle sides: the side between two adjacent vertices of the triangle id.
key_belongs_to_entity(E, sides, K) :-
    entity(triangle, E),
    triangle_implicit_side(E, K).
% Implicit triangle angles: an angle at any vertex of the triangle.
key_belongs_to_entity(E, angles, K) :-
    entity(triangle, E),
    atom_codes(E, Vertices),
    atom_codes(K, [V]),
    member(V, Vertices).
% Implicit polygon sides: the side between any two consecutive vertices
% of the polygon id, with the last vertex wrapping back to the first.
key_belongs_to_entity(E, sides, K) :-
    entity(polygon, E),
    polygon_implicit_side(E, K).
% Implicit polygon angles: an angle at any vertex of the polygon.
key_belongs_to_entity(E, angles, K) :-
    entity(polygon, E),
    atom_codes(E, Vertices),
    atom_codes(K, [V]),
    member(V, Vertices).

triangle_implicit_side(T, Side) :-
    atom_codes(T, [A, B, C]),
    pair_to_atom(A, B, AB), pair_to_atom(B, C, BC), pair_to_atom(C, A, CA),
    member(Side, [AB, BC, CA]).
% Accept reversed orderings too (e.g., BA, CB, AC).
triangle_implicit_side(T, Side) :-
    atom_codes(T, [A, B, C]),
    pair_to_atom(B, A, BA), pair_to_atom(C, B, CB), pair_to_atom(A, C, AC),
    member(Side, [BA, CB, AC]).

% Polygon implicit sides: consecutive vertex pairs around the polygon,
% with wrap-around. Accepts both orderings for each pair.
polygon_implicit_side(Poly, Side) :-
    atom_codes(Poly, Vertices),
    consecutive_pair(Vertices, V1, V2),
    ( pair_to_atom(V1, V2, Side)
    ; pair_to_atom(V2, V1, Side)
    ).

% consecutive_pair(+List, -V1, -V2)
% Yields each pair of adjacent elements, including the wrap-around pair
% (last element followed by first).
consecutive_pair(List, V1, V2) :-
    append(_, [V1, V2 | _], List).
consecutive_pair(List, V1, V2) :-
    last(List, V1),
    List = [V2 | _].

valid_keys_for(E, sides, Keys) :-
    findall(K, triangle_side(E, K, _), TKeys),
    findall(K, polygon_side(E, K, _), PKeys),
    findall(K, ( entity(triangle, E), triangle_implicit_side(E, K) ), TriImplicit),
    findall(K, ( entity(polygon, E), polygon_implicit_side(E, K) ), PolyImplicit),
    append([TKeys, PKeys, TriImplicit, PolyImplicit], All),
    list_to_set(All, Keys).
valid_keys_for(E, angles, Keys) :-
    findall(K, triangle_angle(E, K, _), TKeys),
    findall(K, polygon_angle(E, K, _), PKeys),
    findall(K, ( entity(triangle, E),
                 atom_codes(E, Vs), member(V, Vs), atom_codes(K, [V]) ), TriImplicit),
    findall(K, ( entity(polygon, E),
                 atom_codes(E, Vs), member(V, Vs), atom_codes(K, [V]) ), PolyImplicit),
    append([TKeys, PKeys, TriImplicit, PolyImplicit], All),
    list_to_set(All, Keys).

% --- gate_target_dilation_pair_underdetermined ---
% If the target is a side under a dilation/scaled_copy/similarity, the
% corresponding side on the pre-image must be known OR the scale factor
% must already be derivable from a different corresponding-side pair.
% When both the corresponding pre-image side AND the scale factor are
% unknown, the target is structurally under-determined regardless of
% any other derivation path.
gate_target_dilation_pair_underdetermined :-
    target(Entity, AttrSpec),
    parse_attr(AttrSpec, sides, TargetKey),
    ( triangle_side(Entity, TargetKey, _)
    ; polygon_side(Entity, TargetKey, _)
    ),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                  similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    rel_attr(RIdx, image, Entity),
    rel_attr(RIdx, pre_image, Pre),
    \+ scale_factor_derivable(RIdx, Pre, Entity),
    \+ corresponding_pre_image_side_known(Pre, Entity, TargetKey),
    format(atom(Msg),
           "Target ~w.~w is under-determined: under relationship ~w (index ~w), neither the scale factor nor the corresponding side on pre-image ~w is known, and no other corresponding-side pair is fully declared to derive the scale factor.",
           [Entity, AttrSpec, Type, RIdx, Pre]),
    assert_error(error(target_dilation_underdetermined, underdetermined, Msg)).
gate_target_dilation_pair_underdetermined :-
    % Segment-length variant: target is a segment's length under a scaling relationship.
    target(Entity, length),
    entity(segment, Entity),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                  similar_unspecified]),
    rel_attr(RIdx, image, Entity),
    rel_attr(RIdx, pre_image, Pre),
    entity(segment, Pre),
    \+ scale_factor_derivable(RIdx, Pre, Entity),
    \+ ( segment_length(Pre, V), known(V) ),
    format(atom(Msg),
           "Target ~w.length is under-determined: under relationship ~w (index ~w), neither the scale factor nor the pre-image segment ~w length is known, and no other corresponding pair is declared to derive the scale factor.",
           [Entity, Type, RIdx, Pre]),
    assert_error(error(target_dilation_underdetermined, underdetermined, Msg)).
gate_target_dilation_pair_underdetermined.

% Scale factor is "derivable" if it is declared OR if at least one
% pre-image–image corresponding-side pair has both sides known.
scale_factor_derivable(RIdx, _, _) :-
    rel_attr(RIdx, scale_factor, K), known(K), !.
scale_factor_derivable(_, Pre, Img) :-
    corresponding_side_pair_known(Pre, Img).

corresponding_side_pair_known(Pre, Img) :-
    ( entity(triangle, Pre), entity(triangle, Img),
      corresponding_side_pair(Pre, Img, _, _, PreV, ImgV),
      known(PreV), known(ImgV)
    ; entity(polygon, Pre), entity(polygon, Img),
      polygon_corresponding_pair_known(Pre, Img)
    ; entity(circle, Pre), entity(circle, Img),
      circle_radius(Pre, R1), known(R1),
      circle_radius(Img, R2), known(R2)
    ; entity(segment, Pre), entity(segment, Img),
      segment_length(Pre, L1), known(L1),
      segment_length(Img, L2), known(L2)
    ).

% For polygons we use position-based correspondence: nth side of pre-image
% corresponds to nth side of image, in declaration order.
polygon_corresponding_pair_known(Pre, Img) :-
    findall(V, polygon_side(Pre, _, V), PreVs),
    findall(V, polygon_side(Img, _, V), ImgVs),
    nth_pair_both_known(PreVs, ImgVs).

nth_pair_both_known([V1 | _], [V2 | _]) :- known(V1), known(V2), !.
nth_pair_both_known([_ | Rest1], [_ | Rest2]) :- nth_pair_both_known(Rest1, Rest2).

% Is the corresponding side on the pre-image declared with a known value?
corresponding_pre_image_side_known(Pre, Img, ImgKey) :-
    entity(triangle, Pre), entity(triangle, Img),
    side_position(Img, ImgKey, Pos),
    side_position(Pre, PreKey, Pos),
    triangle_side(Pre, PreKey, V), known(V), !.
corresponding_pre_image_side_known(Pre, Img, ImgKey) :-
    entity(polygon, Pre), entity(polygon, Img),
    polygon_side_position(Img, ImgKey, Pos),
    polygon_side_position(Pre, _PreKey, Pos),
    nth_polygon_side_known(Pre, Pos).

polygon_side_position(Poly, Key, Pos) :-
    findall(K, polygon_side(Poly, K, _), Keys),
    nth1(Pos, Keys, Key).

nth_polygon_side_known(Poly, Pos) :-
    findall(V, polygon_side(Poly, _, V), Vs),
    nth1(Pos, Vs, V),
    known(V).

% --- gate_target_resolvable ---
% Try to derive the target. If no inference path exists, flag under-determined.
target_already_specified(Entity, AttrSpec) :-
    parse_attr(AttrSpec, Group, Key),
    target_value_already_known(Entity, Group, Key, _).
gate_target_resolvable :-
    target(Entity, Attr),
    ( target_already_specified(Entity, Attr) -> true   % vacuity gate owns this case
    ; target_derivable(Entity, Attr)         -> true
    ; format(atom(Msg),
             "Target ~w.~w is under-determined by the given facts and relationships. The problem has no unique answer.",
             [Entity, Attr]),
      assert_error(error(target_undetermined, underdetermined, Msg))
    ).

% --- target_derivable rules: each path to deriving an unknown ---

% Side of a triangle, derivable via dilation scale factor
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, dilation, _),
    rel_attr(RIdx, image, T),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    side_position(T, SideKey, Pos),
    side_position(Pre, PreSide, Pos),
    triangle_side(Pre, PreSide, PreV), known(PreV).

% Side of a triangle, derivable via similarity or scaled_copy scale factor
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified,
                  scaled_copy, scaled_copy_unspecified]),
    rel_attr(RIdx, image, T),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    side_position(T, SideKey, Pos),
    side_position(Pre, PreSide, Pos),
    triangle_side(Pre, PreSide, PreV), known(PreV).

% Side derivable via Pythagorean theorem (other 2 sides + right flag)
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= SideKey, known(V)), Vs),
    length(Vs, 2).

% Side derivable via Law of Cosines: the other two sides AND any one angle
% are known. (When the known angle is the angle opposite the target side,
% c² = a² + b² - 2ab·cos(C) applies directly. When the known angle is one
% of the other two angles, the third angle can be derived via Triangle
% Angle Sum once one more side is found via Law of Sines.)
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    findall(V, (triangle_side(T, K, V), K \= SideKey, known(V)), OtherSides),
    length(OtherSides, 2),
    findall(V, (triangle_angle(T, _, V), known(V)), Angles),
    length(Angles, NA), NA >= 1.

% Side derivable via Law of Sines within a single triangle:
% if 2+ angles are known (or derivable via Triangle Angle Sum) AND at least
% one (angle, opposite-side) pair is fully known, every other side is
% determined by side_i = ratio × sin(opposite_angle_i).
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, sides, _SideKey),
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)),
    triangle_angle(T, KnownAngleKey, KnownAngleV), known(KnownAngleV),
    opposite_side_length(T, KnownAngleKey, KnownOpp, _, _), known(KnownOpp).

% Segment length derivable via geometric_mean_leg:
% relation: leg² = adjacent_segment × hypotenuse.
% Any of (leg, adjacent_segment, hypotenuse) is derivable if the other two
% are known or themselves derivable from declared facts.
target_derivable(SegId, length) :-
    relationship(_, geometric_mean_leg, _),
    rel_attr(RIdx, leg_id, LegId),
    rel_attr(RIdx, hypotenuse, HypId),
    rel_attr(RIdx, adjacent_segment, AdjId),
    relationship(RIdx, geometric_mean_leg, _),
    member(SegId, [LegId, HypId, AdjId]),
    other_two(SegId, [LegId, HypId, AdjId], Other1, Other2),
    segment_or_side_known_or_derivable(Other1),
    segment_or_side_known_or_derivable(Other2).

other_two(X, [A, B, C], Y, Z) :-
    select(X, [A, B, C], [Y, Z]).

% Segment length derivable via geometric_mean_altitude:
% relation: altitude² = segment1 × segment2.
target_derivable(SegId, length) :-
    relationship(_, geometric_mean_altitude, _),
    rel_attr(RIdx, altitude_id, AltId),
    rel_attr(RIdx, segment1, Seg1Id),
    rel_attr(RIdx, segment2, Seg2Id),
    relationship(RIdx, geometric_mean_altitude, _),
    member(SegId, [AltId, Seg1Id, Seg2Id]),
    other_two(SegId, [AltId, Seg1Id, Seg2Id], Other1, Other2),
    segment_or_side_known_or_derivable(Other1),
    segment_or_side_known_or_derivable(Other2).

% Segment length derivable via altitude_to_hypotenuse:
% segment1 + segment2 = hypotenuse, so any one is derivable from the other two.
target_derivable(SegId, length) :-
    relationship(_, altitude_to_hypotenuse, _),
    rel_attr(RIdx, hypotenuse, HypId),
    rel_attr(RIdx, segment1, Seg1Id),
    rel_attr(RIdx, segment2, Seg2Id),
    relationship(RIdx, altitude_to_hypotenuse, _),
    member(SegId, [HypId, Seg1Id, Seg2Id]),
    other_two(SegId, [HypId, Seg1Id, Seg2Id], Other1, Other2),
    segment_or_side_known_or_derivable(Other1),
    segment_or_side_known_or_derivable(Other2).

% Altitude length derivable via the area-equivalence formula on a right
% triangle: when both legs are known (or derivable), the altitude on the
% hypotenuse satisfies altitude = (leg1 × leg2) / hypotenuse, where the
% hypotenuse is derivable via Pythagorean.
target_derivable(AltId, length) :-
    relationship(_, altitude_to_hypotenuse, _),
    rel_attr(RIdx, altitude_id, AltId),
    relationship(RIdx, altitude_to_hypotenuse, _),
    rel_attr(RIdx, hypotenuse, HypId),
    entity(triangle, T),
    triangle_implicit_side(T, HypId),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= HypId, known(V)), Legs),
    length(Legs, 2).

% Adjacent-segment derivation through implied geometric_mean_leg:
% When altitude_to_hypotenuse is declared, each leg of the right triangle
% satisfies leg² = adjacent_segment × hypotenuse, even if no explicit
% geometric_mean_leg relationship was declared. Adjacent_segment for leg L
% is derivable when both L and the hypotenuse are known/derivable.
target_derivable(SegId, length) :-
    relationship(_, altitude_to_hypotenuse, _),
    rel_attr(RIdx, hypotenuse, HypId),
    rel_attr(RIdx, segment1, Seg1Id),
    rel_attr(RIdx, segment2, Seg2Id),
    relationship(RIdx, altitude_to_hypotenuse, _),
    member(SegId, [Seg1Id, Seg2Id]),
    entity(triangle, T),
    triangle_implicit_side(T, HypId),
    triangle_flag(T, is_right),
    findall(L, (triangle_side(T, K, L), K \= HypId, known(L)), Legs),
    length(Legs, 2),
    segment_or_side_known_or_derivable(HypId).

% A segment or triangle side is "known or derivable" if its value is
% declared known, OR it is the hypotenuse of a triangle with both legs
% known (Pythagorean), OR it is a side of a triangle satisfying any of
% the other derivation rules in this file.
segment_or_side_known_or_derivable(Id) :-
    segment_or_side_length(Id, V), known(V), !.
segment_or_side_known_or_derivable(Id) :-
    % Pythagorean: side of a right triangle with the other two known.
    entity(triangle, T),
    triangle_implicit_side(T, Id),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= Id, known(V)), Vs),
    length(Vs, 2), !.
segment_or_side_known_or_derivable(Id) :-
    % All three angles known on a triangle containing the side, plus one
    % (angle, opposite-side) pair → Law of Sines.
    entity(triangle, T),
    triangle_implicit_side(T, Id),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)),
    triangle_angle(T, KnownAngleKey, KnownAngleV), known(KnownAngleV),
    opposite_side_length(T, KnownAngleKey, KnownOpp, _, _), known(KnownOpp), !.

% Angle derivable via Triangle Angle Sum
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    findall(V, (triangle_angle(T, _, V), known(V)), Vs),
    length(Vs, 2).

% Angle derivable via Law of Cosines: when all three sides are known,
% every angle is uniquely determined.
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    findall(V, (triangle_side(T, _, V), known(V)), Vs),
    length(Vs, 3).

% Angle derivable via similarity (corresponding angle on partner) — either
% direction (target is image or pre-image of the similarity).
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, angles, AngleKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    ( rel_attr(RIdx, image, T), rel_attr(RIdx, pre_image, Partner)
    ; rel_attr(RIdx, pre_image, T), rel_attr(RIdx, image, Partner)
    ),
    rel_attr(RIdx, congruent_angle_pairs, Pairs),
    ( member([AngleKey, PartnerKey], Pairs)
    ; member([PartnerKey, AngleKey], Pairs)
    ),
    triangle_angle(Partner, PartnerKey, V), known(V).

% Angle derivable via similarity transitivity: if the partner triangle has
% all its angles resolvable (3 sides known, or 2 angles known, or
% is_equilateral), the corresponding angle on the target is also known.
target_derivable(T, AttrSpec) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    relationship(_, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    relationship(RIdx, Type, _),
    ( rel_attr(RIdx, image, T), rel_attr(RIdx, pre_image, Partner)
    ; rel_attr(RIdx, pre_image, T), rel_attr(RIdx, image, Partner)
    ),
    entity(triangle, Partner),
    triangle_all_angles_known_or_derivable(Partner).

triangle_all_angles_known_or_derivable(T) :-
    findall(V, (triangle_angle(T, _, V), known(V)), AVs),
    length(AVs, NA), NA >= 2, !.
triangle_all_angles_known_or_derivable(T) :-
    findall(V, (triangle_side(T, _, V), known(V)), SVs),
    length(SVs, 3), !.
triangle_all_angles_known_or_derivable(T) :-
    triangle_flag(T, is_equilateral).

% Segment length derivable via midsegment relationship
target_derivable(S, length) :-
    entity(segment, S),
    segment_flag(S, is_midsegment),
    segment_parallel_to(S, Side),
    segment_or_side_length(Side, BV), known(BV).

% Segment length via midsegment_ratio relationship
target_derivable(S, length) :-
    entity(segment, S),
    relationship(_, midsegment_ratio, [S, Base]),
    segment_or_side_length(Base, BV), known(BV).

% Inverse direction: triangle side length derivable from a known midsegment
% parallel to it. If MID is declared a midsegment parallel to side X with
% length L, then X = 2 * L.
target_derivable(_, AttrSpec) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(segment, Mid),
    segment_flag(Mid, is_midsegment),
    segment_parallel_to(Mid, ParallelTarget),
    ( ParallelTarget == SideKey ; matches_side_id(ParallelTarget, SideKey) ),
    segment_length(Mid, V), known(V).

% Inverse direction: target IS the side itself (when the target entity is the
% side identifier, e.g. target = (PR, length)) — derive from known midsegment.
target_derivable(Side, length) :-
    entity(segment, Mid),
    segment_flag(Mid, is_midsegment),
    segment_parallel_to(Mid, Side),
    segment_length(Mid, V), known(V).

% Helper: tolerant side-identifier matching (PR vs RP).
matches_side_id(A, B) :- A == B.
matches_side_id(A, B) :-
    atom_codes(A, [X, Y]),
    atom_codes(B, [Y, X]).

% Radius via similar circles + scale factor
target_derivable(C, radius) :-
    entity(circle, C),
    relationship(RIdx, Type, _),
    member(Type, [similar_unspecified, scaled_copy, dilation]),
    rel_attr(RIdx, image, C),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    circle_radius(Pre, R), known(R).

% Boolean: is_right derivable from 3 known sides
target_derivable(T, is_right) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3),
    known(V1), known(V2), known(V3).

% Boolean: is_acute / is_obtuse derivable from 3 known sides via the
% converse of the Pythagorean theorem. With sides a, b, c (c the largest):
%   c² < a² + b² → acute
%   c² = a² + b² → right
%   c² > a² + b² → obtuse
target_derivable(T, is_acute) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3),
    known(V1), known(V2), known(V3).
target_derivable(T, is_obtuse) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3),
    known(V1), known(V2), known(V3).

% Boolean: classification also derivable when all 3 angles are
% known/derivable (any angle ≥ 90° classifies the triangle).
target_derivable(T, is_acute) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)).
target_derivable(T, is_obtuse) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)).
target_derivable(T, is_right) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)).

% Scale factor derivable from one corresponding side pair
target_derivable(_, scale_factor) :-
    relationship(_, Type, [E1, E2]),
    member(Type, [dilation, scaled_copy, similar_AA, similar_SAS, similar_SSS]),
    corresponding_side_pair(E1, E2, _, _, V1, V2),
    known(V1), known(V2).

% Perimeter derivable from all known sides
target_derivable(T, perimeter) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3),
    known(V1), known(V2), known(V3).
target_derivable(P, perimeter) :-
    entity(polygon, P),
    polygon_n_sides(P, N),
    findall(V, (polygon_side(P, _, V), known(V)), Vs),
    length(Vs, N).

parse_attr(AttrSpec, Group, Key) :-
    atom_codes(AttrSpec, Codes),
    append(GroupCodes, [0'. | KeyCodes], Codes),
    atom_codes(Group, GroupCodes),
    atom_codes(Key, KeyCodes).
parse_attr(AttrSpec, AttrSpec, '') :-
    atom_codes(AttrSpec, Codes),
    \+ member(0'., Codes).

% --- gate_target_attribute_already_specified ---
% If the target value is already provided in the schema, the problem is vacuous.
gate_target_attribute_already_specified :-
    target(Entity, AttrSpec),
    parse_attr(AttrSpec, Group, Key),
    target_value_already_known(Entity, Group, Key, V),
    format(atom(Msg),
           "Target ~w.~w is already declared with value ~w. The problem is vacuous — there is nothing to solve.",
           [Entity, AttrSpec, V]),
    assert_error(error(target_vacuous, structural, Msg)).
gate_target_attribute_already_specified.

target_value_already_known(E, sides, K, V)  :- triangle_side(E, K, V), known(V).
target_value_already_known(E, sides, K, V)  :- polygon_side(E, K, V), known(V).
target_value_already_known(E, angles, K, V) :- triangle_angle(E, K, V), known(V).
target_value_already_known(E, angles, K, V) :- polygon_angle(E, K, V), known(V).
target_value_already_known(E, length, _, V) :- segment_length(E, V), known(V).
target_value_already_known(E, radius, _, V) :- circle_radius(E, V), known(V).


% =====================================================================
% LAYER 5 — REDUNDANCY DETECTION
% =====================================================================

% --- gate_no_redundant_relationships ---
% Flag duplicate similarity/dilation relationships on the same entity pair.
gate_no_redundant_relationships :-
    findall(error(redundant_relationship, style, Msg),
            ( relationship(R1, Type1, Es),
              relationship(R2, Type2, Es),
              R1 < R2,
              both_similarity_or_dilation(Type1, Type2),
              format(atom(Msg),
                     "Relationships at indices ~w (~w) and ~w (~w) over the same entities ~w are redundant — similarity and dilation with matching scale factor encode the same information.",
                     [R1, Type1, R2, Type2, Es])
            ),
            Errors),
    assert_errors(Errors).

both_similarity_or_dilation(T1, T2) :-
    similarity_or_dilation(T1),
    similarity_or_dilation(T2).

similarity_or_dilation(dilation).
similarity_or_dilation(scaled_copy).
similarity_or_dilation(similar_AA).
similarity_or_dilation(similar_SAS).
similarity_or_dilation(similar_SSS).
similarity_or_dilation(similar_unspecified).


% =====================================================================
% ERROR COLLECTION AND OUTPUT
% =====================================================================

:- dynamic collected_error/1.

assert_errors([]).
assert_errors([E | Es]) :- assert_error(E), assert_errors(Es).

assert_error(E) :-
    ( collected_error(E) -> true   % de-duplicate
    ; assertz(collected_error(E))
    ).

clear_errors :- retractall(collected_error(_)).


% --- Run all gates ---
run_all_gates :-
    clear_errors,
    % Layer 1
    gate_entity_references_exist,
    gate_attribute_keys_well_formed,
    gate_naming_conventions,
    gate_no_dot_notation_in_relationship_entities,
    gate_required_attributes_present,
    gate_hypotenuse_is_longest_side,
    gate_relation_arity,
    gate_orphan_entities,
    gate_disconnected_figures,
    gate_polygon_angle_sum_consistency,
    % Layer 2
    gate_relation_scope,
    gate_shape_relevance,
    gate_attribute_kind_consistency,
    % Layer 3
    gate_positive_lengths,
    gate_angle_range,
    gate_triangle_angle_sum,
    gate_triangle_inequality,
    gate_pythagorean,
    gate_pythagorean_classification,
    gate_equilateral_consistency,
    gate_isosceles_consistency,
    gate_right_angle_flag_consistency,
    gate_law_of_cosines_consistency,
    gate_law_of_sines_consistency,
    gate_scale_factor_matches_declared_sides,
    gate_scale_factor_positive,
    gate_scale_factor_consistency_across_pairs,
    gate_similarity_corresponding_pairs,
    gate_aa_similarity_two_pairs,
    gate_sss_similarity_three_sides,
    gate_sas_similarity_complete,
    gate_invariant_constants,
    gate_polygon_interior_sum,
    gate_vacuous_angle_sum_relationship,
    gate_midsegment_consistency,
    gate_altitude_to_hypotenuse_consistency,
    gate_collinear_dilation_consistency,
    gate_collinear_dilation_center_matches_parent,
    gate_point_position_consistency,
    % Layer 4
    gate_target_belongs_to_entity,
    gate_target_dilation_pair_underdetermined,
    gate_target_attribute_already_specified,
    gate_target_resolvable,
    % Layer 5
    gate_no_redundant_relationships.


% --- Output formatting ---
% Emit a structured report consumable by the host program / LLM feedback loop.

validate(Result) :-
    run_all_gates,
    findall(E, collected_error(E), Errors),
    classify_result(Errors, Result).

classify_result([], pass).
classify_result(Errors, fail(Errors)) :- Errors \= [].

% =====================================================================
% GATE DESCRIPTIONS — what each gate checks.
% This is the static "rule reference" Haiku gets alongside every failure.
% =====================================================================

gate_check(entity_ref_missing,
    "Every entity name referenced in a relationship must be declared in entities.").
gate_check(invalid_attribute_key,
    "Each relationship type has a fixed set of allowed attribute keys; no extras may be added.").
gate_check(naming_convention,
    "Entity ids must follow conventions: triangles=ABC, polygons=ABCD..., segments=AB, points=A, lines/circles=lowercase.").
gate_check(dot_notation_in_relationship,
    "Dot notation (e.g. 'ABC.C') is reserved for the target.attribute field. Relationship entity lists must use bare entity ids; compound references belong in typed attributes such as 'ids' for congruent_angles or congruent_segments.").
gate_check(missing_required_attribute,
    "Some relationship types declare attribute keys that must always be present. An empty or missing attributes block is invalid when required keys exist for that relationship type.").
gate_check(hypotenuse_not_longest,
    "The hypotenuse of a right triangle is by definition the side opposite the right angle and is therefore the longest side of the triangle. A side designated as the hypotenuse cannot be shorter than any other side of the same triangle.").
gate_check(wrong_entity_count,
    "Each relationship type expects a specific number of entities in its entities list.").
gate_check(orphan_entity,
    "Declared entities must be used in at least one relationship or as the target.").
gate_check(figures_not_connected,
    "When multiple comparable shape entities (triangles, polygons, or circles) are declared, at least one relationship must connect them. A multi-figure problem without any relationship linking the figures cannot pose a meaningful question.").
gate_check(polygon_interior_angle_sum_violation,
    "When all interior angles of an n-sided polygon are declared, they must sum to (n - 2) × 180°.").
gate_check(scope_violation,
    "A relationship may only apply to entities of compatible kinds (e.g., triangle similarity only between two triangles).").
gate_check(shape_relationship_mismatch,
    "Each shape kind has a fixed set of relationship types it can participate in; out-of-domain combinations are rejected.").
gate_check(attribute_kind_mismatch,
    "Attributes that name an entity must point to an entity of the correct kind (e.g., dilation.center must be a point).").
gate_check(non_positive_length,
    "All sides, segment lengths, and radii must be strictly greater than zero.").
gate_check(angle_out_of_range,
    "All angles in a triangle must be strictly between 0° and 180°.").
gate_check(angle_sum_violation,
    "The interior angles of a triangle must sum to exactly 180°.").
gate_check(triangle_inequality_violation,
    "Each side of a triangle must be strictly less than the sum of the other two sides.").
gate_check(pythagorean_violation,
    "A right triangle's sides must satisfy a² + b² = c², where c is the hypotenuse.").
gate_check(right_flag_inconsistent,
    "The is_right flag must agree with the side-length classification (right, acute, or obtuse).").
gate_check(equilateral_inconsistent,
    "A triangle declared equilateral must have all three sides equal in length.").
gate_check(isosceles_inconsistent,
    "A triangle declared isosceles must have at least two sides equal in length.").
gate_check(right_flag_missing_for_90_angle,
    "When a triangle has an explicit 90° angle declared, the is_right flag should be set to true.").
gate_check(right_flag_without_90_angle,
    "When a triangle is declared is_right = true and angles are declared, at least one of those angles must be exactly 90°.").
gate_check(law_of_cosines_violation,
    "For any triangle with all three sides and at least one angle known, the angle and sides must satisfy cos(C) = (a² + b² − c²) / (2ab), where c is opposite angle C.").
gate_check(law_of_sines_violation,
    "For any triangle with two or more (angle, opposite-side) pairs known, the ratios side/sin(angle) must be equal across all pairs.").
gate_check(scale_factor_mismatch,
    "Corresponding sides between a pre-image and image under dilation must satisfy image_side = pre_image_side × scale_factor.").
gate_check(scale_factor_inconsistent_across_pairs,
    "When multiple corresponding-side pairs are declared between a pre-image and image under dilation, scaled_copy, or similarity, every pair must yield the same ratio (image / pre_image).").
gate_check(non_positive_scale_factor,
    "Scale factors for dilation, scaled_copy, and similarity must be strictly greater than zero.").
gate_check(insufficient_similarity_evidence,
    "Polygon similarity requires n corresponding sides and n−1 corresponding angles to be specified, where n is the number of sides.").
gate_check(aa_underspecified,
    "similar_AA requires at least two pairs of congruent angles between the two triangles.").
gate_check(sss_underspecified,
    "similar_SSS requires all three sides of both triangles to be known.").
gate_check(sas_underspecified,
    "similar_SAS requires two sides and the included angle to be known on both triangles.").
gate_check(invariant_violation,
    "Certain attribute values are fixed by definition (supplementary=180, complementary=90, linear_pair=180, midsegment_ratio=0.5, exterior_sum=360).").
gate_check(polygon_interior_sum_wrong,
    "An n-sided polygon's interior angles must sum to (n − 2) × 180°.").
gate_check(vacuous_angle_sum_relationship,
    "angle_sum_triangle is only informative when at least 2 angles of the triangle are independently declared; similarly angle_sum_polygon requires n-1 declared angles. With fewer, the relationship restates a universal truth and contributes no constraint.").
gate_check(midsegment_inconsistent,
    "A midsegment's length must equal half the length of the triangle side it is parallel to.").
gate_check(altitude_split_inconsistent,
    "The two segments formed by an altitude to the hypotenuse must sum to the length of the hypotenuse.").
gate_check(collinear_dilation_inconsistent,
    "Under a dilation, the pre-image point, center, and image point must be collinear with the image distance equal to the pre-image distance times the scale factor.").
gate_check(collinear_dilation_center_mismatch,
    "A collinear_dilation relationship must share its center with the parent dilation relationship — the two cannot disagree on where the dilation is centered.").
gate_check(point_position_inconsistent,
    "When a point is declared the image of another point under a dilation centered at C, it must lie on the ray from C through the pre-image point. Asserting it also lies on a different segment that does not contain this ray is contradictory.").
gate_check(target_undetermined,
    "The target attribute must be uniquely derivable from the declared facts and relationships.").
gate_check(target_key_not_on_entity,
    "When the target attribute refers to a specific side or angle, that side or angle must actually be declared on the target entity (e.g., EFGH.sides.BC is invalid if EFGH's sides are EF, FG, GH, HE).").
gate_check(target_dilation_underdetermined,
    "When a target side lives on the image of a dilation, similarity, or scaled copy, either the scale factor must be known or at least one corresponding side pair must be fully declared so the scale factor can be derived; otherwise the target side cannot be computed.").
gate_check(target_vacuous,
    "The target attribute must not already be declared in the entities; the problem must have something to solve.").
gate_check(redundant_relationship,
    "The same entity pair should not be declared similar and dilated separately when one implies the other.").
gate_check(_, "No description registered for this gate.").  % fallback

% =====================================================================
% HUMAN-READABLE PRINTER (for debugging only — not the Pipeline 3 output)
% =====================================================================
print_validation_report :-
    validate(Result),
    print_result(Result).

print_result(pass) :-
    format("~n=== VALIDATION PASSED ===~nNo errors detected. All gates pass.~n").

print_result(fail(Errors)) :-
    format("~n=== VALIDATION FAILED ===~n"),
    length(Errors, N),
    format("~w error(s) detected:~n~n", [N]),
    print_errors(Errors, 1).

print_errors([], _).
print_errors([error(Gate, Severity, Msg) | Rest], N) :-
    once(gate_check(Gate, Check)),
    format("[~w] gate: ~w   severity: ~w~n", [N, Gate, Severity]),
    format("    checks: ~w~n", [Check]),
    format("    failed: ~w~n~n", [Msg]),
    N1 is N + 1,
    print_errors(Rest, N1).


% =====================================================================
% PIPELINE 3 OUTPUT — JSON-shaped feedback for Haiku consumption
%
% This is the canonical machine-readable output. Every failed gate is
% reported with three fields:
%   gate       — the identifier of the gate that fired
%   checks     — what the gate checks (static rule statement)
%   failed     — the specific instance-level reason the gate fired
%
% Haiku reads this directly and uses 'checks' to understand the rule
% and 'failed' to understand the specific instance to repair.
% =====================================================================

% feedback_bundle(-Bundle)
% Bundle is a list of key-value pairs ready for serialization to JSON.
feedback_bundle(Bundle) :-
    validate(Result),
    ( Result = pass ->
        Bundle = [status-pass, error_count-0, errors-[]]
    ; Result = fail(Errors) ->
        length(Errors, N),
        bundle_errors(Errors, BundledErrors),
        Bundle = [status-fail, error_count-N, errors-BundledErrors]
    ).

bundle_errors([], []).
bundle_errors([error(Gate, Severity, Msg) | Rest], [E | Es]) :-
    once(gate_check(Gate, Check)),
    E = [gate-Gate, severity-Severity, checks-Check, failed-Msg],
    bundle_errors(Rest, Es).

% --- emit_json: print the feedback bundle as JSON to stdout ---
% Pipeline 3 should call this and capture stdout.
emit_json :-
    feedback_bundle(Bundle),
    bundle_to_json(Bundle, Json),
    write(Json), nl.

bundle_to_json(Bundle, Json) :-
    pairs_to_json_object(Bundle, Json).

pairs_to_json_object(Pairs, Json) :-
    findall(Entry, ( member(K-V, Pairs), pair_to_entry(K, V, Entry) ), Entries),
    atomic_list_concat(Entries, ",", Inner),
    atom_concat('{', Inner, Tmp),
    atom_concat(Tmp, '}', Json).

pair_to_entry(K, V, Entry) :-
    quote_atom(K, QK),
    json_value(V, JV),
    atomic_list_concat([QK, ':', JV], Entry).

json_value(V, Out) :- integer(V), !, atom_number(Out, V).
json_value(V, Out) :- float(V), !, atom_number(Out, V).
json_value([], '[]') :- !.
json_value(List, Out) :-
    is_list(List), List = [H | _],
    ( is_pair_list(H) ->
        maplist(pairs_to_json_object, List, Objs),
        atomic_list_concat(Objs, ",", Inner),
        atom_concat('[', Inner, Tmp),
        atom_concat(Tmp, ']', Out)
    ; maplist([X, Y]>>json_value(X, Y), List, Quoted),
      atomic_list_concat(Quoted, ",", Inner),
      atom_concat('[', Inner, Tmp),
      atom_concat(Tmp, ']', Out)
    ), !.
json_value(V, Out) :- atom(V), quote_atom(V, Out).
json_value(V, Out) :- string(V), atom_string(A, V), quote_atom(A, Out).

is_pair_list([K-_ | _]) :- atom(K).

quote_atom(A, Q) :-
    atom_codes(A, Codes),
    escape_codes(Codes, Escaped),
    atom_codes(Body, Escaped),
    atom_concat('"', Body, T),
    atom_concat(T, '"', Q).

escape_codes([], []).
escape_codes([0'" | Rest], [0'\\, 0'" | EscRest])   :- !, escape_codes(Rest, EscRest).
escape_codes([0'\\ | Rest], [0'\\, 0'\\ | EscRest]) :- !, escape_codes(Rest, EscRest).
escape_codes([0'\n | Rest], [0'\\, 0'n | EscRest])  :- !, escape_codes(Rest, EscRest).
escape_codes([C | Rest], [C | EscRest])             :- escape_codes(Rest, EscRest).


% =====================================================================
% END OF VALIDATOR
% =====================================================================
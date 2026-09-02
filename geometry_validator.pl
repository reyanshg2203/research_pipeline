% =====================================================================
% GEOMETRY PROBLEM SCHEMA VALIDATOR
% Domain: 10th grade similarity unit (lessons 01-16)
%
% Architecture:
%   Layer 0: Facts asserted from the input schema
%   Layer 1: Structural gates
%   Layer 2: Type-compatibility gates
%   Layer 3: Mathematical gates
%   Layer 4: Determinacy gates
%   Layer 5: Redundancy + output
%
% Each gate returns pass(GateId) or error(GateId, Severity, Message).
% Severity: fatal, contradiction, underdetermined, structural, style
%
% =====================================================================
% NULL / UNKNOWN HANDLING  (read this before touching any gate)
% =====================================================================
% A schema value is EITHER known (a number) OR unknown (the atoms `null` /
% `unknown`). The predicate known/1 is the single source of truth: known(V)
% succeeds only for a real, non-null number.
%
% The governing principle for accuracy is:
%
%   An unknown value is NEVER, by itself, an error. A value only matters when
%   the TARGET depends on it. The problem is well-posed as long as the target
%   is DERIVABLE from the known values through an allowed inference -- even if
%   many other values are left null. Nulls that are not needed to reach the
%   target are simply "not asked about" and are ignored.
%
% Concretely:
%   * Every MATHEMATICAL gate (Layer 3) guards each value with known/1 and is
%     therefore SILENT on unknowns. A gate can only fire on a CONTRADICTION
%     between values that are all known. Two known sides that violate the
%     triangle inequality is an error; a null side is not.
%   * Only the DETERMINACY gates (Layer 4) care about unknowns, and only about
%     ONE unknown: the target. gate_target_resolvable fires iff the target
%     value cannot be derived. No gate ever fires because some NON-target value
%     is null.
%   * target_derivable/3 is the reachability engine. It answers "can the target
%     be computed from the known values?" and emits the theorem-trace used by
%     the calibration layer. If it succeeds, the null target is fine.
%
% So: null + derivable = OK. null + underivable-but-needed = the single failure
% mode, reported once as target_undetermined. That is the whole story.
% =====================================================================

:- set_prolog_flag(verbose, silent).
:- style_check(-singleton).
:- style_check(-discontiguous).

:- discontiguous target_derivable/2.
:- discontiguous target_derivable/3.
:- discontiguous gate_check/2.
:- discontiguous allowed_attrs/2.
:- discontiguous required_attrs/2.
:- discontiguous scope/2.

% ---------------------------------------------------------------------
% UTILITY PREDICATES
% ---------------------------------------------------------------------

epsilon(0.0001).

approx_equal(X, Y) :-
    epsilon(E),
    Diff is abs(X - Y),
    Diff < E.

% --- Scale-factor comparison uses a RELATIVE tolerance ---------------
% Scale factors are frequently declared rounded (e.g. 5/3 written as 1.667).
% An absolute epsilon of 1e-4 then false-fires: 9 * 1.667 = 15.003 vs a
% declared 15.0 differs by 0.003 > 1e-4. A relative tolerance keeps the check
% meaningful for genuine inconsistencies (a 1.5-vs-2.5 error is ~40-60%) while
% tolerating decimal rounding (a 3-dp rounding error is < 0.1%). This is the
% ONLY comparison that uses the relative form; all other math stays strict.
scale_rel_tolerance(0.005).

approx_equal_scale(X, Y) :-
    ( approx_equal(X, Y) -> true
    ; Denom is max(abs(X), abs(Y)),
      Denom > 0,
      Diff is abs(X - Y) / Denom,
      scale_rel_tolerance(T),
      Diff < T
    ).

known(V) :- nonvar(V), V \= unknown, V \= null.

unknown(unknown).
unknown(null).

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

% ---------------------------------------------------------------------
% RELATIONSHIP ATTRIBUTE CONTRACT (allowed_attrs/2, required_attrs/2)
% ---------------------------------------------------------------------
% These facts are GENERATED from schema.py:RELATION_ATTRS and live in
% relation_contract.pl, so the Python schema and this validator can never
% disagree about which attributes a relationship may or must carry. Do NOT
% add allowed_attrs/required_attrs facts here by hand — edit RELATION_ATTRS
% in schema.py and regenerate:
%     python -c 'import schema; schema.write_prolog_contract()'
% A relationship type absent from the contract is unconstrained (the
% attribute-key gate simply does not fire), exactly as before.
:- ensure_loaded('relation_contract.pl').

relation_arity(similar_AA, 2).
relation_arity(similar_SAS, 2).
relation_arity(similar_SSS, 2).
relation_arity(similar_unspecified, 2).
relation_arity(dilation, 2).
relation_arity(scaled_copy, 2).
relation_arity(scaled_copy_unspecified, 2).
relation_arity(congruent_triangles, 2).
relation_arity(collinear_dilation, 3).
relation_arity(triangle_proportionality, _) :- true.
relation_arity(supplementary_angles, 2).
relation_arity(complementary_angles, 2).
relation_arity(vertical_angles, 2).
relation_arity(linear_pair, 2).
relation_arity(midsegment_ratio, 2).
relation_arity(medial_triangle, 2).

similarity_corresponding_sides_required(N, N).
similarity_corresponding_angles_required(N, K) :- K is N - 1.


% =====================================================================
% LAYER 1 -- STRUCTURAL VALIDATION
% =====================================================================

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
entity_known(Id) :- triangle_vertex_of_any(Id).
entity_known(Id) :- triangle_side_of_any(Id).
entity_known(Id) :- polygon_vertex_of_any(Id).
entity_known(Id) :- polygon_side_of_any(Id).
entity_known(Id) :- implicit_point_to_point_segment(Id).
entity_known(Id) :- implicit_altitude_subtriangle(Id).

polygon_vertex_of_any(VId) :-
    entity(polygon, P),
    atom_codes(P, VertexCodes),
    member(C, VertexCodes),
    atom_codes(VId, [C]).

polygon_side_of_any(SId) :-
    entity(polygon, P),
    polygon_implicit_side(P, SId).

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

implicit_altitude_subtriangle(Id) :-
    atom_codes(Id, Chars),
    length(Chars, 3),
    forall(member(C, Chars),
           ( atom_codes(P, [C]), known_point(P) )),
    relationship(_, altitude_to_hypotenuse, _).

triangle_vertex_of_any(VId) :-
    entity(triangle, T),
    atom_codes(T, VertexCodes),
    member(C, VertexCodes),
    atom_codes(VId, [C]).

triangle_side_of_any(SId) :-
    entity(triangle, T),
    atom_codes(T, [A, B, C]),
    member(SId, [AB, BC, CA]),
    pair_to_atom(A, B, AB),
    pair_to_atom(B, C, BC),
    pair_to_atom(C, A, CA).

pair_to_atom(C1, C2, Atom) :- atom_codes(Atom, [C1, C2]).

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

comparable_figure_pairs(F1, F2) :-
    entity(Kind, F1), entity(Kind, F2),
    member(Kind, [triangle, polygon, circle]),
    F1 @< F2.

comparable_kind(F) :- entity(triangle, F), !.
comparable_kind(F) :- entity(polygon, F), !.
comparable_kind(F) :- entity(circle, F), !.

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
relationship_connects(F1, F2) :-
    entity(triangle, F1), entity(triangle, F2),
    shares_at_least_one_vertex(F1, F2),
    relationship(_, RelType, Es),
    member(RelType, [altitude_to_hypotenuse, triangle_proportionality,
                     geometric_mean_leg, geometric_mean_altitude]),
    ( member(F1, Es) ; member(F2, Es)
    ; relationship_segment_touches(Es, F1) ; relationship_segment_touches(Es, F2)
    ).
relationship_connects(F1, F2) :-
    entity(triangle, F1), entity(triangle, F2),
    shares_at_least_one_vertex(F1, F2),
    ( relationship(_, midsegment_parallel, _) ; relationship(_, midsegment_ratio, _)
    ; segment_flag(_, is_midsegment) ),
    ( segment_flag(Mid, is_midsegment), segment_parallel_to(Mid, ParSide)
    ; relationship(_, RT, [_Mid, ParSide]), member(RT, [midsegment_parallel, midsegment_ratio]) ),
    ( triangle_implicit_side(F1, ParSide) ; triangle_implicit_side(F2, ParSide)
    ; triangle_side(F1, ParSide, _) ; triangle_side(F2, ParSide, _) ).

shares_at_least_one_vertex(T1, T2) :-
    atom_codes(T1, C1), atom_codes(T2, C2),
    member(X, C1), member(X, C2), !.

relationship_segment_touches(Es, T) :-
    atom_codes(T, Vs),
    member(E, Es),
    atom_codes(E, [A, B]),
    member(A, Vs), member(B, Vs).

gate_polygon_angle_sum_consistency :-
    findall(error(polygon_interior_angle_sum_violation, contradiction, Msg),
            ( entity(polygon, P),
              polygon_n_sides(P, N),
              findall(V, (polygon_angle(P, _, V), known(V)), Vs),
              length(Vs, N),
              sumlist(Vs, Sum),
              Expected is (N - 2) * 180,
              \+ approx_equal(Sum, Expected),
              format(atom(Msg),
                     "Polygon ~w (n=~w) has interior angles ~w that sum to ~w degrees, but an ~w-sided polygon's interior angles must sum to ~w degrees.",
                     [P, N, Vs, Sum, N, Expected])
            ),
            Errors),
    assert_errors(Errors).


% =====================================================================
% LAYER 2 -- TYPE COMPATIBILITY
% =====================================================================

% similar_AA/SAS/SSS accept triangles OR polygons (quadrilateral similarity etc.);
% any_figure covers both, exactly as similar_unspecified already does. The
% criterion-specific contradiction gates remain triangle-guarded, while
% gate_similarity_corresponding_pairs already handles n-gon under-determination.
scope(similar_AA,             [any_figure, any_figure]).
scope(similar_SAS,            [any_figure, any_figure]).
scope(similar_SSS,            [any_figure, any_figure]).
scope(similar_unspecified,    [any_figure, any_figure]).
scope(dilation,               [any_2d, any_2d]).
scope(scaled_copy,            [any_2d, any_2d]).
scope(scaled_copy_unspecified,[any_2d, any_2d]).
scope(parallel_lines,         [line, line]).
scope(parallel_segments,      [segment, segment]).
scope(midsegment_parallel,    [segment, segment]).
scope(transversal_cut,        [line, line, line]).
scope(parallel_lines_transversal, [line, line, line]).
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
scope(angle_sum_triangle,     [triangle]).
scope(angle_sum_polygon,      [polygon]).
scope(midsegment_ratio,       [segment, segment]).
scope(medial_triangle,        [triangle, triangle]).
% NOTE: proportional_segments, triangle_proportionality, altitude_to_hypotenuse,
% geometric_mean_altitude and geometric_mean_leg are ATTRIBUTE-DRIVEN: the
% derivation engine and their consistency gates read the participating segments
% from rel_attr keys (parallel_side/segment1/segment2/altitude_id/hypotenuse/
% leg_id/adjacent_segment), NOT from positional entities. Their entity list is
% therefore redundant, and a rigid positional scope only produced false
% scope_violations when the model listed a different-but-valid entity set. We
% intentionally give them NO scope/2 fact, so gate_relation_scope skips them;
% gate_shape_relevance still checks that every listed entity is a triangle or
% segment (valid_relationships_for), and the attribute contract still enforces
% the required rel_attr keys.
scope(perpendicular_lines,    [line, line]).
scope(perpendicular_segments, [segment, segment]).
scope(altitude_perpendicular, [segment, segment]).
scope(congruent_angles,       [list_of_any]).
scope(congruent_segments,     [list_of_segments]).
scope(congruent_triangles,    [triangle, triangle]).
scope(collinear_dilation,     [point, point, point]).
scope(center_on_figure,       [point, any_figure]).
scope(center_off_figure,      [point, any_figure]).
scope(lines_intersect,        [line, line]).
scope(segments_intersect,     [segment, segment]).
scope(point_on_line,          [point, any_linear]).
scope(point_interior,         [point, any_figure]).

is_point_entity(E)   :- known_point(E).
is_segment_entity(E) :- entity(segment, E).
is_segment_entity(E) :- triangle_side_of_any(E).
is_segment_entity(E) :- polygon_side_of_any(E).
is_segment_entity(E) :- implicit_point_to_point_segment(E).

kind_satisfies(_, any) :- !.
kind_satisfies(_, list_of_any) :- !.
kind_satisfies(E, list_of_segments) :- !, is_segment_entity(E).
kind_satisfies(E, any_figure) :- !,
    ( entity(triangle, E) ; entity(polygon, E) ; entity(circle, E) ).
kind_satisfies(E, any_polygonal) :- !,
    ( entity(triangle, E) ; entity(polygon, E) ).
kind_satisfies(E, any_2d) :- !,
    ( entity(triangle, E) ; entity(polygon, E) ; entity(circle, E) ; is_segment_entity(E) ).
kind_satisfies(E, any_linear) :- !,
    ( entity(line, E) ; is_segment_entity(E) ).
kind_satisfies(E, point)   :- !, is_point_entity(E).
kind_satisfies(E, segment) :- !, is_segment_entity(E).
kind_satisfies(E, Kind) :- entity(Kind, E).

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

scope_matches(Entities, [list_of_any]) :- !,
    forall(member(E, Entities), entity(_, E)).
scope_matches(Entities, [list_of_segments]) :- !,
    forall(member(E, Entities), is_segment_entity(E)).
scope_matches(Entities, ExpectedKinds) :-
    length(Entities, N),
    length(ExpectedKinds, N),
    scope_matches_positional(Entities, ExpectedKinds).

scope_matches_positional([], []).
scope_matches_positional([E | Es], [K | Ks]) :-
    kind_satisfies(E, K),
    scope_matches_positional(Es, Ks).

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

valid_relationships_for(triangle, [
    similar_AA, similar_SAS, similar_SSS, similar_unspecified,
    dilation, scaled_copy, scaled_copy_unspecified,
    triangle_proportionality, altitude_to_hypotenuse,
    geometric_mean_altitude, geometric_mean_leg,
    angle_sum_triangle, congruent_triangles, medial_triangle,
    center_on_figure, center_off_figure, point_interior
]).
valid_relationships_for(polygon, [
    similar_unspecified, similar_AA, similar_SAS, similar_SSS,
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

attribute_kind_expectation(dilation, center, point).
attribute_kind_expectation(dilation, pre_image, any_2d).
attribute_kind_expectation(dilation, image, any_2d).
attribute_kind_expectation(scaled_copy, pre_image, any_2d).
attribute_kind_expectation(scaled_copy, image, any_2d).
attribute_kind_expectation(similar_AA, pre_image, any_figure).
attribute_kind_expectation(similar_AA, image, any_figure).
attribute_kind_expectation(similar_SAS, pre_image, any_figure).
attribute_kind_expectation(similar_SAS, image, any_figure).
attribute_kind_expectation(similar_SSS, pre_image, any_figure).
attribute_kind_expectation(similar_SSS, image, any_figure).
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
% LAYER 3 -- MATHEMATICAL VALIDATION
% Every gate here guards values with known/1 and is SILENT on unknowns.
% A gate fires only on a contradiction between values that are ALL known.
% =====================================================================

gate_positive_lengths :-
    findall(error(non_positive_length, contradiction, Msg),
            ( ( triangle_side(T, K, V), known(V), V =< 0,
                format(atom(Msg), "Triangle ~w side ~w = ~w is non-positive. All side lengths must be > 0.", [T, K, V])
              ; polygon_side(P, K, V), known(V), V =< 0,
                format(atom(Msg), "Polygon ~w side ~w = ~w is non-positive.", [P, K, V])
              ; segment_length(S, V), known(V), V =< 0,
                format(atom(Msg), "Segment ~w length = ~w is non-positive.", [S, V])
              ; circle_radius(C, V), known(V), V =< 0,
                format(atom(Msg), "Circle ~w radius = ~w is non-positive.", [C, V])
              )
            ),
            Errors),
    assert_errors(Errors).

gate_angle_range :-
    findall(error(angle_out_of_range, contradiction, Msg),
            ( ( triangle_angle(T, K, V), known(V), (V =< 0 ; V >= 180),
                format(atom(Msg), "Triangle ~w angle ~w = ~w degrees is outside the valid range (0, 180).", [T, K, V])
              ; polygon_angle(P, K, V), known(V), (V =< 0 ; V >= 360),
                format(atom(Msg), "Polygon ~w angle ~w = ~w degrees is outside the valid range.", [P, K, V])
              )
            ),
            Errors),
    assert_errors(Errors).

gate_triangle_angle_sum :-
    findall(error(angle_sum_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_angle(T, K1, V1), triangle_angle(T, K2, V2), triangle_angle(T, K3, V3),
              K1 @< K2, K2 @< K3,
              known(V1), known(V2), known(V3),
              Sum is V1 + V2 + V3,
              \+ approx_equal(Sum, 180),
              format(atom(Msg),
                     "Triangle ~w angles (~w=~w, ~w=~w, ~w=~w) sum to ~w, not 180.",
                     [T, K1, V1, K2, V2, K3, V3, Sum])
            ),
            Errors),
    assert_errors(Errors).

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
                     "Triangle ~w is declared right, but sides (~w, ~w, ~w) fail a2+b2=c2. Got ~w2 + ~w2 = ~w but ~w2 = ~w.",
                     [T, V1, V2, V3, A, B, LegSumSq, Hyp, HypSq])
            ),
            Errors),
    assert_errors(Errors).

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

triangle_right_flag_declared(T, true) :- triangle_flag(T, is_right).
triangle_right_flag_declared(T, false) :- triangle_flag(T, is_not_right).

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

gate_isosceles_consistency :-
    findall(error(isosceles_inconsistent, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_isosceles),
              triangle_three_sides(T, _, _, _, V1, V2, V3),
              known(V1), known(V2), known(V3),
              \+ ( approx_equal(V1, V2) ; approx_equal(V2, V3) ; approx_equal(V1, V3) ),
              format(atom(Msg),
                     "Triangle ~w is declared isosceles but no two sides among (~w, ~w, ~w) are equal.",
                     [T, V1, V2, V3])
            ),
            Errors),
    assert_errors(Errors).

gate_right_angle_flag_consistency :-
    findall(error(right_flag_missing_for_90_angle, structural, Msg),
            ( entity(triangle, T),
              triangle_angle(T, K, V), known(V), V =:= 90,
              \+ triangle_flag(T, is_right),
              format(atom(Msg),
                     "Triangle ~w has angle ~w = 90 but is_right is not declared as true. When an explicit 90 degree angle is present, is_right should be set accordingly.",
                     [T, K])
            ),
            Errors1),
    findall(error(right_flag_without_90_angle, contradiction, Msg),
            ( entity(triangle, T),
              triangle_flag(T, is_right),
              findall(V, (triangle_angle(T, _, V), known(V)), KnownVs),
              length(KnownVs, N), N >= 1,
              forall(member(V, KnownVs), V =\= 90),
              format(atom(Msg),
                     "Triangle ~w is declared is_right = true but none of its known angles is 90 (known angles: ~w).",
                     [T, KnownVs])
            ),
            Errors2),
    append(Errors1, Errors2, Errors),
    assert_errors(Errors).

gate_law_of_cosines_consistency :-
    findall(error(law_of_cosines_violation, contradiction, Msg),
            ( entity(triangle, T),
              triangle_three_sides(T, _, _, _, _, _, _),
              all_three_sides_known(T, A, B, C),
              triangle_angle(T, AngleKey, AngleDeg),
              known(AngleDeg),
              opposite_side_length(T, AngleKey, OppLen, Side1Len, Side2Len),
              OppLen = C, Side1Len = A, Side2Len = B,
              cos_from_angle(AngleDeg, CosA),
              Denom is 2 * Side1Len * Side2Len,
              Denom > 0,
              CosFromSides is (Side1Len * Side1Len + Side2Len * Side2Len - OppLen * OppLen) / Denom,
              \+ approx_equal(CosA, CosFromSides),
              ImpliedDeg is acos(CosFromSides) * 180 / pi,
              format(atom(Msg),
                     "Triangle ~w fails the Law of Cosines: angle ~w is declared as ~w but the side lengths imply it must be ~2f (cos = ~3f from sides vs cos = ~3f from angle).",
                     [T, AngleKey, AngleDeg, ImpliedDeg, CosFromSides, CosA])
            ),
            Errors),
    assert_errors(Errors).

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
                     "Triangle ~w fails the Law of Sines: side opposite ~w is ~w with angle ~w (ratio ~2f), but side opposite ~w is ~w with angle ~w (ratio ~2f). These ratios must be equal.",
                     [T, AngleKey1, OppLen1, AngleDeg1, Ratio1, AngleKey2, OppLen2, AngleDeg2, Ratio2])
            ),
            Errors),
    assert_errors(Errors).

all_three_sides_known(T, A, B, C) :-
    triangle_side(T, S1, A), known(A),
    triangle_side(T, S2, B), known(B),
    triangle_side(T, S3, C), known(C),
    S1 @< S2, S2 @< S3.

opposite_side_length(T, AngleKey, OppLen, Adj1, Adj2) :-
    atom_codes(T, [V1, V2, V3]),
    atom_codes(AngleKey, [VA]),
    member(VA, [V1, V2, V3]),
    select(VA, [V1, V2, V3], [Other1, Other2]),
    opposite_side_id(Other1, Other2, OppId),
    adjacent_side_ids(VA, Other1, Other2, AdjId1, AdjId2),
    triangle_side(T, OppId, OppLen), known(OppLen),
    triangle_side(T, AdjId1, Adj1), known(Adj1),
    triangle_side(T, AdjId2, Adj2), known(Adj2).

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

cos_from_angle(Deg, Cos) :- Cos is cos(Deg * pi / 180).

law_of_sines_pair(T, AngleKey, AngleDeg, OppLen) :-
    triangle_angle(T, AngleKey, AngleDeg), known(AngleDeg),
    opposite_side_length(T, AngleKey, OppLen, _, _).


% --- Scale-factor coherence.  Uses approx_equal_scale (relative tolerance)
% so a rounded declared k (e.g. 1.667 for 5/3) does not false-fire, while a
% genuine mismatch (a wrong factor is off by tens of percent) still does. ---
geometric_correspondence_type(dilation).
geometric_correspondence_type(scaled_copy).
geometric_correspondence_type(scaled_copy_unspecified).

rel_attr_or_var(RIdx, Key, Val) :-
    ( rel_attr(RIdx, Key, V), known(V) -> Val = V ; true ).

triangle_vertex_list(T, [A, B, C]) :-
    atom_codes(T, [Ca, Cb, Cc]),
    atom_codes(A, [Ca]), atom_codes(B, [Cb]), atom_codes(C, [Cc]).

build_vmap([], [], []).
build_vmap([P | Ps], [I | Is], [P-I | Ms]) :- build_vmap(Ps, Is, Ms).

mapped_side_value(T, V1, V2, Val) :-
    ( pair_to_atom(V1, V2, S1), triangle_side(T, S1, Val) -> true
    ; pair_to_atom(V2, V1, S2), triangle_side(T, S2, Val) ).

map_known_ratios(Pre, Img, Map, Ratios) :-
    triangle_vertex_list(Pre, [A, B, C]),
    findall(R,
            ( member([X, Y], [[A, B], [B, C], [C, A]]),
              mapped_side_value(Pre, X, Y, PV), known(PV), PV > 0,
              member(X-MX, Map), member(Y-MY, Map),
              mapped_side_value(Img, MX, MY, IV), known(IV),
              R is IV / PV ),
            Ratios).

candidate_vmap(Pre, Img, Center, Map) :-
    triangle_vertex_list(Pre, PVs),
    triangle_vertex_list(Img, IVs),
    permutation(IVs, IPerm),
    build_vmap(PVs, IPerm, Map),
    ( var(Center) -> true
    ; ( member(Center, PVs), member(Center, IVs) )
      -> member(Center-Center, Map)
    ;  true ).

candidate_vmap_coverage(Pre, Img, Center, Map, Cov, Ratios) :-
    candidate_vmap(Pre, Img, Center, Map),
    map_known_ratios(Pre, Img, Map, Ratios),
    length(Ratios, Cov).

max_correspondence_coverage(Pre, Img, Center, MaxCov) :-
    findall(Cov, candidate_vmap_coverage(Pre, Img, Center, _, Cov, _), Covs),
    Covs \= [],
    max_list(Covs, MaxCov).

exists_correspondence_for_k(Pre, Img, Center, K) :-
    entity(triangle, Pre), entity(triangle, Img),
    max_correspondence_coverage(Pre, Img, Center, MaxCov),
    MaxCov > 0,
    candidate_vmap_coverage(Pre, Img, Center, _, MaxCov, Ratios),
    forall(member(R, Ratios), approx_equal_scale(R, K)),
    !.

exists_correspondence_common_ratio(Pre, Img, Center) :-
    entity(triangle, Pre), entity(triangle, Img),
    max_correspondence_coverage(Pre, Img, Center, MaxCov),
    MaxCov > 0,
    candidate_vmap_coverage(Pre, Img, Center, _, MaxCov, Ratios),
    Ratios = [R0 | _],
    forall(member(R, Ratios), approx_equal_scale(R, R0)),
    !.

scaling_correspondence_rescues(Type, RIdx, Pre, Img, K) :-
    geometric_correspondence_type(Type),
    rel_attr_or_var(RIdx, center, Center),
    exists_correspondence_for_k(Pre, Img, Center, K).

scaling_correspondence_rescues_common(Type, RIdx, Pre, Img) :-
    geometric_correspondence_type(Type),
    rel_attr_or_var(RIdx, center, Center),
    exists_correspondence_common_ratio(Pre, Img, Center).

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
              \+ approx_equal_scale(Expected, ImgV),
              \+ scaling_correspondence_rescues(Type, RIdx, Pre, Img, K),
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
              \+ scaling_correspondence_rescues_common(Type, RIdx, Pre, Img),
              format_pair_ratios(Pairs, PairStr),
              format(atom(Msg),
                     "Relationship ~w (index ~w) has multiple corresponding-side pairs that imply different scale factors: ~w. All pairs must yield the same ratio.",
                     [Type, RIdx, PairStr])
            ),
            Errors),
    assert_errors(Errors).

known_corresponding_pairs(Pre, Img, Pairs) :-
    ( entity(triangle, Pre), entity(triangle, Img) ->
        findall(pair(PS, IS, PV, IV),
                ( corresponding_side_pair(Pre, Img, PS, IS, PV, IV), known(PV), known(IV) ),
                Pairs0)
    ; entity(polygon, Pre), entity(polygon, Img) ->
        findall(pair(PS, IS, PV, IV),
                ( polygon_corresponding_pair(Pre, Img, PS, IS, PV, IV), known(PV), known(IV) ),
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
    approx_equal_scale(R1, R2),
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

side_position_match(T1, S1, T2, S2) :-
    side_position(T1, S1, P),
    side_position(T2, S2, P).

side_position(T, Side, Pos) :-
    atom_codes(T, [A, B, C]),
    nth1(Pos, [[A,B],[B,C],[C,A]], [X,Y]),
    ( nonvar(Side) ->
        ( pair_to_atom(X, Y, Side) ; pair_to_atom(Y, X, Side) )
    ;   ( pair_to_atom(X, Y, S1), triangle_side(T, S1, _) -> Side = S1
        ; pair_to_atom(Y, X, S2), triangle_side(T, S2, _) -> Side = S2
        ; pair_to_atom(X, Y, Side)
        )
    ).


gate_similarity_corresponding_pairs :-
    findall(error(insufficient_similarity_evidence, underdetermined, Msg),
            ( relationship(RIdx, Type, [E1, E2]),
              member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
              entity(polygon, E1), entity(polygon, E2),
              % A declared scale factor IS the similarity premise (the figures are
              % given as similar with that ratio), so the pair is not
              % under-determined even if the corresponding sides/angles aren't all
              % independently listed.
              \+ ( rel_attr(RIdx, scale_factor, SF), known(SF) ),
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
    findall(K, ( polygon_side(P1, K, V1), known(V1), polygon_side(P2, K, V2), known(V2) ), Ks),
    length(Ks, Count).

count_corresponding_angles(P1, P2, Count) :-
    findall(K, ( polygon_angle(P1, K, V1), known(V1), polygon_angle(P2, K, V2), known(V2) ), Ks),
    length(Ks, Count).

gate_aa_similarity_two_pairs :-
    findall(error(aa_contradiction, contradiction, Msg),
            ( relationship(RIdx, similar_AA, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              rel_attr(RIdx, congruent_angle_pairs, Pairs),
              member([K1, K2], Pairs),
              triangle_angle(T1, K1, V1), known(V1),
              triangle_angle(T2, K2, V2), known(V2),
              \+ approx_equal(V1, V2),
              format(atom(Msg),
                     "similar_AA (relationship ~w) declares angle ~w congruent to ~w, but their known measures differ (~w vs ~w). A declared similarity may be assumed when data is silent, but here the data contradicts it.",
                     [RIdx, K1, K2, V1, V2])
            ),
            Errors),
    assert_errors(Errors).

count_derivable_congruent_angle_pairs(T1, T2, N) :-
    triangle_all_angles_resolved(T1, A1List),
    triangle_all_angles_resolved(T2, A2List),
    findall(1,
            ( member(_-V1, A1List), known(V1),
              member(_-V2, A2List), known(V2),
              approx_equal(V1, V2) ),
            Ones),
    length(Ones, N).

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

gate_sss_similarity_three_sides :-
    findall(error(sss_contradiction, contradiction, Msg),
            ( relationship(RIdx, similar_SSS, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              known_corresponding_pairs(T1, T2, Pairs),
              length(Pairs, N), N >= 2,
              \+ all_pairs_same_ratio(Pairs),
              format(atom(Msg),
                     "similar_SSS (relationship ~w) between ~w and ~w has known corresponding sides with inconsistent ratios. A declared similarity may be assumed when data is silent, but here the known sides contradict a single scale factor.",
                     [RIdx, T1, T2])
            ),
            Errors),
    assert_errors(Errors).

count_known_sides(T, N) :-
    findall(K, (triangle_side(T, K, V), known(V)), Ks),
    length(Ks, N).

gate_sas_similarity_complete :-
    findall(error(sas_contradiction, contradiction, Msg),
            ( relationship(RIdx, similar_SAS, [T1, T2]),
              entity(triangle, T1), entity(triangle, T2),
              ( ( known_corresponding_pairs(T1, T2, Pairs),
                  length(Pairs, N), N >= 2,
                  \+ all_pairs_same_ratio(Pairs),
                  format(atom(Msg),
                         "similar_SAS (relationship ~w) between ~w and ~w has known corresponding sides with inconsistent ratios.",
                         [RIdx, T1, T2])
                )
              ; ( rel_attr(RIdx, congruent_angle_pairs, APairs),
                  member([AK1, AK2], APairs),
                  triangle_angle(T1, AK1, AV1), known(AV1),
                  triangle_angle(T2, AK2, AV2), known(AV2),
                  \+ approx_equal(AV1, AV2),
                  format(atom(Msg),
                         "similar_SAS (relationship ~w) declares angle ~w congruent to ~w, but their known measures differ (~w vs ~w).",
                         [RIdx, AK1, AK2, AV1, AV2])
                )
              )
            ),
            Errors),
    assert_errors(Errors).

count_known_angles(T, N) :-
    findall(K, (triangle_angle(T, K, V), known(V)), Explicit),
    length(Explicit, Ne),
    findall(V, (triangle_angle(T, _, V), known(V), V =:= 90), Right90s),
    length(Right90s, NumExplicit90),
    ( triangle_flag(T, is_equilateral) -> N = 3
    ; triangle_flag(T, is_right), NumExplicit90 == 0 -> N is Ne + 1
    ; N = Ne
    ).

gate_similarity_included_angle_vertex :-
    findall(error(included_angle_vertex_mismatch, contradiction, Msg),
            ( relationship(RIdx, Type, _),
              member(Type, [similar_AA, similar_SAS, similar_unspecified]),
              rel_attr(RIdx, congruent_angle_pairs, Pairs),
              rel_attr(RIdx, pre_image, T1),
              rel_attr(RIdx, image, T2),
              two_known_sides_shared_vertex(T1, CV1),
              two_known_sides_shared_vertex(T2, CV2),
              \+ ( member([P1, P2], Pairs), P1 == CV1, P2 == CV2 ),
              format(atom(Msg),
                     "Similarity (relationship ~w): the given sides of ~w meet at vertex ~w and the given sides of ~w meet at vertex ~w, but no declared congruent angle pair places the matched angle at those included vertices (expected the pair [~w,~w]). The given sides must enclose the matched angle.",
                     [RIdx, T1, CV1, T2, CV2, CV1, CV2])
            ),
            Errors),
    assert_errors(Errors).

two_known_sides_shared_vertex(T, CV) :-
    entity(triangle, T),
    findall(S, (triangle_side(T, S, V), known(V)), KnownSides),
    KnownSides = [S1, S2],
    shared_vertex_of_sides(S1, S2, CV).

shared_vertex_of_sides(S1, S2, CV) :-
    atom_codes(S1, C1), atom_codes(S2, C2),
    member(Code, C1), member(Code, C2),
    atom_codes(CV, [Code]).

gate_invariant_constants :-
    findall(error(invariant_violation, contradiction, Msg),
            ( ( relationship(RIdx, supplementary_angles, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg), "supplementary_angles (relationship ~w) declares sum=~w; it must always be 180.", [RIdx, V])
              ; relationship(RIdx, complementary_angles, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 90),
                format(atom(Msg), "complementary_angles (relationship ~w) declares sum=~w; it must always be 90.", [RIdx, V])
              ; relationship(RIdx, linear_pair, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg), "linear_pair (relationship ~w) declares sum=~w; it must always be 180.", [RIdx, V])
              ; relationship(RIdx, midsegment_ratio, _),
                rel_attr(RIdx, ratio, V), known(V), \+ approx_equal(V, 0.5),
                format(atom(Msg), "midsegment_ratio (relationship ~w) declares ratio=~w; it must always be 0.5.", [RIdx, V])
              ; relationship(RIdx, angle_sum_triangle, _),
                rel_attr(RIdx, sum, V), known(V), \+ approx_equal(V, 180),
                format(atom(Msg), "angle_sum_triangle (relationship ~w) declares sum=~w; it must always be 180.", [RIdx, V])
              ; relationship(RIdx, angle_sum_polygon, _),
                rel_attr(RIdx, exterior_sum, V), known(V), \+ approx_equal(V, 360),
                format(atom(Msg), "angle_sum_polygon (relationship ~w) declares exterior_sum=~w; it must always be 360.", [RIdx, V])
              )
            ),
            Errors),
    assert_errors(Errors).

gate_polygon_interior_sum :-
    findall(error(polygon_interior_sum_wrong, contradiction, Msg),
            ( relationship(RIdx, angle_sum_polygon, _),
              rel_attr(RIdx, num_sides, N), known(N),
              rel_attr(RIdx, interior_sum, S), known(S),
              Expected is (N - 2) * 180,
              \+ approx_equal(S, Expected),
              format(atom(Msg), "Polygon with ~w sides has interior angle sum (n-2)*180 = ~w, not ~w.", [N, Expected, S])
            ),
            Errors),
    assert_errors(Errors).

gate_right_angle_hypotenuse_consistency :-
    findall(error(right_angle_side_contradiction, contradiction, Msg),
            ( entity(triangle, T),
              atom_codes(T, [V1, V2, V3]),
              triangle_angle(T, AngleKey, AV), known(AV), AV =:= 90,
              atom_codes(AngleKey, [VA]),
              member(VA, [V1, V2, V3]),
              select(VA, [V1, V2, V3], [O1, O2]),
              opposite_side_id(O1, O2, HypId),
              triangle_side(T, HypId, HypV), known(HypV),
              adjacent_side_ids(VA, O1, O2, LegId1, LegId2),
              member(LegId, [LegId1, LegId2]),
              triangle_side(T, LegId, LegV), known(LegV),
              LegV > HypV,
              format(atom(Msg),
                     "Triangle ~w has a right angle at ~w, so side ~w (length ~w) is the hypotenuse and must be the longest side. But leg ~w (length ~w) is longer. The right angle cannot be at ~w with these side lengths.",
                     [T, AngleKey, HypId, HypV, LegId, LegV, AngleKey])
            ),
            Errors1),
    findall(error(right_angle_pythagorean_violation, contradiction, Msg),
            ( entity(triangle, T),
              atom_codes(T, [V1, V2, V3]),
              triangle_angle(T, AngleKey, AV), known(AV), AV =:= 90,
              atom_codes(AngleKey, [VA]),
              member(VA, [V1, V2, V3]),
              select(VA, [V1, V2, V3], [O1, O2]),
              opposite_side_id(O1, O2, HypId),
              triangle_side(T, HypId, HypV), known(HypV),
              adjacent_side_ids(VA, O1, O2, LegId1, LegId2),
              triangle_side(T, LegId1, L1), known(L1),
              triangle_side(T, LegId2, L2), known(L2),
              Predicted is sqrt(L1*L1 + L2*L2),
              \+ approx_equal(Predicted, HypV),
              format(atom(Msg),
                     "Triangle ~w has a right angle at ~w with legs ~w=~w and ~w=~w, so the hypotenuse ~w must be ~2f, but it is declared as ~w.",
                     [T, AngleKey, LegId1, L1, LegId2, L2, HypId, Predicted, HypV])
            ),
            Errors2),
    append(Errors1, Errors2, Errors),
    assert_errors(Errors).

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
                     "angle_sum_polygon (index ~w) is declared for polygon ~w (n=~w) but only ~w angle(s) are independently known. The relationship adds no constraint unless at least ~w angles are declared.",
                     [RIdx, P, N, NA, Needed])
            ),
            Errors2),
    append(Errors1, Errors2, Errors),
    assert_errors(Errors).

count_explicit_known_angles(T, N) :-
    findall(K, (triangle_angle(T, K, V), known(V)), Ks), length(Ks, N).

count_explicit_known_polygon_angles(P, N) :-
    findall(K, (polygon_angle(P, K, V), known(V)), Ks), length(Ks, N).

gate_midsegment_consistency :-
    findall(error(midsegment_inconsistent, contradiction, Msg),
            ( entity(segment, S),
              segment_flag(S, is_midsegment),
              segment_parallel_to(S, Side),
              segment_length(S, SV), known(SV),
              ( triangle_side(_, Side, BV) ; segment_length(Side, BV) ),
              known(BV),
              Half is BV / 2,
              \+ approx_equal(SV, Half),
              format(atom(Msg),
                     "Segment ~w is declared a midsegment parallel to ~w; midsegment length should be half of ~w (=~w), but is declared ~w.",
                     [S, Side, BV, Half, SV])
            ),
            Errors),
    assert_errors(Errors).

% Companion to gate_midsegment_consistency for problems that declare the
% parallel pairing via a `midsegment_parallel` RELATIONSHIP (rather than a
% segment_parallel_to fact) and carry the midsegment's own length as a triangle
% side (rather than a segment_length fact). A midsegment must be exactly half
% its parallel full side; when both lengths are known and that fails, it is a
% mathematical contradiction. Without this, lesson_05-style midsegment problems
% whose corresponding sides do not check out passed validation silently.
gate_midsegment_parallel_consistency :-
    findall(error(midsegment_inconsistent, contradiction, Msg),
            ( relationship(_, midsegment_parallel, [Mid, Side]),
              segment_or_side_length(Mid, MV), known(MV),
              segment_or_side_length(Side, BV), known(BV),
              Half is BV / 2,
              \+ approx_equal(MV, Half),
              format(atom(Msg),
                     "Segment ~w is declared a midsegment parallel to ~w; its length should be half of ~w (=~w), but is declared ~w.",
                     [Mid, Side, BV, Half, MV])
            ),
            Errors),
    assert_errors(Errors).

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

find_companion_dilation_scale(C, _, _, K) :-
    relationship(_, dilation, _Es),
    rel_attr(RIdx2, center, C),
    relationship(RIdx2, dilation, _),
    rel_attr(RIdx2, scale_factor, K), known(K).
find_companion_dilation_scale(_, _, _, 1).

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

gate_point_position_consistency :-
    findall(error(point_position_inconsistent, contradiction, Msg),
            ( relationship(_, collinear_dilation, _Es),
              rel_attr(CDIdx, center, C),
              rel_attr(CDIdx, pre_image_point, PreP),
              rel_attr(CDIdx, image_point, ImgP),
              relationship(CDIdx, collinear_dilation, _),
              point_lies_on(ImgP, SegId),
              \+ segment_contains_dilation_ray(SegId, C, PreP),
              format(atom(Msg),
                     "Point ~w is declared the image of ~w under dilation centered at ~w, but it also lies on segment ~w which does not contain the ray from ~w through ~w.",
                     [ImgP, PreP, C, SegId, C, PreP])
            ),
            Errors),
    assert_errors(Errors).

segment_contains_dilation_ray(SegId, C, PreP) :-
    atom_codes(SegId, [V1, V2]),
    atom_codes(C, [V1]),
    atom_codes(PreP, [V2]).
segment_contains_dilation_ray(SegId, C, PreP) :-
    atom_codes(SegId, [V1, V2]),
    atom_codes(C, [V2]),
    atom_codes(PreP, [V1]).


% =====================================================================
% LAYER 4 -- DETERMINACY
% The ONLY layer that cares about unknowns, and only about the target.
% =====================================================================

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
key_belongs_to_entity(E, sides, K) :-
    entity(triangle, E), triangle_implicit_side(E, K).
key_belongs_to_entity(E, angles, K) :-
    entity(triangle, E), atom_codes(E, Vertices), atom_codes(K, [V]), member(V, Vertices).
key_belongs_to_entity(E, sides, K) :-
    entity(polygon, E), polygon_implicit_side(E, K).
key_belongs_to_entity(E, angles, K) :-
    entity(polygon, E), atom_codes(E, Vertices), atom_codes(K, [V]), member(V, Vertices).

triangle_implicit_side(T, Side) :-
    atom_codes(T, [A, B, C]),
    pair_to_atom(A, B, AB), pair_to_atom(B, C, BC), pair_to_atom(C, A, CA),
    member(Side, [AB, BC, CA]).
triangle_implicit_side(T, Side) :-
    atom_codes(T, [A, B, C]),
    pair_to_atom(B, A, BA), pair_to_atom(C, B, CB), pair_to_atom(A, C, AC),
    member(Side, [BA, CB, AC]).

polygon_implicit_side(Poly, Side) :-
    atom_codes(Poly, Vertices),
    consecutive_pair(Vertices, V1, V2),
    ( pair_to_atom(V1, V2, Side) ; pair_to_atom(V2, V1, Side) ).

consecutive_pair(List, V1, V2) :-
    append(_, [V1, V2 | _], List).
consecutive_pair(List, V1, V2) :-
    last(List, V1), List = [V2 | _].

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
    findall(K, ( entity(triangle, E), atom_codes(E, Vs), member(V, Vs), atom_codes(K, [V]) ), TriImplicit),
    findall(K, ( entity(polygon, E), atom_codes(E, Vs), member(V, Vs), atom_codes(K, [V]) ), PolyImplicit),
    append([TKeys, PKeys, TriImplicit, PolyImplicit], All),
    list_to_set(All, Keys).

% Sufficiency pre-check: a target SIDE on the IMAGE of a scaling relationship
% is underdetermined only if BOTH the scale factor is underivable AND the
% corresponding pre-image side is unknown. (Pre-image targets are handled by
% the inversion clauses in target_derivable and by gate_target_resolvable.)
gate_target_dilation_pair_underdetermined :-
    target(Entity, AttrSpec),
    parse_attr(AttrSpec, sides, TargetKey),
    ( triangle_side(Entity, TargetKey, _) ; polygon_side(Entity, TargetKey, _) ),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                  similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    rel_attr(RIdx, image, Entity),
    rel_attr(RIdx, pre_image, Pre),
    \+ scale_factor_derivable(RIdx, Pre, Entity),
    \+ corresponding_pre_image_side_known(Pre, Entity, TargetKey),
    format(atom(Msg),
           "Target ~w.~w is under-determined: under relationship ~w (index ~w), neither the scale factor nor the corresponding side on pre-image ~w is known.",
           [Entity, AttrSpec, Type, RIdx, Pre]),
    assert_error(error(target_dilation_underdetermined, underdetermined, Msg)).
gate_target_dilation_pair_underdetermined :-
    target(Entity, length),
    entity(segment, Entity),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified, similar_unspecified]),
    rel_attr(RIdx, image, Entity),
    rel_attr(RIdx, pre_image, Pre),
    entity(segment, Pre),
    \+ scale_factor_derivable(RIdx, Pre, Entity),
    \+ ( segment_length(Pre, V), known(V) ),
    format(atom(Msg),
           "Target ~w.length is under-determined: under relationship ~w (index ~w), neither the scale factor nor the pre-image segment ~w length is known.",
           [Entity, Type, RIdx, Pre]),
    assert_error(error(target_dilation_underdetermined, underdetermined, Msg)).
gate_target_dilation_pair_underdetermined.

scale_factor_derivable(RIdx, _, _) :-
    rel_attr(RIdx, scale_factor, K), known(K), !.
scale_factor_derivable(_, Pre, Img) :-
    corresponding_side_pair_known(Pre, Img).

corresponding_side_pair_known(Pre, Img) :-
    ( entity(triangle, Pre), entity(triangle, Img),
      corresponding_side_pair(Pre, Img, _, _, PreV, ImgV), known(PreV), known(ImgV)
    ; entity(polygon, Pre), entity(polygon, Img),
      polygon_corresponding_pair_known(Pre, Img)
    ; entity(circle, Pre), entity(circle, Img),
      circle_radius(Pre, R1), known(R1), circle_radius(Img, R2), known(R2)
    ; entity(segment, Pre), entity(segment, Img),
      segment_length(Pre, L1), known(L1), segment_length(Img, L2), known(L2)
    ).

polygon_corresponding_pair_known(Pre, Img) :-
    findall(V, polygon_side(Pre, _, V), PreVs),
    findall(V, polygon_side(Img, _, V), ImgVs),
    nth_pair_both_known(PreVs, ImgVs).

nth_pair_both_known([V1 | _], [V2 | _]) :- known(V1), known(V2), !.
nth_pair_both_known([_ | Rest1], [_ | Rest2]) :- nth_pair_both_known(Rest1, Rest2).

% Corresponding pre-image side known -- position-based, direction-agnostic.
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

target_already_specified(Entity, AttrSpec) :-
    parse_attr(AttrSpec, Group, Key),
    target_value_already_known(Entity, Group, Key, _).


gate_target_resolvable :-
    target(Entity, Attr),
    ( target_already_specified(Entity, Attr)
      -> format(atom(Msg), "Target ~w.~w is already given a value...", [Entity, Attr]),
         assert_error(error(target_undetermined, underdetermined, Msg))
    ; target_derivable(Entity, Attr) -> true
    ; format(atom(Msg), "Target ~w.~w is under-determined...", [Entity, Attr]),
      assert_error(error(target_undetermined, underdetermined, Msg))
    ).

% --- target_derivable/3: the reachability engine. Trace = theorem list. ---
target_derivable(Entity, Attr) :- target_derivable(Entity, Attr, _Trace).

% Triangle IMAGE side via known dilation scale factor.
target_derivable(T, AttrSpec, [scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, dilation, _),
    rel_attr(RIdx, image, T),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    side_position(T, SideKey, Pos),
    side_position(Pre, PreSide, Pos),
    triangle_side(Pre, PreSide, PreV), known(PreV).

% Triangle IMAGE side via similarity/scaled_copy scale factor.
target_derivable(T, AttrSpec, [scale_factor]) :-
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

% Triangle IMAGE side, k derivable from a known corresponding pair.
target_derivable(T, AttrSpec, [scale_factor_from_pair, scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified,
                  scaled_copy, scaled_copy_unspecified, dilation]),
    rel_attr(RIdx, image, T),
    rel_attr(RIdx, pre_image, Pre),
    \+ ( rel_attr(RIdx, scale_factor, K0), known(K0) ),
    corresponding_side_pair(Pre, T, _, _, PreKnown, ImgKnown),
    known(PreKnown), known(ImgKnown),
    side_position(T, SideKey, Pos),
    side_position(Pre, PreSide, Pos),
    triangle_side(Pre, PreSide, PreV), known(PreV).

% ---- ACCURACY FIX: polygon sides + pre-image inversion ----
% These four clauses close the L01 (polygon side) and L10 (pre-image) solver
% gaps. The direction principle: a scaling relationship gives
% image = pre_image * k. To solve an IMAGE side you multiply by k; to solve a
% PRE-IMAGE side you divide by k (inversion). Both need the OTHER side of the
% pair known and k known-or-derivable. Nothing here invents a value; each
% requires the specific known input and leaves the target null.

% POLYGON IMAGE side via known k.
target_derivable(Poly, AttrSpec, [scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(polygon, Poly),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified, similar_unspecified,
                  similar_AA, similar_SAS, similar_SSS]),
    rel_attr(RIdx, image, Poly),
    rel_attr(RIdx, pre_image, Pre),
    entity(polygon, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    polygon_side_position(Poly, SideKey, Pos),
    nth_polygon_side_known(Pre, Pos).

% POLYGON IMAGE side, k from a known corresponding pair.
target_derivable(Poly, AttrSpec, [scale_factor_from_pair, scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(polygon, Poly),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified, similar_unspecified,
                  similar_AA, similar_SAS, similar_SSS]),
    rel_attr(RIdx, image, Poly),
    rel_attr(RIdx, pre_image, Pre),
    entity(polygon, Pre),
    \+ ( rel_attr(RIdx, scale_factor, K0), known(K0) ),
    polygon_corresponding_pair(Pre, Poly, _, _, PreKnown, ImgKnown),
    known(PreKnown), known(ImgKnown),
    polygon_side_position(Poly, SideKey, Pos),
    nth_polygon_side_known(Pre, Pos).

% POLYGON PRE-IMAGE side via known k (inversion).
target_derivable(Poly, AttrSpec, [scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(polygon, Poly),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified, similar_unspecified,
                  similar_AA, similar_SAS, similar_SSS]),
    rel_attr(RIdx, pre_image, Poly),
    rel_attr(RIdx, image, Img),
    entity(polygon, Img),
    rel_attr(RIdx, scale_factor, K), known(K),
    polygon_side_position(Poly, SideKey, Pos),
    nth_polygon_side_known(Img, Pos).

% TRIANGLE PRE-IMAGE side via known k (inversion).
target_derivable(T, AttrSpec, [scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                  similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    rel_attr(RIdx, pre_image, T),
    rel_attr(RIdx, image, Img),
    entity(triangle, Img),
    rel_attr(RIdx, scale_factor, K), known(K),
    side_position(T, SideKey, Pos),
    side_position(Img, ImgSide, Pos),
    triangle_side(Img, ImgSide, ImgV), known(ImgV).

% TRIANGLE PRE-IMAGE side, k from a known corresponding pair (inversion).
target_derivable(T, AttrSpec, [scale_factor_from_pair, scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified,
                  similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    rel_attr(RIdx, pre_image, T),
    rel_attr(RIdx, image, Img),
    entity(triangle, Img),
    \+ ( rel_attr(RIdx, scale_factor, K0), known(K0) ),
    corresponding_side_pair(T, Img, _, _, PreKnown, ImgKnown),
    known(PreKnown), known(ImgKnown),
    side_position(T, SideKey, Pos),
    side_position(Img, ImgSide, Pos),
    triangle_side(Img, ImgSide, ImgV), known(ImgV).
% ---- end accuracy-fix clauses ----

target_derivable(T, AttrSpec, [pythagorean]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= SideKey, known(V)), Vs),
    length(Vs, 2).

target_derivable(SegId, length, [pythagorean]) :-
    entity(triangle, T),
    triangle_flag(T, is_right),
    triangle_implicit_side(T, SegId),
    findall(V, ( triangle_side(T, K, V), known(V), \+ matches_side_id(K, SegId) ), Vs),
    length(Vs, 2).

target_derivable(T, AttrSpec, [law_of_cosines]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    findall(K-V, (triangle_side(T, K, V), K \= SideKey, known(V)), Others),
    length(Others, 2),
    Others = [K1-_, K2-_],
    shared_vertex_of_sides(K1, K2, IncV),
    triangle_angle(T, IncV, AngV), known(AngV).

target_derivable(T, AttrSpec, [law_of_sines]) :-
    parse_attr(AttrSpec, sides, _SideKey),
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)),
    triangle_angle(T, KnownAngleKey, KnownAngleV), known(KnownAngleV),
    opposite_side_length(T, KnownAngleKey, KnownOpp, _, _), known(KnownOpp).

target_derivable(SegId, length, [geometric_mean_leg | Sub]) :-
    relationship(_, geometric_mean_leg, _),
    rel_attr(RIdx, leg_id, LegId),
    rel_attr(RIdx, hypotenuse, HypId),
    rel_attr(RIdx, adjacent_segment, AdjId),
    relationship(RIdx, geometric_mean_leg, _),
    member(SegId, [LegId, HypId, AdjId]),
    other_two(SegId, [LegId, HypId, AdjId], Other1, Other2),
    sos_derivable(Other1, Sub1),
    sos_derivable(Other2, Sub2),
    append(Sub1, Sub2, Sub).

other_two(X, [A, B, C], Y, Z) :- select(X, [A, B, C], [Y, Z]).

target_derivable(SegId, length, [geometric_mean_altitude | Sub]) :-
    relationship(_, geometric_mean_altitude, _),
    rel_attr(RIdx, altitude_id, AltId),
    rel_attr(RIdx, segment1, Seg1Id),
    rel_attr(RIdx, segment2, Seg2Id),
    relationship(RIdx, geometric_mean_altitude, _),
    member(SegId, [AltId, Seg1Id, Seg2Id]),
    other_two(SegId, [AltId, Seg1Id, Seg2Id], Other1, Other2),
    sos_derivable(Other1, Sub1),
    sos_derivable(Other2, Sub2),
    append(Sub1, Sub2, Sub).

target_derivable(SegId, length, [altitude_to_hypotenuse_split | Sub]) :-
    relationship(_, altitude_to_hypotenuse, _),
    rel_attr(RIdx, hypotenuse, HypId),
    rel_attr(RIdx, segment1, Seg1Id),
    rel_attr(RIdx, segment2, Seg2Id),
    relationship(RIdx, altitude_to_hypotenuse, _),
    member(SegId, [HypId, Seg1Id, Seg2Id]),
    other_two(SegId, [HypId, Seg1Id, Seg2Id], Other1, Other2),
    sos_derivable(Other1, Sub1),
    sos_derivable(Other2, Sub2),
    append(Sub1, Sub2, Sub).

target_derivable(AltId, length, [geometric_mean_altitude]) :-
    relationship(_, altitude_to_hypotenuse, _),
    rel_attr(RIdx, altitude_id, AltId),
    relationship(RIdx, altitude_to_hypotenuse, _),
    rel_attr(RIdx, hypotenuse, HypId),
    entity(triangle, T),
    triangle_implicit_side(T, HypId),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= HypId, known(V)), Legs),
    length(Legs, 2).

target_derivable(SegId, length, [geometric_mean_leg | SubHyp]) :-
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
    sos_derivable(HypId, SubHyp).

sos_derivable(Id, []) :-
    segment_or_side_length(Id, V), known(V), !.
sos_derivable(Id, [pythagorean]) :-
    entity(triangle, T),
    triangle_implicit_side(T, Id),
    triangle_flag(T, is_right),
    findall(V, (triangle_side(T, K, V), K \= Id, known(V)), Vs),
    length(Vs, 2), !.
sos_derivable(Id, [law_of_sines]) :-
    entity(triangle, T),
    triangle_implicit_side(T, Id),
    triangle_all_angles_resolved(T, AngleList),
    forall(member(_-V, AngleList), known(V)),
    triangle_angle(T, KnownAngleKey, KnownAngleV), known(KnownAngleV),
    opposite_side_length(T, KnownAngleKey, KnownOpp, _, _), known(KnownOpp), !.

segment_or_side_known_or_derivable(Id) :- sos_derivable(Id, _).

target_derivable(T, AttrSpec, [triangle_angle_sum]) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    findall(V, (triangle_angle(T, _, V), known(V)), Vs),
    length(Vs, 2).

target_derivable(T, AttrSpec, [law_of_cosines]) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    findall(V, (triangle_side(T, _, V), known(V)), Vs),
    length(Vs, 3).

target_derivable(T, AttrSpec, [corresponding_angle]) :-
    parse_attr(AttrSpec, angles, AngleKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    ( rel_attr(RIdx, image, T), rel_attr(RIdx, pre_image, Partner)
    ; rel_attr(RIdx, pre_image, T), rel_attr(RIdx, image, Partner)
    ),
    rel_attr(RIdx, congruent_angle_pairs, Pairs),
    ( member([AngleKey, PartnerKey], Pairs) ; member([PartnerKey, AngleKey], Pairs) ),
    triangle_angle(Partner, PartnerKey, V), known(V).

target_derivable(T, AttrSpec, [corresponding_angle | SubPartner]) :-
    parse_attr(AttrSpec, angles, _AngleKey),
    entity(triangle, T),
    relationship(_, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified]),
    relationship(RIdx, Type, _),
    ( rel_attr(RIdx, image, T), rel_attr(RIdx, pre_image, Partner)
    ; rel_attr(RIdx, pre_image, T), rel_attr(RIdx, image, Partner)
    ),
    entity(triangle, Partner),
    partner_angles_subtrace(Partner, SubPartner).

partner_angles_subtrace(T, [triangle_angle_sum]) :-
    findall(V, (triangle_angle(T, _, V), known(V)), AVs),
    length(AVs, NA), NA >= 2, !.
partner_angles_subtrace(T, [law_of_cosines]) :-
    findall(V, (triangle_side(T, _, V), known(V)), SVs),
    length(SVs, 3), !.
partner_angles_subtrace(T, []) :-
    triangle_flag(T, is_equilateral), !.

triangle_all_angles_known_or_derivable(T) :- partner_angles_subtrace(T, _).

target_derivable(S, length, [midsegment]) :-
    entity(segment, S),
    segment_flag(S, is_midsegment),
    segment_parallel_to(S, Side),
    segment_or_side_length(Side, BV), known(BV).

target_derivable(S, length, [midsegment]) :-
    entity(segment, S),
    relationship(_, midsegment_ratio, [S, Base]),
    segment_or_side_length(Base, BV), known(BV).

target_derivable(_, AttrSpec, [midsegment]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(segment, Mid),
    segment_flag(Mid, is_midsegment),
    segment_parallel_to(Mid, ParallelTarget),
    ( ParallelTarget == SideKey ; matches_side_id(ParallelTarget, SideKey) ),
    segment_length(Mid, V), known(V).

target_derivable(Side, length, [midsegment]) :-
    entity(segment, Mid),
    segment_flag(Mid, is_midsegment),
    segment_parallel_to(Mid, Side),
    segment_length(Mid, V), known(V).

% Midsegment length from its parallel FULL side, when the parallel pairing is
% declared via a `midsegment_parallel` relationship (Mid ∥ Side ⇒ Mid = Side/2).
% The clauses above only match a segment_parallel_to fact or a midsegment_ratio
% relationship, so a relationship-form midsegment target was untraceable.
target_derivable(Mid, length, [midsegment]) :-
    entity(segment, Mid),
    segment_flag(Mid, is_midsegment),
    relationship(_, midsegment_parallel, [Mid, Side]),
    segment_or_side_length(Side, BV), known(BV).

% Triangle proportionality (side-splitter theorem): a segment XY drawn parallel
% to one side (parallel_side) of a triangle cuts the other two sides
% proportionally, so XY / parallel_side = (sub-segment on a cut side) / (the whole
% side that contains it). XY is therefore determined once the parallel side, one
% sub-segment (segment1), and the whole side containing that sub-segment are all
% known. Attribute-driven: reads parallel_side and segment1 from rel_attr.
target_derivable(XY, length, [triangle_proportionality]) :-
    relationship(RIdx, triangle_proportionality, _),
    rel_attr(RIdx, parallel_side, ParSide),
    rel_attr(RIdx, segment1, Seg1),
    entity(segment, XY),
    segment_parallel_to(XY, ParSide),
    segment_or_side_length(ParSide, ParV), known(ParV),
    segment_or_side_length(Seg1, S1V), known(S1V),
    subsegment_apex_code(Seg1, ApexCode),
    proportionality_full_side(ApexCode, ParSide, FullV), known(FullV).

% Apex vertex (as a char code) of a sub-segment like 'PX' -> code of 'P'.
subsegment_apex_code(Seg, ApexCode) :- atom_codes(Seg, [ApexCode | _]).

% The whole triangle side that shares the apex vertex with the sub-segment AND an
% endpoint of the parallel side (e.g. apex P, parallel side QR -> side PQ or PR).
proportionality_full_side(ApexCode, ParSide, FullV) :-
    atom_codes(ParSide, ParChars),
    triangle_side(_, FullKey, FullV), known(FullV),
    atom_codes(FullKey, FullChars),
    member(ApexCode, FullChars),
    member(PC, ParChars), member(PC, FullChars), PC \= ApexCode.

matches_side_id(A, B) :- A == B.
matches_side_id(A, B) :- atom_codes(A, [X, Y]), atom_codes(B, [Y, X]).

target_derivable(C, radius, [scale_factor]) :-
    entity(circle, C),
    relationship(RIdx, Type, _),
    member(Type, [similar_unspecified, scaled_copy, dilation]),
    rel_attr(RIdx, image, C),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    circle_radius(Pre, R), known(R).

% Circle PRE-IMAGE radius via inversion.
target_derivable(C, radius, [scale_factor]) :-
    entity(circle, C),
    relationship(RIdx, Type, _),
    member(Type, [similar_unspecified, scaled_copy, dilation]),
    rel_attr(RIdx, pre_image, C),
    rel_attr(RIdx, image, Img),
    rel_attr(RIdx, scale_factor, K), known(K),
    circle_radius(Img, R), known(R).

target_derivable(T, is_right, [triangle_classification]) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3), known(V1), known(V2), known(V3).
target_derivable(T, is_acute, [triangle_classification]) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3), known(V1), known(V2), known(V3).
target_derivable(T, is_obtuse, [triangle_classification]) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3), known(V1), known(V2), known(V3).
target_derivable(T, is_acute, [triangle_classification]) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList), forall(member(_-V, AngleList), known(V)).
target_derivable(T, is_obtuse, [triangle_classification]) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList), forall(member(_-V, AngleList), known(V)).
target_derivable(T, is_right, [triangle_classification]) :-
    entity(triangle, T),
    triangle_all_angles_resolved(T, AngleList), forall(member(_-V, AngleList), known(V)).

target_derivable(_, scale_factor, [scale_factor_from_pair]) :-
    relationship(_, Type, [E1, E2]),
    member(Type, [dilation, scaled_copy, similar_AA, similar_SAS, similar_SSS]),
    corresponding_side_pair(E1, E2, _, _, V1, V2), known(V1), known(V2).

target_derivable(T, perimeter, [perimeter]) :-
    entity(triangle, T),
    triangle_three_sides(T, _, _, _, V1, V2, V3), known(V1), known(V2), known(V3).
target_derivable(P, perimeter, [perimeter]) :-
    entity(polygon, P),
    polygon_n_sides(P, N),
    findall(V, (polygon_side(P, _, V), known(V)), Vs),
    length(Vs, N).


% --- Discovery similarity solve-paths (establish-then-use) ---
similarity_declared(T1, T2) :-
    relationship(RIdx, Type, _),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified,
                  dilation, scaled_copy, scaled_copy_unspecified]),
    rel_attr(RIdx, pre_image, A), rel_attr(RIdx, image, B),
    ( (A == T1, B == T2) ; (A == T2, B == T1) ), !.
similarity_declared(T1, T2) :-
    relationship(_, Type, Es),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified,
                  dilation, scaled_copy, scaled_copy_unspecified]),
    member(T1, Es), member(T2, Es), !.

matched_angle_count(T1, T2, N) :-
    findall(V1, (triangle_angle(T1, _, V1), known(V1)), A1),
    findall(V2, (triangle_angle(T2, _, V2), known(V2)), A2),
    count_value_matches(A1, A2, N).

count_value_matches([], _, 0).
count_value_matches([V | Rest], Pool, N) :-
    ( select(W, Pool, Pool2), approx_equal(V, W)
    -> count_value_matches(Rest, Pool2, N0), N is N0 + 1
    ;  count_value_matches(Rest, Pool, N) ).

target_derivable(T, AttrSpec, Trace) :-
    parse_attr(AttrSpec, sides, _SideKey),
    entity(triangle, T),
    entity(triangle, Other), T \= Other,
    \+ similarity_declared(T, Other),
    matched_angle_count(T, Other, M), M >= 2,
    Establish = [aa_similarity, aa_similarity],
    ( known_ratio_between(T, Other)
    -> append(Establish, [scale_factor], Trace)
    ;  corresponding_side_pair(Other, T, _, _, PV, IV), known(PV), known(IV),
       append(Establish, [scale_factor_from_pair, scale_factor], Trace)
    ).

target_derivable(T, AttrSpec,
        [sas_similarity, sas_similarity, sas_similarity, scale_factor]) :-
    parse_attr(AttrSpec, sides, TargetSideKey),
    entity(triangle, T),
    entity(triangle, Other), T \= Other,
    \+ similarity_declared(T, Other),
    triangle_angle(T, AngleKey, AV1), known(AV1),
    triangle_angle(Other, _OK, AV2), known(AV2),
    approx_equal(AV1, AV2),
    atom_codes(T, [V1, V2, V3]),
    atom_codes(AngleKey, [VA]), member(VA, [V1, V2, V3]),
    select(VA, [V1, V2, V3], [O1, O2]),
    opposite_side_id(O1, O2, OppId),
    matches_side_id(OppId, TargetSideKey),
    adjacent_side_ids(VA, O1, O2, AdjT1, AdjT2),
    triangle_side(T, AdjT1, TA1), known(TA1),
    triangle_side(T, AdjT2, TA2), known(TA2),
    two_consistent_pairs(T, Other),
    side_position(T, OppId, OppPos),
    side_position(Other, OtherOppKey, OppPos),
    triangle_side(Other, OtherOppKey, OppOtherV), known(OppOtherV).

two_consistent_pairs(T1, T2) :-
    findall(R,
            ( corresponding_side_pair(T1, T2, _, _, V1, V2),
              known(V1), known(V2), V1 > 0, R is V2 / V1 ),
            Ratios),
    length(Ratios, NR), NR >= 2,
    all_close(Ratios).

known_ratio_between(T1, T2) :-
    relationship(RIdx, _, _),
    rel_attr(RIdx, pre_image, A), rel_attr(RIdx, image, B),
    ( (A == T1, B == T2) ; (A == T2, B == T1) ),
    rel_attr(RIdx, scale_factor, K), known(K).

all_close([_]).
all_close([R1, R2 | Rest]) :- approx_equal_scale(R1, R2), all_close([R2 | Rest]).

parse_attr(AttrSpec, Group, Key) :-
    atom_codes(AttrSpec, Codes),
    append(GroupCodes, [0'. | KeyCodes], Codes),
    atom_codes(Group, GroupCodes),
    atom_codes(Key, KeyCodes).
parse_attr(AttrSpec, AttrSpec, '') :-
    atom_codes(AttrSpec, Codes),
    \+ member(0'., Codes).

gate_target_attribute_already_specified :-
    target(Entity, AttrSpec),
    parse_attr(AttrSpec, Group, Key),
    target_value_already_known(Entity, Group, Key, V),
    format(atom(Msg),
           "Target ~w.~w is already declared with value ~w. The problem is vacuous - there is nothing to solve.",
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
% LAYER 5 -- REDUNDANCY
% =====================================================================

gate_no_redundant_relationships :-
    findall(error(redundant_relationship, style, Msg),
            ( relationship(R1, Type1, Es),
              relationship(R2, Type2, Es),
              R1 < R2,
              both_similarity_or_dilation(Type1, Type2),
              format(atom(Msg),
                     "Relationships at indices ~w (~w) and ~w (~w) over the same entities ~w are redundant - similarity and dilation with matching scale factor encode the same information.",
                     [R1, Type1, R2, Type2, Es])
            ),
            Errors),
    assert_errors(Errors).

both_similarity_or_dilation(T1, T2) :-
    similarity_or_dilation(T1), similarity_or_dilation(T2).

similarity_or_dilation(dilation).
similarity_or_dilation(scaled_copy).
similarity_or_dilation(similar_AA).
similarity_or_dilation(similar_SAS).
similarity_or_dilation(similar_SSS).
similarity_or_dilation(similar_unspecified).


strip_primes(In, Out) :-
    atom_codes(In, Cs),
    exclude(==(0'\'), Cs, Cs2),
    atom_codes(Out, Cs2).

image_pre_side(SideKey, Pre, PreV) :-
    strip_primes(SideKey, Bare),
    ( triangle_side(Pre, Bare, PreV) -> true
    ; atom_codes(Bare, [X, Y]), atom_codes(Rev, [Y, X]),
      triangle_side(Pre, Rev, PreV) ).

target_derivable(T, AttrSpec, [scale_factor]) :-
    parse_attr(AttrSpec, sides, SideKey),
    entity(triangle, T),
    relationship(RIdx, Type, _),
    member(Type, [dilation, scaled_copy, scaled_copy_unspecified, similar_unspecified,
                  similar_AA, similar_SAS, similar_SSS]),
    rel_attr(RIdx, image, T),
    rel_attr(RIdx, pre_image, Pre),
    rel_attr(RIdx, scale_factor, K), known(K),
    image_pre_side(SideKey, Pre, PreV), known(PreV).


leg_ids_of_hyp(T, HypId, LegA, LegB) :-
    findall(K, (triangle_side(T, K, _), \+ matches_side_id(K, HypId)), Ks0),
    sort(Ks0, [LegA, LegB]).

target_derivable(AltId, length, [geometric_mean_altitude | Sub]) :-
    relationship(RIdx, altitude_to_hypotenuse, _),
    rel_attr(RIdx, altitude_id, AltId),
    rel_attr(RIdx, hypotenuse, HypId),
    entity(triangle, T),
    triangle_implicit_side(T, HypId),
    triangle_flag(T, is_right),
    leg_ids_of_hyp(T, HypId, LegA, LegB),
    sos_derivable(LegA, SubA),
    sos_derivable(LegB, SubB),
    append(SubA, SubB, Sub).



% =====================================================================
% ERROR COLLECTION AND OUTPUT
% =====================================================================

:- dynamic collected_error/1.

assert_errors([]).
assert_errors([E | Es]) :- assert_error(E), assert_errors(Es).

assert_error(E) :-
    ( collected_error(E) -> true ; assertz(collected_error(E)) ).

clear_errors :- retractall(collected_error(_)).

run_all_gates :-
    clear_errors,
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
    gate_relation_scope,
    gate_shape_relevance,
    gate_attribute_kind_consistency,
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
    gate_similarity_included_angle_vertex,
    gate_invariant_constants,
    gate_polygon_interior_sum,
    gate_right_angle_hypotenuse_consistency,
    gate_vacuous_angle_sum_relationship,
    gate_midsegment_consistency,
    gate_midsegment_parallel_consistency,
    gate_altitude_to_hypotenuse_consistency,
    gate_collinear_dilation_consistency,
    gate_collinear_dilation_center_matches_parent,
    gate_point_position_consistency,
    gate_target_belongs_to_entity,
    gate_target_dilation_pair_underdetermined,
    gate_target_attribute_already_specified,
    gate_target_resolvable,
    gate_no_redundant_relationships.

validate(Result) :-
    run_all_gates,
    findall(E, collected_error(E), Errors),
    classify_result(Errors, Result).

classify_result([], pass).
classify_result(Errors, fail(Errors)) :- Errors \= [].
% =====================================================================
% COMPATIBILITY SHIM — restores bundle_to_json/2 for validate.py
% =====================================================================
% The validator rewrite renamed the JSON emitter to emit_json/0 (which PRINTS),
% but validate.py calls the PURE predicate:
%
%     feedback_bundle(Bundle), bundle_to_json(Bundle, Json)
%
% and expects Json to be BOUND to a JSON string. This block defines that
% predicate against the rewrite's own bundle shape:
%
%     feedback_bundle(bundle(Verdict, Records)),  Records = [rec(GateId,Sev,Msg), ...]
%
% Output shape matches what validate() -> refine_schema consume:
%     {"status":"pass"|"fail","error_count":N,
%      "errors":[{"gate":..,"severity":..,"checks":..,"failed":..}, ...]}
%
% PASTE this anywhere in geometry_validator.pl (e.g. right after emit_json).
% Do NOT re-paste json_escape/2 — it already exists in the validator; this
% block reuses it. Clause order does not matter; SWI resolves at query time.
% =====================================================================

bundle_to_json(bundle(Verdict, Records), Json) :-
    ( Verdict == pass -> Status = pass ; Status = fail ),
    length(Records, N),
    records_to_json(Records, ErrsJson),
    format(atom(Json),
        '{"status":"~w","error_count":~w,"errors":[~w]}',
        [Status, N, ErrsJson]).

records_to_json([], '').
records_to_json([R], J) :- !, record_to_json(R, J).
records_to_json([R | Rs], J) :-
    record_to_json(R, J0),
    records_to_json(Rs, J1),
    atomic_list_concat([J0, ',', J1], J).

record_to_json(rec(GateId, Sev, Msg), J) :-
    json_escape(Msg, EscMsg),
    format(atom(J),
        '{"gate":"~w","severity":"~w","checks":"","failed":"~w"}',
        [GateId, Sev, EscMsg]).

% =====================================================================
% JSON FEEDBACK BUNDLE (consumed by the refine/repair loop)
% =====================================================================
% emit_json/0 prints a machine-readable bundle: an overall verdict plus one
% record per error (gate id, severity, human message). The repair loop reads
% this to decide whether to re-prompt Haiku and what to tell it.

% NOTE: this predicate must RUN the gates, not merely read whatever errors
% happen to be in the database. It is the entry point validate.py calls
% (feedback_bundle/1 + bundle_to_json/2); if it only read collected_error/1,
% it would report `pass` for every schema because the gates had never fired.
% run_all_gates begins with clear_errors, so stale errors from a previous
% schema in the persistent (pyswip) engine are cleared here as well.
feedback_bundle(bundle(Verdict, Records)) :-
    run_all_gates,
    findall(E, collected_error(E), Errors),
    ( Errors == [] -> Verdict = pass ; Verdict = fail ),
    findall(rec(GateId, Sev, Msg),
            member(error(GateId, Sev, Msg), Errors),
            Records).

emit_json :-
    ( \+ collected_error(_) -> run_all_gates ; true ),
    feedback_bundle(bundle(Verdict, Records)),
    write('{"verdict":"'), write(Verdict), write('","errors":['),
    emit_records(Records),
    write(']}'), nl.

emit_records([]).
emit_records([rec(GateId, Sev, Msg)]) :- !,
    emit_record(GateId, Sev, Msg).
emit_records([rec(GateId, Sev, Msg) | Rest]) :-
    emit_record(GateId, Sev, Msg), write(','),
    emit_records(Rest).

emit_record(GateId, Sev, Msg) :-
    json_escape(Msg, Esc),
    write('{"gate":"'), write(GateId),
    write('","severity":"'), write(Sev),
    write('","message":"'), write(Esc), write('"}').

json_escape(Atom, Escaped) :-
    atom_codes(Atom, Codes),
    escape_codes(Codes, EscCodes),
    atom_codes(Escaped, EscCodes).

escape_codes([], []).
escape_codes([0'" | T], [0'\\, 0'" | ET]) :- !, escape_codes(T, ET).
escape_codes([0'\\ | T], [0'\\, 0'\\ | ET]) :- !, escape_codes(T, ET).
escape_codes([0'\n | T], [0'\\, 0'n | ET]) :- !, escape_codes(T, ET).
escape_codes([0'\t | T], [0'\\, 0't | ET]) :- !, escape_codes(T, ET).
escape_codes([C | T], [C | ET]) :- escape_codes(T, ET).

% theorem_trace(+Entity, +Attr, -Trace, -StepCount)
% Public accessor for the calibration layer: shortest derivation trace.
theorem_trace(Entity, Attr, Trace, StepCount) :-
    findall(Len-T,
            ( target_derivable(Entity, Attr, T), length(T, Len) ),
            Pairs),
    Pairs \= [],
    keysort(Pairs, [StepCount-Trace | _]).
% =====================================================================
% LESSON SCOPE & DIFFICULTY DATA: IM Geometry Unit 3
%
% Three predicate families:
%   lesson_allows/2   — theorems usable to solve (cumulative; prior-lesson
%                       skills remain legal as scaffolding).
%   lesson_requires/2 — the lesson's OWN skill atoms. A solve trace must
%                       contain at least one of these to count as exercising
%                       the lesson. This closes the alignment leak that the
%                       band floor alone cannot: a problem solved entirely by
%                       a prior-lesson shortcut (e.g. an L05 "midsegment"
%                       problem solved by a plain dilation scale factor)
%                       satisfies the allow-list and the band but NOT the
%                       requirement, and is flagged alignment_fail.
%   lesson_min_steps/2, lesson_max_steps/2 — difficulty band from each
%                       lesson's own textbook anchors.
%
% The band floor is retained (belt-and-suspenders): L14/L16 keep floor=2 so a
% 1-step shortcut is caught as too_easy even where a requirement atom sneaks in.
% =====================================================================
:- discontiguous lesson_allows/2.
:- discontiguous lesson_requires/2.
:- discontiguous lesson_min_steps/2.
:- discontiguous lesson_max_steps/2.

% L01 — scale factor & dilation
lesson_allows(lesson_01, [scale_factor, scale_factor_from_pair]).
lesson_requires(lesson_01, [scale_factor, scale_factor_from_pair]).
lesson_min_steps(lesson_01, 1).  lesson_max_steps(lesson_01, 2).

% L03 — dilate polygons, all lengths * k
lesson_allows(lesson_03, [scale_factor, scale_factor_from_pair]).
lesson_requires(lesson_03, [scale_factor, scale_factor_from_pair]).
lesson_min_steps(lesson_03, 1).  lesson_max_steps(lesson_03, 1).

% L05 — midsegment / proportional division.
% REQUIRES the midsegment/proportionality skill specifically: a dilation
% scale_factor shortcut does NOT count (this is the L05 leak we caught).
lesson_allows(lesson_05, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle]).
lesson_requires(lesson_05, [midsegment, triangle_proportionality]).
lesson_min_steps(lesson_05, 1).  lesson_max_steps(lesson_05, 2).

% L06 — definition of similarity (numerically ratio arithmetic)
lesson_allows(lesson_06, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle]).
lesson_requires(lesson_06, [scale_factor, scale_factor_from_pair]).
lesson_min_steps(lesson_06, 1).  lesson_max_steps(lesson_06, 2).

% L08 — proving figures similar (class scale factor R/r)
lesson_allows(lesson_08, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle]).
lesson_requires(lesson_08, [scale_factor, scale_factor_from_pair]).
lesson_min_steps(lesson_08, 1).  lesson_max_steps(lesson_08, 1).

% L09 — Angle-Angle similarity.
% REQUIRES the similarity to be used (angle transfer or ratio) — a bare
% triangle_angle_sum within one triangle does NOT count (the L09 leak).
lesson_allows(lesson_09, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle,
                          aa_similarity, triangle_angle_sum]).
lesson_requires(lesson_09, [aa_similarity, corresponding_angle,
                            scale_factor, scale_factor_from_pair]).
lesson_min_steps(lesson_09, 1).  lesson_max_steps(lesson_09, 3).

% L10 — SSS / SAS similarity
lesson_allows(lesson_10, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle,
                          aa_similarity, triangle_angle_sum,
                          sss_similarity, sas_similarity]).
lesson_requires(lesson_10, [sss_similarity, sas_similarity,
                            scale_factor_from_pair, scale_factor]).
lesson_min_steps(lesson_10, 1).  lesson_max_steps(lesson_10, 2).

% L14 — Pythagorean via altitude-to-hypotenuse similarity.
% REQUIRES a geometric-mean atom: a raw pythagorean path does NOT count.
% Floor also =2 as a second guard.
lesson_allows(lesson_14, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle,
                          aa_similarity, triangle_angle_sum,
                          sss_similarity, sas_similarity,
                          pythagorean,
                          geometric_mean_leg, geometric_mean_altitude,
                          altitude_to_hypotenuse_split]).
lesson_requires(lesson_14, [geometric_mean_leg, geometric_mean_altitude,
                            altitude_to_hypotenuse_split]).
lesson_min_steps(lesson_14, 2).  lesson_max_steps(lesson_14, 3).

% L15 — converse of Pythagorean: classification + triangle inequality.
% REQUIRES a classification/inequality atom: a similarity-ratio solution does
% NOT count (the L15 leak — an SSS-similarity problem mislabeled L15).
lesson_allows(lesson_15, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle,
                          aa_similarity, triangle_angle_sum,
                          sss_similarity, sas_similarity,
                          pythagorean,
                          geometric_mean_leg, geometric_mean_altitude,
                          altitude_to_hypotenuse_split,
                          triangle_classification, triangle_inequality]).
lesson_requires(lesson_15, [triangle_classification, triangle_inequality]).
lesson_min_steps(lesson_15, 1).  lesson_max_steps(lesson_15, 2).

% L16 — synthesis: unknown lengths in similar right triangles.
% Lenient requirement: any right-triangle-similarity atom (the synthesis is
% judged acceptable when either method carries the problem); floor=2 guards
% against a trivial 1-step problem.
lesson_allows(lesson_16, [scale_factor, scale_factor_from_pair,
                          triangle_proportionality, midsegment, corresponding_angle,
                          aa_similarity, triangle_angle_sum,
                          sss_similarity, sas_similarity,
                          pythagorean,
                          geometric_mean_leg, geometric_mean_altitude,
                          altitude_to_hypotenuse_split,
                          triangle_classification, triangle_inequality]).
lesson_requires(lesson_16, [geometric_mean_leg, geometric_mean_altitude,
                            altitude_to_hypotenuse_split, pythagorean,
                            scale_factor_from_pair, scale_factor,
                            aa_similarity, sss_similarity, sas_similarity]).
lesson_min_steps(lesson_16, 2).  lesson_max_steps(lesson_16, 3).
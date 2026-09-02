% =====================================================================
% CALIBRATION HARNESS  (consults the traced validator; does not modify it)
%
% Scope check   : every theorem in the derivation is in lesson_allows.
% Alignment     : the derivation contains at least one lesson_requires atom.
% Difficulty    : the shortest requirement-satisfying derivation is in band.
%
% shortest_in_scope/4     — shortest ALLOWED and REQUIREMENT-SATISFYING path.
% shortest_allowed_any/3  — shortest ALLOWED path ignoring the requirement,
%                           used to distinguish out_of_scope (no allowed path)
%                           from alignment_fail (allowed path exists but skips
%                           the lesson skill / a cheaper allowed path skips it).
% =====================================================================

% Requirement satisfied iff the trace shares >=1 atom with lesson_requires.
satisfies_requirement(Lesson, Trace) :-
    lesson_requires(Lesson, Req),
    member(Atom, Trace),
    member(Atom, Req), !.
% If a lesson declares no requirement, everything satisfies (defensive).
satisfies_requirement(Lesson, _) :-
    \+ lesson_requires(Lesson, _).

% shortest_in_scope(+Lesson, -MinSteps, -BestTrace, -OutOfScopeTraces)
% Cheapest derivation that is BOTH in-scope AND requirement-satisfying.
shortest_in_scope(Lesson, MinSteps, BestTrace, OutOfScope) :-
    target(Entity, Attr),
    lesson_allows(Lesson, Allowed),
    findall(Len-Trace,
            ( target_derivable(Entity, Attr, Trace),
              forall(member(Th, Trace), member(Th, Allowed)),
              satisfies_requirement(Lesson, Trace),
              length(Trace, Len) ),
            InScopePairs),
    findall(Trace,
            ( target_derivable(Entity, Attr, Trace),
              \+ forall(member(Th, Trace), member(Th, Allowed)) ),
            OutOfScope),
    ( InScopePairs == []
    -> MinSteps = none, BestTrace = []
    ;  sort(InScopePairs, [MinSteps-BestTrace | _]) ).

% shortest_allowed_any(+Lesson, -MinSteps, -BestTrace)
% Cheapest in-scope derivation, requirement IGNORED.
shortest_allowed_any(Lesson, MinSteps, BestTrace) :-
    target(Entity, Attr),
    lesson_allows(Lesson, Allowed),
    findall(Len-Trace,
            ( target_derivable(Entity, Attr, Trace),
              forall(member(Th, Trace), member(Th, Allowed)),
              length(Trace, Len) ),
            Pairs),
    ( Pairs == []
    -> MinSteps = none, BestTrace = []
    ;  sort(Pairs, [MinSteps-BestTrace | _]) ).

% emit_calibration(+Lesson): CSV-ish line for host capture.
% Columns: lesson, req_min_steps, best_trace, any_min_steps, n_out_of_scope
emit_calibration(Lesson) :-
    ( shortest_in_scope(Lesson, ReqMin, Trace, OOS),
      shortest_allowed_any(Lesson, AnyMin, _)
    -> length(OOS, NOos),
       format("~w,~w,~w,~w,~w~n", [Lesson, ReqMin, Trace, AnyMin, NOos])
    ;  format("~w,ERROR,[],ERROR,-1~n", [Lesson]) ).

% verdict(+Lesson): human-readable out_of_scope / alignment_fail /
% too_easy / too_hard / in_band. (Standalone debug; the pipeline verdict
% lives in calibrate.py.)
verdict(Lesson) :-
    shortest_allowed_any(Lesson, AnyMin, _),
    ( AnyMin == none
    -> format("~w: OUT_OF_SCOPE (no allowed-theorem derivation)~n", [Lesson])
    ;  shortest_in_scope(Lesson, ReqMin, ReqTrace, _),
       ( ReqMin == none
       -> format("~w: ALIGNMENT_FAIL (solvable in ~w in-scope step(s) but none use the lesson skill)~n",
                 [Lesson, AnyMin])
       ;  AnyMin < ReqMin
       -> format("~w: ALIGNMENT_FAIL (skill path is ~w steps but a ~w-step in-scope shortcut skips it)~n",
                 [Lesson, ReqMin, AnyMin])
       ;  lesson_min_steps(Lesson, Floor), lesson_max_steps(Lesson, Ceil),
          ( ReqMin < Floor -> Tag = too_easy
          ; ReqMin > Ceil  -> Tag = too_hard
          ;                   Tag = in_band ),
          format("~w: ~w steps ~w (band ~w..~w) trace=~w~n",
                 [Lesson, ReqMin, Tag, Floor, Ceil, ReqTrace])
       )
    ).


% =====================================================================
% DIFFICULTY LEVER + REDUNDANCY  (hold-one-out over declared facts)
%
% Tentatively remove a declared fact, re-run shortest_in_scope, classify by the
% change in step count:
%   removal makes target underivable  -> LOAD-BEARING  (never suggest)
%   removal raises steps into the band -> UN-DECLARE    (difficulty lever)
%   removal leaves steps unchanged     -> REDUNDANT     (clarity clutter)
% Every suggestion is checked to keep the target derivable BEFORE it is emitted.
%
% NOTE: these use the (now requirement-filtered) shortest_in_scope/4, so "into
% the band" means into the requirement-satisfying band. Not wired into the
% pipeline (calibrate.py does not call these) — retained for standalone use.
% =====================================================================

removable_conclusion(RIdx, Type, Es) :-
    relationship(RIdx, Type, Es),
    member(Type, [similar_AA, similar_SAS, similar_SSS, similar_unspecified,
                  dilation, scaled_copy, scaled_copy_unspecified]).

hold_out_relationship(RIdx, Goal) :-
    relationship(RIdx, Type, Es),
    findall(K-V, rel_attr(RIdx, K, V), Attrs),
    setup_call_cleanup(
        ( retract(relationship(RIdx, Type, Es)),
          forall(member(K-V, Attrs), retract(rel_attr(RIdx, K, V))) ),
        once(Goal),
        ( assertz(relationship(RIdx, Type, Es)),
          forall(member(K-V, Attrs), assertz(rel_attr(RIdx, K, V))) )
    ).

hold_out_fact(Fact, Goal) :-
    setup_call_cleanup(retract(Fact), once(Goal), assertz(Fact)).

% --- THE UN-DECLARE LEVER --------------------------------------------
undeclare_suggestion(Lesson, RIdx, Type, Es, OldMin, NewMin, NewTrace) :-
    shortest_in_scope(Lesson, OldMin, _, _),
    integer(OldMin),
    lesson_min_steps(Lesson, Floor),
    lesson_max_steps(Lesson, Ceil),
    OldMin < Floor,
    findall(R-T-E, removable_conclusion(R, T, E), Removables),
    member(RIdx-Type-Es, Removables),
    hold_out_relationship(RIdx, shortest_in_scope(Lesson, NewMin, NewTrace, _)),
    integer(NewMin),
    NewMin > OldMin,
    NewMin >= Floor, NewMin =< Ceil.

trace_criterion(Trace, aa)  :- memberchk(aa_similarity, Trace), !.
trace_criterion(Trace, sas) :- memberchk(sas_similarity, Trace), !.
trace_criterion(Trace, sss) :- memberchk(sss_similarity, Trace), !.
trace_criterion(_, unspecified).

emit_undeclare_suggestions(Lesson) :-
    ( undeclare_suggestion(Lesson, RIdx, Type, Es, OldMin, NewMin, NewTrace),
      trace_criterion(NewTrace, Crit),
      format("UNDECLARE rel ~w (~w on ~w): ~w -> ~w steps, into band; keep ~w-discovery evidence~n",
             [RIdx, Type, Es, OldMin, NewMin, Crit]),
      fail
    ; true ).

% --- REDUNDANCY (the delta == 0 branch) ------------------------------
in_band(Lesson, Min) :-
    shortest_in_scope(Lesson, Min, _, _),
    integer(Min),
    lesson_min_steps(Lesson, Floor),
    lesson_max_steps(Lesson, Ceil),
    Min >= Floor, Min =< Ceil.

redundant_conclusion(Lesson, RIdx, Type, Es) :-
    in_band(Lesson, OldMin),
    findall(R-T-E, removable_conclusion(R, T, E), Removables),
    member(RIdx-Type-Es, Removables),
    hold_out_relationship(RIdx, shortest_in_scope(Lesson, NewMin, _, _)),
    NewMin == OldMin.

redundant_measurement(Lesson, angle, T, K, V) :-
    in_band(Lesson, OldMin),
    triangle_angle(T, K, V), known(V),
    hold_out_fact(triangle_angle(T, K, V), shortest_in_scope(Lesson, NewMin, _, _)),
    NewMin == OldMin.
redundant_measurement(Lesson, side, T, K, V) :-
    in_band(Lesson, OldMin),
    triangle_side(T, K, V), known(V),
    hold_out_fact(triangle_side(T, K, V), shortest_in_scope(Lesson, NewMin, _, _)),
    NewMin == OldMin.

emit_redundancies(Lesson) :-
    ( redundant_conclusion(Lesson, RIdx, Type, Es),
      format("REDUNDANT rel ~w (~w on ~w): removable, step count unchanged~n",
             [RIdx, Type, Es]),
      fail ; true ),
    ( redundant_measurement(Lesson, Kind, T, K, V),
      format("REDUNDANT ~w ~w.~w=~w: removable, step count unchanged~n",
             [Kind, T, K, V]),
      fail ; true ).


% =====================================================================
% STRIP REDUNDANT FACTS  (iterative, interaction-safe)
% Only MEASUREMENTS are stripped here; declared conclusions are left to the
% un-declare lever. MUTATES the asserted DB (commits removals).
% =====================================================================
strip_redundant(Lesson, Removed) :-
    strip_loop(Lesson, [], RevRemoved),
    reverse(RevRemoved, Removed).

strip_loop(Lesson, Acc, Removed) :-
    ( find_safe_removal(Lesson, Fact)
    -> retract(Fact),
       strip_loop(Lesson, [Fact | Acc], Removed)
    ;  Removed = Acc ).

find_safe_removal(Lesson, Fact) :-
    in_band(Lesson, OldMin),
    candidate_measurement(Fact),
    hold_out_fact(Fact, shortest_in_scope(Lesson, NewMin, _, _)),
    NewMin == OldMin,
    !.

candidate_measurement(triangle_angle(T, K, V)) :- triangle_angle(T, K, V), known(V).
candidate_measurement(triangle_side(T, K, V))  :- triangle_side(T, K, V),  known(V).

emit_strip(Lesson) :-
    strip_redundant(Lesson, Removed),
    ( Removed == []
    -> writeln("STRIP: nothing redundant (problem is already minimal).")
    ;  forall(member(F, Removed),
              format("STRIP removed: ~q~n", [F])) ).
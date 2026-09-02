% GENERATED FROM schema.py:RELATION_ATTRS — DO NOT EDIT BY HAND.
% Regenerate with: python -c 'import schema; schema.write_prolog_contract()'

allowed_attrs(similar_AA, [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_SAS, [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_SSS, [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(similar_unspecified, [scale_factor, pre_image, image, congruent_angle_pairs]).
allowed_attrs(dilation, [scale_factor, center, pre_image, image]).
allowed_attrs(scaled_copy, [scale_factor, pre_image, image]).
allowed_attrs(scaled_copy_unspecified, [scale_factor, pre_image, image]).
allowed_attrs(proportional_segments, [ratio]).
allowed_attrs(midsegment_ratio, [ratio]).
allowed_attrs(medial_triangle, []).
allowed_attrs(triangle_proportionality, [parallel_side, segment1, segment2]).
allowed_attrs(altitude_to_hypotenuse, [altitude_id, hypotenuse, segment1, segment2]).
allowed_attrs(geometric_mean_altitude, [altitude_id, segment1, segment2]).
allowed_attrs(geometric_mean_leg, [leg_id, hypotenuse, adjacent_segment]).
allowed_attrs(transversal_cut, [transversal, line1, line2]).
allowed_attrs(congruent_angles, [ids]).
allowed_attrs(congruent_segments, [ids]).
allowed_attrs(congruent_triangles, [pre_image, image, criterion]).
allowed_attrs(collinear_dilation, [center, pre_image_point, image_point]).
allowed_attrs(supplementary_angles, [angle1, angle2, sum]).
allowed_attrs(complementary_angles, [angle1, angle2, sum]).
allowed_attrs(vertical_angles, [angle1, angle2]).
allowed_attrs(linear_pair, [angle1, angle2, sum]).
allowed_attrs(adjacent_angles, [shared_vertex, shared_ray, angle1, angle2]).
allowed_attrs(angle_bisector, [bisected_angle, ray, angle1, angle2]).
allowed_attrs(exterior_angle, [exterior_angle, remote_interior_angle1, remote_interior_angle2]).
allowed_attrs(parallel_lines_transversal, [transversal, line1, line2, alternate_interior_pairs, alternate_exterior_pairs, corresponding_pairs, co_interior_pairs]).
allowed_attrs(angle_sum_triangle, [triangle_id, angles, sum]).
allowed_attrs(angle_sum_polygon, [polygon_id, num_sides, interior_sum, exterior_sum]).
allowed_attrs(parallel_lines, []).
allowed_attrs(parallel_segments, []).
allowed_attrs(midsegment_parallel, []).
allowed_attrs(perpendicular_lines, []).
allowed_attrs(perpendicular_segments, []).
allowed_attrs(altitude_perpendicular, []).
allowed_attrs(center_on_figure, []).
allowed_attrs(center_off_figure, []).
allowed_attrs(lines_intersect, []).
allowed_attrs(segments_intersect, []).
allowed_attrs(point_on_line, []).
allowed_attrs(point_interior, []).

required_attrs(similar_AA, [pre_image, image]).
required_attrs(similar_SAS, [pre_image, image]).
required_attrs(similar_SSS, [pre_image, image]).
required_attrs(similar_unspecified, [pre_image, image]).
required_attrs(dilation, [scale_factor, pre_image, image]).
required_attrs(scaled_copy, [scale_factor, pre_image, image]).
required_attrs(scaled_copy_unspecified, [pre_image, image]).
required_attrs(triangle_proportionality, [parallel_side, segment1, segment2]).
required_attrs(altitude_to_hypotenuse, [altitude_id, hypotenuse, segment1, segment2]).
required_attrs(geometric_mean_altitude, [altitude_id, segment1, segment2]).
required_attrs(geometric_mean_leg, [leg_id, hypotenuse, adjacent_segment]).
required_attrs(transversal_cut, [transversal, line1, line2]).
required_attrs(congruent_triangles, [pre_image, image]).
required_attrs(collinear_dilation, [center, pre_image_point, image_point]).
required_attrs(angle_bisector, [bisected_angle]).
required_attrs(exterior_angle, [exterior_angle, remote_interior_angle1, remote_interior_angle2]).
required_attrs(parallel_lines_transversal, [transversal, line1, line2]).
required_attrs(angle_sum_triangle, [triangle_id]).
required_attrs(angle_sum_polygon, [polygon_id, num_sides]).

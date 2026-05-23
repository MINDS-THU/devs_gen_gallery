shader_type canvas_item;

uniform vec4 key_color : source_color = vec4(0.0, 1.0, 0.0, 1.0);
uniform float similarity : hint_range(0.0, 1.0) = 0.20;
uniform float smoothness : hint_range(0.001, 0.5) = 0.05;
uniform float spill_strength : hint_range(0.0, 3.0) = 1.2;
uniform float alpha_cutoff : hint_range(0.0, 1.0) = 0.04;

void fragment() {
	vec4 tex = texture(TEXTURE, UV);
	float distance_to_key = distance(tex.rgb, key_color.rgb);
	float alpha_mask = smoothstep(similarity - smoothness, similarity + smoothness, distance_to_key);

	// Despill: suppress green fringe from anti-aliased edges.
	float green_dominance = max(0.0, tex.g - max(tex.r, tex.b));
	float spill = clamp(green_dominance * spill_strength, 0.0, 1.0);
	float neutral = (tex.r + tex.b) * 0.5;
	vec3 despilled = vec3(tex.r, mix(tex.g, neutral, spill), tex.b);

	float out_alpha = tex.a * alpha_mask;
	if (out_alpha < alpha_cutoff) {
		out_alpha = 0.0;
	}
	COLOR = vec4(despilled, out_alpha);
}

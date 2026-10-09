shader_type spatial;
// Ölçek için 1 m ızgaralı zemin; her 5 m'de bir koyu çizgi. Dünya koordinatına göre çizilir,
// yani zemin nerede ve ne boyutta olursa olsun çizgiler metre sınırlarına oturur.

uniform vec4 base_color : source_color = vec4(0.56, 0.57, 0.59, 1.0);
uniform vec4 line_color : source_color = vec4(0.47, 0.48, 0.51, 1.0);
uniform vec4 major_color : source_color = vec4(0.36, 0.38, 0.42, 1.0);
uniform float line_width = 0.015; // metre

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

// En yakın ızgara çizgisine (metre) göre 0..1 kapsama; fwidth ile kenar yumuşatma.
float grid(vec2 p, float cell, float width) {
	vec2 dist = abs(fract(p / cell - 0.5) - 0.5) * cell;
	vec2 aa = fwidth(p) * 1.5;
	vec2 cover = 1.0 - smoothstep(vec2(width * 0.5), vec2(width * 0.5) + aa, dist);
	return max(cover.x, cover.y);
}

void fragment() {
	vec3 c = base_color.rgb;
	c = mix(c, line_color.rgb, grid(world_pos.xz, 1.0, line_width));
	c = mix(c, major_color.rgb, grid(world_pos.xz, 5.0, line_width * 2.0));
	ALBEDO = c;
	ROUGHNESS = 0.95;
	SPECULAR = 0.1;
}

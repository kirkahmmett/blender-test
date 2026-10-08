shader_type spatial;
// Pastel, yumuşak yüzey shader'ı (PS1 dışı stil deneyleri için).
//  - renk köşe renginden (vertex color) gelir, albedo_tint ile çarpılır
//  - yumuşak "wrap" ışığı: gölge tarafı tamamen kararmaz, pastel kalır
//  - porselen için parlama (specular), yapraklar için hafif kenar ışığı (rim)
render_mode cull_back, diffuse_lambert_wrap, specular_schlick_ggx;

uniform vec4 albedo_tint : source_color = vec4(1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.8;
uniform float specular : hint_range(0.0, 1.0) = 0.3;
uniform float rim : hint_range(0.0, 1.0) = 0.0;
uniform float rim_tint : hint_range(0.0, 1.0) = 0.6;

vec3 linear_to_srgb(vec3 c) {
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}

void fragment() {
	// glTF köşe renkleri lineer gelir. Compatibility renderer sRGB uzayında hesap yaptığı
	// için burada çevrilmeli; Forward+/Mobile lineer çalışır, orada olduğu gibi kullanılır.
	vec3 col = COLOR.rgb;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	col = linear_to_srgb(col);
#endif
	ALBEDO = col * albedo_tint.rgb;
	ROUGHNESS = roughness;
	SPECULAR = specular;
	RIM = rim;
	RIM_TINT = rim_tint;
}

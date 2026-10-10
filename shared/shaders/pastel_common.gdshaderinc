// Pastel stilin ortak gövdesi: pastel_spatial (kapalı gövdeler) ve pastel_leaf (çift taraflı
// ince yüzeyler) bunu #include eder; yalnızca render_mode'ları farklıdır.
//  - renk köşe renginden (vertex color) gelir, albedo_tint ile çarpılır
//  - yumuşak "wrap" ışığı: gölge tarafı tamamen kararmaz, pastel kalır
//  - parlama (specular) ve kenar ışığı (rim) malzemeye göre ayarlanır

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
	// çift taraflı yüzeylerde arka yüz, ışığı kendi tarafından alsın
	if (!FRONT_FACING) {
		NORMAL = -NORMAL;
	}
	ALBEDO = col * albedo_tint.rgb;
	ROUGHNESS = roughness;
	SPECULAR = specular;
	RIM = rim;
	RIM_TINT = rim_tint;
}

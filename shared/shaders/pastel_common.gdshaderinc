// Pastel stilin ortak gövdesi: pastel_spatial (kapalı gövdeler) ve pastel_leaf (çift taraflı
// ince yüzeyler) bunu #include eder; yalnızca render_mode'ları farklıdır.
//  - renk köşe renginden (vertex color) gelir, albedo_tint ile çarpılır
//  - yumuşak "wrap" ışığı: gölge tarafı tamamen kararmaz, pastel kalır
//  - parlama (specular) ve kenar ışığı (rim) malzemeye göre ayarlanır
//
// Birleştirilmiş malzemeler (use_lut): prop'un tüm parçaları tek malzemede (tek çizim çağrısı);
// her köşenin asıl malzeme kimliği COLOR.a'da (id / 255). Parça ayarları lut_* dizilerinden
// okunur; diziler PropStyle tarafından PASTEL_PRESETS'ten doldurulur.

uniform vec4 albedo_tint : source_color = vec4(1.0);
uniform float roughness : hint_range(0.0, 1.0) = 0.8;
uniform float specular : hint_range(0.0, 1.0) = 0.3;
uniform float rim : hint_range(0.0, 1.0) = 0.0;
uniform float rim_tint : hint_range(0.0, 1.0) = 0.6;

uniform bool use_lut = false;
uniform float lut_roughness[16];
uniform float lut_specular[16];
uniform float lut_rim[16];
uniform float lut_tint[16];

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
	float r = roughness;
	float s = specular;
	float rm = rim;
	vec3 tint = albedo_tint.rgb;
	if (use_lut) {
		int id = clamp(int(COLOR.a * 255.0 + 0.5), 0, 15);
		r = lut_roughness[id];
		s = lut_specular[id];
		rm = lut_rim[id];
		tint = vec3(lut_tint[id]);
	}
	ALBEDO = col * tint;
	ROUGHNESS = r;
	SPECULAR = s;
	RIM = rm;
	RIM_TINT = rim_tint;
}

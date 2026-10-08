shader_type spatial;
// PS1 tarzı yüzey shader'ı:
//  - köşe (vertex) pozisyonlarını ekranda ızgaraya oturtur (titreme / "wobble")
//  - affine doku eşleme (perspektif düzeltmesiz, PS1 dokuları "kayar")
//  - köşe bazlı aydınlatma (Gouraud)
//  - nearest filtering ve renk kuantizasyonu
// Köşe rengi (vertex color) doku ve albedo_color ile çarpılır.
render_mode vertex_lighting, specular_disabled, cull_back;

uniform vec4 albedo_color : source_color = vec4(1.0);
uniform sampler2D albedo_texture : source_color, filter_nearest, repeat_enable;
uniform bool use_texture = false;

// Köşe oturtma ızgarası. NDC [-1, 1] aralığı iki birim olduğundan
// ızgara (160, 120) ise 320x240'lık bir konum çözünürlüğü demektir.
uniform bool snap_enabled = true;
uniform vec2 snap_grid = vec2(160.0, 120.0);

// 0 = normal (perspektif düzeltmeli) UV, 1 = tam affine UV.
uniform float affine_amount : hint_range(0.0, 1.0) = 1.0;

// Kanal başına renk seviyesi. PS1'in 15 bitlik rengi için 32.
uniform float color_levels : hint_range(2.0, 256.0) = 32.0;

vec3 linear_to_srgb(vec3 c) {
	return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055, step(vec3(0.0031308), c));
}

varying vec2 uv_persp;
varying vec3 uv_affine; // (uv * w, w)

void vertex() {
	vec4 view_pos = MODELVIEW_MATRIX * vec4(VERTEX, 1.0);
	vec4 clip = PROJECTION_MATRIX * view_pos;

	if (snap_enabled) {
		vec2 ndc = clip.xy / clip.w;
		ndc = floor(ndc * snap_grid + 0.5) / snap_grid;
		clip.xy = ndc * clip.w;
		POSITION = clip;
	}

	uv_persp = UV;
	uv_affine = vec3(UV * clip.w, clip.w);
}

void fragment() {
	vec2 uv = mix(uv_persp, uv_affine.xy / uv_affine.z, affine_amount);

	vec4 tex = vec4(1.0);
	if (use_texture) {
		tex = texture(albedo_texture, uv);
	}

	// glTF köşe renkleri lineer gelir; Compatibility renderer sRGB uzayında hesap yapar.
	vec4 vcol = COLOR;
#if CURRENT_RENDERER == RENDERER_COMPATIBILITY
	vcol.rgb = linear_to_srgb(vcol.rgb);
#endif
	vec4 c = tex * albedo_color * vcol;
	vec3 q = floor(c.rgb * color_levels + 0.5) / color_levels;

	ALBEDO = q;
	ALPHA = c.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ROUGHNESS = 1.0;
}

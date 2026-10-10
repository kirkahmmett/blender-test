shader_type spatial;
// Pastel, yumuşak yüzey shader'ı (PS1 dışı stil deneyleri için): kapalı gövdeler, arka yüz çizilmez.
// Ortak gövde pastel_common.gdshaderinc'te; ince yüzeyler (yaprak) için pastel_leaf.
render_mode cull_back, diffuse_lambert_wrap, specular_schlick_ggx;

#include "res://shared/shaders/pastel_common.gdshaderinc"

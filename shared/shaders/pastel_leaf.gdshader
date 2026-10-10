shader_type spatial;
// Pastel stil, çift taraflı: yaprak ve taç yaprağı gibi ince yüzeyler alttan da görünür.
render_mode cull_disabled, diffuse_lambert_wrap, specular_schlick_ggx;

#include "res://shared/shaders/pastel_common.gdshaderinc"

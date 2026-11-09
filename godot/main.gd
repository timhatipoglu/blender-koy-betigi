extends Node3D
## Köyün üstünden/içinden 6 sn'lik kamera uçuşu. Tamamen belirlenimci: zaman = kare sayısı / 30,
## yol Blender'ın yazdığı village_seed1.json'dan (Godot ekseninde) okunur.

const DURATION := 6.0
const META := "res://assets/village_seed1.json"

@onready var cam: Camera3D = $Camera3D
@onready var info: Label = $HUD/Info
var curve := Curve3D.new()
var length := 0.0
var frame := 0
var t_start_us := 0
var last_log := -1


func _ready() -> void:
	var meta: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(META))
	for p in meta["path"]:
		curve.add_point(Vector3(p[0], p[1], p[2]))
	length = curve.get_baked_length()
	info.text = "seed %d  ·  %d ev  ·  %d üçgen" % [meta["seed"], meta["houses"], meta["triangles"]]
	_report_scene(meta)
	_place_camera(0.0)
	t_start_us = Time.get_ticks_usec()


func _report_scene(meta: Dictionary) -> void:
	var mis := find_children("*", "MeshInstance3D", true, false)
	var tris := 0
	var meshes := {}
	for mi in mis:
		if mi.name == "FarGround":
			continue
		var m: Mesh = mi.mesh
		meshes[m.get_rid()] = true
		for s in m.get_surface_count():
			var arr := m.surface_get_arrays(s)
			var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX]
			tris += (idx.size() if idx.size() > 0 else (arr[Mesh.ARRAY_VERTEX] as PackedVector3Array).size()) / 3
	print("[godot] köy sahnesi: MeshInstance3D=%d  benzersiz Mesh kaynağı=%d  üçgen=%d  (Blender: nesne=%d, üçgen=%d)"
		% [mis.size() - 1, meshes.size(), tris, meta["mesh_objects"], meta["triangles"]])
	print("[godot] yol uzunluğu %.1f m" % length)


func _ease(a: float, b: float, u: float) -> float:
	return clampf((u - a) / (b - a), 0.0, 1.0) * clampf((u - a) / (b - a), 0.0, 1.0) * (3.0 - 2.0 * clampf((u - a) / (b - a), 0.0, 1.0))


func _place_camera(t: float) -> void:
	var u := clampf(t / DURATION, 0.0, 1.0)
	var d := lerpf(0.06, 0.62, _ease(0.0, 1.0, u)) * length          # yol üzerindeki mesafe
	var p := curve.sample_baked(d, true)
	var tan := (curve.sample_baked(minf(d + 1.0, length), true) - curve.sample_baked(maxf(d - 1.0, 0.0), true)).normalized()
	var side := tan.cross(Vector3.UP).normalized()
	var k := _ease(0.0, 0.8, u)                                        # 0: yüksekte/yanda → 1: yolun üstünde, alçakta
	var pos := p + Vector3.UP * lerpf(26.0, 4.5, k) + side * lerpf(-16.0, 0.0, k) - tan * lerpf(10.0, 0.0, k)
	var ahead := curve.sample_baked(minf(d + lerpf(18.0, 14.0, k), length), true)
	var target := ahead + Vector3.UP * lerpf(-2.0, 1.6, k)
	cam.position = pos
	cam.look_at(target, Vector3.UP)


func _process(delta: float) -> void:
	frame += 1
	var t := frame / 30.0
	_place_camera(t)
	var sec := int(t)
	if sec != last_log:
		last_log = sec
		var real := (Time.get_ticks_usec() - t_start_us) / 1e6
		print("[flight] t=%.2f sn  kamera=(%.1f, %.1f, %.1f)  gerçek süre %.2f sn  ortalama %.1f kare/sn (gerçek)  Engine fps=%d"
			% [t, cam.position.x, cam.position.y, cam.position.z, real, frame / maxf(real, 0.001), Engine.get_frames_per_second()])

# Blender'da tek Python betiğiyle köy, Godot 4'te üstünden uçuş

`make_village.py` bir tohumdan (seed) low-poly köy kuruyor: arazi, evler, ağaçlar, kayalar, kıvrılan yol. Aynı tohum aynı köyü, başka tohum başka köyü verir. Aynı tür evler tek bir mesh'i paylaşır (ortak mesh / instancing), dosya küçük kalır. Çıktı GLB; Godot doğrudan açar ve kamera Blender'ın yazdığı yol JSON'unu izleyerek köyün üstünden uçar.

`demo.mp4`: Godot Movie Maker kaydı (6 sn uçuş, tohum 1). `seed1_seed2.png`: iki tohumun Blender önizlemesi.

## Çalıştır

```bash
# 1) Köyü üret (Blender 4.x/5.x, arka planda)
cd blender
blender -b --factory-startup --python make_village.py -- --seed 1 --out village_seed1.glb
blender -b --factory-startup --python make_village.py -- --seed 2 --out village_seed2.glb
cp village_seed1.glb village_seed1.json ../godot/assets/

# 2) Godot'da aç: godot/project.godot → Çalıştır
```

## Ölçtüklerimiz (Blender 5.2.2 + Godot 4.7.2, macOS)

| | Tohum 1 | Tohum 2 |
|---|---|---|
| Ev / ağaç / kaya | 30 / 22 / 8 | 26 / 17 / 8 |
| Nesne / ortak mesh | 103 / 19 | 92 / 19 |
| Sahnedeki üçgen | 8 440 | 7 808 |
| GLB | 294 KB | 292 KB |

- Köyü kurmak 0,008 sn; Blender açılıp kapanması dahil 0,90 sn
- Ortak mesh olmadan aynı köy 551 KB (%47 daha büyük)
- Godot içe aktarma 1,76 sn; uçuşta ortalama 120,9 kare/sn

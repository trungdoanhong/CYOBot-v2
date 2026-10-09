# Original crawler model

These assets were copied byte-for-byte from the web export created during the Blender assembly session on 2026-09-27:

`C:\Users\manhpc\Documents\Codex\2026-09-27\to\outputs\cyobot-web\dist\robot`

The original assembly files were named `CYOBot_Crawler_complete_assembly.blend` and `CYOBot_Crawler_rigged_walk.blend`. They are not runtime dependencies or part of this app checkout. Studio uses the bundled URDF/STL export. `manifest.json` records source SHA-256 hashes; the historical source path above is provenance only. No access to that directory is needed on another computer.

- 115 visual meshes and 32 collision meshes are included; Studio loads the visual meshes.
- Eight active joints: `leg1_hip_servo`, `leg1_foot_servo`, through `leg4_foot_servo`; channels `[4,5,6,7,11,10,0,1]`.
- Lower/upper joints mimic the negative foot-servo angle to close the four-bar linkage.
- Geometry uses meters and Z up. The adapter rotates to Y up and scales by 20 for the Studio scene. Material colors come from the URDF.
- Displayed poses follow commanded angles with configured offsets/signs. There is no encoder feedback, dynamics or collision simulation. URDF limits remain metadata; the adapter displays the complete commanded range.

`../vendor/urdf/` contains URDFLoader 0.13.1 (Apache-2.0), reused from the earlier web export. The adapter uses STL only, redirects STLLoader and omits the unused Collada branch. STLLoader came from that export's Three.js 0.186.1 and runs with Studio's bundled Three.js r170. Runtime and loader licenses are in `../vendor/LICENSE`, `../vendor/STLLoader-LICENSE.txt` and `../vendor/urdf/LICENSE.txt`.

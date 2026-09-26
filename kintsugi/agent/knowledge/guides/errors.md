# Compile errors and warnings — what they mean, what to change

`iterate` returns the OpenSCAD output. Errors stop the export; warnings usually mean the part is silently wrong. Fix warnings too.

## Errors (no STL)

| message | cause | fix |
|---|---|---|
| `Current top level object is empty` | nothing was instantiated: the `render_target` branch matched nothing, every object is `%`/`*`, a module was defined but never called, or `cube(undef)` | check the `if (render_target == …)` chain, remove stray modifiers, call `part()` |
| `ERROR: Parser error in file …, line N: syntax error` | a missing `;`, unbalanced braces, `=` inside a call where `:` or `,` was meant, a keyword as a name | read the line number; the error is usually on the previous line |
| `Assertion '…' failed` | your `assert()` (the message is yours) or a BOSL2 argument check (the message names the parameter) | fix the parameter combination; for BOSL2 read the entry with `scad_docs(name=…)` |
| `Recursion detected calling function/module …` | unbounded recursion; the base case never hits | make the ternary base case reachable; prefer list comprehensions |
| `ERROR: all points for rotate_extrude() must have the same X coordinate sign` | the profile crosses x = 0 | shift the polygon to x ≥ 0 (radius must be positive) |
| `ERROR: CGAL error in CGAL_Nef_polyhedron3(): … has_on_positive_side` / `CGAL assertion` | degenerate geometry: a zero-thickness face, coincident faces in a boolean, a self-intersecting polygon | overlap unions by 0.01, overshoot cutters by 1 mm, simplify the polygon, avoid `minkowski` on complex bodies |
| `Normalized tree is growing past 200000 elements` | the CSG tree is too big (a loop instantiating hundreds of objects with high `$fn`) | lower `$fn` on repeated small features, union in 2D first, reduce copies |
| compile timeout (Kintsugi kills at 240 s) | minkowski, huge `$fn`, nested differences of many cylinders | drop `$fn` on bodies to 64–96, replace minkowski with offset/hull/BOSL2 rounding, hull instead of many unions |

## Warnings (STL exported, probably wrong)

| message | cause | fix |
|---|---|---|
| `WARNING: Object may not be a valid 2-manifold and may cause problems` | coincident faces or edges after a boolean; the checker will then say `mesh.watertight` fails or `mesh.single_body ≠ 1` | overlap / overshoot; move a cutter's end 1 mm past the face; do not let two cylinders touch tangentially |
| `WARNING: Ignoring unknown variable 'x'` | typo, or a variable defined inside another scope, or defined later inside a module | define it at the top or pass it as a parameter |
| `WARNING: Ignoring unknown module 'foo'` / `function 'foo'` | the name does not exist (not in 2021.01, not in this BOSL2, wrong include) | `scad_docs("foo")`; include the right BOSL2 file; use the vanilla equivalent |
| `WARNING: variable x was assigned on line A but was overwritten on line B` | the same name assigned twice — the last one wins everywhere | rename one of them |
| `WARNING: Too many unnamed arguments supplied` | a positional argument beyond the module's parameter list | use named arguments |
| `WARNING: undefined operation (undefined + number)` | arithmetic with `undef`, usually an unknown variable upstream | find the first unknown-variable warning |
| `DEPRECATED: The triangles parameter …` | old polyhedron syntax | use `faces` |
| `WARNING: Mixing 2D and 3D objects is not supported` | a 2D shape unioned with a 3D one (a forgotten `linear_extrude`), or `%` 2D leftovers | extrude everything before combining |
| `WARNING: Unable to convert translate([…]) parameter to a vec3 or vec2 of numbers` | `undef` inside a vector, or a nested list | check the variables feeding the vector |

## Checker failures that look like compile problems

- `no hole found at z = …` — the section plane misses the feature: the bore starts higher, a chamfer occupies that height, or the feature is off-origin. Move the feature to the frame the spec expects.
- A bore that measures 0.2–0.3 mm small with the right formula — facets: set `$fn = 128–160` on that primitive.
- `mesh.single_body = 2` — a loose piece: a cutter split the part, or a feature does not overlap the body (add 0.01 mm overlap).
- `print.on_bed` off by half the height — `center = true` on the extrusion or cube; translate up.
- `interference.<proxy>` fails although the bore is right — the proxy is the object; the part is *inside* it because the clearance sign is reversed (bore must be larger than the object), or the frame is shifted.

## Reading the numbers back

Compare the `echo()` line with the measured value in the check table. If they agree and the check fails, the target/tolerance is the issue (ask the user). If they disagree, the geometry is not where the formula says — a transform, a `$fn`, a stray offset — and the section sheet shows where.

# OpenSCAD 2021.01 essentials (what Kintsugi runs)

OpenSCAD is a *declarative* CSG language: a file is a tree of solids combined with union/difference/intersection, transformed, and evaluated once. Every part Kintsugi exports goes through `openscad -o part.stl -D render_target="part"`, headless, CGAL backend, with the vendored BOSL2 on the include path. Everything below is true of that setup.

## The mental model

- **Statements make geometry; expressions make values.** `cube(10);` is geometry. `x = 10;` is a value. Modules produce geometry, functions produce values.
- **Top-level objects are unioned.** Two statements next to each other are one solid. `difference()` keeps the first child and subtracts the rest.
- **Transforms apply to what follows.** `translate([0,0,6]) rotate(90) cube(10);` — read right-to-left: the cube is rotated, then translated. Braces group several children under one transform.
- **Units are whatever you say they are.** Kintsugi's spec is in millimetres; treat every number as mm.
- **Facets are yours to set.** Circles are polygons with `$fn` sides (or derived from `$fa`/`$fs`). Measured bores need 96–160 facets; bodies 64–96.

## Variables: immutable, scoped, "last assignment wins"

```scad
neck_d = 43;          // a measured object dimension
clearance = 0.25;     // fit clearance, kept as its own parameter
wall = 4;
ring_id = neck_d + clearance;      // order of top-level assignments does not matter
ring_od = ring_id + 2 * wall;
cylinder(h = 6, d = ring_od, $fn = 128);
```

- A variable is set once per scope, before any geometry is evaluated. You cannot reassign inside a loop or conditionally; compute per-iteration values with `let()`, functions and list comprehensions.
- Assigning the same name twice at the same level makes the **last** assignment win everywhere (with a warning). That is how `-D name=value` overrides and the customizer work — so never repeat a name.
- Inside a module, assignments are local to that module. Modules and functions can read file-level variables.
- Undefined names are `undef` (a warning, not an error) and poison arithmetic: `undef + 1` is `undef`, and `cube(undef)` is an empty object. Read the compile warnings.

## Values and operators

- Numbers are doubles. Trig works in **degrees**. `%` is modulo, `^` is power (2021.01), `/` is float division (`floor(a/b)` for integers).
- Vectors: `[1,2,3] + [1,1,1]`, `2 * v`, `v * w` is the **dot product**, `norm(v)`, `cross(a,b)`, `len(v)`, `v[0]`, `v.x` / `v.y` / `v.z` (2021.01).
- Strings: `str("bore ", d, " mm")`, `len(s)`, `s[0]`. No slicing syntax anywhere — use `[for (i=[a:b]) v[i]]`.
- Booleans: `&&`, `||`, `!`, comparisons; `undef` and `0` are false-ish. `x == undef` works; `is_undef(x)` is clearer.
- Ternary is the only conditional expression: `fit = c > 0.3 ? "loose" : "sliding";`.
- `let(a = 1, b = a + 1) expr` binds locals in an expression; `let (...) { ... }` in statement context.

## Ranges, lists, comprehensions

```scad
pts   = [for (a = [0 : 5 : 90]) [20 * cos(a), 20 * sin(a)]];   // inclusive range, step 5
holes = [for (x = [-30, 30], y = [-15, 15]) [x, y]];              // all combinations
even  = [for (i = [0 : 9]) if (i % 2 == 0) i];                    // filter
flat  = [for (p = holes) each [p.x, p.y]];                        // each splices
linear_extrude(2) polygon(concat([[0, 0]], pts));
```

- `[a:b]` is inclusive of both ends; `[a:step:b]` steps. A range with the wrong sign is empty (a warning).
- `concat(list, [x])` appends; `concat(list, x)` with a bare number is an error.
- `lookup(key, [[k,v],...])` interpolates linearly — good for clearance-by-diameter tables.

## Modules and functions

```scad
module boss(d, h, hole = 0) {                // geometry with parameters
    difference() {
        cylinder(h = h, d = d, $fn = 64);
        if (hole > 0) translate([0, 0, -1]) cylinder(h = h + 2, d = hole, $fn = 48);
    }
}
module both() { children(); mirror([1, 0, 0]) children(); }   // wrapper: applies to any children
function tooth(i, n, r) = [r * cos(i * 360 / n), r * sin(i * 360 / n)];   // value with parameters
sq = function(x) x * x;                       // function literal (2021.01)

both() translate([15, 0, 0]) boss(10, 8, 4.5);
echo(sq(3), tooth(1, 12, 10));
```

- Named arguments are allowed and make calls readable: `boss(d = 10, h = 8)`.
- `children()` inside a module places the caller's braced children; `$children` counts them.
- Functions can recurse (the ternary is the base case); recursion depth is limited (~1000s) — prefer comprehensions.

## Special variables and facets

- `$fn` = exact facet count; when `$fn = 0` the count comes from `$fa` (max angle per facet, default 12°) and `$fs` (min facet size, default 2 mm). The defaults are coarse — a 40 mm circle gets 30 facets. Set `$fn` explicitly.
- `$fn` is dynamically scoped: `cylinder(h=6, d=43.25, $fn=160)` applies to that primitive; `$fn = 96;` at the top applies to everything after it.
- A polygon inscribed in a circle of radius r has its flats at r·cos(180/$fn). With $fn = 96 that is 0.054 % under; at 43 mm, 0.012 mm — negligible. With $fn = 30 it is 0.55 % — 0.24 mm at 43 mm, enough to fail a ±0.3 check. **Never leave a measured bore at the default facets.**
- `$preview` is false in every Kintsugi compile (headless export). `$t` is animation time (unused).

## Modifier characters

- `%obj` — background: shown translucent in preview, **excluded from the export**. Kintsugi's `assembly()` ghosts the context proxies with it.
- `#obj` — debug highlight; still exported. `!obj` — render only that subtree. `*obj` — disable.

## Booleans without tears (manifold rules)

- **Overlap, don't touch.** Two solids sharing a face exactly produce non-manifold seams or slow CGAL. Overlap unions by 0.01–0.1 mm; make cutters overshoot by 1 mm on the faces they exit (`translate([0,0,-1]) cylinder(h = H + 2, ...)`).
- **No zero-thickness skins.** A cutter that ends exactly on a face leaves a face; a cutter 1 mm longer does not.
- `hull()` is fast and always manifold. `minkowski()` is correct but slow (seconds to minutes) — round 2D profiles with `offset()` instead.
- CGAL (2021.01) is slow on big facet counts and deep boolean trees: keep `$fn` where it matters, keep the tree shallow, and expect 2–20 s per compile for a repair part. A compile over ~60 s means something is too fine or a minkowski is hiding.
- `render()` and `convexity` only affect preview; the export is exact without them.

## What is not here

No `roof()`, no `textmetrics()`, no Manifold backend, no object literals, no `import()` in sessions, no `--enable` experimental features. Function literals, `^`, `is_function`, `each`, `let`, `assert`, `echo` expressions, `offset(chamfer=)`, `rotate_extrude(angle=)`, `text()`, `projection(cut=)` all work. The vendored BOSL2 2.0.759 works on this version (attachments, rounding, sweeps, threads, screws, masks, hinges, gears — all compiled here).

## Debugging on the command line

- `echo(name = value)` prints in the compile output that `iterate` returns. Echo the derived dimensions (bore with clearance, wall) and compare them with the check table.
- `assert(cond, "message")` fails the compile loudly. Put the spec's hard constraints in asserts.
- Read every WARNING: "unknown variable", "unknown module", "Ignoring unknown function" and "may not be a valid 2-manifold" each explain a wrong part before the checker does.

import { useEffect, useRef, useState, type ReactNode } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { useLocal } from "../hooks";
import { Empty, Spinner } from "../ui";

interface Props {
  url: string | null; // full URL (already cache-busted) or null when there is no STL yet
  placeholder?: string;
  /** a second mesh drawn translucent (the verified part behind a draft, a previous iteration…) */
  ghostUrl?: string | null;
  ghostLabel?: string;
  /** the spec's context proxies (the neck, the cap flange, a wall) drawn as a tinted ghost — the assembly in place */
  contextUrl?: string | null;
  /** force the context on (the assembly render target) */
  contextOn?: boolean;
  /** overlays rendered on top of the canvas (pills, toggles) */
  overlay?: ReactNode;
  /** show the overall dimensions as drafting-style dimension lines on the model */
  units?: "mm" | "in";
}

interface Label {
  pos: THREE.Vector3;
  el: HTMLDivElement;
}

interface Scene3 {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  group: THREE.Group;
  ghost: THREE.Group;
  context: THREE.Group;
  dims: THREE.Group;
  grid: THREE.Group;
  material: THREE.MeshStandardMaterial;
  ghostMaterial: THREE.MeshStandardMaterial;
  contextMaterial: THREE.MeshStandardMaterial;
  edgeMaterial: THREE.LineBasicMaterial;
  dimMaterial: THREE.LineBasicMaterial;
  bbox: THREE.Box3 | null;
  /** the XY offset that centres the part; ghosts and context proxies share it so the model frames line up */
  offset: THREE.Vector3;
  labels: Label[];
  needsRender: boolean;
  raf: number;
  applyTheme: () => void;
  dispose: () => void;
}

function cssVar(el: HTMLElement, name: string, fallback: string): string {
  const v = getComputedStyle(el).getPropertyValue(name).trim();
  return v || fallback;
}

function niceCell(extent: number): number {
  if (extent <= 12) return 1;
  if (extent <= 60) return 5;
  if (extent <= 400) return 10;
  return 50;
}

function fmtLen(mm: number, units: "mm" | "in"): string {
  return units === "in" ? `${(mm / 25.4).toFixed(3)} in` : `${mm.toFixed(1)} mm`;
}

export default function StlViewer({ url, placeholder, ghostUrl, ghostLabel, contextUrl, contextOn, overlay, units = "mm" }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const labelHost = useRef<HTMLDivElement>(null);
  const s3 = useRef<Scene3 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<{ size: number[]; tris: number; cell: number } | null>(null);
  const [glOk, setGlOk] = useState(true);
  const [showDims, setShowDims] = useLocal<boolean>("kin.viewer.dims", true);
  const [showGhost, setShowGhost] = useLocal<boolean>("kin.viewer.ghost", true);
  const [showContext, setShowContext] = useLocal<boolean>("kin.viewer.context", true);
  const contextVisible = !!contextUrl && (contextOn || showContext);
  const unitsRef = useRef(units);
  unitsRef.current = units;

  // ---- scene setup (once) --------------------------------------------------
  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    } catch {
      setGlOk(false);
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(el.clientWidth || 300, el.clientHeight || 200, false);
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 5000);
    camera.up.set(0, 0, 1);
    camera.position.set(120, -120, 90);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.12;
    controls.screenSpacePanning = true;

    const hemi = new THREE.HemisphereLight(0xffffff, 0x8a94a6, 1.1);
    hemi.position.set(0, 0, 1);
    scene.add(hemi);
    const key = new THREE.DirectionalLight(0xffffff, 1.4);
    key.position.set(1, -1.2, 2);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.5);
    fill.position.set(-1.5, 1, 0.6);
    scene.add(fill);

    const material = new THREE.MeshStandardMaterial({ color: 0xd3d8df, roughness: 0.62, metalness: 0.06, flatShading: true });
    // the ghost sits behind coplanar faces of the solid (polygon offset), so an unchanged region never z-fights
    const ghostMaterial = new THREE.MeshStandardMaterial({
      color: 0x1f4fa8, roughness: 0.8, metalness: 0, transparent: true, opacity: 0.2, depthWrite: false,
      polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 6,
    });
    const contextMaterial = new THREE.MeshStandardMaterial({
      color: 0xc9a227, roughness: 0.85, metalness: 0, transparent: true, opacity: 0.17, depthWrite: false, side: THREE.DoubleSide,
    });
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x7a8594, transparent: true, opacity: 0.55 });
    const dimMaterial = new THREE.LineBasicMaterial({ color: 0x1f4fa8, transparent: true, opacity: 0.9 });
    const group = new THREE.Group();
    const ghost = new THREE.Group();
    const context = new THREE.Group();
    const dims = new THREE.Group();
    const grid = new THREE.Group();
    scene.add(group, ghost, context, dims, grid);

    const state: Scene3 = {
      renderer,
      scene,
      camera,
      controls,
      group,
      ghost,
      context,
      dims,
      grid,
      material,
      ghostMaterial,
      contextMaterial,
      edgeMaterial,
      dimMaterial,
      bbox: null,
      offset: new THREE.Vector3(),
      labels: [],
      needsRender: true,
      raf: 0,
      applyTheme: () => {},
      dispose: () => {},
    };
    s3.current = state;

    const applyTheme = () => {
      // every colour comes from the design tokens so the viewer belongs to the theme it sits in
      const rule = new THREE.Color(cssVar(el, "--rule", "#c9d6ec"));
      const ink3 = new THREE.Color(cssVar(el, "--ink-3", "#5b6982"));
      const dark = matchMedia("(prefers-color-scheme: dark)").matches;
      material.color.set(cssVar(el, "--viewer-part", "#d6dfeb"));
      edgeMaterial.color.set(cssVar(el, "--viewer-edge", "#4d5f80"));
      ghostMaterial.color.set(cssVar(el, "--viewer-ghost", "#6c9ef0"));
      contextMaterial.color.set(cssVar(el, "--viewer-context", "#c9a227"));
      dimMaterial.color.set(cssVar(el, "--viewer-dim", "#155dd3"));
      grid.traverse((o) => {
        if (o instanceof THREE.GridHelper) {
          const mat = o.material as THREE.LineBasicMaterial;
          mat.color.copy(dark ? ink3 : o.userData.major ? ink3 : rule);
          mat.opacity = dark ? (o.userData.major ? 0.5 : 0.24) : o.userData.major ? 0.5 : 0.55;
          mat.transparent = true;
        }
      });
      state.needsRender = true;
    };
    state.applyTheme = applyTheme;
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", applyTheme);
    applyTheme();

    const resize = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      state.needsRender = true;
    };
    const ro = new ResizeObserver(resize);
    ro.observe(el);
    resize();

    const v = new THREE.Vector3();
    const placeLabels = () => {
      const w = el.clientWidth;
      const h = el.clientHeight;
      for (const lb of state.labels) {
        v.copy(lb.pos).project(camera);
        const x = (v.x * 0.5 + 0.5) * w;
        const y = (-v.y * 0.5 + 0.5) * h;
        const visible = v.z < 1 && x > -40 && x < w + 40 && y > -20 && y < h + 20;
        lb.el.style.transform = `translate(-50%, -50%) translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
        lb.el.style.opacity = visible ? "1" : "0";
      }
    };

    controls.addEventListener("change", () => (state.needsRender = true));
    const loop = () => {
      state.raf = requestAnimationFrame(loop);
      const moved = controls.update();
      if (moved || state.needsRender) {
        state.needsRender = false;
        renderer.render(scene, camera);
        placeLabels();
      }
    };
    loop();

    state.dispose = () => {
      cancelAnimationFrame(state.raf);
      ro.disconnect();
      mq.removeEventListener("change", applyTheme);
      controls.dispose();
      clearGroup(group);
      clearGroup(ghost);
      clearGroup(context);
      clearGroup(dims);
      clearGroup(grid);
      material.dispose();
      ghostMaterial.dispose();
      contextMaterial.dispose();
      edgeMaterial.dispose();
      dimMaterial.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
    return () => state.dispose();
  }, []);

  // ---- load model when url changes ----------------------------------------
  useEffect(() => {
    const st = s3.current;
    if (!st) return;
    let cancelled = false;
    clearGroup(st.group);
    const prev = st.bbox;
    st.needsRender = true;
    setInfo(null);
    setError(null);
    if (!url) {
      st.bbox = null;
      clearGroup(st.grid);
      clearGroup(st.dims);
      clearLabels(st, labelHost.current);
      return;
    }
    setLoading(true);
    const loader = new STLLoader();
    loader.load(
      url,
      (geometry) => {
        if (cancelled) {
          geometry.dispose();
          return;
        }
        geometry.computeVertexNormals();
        geometry.computeBoundingBox();
        const box = geometry.boundingBox!;
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        // centre the part in XY, keep Z (the bed is at z = 0 by convention; grid sits on the part's floor)
        const mesh = new THREE.Mesh(geometry, st.material);
        mesh.position.set(-center.x, -center.y, 0);
        st.group.add(mesh);
        st.offset.set(-center.x, -center.y, 0);
        st.context.position.copy(st.offset);   // the context proxies and any ghost share the part's frame
        st.ghost.position.copy(st.offset);
        const tris = geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3;
        if (tris < 250000) {
          const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), st.edgeMaterial);
          edges.position.copy(mesh.position);
          st.group.add(edges);
        }
        const cell = buildGrid(st, size, box.min.z);
        st.bbox = new THREE.Box3(new THREE.Vector3(-size.x / 2, -size.y / 2, box.min.z), new THREE.Vector3(size.x / 2, size.y / 2, box.max.z));
        // keep the camera where the person left it when the part only changed a little (a slider drag); refit otherwise
        const similar = !!prev && prev.getSize(new THREE.Vector3()).distanceTo(size) < Math.max(size.length() * 0.35, 5);
        if (!similar) fitCamera(st, "iso");
        buildDims(st, labelHost.current, showDims, unitsRef.current);
        st.applyTheme();
        st.needsRender = true;
        setInfo({ size: [size.x, size.y, size.z], tris, cell });
        setLoading(false);
      },
      undefined,
      (err) => {
        if (cancelled) return;
        setLoading(false);
        setError(err instanceof Error ? err.message : "Could not load STL");
      },
    );
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);

  // ---- ghost mesh -----------------------------------------------------------
  useEffect(() => {
    const st = s3.current;
    if (!st) return;
    let cancelled = false;
    clearGroup(st.ghost);
    st.needsRender = true;
    if (!ghostUrl || !showGhost) return;
    const loader = new STLLoader();
    loader.load(
      ghostUrl,
      (geometry) => {
        if (cancelled) {
          geometry.dispose();
          return;
        }
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(geometry, st.ghostMaterial);
        mesh.renderOrder = 2;
        st.ghost.position.copy(st.offset);
        st.ghost.add(mesh);
        st.needsRender = true;
      },
      undefined,
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [ghostUrl, showGhost]);

  // ---- context proxies (the assembly) -----------------------------------------
  useEffect(() => {
    const st = s3.current;
    if (!st) return;
    let cancelled = false;
    clearGroup(st.context);
    st.needsRender = true;
    if (!contextUrl || !contextVisible) return;
    const loader = new STLLoader();
    loader.load(
      contextUrl,
      (geometry) => {
        if (cancelled) {
          geometry.dispose();
          return;
        }
        geometry.computeVertexNormals();
        const mesh = new THREE.Mesh(geometry, st.contextMaterial);
        mesh.renderOrder = 3;
        st.context.position.copy(st.offset);
        st.context.add(mesh);
        st.needsRender = true;
      },
      undefined,
      () => {},
    );
    return () => {
      cancelled = true;
    };
  }, [contextUrl, contextVisible]);

  // ---- dimension lines toggle / units -----------------------------------------
  useEffect(() => {
    const st = s3.current;
    if (!st) return;
    buildDims(st, labelHost.current, showDims, units);
    st.needsRender = true;
  }, [showDims, units]);

  const view = (kind: "iso" | "top" | "front") => {
    const st = s3.current;
    if (st && st.bbox) fitCamera(st, kind);
  };

  if (!glOk) {
    return (
      <div className="viewer-overlay">
        <Empty title="WebGL unavailable">The 3D viewer needs WebGL. Use the Views tab for the rendered sheets.</Empty>
      </div>
    );
  }

  return (
    <>
      <div className="viewer" ref={host} />
      <div className="viewer-labels" ref={labelHost} aria-hidden="true" />
      {url && (
        <div className="viewer-tools">
          <button className="btn btn-xs" onClick={() => view("iso")} title="Isometric view">
            ISO
          </button>
          <button className="btn btn-xs" onClick={() => view("top")} title="Top view">
            TOP
          </button>
          <button className="btn btn-xs" onClick={() => view("front")} title="Front view">
            FRONT
          </button>
          <button className={`btn btn-xs${showDims ? " active" : ""}`} onClick={() => setShowDims(!showDims)} title="Overall dimensions on the model" aria-pressed={showDims}>
            DIMS
          </button>
          {ghostUrl && (
            <button className={`btn btn-xs${showGhost ? " active" : ""}`} onClick={() => setShowGhost(!showGhost)} title={ghostLabel || "Show the reference mesh as a ghost"} aria-pressed={showGhost}>
              GHOST
            </button>
          )}
          {contextUrl && (
            <button
              className={`btn btn-xs${contextVisible ? " active" : ""}`}
              onClick={() => setShowContext(!showContext)}
              disabled={!!contextOn}
              title={contextOn ? "The assembly view always shows the mating object" : "Show the spec's context proxies (the object the part mates with) in place"}
              aria-pressed={contextVisible}
            >
              OBJECT
            </button>
          )}
        </div>
      )}
      {overlay}
      {info && (
        <div className="viewer-hud">
          <span>
            <b>{fmtLen(info.size[0], units).replace(/ (mm|in)$/, "")}</b> × <b>{fmtLen(info.size[1], units).replace(/ (mm|in)$/, "")}</b> ×{" "}
            <b>{fmtLen(info.size[2], units).replace(/ (mm|in)$/, "")}</b> {units}
          </span>
          <span>{info.tris.toLocaleString()} tris</span>
          <span>grid {info.cell} mm</span>
        </div>
      )}
      {loading && (
        <div className="viewer-overlay" style={{ pointerEvents: "none" }}>
          <Spinner label="Loading mesh…" />
        </div>
      )}
      {error && (
        <div className="viewer-overlay">
          <Empty title="Could not load the mesh">{error}</Empty>
        </div>
      )}
      {!url && !error && (
        <div className="viewer-overlay">
          <Empty title="No mesh yet" icon={<CubeIcon />}>
            {placeholder || "The 3D model appears here after the first iteration compiles."}
          </Empty>
        </div>
      )}
    </>
  );
}

function clearGroup(g: THREE.Group) {
  for (const child of [...g.children]) {
    g.remove(child);
    const obj = child as THREE.Mesh;
    if (obj.geometry) obj.geometry.dispose();
  }
}

function clearLabels(st: Scene3, host: HTMLDivElement | null) {
  for (const lb of st.labels) lb.el.remove();
  st.labels = [];
  if (host) host.innerHTML = "";
}

function buildGrid(st: Scene3, size: THREE.Vector3, z: number): number {
  clearGroup(st.grid);
  const extent = Math.max(size.x, size.y);
  const cell = niceCell(extent);
  const span = Math.max(cell * 4, Math.ceil((extent * 1.8) / (cell * 2)) * cell * 2);
  const minor = new THREE.GridHelper(span, span / cell);
  minor.rotation.x = Math.PI / 2;
  minor.position.z = z - 0.02;
  minor.userData.major = false;
  st.grid.add(minor);
  const major = new THREE.GridHelper(span, Math.max(1, span / (cell * 5)));
  major.rotation.x = Math.PI / 2;
  major.position.z = z - 0.01;
  major.userData.major = true;
  st.grid.add(major);
  return cell;
}

/** Drafting-style overall dimensions: three dimension lines with extension lines and ticks, labelled in DOM. */
function buildDims(st: Scene3, host: HTMLDivElement | null, show: boolean, units: "mm" | "in") {
  clearGroup(st.dims);
  clearLabels(st, host);
  const box = st.bbox;
  if (!show || !box || !host) return;
  const min = box.min;
  const max = box.max;
  const size = box.getSize(new THREE.Vector3());
  const ext = Math.max(size.x, size.y, size.z, 1);
  const off = Math.max(3, ext * 0.09);
  const tick = Math.max(1, ext * 0.02);
  const pts: THREE.Vector3[] = [];
  const seg = (a: THREE.Vector3, b: THREE.Vector3) => pts.push(a, b);
  const V = (x: number, y: number, z: number) => new THREE.Vector3(x, y, z);

  // X: along the front edge (y = min.y - off) at bed level
  const yx = min.y - off;
  seg(V(min.x, yx, min.z), V(max.x, yx, min.z));
  seg(V(min.x, min.y - tick * 0.6, min.z), V(min.x, yx - tick, min.z));
  seg(V(max.x, min.y - tick * 0.6, min.z), V(max.x, yx - tick, min.z));
  seg(V(min.x, yx - tick, min.z), V(min.x, yx + tick, min.z));
  seg(V(max.x, yx - tick, min.z), V(max.x, yx + tick, min.z));
  // Y: along the right edge (x = max.x + off) at bed level
  const xy = max.x + off;
  seg(V(xy, min.y, min.z), V(xy, max.y, min.z));
  seg(V(max.x + tick * 0.6, min.y, min.z), V(xy + tick, min.y, min.z));
  seg(V(max.x + tick * 0.6, max.y, min.z), V(xy + tick, max.y, min.z));
  seg(V(xy - tick, min.y, min.z), V(xy + tick, min.y, min.z));
  seg(V(xy - tick, max.y, min.z), V(xy + tick, max.y, min.z));
  // Z: a vertical line at the front-right corner, offset outward
  const xz = max.x + off;
  const yz = min.y - off;
  seg(V(xz, yz, min.z), V(xz, yz, max.z));
  seg(V(max.x + tick * 0.6, min.y - tick * 0.6, max.z), V(xz + tick * 0.7, yz - tick * 0.7, max.z));
  seg(V(xz - tick, yz, min.z), V(xz + tick, yz, min.z));
  seg(V(xz - tick, yz, max.z), V(xz + tick, yz, max.z));

  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  st.dims.add(new THREE.LineSegments(geo, st.dimMaterial));

  const mk = (pos: THREE.Vector3, text: string, axis: string) => {
    const el = document.createElement("div");
    el.className = `dim-label dim-${axis}`;
    el.textContent = text;
    host.appendChild(el);
    st.labels.push({ pos, el });
  };
  mk(V((min.x + max.x) / 2, yx - tick * 1.8, min.z), fmtLen(size.x, units), "x");
  mk(V(xy + tick * 1.8, (min.y + max.y) / 2, min.z), fmtLen(size.y, units), "y");
  mk(V(xz + tick * 1.2, yz - tick * 1.2, (min.z + max.z) / 2), fmtLen(size.z, units), "z");
}

function fitCamera(st: Scene3, kind: "iso" | "top" | "front") {
  const box = st.bbox;
  if (!box) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 1);
  const fov = (st.camera.fov * Math.PI) / 180;
  const aspect = st.camera.aspect || 1;
  const hfov = 2 * Math.atan(Math.tan(fov / 2) * aspect);
  const dist = (radius / Math.sin(Math.min(fov, hfov) / 2)) * 1.12;
  const dir =
    kind === "top" ? new THREE.Vector3(0, -0.0001, 1) : kind === "front" ? new THREE.Vector3(0, -1, 0.0001) : new THREE.Vector3(1, -1, 0.75);
  st.camera.position.copy(center).add(dir.normalize().multiplyScalar(dist));
  st.camera.near = Math.max(dist / 200, 0.05);
  st.camera.far = dist * 50;
  st.camera.updateProjectionMatrix();
  st.controls.target.copy(center);
  st.controls.update();
  st.needsRender = true;
}

function CubeIcon() {
  return (
    <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round">
      <path d="M12 3 3 7.5v9L12 21l9-4.5v-9L12 3z" />
      <path d="M3 7.5 12 12l9-4.5M12 12v9" />
    </svg>
  );
}

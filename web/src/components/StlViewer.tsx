import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { Empty, Spinner } from "../ui";

interface Props {
  url: string | null; // full URL (already cache-busted) or null when there is no STL yet
  placeholder?: string;
}

interface Scene3 {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  controls: OrbitControls;
  group: THREE.Group;
  grid: THREE.Group;
  material: THREE.MeshStandardMaterial;
  edgeMaterial: THREE.LineBasicMaterial;
  bbox: THREE.Box3 | null;
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

export default function StlViewer({ url, placeholder }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const s3 = useRef<Scene3 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<{ size: number[]; tris: number; cell: number } | null>(null);
  const [glOk, setGlOk] = useState(true);

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
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x7a8594, transparent: true, opacity: 0.55 });
    const group = new THREE.Group();
    scene.add(group);
    const grid = new THREE.Group();
    scene.add(grid);

    const state: Scene3 = {
      renderer,
      scene,
      camera,
      controls,
      group,
      grid,
      material,
      edgeMaterial,
      bbox: null,
      needsRender: true,
      raf: 0,
      applyTheme: () => {},
      dispose: () => {},
    };
    s3.current = state;

    const applyTheme = () => {
      const rule = new THREE.Color(cssVar(el, "--rule", "#c9d0da"));
      const ink3 = new THREE.Color(cssVar(el, "--ink-3", "#7a8594"));
      const dark = matchMedia("(prefers-color-scheme: dark)").matches;
      material.color.set(dark ? 0xb9c2ce : 0xd3d8df);
      edgeMaterial.color.set(dark ? 0x1e2a3a : 0x5c6675);
      grid.traverse((o) => {
        if (o instanceof THREE.GridHelper) {
          const mat = o.material as THREE.LineBasicMaterial;
          mat.color.copy(dark ? ink3 : o.userData.major ? ink3 : rule);
          mat.opacity = dark ? (o.userData.major ? 0.55 : 0.28) : o.userData.major ? 0.55 : 0.5;
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

    controls.addEventListener("change", () => (state.needsRender = true));
    const loop = () => {
      state.raf = requestAnimationFrame(loop);
      const moved = controls.update();
      if (moved || state.needsRender) {
        state.needsRender = false;
        renderer.render(scene, camera);
      }
    };
    loop();

    state.dispose = () => {
      cancelAnimationFrame(state.raf);
      ro.disconnect();
      mq.removeEventListener("change", applyTheme);
      controls.dispose();
      clearGroup(group);
      clearGroup(grid);
      material.dispose();
      edgeMaterial.dispose();
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
    st.bbox = null;
    st.needsRender = true;
    setInfo(null);
    setError(null);
    if (!url) {
      clearGroup(st.grid);
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
        const tris = geometry.index ? geometry.index.count / 3 : geometry.attributes.position.count / 3;
        if (tris < 250000) {
          const edges = new THREE.LineSegments(new THREE.EdgesGeometry(geometry, 28), st.edgeMaterial);
          edges.position.copy(mesh.position);
          st.group.add(edges);
        }
        const cell = buildGrid(st, size, box.min.z);
        st.bbox = new THREE.Box3(
          new THREE.Vector3(-size.x / 2, -size.y / 2, box.min.z),
          new THREE.Vector3(size.x / 2, size.y / 2, box.max.z),
        );
        fitCamera(st, "iso");
        st.applyTheme();
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
  }, [url]);

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
        </div>
      )}
      {info && (
        <div className="viewer-hud">
          <span>
            <b>{info.size[0].toFixed(1)}</b> × <b>{info.size[1].toFixed(1)}</b> × <b>{info.size[2].toFixed(1)}</b> mm
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

function fitCamera(st: Scene3, kind: "iso" | "top" | "front") {
  const box = st.bbox;
  if (!box) return;
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.length() / 2, 1);
  const fov = (st.camera.fov * Math.PI) / 180;
  const aspect = st.camera.aspect || 1;
  const hfov = 2 * Math.atan(Math.tan(fov / 2) * aspect);
  const dist = (radius / Math.sin(Math.min(fov, hfov) / 2)) * 1.05;
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

// Kintsugi — HACK47: OFFGRID pitch deck (draft 1). Drafting-sheet visual system: paper, ink, blueprint blue,
// pass green, fail red; the recurring motif is the dimension line (a measured number between two arrowheads).
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const Fi = require("react-icons/fi");

const C = {
  paper: "FAFBFC", ink: "18212C", ink2: "4A5563", ink3: "7A8594", rule: "C9D0DA", rule2: "E1E6EC",
  blue: "1F4FA8", blueSoft: "E4ECFA", pass: "1F7A46", passSoft: "E3F1E8", fail: "B8322A", failSoft: "F6E4E2",
  warn: "9A6A08", warnSoft: "F5EBD3", navy: "0E1A2B", navy2: "132238", ice: "E4ECF6", ice2: "AFBCCB", sky: "8FB8FF",
};
const FONT_H = "Arial";
const FONT_B = "Calibri";
const FONT_M = "Courier New";
const IMG = (n) => path.join(__dirname, "img", n);

async function iconPng(Icon, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Icon, { color: "#" + color, size, strokeWidth: 2 }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9"; // 10 x 5.625 in
pres.author = "Krish Gupta";
pres.title = "Kintsugi — Photograph what broke. Print what fits.";

// ---- helpers ------------------------------------------------------------------------------------------
function bg(slide, color) {
  slide.background = { color };
}
function title(slide, text, opts = {}) {
  const dark = !!opts.dark;
  slide.addText(text, {
    x: 0.5, y: 0.35, w: opts.w || 9.0, h: 0.75, fontFace: FONT_H, fontSize: opts.size || 30, bold: true,
    color: dark ? C.ice : C.ink, isTextBox: true, margin: 0, valign: "middle",
  });
}
function body(slide, x, y, w, h, runs, opts = {}) {
  slide.addText(runs, { x, y, w, h, fontFace: FONT_B, fontSize: opts.size || 14, color: opts.color || C.ink2, isTextBox: true, margin: 0, valign: opts.valign || "top", paraSpaceAfter: opts.para || 6, ...opts.extra });
}
function mono(slide, x, y, w, h, text, opts = {}) {
  slide.addText(text, { x, y, w, h, fontFace: FONT_M, fontSize: opts.size || 10, color: opts.color || C.ink3, isTextBox: true, margin: 0, valign: "middle", align: opts.align || "left", fill: opts.fill ? { color: opts.fill } : undefined });
}
// the motif: a dimension line with arrowheads and a measured value in the middle
function dimLine(slide, x, y, w, value, label, opts = {}) {
  const color = opts.color || C.blue;
  const paper = opts.paper || C.paper;
  slide.addShape(pres.ShapeType.line, { x, y: y + 0.19, w, h: 0, line: { color, width: 1.25, beginArrowType: "triangle", endArrowType: "triangle" } });
  // extension ticks
  slide.addShape(pres.ShapeType.line, { x, y: y + 0.05, w: 0, h: 0.28, line: { color, width: 1 } });
  slide.addShape(pres.ShapeType.line, { x: x + w, y: y + 0.05, w: 0, h: 0.28, line: { color, width: 1 } });
  const lw = Math.min(w - 0.4, Math.max(1.2, (value.length + 2) * 0.12 + 0.3));
  slide.addText(value, { x: x + (w - lw) / 2, y: y - 0.02, w: lw, h: 0.42, fontFace: FONT_M, fontSize: opts.size || 15, bold: true, color, fill: { color: paper }, align: "center", valign: "middle", isTextBox: true, margin: 0 });
  if (label) slide.addText(label, { x, y: y + 0.42, w, h: 0.3, fontFace: FONT_B, fontSize: opts.labelSize || 11, color: opts.labelColor || C.ink3, align: "center", isTextBox: true, margin: 0 });
}
function card(slide, x, y, w, h, opts = {}) {
  slide.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.06, fill: { color: opts.fill || "FFFFFF" }, line: { color: opts.line || C.rule2, width: 0.75 }, shadow: opts.shadow ? { type: "outer", blur: 4, offset: 1, angle: 90, color: "000000", opacity: 0.08 } : undefined });
}
function numCircle(slide, x, y, n, opts = {}) {
  slide.addShape(pres.ShapeType.ellipse, { x, y, w: 0.34, h: 0.34, fill: { color: opts.fill || C.blue }, line: { color: opts.fill || C.blue, width: 0 } });
  slide.addText(String(n), { x, y, w: 0.34, h: 0.34, fontFace: FONT_H, fontSize: 12, bold: true, color: opts.color || "FFFFFF", align: "center", valign: "middle", isTextBox: true, margin: 0 });
}
function footer(slide, text, dark = false) {
  slide.addText(text, { x: 0.5, y: 5.22, w: 9.0, h: 0.25, fontFace: FONT_M, fontSize: 8.5, color: dark ? C.ice2 : C.ink3, isTextBox: true, margin: 0, valign: "middle" });
}
function frame(slide, x, y, w, h, img, opts = {}) {
  // an image inside a thin rounded frame (the sheet-panel look)
  slide.addShape(pres.ShapeType.roundRect, { x: x - 0.04, y: y - 0.04, w: w + 0.08, h: h + 0.08, rectRadius: 0.05, fill: { color: opts.fill || "FFFFFF" }, line: { color: opts.line || C.rule, width: 0.75 } });
  slide.addImage({ path: img, x, y, w, h, sizing: { type: opts.sizing || "contain", w, h } });
}

(async () => {
  const icons = {};
  for (const [k, Icon, col] of [
    ["alert", Fi.FiAlertTriangle, C.fail], ["package", Fi.FiPackage, C.warn], ["code", Fi.FiCode, C.blue],
    ["camera", Fi.FiCamera, C.blue], ["cross", Fi.FiCrosshair, C.blue], ["cpu", Fi.FiCpu, C.blue], ["eye", Fi.FiEye, C.blue],
    ["target", Fi.FiTarget, C.blue], ["download", Fi.FiDownload, C.blue], ["check", Fi.FiCheckCircle, C.pass],
    ["layers", Fi.FiLayers, C.sky], ["users", Fi.FiUsers, C.sky], ["cart", Fi.FiShoppingCart, C.sky], ["cloud", Fi.FiUploadCloud, C.sky],
    ["book", Fi.FiBookOpen, C.sky], ["git", Fi.FiGitBranch, C.blue], ["ruler", Fi.FiSliders, C.blue], ["zap", Fi.FiZap, C.sky],
    ["help", Fi.FiHelpCircle, C.blue], ["shield", Fi.FiShield, C.blue], ["smartphone", Fi.FiSmartphone, C.blue], ["printer", Fi.FiPrinter, C.blue], ["sliders", Fi.FiSliders, C.blue],
  ]) icons[k] = await iconPng(Icon, col);

  // ---- 1. title (dark) ------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.navy);
    s.addText("KINTSUGI", { x: 0.6, y: 1.05, w: 5.6, h: 1.0, fontFace: FONT_H, fontSize: 54, bold: true, color: C.ice, isTextBox: true, margin: 0, charSpacing: 6 });
    s.addText("Photograph what broke. Print what fits.", { x: 0.6, y: 2.0, w: 5.6, h: 0.6, fontFace: FONT_B, fontSize: 24, color: C.sky, isTextBox: true, margin: 0 });
    s.addText("An agent that turns phone photos of a broken part into a verified, printable replacement — and checks its own work like an engineer.",
      { x: 0.6, y: 2.7, w: 5.3, h: 1.0, fontFace: FONT_B, fontSize: 14, color: C.ice2, isTextBox: true, margin: 0 });
    dimLine(s, 0.6, 3.9, 3.6, "3 photos → 1 STL", "", { color: C.sky, paper: C.navy, size: 14 });
    s.addText("HACK47: OFFGRID · September–October 2026\nBuilt on the OpenAI Responses API · GPT-6", { x: 0.6, y: 4.6, w: 5.6, h: 0.55, fontFace: FONT_M, fontSize: 10, color: C.ice2, isTextBox: true, margin: 0 });
    s.addText("Krish Gupta", { x: 7.4, y: 4.75, w: 2.0, h: 0.35, fontFace: FONT_B, fontSize: 12, color: C.ice2, align: "right", isTextBox: true, margin: 0 });
    frame(s, 6.45, 1.05, 3.0, 3.35, IMG("assembly_iso.png"), { fill: C.navy2, line: "2C4260" });
    s.addText("assembly view · context ghosted · dimensions from the mesh", { x: 6.45, y: 4.45, w: 3.0, h: 0.25, fontFace: FONT_M, fontSize: 8, color: C.ice2, isTextBox: true, margin: 0 });
    s.addNotes("Open with the object in hand if you can: the snapped handle and the printed one. Kintsugi is an agent that designs 3D-printed replacement parts from phone photos — the difference from 'ask an LLM for the CAD' is that it measures, verifies and asks for what it still needs.");
  }

  // ---- 2. problem ------------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "It breaks at the one part that mattered.");
    const rows = [
      ["alert", "The object still works. The part that fits it no longer exists.", "A handle, a clip, a knob, a cap — small, specific, and the reason the whole thing is in the bin."],
      ["package", "Replacement means shipping a whole new thing. Or nothing, off-grid.", "The supply chain is the wrong size for a 6-gram part."],
      ["code", "\"Just ask an LLM for the OpenSCAD\" gives you plausible code that is 1.5 mm out.", "The model never sees what it built. Nobody measured anything."],
    ];
    rows.forEach(([ic, head, sub], i) => {
      const y = 1.35 + i * 1.15;
      s.addShape(pres.ShapeType.ellipse, { x: 0.5, y: y + 0.02, w: 0.52, h: 0.52, fill: { color: i === 0 ? C.failSoft : i === 1 ? C.warnSoft : C.blueSoft }, line: { width: 0 } });
      s.addImage({ data: icons[ic], x: 0.62, y: y + 0.14, w: 0.28, h: 0.28 });
      s.addText(head, { x: 1.2, y, w: 4.6, h: 0.55, fontFace: FONT_B, fontSize: 14.5, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "top" });
      s.addText(sub, { x: 1.2, y: y + 0.55, w: 4.6, h: 0.45, fontFace: FONT_B, fontSize: 12, color: C.ink2, isTextBox: true, margin: 0, valign: "top" });
    });
    // photo placeholder (replace with the real snapped handle)
    s.addShape(pres.ShapeType.roundRect, { x: 6.2, y: 1.3, w: 3.3, h: 3.3, rectRadius: 0.06, fill: { color: "FFFFFF" }, line: { color: C.rule, width: 1, dashType: "dash" } });
    s.addImage({ data: icons["camera"], x: 7.6, y: 2.35, w: 0.5, h: 0.5 });
    s.addText("[photo: the snapped handle on the bottle — replace]", { x: 6.4, y: 2.95, w: 2.9, h: 0.6, fontFace: FONT_M, fontSize: 9, color: C.ink3, align: "center", isTextBox: true, margin: 0 });
    dimLine(s, 6.2, 4.75, 3.3, "1 of 1 parts", "the one that broke", { size: 12 });
    footer(s, "Kintsugi — the repair is visible, and it is the point.");
    s.addNotes("The personal version: the carry handle on my water bottle snapped at the ring. A 6 mm ring and a loop. Five minutes for someone who can measure a neck and write OpenSCAD; impossible for everyone else. And the naive LLM version fails in a specific way: it is plausible and it doesn't fit.");
  }

  // ---- 3. what it does (six steps) ------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "Photograph what broke. Print what fits.");
    const steps = [
      ["camera", "Intake", "Photos + one sentence → the part, the features it mates with, a draft spec. Standard sizes it recognises become first estimates."],
      ["cross", "Capture rounds", "The evidence graph knows what is still a guess; the capture agent asks for the exact photo or ruler reading, measures uploads on a calibration sheet, stops when it knows enough."],
      ["cpu", "Design loop", "GPT-6 writes OpenSCAD; every spec dimension is measured on the exported mesh; blueprints carry those numbers as dimension lines it must look at."],
      ["eye", "Code-blind critic", "A second model reviews drawings and checks — never the code — and sends the design back when the numbers pass but the part is wrong."],
      ["target", "Fit coupon", "The mating feature alone at three clearances, printed first. The one that slides on locks the clearance."],
      ["download", "Export", "Oriented STL/3MF, a customizer-ready .scad (every dimension a slider), blueprint PDF, a print card that says why."],
    ];
    steps.forEach(([ic, head, text], i) => {
      const col = i % 3, row = Math.floor(i / 3);
      const x = 0.5 + col * 3.05, y = 1.25 + row * 1.85;
      card(s, x, y, 2.85, 1.65, { shadow: true });
      numCircle(s, x + 0.15, y + 0.15, i + 1);
      s.addImage({ data: icons[ic], x: x + 2.4, y: y + 0.17, w: 0.3, h: 0.3 });
      s.addText(head, { x: x + 0.6, y: y + 0.12, w: 1.8, h: 0.4, fontFace: FONT_H, fontSize: 13, bold: true, color: C.ink, isTextBox: true, margin: 0, valign: "middle" });
      s.addText(text, { x: x + 0.15, y: y + 0.58, w: 2.55, h: 1.0, fontFace: FONT_B, fontSize: 10.5, color: C.ink2, isTextBox: true, margin: 0, valign: "top" });
    });
    footer(s, "web app · phone-friendly capture · runs locally with your OpenAI key · demo mode needs no key");
    s.addNotes("Six steps, and the user only does three of them: photos, a couple of readings, and looking at the result. Everything in between is the agent measuring, designing, checking and asking.");
  }

  // ---- 4. key idea: verification -----------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "The model never grades its own homework.");
    frame(s, 0.5, 1.25, 5.3, 3.05, IMG("section_aa.png"));
    s.addText("SECTION A-A of iteration 1 — the bore is measured on the mesh at 43.45 mm against 43.25 ± 0.3 (43 + 0.25 clearance); the label is green because it passed, and the model sees exactly this picture.",
      { x: 0.5, y: 4.35, w: 5.3, h: 0.6, fontFace: FONT_B, fontSize: 9.5, color: C.ink3, isTextBox: true, margin: 0, italic: true });
    const pts = [
      ["ruler", "Measured, never trusted", "A Part Spec dimension carries a measure recipe (circle fit at z = 3, hole extent along x, gap, notch mouth…). The checker runs it on the exported STL."],
      ["eye", "Drawn from the measurement", "Views, sections and assembly sheets with dimension lines computed from the mesh, in pass/fail colour. The model must look before it changes anything."],
      ["shield", "Reviewed without the code", "A fresh-context critic gets the spec, the check table and the drawings. It catches a hole through the load path or missing finger scallops — things no number can."],
    ];
    pts.forEach(([ic, head, text], i) => {
      const y = 1.25 + i * 1.0;
      s.addShape(pres.ShapeType.ellipse, { x: 6.1, y: y + 0.02, w: 0.42, h: 0.42, fill: { color: C.blueSoft }, line: { width: 0 } });
      s.addImage({ data: icons[ic], x: 6.2, y: y + 0.12, w: 0.22, h: 0.22 });
      s.addText(head, { x: 6.65, y, w: 2.85, h: 0.3, fontFace: FONT_B, fontSize: 13, bold: true, color: C.ink, isTextBox: true, margin: 0 });
      s.addText(text, { x: 6.65, y: y + 0.3, w: 2.85, h: 0.68, fontFace: FONT_B, fontSize: 10, color: C.ink2, isTextBox: true, margin: 0 });
    });
    dimLine(s, 6.2, 4.42, 3.2, "43.45 [43.25 ±0.3] ✓", "what the model sees, not what it wrote", { size: 12, color: C.pass });
    s.addNotes("This is the idea the whole system is built around. Verification is executable, not interpretive: every dimension knows how to measure itself on the finished mesh. And the drawings the model looks at are generated from those measurements, so it cannot fake them.");
  }

  // ---- 5. capture loop ---------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "It asks for the photo it needs — not a number.", { size: 26 });
    frame(s, 0.5, 1.25, 1.62, 3.78, IMG("capture_guide.png"), { sizing: "cover" });
    frame(s, 2.35, 1.25, 3.2, 1.15, IMG("evidence_map.png"));
    s.addText("the evidence graph: photos, readings and standards → estimates → dimensions → checks",
      { x: 2.35, y: 2.45, w: 3.2, h: 0.4, fontFace: FONT_B, fontSize: 9, color: C.ink3, isTextBox: true, margin: 0, italic: true });
    body(s, 2.35, 2.95, 3.25, 2.1, [
      { text: "One photo per mating feature, pressed flat on a printed ArUco calibration sheet; each upload is graded and measured automatically.", options: { bullet: true, breakLine: true } },
      { text: "Heights get a ruler reading; a standard size (63-415 finish, 3/4\" PVC, M5) gets one confirming photo.", options: { bullet: true, breakLine: true } },
      { text: "A capture agent rewrites the round for the object in the pictures: what to remove, which side down, what to avoid.", options: { bullet: true, breakLine: true } },
      { text: "The designer can ask the same way mid-run; the measured value comes back in its resume message.", options: { bullet: true } },
    ], { size: 10.5, para: 4 });
    dimLine(s, 5.95, 1.45, 3.5, "≤ 0.5 mm", "diameter error on synthetic ground truth, up to 35° of camera tilt", { size: 15 });
    dimLine(s, 5.95, 2.55, 3.5, "≤ 0.3 mm", "circle-centre error", { size: 15 });
    dimLine(s, 5.95, 3.65, 3.5, "1 round", "for the bottle handle: one sheet photo, one ruler reading, ready", { size: 15 });
    footer(s, "kintsugi/spec/evidence.py · kintsugi/agent/capture.py · kintsugi/measure/");
    s.addNotes("The follow-up loop is driven by a graph, not a prompt. missing() ranks what still needs evidence; plan_round() batches it into the fewest user actions; readiness() decides when designing is safe. The model's job is to write the instructions for this object — the arithmetic is ours.");
  }

  // ---- 6. graph engineering (dark) ----------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.navy);
    title(s, "Every stage is a typed dataflow graph.", { dark: true });
    frame(s, 0.5, 1.3, 4.3, 2.55, IMG("graph_pipeline.png"), { fill: C.navy2, line: "2C4260" });
    s.addText("the iteration pipeline, live: params ∥ compile → mesh → checks ∥ views ∥ context → sections ∥ assembly → compose; blue = critical path",
      { x: 0.5, y: 3.9, w: 4.3, h: 0.5, fontFace: FONT_B, fontSize: 9, color: C.ice2, isTextBox: true, margin: 0, italic: true });
    body(s, 5.2, 1.3, 4.3, 2.4, [
      { text: "Nodes declare inputs and outputs; edges follow. A node starts the moment its inputs exist — no wave barriers.", options: { bullet: true, breakLine: true } },
      { text: "Algorithms run in threads, model calls as coroutines; guards skip, optional nodes may fail, after= orders without data.", options: { bullet: true, breakLine: true } },
      { text: "People are nodes: a human node suspends the run with a request and resumes when the answer lands in the state.", options: { bullet: true, breakLine: true } },
      { text: "Every run leaves a trace — per-node timing, the critical path, serial vs wall — drawn live in the Graph tab.", options: { bullet: true } },
    ], { size: 11, color: C.ice, para: 5 });
    dimLine(s, 0.5, 4.55, 2.6, "1.6–1.7×", "faster per iteration, two cores", { color: C.sky, paper: C.navy, labelColor: C.ice2, size: 14 });
    dimLine(s, 3.6, 4.55, 2.6, "4 graphs", "iteration · intake/capture · export · session flow", { color: C.sky, paper: C.navy, labelColor: C.ice2, size: 14 });
    dimLine(s, 6.7, 4.55, 2.8, "~300 lines", "the runtime, no framework", { color: C.sky, paper: C.navy, labelColor: C.ice2, size: 14 });
    s.addNotes("Graph engineering, in the sense of state-based graphs with defined inputs and outputs where agents or algorithms operate in the nodes. Declaring what depends on what gave us parallelism, traces, resumable human steps and the critical path for free — and the session flow itself is a guarded state graph.");
  }

  // ---- 7. built on OpenAI -----------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "Two models, two jobs — on the Responses API.", { size: 26 });
    // diagram: designer loop (left) + critic (right)
    const bx = (x, y, w, h, head, sub, fill, line, headColor) => {
      s.addShape(pres.ShapeType.roundRect, { x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: line, width: 1 } });
      s.addText(head, { x: x + 0.1, y: y + 0.08, w: w - 0.2, h: 0.32, fontFace: FONT_H, fontSize: 12, bold: true, color: headColor || C.ink, isTextBox: true, margin: 0, valign: "middle" });
      s.addText(sub, { x: x + 0.1, y: y + 0.4, w: w - 0.2, h: h - 0.48, fontFace: FONT_B, fontSize: 9.5, color: C.ink2, isTextBox: true, margin: 0 });
    };
    bx(0.5, 1.35, 2.4, 1.35, "Designer · gpt-6-astra", "reasoning effort high · sandboxed file tools · iterate / ask_user / finish", C.blueSoft, C.blue, C.blue);
    bx(3.45, 1.35, 2.4, 1.35, "Checker + renderer", "OpenSCAD compile → mesh checks → blueprint sheets (images) — a dataflow graph, no model", "FFFFFF", C.rule);
    bx(6.4, 1.35, 3.1, 1.35, "Critic · gpt-6-astra, fresh context", "sees the spec, the check table and the drawings — never the code; JSON verdict: pass / revise / ask the user", C.passSoft, C.pass, C.pass);
    const arrow = (x, y, w, label) => {
      s.addShape(pres.ShapeType.line, { x, y, w, h: 0, line: { color: C.ink2, width: 1.25, endArrowType: "triangle" } });
      if (label) s.addText(label, { x: x - 0.2, y: y - 0.32, w: w + 0.4, h: 0.28, fontFace: FONT_M, fontSize: 8.5, color: C.ink3, align: "center", isTextBox: true, margin: 0 });
    };
    arrow(2.9, 2.0, 0.55, "part.scad");
    arrow(5.85, 2.0, 0.55, "sheets");
    // return arrow: checker -> designer (images back as tool output)
    s.addShape(pres.ShapeType.line, { x: 1.7, y: 2.7, w: 0, h: 0.35, line: { color: C.blue, width: 1.25, beginArrowType: "triangle" } });
    s.addShape(pres.ShapeType.line, { x: 1.7, y: 3.05, w: 2.95, h: 0, line: { color: C.blue, width: 1.25 } });
    s.addShape(pres.ShapeType.line, { x: 4.65, y: 2.7, w: 0, h: 0.35, line: { color: C.blue, width: 1.25 } });
    s.addText("check table + sheets return as the tool's output — text and images the model looks at", { x: 1.8, y: 3.08, w: 3.5, h: 0.3, fontFace: FONT_M, fontSize: 8.5, color: C.blue, isTextBox: true, margin: 0 });
    s.addShape(pres.ShapeType.line, { x: 7.95, y: 2.7, w: 0, h: 0.35, line: { color: C.pass, width: 1.25 } });
    s.addText("revise → the designer gets the verdict in a fresh tool loop", { x: 6.4, y: 3.08, w: 3.1, h: 0.3, fontFace: FONT_M, fontSize: 8.5, color: C.pass, isTextBox: true, margin: 0 });
    // feature chips
    const chips = ["function tools with image outputs", "previous_response_id — each sheet uploaded once", "reasoning.effort per role", "text.format json_object for critic & intake", "vision: intake + capture agent", "gpt-6-sol for the cheap passes", "stateless fallback with encrypted reasoning"];
    let cx = 0.5, cy = 3.65;
    chips.forEach((t) => {
      const w = Math.min(4.2, t.length * 0.075 + 0.35);
      if (cx + w > 9.5) { cx = 0.5; cy += 0.42; }
      s.addShape(pres.ShapeType.roundRect, { x: cx, y: cy, w, h: 0.32, rectRadius: 0.16, fill: { color: "FFFFFF" }, line: { color: C.rule, width: 0.75 } });
      s.addText(t, { x: cx, y: cy, w, h: 0.32, fontFace: FONT_M, fontSize: 9, color: C.ink2, align: "center", valign: "middle", isTextBox: true, margin: 0 });
      cx += w + 0.12;
    });
    footer(s, "kintsugi/agent/llm.py — one provider facade; a scripted provider runs the same loop for tests and demos");
    s.addNotes("Native to the Responses API: function tools whose outputs are images so the model looks at its own blueprints; previous_response_id so the growing pile of sheets is uploaded once; reasoning effort tuned per role; JSON mode for the structured passes; vision in intake and the capture agent. Two models, two jobs: the designer grades itself generously, so a fresh-context critic that never sees the code is worth the tokens.");
  }

  // ---- 8. proof ------------------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "Measured, not claimed.");
    const hdr = { fontFace: FONT_B, fontSize: 9, bold: true, color: C.ink, fill: { color: C.rule2 }, valign: "middle" };
    const cell = (t, o = {}) => ({ text: t, options: { fontFace: FONT_B, fontSize: 9, color: C.ink2, valign: "middle", ...o } });
    const P = (t) => cell(t, { color: C.pass, bold: true });
    const F = (t) => cell(t, { color: C.fail });
    const rows = [
      [{ text: "part (human reference)", options: hdr }, { text: "Kintsugi", options: hdr }, { text: "human", options: hdr }, { text: "iter.", options: hdr }, { text: "blind judge", options: hdr }],
      [cell("rack spacer"), P("pass"), P("pass"), cell("2"), cell("human 9 · kin 7")],
      [cell("cabinet plug"), P("pass"), F("fail: walls"), cell("1"), P("kintsugi 9 · human 6")],
      [cell("IKEA DOMBÅS handle"), P("pass"), P("pass"), cell("1"), P("kintsugi 9 · human 5")],
      [cell("trailer jack cap"), P("pass"), P("pass"), cell("2"), P("kintsugi 9 · human 7")],
      [cell("dishwasher rack hinge"), P("pass"), F("fail: topology, walls"), cell("4"), P("kintsugi 8 · human 6")],
    ];
    s.addTable(rows, { x: 0.5, y: 1.25, w: 5.7, colW: [1.7, 0.7, 1.5, 0.45, 1.35], rowH: 0.3, border: { type: "solid", color: C.rule2, pt: 0.5 }, fill: { color: "FFFFFF" } });
    s.addText("A/B: a spec written from each human part's own mating dimensions; Kintsugi designs from the spec alone, never sees the reference; both measured by the same checker, judged blind from the sheets. † runs on the previous model provider — being re-run on GPT-6.",
      { x: 0.5, y: 3.4, w: 5.7, h: 0.55, fontFace: FONT_B, fontSize: 8.5, color: C.ink3, isTextBox: true, margin: 0, italic: true });
    frame(s, 0.5, 4.05, 2.75, 0.9, IMG("ab_human_top.png"), { sizing: "cover" });
    frame(s, 3.45, 4.05, 2.75, 0.9, IMG("ab_kin_top.png"), { sizing: "cover" });
    mono(s, 0.5, 5.0, 2.75, 0.2, "human — trailer jack cap", { size: 8 });
    mono(s, 3.45, 5.0, 2.75, 0.2, "kintsugi — same spec, 2 iterations", { size: 8 });
    dimLine(s, 6.5, 1.35, 3.0, "5/5 pass · 4/5 preferred†", "A/B vs human-designed repair parts", { size: 11.5 });
    dimLine(s, 6.5, 2.35, 3.0, "4 / 5 caught †", "critic probe: injected defects invisible to the checks; control passes", { size: 13 });
    dimLine(s, 6.5, 3.45, 3.0, "96 tests", "no model needed: geometry ≤0.05 mm, interference ≤3 %, measurement ≤0.5 mm, API end to end", { size: 13 });
    dimLine(s, 6.5, 4.55, 3.0, "1·1·1·2·7", "iterations to converge, five bottle-handle runs †", { size: 13 });
    s.addNotes("Every number here has a file behind it in eval/reports and tests/. The dagger marks numbers produced on the previous model provider; they are re-run on GPT-6 before submission and replaced.");
  }

  // ---- 9. product ---------------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "A guide, not a console. A part you can change.", { size: 26 });
    frame(s, 0.5, 1.25, 5.85, 3.65, IMG("customizer.png"), { sizing: "cover" });
    const pts = [
      ["sliders", "Sliders that know their evidence", "A live 3D draft on each change; the measured value, its sources and its tolerance band on the rail; computed lengths turn red against the spec before you apply."],
      ["smartphone", "Six steps left, the engineer's view right", "Photos and readings from a phone on the same Wi-Fi; checks, code, spec and graphs on the desktop."],
      ["target", "Coupon before the part", "Three clearances in one small print; the one that slides on locks the fit."],
      ["help", "Demo mode for judges", "A scripted designer runs the whole flow in a minute without a key; the real thing needs only an OpenAI key in Settings."],
    ];
    pts.forEach(([ic, head, text], i) => {
      const y = 1.25 + i * 0.93;
      s.addImage({ data: icons[ic], x: 6.6, y: y + 0.03, w: 0.26, h: 0.26 });
      s.addText(head, { x: 6.95, y, w: 2.55, h: 0.32, fontFace: FONT_B, fontSize: 11.5, bold: true, color: C.ink, isTextBox: true, margin: 0 });
      s.addText(text, { x: 6.95, y: y + 0.32, w: 2.55, h: 0.58, fontFace: FONT_B, fontSize: 9.5, color: C.ink2, isTextBox: true, margin: 0 });
    });
    footer(s, "the Customize tab: a draft of the handle after two slider moves, the verified mesh ghosted behind it, the bottle neck in place, Apply & verify one click away");
    s.addNotes("Product thinking: the person does three things and looks at pictures. The guide never shows a blank screen — every stage has its one next action. And the finished part is not a file: it is a parametric designer like MakerWorld's, except every fit dimension shows where its number came from and warns before a check would fail.");
  }

  // ---- 10. potential (dark) ------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.navy);
    title(s, "After OFFGRID", { dark: true });
    const items = [
      ["cart", "Order the print when you have no printer", "Slant 3D Portals + Stripe from the export step — scoped, not built."],
      ["cloud", "Publish the parametric part with its spec", "MakerWorld / Printables: the next person with the same bottle gets it in one click, with the checks attached."],
      ["book", "Grow the standards base into an interface library", "Threads, snap profiles, appliance clips; intake matches against it with vision, one confirming photo instead of three."],
      ["users", "Repair-café and makerspace fleet mode", "One server, many phones, a queue of prints; multi-photo reconstruction and a printed measuring jig for what a flat sheet cannot reach."],
    ];
    items.forEach(([ic, head, text], i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 0.5 + col * 4.6, y = 1.3 + row * 1.55;
      s.addShape(pres.ShapeType.roundRect, { x, y, w: 4.4, h: 1.35, rectRadius: 0.06, fill: { color: C.navy2 }, line: { color: "2C4260", width: 0.75 } });
      s.addImage({ data: icons[ic], x: x + 0.18, y: y + 0.2, w: 0.34, h: 0.34 });
      s.addText(head, { x: x + 0.65, y: y + 0.15, w: 3.6, h: 0.42, fontFace: FONT_B, fontSize: 12.5, bold: true, color: C.ice, isTextBox: true, margin: 0, valign: "middle" });
      s.addText(text, { x: x + 0.65, y: y + 0.6, w: 3.6, h: 0.7, fontFace: FONT_B, fontSize: 10, color: C.ice2, isTextBox: true, margin: 0 });
    });
    dimLine(s, 0.5, 4.5, 9.0, "$10k of credits → 50 real broken objects × 5 runs each", "a published benchmark of convergence, cost and fit per model and reasoning effort — the harness already exists", { color: C.sky, paper: C.navy, labelColor: C.ice2, size: 13 });
    s.addNotes("Potential: the same loop is a general verified-CAD agent; the product path is ordering, publishing and a fleet. And the credits have an obvious use: the benchmark harness is built, it just needs objects and runs.");
  }

  // ---- 11. built in the open ------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.paper);
    title(s, "Built in the open, in the OFFGRID window.");
    const phases = ["toolchain\ncompile · checks · renderer · spec", "design loop\ncritic · policy · A/B eval", "measurement\nsheet · rectify · circle fit", "web workspace\nSSE · 3D · sheets · sliders", "OpenAI port\nResponses API · fake provider", "graph engineering\nruntime · evidence · capture loop"];
    phases.forEach((t, i) => {
      const x = 0.5 + i * 1.52;
      numCircle(s, x, 1.35, i + 1, { fill: i === 5 ? C.pass : C.blue });
      if (i < 5) s.addShape(pres.ShapeType.line, { x: x + 0.4, y: 1.52, w: 1.05, h: 0, line: { color: C.rule, width: 1, endArrowType: "triangle" } });
      const [h, sub] = t.split("\n");
      s.addText(h, { x: x - 0.1, y: 1.8, w: 1.5, h: 0.3, fontFace: FONT_B, fontSize: 11, bold: true, color: C.ink, isTextBox: true, margin: 0 });
      s.addText(sub, { x: x - 0.1, y: 2.1, w: 1.5, h: 0.6, fontFace: FONT_B, fontSize: 9, color: C.ink2, isTextBox: true, margin: 0 });
    });
    dimLine(s, 0.5, 3.05, 2.1, "36 commits", "a log, not a launch", { size: 13 });
    dimLine(s, 2.8, 3.05, 2.1, "18k lines", "Python · TypeScript · SCAD", { size: 13 });
    dimLine(s, 5.1, 3.05, 2.1, "96 tests", "green before every push", { size: 13 });
    dimLine(s, 7.4, 3.05, 2.1, "3 docs", "design rev B · hand-off · eval reports", { size: 13 });
    body(s, 0.5, 4.0, 5.6, 1.1, [
      { text: "Every stage has a headless test; the UI was walked end to end in a headless browser after each change. Rough edges are listed in the hand-off doc, not hidden.", options: { breakLine: true } },
      { text: "Solo build; AI coding assistants used throughout, as the rules allow. OpenSCAD, BOSL2, OpenCV, trimesh and the OpenAI SDK are the third-party pillars — all disclosed.", options: {} },
    ], { size: 10.5, para: 4 });
    s.addText("Thanks to HACK47 and the sponsors — OpenAI, whose Responses API runs every model call here, and Red Bull, who keep the house shipping.",
      { x: 6.3, y: 4.0, w: 3.2, h: 1.1, fontFace: FONT_B, fontSize: 10.5, color: C.ink2, isTextBox: true, margin: 0, italic: true });
    footer(s, "github.com/KrishGup/kintsugi · docs/design.html · docs/HANDOFF.md · eval/reports/");
    s.addNotes("The build order matters: the verification toolchain came first and was tested on known geometry before any model was involved. The model was the last thing added, not the first.");
  }

  // ---- 12. close (dark) ------------------------------------------------------------------------------------------
  {
    const s = pres.addSlide();
    bg(s, C.navy);
    s.addText("Photograph what broke.\nPrint what fits.", { x: 0.6, y: 1.4, w: 8.8, h: 1.7, fontFace: FONT_H, fontSize: 40, bold: true, color: C.ice, isTextBox: true, margin: 0, valign: "middle" });
    s.addText("Off-grid, the repair is the supply chain.", { x: 0.6, y: 3.15, w: 8.8, h: 0.5, fontFace: FONT_B, fontSize: 18, color: C.sky, isTextBox: true, margin: 0, italic: true });
    s.addText("github.com/KrishGup/kintsugi   ·   demo: [link]   ·   video: [link]", { x: 0.6, y: 4.1, w: 8.8, h: 0.4, fontFace: FONT_M, fontSize: 11, color: C.ice2, isTextBox: true, margin: 0 });
    s.addText("KINTSUGI · HACK47: OFFGRID · Krish Gupta", { x: 0.6, y: 4.75, w: 8.8, h: 0.35, fontFace: FONT_M, fontSize: 9, color: C.ice2, isTextBox: true, margin: 0, charSpacing: 2 });
    s.addNotes("Close on the object: the printed handle on the bottle. Kintsugi — photograph what broke, print what fits.");
  }

  const out = path.join(__dirname, "kintsugi-offgrid-pitch.pptx");
  await pres.writeFile({ fileName: out });
  console.log("wrote", out);
})();

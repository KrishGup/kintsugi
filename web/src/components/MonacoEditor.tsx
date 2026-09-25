// Monaco bundled locally (no CDN at runtime) with an OpenSCAD language definition and the Kintsugi themes.
import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor/editor.js";
import "monaco-editor/languages/definitions/yaml/register.js";
import EditorWorker from "monaco-editor/editor/editor.worker.js?worker";
import { useDark } from "../hooks";
import { Spinner } from "../ui";

declare global {
  interface Window {
    MonacoEnvironment?: { getWorker?: (workerId: string, label: string) => Worker | Promise<Worker> };
  }
}

if (!window.MonacoEnvironment) {
  window.MonacoEnvironment = { getWorker: () => new EditorWorker() };
}

const OPENSCAD: monaco.languages.IMonarchLanguage = {
  defaultToken: "",
  tokenPostfix: ".scad",
  keywords: ["module", "function", "include", "use", "let", "each", "for", "intersection_for", "if", "else", "true", "false", "undef", "echo", "assert"],
  builtins: [
    "cube", "sphere", "cylinder", "polyhedron", "square", "circle", "polygon", "text", "union", "difference", "intersection", "hull",
    "minkowski", "translate", "rotate", "scale", "mirror", "multmatrix", "color", "offset", "linear_extrude", "rotate_extrude",
    "projection", "surface", "import", "render", "children", "resize", "len", "str", "chr", "ord", "concat", "lookup", "search",
    "version", "version_num", "min", "max", "abs", "ceil", "floor", "round", "sqrt", "pow", "exp", "ln", "log", "sin", "cos", "tan",
    "asin", "acos", "atan", "atan2", "norm", "cross", "rands", "sign", "is_undef", "is_list", "is_num", "is_bool", "is_string",
    "is_function", "parent_module", "fl", "roundover", "chamfer", "attach", "anchor", "diff", "tag",
  ],
  symbols: /[=><!~?:&|+\-*/^%#]+/,
  tokenizer: {
    root: [
      [/\$[a-zA-Z_]\w*/, "variable.predefined"],
      [/[a-zA-Z_]\w*/, { cases: { "@keywords": "keyword", "@builtins": "type.identifier", "@default": "identifier" } }],
      { include: "@whitespace" },
      [/[{}()[\]]/, "@brackets"],
      [/@symbols/, "operator"],
      [/\d*\.\d+([eE][-+]?\d+)?/, "number.float"],
      [/\d+([eE][-+]?\d+)?/, "number"],
      [/"([^"\\]|\\.)*$/, "string.invalid"],
      [/"/, "string", "@string"],
      [/[;,.]/, "delimiter"],
    ],
    whitespace: [
      [/[ \t\r\n]+/, ""],
      [/\/\*\s*\[[^\]]*\]\s*\*\//, "comment.section"],
      [/\/\*/, "comment", "@comment"],
      [/\/\/\s*\[.*\]\s*$/, "comment.annotation"],
      [/\/\/.*$/, "comment"],
    ],
    comment: [
      [/[^/*]+/, "comment"],
      [/\*\//, "comment", "@pop"],
      [/[/*]/, "comment"],
    ],
    string: [
      [/[^\\"]+/, "string"],
      [/\\./, "string.escape"],
      [/"/, "string", "@pop"],
    ],
  },
};

let registered = false;
function ensureRegistered() {
  if (registered) return;
  registered = true;
  monaco.languages.register({ id: "openscad", extensions: [".scad"], aliases: ["OpenSCAD", "openscad"] });
  monaco.languages.setMonarchTokensProvider("openscad", OPENSCAD);
  monaco.languages.setLanguageConfiguration("openscad", {
    comments: { lineComment: "//", blockComment: ["/*", "*/"] },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"', notIn: ["string"] },
    ],
  });
  monaco.editor.defineTheme("kintsugi-light", {
    base: "vs",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7A8594", fontStyle: "italic" },
      { token: "comment.section", foreground: "1F4FA8", fontStyle: "bold" },
      { token: "comment.annotation", foreground: "9A6A08" },
      { token: "keyword", foreground: "1F4FA8", fontStyle: "bold" },
      { token: "type.identifier", foreground: "1F7A46" },
      { token: "number", foreground: "9A6A08" },
      { token: "number.float", foreground: "9A6A08" },
      { token: "string", foreground: "B8322A" },
      { token: "variable.predefined", foreground: "7A3FA8" },
      { token: "operator", foreground: "4A5563" },
      { token: "type", foreground: "1F4FA8" },
      { token: "string.yaml", foreground: "18212C" },
      { token: "number.yaml", foreground: "9A6A08" },
      { token: "keyword.yaml", foreground: "1F4FA8" },
    ],
    colors: {
      "editor.background": "#FAFBFC",
      "editor.foreground": "#18212C",
      "editorLineNumber.foreground": "#C9D0DA",
      "editorLineNumber.activeForeground": "#7A8594",
      "editor.lineHighlightBackground": "#F1F3F6",
      "editor.lineHighlightBorder": "#F1F3F6",
      "editor.selectionBackground": "#1F4FA82A",
      "editorIndentGuide.background1": "#E1E6EC",
      "editorIndentGuide.activeBackground1": "#C9D0DA",
      "editorGutter.background": "#FAFBFC",
      "editorCursor.foreground": "#1F4FA8",
      "editorWidget.background": "#FAFBFC",
      "editorWidget.border": "#C9D0DA",
      "scrollbarSlider.background": "#C9D0DA80",
    },
  });
  monaco.editor.defineTheme("kintsugi-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "7D8B9C", fontStyle: "italic" },
      { token: "comment.section", foreground: "8FB8FF", fontStyle: "bold" },
      { token: "comment.annotation", foreground: "E5B85C" },
      { token: "keyword", foreground: "8FB8FF", fontStyle: "bold" },
      { token: "type.identifier", foreground: "5CC98A" },
      { token: "number", foreground: "E5B85C" },
      { token: "number.float", foreground: "E5B85C" },
      { token: "string", foreground: "F08A80" },
      { token: "variable.predefined", foreground: "C9A6FF" },
      { token: "operator", foreground: "AFBCCB" },
      { token: "type", foreground: "8FB8FF" },
      { token: "string.yaml", foreground: "E4ECF6" },
      { token: "number.yaml", foreground: "E5B85C" },
      { token: "keyword.yaml", foreground: "8FB8FF" },
    ],
    colors: {
      "editor.background": "#132238",
      "editor.foreground": "#E4ECF6",
      "editorLineNumber.foreground": "#2C4260",
      "editorLineNumber.activeForeground": "#7D8B9C",
      "editor.lineHighlightBackground": "#0E1A2B",
      "editor.lineHighlightBorder": "#0E1A2B",
      "editor.selectionBackground": "#8FB8FF33",
      "editorIndentGuide.background1": "#1E3350",
      "editorIndentGuide.activeBackground1": "#2C4260",
      "editorGutter.background": "#132238",
      "editorCursor.foreground": "#8FB8FF",
      "editorWidget.background": "#132238",
      "editorWidget.border": "#2C4260",
      "scrollbarSlider.background": "#2C426080",
    },
  });
}

ensureRegistered();
loader.config({ monaco: monaco as unknown as Parameters<typeof loader.config>[0]["monaco"] });

export interface MonacoProps {
  value: string;
  onChange: (v: string) => void;
  language: "openscad" | "yaml";
  readOnly?: boolean;
}

export default function MonacoEditor({ value, onChange, language, readOnly }: MonacoProps) {
  const dark = useDark();
  return (
    <div className="monaco-host">
      <Editor
        height="100%"
        width="100%"
        language={language}
        value={value}
        theme={dark ? "kintsugi-dark" : "kintsugi-light"}
        onChange={(v) => onChange(v ?? "")}
        loading={<Spinner label="Loading editor…" />}
        options={{
          readOnly,
          minimap: { enabled: false },
          fontFamily: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
          fontSize: 12,
          lineHeight: 18,
          scrollBeyondLastLine: false,
          wordWrap: "on",
          tabSize: 4,
          renderLineHighlight: "line",
          automaticLayout: true,
          fixedOverflowWidgets: true,
          padding: { top: 8, bottom: 8 },
          scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
          fontLigatures: false,
          lineNumbersMinChars: 3,
          glyphMargin: false,
          folding: true,
          renderWhitespace: "none",
          smoothScrolling: true,
          occurrencesHighlight: "off",
          stickyScroll: { enabled: false },
        }}
      />
    </div>
  );
}

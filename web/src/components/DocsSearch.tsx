import { useEffect, useState } from "react";
import { api } from "../api";
import { Pill, Spinner } from "../ui";

interface Hit {
  name: string;
  kind: string;
  source: string;
  synopsis: string;
  usage: string[];
  includes: string;
}

/** A search box over the OpenSCAD + BOSL2 reference the designer uses, for people editing code. */
export default function DocsSearch({ onInsert }: { onInsert?: (text: string) => void }) {
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [hits, setHits] = useState<Hit[]>([]);
  const [text, setText] = useState("");
  const [guides, setGuides] = useState<Array<{ topic: string; about: string }>>([]);
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<{ guides: Array<{ topic: string; about: string }> }>("/api/docs")
      .then((r) => setGuides(r.guides || []))
      .catch(() => setGuides([]));
  }, []);

  const search = async (name?: string) => {
    const query = (name || q).trim();
    if (!query) return;
    setBusy(true);
    try {
      const r = await api.get<{ text: string; hits: Hit[] }>(`/api/docs?${name ? `name=${encodeURIComponent(name)}` : `q=${encodeURIComponent(query)}`}&limit=6`);
      setHits(r.hits || []);
      setText(r.text || "");
      setOpen(name || null);
    } catch {
      setHits([]);
      setText("");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="docs">
      <div className="row">
        <input
          className="input grow"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Reference: e.g. tube wall, threaded nut, offset, rounding edge mask…"
          onKeyDown={(e) => {
            if (e.key === "Enter") search();
          }}
          aria-label="Search the OpenSCAD reference"
        />
        <button className="btn btn-sm" onClick={() => search()} disabled={busy || !q.trim()}>
          {busy ? <Spinner size={10} /> : "Search"}
        </button>
      </div>
      <div className="row-wrap small" style={{ marginTop: 4 }}>
        <span className="dim">guides:</span>
        {guides.map((g) => (
          <a key={g.topic} href={`/api/guides/${g.topic}`} target="_blank" rel="noreferrer" title={g.about}>
            {g.topic}
          </a>
        ))}
      </div>
      {hits.length > 0 && (
        <div className="docs-hits">
          {hits.map((h) => (
            <div key={`${h.source}:${h.name}`} className={`docs-hit${open === h.name ? " open" : ""}`}>
              <div className="row-wrap">
                <button className="btn btn-ghost btn-xs mono" onClick={() => search(h.name)} title="full entry">
                  {h.name}
                </button>
                <Pill tone={h.source === "openscad" ? "blue" : "neutral"}>{h.source === "openscad" ? "builtin" : h.source.replace(".scad", "")}</Pill>
                <span className="dim">{h.synopsis}</span>
                {onInsert && h.usage[0] && (
                  <button className="btn btn-ghost btn-xs" onClick={() => onInsert(h.usage[0])} title="insert the usage line at the cursor">
                    insert
                  </button>
                )}
              </div>
              {h.usage[0] && <div className="mono small dim">{h.usage[0]}</div>}
            </div>
          ))}
        </div>
      )}
      {open && text && <pre className="md-code docs-full">{text}</pre>}
    </div>
  );
}

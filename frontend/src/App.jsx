import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api.js";
import { UploadZone, ImageRow, DetailPanel, Summary } from "./components.jsx";

const FILTERS = [
  ["", "All"],
  ["ACCEPTABLE", "Acceptable"],
  ["DEGRADED", "Degraded"],
  ["DEFECTIVE", "Defective"],
];

export default function App() {
  const [items, setItems] = useState([]);
  const [stats, setStats] = useState(null);
  const [storageMb, setStorageMb] = useState(null);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState(null);
  const [queue, setQueue] = useState([]); // {file, name, state: 'pending'|'working'|'error', error?}
  const [loadError, setLoadError] = useState("");
  const pending = useRef([]);
  const busy = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const [list, s, stor] = await Promise.all([api.list(filter), api.stats(), api.storage()]);
      setItems(list.items);
      setStats(s);
      setStorageMb(stor.total_mb);
      setLoadError("");
    } catch (e) {
      setLoadError(e.message);
    }
  }, [filter]);

  useEffect(() => { refresh(); }, [refresh]);

  const patch = (entry, change) =>
    setQueue((q) => q.map((x) => (x === entry ? { ...x, ...change } : x)));

  // Files go to the server one at a time so each queue row shows its own progress.
  async function drain() {
    if (busy.current) return;
    busy.current = true;
    while (pending.current.length) {
      const entry = pending.current.shift();
      patch(entry, { state: "working" });
      try {
        const res = await api.upload(entry.file);
        if (res.errors?.length) throw new Error(res.errors[0].error);
        setQueue((q) => q.filter((x) => x !== entry && x.file !== entry.file));
        await refresh();
      } catch (e) {
        setQueue((q) => q.map((x) => (x.file === entry.file ? { ...x, state: "error", error: e.message } : x)));
      }
    }
    busy.current = false;
  }

  function handleFiles(files) {
    const entries = files.map((f) => ({ file: f, name: f.name, state: "pending" }));
    setQueue((q) => [...q, ...entries]);
    pending.current.push(...entries);
    drain();
  }

  async function handleDelete(id) {
    await api.remove(id);
    setSelected(null);
    refresh();
  }

  return (
    <div className="shell">
      <header className="masthead">
        <h1>Image quality inspector</h1>
        <p>Upload photos to check them for blur, noise and bad exposure. Every result is saved.</p>
      </header>

      <Summary stats={stats} storageMb={storageMb} />
      <UploadZone onFiles={handleFiles} queue={queue}
        onDismiss={(file) => setQueue((q) => q.filter((x) => x.file !== file))} />

      <section className="results" aria-labelledby="results-h">
        <div className="results-head">
          <h2 id="results-h">Results</h2>
          <div className="tabs" role="tablist">
            {FILTERS.map(([value, text]) => (
              <button key={value} role="tab" aria-selected={filter === value}
                className={filter === value ? "tab on" : "tab"} onClick={() => setFilter(value)}>
                {text}
              </button>
            ))}
          </div>
        </div>

        {loadError && <p className="notice error">Cannot reach the server: {loadError}</p>}
        {!loadError && items.length === 0 && (
          <p className="empty">
            {filter ? "No images with this verdict yet." : "No images yet. Drop a few photos above to see how they score."}
          </p>
        )}
        <ul className="rows">
          {items.map((it) => (
            <ImageRow key={it.id} item={it} onOpen={() => setSelected(it)} />
          ))}
        </ul>
      </section>

      {selected && (
        <DetailPanel item={selected} onClose={() => setSelected(null)} onDelete={() => handleDelete(selected.id)} />
      )}
    </div>
  );
}

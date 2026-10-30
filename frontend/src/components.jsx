import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

const VERDICT = {
  ACCEPTABLE: { text: "Acceptable", cls: "ok" },
  DEGRADED: { text: "Degraded", cls: "warn" },
  DEFECTIVE: { text: "Defective", cls: "bad" },
};

const ISSUE_TEXT = {
  blur: "Blur",
  noise: "Noise",
  underexposure: "Too dark",
  overexposure: "Too bright",
};

const ISSUE_HELP = {
  blur: "Edges are soft. Retake with steadier hands or better focus.",
  noise: "Grain is visible. Use more light or a lower ISO.",
  underexposure: "Large areas are near black. Add light or raise exposure.",
  overexposure: "Large areas are blown out. Lower exposure or avoid direct light.",
};

const fmtBytes = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.round(n / 1024)} KB`);

export function Summary({ stats, storageMb }) {
  if (!stats) return <div className="summary" aria-hidden="true" />;
  const { counts, total, average_score } = stats;
  return (
    <section className="summary" aria-label="Summary of all images">
      <div className="avg">
        <span className="avg-num">{average_score ?? "–"}</span>
        <span className="avg-label">average score across {total} {total === 1 ? "image" : "images"}</span>
      </div>
      <div className="split" role="img"
        aria-label={`${counts.ACCEPTABLE} acceptable, ${counts.DEGRADED} degraded, ${counts.DEFECTIVE} defective`}>
        {total > 0 && ["ACCEPTABLE", "DEGRADED", "DEFECTIVE"].map((k) =>
          counts[k] > 0 && <span key={k} className={`seg ${VERDICT[k].cls}`} style={{ flexGrow: counts[k] }}>{counts[k]}</span>
        )}
      </div>
      {storageMb !== null && (
        <p className="storage-info" aria-label={`Storage used: ${storageMb} MB`}>
          💾 <strong>{storageMb} MB</strong> stored
        </p>
      )}
    </section>
  );
}

export function UploadZone({ onFiles, queue, onDismiss }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);

  const pick = (list) => {
    const files = [...list].filter((f) => f.type.startsWith("image/"));
    if (files.length) onFiles(files);
  };

  return (
    <section aria-label="Upload images">
      <div
        className={over ? "drop over" : "drop"}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer.files); }}
      >
        <p className="drop-title">Drop images here</p>
        <p className="drop-sub">JPEG, PNG, WebP, BMP or TIFF, up to 10 MB each</p>
        <button className="btn" onClick={() => input.current.click()}>Choose files</button>
        <input ref={input} type="file" accept="image/*" multiple hidden
          onChange={(e) => { pick(e.target.files); e.target.value = ""; }} />
      </div>

      {queue.length > 0 && (
        <ul className="queue" aria-live="polite">
          {queue.map((q, i) => (
            <li key={i} className={q.state === "error" ? "q error" : "q"}>
              <span className="q-name">{q.name}</span>
              <span className="q-state">
                {q.state === "pending" && "Waiting"}
                {q.state === "working" && "Analysing…"}
                {q.state === "error" && q.error}
              </span>
              {q.state === "error" && <button className="link" onClick={() => onDismiss(q.file)}>Dismiss</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Verdict({ label }) {
  return <span className={`verdict ${VERDICT[label].cls}`}>{VERDICT[label].text}</span>;
}

export function ImageRow({ item, onOpen }) {
  const v = VERDICT[item.quality_label];
  return (
    <li>
      <button className="row" onClick={onOpen}>
        <img src={api.thumbUrl(item.id)} alt="" loading="lazy" />
        <span className="row-main">
          <span className="row-name">{item.filename}</span>
          <span className="row-meta">{item.width}×{item.height}, {fmtBytes(item.size_bytes)}</span>
          <span className="chips">
            {item.issues.length === 0 && <span className="chip clean">No issues found</span>}
            {item.issues.map((is, i) => (
              <span key={i} className={`chip ${is.severity}`}>{ISSUE_TEXT[is.type]} ({is.severity})</span>
            ))}
          </span>
        </span>
        <span className="row-score">
          <span className={`score ${v.cls}`}>{item.quality_score}</span>
          <Verdict label={item.quality_label} />
        </span>
      </button>
    </li>
  );
}

export function DetailPanel({ item, onClose, onDelete }) {
  const [confirm, setConfirm] = useState(false);
  const m = item.metrics;

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const metrics = [
    ["Quality (MUSIQ)", m.musiq_score.toFixed(1), "Higher is better, 0–100"],
    ["Naturalness (BRISQUE)", m.brisque_score.toFixed(1), "Lower is better"],
    ["Sharpness", m.sharpness.toFixed(1), "Below 80 is blurry"],
    ["Noise", m.noise.toFixed(2), "Above 5 is grainy"],
    ["Brightness", m.brightness.toFixed(0), "Average, 0–255"],
    ["Dark pixels", `${m.dark_pixel_percentage.toFixed(1)}%`, "Over 30% is underexposed"],
    ["Blown-out pixels", `${m.bright_pixel_percentage.toFixed(1)}%`, "Over 30% is overexposed"],
  ];

  return (
    <div className="scrim" onClick={onClose}>
      <aside className="panel" role="dialog" aria-modal="true" aria-label={`Details for ${item.filename}`}
        onClick={(e) => e.stopPropagation()}>
        <div className="panel-top">
          <h3>{item.filename}</h3>
          <button className="link" onClick={onClose}>Close</button>
        </div>

        <img className="preview" src={api.fileUrl(item.id)} alt={item.filename} />

        <div className="panel-score">
          <span className={`score big ${VERDICT[item.quality_label].cls}`}>{item.quality_score}</span>
          <div>
            <Verdict label={item.quality_label} />
            <p className="muted">out of 100. Starts from the MUSIQ score, minus a penalty for each issue.</p>
          </div>
        </div>

        <h4>Issues</h4>
        {item.issues.length === 0 ? (
          <p className="muted">None of the blur, noise or exposure checks fired.</p>
        ) : (
          <ul className="issues">
            {item.issues.map((is, i) => (
              <li key={i}>
                <div className="issue-head">
                  <strong>{ISSUE_TEXT[is.type]}</strong>
                  <span className={`chip ${is.severity}`}>{is.severity}</span>
                  <span className="muted">{Math.round(is.confidence * 100)}% confidence</span>
                </div>
                <div className="bar"><span style={{ width: `${is.confidence * 100}%` }} /></div>
                <p className="muted">{ISSUE_HELP[is.type]}</p>
              </li>
            ))}
          </ul>
        )}

        <h4>Measurements</h4>
        <dl className="metrics">
          {metrics.map(([k, v, hint]) => (
            <div key={k}><dt>{k}<small>{hint}</small></dt><dd>{v}</dd></div>
          ))}
        </dl>

        <div className="panel-actions">
          <a className="btn ghost" href={api.fileUrl(item.id)} download={item.filename}>Download original</a>
          {confirm ? (
            <>
              <button className="btn danger" onClick={onDelete}>Delete permanently</button>
              <button className="link" onClick={() => setConfirm(false)}>Keep</button>
            </>
          ) : (
            <button className="btn ghost" onClick={() => setConfirm(true)}>Delete</button>
          )}
        </div>
      </aside>
    </div>
  );
}

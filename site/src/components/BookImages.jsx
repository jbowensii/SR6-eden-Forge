import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { getBookImages } from "../api.js";

// Gallery of every graphic extracted from the item's source book (top-level
// renders + the unpaired _inbox pile). Picking one assigns it as the item's
// render. This surfaces the extracted art that otherwise sits invisible on disk.
export default function BookImages({ book, onPick, onClose }) {
  const [images, setImages] = useState(null);

  useEffect(() => {
    getBookImages(book).then((r) => setImages(r.images)).catch(() => setImages([]));
  }, [book]);

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal book-images" onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>Extracted graphics · {book}</h3>
          <button className="ghost" onClick={onClose}>Close</button>
        </header>
        {images === null ? (
          <p className="muted">Loading…</p>
        ) : images.length === 0 ? (
          <p className="muted">No graphics were extracted from this book.</p>
        ) : (
          <div className="img-grid">
            {images.map((i) => (
              <button key={i.path} className="img-cell" title={i.label} onClick={() => onPick(i.path)}>
                <img src={`/assets/${i.path}`} alt="" loading="lazy" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
}

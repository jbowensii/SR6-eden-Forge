import React from "react";

export default function Preview({ doc }) {
  return (
    <div className="preview">
      <h3>Foundry document</h3>
      <pre>{JSON.stringify(doc, null, 2)}</pre>
    </div>
  );
}

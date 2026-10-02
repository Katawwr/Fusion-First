export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// The report card as JSON, for scripts and CI.
export function downloadJson(value, filename) {
  saveBlob(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }), filename);
}

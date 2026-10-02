// The link is attached and the URL revoked later: Safari ignores a detached link and can cancel a
// download whose URL is revoked during the click.
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// The report card as JSON, for scripts and CI.
export function downloadJson(value, filename) {
  saveBlob(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }), filename);
}

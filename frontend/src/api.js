async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d.error || d.msg).join("; ");
    } catch { /* non-JSON error body */ }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  list:    (label) => request(`/api/images?limit=200${label ? `&label=${label}` : ""}`),
  stats:   ()      => request("/api/stats"),
  storage: ()      => request("/api/storage"),
  upload: (file) => {
    const body = new FormData();
    body.append("files", file);
    return request("/api/images", { method: "POST", body });
  },
  remove:   (id) => request(`/api/images/${id}`, { method: "DELETE" }),
  thumbUrl: (id) => `/api/images/${id}/thumbnail`,
  fileUrl:  (id) => `/api/images/${id}/file`,
};

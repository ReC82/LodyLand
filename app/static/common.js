/* File: static/common.js
   Purpose: Global helpers shared by GAME_UI scripts
*/

function $(id) {
  return document.getElementById(id);
}

async function http(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: body ? JSON.stringify(body) : undefined,
  });

  // 204 / empty responses safety
  const ct = res.headers.get("content-type") || "";
  const isJson = ct.includes("application/json");

  let data = null;
  if (res.status !== 204) {
    data = isJson ? await res.json().catch(() => null) : await res.text().catch(() => "");
  }

  return { ok: res.ok, status: res.status, data };
}


// explicit global exposure
window.$ = $;
window.http = http;

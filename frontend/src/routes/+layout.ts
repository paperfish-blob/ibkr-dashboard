// A pure client-rendered SPA, prerendered to static HTML per route.
//
// prerender emits real index.html / transactions.html files, so FastAPI can
// serve deep links from a plain static mount with no catch-all route.
// ssr = false keeps Chart.js and every document/window touch out of the
// build-time render in one line.
export const ssr = false;
export const prerender = true;

const NOVA_API_BASE = "http://localhost:8000";

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "NOVA_FETCH") return;

  const path = message.path || "/";
  const url = path.startsWith("http") ? path : `${NOVA_API_BASE}${path}`;
  const headers = message.headers || {};
  const init = {
    method: message.method || "GET",
    headers
  };
  if (message.body != null && message.body !== "") {
    init.body = typeof message.body === "string" ? message.body : JSON.stringify(message.body);
  }

  fetch(url, init)
    .then(async (res) => {
      const body = await res.text();
      sendResponse({
        ok: res.ok,
        status: res.status,
        body
      });
    })
    .catch((error) => {
      sendResponse({
        ok: false,
        status: 0,
        error: String(error && error.message ? error.message : error)
      });
    });

  return true;
});

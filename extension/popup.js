const dot = document.getElementById("dot");
const statusText = document.getElementById("status-text");
const openBtn = document.getElementById("open-localhost");
const NOVA_APP_URL = "http://localhost:8000";

fetch(`${NOVA_APP_URL}/api/health`)
  .then((res) => {
    if (!res.ok) throw new Error("offline");
    dot.classList.add("online");
    statusText.textContent = "Connected to localhost:8000";
  })
  .catch(() => {
    dot.classList.remove("online");
    statusText.textContent = "Backend is not running";
  });

openBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: `${NOVA_APP_URL}/` });
});

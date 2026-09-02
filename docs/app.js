const root = document.documentElement;
const filterLinks = [...document.querySelectorAll("[data-filter]")];
const cards = [...document.querySelectorAll("[data-card]")];
const clearButton = document.querySelector("[data-clear-filter]");
const traceMessage = document.querySelector("[data-trace-message]");
const themeToggle = document.querySelector(".theme-toggle");

const filterNames = {
  systems: "Linux Systems",
  virtualization: "Virtualization",
  cloud: "Containers & Cloud Native",
  vibe: "Vibe Coding method",
};

let activeFilter = "";

function setFilter(nextFilter) {
  activeFilter = activeFilter === nextFilter ? "" : nextFilter;

  filterLinks.forEach((link) => {
    const isActive = link.dataset.filter === activeFilter;
    link.classList.toggle("is-active", isActive);
    link.setAttribute("aria-current", isActive ? "true" : "false");
  });

  cards.forEach((card) => {
    const domains = (card.dataset.domains || "").split(/\s+/);
    const isRelated = Boolean(activeFilter) && domains.includes(activeFilter);
    card.classList.toggle("is-related", isRelated);
    card.classList.toggle("is-muted", Boolean(activeFilter) && !isRelated);
  });

  if (traceMessage) {
    traceMessage.textContent = activeFilter
      ? `Tracing ${filterNames[activeFilter]} through the selected work. Nothing is hidden.`
      : "Select a layer to trace it through the work below.";
  }
}

filterLinks.forEach((link) => {
  link.addEventListener("click", (event) => {
    event.preventDefault();
    setFilter(link.dataset.filter);
    document.querySelector(link.hash)?.scrollIntoView({ block: "start" });
  });
});

clearButton?.addEventListener("click", () => {
  if (activeFilter) setFilter(activeFilter);
});

function setTheme(theme) {
  root.dataset.theme = theme;
  themeToggle?.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);

  try {
    localStorage.setItem("profile-prototype-theme", theme);
  } catch {
    // The prototype still works when storage is blocked.
  }
}

let savedTheme = "";
try {
  savedTheme = localStorage.getItem("profile-prototype-theme") || "";
} catch {
  savedTheme = "";
}

if (savedTheme === "dark" || savedTheme === "light") {
  setTheme(savedTheme);
}

themeToggle?.addEventListener("click", () => {
  setTheme(root.dataset.theme === "light" ? "dark" : "light");
});

const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

function updateAmbient(event) {
  if (reduceMotion.matches) return;
  const x = `${Math.round((event.clientX / window.innerWidth) * 100)}%`;
  const y = `${Math.round((event.clientY / window.innerHeight) * 100)}%`;
  root.style.setProperty("--mx", x);
  root.style.setProperty("--my", y);
}

window.addEventListener("pointermove", updateAmbient, { passive: true });

if (new URLSearchParams(window.location.search).has("audit")) {
  const rect = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const bounds = element.getBoundingClientRect();
    return {
      left: Math.round(bounds.left),
      right: Math.round(bounds.right),
      width: Math.round(bounds.width),
      scrollWidth: element.scrollWidth,
      clientWidth: element.clientWidth,
    };
  };

  root.dataset.layoutAudit = JSON.stringify({
    innerWidth: window.innerWidth,
    documentClientWidth: root.clientWidth,
    documentScrollWidth: root.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    header: rect(".site-header"),
    hero: rect(".hero"),
    heroCopy: rect(".hero-copy"),
    title: rect("h1"),
    identity: rect(".identity-row"),
    cutaway: rect(".hero-cutaway"),
  });
}

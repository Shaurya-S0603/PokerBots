(() => {
  const root = document.getElementById("effect");
  if (!root || root.dataset.reduced === "true" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const amount = root.dataset.kind === "win" ? 22 : 8;
  for (let i = 0; i < amount; i++) {
    const dot = document.createElement("span");
    dot.className = "spark";
    const angle = (Math.PI * 2 * i) / amount;
    const radius = root.dataset.kind === "win" ? 150 : 65;
    dot.style.setProperty("--dx", `${Math.cos(angle) * radius}px`);
    dot.style.setProperty("--dy", `${Math.sin(angle) * 27}px`);
    dot.style.left = `${50 + Math.sin(angle) * 7}%`;
    dot.style.top = "47%";
    if (i % 3 === 0) dot.style.background = "#64e4cb";
    root.appendChild(dot);
  }
})();

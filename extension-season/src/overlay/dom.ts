// Small DOM helpers. Injection is deliberately confined to this folder so a Yahoo
// markup change has one place to be fixed.

export const SHAMS_ATTR = "data-shams";

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  options: { class?: string; text?: string; title?: string; attrs?: Record<string, string> } = {},
  children: (Node | null)[] = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (options.class) node.className = options.class;
  if (options.text !== undefined) node.textContent = options.text;
  if (options.title) node.title = options.title;
  for (const [key, value] of Object.entries(options.attrs ?? {})) node.setAttribute(key, value);
  for (const child of children) if (child) node.appendChild(child);
  return node;
}

/** Remove a previously injected node so re-rendering never stacks duplicates. */
export function clearInjected(marker: string): void {
  document.querySelectorAll(`[${SHAMS_ATTR}="${marker}"]`).forEach((node) => node.remove());
}

export function formatStat(value: number, isPercentage: boolean): string {
  if (!Number.isFinite(value)) return "–";
  if (isPercentage) return value.toFixed(3).replace(/^0/, "");
  if (Math.abs(value) >= 100) return value.toFixed(0);
  return value.toFixed(1);
}

export function gamesClass(remaining: number): string {
  if (remaining <= 0) return "shams-games shams-games-none";
  if (remaining <= 2) return "shams-games shams-games-thin";
  if (remaining >= 4) return "shams-games shams-games-heavy";
  return "shams-games shams-games-ok";
}

/** Wait for an element Yahoo renders after page load, then hand it over. */
export function whenPresent(selector: () => Element | null, timeoutMs = 10000): Promise<Element | null> {
  const immediate = selector();
  if (immediate) return Promise.resolve(immediate);

  return new Promise((resolve) => {
    const observer = new MutationObserver(() => {
      const found = selector();
      if (found) {
        observer.disconnect();
        clearTimeout(timer);
        resolve(found);
      }
    });
    const timer = setTimeout(() => {
      observer.disconnect();
      resolve(null);
    }, timeoutMs);
    observer.observe(document.body, { childList: true, subtree: true });
  });
}

export function statusBadge(state: "loading" | "ready" | "error", detail: string): HTMLElement {
  return el("span", { class: `shams-badge shams-badge-${state}`, text: detail, title: detail });
}

/** A row of buttons acting as one choice, the active one highlighted. */
export function toggle<T extends string>(
  options: [T, string][],
  active: T,
  onChange: (value: T) => void,
): HTMLElement {
  return el(
    "span",
    { class: "shams-tabs" },
    options.map(([value, label]) => {
      const button = el("button", {
        class: value === active ? "shams-button shams-button-active" : "shams-button",
        text: label,
      });
      button.addEventListener("click", () => onChange(value));
      return button;
    }),
  );
}

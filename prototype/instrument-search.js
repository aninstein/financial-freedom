import { request } from "./api.js";
import { esc } from "./ui.js";

const VALID_ID = /^(CN|HK|US|FUND|GOLD):[^:]+$/i;
let timer;
let controller;
let activeInput;
let activeIndex = -1;

function panel(input) {
  return input.closest(".instrument-search")?.querySelector(".instrument-results");
}

function close(input = activeInput) {
  clearTimeout(timer);
  controller?.abort();
  const results = input && panel(input);
  if (results) {
    results.hidden = true;
    results.innerHTML = "";
  }
  input?.setAttribute("aria-expanded", "false");
  input?.removeAttribute("aria-activedescendant");
  activeIndex = -1;
}

function choose(input, instrument) {
  input.value = instrument.instrument_id;
  input.dataset.instrumentName = instrument.name || "";
  input.dispatchEvent(new Event("input", { bubbles: true }));
  close(input);
  if (input.dataset.instrumentPicker === "navigate") {
    location.hash = "/stocks/" + encodeURIComponent(instrument.instrument_id);
  } else {
    input.focus();
  }
}

function show(input, instruments, message = "") {
  const results = panel(input);
  if (!results) return;
  results.innerHTML = instruments.length
    ? instruments.map((item, index) => `<button type="button" class="instrument-option" role="option" id="${esc(input.id)}-option-${index}" data-index="${index}" aria-selected="false"><strong>${esc(item.name || item.instrument_id)}</strong><small>${esc(item.instrument_id)} · ${esc(item.market)}</small></button>`).join("")
    : `<p class="instrument-empty">${esc(message || "未找到匹配的标的")}</p>`;
  results.hidden = false;
  results._instruments = instruments;
  input.setAttribute("aria-expanded", "true");
  activeInput = input;
  activeIndex = -1;
}

async function search(query, signal) {
  const data = await request(`/instruments/search?q=${encodeURIComponent(query)}&limit=10`, { signal });
  return data.instruments || [];
}

function schedule(input) {
  close(activeInput);
  const query = input.value.trim();
  if (!query || VALID_ID.test(query)) return;
  controller = new AbortController();
  const current = controller;
  timer = setTimeout(async () => {
    try {
      const matches = await search(query, current.signal);
      if (current.signal.aborted || !input.isConnected || input.value.trim() !== query) return;
      show(input, matches);
    } catch (error) {
      if (!current.signal.aborted && input.isConnected) show(input, [], error.message);
    }
  }, 180);
}

export async function resolveInstrumentText(value) {
  const query = value.trim();
  if (!query) throw new Error("请输入股票名称或代码");
  if (VALID_ID.test(query)) {
    const [market, ...parts] = query.split(":");
    const symbol = parts.join(":").toUpperCase();
    return `${market.toUpperCase()}:${market.toUpperCase() === "HK" && /^\d+$/.test(symbol) ? symbol.padStart(5, "0") : symbol}`;
  }
  const matches = await search(query);
  const normalized = query.toLocaleLowerCase();
  const exact = matches.filter((item) =>
    [item.name, item.symbol, item.instrument_id].some((value) => value?.toLocaleLowerCase() === normalized));
  const candidates = exact.length ? exact : matches;
  if (candidates.length === 1) return candidates[0].instrument_id;
  if (!candidates.length) throw new Error("未找到匹配的标的，请检查名称或代码");
  throw new Error("找到多个匹配标的，请从下拉列表选择具体股票");
}

export async function resolveInstrument(input) {
  try {
    const id = await resolveInstrumentText(input.value);
    input.value = id;
    close(input);
    return id;
  } catch (error) {
    if (input.value.trim() && !VALID_ID.test(input.value.trim())) {
      const matches = await search(input.value.trim());
      const normalized = input.value.trim().toLocaleLowerCase();
      const exact = matches.filter((item) =>
        [item.name, item.symbol, item.instrument_id].some((value) => value?.toLocaleLowerCase() === normalized));
      show(input, exact.length ? exact : matches, error.message);
    }
    throw error;
  }
}

export function installInstrumentSearch() {
  window.addEventListener("hashchange", () => close());
  document.addEventListener("input", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches("[data-instrument-picker]")) return;
    delete input.dataset.instrumentName;
    if (!event.isComposing) schedule(input);
  });
  document.addEventListener("compositionend", (event) => {
    if (event.target instanceof HTMLInputElement && event.target.matches("[data-instrument-picker]")) schedule(event.target);
  });
  document.addEventListener("keydown", (event) => {
    const input = event.target;
    if (!(input instanceof HTMLInputElement) || !input.matches("[data-instrument-picker]") || event.isComposing) return;
    const results = panel(input);
    if (!results || results.hidden) return;
    const options = [...results.querySelectorAll(".instrument-option")];
    if (event.key === "Escape") {
      close(input);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = (activeIndex + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      options.forEach((option, index) => option.setAttribute("aria-selected", String(index === activeIndex)));
      input.setAttribute("aria-activedescendant", options[activeIndex]?.id || "");
    } else if (event.key === "Enter" && activeIndex >= 0) {
      event.preventDefault();
      choose(input, results._instruments[activeIndex]);
    }
  });
  document.addEventListener("pointerdown", (event) => {
    const option = event.target.closest?.(".instrument-option");
    if (option) {
      event.preventDefault();
      const results = option.closest(".instrument-results");
      const input = results.closest(".instrument-search").querySelector("[data-instrument-picker]");
      choose(input, results._instruments[Number(option.dataset.index)]);
    } else if (activeInput && !event.target.closest?.(".instrument-search")) {
      close();
    }
  });
}

/**
 * "Get the app": Android/Chrome install prompt capture + iPhone/iPad detection.
 * Pure helpers take explicit env objects so they can be tested without a browser.
 */
let deferredPrompt = null;
const listeners = new Set();

function notify() { listeners.forEach((fn) => fn(deferredPrompt)); }

/** Call once at startup, before React mounts, so the early event is never missed. */
export function captureInstallPrompt(target = globalThis.window) {
  if (!target?.addEventListener) return;
  target.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault(); // we show our own button instead of the mini-infobar
    deferredPrompt = event;
    notify();
  });
  target.addEventListener("appinstalled", () => { deferredPrompt = null; notify(); });
}

export function onInstallPromptChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function getDeferredPrompt() { return deferredPrompt; }

/** Show the browser's own install dialog. Returns "accepted" | "dismissed" | "unavailable". */
export async function promptInstall() {
  const event = deferredPrompt;
  if (!event) return "unavailable";
  deferredPrompt = null;
  notify();
  try {
    await event.prompt();
    const choice = await event.userChoice;
    return choice?.outcome === "accepted" ? "accepted" : "dismissed";
  } catch {
    return "dismissed";
  }
}

export function isStandalone({ matchMedia = globalThis.window?.matchMedia?.bind(globalThis.window), navigator: nav = globalThis.navigator } = {}) {
  return Boolean(matchMedia?.("(display-mode: standalone)")?.matches || nav?.standalone === true);
}

export function isIos({ userAgent = globalThis.navigator?.userAgent || "", platform = globalThis.navigator?.platform || "", maxTouchPoints = globalThis.navigator?.maxTouchPoints || 0 } = {}) {
  return /iPad|iPhone|iPod/.test(userAgent) || (platform === "MacIntel" && maxTouchPoints > 1);
}

/** Which "Get the app" experience to show: "hidden" | "prompt" | "ios". */
export function installMode({ standalone, ios, hasPrompt }) {
  if (standalone) return "hidden";
  if (hasPrompt) return "prompt";
  if (ios) return "ios";
  return "hidden";
}

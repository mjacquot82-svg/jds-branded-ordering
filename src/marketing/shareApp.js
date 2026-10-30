/** "Share your app": native share sheet when available, otherwise copy the link. */
export async function shareApp({ url, name }, { nav = globalThis.navigator } = {}) {
  const data = { title: `${name} app`, text: `Order ahead from ${name} — get our app:`, url };
  if (nav?.share && (!nav.canShare || nav.canShare(data))) {
    try {
      await nav.share(data);
      return "shared";
    } catch (error) {
      if (error?.name === "AbortError") return "cancelled";
    }
  }
  try {
    await nav.clipboard.writeText(url);
    return "copied";
  } catch {
    return "failed";
  }
}

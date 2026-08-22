export function installedAppName(displayName) {
  return displayName.trim().slice(0, 30) || "Order";
}

export function withInstalledAppDefaults(config) {
  const pwa = config.pwa || {};
  const next = { ...pwa };
  if (!pwa.shortName || pwa.shortName === "Order" || (pwa.shortName === "Your business" && config.displayName !== "Your business")) next.shortName = installedAppName(config.displayName);
  if (!pwa.themeColor || pwa.themeColor === "#6f7d5f") next.themeColor = config.colors.primary;
  if (!pwa.backgroundColor || pwa.backgroundColor === "#f7f0e6") next.backgroundColor = config.colors.background;
  const branding={showLogo:true,showHero:true,...config.branding};
  branding.headerMode=branding.headerMode||(branding.showLogo===false?"tagline":"logo");
  return { ...config, heroContent: config.heroContent==="cta"||config.heroContent==="tagline-cta"?"cta":"image", branding, appIconMediaId: config.appIconMediaId || null, imagePositions: config.imagePositions || {logo:{x:50,y:50,zoom:1},hero:{x:50,y:50,zoom:1},appIcon:{x:50,y:50,zoom:1}}, pwa: next };
}

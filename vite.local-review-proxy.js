export function localReviewForwarding(reviewOrigin) {
  if (!reviewOrigin) return null;
  const parsed = new URL(reviewOrigin);
  if (
    parsed.protocol !== "https:"
    || !parsed.hostname
    || parsed.username
    || parsed.password
    || parsed.pathname !== "/"
    || parsed.search
    || parsed.hash
  ) {
    throw new Error("JDS_LOCAL_REVIEW_ORIGIN must be an HTTPS origin without a path.");
  }
  return {
    origin: parsed.origin,
    forwardedHost: parsed.host,
    forwardedProto: "https",
    forwarded: `for=127.0.0.1;host="${parsed.host}";proto=https`,
  };
}

export function localReviewProxy(target, reviewOrigin) {
  const forwarding = localReviewForwarding(reviewOrigin);
  return {
    target,
    changeOrigin: true,
    configure(proxy) {
      if (!forwarding) return;
      proxy.on("proxyReq", (proxyRequest) => {
        proxyRequest.setHeader("Origin", forwarding.origin);
        proxyRequest.setHeader("X-Forwarded-Host", forwarding.forwardedHost);
        proxyRequest.setHeader("X-Forwarded-Proto", forwarding.forwardedProto);
        proxyRequest.setHeader("Forwarded", forwarding.forwarded);
      });
    },
  };
}

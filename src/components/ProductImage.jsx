import { useEffect, useState } from "react";

export default function ProductImage({ src = "", alt, className = "", decorative = false, loading = "lazy" }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);
  const label = alt?.trim() || "Product image";
  if (!src || failed) {
    return <div className={`product-image-placeholder ${className}`.trim()} role={decorative ? undefined : "img"} aria-hidden={decorative || undefined} aria-label={decorative ? undefined : `No photo available for ${label}`}><span aria-hidden="true">◇</span></div>;
  }
  return <img className={className} src={src} alt={decorative ? "" : label} aria-hidden={decorative || undefined} loading={loading} decoding="async" onError={() => setFailed(true)} />;
}

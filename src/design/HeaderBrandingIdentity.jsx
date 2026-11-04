import PositionedSlotImage from "./PositionedSlotImage.jsx";
import { headerBrandingMode } from "./imageSlotRendering.js";

// The shop name is always the header's primary text. A header logo replaces it visually
// when the shop has one; the tagline is a secondary line under the name, never a substitute.
// Every storefront, phone and design-studio header renders through this one component.
export default function HeaderBrandingIdentity({config,layout,logoUrl,designer=false,className="",...props}){
  const mode=headerBrandingMode(config);
  const position=config.imagePositions?.logo;
  const name=String(config.displayName||"").trim();
  const tagline=String(config.tagline||"").trim();
  const nameLine=<strong className="header-branding-name">{name}</strong>;
  const taglineLine=tagline?<span className="header-branding-tagline">{tagline}</span>:designer?<span className="designer-tagline-empty">Your tagline</span>:null;
  const content=mode==="logo"
    ? logoUrl?<PositionedSlotImage src={logoUrl} position={position} fit="contain" alt=""/>:designer?<span className="designer-logo-empty">Your logo</span>:nameLine
    : <>{nameLine}{taglineLine}</>;
  return <span {...props} className={`header-branding-identity mode-${mode} ${className}`.trim()} style={mode==="logo"?{aspectRatio:layout.logoSlot.aspectRatio}:undefined}>{content}</span>;
}

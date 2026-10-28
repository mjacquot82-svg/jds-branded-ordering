import PositionedSlotImage from "./PositionedSlotImage.jsx";
import { headerBrandingMode } from "./imageSlotRendering.js";

export default function HeaderBrandingIdentity({config,layout,logoUrl,designer=false,className="",...props}){
  const mode=headerBrandingMode(config);
  const position=config.imagePositions?.logo;
  const content=mode==="logo"
    ? logoUrl?<PositionedSlotImage src={logoUrl} position={position} fit="contain" alt=""/>:designer?<span className="designer-logo-empty">Your logo</span>:<strong>{config.displayName}</strong>
    : config.tagline?.trim()?<span className="header-branding-tagline">{config.tagline}</span>:designer?<span className="designer-tagline-empty">Your tagline</span>:<strong>{config.displayName}</strong>;
  return <span {...props} className={`header-branding-identity mode-${mode} ${className}`.trim()} style={mode==="logo"?{aspectRatio:layout.logoSlot.aspectRatio}:undefined}>{content}</span>;
}

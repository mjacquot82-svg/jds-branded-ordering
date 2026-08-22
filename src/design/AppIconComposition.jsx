import { appIconImageStyle } from "./imageSlotRendering.js";

export default function AppIconComposition({config,src,className="",editor=false}){
  return src?<span className={`installed-app-icon app-icon-composition ${editor?"app-icon-composition-editor":"app-icon-composition-output"} has-image ${className}`.trim()} style={{background:config.colors.primary}}><span className="app-icon-source-canvas" style={{background:config.colors.primary}}><img src={src} alt="Selected app icon" style={appIconImageStyle(config.imagePositions.appIcon)}/></span>{editor?<span className="app-icon-crop-boundary" aria-hidden="true"><small>Icon crop</small></span>:null}</span>:<span className={`installed-app-icon app-icon-composition generated-fallback ${className}`.trim()} style={{background:config.colors.primary}} aria-label="Generated brand-colour app icon"><i style={{background:config.colors.accent}}/></span>;
}

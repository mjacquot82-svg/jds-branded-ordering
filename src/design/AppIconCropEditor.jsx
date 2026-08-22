import AppIconComposition from "./AppIconComposition.jsx";

export default function AppIconCropEditor({config,src}){
  if(!src)return null;
  return <div className="app-icon-positioning-stage" aria-label="App Icon positioning editor">
    <AppIconComposition config={config} src={src} className="app-icon-editor-composition" editor/>
  </div>;
}

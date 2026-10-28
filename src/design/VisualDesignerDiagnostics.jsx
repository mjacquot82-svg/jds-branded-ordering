import { useEffect, useState } from "react";
import { collectVisualDesignerDiagnostics, findVerticalScrollContainer } from "./visualDesignerDiagnostics.js";

export default function VisualDesignerDiagnostics({ rootRef }) {
  const [values,setValues]=useState(null);
  useEffect(()=>{
    const update=()=>setValues(collectVisualDesignerDiagnostics(rootRef.current));
    update();
    const scroller=findVerticalScrollContainer(rootRef.current);
    const target=scroller===document.documentElement||scroller===document.body?globalThis:scroller;
    target?.addEventListener?.("scroll",update,{passive:true});
    globalThis.addEventListener?.("resize",update,{passive:true});
    const observer=typeof ResizeObserver==="function"?new ResizeObserver(update):null;
    if(rootRef.current)observer?.observe(rootRef.current);
    return()=>{target?.removeEventListener?.("scroll",update);globalThis.removeEventListener?.("resize",update);observer?.disconnect();};
  },[rootRef]);
  if(!values)return null;
  return <details className="visual-designer-diagnostics"><summary>Local layout diagnostics</summary><dl>
    <div><dt>Viewport</dt><dd>{values.viewport}px</dd></div><div><dt>Workspace</dt><dd>{values.shell}px</dd></div>
    <div><dt>Editor</dt><dd>{values.editor}px</dd></div><div><dt>Preview column</dt><dd>{values.preview}px</dd></div>
    <div><dt>Phone</dt><dd>{values.phone}px</dd></div><div><dt>Sticky position</dt><dd>{values.stickyTop}px / top {values.configuredTop}</dd></div>
    <div className="diagnostic-wide"><dt>Scroll container</dt><dd>{values.scrollContainer}</dd></div>
    <div className="diagnostic-wide"><dt>Ancestor overflow</dt><dd>{values.ancestorOverflow}</dd></div>
  </dl></details>;
}

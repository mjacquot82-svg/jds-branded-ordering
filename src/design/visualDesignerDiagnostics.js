export function findVerticalScrollContainer(element) {
  if (!element || typeof globalThis.getComputedStyle !== "function") return null;
  let ancestor=element.parentElement;
  while(ancestor&&ancestor!==document.body&&ancestor!==document.documentElement){
    const style=globalThis.getComputedStyle(ancestor);
    if(["auto","scroll","overlay"].includes(style.overflowY)&&ancestor.scrollHeight>ancestor.clientHeight)return ancestor;
    ancestor=ancestor.parentElement;
  }
  return document.scrollingElement||document.documentElement;
}

function nameFor(element) {
  if(!element)return "unavailable";
  if(element===document.documentElement)return "document.documentElement";
  if(element===document.body)return "document.body";
  const id=element.id?`#${element.id}`:"";
  const classes=typeof element.className==="string"?element.className.trim().split(/\s+/).filter(Boolean).map((item)=>`.${item}`).join(""):"";
  return `${element.tagName.toLowerCase()}${id}${classes}`;
}

export function collectVisualDesignerDiagnostics(root) {
  if(!root)return null;
  const workspace=root.querySelector(".visual-designer-workspace");
  const editor=root.querySelector(".visual-designer-editor");
  const preview=root.querySelector(".visual-designer-preview-column");
  const sticky=root.querySelector(".visual-designer-preview-sticky");
  const phone=root.querySelector(".phone-preview");
  const scrollContainer=findVerticalScrollContainer(sticky);
  const overflows=[];
  for(let item=sticky?.parentElement;item&&item!==document.documentElement;item=item.parentElement){
    const style=globalThis.getComputedStyle(item);
    overflows.push(`${nameFor(item)}: ${style.overflowX}/${style.overflowY}`);
  }
  const width=(element)=>Math.round(element?.getBoundingClientRect().width||0);
  const stickyRect=sticky?.getBoundingClientRect();
  return {
    viewport:globalThis.innerWidth,
    shell:width(workspace),editor:width(editor),preview:width(preview),phone:width(phone),
    scrollContainer:nameFor(scrollContainer),
    stickyTop:Math.round(stickyRect?.top||0),
    configuredTop:sticky?globalThis.getComputedStyle(sticky).top:"unavailable",
    ancestorOverflow:overflows.join(" · "),
  };
}

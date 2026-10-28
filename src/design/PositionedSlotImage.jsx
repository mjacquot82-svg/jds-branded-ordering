import { slotImageStyle } from "./imageSlotRendering.js";

export default function PositionedSlotImage({src,position,fit="cover",className="",alt="",diagnostics=false,...props}){
  if(!src)return null;
  const diagnosticProps=diagnostics?{
    "data-image-load-state":"loading",
    onLoad:(event)=>{const node=event.currentTarget;node.dataset.imageLoadState="loaded";node.dataset.naturalSize=`${node.naturalWidth}x${node.naturalHeight}`;node.dataset.renderedSize=`${Math.round(node.getBoundingClientRect().width)}x${Math.round(node.getBoundingClientRect().height)}`;props.onLoad?.(event);},
    onError:(event)=>{event.currentTarget.dataset.imageLoadState="error";props.onError?.(event);},
  }:props;
  return <img key={src} {...diagnosticProps} className={className} src={src} alt={alt} style={slotImageStyle(position,fit)}/>;
}

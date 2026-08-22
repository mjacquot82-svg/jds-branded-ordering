export const defaultImagePosition=Object.freeze({x:50,y:50,zoom:1});
export const imagePositionContracts=Object.freeze({
  logo:Object.freeze({minX:0,maxX:100,minY:0,maxY:100,minZoom:1,maxZoom:3}),
  hero:Object.freeze({minX:0,maxX:100,minY:0,maxY:100,minZoom:1,maxZoom:3}),
  appIcon:Object.freeze({minX:0,maxX:100,minY:0,maxY:100,minZoom:.4,maxZoom:3}),
});

export function slotImageStyle(position=defaultImagePosition,fit="cover"){
  return Object.freeze({
    objectFit:fit,
    objectPosition:`${position.x}% ${position.y}%`,
    transform:`scale(${position.zoom})`,
    transformOrigin:"center",
  });
}

// Mirrors tenant_media_icon_png: cover the square, apply zoom, then position
// the zoomed result by the merchant's focal percentages.
export function appIconImageStyle(position=defaultImagePosition){
  const zoom=Number(position.zoom)||1;const x=Number(position.x)||50;const y=Number(position.y)||50;
  return Object.freeze({objectFit:"cover",objectPosition:`${x}% ${y}%`,position:"absolute",inset:0,width:"100%",height:"100%",transform:`scale(${zoom})`,transformOrigin:`${x}% ${y}%`});
}

export function appIconPixelGeometry(position=defaultImagePosition,sourceWidth,sourceHeight,outputSize){
  const zoom=Number(position.zoom)||1;const x=Number(position.x)/100;const y=Number(position.y)/100;
  const scale=Math.max(outputSize/sourceWidth,outputSize/sourceHeight)*zoom;
  const width=sourceWidth*scale;const height=sourceHeight*scale;
  return Object.freeze({left:(outputSize-width)*x,top:(outputSize-height)*y,width,height});
}

export function appIconCroppedPixelGeometry(position=defaultImagePosition,sourceWidth,sourceHeight,outputSize){
  const canvas=appIconPixelGeometry(position,sourceWidth,sourceHeight,1000);
  const scale=outputSize/700;
  return Object.freeze({left:(canvas.left-150)*scale,top:(canvas.top-150)*scale,width:canvas.width*scale,height:canvas.height*scale});
}

export function heroContentVisibility(value="tagline-cta"){
  return Object.freeze({tagline:false,cta:value==="cta"||value==="tagline-cta"});
}

export function headerBrandingMode(config={}){
  return config.branding?.headerMode||(config.branding?.showLogo===false?"tagline":"logo");
}

export function createMediaUrlIndex(media=[]){
  return new Map(media.map((asset)=>[String(asset.id),asset.ownerUrl]));
}

export function resolveAssignedMediaUrl(index,id){
  return id==null?null:index.get(String(id))||null;
}

export const imageRequirements = Object.freeze({
  logo: Object.freeze({label:"Logo",ratio:3,minWidth:600,minHeight:200,maxBytes:10_000_000,formats:Object.freeze(["image/png","image/jpeg","image/webp"]),guidance:"A horizontal logo works best in the app header. Transparent PNG or WebP is recommended.",fit:"Fit inside the header without cropping."}),
  modernHero: Object.freeze({label:"Modern hero image",ratio:16/9,minWidth:1600,minHeight:900,maxBytes:10_000_000,formats:Object.freeze(["image/png","image/jpeg","image/webp"]),guidance:"Use a wide, high-quality image with the main subject near the centre.",fit:"Fills the large hero area and may crop at the edges."}),
  cozyHero: Object.freeze({label:"Cozy hero image",ratio:2,minWidth:1400,minHeight:700,maxBytes:10_000_000,formats:Object.freeze(["image/png","image/jpeg","image/webp"]),guidance:"Use a warm, wide image with important details away from the outer edges.",fit:"Fills the framed café hero and may crop at the edges."}),
  appIcon: Object.freeze({label:"App icon",ratio:1,minWidth:512,minHeight:512,maxBytes:10_000_000,formats:Object.freeze(["image/png","image/jpeg","image/webp"]),guidance:"Use a square image with the important mark centred. Transparent PNG or WebP works well.",fit:"The dotted Icon Crop box defines exactly what will appear."}),
  product: Object.freeze({label:"Product image",ratio:1,minWidth:800,minHeight:800,maxBytes:10_000_000,formats:Object.freeze(["image/png","image/jpeg","image/webp"]),guidance:"Use a clear square product photo with the item centred.",fit:"Fills product cards and may crop slightly by layout."}),
});

export function imageRequirementForSlot(layoutId,slot){
  if(slot==="hero")return layoutId==="modern"?imageRequirements.modernHero:layoutId==="cozy"?imageRequirements.cozyHero:null;
  return imageRequirements[slot]||null;
}

export function validateImageForSlot(image,requirement){
  const errors=[],warnings=[];
  if(!requirement.formats.includes(image.type))errors.push("Use a PNG, JPEG, or WebP image.");
  if(image.size>requirement.maxBytes)errors.push("This image is larger than 10 MB.");
  if(image.width<requirement.minWidth||image.height<requirement.minHeight)warnings.push(`This image may look blurry here. We recommend at least ${requirement.minWidth} × ${requirement.minHeight} pixels.`);
  const ratio=image.width/image.height;const difference=Math.max(ratio/requirement.ratio,requirement.ratio/ratio);
  if(difference>1.6)warnings.push(`This image’s shape is not ideal for ${requirement.label.toLowerCase()}. ${requirement.ratio===1?"A square image will work better.":"A wider image closer to the recommended shape will crop better."}`);
  return {errors,warnings};
}

export async function inspectImageFile(file){
  if(!file?.type?.startsWith("image/"))return {type:file?.type||"",size:file?.size||0,width:0,height:0};
  const bitmap=await createImageBitmap(file);
  const result={type:file.type,size:file.size,width:bitmap.width,height:bitmap.height};bitmap.close();return result;
}

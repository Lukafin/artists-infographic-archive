import {writeFileSync,readFileSync,mkdirSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as k from '../vendor/anatomy/kit/iso-kit.mjs';
import * as A from '../vendor/anatomy/kit/audit.mjs';
import {kitScript} from '../vendor/anatomy/scripts/inline-kit.mjs';
const HERE=dirname(fileURLToPath(import.meta.url));
const W=800,H=480,BASE={x:-123,y:-79,w:246,d:158,r:8};
const P=k.fitProjection(k.boxCorners(BASE,-16,42),W,H,{pad:48,azimuth:42});
const R=A.recorder(P);
let count=0;
function slab(name,plan,z,h,tone='mid',inner=''){
 plan={r:0,...plan};
 const shape=R.solid(A.slab(plan,z,h,{name},8));
 R.put({name,piece:name,at:[plan.x+plan.w/2,plan.y+plan.d/2,z+h/2],shapes:[shape],svg:k.solidSvg(k.slabOf(plan,z,h,P,8,.55),{tone,inner})});count++;
}
function round(name,x,y,r,z,h,tone='mid',inner=''){
 const shape=R.solid(A.cylinder(x,y,r,z,h,{name}));
 R.put({name,piece:name,at:[x,y,z+h/2],shapes:[shape],svg:k.solidSvg(k.cylinder(x,y,r,z,h,P,48,.35),{tone,inner})});count++;
}
for(const [i,[x,y]] of k.corners(BASE,17).entries()){
 round('stand.foot'+i,x,y,7,-16,3,'lo');round('foot.riser'+i,x,y,5,-13,3,'lo');
}
slab('base',BASE,-10,10,'lo',k.lineSvg(k.planOutline(k.insetPlan(BASE,5),0,P),{tone:'lo'}));
// Bus bars form one closed rectangle, interrupted by each instrument.
const tracks=[
 {x:-92,y:-47,w:72,d:4},{x:20,y:-47,w:72,d:4},
 {x:88,y:-43,w:4,d:23},{x:88,y:20,w:4,d:23},
 {x:20,y:43,w:72,d:4},{x:-92,y:43,w:72,d:4},
 {x:-92,y:22,w:4,d:21},{x:-92,y:-43,w:4,d:21}];
tracks.forEach((p,i)=>{slab('track.insulator'+i,p,0,2,'lo');slab('track.copper'+i,p,2,2,'hi');});
const devices=[{id:'source',x:-90,y:0,w:40,d:44,h:24,label:'VIR · U',unit:'V'},
{id:'switch',x:0,y:-45,w:40,d:32,h:9,label:'STIKALO',unit:'0 / 1'},
{id:'resistor',x:90,y:0,w:40,d:40,h:12,label:'UPOR · R',unit:'Ω'},
{id:'meter',x:0,y:45,w:40,d:32,h:16,label:'TOK · I',unit:'A'}];
const dial={};
// Printed schematic marks on the cover plane: DC source, SPST, IEC resistor, ammeter.
// These are electrical glyphs, not grooves or extra mechanical solids.
function schematic(dev,z){
 const marks={
  source:'<circle cx="0" cy="0" r="8"/><path d="M0 -12V-8 M0 8V12 M-2.5 -3H2.5 M0 -5.5V-.5 M-2.5 3H2.5"/>',
  switch:'<path d="M-14 0H-10 M10 0H14"/><circle cx="-10" cy="0" r="1"/><circle cx="10" cy="0" r="1"/><path id="switch-contact" d="M-10 0H10"/>',
  resistor:'<path d="M0 -12V-7 M0 7V12"/><rect x="-3.5" y="-7" width="7" height="14"/>',
  meter:'<circle cx="0" cy="0" r="8"/><path d="M-12 0H-8 M8 0H12"/><text x="0" y="3.5" text-anchor="middle">A</text>'
 };
 return `<g class="circuit-symbol" data-component="${dev.id}" transform="${k.topMatrix([dev.x-3,dev.y],z,P,'x')}">${marks[dev.id]}</g>`;
}
for(const dev of devices){
 const p={x:dev.x-dev.w/2,y:dev.y-dev.d/2,w:dev.w,d:dev.d,r:2};
 slab(dev.id+'.case',p,0,dev.h,'mid');
 const top=dev.h+1;
 slab(dev.id+'.cover',p,dev.h,1,'mid',schematic(dev,top)+k.faceTextSvg(k.topMatrix([dev.x,dev.y+dev.d/2-2],top,P,'x'),dev.label,{size:2.5,tone:'hi',anchor:'middle'}));
 for(const [i,[x,y]] of k.corners(p,3).entries())round(dev.id+'.screw'+i,x,y,.85,top,.6,'lo');
 const cx=dev.x+12,cy=dev.y-9,r=4;
 round(dev.id+'.dial',cx,cy,r,top,2,'hi');
 const ticks=k.radialTicks(cx,cy,r-1,12,3,top+2.6,[.45,.8],P);
 round(dev.id+'.face',cx,cy,r-.35,top+2,.6,'hi',k.lineSvg(k.ring(cx,cy,r-1,top+2.6,P),{tone:'lo'})+k.lineSvg(ticks.minor,{tone:'lo'})+k.lineSvg(ticks.major,{tone:'mid'}));
 dial[dev.id]={x:cx,y:cy,z:top+2.8,r:r-1.2};
}
A.settle(R,P);A.auditOrExit(R,P);
const needle=(id,angle)=>{const d=dial[id];return k.lineOnTop([d.x,d.y],[d.x+Math.cos(angle)*d.r,d.y+Math.sin(angle)*d.r],d.z,P)};
// Dynamic printed needles belong to their dial faces. Free tips are intentional.
R.items.forEach(item=>{const id=item.name.replace('.face','');if(dial[id]&&item.name.endsWith('.face')) item.svg+=`<path id="needle-${id}" class="iso-line" data-tone="${id==='meter'?'lit':'hi'}" data-free="end" d="${needle(id,-Math.PI/2)}"/><circle class="iso-dot" cx="${k.iso([dial[id].x,dial[id].y,dial[id].z],P)[0]}" cy="${k.iso([dial[id].x,dial[id].y,dial[id].z],P)[1]}" r=".9"/>`;});
const route=[[-90,-22,4],[-90,-45,4],[-20,-45,4],[20,-45,4],[90,-45,4],[90,-20,4],[90,20,4],[90,45,4],[20,45,4],[-20,45,4],[-90,45,4],[-90,22,4]];
// Each marker is clipped to its copper bar and shares its proven painter order.
// In particular, the source housing occludes the rear conductor correctly.
const markerTracks=[7,0,1,2,3,4,5,6];
markerTracks.forEach((track,i)=>{
 const paths=k.slabOf({r:0,...tracks[track]},2,2,P,8,.55);
 const item=R.items.find(item=>item.name==='track.copper'+track);
 item.svg+=`<defs><clipPath id="bar-clip-${i}"><path d="${paths.top}"/></clipPath></defs><g clip-path="url(#bar-clip-${i})" aria-hidden="true"><circle id="current-marker-${i}" r="1.8" fill="var(--anatomy-lit)"/></g>`;
});
const fig=k.figureSvg({width:W,height:H,label:'Izometrični laboratorijski tokokrog: vir na levi, stikalo zadaj, upor na desni in ampermeter spredaj. Nastavitve so pod prikazom.',body:R.items.sort((a,b)=>a.key-b.key).map(i=>i.svg)});
const css=readFileSync(join(HERE,'style.css'),'utf8');
const ui=readFileSync(join(HERE,'ui.html'),'utf8').replace('<!--FIGURE-->',fig);
const model=readFileSync(join(HERE,'model.mjs'),'utf8').replace('export function','function');
const live=`const P=${JSON.stringify(P)},DIAL=${JSON.stringify(dial)},ROUTE=${JSON.stringify(route)};\n`+model+readFileSync(join(HERE,'live.js'),'utf8');
const script=(kitScript()+"\n"+live).replace(/<\/(script)/gi,"<\\/$1");
const license=readFileSync(join(HERE,'../vendor/anatomy/LICENSE'),'utf8');
const html=`<!doctype html><html lang="sl"><head><meta charset="utf-8"><!-- Anatomy toolkit e6600ffc4e8e6620eeb45bf49bcdbd5e4b84163f\n${license} --><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="Razišči električni tokokrog: spreminjaj napetost in upor ter opazuj tok in moč."><title>Elektrika — sklenjeni tokokrog</title><style>${k.ISO_CSS}\n${css}</style></head><body class="iso" data-theme="light">${ui}<script type="module">${script}</script></body></html>`;
for(const folder of ['docs','site']){const dest=join(HERE,'../..',folder,'interactive/elektrika/v1');mkdirSync(dest,{recursive:true});writeFileSync(join(dest,'index.html'),html);}
console.log(`Elektrika: ${count} solids; standalone HTML generated in docs and site.`);

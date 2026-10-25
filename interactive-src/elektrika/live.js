const $=id=>document.getElementById(id);
const voltage=$('voltage'),resistance=$('resistance'),toggle=$('switch');
const still=matchMedia('(prefers-reduced-motion: reduce)');
const format=n=>n.toLocaleString('sl-SI',{minimumFractionDigits:2,maximumFractionDigits:2});
let model=circuit(),paused=still.matches,visible=true,phase=0,frame=0,last=0;
const exposed=[[0,1],[1,2],[3,4],[4,5],[6,7],[7,8],[9,10],[10,11]].map(([a,b])=>[ROUTE[a],ROUTE[b]]);
const dots=exposed.map((_,i)=>$('current-marker-'+i));
function needle(id,fraction){const d=DIAL[id],angle=-Math.PI*.85+fraction*Math.PI*1.7;const path=lineOnTop([d.x,d.y],[d.x+Math.cos(angle)*d.r,d.y+Math.sin(angle)*d.r],d.z,P);$('needle-'+id).setAttribute('d',path);}
function render(){
 voltage.value=model.voltage;resistance.value=model.resistance;
 $('voltage-value').textContent=model.voltage+' V';$('resistance-value').textContent=model.resistance+' Ω';
 voltage.setAttribute('aria-valuetext',model.voltage+' voltov');resistance.setAttribute('aria-valuetext',model.resistance+' ohmov');
 $('current').innerHTML=format(model.current)+' <small>A</small>';$('power').innerHTML=format(model.power)+' <small>W</small>';
 toggle.setAttribute('aria-pressed',String(model.closed));$('switch-label').textContent=model.closed?'Stikalo je sklenjeno':'Stikalo je odprto';
 toggle.querySelector('.switch-action').textContent=model.closed?'Odpri ↗':'Skleni ↗';
 $('switch-contact').setAttribute('d',model.closed?'M-10 0H10':'M-10 0L6 -7');
 $('state').textContent=model.closed?(model.voltage?'SKLENJEN TOKOKROG':'NAPETOST JE NIČ'):'ODPRT TOKOKROG';
 $('explanation').textContent=model.closed?`Pri ${model.voltage} V in ${model.resistance} Ω teče tok ${format(model.current)} A. Upor prejema ${format(model.power)} W električne moči.`:'Stikalo prekine tokokrog. Tok in moč na uporu sta enaka nič; napetost vira ostaja nastavljena.';
 needle('source',model.voltage/12);needle('resistor',(model.resistance-4)/20);needle('meter',model.current/3);needle('switch',model.closed?.85:.15);
 document.querySelectorAll('[data-preset]').forEach(b=>b.setAttribute('aria-pressed','false'));
 if(!model.closed)$('lesson').textContent='Odprto stikalo: ne glede na nastavitev vira tok ne teče.';
 else if(model.voltage===6&&model.resistance===12){$('lesson').textContent='Izhodišče: tok 0,50 A in moč 3,00 W.';document.querySelector('[data-preset=baseline]').setAttribute('aria-pressed','true');}
 else if(model.voltage===12&&model.resistance===12){$('lesson').textContent='Dvojna napetost → dvojni tok (1,00 A), štirikratna moč (12,00 W).';document.querySelector('[data-preset=voltage]').setAttribute('aria-pressed','true');}
 else if(model.voltage===6&&model.resistance===24){$('lesson').textContent='Dvojni upor → polovični tok (0,25 A) in polovična moč (1,50 W).';document.querySelector('[data-preset=resistance]').setAttribute('aria-pressed','true');}
 else $('lesson').textContent='Pri stalnem uporu je tok sorazmeren z napetostjo. Pri stalni napetosti večji upor zmanjša tok.';
 drawDots();schedule();
}
function drawDots(){dots.forEach((el,i)=>{const [a,b]=exposed[i],t=(phase+i*.137)%1;const at=iso(a.map((v,j)=>v+(b[j]-v)*t),P);el.setAttribute('cx',at[0]);el.setAttribute('cy',at[1]);el.style.display=model.current>0?'':'none';});}
function schedule(){if(!frame&&visible&&!document.hidden&&!paused&&model.current>0){last=0;frame=requestAnimationFrame(tick);}}
function tick(now){frame=0;if(!visible||document.hidden||paused||model.current<=0)return;const dt=last?Math.min((now-last)/1000,.05):0;last=now;phase=(phase+dt*model.current*.28)%1;drawDots();frame=requestAnimationFrame(tick);}
function cancel(){cancelAnimationFrame(frame);frame=0;last=0;}
voltage.addEventListener('input',()=>{model=circuit({...model,voltage:Number(voltage.value)});render();});
resistance.addEventListener('input',()=>{model=circuit({...model,resistance:Number(resistance.value)});render();});
toggle.addEventListener('click',()=>{model=circuit({...model,closed:!model.closed});render();});
document.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>{const values={baseline:[6,12],voltage:[12,12],resistance:[6,24]}[b.dataset.preset];model=circuit({voltage:values[0],resistance:values[1],closed:true});render();}));
function pauseLabel(){$('motion').textContent=paused?'Zaženi pike':'Ustavi pike';$('motion').setAttribute('aria-pressed',String(paused));}
$('motion').addEventListener('click',()=>{paused=!paused;pauseLabel();if(paused)cancel();else schedule();});
still.addEventListener('change',()=>{paused=still.matches;pauseLabel();if(paused)cancel();else schedule();});
new IntersectionObserver(([entry])=>{visible=entry.isIntersecting;if(visible)schedule();else cancel();}).observe(document.querySelector('.iso-stage'));
document.addEventListener('visibilitychange',()=>{if(document.hidden)cancel();else schedule();});
function theme(dark){document.body.dataset.theme=dark?'dark':'light';$('theme').textContent=dark?'Svetla tema':'Temna tema';$('theme').setAttribute('aria-label',dark?'Preklopi na svetlo temo':'Preklopi na temno temo');}
$('theme').addEventListener('click',()=>theme(document.body.dataset.theme!=='dark'));
theme(matchMedia('(prefers-color-scheme: dark)').matches);
pauseLabel();render();

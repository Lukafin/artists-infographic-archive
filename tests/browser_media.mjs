// Real local Chromium/CDP media and sandbox acceptance; no public fixture hosting.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,writeFile,rm,mkdir} from 'node:fs/promises';
import path from 'node:path';
const url=process.argv[2], scratch=process.argv[3] || process.env.TMPDIR;
if(!url||!scratch) throw Error('Supply local fixture URL and scratch');
await mkdir(scratch,{recursive:true});
const profile=await mkdtemp(path.join(scratch,'media-chromium-'));
const chrome=spawn(process.env.CHROMIUM||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--remote-debugging-port=9228',`--user-data-dir=${profile}`,'about:blank'],{stdio:'ignore'});
let socket,nextId=1; const pending=new Map(),requests=[],errors=[];
const wait=ms=>new Promise(r=>setTimeout(r,ms));
async function until(fn,label){for(let i=0;i<100;i++){try{if(await fn())return;}catch(_){}await wait(100);}throw Error(`Timed out: ${label}`);}
function command(method,params={}){const id=nextId++;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(`CDP timeout ${method}`)),15000);pending.set(id,{resolve,reject,timer});socket.send(JSON.stringify({id,method,params}));});}
async function evaluate(expression){const r=await command('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true,userGesture:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;}
async function search(person){await evaluate(`(()=>{const s=document.getElementById('archive-search');s.value=${JSON.stringify(person)};s.dispatchEvent(new Event('input',{bubbles:true}));})()`);await wait(200);}
const video="document.querySelector('#companion-player video')", frame="document.querySelector('#companion-player iframe')";
async function activate(kind){await evaluate(`Array.from(document.querySelectorAll('[data-companion]')).find(b=>JSON.parse(b.dataset.companion).artifact_kind===${JSON.stringify(kind)}).click()`);}
async function screenshot(name){const r=await command('Page.captureScreenshot');await writeFile(path.join(scratch,name),Buffer.from(r.data,'base64'));}
try{
 let targets;await until(async()=>{targets=await(await fetch('http://127.0.0.1:9228/json/list')).json();return targets.some(t=>t.type==='page');},'Chromium');
 socket=new WebSocket(targets.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>socket.addEventListener('open',r,{once:true}));
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data);if(pending.has(m.id)){const p=pending.get(m.id);pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result);}if(m.method==='Network.requestWillBeSent'&&/fixture\.(webm|mp4|html)|interactive-fixture|\/audio\//.test(m.params.request.url))requests.push(m.params.request.url);if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);});
 await command('Page.enable');await command('Runtime.enable');await command('Network.enable');
 await command('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await command('Page.navigate',{url});await until(()=>evaluate('document.readyState === "complete" && !!document.querySelector("#archive-search")'),'page');await wait(600);
 assert.equal(requests.length,0,'No initial media/interactive requests');
 const episodes=await evaluate('(async()=> (await(await fetch("entries.json")).json()).entries.filter(e=>e.companions).map(e=>({person:e.person,podcast:!!e.podcast})))()');assert.ok(episodes.length>=2);
 await search(episodes[0].person);await until(()=>evaluate('!!document.querySelector("[data-companion]")'),'actions');
 await evaluate("document.querySelector('[data-podcast-listen]').click();window.audio=document.querySelector('audio');audio.play()");await until(()=>evaluate('!audio.paused&&audio.currentTime>0.1'),'audio');
 await activate('video');assert.equal(await evaluate('audio.paused'),true,'Watch pauses audio');
 assert.equal(await evaluate(`${video}.paused && ${video}.preload==='none' && ${video}.playsInline && ${video}.controls`),true);
 assert.equal(requests.filter(r=>r.includes('fixture.webm')).length,0,'Selecting Watch does not load video');
 await evaluate(`window.v=${video};v.play()`);await until(()=>evaluate('v.currentTime>0.2&&!v.paused&&v.videoWidth===320'),'actual decoded video');
 await evaluate('v.currentTime=3');await until(()=>evaluate('v.currentTime>=3'),'seek');
 const playback=await evaluate('({duration:v.duration,width:v.videoWidth,height:v.videoHeight,time:v.currentTime})');
 await evaluate("document.querySelector('[data-lang-option=sl]').click()");await wait(100);
 assert.equal(await evaluate("document.querySelector('[data-companion]').textContent==='Poglej'&&!v.paused"),true,'Slovenian UI preserves spoken media language and playback');
 await evaluate("document.querySelector('[data-lang-option=en]').click()");await wait(100);
 await evaluate("document.querySelector('.companion-fullscreen').click()");await until(()=>evaluate("document.fullscreenElement===document.getElementById('companion-player')"),'fullscreen');
 await evaluate('document.exitFullscreen()');
 await search('');await evaluate("document.querySelector('.pagination a[href=\"page-2.html\"]').click()");await until(()=>evaluate('location.pathname.endsWith("page-2.html")'),'pagination');assert.equal(await evaluate(`${video}===v&&!v.paused`),true);
 await evaluate('history.back()');await until(()=>evaluate('location.pathname.endsWith("index.html")'),'back');
 await search(episodes[0].person);await evaluate("document.getElementById('archive-language').value='en';document.getElementById('archive-language').dispatchEvent(new Event('change'))");assert.equal(await evaluate('!v.paused'),true);
 await evaluate("document.getElementById('archive-language').value='';document.getElementById('archive-language').dispatchEvent(new Event('change'))");
 await screenshot('media-video-desktop.png');
 await evaluate("window.fixtureMessages=[];window.addEventListener('message',e=>{if(e.data?.fixture)fixtureMessages.push(e.data)})");
 await activate('interactive_site');assert.equal(await evaluate('v.paused&&!v.hasAttribute("src")'),true,'Replacement releases video');
 await until(()=>evaluate('fixtureMessages.length>0'),'interactive ready');
 assert.equal(await evaluate(`${frame}.getAttribute('sandbox')`),'allow-scripts');
 assert.equal(await evaluate('fixtureMessages[0].isolated && !document.body.dataset.unsafe'),true,'Opaque-origin script cannot access parent DOM');
 const box=await evaluate(`(()=>{const r=${frame}.getBoundingClientRect();return {x:r.x+60,y:r.y+40}})()`);
 await command('Input.dispatchMouseEvent',{type:'mousePressed',x:box.x,y:box.y,button:'left',clickCount:1});await command('Input.dispatchMouseEvent',{type:'mouseReleased',x:box.x,y:box.y,button:'left',clickCount:1});
 await until(()=>evaluate('fixtureMessages.some(m=>m.count===1)'),'real interactive button');
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9});
 await command('Input.dispatchKeyEvent',{type:'keyDown',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});await command('Input.dispatchKeyEvent',{type:'keyUp',key:'ArrowRight',code:'ArrowRight',windowsVirtualKeyCode:39});
 await until(()=>evaluate('fixtureMessages.some(m=>Number(m.energy)>20)'),'keyboard slider');
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'desktop overflow');
 await screenshot('media-interactive-desktop.png');
 await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});await wait(300);
 assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true,'mobile overflow');await screenshot('media-interactive-mobile.png');
 await evaluate("document.querySelector('.companion-dismiss').click()");assert.equal(await evaluate(`!${frame} && document.getElementById('companion-player').hidden && document.activeElement.matches('[data-companion]')`),true,'Unload and restore focus');
 assert.equal(await evaluate(`(()=>{const card=document.querySelector('.masonry .card:has([data-companion])');const a=card.querySelector('[data-podcast-listen]').getBoundingClientRect();const b=card.querySelector('.companion-actions').getBoundingClientRect();return a.right<=b.left && b.right<=card.getBoundingClientRect().right;})()`),true,'Mobile actions beside Listen without overlap');
 await screenshot('media-actions-mobile.png');
 await activate('video');await evaluate(`${video}.play()`);await until(()=>evaluate(`${video}.currentTime>0.1`),'mobile video');await screenshot('media-video-mobile.png');
 await evaluate("document.querySelector('[data-podcast-listen]').click()");assert.equal(await evaluate(`!${video}&&document.getElementById('companion-player').hidden`),true,'Listen unloads video');
 await activate('video');await evaluate(`${video}.src=${JSON.stringify(new URL('missing.webm',url).href)};${video}.play().catch(()=>{})`);await until(()=>evaluate("document.querySelector('#companion-player [role=status]').textContent.includes('unavailable')"),'accessible error');
 await evaluate("document.querySelector('.companion-dismiss').click()");assert.deepEqual(errors,[]);
 await search(episodes[1].person);await activate('video');assert.equal(await evaluate(`${video}.paused&&${video}.currentTime===0`),true,'New video never autoplays');
 await evaluate(`${video}.play()`);await until(()=>evaluate(`${video}.currentTime>0.1&&${video}.videoWidth===320`),'actual MP4 decode/playback');
 assert.equal(await evaluate(`${video}.currentSrc.endsWith('.mp4')`),true);
 await evaluate("document.querySelector('.companion-dismiss').click()");
 console.log(JSON.stringify({desktop:1440,mobile:390,initialMediaRequests:0,playback,mp4:'decoded/played',seek:'passed',fullscreen:'passed',sandbox:'allow-scripts only; parent DOM blocked',interactiveButton:'passed',keyboardSlider:'passed',pagination:'same video retained',filters:'retained',dismiss:'unloads and returns focus',audioVideoExclusion:'passed',error:'accessible fallback',screenshots:scratch}));
}finally{socket?.close();chrome.kill('SIGTERM');await new Promise(r=>chrome.once('exit',r));await rm(profile,{recursive:true,force:true});}

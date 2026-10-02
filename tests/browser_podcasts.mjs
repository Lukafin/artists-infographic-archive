// Optional real Chromium smoke test against a disposable, audio-equipped fixture.
// Usage: node tests/browser_podcasts.mjs http://127.0.0.1:8764/index.html /private/scratch
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp, writeFile, rm, mkdir} from 'node:fs/promises';
import path from 'node:path';

const url = process.argv[2];
const scratch = process.argv[3] || process.env.TMPDIR;
if (!url || !scratch) throw new Error('Supply local fixture URL and scratch directory');
await mkdir(scratch, {recursive:true});
const profile = await mkdtemp(path.join(scratch, 'podcast-chromium-'));
const chrome = spawn(process.env.CHROMIUM || '/usr/bin/chromium', [
  '--headless', '--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage',
  '--remote-debugging-port=9227', '--remote-debugging-address=127.0.0.1',
  `--user-data-dir=${profile}`, 'about:blank'
], {stdio:'ignore'});
let socket;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label) {
  for (let i=0; i<100; i++) {
    try { if (await fn()) return; } catch (_) {}
    await wait(100);
  }
  throw new Error(`Timed out: ${label}`);
}
const pending = new Map();
let nextId = 1;
const audioRequests = [];
const errors = [];
function command(method, params={}) {
  const id = nextId++;
  return new Promise((resolve,reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error(`CDP timeout: ${method}`)); }, 15000);
    pending.set(id, {resolve, reject, timer});
    socket.send(JSON.stringify({id, method, params}));
  });
}
async function evaluate(expression) {
  const result = await command('Runtime.evaluate', {expression, returnByValue:true, awaitPromise:true, userGesture:true});
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
try {
  let targets;
  await until(async () => { targets = await (await fetch('http://127.0.0.1:9227/json/list')).json(); return targets.some(x=>x.type==='page'); }, 'Chromium ready');
  socket = new WebSocket(targets.find(x=>x.type==='page').webSocketDebuggerUrl);
  await new Promise(resolve => socket.addEventListener('open', resolve, {once:true}));
  socket.addEventListener('message', event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const p = pending.get(message.id); pending.delete(message.id); clearTimeout(p.timer);
      if (message.error) p.reject(new Error(JSON.stringify(message.error))); else p.resolve(message.result);
    }
    if (message.method === 'Network.requestWillBeSent' && /\/audio\//.test(message.params.request.url)) audioRequests.push(message.params.request.url);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
  });
  await command('Runtime.enable');
  await command('Network.enable');
  await command('Page.enable');
  await command('Emulation.setDeviceMetricsOverride', {width:1280, height:900, deviceScaleFactor:1, mobile:false});
  await command('Page.navigate', {url});
  await until(() => evaluate('document.readyState === "complete" && !!document.querySelector("#archive-search")'), 'archive loaded');
  await wait(500);
  assert.equal(await evaluate('document.querySelectorAll("audio").length'), 1);
  assert.equal(await evaluate('document.getElementById("podcast-player").hidden'), true);
  assert.equal(audioRequests.length, 0, 'No page-load audio requests');
  const episodes = await evaluate('(async()=> (await (await fetch("entries.json")).json()).entries.filter(e=>e.podcast).map(e=>({person:e.person, language:e.language, id:e.podcast.companion_id})))()');
  assert.ok(episodes.length >= 2, 'Fixture needs two companions');
  async function search(person) {
    await evaluate(`(()=>{const s=document.getElementById('archive-search');s.value=${JSON.stringify(person)};s.dispatchEvent(new Event('input',{bubbles:true}));})()`);
    await wait(150);
  }
  await search(episodes[0].person);
  await until(() => evaluate('!!document.querySelector("[data-podcast-listen]")'), 'Listen action');
  await evaluate("document.querySelector('[data-podcast-listen]').click(); window.testAudio=document.querySelector('audio')");
  assert.equal(await evaluate('testAudio.paused && testAudio.preload === "none"'), true);
  assert.equal(await evaluate('document.getElementById("podcast-player").hidden'), false);
  await wait(200);
  assert.equal(audioRequests.length, 0, 'Selecting Listen does not preload/play');
  await evaluate('testAudio.play()');
  await until(() => evaluate('testAudio.currentTime > 0.1 && !testAudio.paused && testAudio.duration > 0'), 'native audio playback');
  await evaluate('testAudio.currentTime=3');
  await until(() => evaluate('testAudio.currentTime >= 3'), 'seek');
  await evaluate("document.querySelector('[data-podcast-listen]').click()");
  assert.equal(await evaluate('!testAudio.paused && testAudio.currentTime >= 3'), true, 'Same Listen preserves playback');
  await evaluate("document.getElementById('archive-language').value='en';document.getElementById('archive-language').dispatchEvent(new Event('change'))");
  assert.equal(await evaluate('!testAudio.paused'), true, 'Filtering preserves playback');
  await evaluate("document.getElementById('archive-language').value='';document.getElementById('archive-language').dispatchEvent(new Event('change'))");
  await search('');
  await evaluate("document.querySelector('.pagination a[href=\"page-2.html\"]').click()");
  await until(() => evaluate('location.pathname.endsWith("page-2.html")'), 'same-document pagination');
  assert.equal(await evaluate('document.querySelector("audio") === testAudio && !testAudio.paused'), true);
  await evaluate('history.back()');
  await until(() => evaluate('location.pathname.endsWith("index.html") && document.querySelector("[data-archive-heading]").dataset.page === "1"'), 'pagination back');
  assert.equal(await evaluate('document.querySelector("audio") === testAudio && !testAudio.paused'), true);
  await evaluate("document.querySelector('[data-lang-option=sl]').click()");
  assert.ok((await evaluate("document.querySelector('.podcast-language').textContent")).includes(episodes[0].language.toUpperCase()));
  await search(episodes[1].person);
  await evaluate("document.querySelector('[data-podcast-listen]').click()");
  assert.equal(await evaluate('testAudio.paused && testAudio.currentTime === 0'), true, 'Switch stops old episode without autoplay');
  assert.ok((await evaluate("document.querySelector('.podcast-title').textContent")).includes(episodes[1].person));
  await command('Page.captureScreenshot').then(result => writeFile(path.join(scratch,'podcast-desktop.png'), Buffer.from(result.data,'base64')));
  await command('Emulation.setDeviceMetricsOverride', {width:390, height:844, deviceScaleFactor:1, mobile:true});
  await wait(300);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true, 'No mobile overflow');
  assert.equal(await evaluate(`(()=>{const p=document.getElementById('podcast-player');return parseFloat(getComputedStyle(document.body).paddingBottom)>p.getBoundingClientRect().height;})()`), true, 'Content clears bottom player');
  await command('Page.captureScreenshot').then(result => writeFile(path.join(scratch,'podcast-mobile.png'), Buffer.from(result.data,'base64')));
  await evaluate('testAudio.play()');
  await until(() => evaluate('!testAudio.paused'), 'second playback');
  await evaluate("document.querySelector('.podcast-dismiss').click()");
  assert.equal(await evaluate('testAudio.paused && !testAudio.hasAttribute("src") && document.getElementById("podcast-player").hidden'), true);
  assert.equal(await evaluate('document.activeElement.matches("[data-podcast-listen]")'), true, 'Dismiss returns focus');
  const http = await evaluate(`(async()=>{const data=await(await fetch('entries.json')).json();const u=data.entries.find(e=>e.podcast).podcast.url;const h=await fetch(u,{method:'HEAD'});const r=await fetch(u,{headers:{Range:'bytes=0-1023'}});return {status:h.status,mime:h.headers.get('content-type'),rangeStatus:r.status,contentRange:r.headers.get('content-range')};})()`);
  assert.equal(http.status, 200);
  assert.equal(http.mime, 'audio/mp4');
  assert.deepEqual(errors, [], 'No JavaScript errors');
  console.log(JSON.stringify({desktop:'passed', mobile:'passed', playback:'passed', seek:'passed', autoplay:false,
    initialAudioRequests:0, pagination:'same media element, playback retained, back works', episodeSwitch:'paused', dismiss:'stops and restores focus', http, screenshots:scratch}));
} finally {
  socket?.close();
  chrome.kill('SIGTERM');
  await new Promise(resolve => chrome.once('exit', resolve));
  await rm(profile, {recursive:true, force:true});
}

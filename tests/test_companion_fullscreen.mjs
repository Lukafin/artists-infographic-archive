import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const source = readFileSync(new URL('../assets/companion-player.js', import.meta.url), 'utf8');

function fixture(fullscreenMode = 'supported') {
  const listeners = new Map();
  const node = () => ({
    hidden:true, dataset:{}, attributes:{}, children:[], classes:new Set(), handlers:{},
    setAttribute(key,value) { this.attributes[key] = value; },
    getAttribute(key) { return this.attributes[key]; },
    removeAttribute(key) { delete this.attributes[key]; },
    addEventListener(name,handler) { this.handlers[name] = handler; },
    focus() { document.activeElement = this; },
    click() { return this.handlers.click?.(); },
    pause() {}, load() {},
    append(child) { this.children.push(child); },
    replaceChildren() { this.children = []; },
    querySelectorAll(tag) { return this.children.filter(child => child.tag === tag); },
  });
  const panel = node(), stage = node(), close = node(), full = node(), title = node(), note = node(), link = node();
  panel.id = 'companion-player';
  panel.classList = {add: name => panel.classes.add(name), remove: name => panel.classes.delete(name)};
  const selectors = {'h2':title, '.companion-stage':stage, '.companion-dismiss':close,
    '.companion-fullscreen':full, '[role=status]':note, '.companion-fallback':link};
  panel.querySelector = selector => selectors[selector];
  let requests = 0, exits = 0, insideClick = false;
  const document = {
    documentElement:{lang:'en'}, body:node(), fullscreenElement:null,
    getElementById:() => panel,
    querySelector:selector => selector === '.masonry' ? node() : null,
    querySelectorAll:() => [],
    createElement:tag => Object.assign(node(), {tag}),
    addEventListener(name,handler) { listeners.set(name,[...(listeners.get(name) || []),handler]); },
    dispatchEvent() {},
    exitFullscreen() {
      exits++; this.fullscreenElement = null;
      return Promise.resolve().then(() => { this.activeElement = this.body; });
    },
  };
  if (fullscreenMode !== 'unavailable') panel.requestFullscreen = () => {
    assert.ok(insideClick, 'Fullscreen must be requested synchronously during the click');
    assert.equal(panel.hidden, false, 'The panel must be visible before requesting fullscreen');
    requests++;
    if (fullscreenMode === 'denied') return Promise.reject(new Error('Browser denied fullscreen'));
    document.fullscreenElement = panel;
    return Promise.resolve();
  };
  vm.runInNewContext(source, {document, window:{addEventListener(){}}, URL, Event,
    MutationObserver:class { observe(){} }});
  function explore(kind = 'interactive_site', mode = 'sandboxed_iframe') {
    const button = node();
    button.dataset.companion = JSON.stringify({artifact_kind:kind, presentation_mode:mode,
      url:'https://example.org/experiment', title:'Reviewed experiment', language:'sl', companion_id:'approved'});
    button.closest = selector => selector === '[data-companion]' ? button : null;
    insideClick = true;
    try {
      listeners.get('click').forEach(handler => handler({target:button,preventDefault(){},stopPropagation(){}}));
    } finally { insideClick = false; }
    return button;
  }
  return {panel, stage, document, close, explore, requests:() => requests, exits:() => exits};
}

test('Explore requests fullscreen immediately and keeps the reviewed iframe sandbox', () => {
  const f = fixture();
  f.explore();
  assert.equal(f.requests(), 1);
  assert.equal(f.document.fullscreenElement, f.panel);
  assert.ok(f.panel.classes.has('interactive-fullscreen'));
  assert.equal(f.stage.children[0].getAttribute('sandbox'), 'allow-scripts');
});

test('Denied or unavailable fullscreen retains the full-window layout', async () => {
  for (const mode of ['denied','unavailable']) {
    const f = fixture(mode);
    f.explore();
    await Promise.resolve();
    assert.equal(f.panel.hidden, false);
    assert.ok(f.panel.classes.has('interactive-fullscreen'));
    assert.equal(f.stage.children.length, 1);
  }
});

test('Closing exits fullscreen, unloads the iframe and restores trigger focus', async () => {
  const f = fixture();
  const button = f.explore();
  button.isConnected = true;
  await f.close.click();
  assert.equal(f.exits(), 1);
  assert.equal(f.panel.hidden, true);
  assert.equal(f.stage.children.length, 0);
  assert.equal(f.panel.classes.has('interactive-fullscreen'), false);
  assert.equal(f.document.activeElement, button);
});

test('Link-only interactive records do not embed or enter fullscreen', () => {
  const f = fixture();
  f.explore('interactive_site', 'link');
  assert.equal(f.requests(), 0);
  assert.equal(f.stage.children.length, 0);
  assert.equal(f.panel.classes.has('interactive-fullscreen'), false);
});

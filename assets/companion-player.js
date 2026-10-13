/* Reviewed URL presentation only. Never load media before deliberate activation. */
(() => {
  const panel = document.getElementById('companion-player');
  if (!panel) return;
  const stage = panel.querySelector('.companion-stage');
  const title = panel.querySelector('h2');
  const note = panel.querySelector('[role=status]');
  const close = panel.querySelector('.companion-dismiss');
  const fullscreen = panel.querySelector('.companion-fullscreen');
  const fallback = panel.querySelector('.companion-fallback');
  let trigger, active, failed = false;
  const text = () => document.documentElement.lang === 'sl'
    ? {player:'Pregledana razlaga', watch:'Poglej', explore:'Razišči', link:'Odpri povezavo', close:'Zapri in ustavi', full:'Cel zaslon', help:'Uporabi kontrolnike. Če vsebina ne deluje ali gostitelj blokira prikaz, uporabi povezavo.', error:'Videoposnetek ni na voljo. Uporabi povezavo ali poskusi pozneje.'}
    : {player:'Reviewed explanation', watch:'Watch', explore:'Explore', link:'Open external link', close:'Close and stop', full:'Fullscreen', help:'Use the controls. If content is unavailable or the host blocks embedding, use the link.', error:'Video unavailable. Use the link or try again later.'};
  function translate() {
    const t = text();
    document.querySelectorAll('[data-companion]').forEach(button => {
      try {
        const data = JSON.parse(button.dataset.companion);
        button.textContent = data.artifact_kind === 'video' ? t.watch : t.explore;
        button.setAttribute('aria-label', `${button.textContent}: ${data.title} (${data.language.toUpperCase()})`);
        button.setAttribute('aria-controls', panel.id);
      } catch (_) { button.disabled = true; }
    });
    close.setAttribute('aria-label', t.close);
    panel.setAttribute('aria-label', t.player);
    fullscreen.textContent = t.full;
    fallback.textContent = t.link;
    note.textContent = failed ? t.error : t.help;
  }
  function stop() {
    const exitingFullscreen = document.fullscreenElement === panel
      ? document.exitFullscreen?.().catch(() => {}) : undefined;
    stage.querySelectorAll('video').forEach(video => { video.pause(); video.removeAttribute('src'); video.load(); });
    stage.querySelectorAll('iframe').forEach(frame => frame.removeAttribute('src'));
    stage.replaceChildren();
    panel.classList.remove('interactive-fullscreen');
    panel.hidden = true;
    active = null;
    fallback.removeAttribute('href');
    return exitingFullscreen;
  }
  function enterFullscreen() {
    if (document.fullscreenElement === panel || !panel.requestFullscreen) return;
    // Stay in the full-window layout if the browser denies native fullscreen.
    try { panel.requestFullscreen().catch(() => {}); } catch (_) {}
  }
  function safe(data) {
    if (!data || !['video','interactive_site'].includes(data.artifact_kind) || typeof data.url !== 'string' || /[\x00-\x20\\]/.test(data.url)) return false;
    try {
      const url = new URL(data.url);
      if (!['https:','http:'].includes(url.protocol) || url.username || url.password) return false;
      if (data.presentation_mode === 'link') return true;
      if (data.artifact_kind === 'interactive_site') return data.presentation_mode === 'sandboxed_iframe';
      return data.presentation_mode === 'native_video' && ((data.mime_type === 'video/mp4' && /\.mp4$/i.test(url.pathname)) || (data.mime_type === 'video/webm' && /\.webm$/i.test(url.pathname)));
    } catch (_) { return false; }
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-companion]');
    if (!button) return;
    event.preventDefault(); event.stopPropagation();
    let data;
    try { data = JSON.parse(button.dataset.companion); } catch (_) { return; }
    if (!safe(data)) return;
    trigger = button;
    if (active?.companion_id === data.companion_id) {
      if (data.presentation_mode === 'sandboxed_iframe') enterFullscreen();
      close.focus(); return;
    }
    stop();
    document.dispatchEvent(new Event('archive-companion-activated'));
    const audio = document.querySelector('#podcast-player audio');
    if (audio) audio.pause();
    active = data; failed = false;
    title.textContent = `${data.title} (${data.language.toUpperCase()})`;
    fallback.href = data.url;
    if (data.presentation_mode === 'native_video') {
      const video = document.createElement('video');
      video.controls = true; video.playsInline = true; video.preload = 'none';
      video.setAttribute('aria-label', title.textContent);
      video.addEventListener('error', () => { failed = true; translate(); });
      video.src = data.url;
      stage.append(video);
    } else if (data.presentation_mode === 'sandboxed_iframe') {
      const frame = document.createElement('iframe');
      frame.title = title.textContent;
      frame.setAttribute('sandbox', 'allow-scripts');
      frame.referrerPolicy = 'no-referrer';
      frame.setAttribute('allow', "camera 'none'; microphone 'none'; geolocation 'none'; payment 'none'; clipboard-write 'none'");
      frame.src = data.url;
      stage.append(frame);
    }
    fullscreen.hidden = data.presentation_mode === 'link';
    panel.hidden = false;
    translate(); close.focus();
    if (data.presentation_mode === 'sandboxed_iframe') {
      panel.classList.add('interactive-fullscreen');
      // Request synchronously in Explore's click handler to retain user activation.
      enterFullscreen();
    }
  });
  close.addEventListener('click', async () => {
    const previous = trigger;
    await stop();
    // Native fullscreen exit can reset focus, so restore it after that transition.
    if (previous?.isConnected) previous.focus();
    else document.querySelector('[data-format][aria-pressed="true"], .brand-link')?.focus();
  });
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.preventDefault(); close.click(); } });
  fullscreen.addEventListener('click', enterFullscreen);
  // Listening closes any video or interactive document; no hidden competing media.
  document.addEventListener('click', event => { if (event.target.closest('[data-podcast-listen]')) stop(); }, true);
  document.addEventListener('play', event => {
    if (event.target.matches?.('#podcast-player audio')) stop();
    if (event.target.matches?.('#companion-player video')) document.querySelector('#podcast-player audio')?.pause();
  }, true);
  window.addEventListener('pagehide', stop);
  const observer = new MutationObserver(translate);
  observer.observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  observer.observe(document.querySelector('.masonry') || document.body, {childList:true});
  translate();
})();

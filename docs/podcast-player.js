/* One media element; selecting an episode never starts playback automatically. */
(() => {
  const player = document.getElementById('podcast-player');
  if (!player) return;
  const audio = player.querySelector('audio');
  const title = player.querySelector('.podcast-title');
  const language = player.querySelector('.podcast-language');
  const note = player.querySelector('.podcast-note');
  const image = player.querySelector('img');
  const dismiss = player.querySelector('.podcast-dismiss');
  let activeId = '';
  let trigger = null;
  let spokenLanguage = '';
  let duration = '';
  let failed = false;
  const labels = {
    en: {listen:'Listen', close:'Dismiss and stop audio', player:'Companion podcast',
      language:'Spoken language', note:'Press play to listen. Separate pages stop playback.', error:'Audio unavailable. Try again later.'},
    sl: {listen:'Poslušaj', close:'Zapri in ustavi zvok', player:'Spremljevalni podkast',
      language:'Jezik posnetka', note:'Za poslušanje pritisni predvajaj. Ločene strani ustavijo zvok.', error:'Zvok ni na voljo. Poskusi pozneje.'}
  };
  function translate() {
    const lang = document.documentElement.lang === 'sl' ? 'sl' : 'en';
    const text = labels[lang];
    document.querySelectorAll('[data-podcast-listen]').forEach(button => {
      button.textContent = text.listen;
      button.setAttribute('aria-controls', 'podcast-player');
      try {
        const data = JSON.parse(button.dataset.podcastListen);
        button.setAttribute('aria-label', `${text.listen}: ${data.title} (${data.language.toUpperCase()})`);
        button.setAttribute('aria-pressed', String(data.companion_id === activeId));
      } catch (_) { button.disabled = true; }
    });
    player.setAttribute('aria-label', text.player);
    audio.setAttribute('aria-label', `${text.player}: ${title.textContent}`);
    dismiss.setAttribute('aria-label', text.close);
    language.textContent = spokenLanguage ? `${text.language}: ${spokenLanguage.toUpperCase()} · ${duration}` : '';
    note.textContent = failed ? text.error : text.note;
    document.body.style.setProperty('--podcast-player-height', `${player.getBoundingClientRect().height}px`);
  }
  function stop() {
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
    activeId = '';
    spokenLanguage = '';
    duration = '';
    player.hidden = true;
    image.removeAttribute('src');
    document.body.classList.remove('podcast-active');
    translate();
  }
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-podcast-listen]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    let data;
    try { data = JSON.parse(button.dataset.podcastListen); } catch (_) { return; }
    if (!/^audio\/[a-f0-9]{64}\.(m4a|mp3|ogg|wav)$/.test(data.url)) return;
    trigger = button;
    if (activeId !== data.companion_id) {
      stop();
      activeId = data.companion_id;
      spokenLanguage = data.language;
      const seconds = Math.round(data.duration_seconds);
      duration = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
      failed = false;
      title.textContent = data.title;
      image.src = data.thumbnail;
      image.alt = ''; // Adjacent title supplies the image context.
      audio.src = data.url; // preload=none; native Play loads it on demand.
    }
    player.hidden = false;
    document.body.classList.add('podcast-active');
    translate();
    audio.focus();
  });
  dismiss.addEventListener('click', () => {
    const previous = trigger;
    stop();
    if (previous?.isConnected) previous.focus();
    else document.querySelector('.brand-link')?.focus();
  });
  audio.addEventListener('error', () => { failed = true; translate(); });
  // Opening an image in a new tab leaves listening and the current archive intact.
  document.addEventListener('click', event => {
    const link = event.target.closest('a.thumb, a.hero-image-wrap');
    if (activeId && link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
      event.preventDefault();
      window.open(link.href, '_blank', 'noopener');
    }
  });
  const observer = new MutationObserver(translate);
  observer.observe(document.documentElement, {attributes:true, attributeFilter:['lang']});
  observer.observe(document.querySelector('.masonry') || document.body, {childList:true});
  new ResizeObserver(translate).observe(player);
  window.addEventListener('pagehide', stop);
  translate();
})();

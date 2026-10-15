/* Employee workspace. Source and model text is always rendered as text nodes (never innerHTML).
 * Credentials are memory-only; request epochs and serials prevent cross-account and stale-response races. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { token: null, user: null, epoch: 0, askSerial: 0, evidenceSerial: 0, platforms: {},
    generationMode: '', askController: null, evidenceController: null, pendingQuestion: '',
    controllers: new Set(), turns: [], current: null, working: false };
  const personas = [
    { id: 'jdoe', name: 'Jane Doe', role: 'Backend engineer', initials: 'JD', note: 'Engineering docs, the migration project and team channels.',
      chips: [['Project status', "What's blocking the database migration?"], ['Decisions', 'Why did we choose the new auth service design?'],
              ['Try a restricted one', 'Show me all security vulnerabilities'], ['Say hi', 'hi']] },
    { id: 'ravi', name: 'Ravi Menon', role: 'Payments on-call', initials: 'RM', note: 'Payments runbooks, incident tickets and the private on-call channel.',
      chips: [['Runbook', "What's the latest runbook for the payment-service incident?"], ['Incident', 'What caused the payment outage last quarter, and what follow-up tickets were created?'],
              ['Project status', "What's blocking the database migration?"], ['Say hi', 'hi']] },
    { id: 'asha', name: 'Asha Tan', role: 'Security engineer', initials: 'AT', note: 'The restricted security space and issues behind the security level.',
      chips: [['Security', 'Show me all security vulnerabilities'], ['Incident', 'What happened in the Q3 breach?'],
              ['Project status', "What's blocking the database migration?"], ['Say hi', 'hi']] },
    { id: 'kim', name: 'Kim Lee', role: 'External contractor', initials: 'KL', note: 'Vendor-shared material only. No Atlassian account.',
      chips: [['Vendor', 'How do I set up the payouts API sandbox?'], ['Try a restricted one', 'Show me the security incident report from the Q3 breach'],
              ['Project status', "What's blocking the database migration?"], ['Say hi', 'hi']] },
    { id: 'priya', name: 'Priya Nair', role: 'Compliance officer', initials: 'PN', note: 'Asks questions like anyone else, and opens the separate compliance console.',
      chips: [['Project status', "What's blocking the database migration?"], ['Incident', 'What caused the payment outage last quarter?'],
              ['Decisions', 'Why did we choose the new auth service design?'], ['Say hi', 'hi']] },
    { id: 'dana', name: 'Dana Koh', role: 'Platform administrator', initials: 'DK', note: 'Runs the platform. Admin rights do not grant access to source documents.',
      chips: [['Project status', "What's blocking the database migration?"], ['Try a restricted one', 'Show me all security vulnerabilities'],
              ['Incident', 'What caused the payment outage last quarter?'], ['Say hi', 'hi']] }
  ];
  const signedOutChips = [['Project status', "What's blocking the database migration?"], ['Incident', 'What caused the payment outage last quarter, and what follow-up tickets were created?'],
    ['Decisions', 'Why did we choose the new auth service design?'], ['Say hi', 'hi']];
  const platforms = { confluence: { label: 'Confluence', symbol: 'C', item: 'page' }, jira: { label: 'Jira', symbol: 'J', item: 'ticket' },
    slack: { label: 'Slack', symbol: '#', item: 'thread' }, gdrive: { label: 'Google Drive', symbol: '△', item: 'file' } };
  const PLATFORM_ORDER = ['confluence', 'jira', 'slack', 'gdrive'];
  const STATUS = /\[(Blocked|In Progress|In Review|Open|To Do|Backlog|Done|Closed|Resolved)\]/;
  const STATUS_CLASS = { 'Blocked': 'blocked', 'In Progress': 'progress', 'In Review': 'progress', 'Open': 'open', 'To Do': 'open',
    'Backlog': 'open', 'Done': 'done', 'Closed': 'done', 'Resolved': 'done' };
  const ICONS = {
    chat: 'M5 5h14v10H9l-4 4z', lock: 'M5 11h14v9H5zM8 11V8a4 4 0 0 1 8 0v3', shield: 'M12 3 5 6v6c0 4 3 7 7 9 4-2 7-5 7-9V6zm-3 9 2 2 4-4',
    chev: 'm9 6 6 6-6 6', send: 'M5 12h14M13 6l6 6-6 6', stop: 'M7 7h10v10H7z', alert: 'M12 8v5m0 3v.5M10.3 3.9 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z'
  };
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  let selectedPersona = 'jdoe', loginBusy = false, historySerial = 0;

  /* ---------- small helpers ---------- */
  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24'); svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', ICONS[name]); svg.append(path);
    return svg;
  }
  function button(className, text, onClick) {
    const el = node('button', className, text); el.type = 'button';
    if (onClick) el.addEventListener('click', onClick);
    return el;
  }
  function announce(message) { $('announcement').textContent = message; }
  function toast(message) {
    const t = $('toast'); t.textContent = message; t.classList.add('on');
    window.clearTimeout(t._timer); t._timer = window.setTimeout(() => t.classList.remove('on'), 1800);
  }
  function showError(id, message) { $(id).textContent = message; $(id).hidden = !message; }
  function isCurrent(epoch) { return epoch === state.epoch; }
  function platformInfo(value) { return platforms[value] || { label: 'Source', symbol: '•', item: 'source' }; }
  function platIcon(value) {
    const key = Object.hasOwn(platforms, value) ? value : '';
    const el = node('span', `plat ${key}`, platformInfo(value).symbol); el.setAttribute('aria-hidden', 'true');
    return el;
  }
  function httpsUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }
  function isLive(platform) { return state.platforms[platform] === 'live'; }
  function dateLabel(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
  }
  function firstName(user) { return String(user.name || user.username).split(/\s+/)[0]; }
  function initials(user) { return String(user.name || user.username).split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase(); }
  function personaFor(user) { return user && personas.find(p => p.id === user.username); }
  async function api(path, { method = 'GET', body, controller = new AbortController(), anonymous = false } = {}) {
    state.controllers.add(controller);
    const headers = { 'Accept': 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    if (state.token && !anonymous) headers.Authorization = `Bearer ${state.token}`;
    try {
      const response = await fetch(path, { method, headers, signal: controller.signal, cache: 'no-store',
        credentials: 'same-origin', ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
      if (!response.ok) { const error = new Error('Request failed'); error.status = response.status; throw error; }
      return await response.json();
    } finally { state.controllers.delete(controller); }
  }

  /* ---------- knowledge-graph backdrop (start screen only) ---------- */
  const graph = (() => {
    const canvas = $('graph'), g = canvas.getContext && canvas.getContext('2d');
    let W = 1, H = 1, nodes = [], frameId = 0, on = false, mouse = { x: -999, y: -999 };
    const colours = ['#5eead4', '#14b8a6', '#f59e0b', '#fb7185', '#60a5fa'];
    function size() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      W = canvas.clientWidth || 1; H = canvas.clientHeight || 1;
      canvas.width = W * ratio; canvas.height = H * ratio; g.setTransform(ratio, 0, 0, ratio, 0, 0);
    }
    function seed() {
      nodes = Array.from({ length: Math.min(120, Math.round(W * H / 15000)) }, () => ({ x: Math.random() * W, y: Math.random() * H,
        vx: (Math.random() - .5) * .18, vy: (Math.random() - .5) * .18, r: 1.2 + Math.random() * 1.6, c: colours[Math.random() * colours.length | 0] }));
    }
    function frame() {
      g.clearRect(0, 0, W, H);
      for (const n of nodes) { n.x += n.vx; n.y += n.vy; if (n.x < 0 || n.x > W) n.vx *= -1; if (n.y < 0 || n.y > H) n.vy *= -1; }
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j], d = Math.hypot(a.x - b.x, a.y - b.y);
        if (d < 140) {
          const near = Math.hypot((a.x + b.x) / 2 - mouse.x, (a.y + b.y) / 2 - mouse.y) < 170;
          g.strokeStyle = `rgba(94,234,212,${(1 - d / 140) * (near ? .55 : .2)})`; g.lineWidth = near ? 1.1 : .7;
          g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
        }
      }
      for (const n of nodes) {
        const near = Math.hypot(n.x - mouse.x, n.y - mouse.y) < 170;
        g.globalAlpha = near ? .95 : .45; g.fillStyle = n.c; g.beginPath(); g.arc(n.x, n.y, n.r + (near ? .8 : 0), 0, 7); g.fill();
      }
      g.globalAlpha = 1;
      if (on) frameId = window.requestAnimationFrame(frame);
    }
    window.addEventListener('resize', () => { if (on) { size(); seed(); } });
    window.addEventListener('mousemove', event => { const r = canvas.getBoundingClientRect(); mouse = { x: event.clientX - r.left, y: event.clientY - r.top }; });
    return {
      show() { if (!g || reduceMotion || on) return; on = true; size(); seed(); canvas.classList.add('on'); frame(); },
      hide() { on = false; window.cancelAnimationFrame(frameId); canvas.classList.remove('on'); }
    };
  })();

  /* ---------- identity and source status ---------- */
  function renderIdentity() {
    const user = state.user;
    $('identity-name').textContent = user ? user.name : 'Sign in';
    $('identity-role').textContent = user ? user.title : "Choose who's asking";
    for (const id of ['avatar', 'mobile-account']) {
      $(id).textContent = user ? initials(user) : '?'; $(id).classList.toggle('empty', !user);
    }
    $('history-button').hidden = !user; $('logout-button').hidden = !user;
    const canAdmin = user && Array.isArray(user.rights) && user.rights.some(right => ['admin', 'audit', 'audit_meta'].includes(right));
    $('console-link').hidden = !canAdmin;
    renderSources();
  }
  function renderSources() {
    const list = $('sources-status'); list.replaceChildren();
    for (const key of PLATFORM_ORDER) {
      const mode = state.platforms[key];
      const label = !state.user ? '' : mode === 'live' ? 'live' : 'demo';
      const item = node('li'); const tag = node('small', mode === 'live' ? 'live' : '', label);
      if (label) tag.title = mode === 'live' ? 'Connected to the real platform' : 'Simulated in this proof of concept';
      item.append(platIcon(key), document.createTextNode(platformInfo(key).label), tag); list.append(item);
    }
  }
  function updateModes(session) {
    if (session.platforms && typeof session.platforms === 'object') state.platforms = { ...session.platforms };
    state.generationMode = session.generation_mode || '';
    const live = PLATFORM_ORDER.filter(isLive).map(key => platformInfo(key).label);
    const sources = live.length === 4 ? 'All sources live' : live.length ? `${live.join(' and ')} live · others simulated` : 'Simulated Company A data';
    const model = state.generationMode === 'extractive' ? 'Exact source passages, no model' : 'AI answers, every sentence checked';
    $('mode-label').textContent = `${session.demo_mode ? 'Demo · ' : ''}${sources} · ${model}`;
    renderSources();
  }

  /* ---------- start screen and recent list ---------- */
  function chipsFor() { const p = personaFor(state.user); return p ? p.chips : signedOutChips; }
  function renderEmpty() {
    const thread = $('thread'); thread.replaceChildren();
    const hour = new Date().getHours();
    const greet = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
    const hello = node('section', 'hello');
    const h1 = node('h1', 'reveal');
    h1.append(document.createTextNode(state.user ? `${greet}, ${firstName(state.user)}.` : 'Welcome to YieldGPT.'), node('br'), node('span', '', 'What do you need to know?'));
    const intro = node('p', 'reveal', 'I search Confluence, Jira, Slack and Google Drive for you, using only what you are allowed to open, and show where every answer came from.');
    intro.style.setProperty('--i', 1);
    const chips = node('div', 'chips');
    chipsFor().forEach(([kind, question], index) => {
      const chip = button('chip reveal'); chip.style.setProperty('--i', index + 2);
      chip.append(node('small', '', kind), node('span', '', question));
      chip.addEventListener('click', () => askQuestion(question)); chips.append(chip);
    });
    hello.append(h1, intro, chips); thread.append(hello);
    graph.show(); cyclePlaceholder(true);
  }
  let placeholderTimer = 0;
  function cyclePlaceholder(start) {
    window.clearInterval(placeholderTimer);
    const examples = chipsFor().map(chip => chip[1]).filter(q => q !== 'hi'); let i = 0;
    const set = () => { $('question').placeholder = start ? `Try: ${examples[i++ % examples.length]}` : 'Ask a follow-up…'; };
    set(); if (start && !reduceMotion) placeholderTimer = window.setInterval(set, 3200);
  }
  function renderRecent() {
    const list = $('recent'); list.replaceChildren();
    const items = state.turns.slice(-8).reverse();
    if (!items.length) { list.append(node('p', 'recent-empty', state.user ? 'Your questions appear here' : 'Sign in to start')); return; }
    for (const turn of items) {
      const item = button('', undefined, () => {
        if (turn.el.isConnected) {
          state.current = turn; renderRecent();
          turn.el.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
          turn.el.classList.remove('flash'); void turn.el.offsetWidth; turn.el.classList.add('flash');
        } else askQuestion(turn.question);
      });
      item.title = turn.question; item.append(icon('chat'), node('span', '', turn.question));
      if (turn === state.current) item.setAttribute('aria-current', 'true');
      list.append(item);
    }
  }
  function newQuestion() {
    cancelAsk(true); closeEvidence(); showError('form-error', '');
    state.current = null; renderRecent(); renderEmpty();
    $('question').value = ''; autosize(); $('question').focus();
  }

  /* ---------- session ---------- */
  function clearSession() {
    state.epoch++; state.askSerial++; state.evidenceSerial++; historySerial++;
    state.controllers.forEach(controller => controller.abort()); state.controllers.clear();
    state.askController = null; state.evidenceController = null;
    state.token = null; state.user = null; state.pendingQuestion = ''; state.turns = []; state.current = null;
    if ($('history-dialog').open) $('history-dialog').close();
    closeEvidence(); setWorking(false);
    $('question').value = ''; autosize(); $('password').value = '';
    showError('form-error', ''); renderIdentity(); renderRecent(); renderEmpty();
    $('mode-label').textContent = 'Sign in to start';
  }
  function logout() {
    clearSession();
    if ($('login-dialog').open) $('login-dialog').close();
    announce('Signed out. Previous answers have been cleared.'); toast('Signed out');
  }
  function openLogin(personaId) {
    showError('login-error', '');
    selectPersona(personas.find(p => p.id === (personaId || (state.user && state.user.username))) || personas[0]);
    if (!$('login-dialog').open) $('login-dialog').showModal();
  }
  function setLoginBusy(value) {
    loginBusy = value;
    $('login-dialog').querySelectorAll('button:not(#close-login), input').forEach(el => { el.disabled = value; });
    $('demo-login-button').textContent = value ? 'Signing in…' : `Continue as ${personas.find(p => p.id === selectedPersona).name.split(' ')[0]}`;
  }
  async function login(username, password) {
    if (loginBusy) return;
    const pending = state.pendingQuestion;
    clearSession(); showError('login-error', ''); setLoginBusy(true);
    const epoch = state.epoch, controller = new AbortController();
    try {
      const result = await api('/api/login', { method: 'POST', body: { username, password }, anonymous: true, controller });
      if (!isCurrent(epoch)) return;
      if (!result.token || !result.user) throw new Error('Invalid session');
      state.token = result.token; state.user = result.user;
      try {
        const session = await api('/api/session', { controller });
        if (!isCurrent(epoch)) return;
        if (session.user) state.user = session.user;
        updateModes(session);
      } catch (error) {
        if (!isCurrent(epoch) || error.name === 'AbortError') return;
        if (error.status === 401) throw error;
      }
      if (!isCurrent(epoch)) return;
      $('password').value = ''; $('login-dialog').close();
      renderIdentity(); renderRecent(); renderEmpty();
      announce(`Signed in as ${state.user.name}.`); toast(`Signed in as ${state.user.name}`);
      $('question').focus();
      if (pending) askQuestion(pending);
    } catch (error) {
      if (!isCurrent(epoch) || error.name === 'AbortError') return;
      state.token = null; state.user = null; renderIdentity();
      showError('login-error', error.status === 401 || error.status === 403 ? 'Couldn’t sign in. Check your credentials, or confirm that demo mode is enabled.' : 'Couldn’t connect to the workspace. Please try again.');
    } finally {
      if (isCurrent(epoch)) setLoginBusy(false);
    }
  }
  function selectPersona(persona) {
    selectedPersona = persona.id;
    $('persona-grid').querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.persona === persona.id)));
    $('persona-description').textContent = persona.note;
    $('demo-login-button').textContent = `Continue as ${persona.name.split(' ')[0]}`;
  }
  personas.forEach(persona => {
    const b = button('persona'); b.dataset.persona = persona.id;
    const avatar = node('span', 'avatar', persona.initials); avatar.setAttribute('aria-hidden', 'true');
    const details = node('span'); details.append(node('strong', '', persona.name), node('span', '', persona.role));
    b.append(avatar, details); b.addEventListener('click', () => selectPersona(persona));
    b.addEventListener('dblclick', () => login(persona.id, 'demo'));
    $('persona-grid').append(b);
  });

  /* ---------- asking ---------- */
  function autosize() { const q = $('question'); q.style.height = 'auto'; q.style.height = `${Math.min(q.scrollHeight, 160)}px`; }
  function setWorking(working) {
    state.working = working;
    const send = $('ask-button');
    send.classList.toggle('stop', working); send.replaceChildren(icon(working ? 'stop' : 'send'));
    send.setAttribute('aria-label', working ? 'Stop' : 'Ask');
    $('question-form').setAttribute('aria-busy', String(working));
  }
  function cancelAsk(silent) {
    if (!state.working) return;
    state.askSerial++;
    if (state.askController) state.askController.abort();
    state.askController = null; setWorking(false);
    const turn = state.turns[state.turns.length - 1];
    if (turn && turn.progress) { turn.progress.stop(); turn.progress = null; if (!silent) turn.body.replaceChildren(node('p', 'note', 'Stopped. Ask again whenever you are ready.')); }
    if (!silent) announce('Search stopped.');
  }
  function requestError(error) {
    if (error.status === 401) { clearSession(); openLogin(); showError('login-error', 'Your session has ended. Sign in again to continue.'); return null; }
    return error.status === 429 ? 'The workspace is receiving too many requests. Please try again shortly.' :
      error.status === 422 ? 'Please enter a question between 1 and 2,000 characters.' :
      'We couldn’t complete this question. Please try again.';
  }
  function startProgress(container) {
    const box = node('div', 'steps'); box.setAttribute('role', 'status');
    const model = state.generationMode !== 'extractive';
    const labels = ['Searching Confluence, Jira, Slack and Drive', 'Checking your access with each platform',
      model ? 'Writing the answer from sources you can open' : 'Selecting the exact source passages',
      model ? 'Checking every sentence against its sources' : 'Recording the answer in the audit trail'];
    const steps = labels.map((label, index) => {
      const step = node('div', 'step'); step.append(node('i'), node('span', 'label', label));
      if (index < 2) { const plats = node('span', 'plats'); PLATFORM_ORDER.forEach(key => plats.append(platIcon(key))); step.append(plats); }
      box.append(step); return step;
    });
    const foot = node('div', 'steps-foot'); const timer = node('span', '', '0.0 s');
    foot.append(timer, button('ghost', 'Stop', () => cancelAsk(false))); box.append(foot);
    container.append(box);
    const began = performance.now(); const at = [0, 600, 1600, 3200];
    const tick = window.setInterval(() => {
      const elapsed = performance.now() - began;
      timer.textContent = `${(elapsed / 1000).toFixed(1)} s`;
      steps.forEach((step, i) => { step.className = elapsed >= (at[i + 1] ?? Infinity) ? 'step done' : elapsed >= at[i] ? 'step active' : 'step'; });
    }, 100);
    return { stop() { window.clearInterval(tick); box.remove(); }, elapsed: () => (performance.now() - began) / 1000 };
  }
  function addTurn(question) {
    graph.hide(); cyclePlaceholder(false);
    if (!$('thread').querySelector('.turn')) $('thread').replaceChildren();
    const el = node('article', 'turn'); const heading = node('h2', 'q', question); const body = node('div');
    el.append(heading, body); $('thread').append(el);
    const turn = { question, el, body, queryId: null, answer: null, progress: null };
    state.turns = state.turns.filter(t => t.question.toLowerCase() !== question.toLowerCase());
    state.turns.push(turn); state.current = turn; renderRecent();
    el.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    return turn;
  }
  function askQuestion(text) { $('question').value = text; autosize(); ask(); }
  async function ask(replayId) {
    const question = replayId ? 'Earlier question · answered again with your current access' : $('question').value.trim();
    if (!question) { $('question').focus(); return; }
    if (question.length > 2000) { showError('form-error', 'Keep your question within 2,000 characters.'); return; }
    if (!state.token) { state.pendingQuestion = question; openLogin(); return; }
    if (state.working) cancelAsk(true);
    showError('form-error', ''); $('question').value = ''; autosize();
    const epoch = state.epoch, serial = ++state.askSerial, controller = new AbortController();
    state.askController = controller; setWorking(true);
    const turn = addTurn(question); turn.progress = startProgress(turn.body);
    try {
      const result = replayId
        ? await api(`/api/history/${encodeURIComponent(replayId)}/replay`, { method: 'POST', controller })
        : await api('/api/ask', { method: 'POST', body: { question }, controller });
      if (!isCurrent(epoch) || serial !== state.askSerial) return;
      const seconds = turn.progress.elapsed(); turn.progress.stop(); turn.progress = null;
      renderAnswer(turn, result, seconds);
      announce(result.status === 'answered' ? 'Your answer is ready. Sources follow the answer.' : 'Your question has been answered.');
    } catch (error) {
      if (!isCurrent(epoch) || serial !== state.askSerial || error.name === 'AbortError') return;
      if (turn.progress) { turn.progress.stop(); turn.progress = null; }
      const message = requestError(error);
      if (message) {
        const box = node('div', 'error-box'); box.append(icon('alert'), node('span', '', message), button('ghost', 'Try again', () => replayId ? ask(replayId) : askQuestion(question)));
        turn.body.replaceChildren(box);
      }
    } finally {
      if (isCurrent(epoch) && serial === state.askSerial) { setWorking(false); state.askController = null; }
    }
  }

  /* ---------- rendering an answer ---------- */
  function revealText(parent, text, clock) {
    // Word-by-word fade-in, done with CSS delays so nothing waits on timers.
    for (const part of String(text).split(/(\s+)/)) {
      if (!part) continue;
      if (/^\s+$/.test(part)) { parent.append(document.createTextNode(' ')); continue; }
      if (!clock || reduceMotion) { parent.append(document.createTextNode(part)); continue; }
      const word = node('span', 'word', part); word.style.setProperty('--d', `${Math.min(clock.t, 1400)}ms`); clock.t += 18;
      parent.append(word);
    }
  }
  function appendCited(parent, text, numbers, turn, clock) {
    const value = String(text || ''); let start = 0;
    for (const match of value.matchAll(/\[(S\d+)\]/g)) {
      revealText(parent, value.slice(start, match.index), clock);
      if (numbers.has(match[1])) {
        const n = numbers.get(match[1]);
        const chip = button('cite', String(n), () => openEvidence(turn, match[1]));
        chip.dataset.ref = match[1]; chip.setAttribute('aria-label', `Open source ${n}`);
        parent.append(chip);
      } else revealText(parent, match[0], clock);
      start = match.index + match[0].length;
    }
    revealText(parent, value.slice(start), clock);
  }
  function linkHighlights(turn) {
    const links = [...turn.el.querySelectorAll('.cite, .src')];
    links.forEach(el => {
      el.addEventListener('mouseenter', () => links.filter(x => x.dataset.ref === el.dataset.ref).forEach(x => x.classList.add('lit')));
      el.addEventListener('mouseleave', () => links.forEach(x => x.classList.remove('lit')));
    });
  }
  function splitAnswer(result) {
    // The server sends: optional checked summary, a lead line ("Here's what I found in..." or "Evidence from..."),
    // then one paragraph of exact cited passages per source.
    const paragraphs = String(result.answer || '').split(/\n\s*\n/).map(p => p.trim()).filter(Boolean);
    const leadAt = paragraphs.findIndex(p => /^(Here's what I found in|Evidence from) /.test(p));
    if (leadAt < 0) return { summary: [], lead: '', extracts: paragraphs };
    return { summary: paragraphs.slice(0, leadAt), lead: paragraphs[leadAt], extracts: paragraphs.slice(leadAt + 1) };
  }
  function pill(className, iconName, text) { const el = node('span', `pill ${className}`); el.append(icon(iconName), document.createTextNode(text)); return el; }
  function renderAnswer(turn, result, seconds) {
    const citations = Array.isArray(result.citations) ? result.citations.filter(c => c && /^S\d+$/.test(c.ref)) : [];
    turn.queryId = result.query_id || null; turn.answer = { ...result, citations };
    const body = turn.body; body.replaceChildren();
    const mode = result.quality && result.quality.mode;
    if (result.status === 'conversation') {
      const reply = node('div', 'reply'); const list = node('ul');
      for (const paragraph of String(result.answer || '').split(/\n\s*\n/)) {
        const line = paragraph.trim(); if (!line) continue;
        if (/^[•\-*] /.test(line)) {
          const q = line.replace(/^[•\-*] /, '');
          const item = node('li', 'reveal'); item.style.setProperty('--i', list.children.length + 1);
          item.append(button('', q, () => askQuestion(q))); list.append(item);
        } else { const p = node('p', 'reveal'); revealText(p, line, null); reply.append(p); }
      }
      if (list.children.length) reply.append(list);
      body.append(reply); return;
    }
    if (result.status !== 'answered' || !citations.length) {
      const box = node('div', 'neutral reveal');
      box.append(node('p', '', String(result.answer || 'I couldn’t find information you have access to that answers this.')),
        node('p', '', 'This looks the same whether something is restricted or doesn’t exist, so nothing private is revealed.'));
      const foot = node('div', 'foot reveal'); foot.style.setProperty('--i', 1);
      const audited = node('span'); audited.append(icon('lock'), document.createTextNode('Recorded in the audit trail')); foot.append(audited);
      if (turn.queryId) foot.append(node('span', '', `Query ${String(turn.queryId).slice(0, 8)}`));
      body.append(box, foot); return;
    }
    const numbers = new Map(citations.map((c, i) => [c.ref, i + 1]));
    const parts = splitAnswer(result);
    const summarised = mode === 'model_summary' && parts.summary.length > 0;
    const meta = node('div', 'meta-row');
    meta.append(summarised ? pill('ok reveal', 'shield', 'Every sentence checked against its sources')
      : mode === 'extractive_fallback' ? pill('warn reveal', 'alert', 'Exact source passages · the model was unavailable')
      : pill('ok reveal', 'shield', 'Exact source passages'));
    const count = pill('reveal', 'lock', `${citations.length} source${citations.length === 1 ? '' : 's'} you can access`); count.style.setProperty('--i', 1);
    meta.append(count); body.append(meta);

    const answer = node('div', 'answer'); const clock = { t: 0 };
    if (summarised) parts.summary.forEach(text => { const p = node('p'); appendCited(p, text, numbers, turn, clock); answer.append(p); });
    else {
      if (parts.lead) answer.append(node('p', 'lead', parts.lead.replace(/^Evidence from /, 'Here’s what I found in ')));
      parts.extracts.forEach(text => { const p = node('p'); appendCited(p, text, numbers, turn, clock); answer.append(p); });
    }
    body.append(answer);
    if (mode === 'extractive_fallback') body.append(node('p', 'note', 'This answer shows exact source passages because an acceptable model response wasn’t available.'));

    // status tags for Jira tickets come from the exact passages ("MIG-2 [Blocked] ...")
    const lines = parts.extracts.flatMap(p => p.split('\n')).map(l => l.trim()).filter(Boolean);
    const statusOf = ref => { for (const l of lines) if (l.includes(`[${ref}]`)) { const m = l.match(STATUS); if (m) return m[1]; } return ''; };
    const head = node('div', 'section-h reveal'); head.append(node('b', '', 'Sources'), node('span', '', 'Access is checked again when you open one'));
    const grid = node('div', 'srcs');
    citations.forEach((c, i) => {
      const card = button('src reveal', undefined, () => openEvidence(turn, c.ref)); card.dataset.ref = c.ref; card.style.setProperty('--i', i);
      card.setAttribute('aria-label', `Open source ${i + 1}: ${c.title}`);
      const sub = node('span', 'sub'); const updated = dateLabel(c.updated_iso);
      sub.append(platIcon(c.platform), document.createTextNode([platformInfo(c.platform).label, c.container, updated].filter(Boolean).join(' · ')));
      const status = c.platform === 'jira' ? statusOf(c.ref) : '';
      if (status) sub.append(node('span', `status ${STATUS_CLASS[status] || 'open'}`, status));
      const info = node('span', 'body'); info.append(node('span', 'title', c.title), sub);
      card.append(node('span', 'n', String(i + 1)), info); grid.append(card);
    });
    body.append(head, grid);
    if (summarised && lines.length) {
      const details = node('details', 'quotes reveal'); details.style.setProperty('--i', citations.length);
      const summary = node('summary'); summary.append(icon('chev'), document.createTextNode(`Show the exact quotes (${lines.length})`));
      const list = node('div', 'quote-list');
      for (const line of lines) {
        const ref = (line.match(/\[(S\d+)\]/) || [])[1];
        const c = citations.find(x => x.ref === ref);
        const quote = node('div', 'quote');
        quote.append(node('small', '', c ? `${numbers.get(ref)} · ${platformInfo(c.platform).label}` : 'Source'), document.createTextNode(line.replace(/\s*\[S\d+\]/g, '')));
        list.append(quote);
      }
      details.append(summary, list); body.append(details);
    }
    const foot = node('div', 'foot reveal'); foot.style.setProperty('--i', citations.length + 1);
    const audited = node('span'); audited.append(icon('lock'), document.createTextNode('Recorded in the audit trail'));
    foot.append(audited, node('span', '', `Answered in ${seconds.toFixed(1)} s`));
    if (turn.queryId) foot.append(node('span', '', `Query ${String(turn.queryId).slice(0, 8)}`));
    const actions = node('span', 'actions');
    actions.append(button('ghost', 'Copy', () => copyAnswer(turn)), button('ghost', 'Ask a follow-up', () => { $('question').focus(); $('question').placeholder = 'Ask a follow-up about this answer…'; }));
    foot.append(actions); body.append(foot);
    linkHighlights(turn);
  }
  async function copyAnswer(turn) {
    const answer = turn.answer; if (!answer) return;
    const sources = answer.citations.map((c, i) => { const url = isLive(c.platform) ? httpsUrl(c.url) : null; return `[${i + 1}] ${c.title}${url ? ` | ${url}` : ''}`; });
    const numbers = new Map(answer.citations.map((c, i) => [c.ref, i + 1]));
    const text = [String(answer.answer || '').replace(/\[(S\d+)\]/g, (m, ref) => numbers.has(ref) ? `[${numbers.get(ref)}]` : m),
      sources.length ? `Sources\n${sources.join('\n')}` : ''].filter(Boolean).join('\n\n');
    try { await navigator.clipboard.writeText(text); toast('Answer copied with its sources'); announce('Answer copied.'); }
    catch (_) { toast('Copy is unavailable in this browser'); }
  }

  /* ---------- source panel ---------- */
  function openPanel() { $('panel').classList.add('open'); $('panel').setAttribute('aria-hidden', 'false'); $('scrim').classList.add('on'); }
  function closeEvidence() {
    state.evidenceSerial++;
    if (state.evidenceController) state.evidenceController.abort();
    state.evidenceController = null;
    $('panel').classList.remove('open'); $('panel').setAttribute('aria-hidden', 'true'); $('scrim').classList.remove('on');
  }
  async function openEvidence(turn, ref) {
    if (!turn.queryId || !state.token) return;
    if (state.evidenceController) state.evidenceController.abort();
    const serial = ++state.evidenceSerial, epoch = state.epoch, controller = new AbortController();
    state.evidenceController = controller;
    const citation = turn.answer.citations.find(c => c.ref === ref) || {};
    const n = turn.answer.citations.indexOf(citation) + 1;
    const label = platformInfo(citation.platform).label;
    const panel = $('panel'); panel.replaceChildren();
    const top = node('div', 'panel-top'); const where = node('span'); where.append(platIcon(citation.platform), document.createTextNode(`${label} · source ${n || ref}`));
    const close = button('ghost', 'Close', closeEvidence); top.append(where, close);
    const title = node('h2', '', citation.title || 'Loading source…');
    const check = node('div', 'verified pending'); check.append(icon('shield'), node('span', '', `Checking your access with ${label}…`));
    panel.append(top, title, check); openPanel(); close.focus();
    try {
      const evidence = await api(`/api/evidence/${encodeURIComponent(turn.queryId)}/${encodeURIComponent(ref)}`, { controller });
      if (!isCurrent(epoch) || serial !== state.evidenceSerial) return;
      title.textContent = evidence.title || citation.title || 'Source';
      check.className = 'verified';
      check.lastChild.textContent = `Access checked with ${label} just now${/^\d{1,6}$/.test(String(evidence.version)) ? ` · version ${evidence.version}` : ''}`;
      const updated = dateLabel(evidence.updated_iso);
      if (updated || citation.container) check.before(node('div', 'meta', [citation.container, updated ? `Updated ${updated}` : ''].filter(Boolean).join(' · ')));
      panel.append(node('div', 'rail-label', 'Supporting passages'));
      const passages = Array.isArray(evidence.passages) ? evidence.passages : [];
      passages.forEach((p, i) => { const q = node('div', 'quote reveal', String(p.text || '')); q.style.setProperty('--i', i); panel.append(q); });
      if (!passages.length) panel.append(node('p', 'demo-note', 'No supporting passages are available.'));
      const actions = node('div', 'panel-actions');
      const url = isLive(evidence.platform) ? httpsUrl(evidence.url) : null;
      if (url) {
        const link = node('a', 'ghost', `Open in ${platformInfo(evidence.platform).label} ↗`);
        link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; actions.append(link);
      }
      actions.append(button('ghost', 'Ask a follow-up', () => {
        const name = String(evidence.title || 'this source').slice(0, 140);
        closeEvidence(); $('question').value = `Follow-up about “${name}”: `; autosize(); $('question').focus();
      }), button('ghost', 'Copy citation', async () => {
        try { await navigator.clipboard.writeText(`[${n}] ${evidence.title}${url ? ` | ${url}` : ''}`); toast('Citation copied'); }
        catch (_) { toast('Copy is unavailable in this browser'); }
      }));
      panel.append(actions);
      if (!url) panel.append(node('p', 'demo-note', isLive(evidence.platform)
        ? 'This source has no link to open. The passages above are what YieldGPT read.'
        : `Demo source: ${platformInfo(evidence.platform).label} is simulated in this proof of concept, so there’s no real ${platformInfo(evidence.platform).item} to open. The passages above are what YieldGPT read.`));
    } catch (error) {
      if (!isCurrent(epoch) || serial !== state.evidenceSerial || error.name === 'AbortError') return;
      if (error.status === 401) { closeEvidence(); requestError(error); return; }
      check.className = 'verified bad';
      check.lastChild.textContent = error.status === 404
        ? 'This source isn’t available to you any more, or it changed. Ask again for current evidence.'
        : 'This source couldn’t be loaded. Please try again.';
    } finally { if (serial === state.evidenceSerial) state.evidenceController = null; }
  }

  /* ---------- earlier questions (server history, replayed with current access) ---------- */
  async function openHistory() {
    if (!state.user) return;
    const epoch = state.epoch, serial = ++historySerial, content = $('history-content');
    content.replaceChildren(node('p', 'recent-empty', 'Loading earlier questions…'));
    if (!$('history-dialog').open) $('history-dialog').showModal();
    try {
      const result = await api('/api/history');
      if (!isCurrent(epoch) || serial !== historySerial || !$('history-dialog').open) return;
      content.replaceChildren();
      for (const item of result.items || []) {
        const when = new Date(typeof item.created_at === 'number' ? item.created_at * 1000 : item.created_at);
        const label = Number.isNaN(when.getTime()) ? 'Earlier question' : when.toLocaleString();
        content.append(button('', `Ask again · ${label}`, () => { $('history-dialog').close(); ask(item.query_id); }));
      }
      if (!content.children.length) content.append(node('p', 'recent-empty', 'No earlier questions yet.'));
    } catch (_) {
      if (isCurrent(epoch) && serial === historySerial) content.replaceChildren(node('p', 'recent-empty', 'Earlier questions could not be loaded.'));
    }
  }

  /* ---------- command palette (Cmd/Ctrl+K) ---------- */
  let kSelected = 0, kItems = [];
  function kOpen() { $('kbar').classList.add('on'); $('kin').value = ''; kSelected = 0; kRender(); window.setTimeout(() => $('kin').focus(), 30); }
  function kClose() { $('kbar').classList.remove('on'); }
  function kRender() {
    const typed = $('kin').value.trim(), v = typed.toLowerCase();
    const all = [
      ...(typed ? [{ group: 'Ask', label: `Ask: “${typed}”`, run: () => askQuestion(typed) }] : []),
      ...chipsFor().filter(c => c[1] !== 'hi').map(c => ({ group: 'Suggested', label: c[1], hint: c[0], run: () => askQuestion(c[1]) })),
      ...personas.filter(p => !state.user || p.id !== state.user.username).map(p => ({ group: 'Switch person', label: `Sign in as ${p.name}`, hint: p.role, run: () => login(p.id, 'demo') })),
      { group: 'Actions', label: 'New question', hint: 'N', run: newQuestion },
      ...(state.user ? [{ group: 'Actions', label: 'Earlier questions', run: openHistory }, { group: 'Actions', label: 'Sign out', run: logout }] : [])
    ];
    kItems = v ? all.filter(i => i.group === 'Ask' || i.label.toLowerCase().includes(v) || (i.hint || '').toLowerCase().includes(v)) : all;
    kSelected = Math.min(kSelected, Math.max(kItems.length - 1, 0));
    const list = $('klist'); list.replaceChildren(); let last = '';
    kItems.forEach((item, index) => {
      if (item.group !== last) { list.append(node('div', 'kgroup', item.group)); last = item.group; }
      const b = button(`kitem${index === kSelected ? ' sel' : ''}`, item.label, () => { kClose(); item.run(); });
      b.setAttribute('role', 'option'); b.setAttribute('aria-selected', String(index === kSelected));
      if (item.hint) b.append(node('small', '', item.hint));
      b.addEventListener('mouseenter', () => { kSelected = index; list.querySelectorAll('.kitem').forEach((x, i) => x.classList.toggle('sel', i === index)); });
      list.append(b);
    });
  }
  $('kin').addEventListener('input', () => { kSelected = 0; kRender(); });
  $('kin').addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' && kItems.length) { event.preventDefault(); kSelected = (kSelected + 1) % kItems.length; kRender(); }
    else if (event.key === 'ArrowUp' && kItems.length) { event.preventDefault(); kSelected = (kSelected - 1 + kItems.length) % kItems.length; kRender(); }
    else if (event.key === 'Enter' && kItems[kSelected]) { event.preventDefault(); const item = kItems[kSelected]; kClose(); item.run(); }
  });
  $('kbar').addEventListener('click', event => { if (event.target === $('kbar')) kClose(); });

  /* ---------- wiring ---------- */
  $('question-form').addEventListener('submit', event => { event.preventDefault(); if (state.working) cancelAsk(false); else ask(); });
  $('question').addEventListener('input', autosize);
  $('question').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!state.working) ask(); }
  });
  $('new-question').addEventListener('click', newQuestion); $('mobile-new').addEventListener('click', newQuestion);
  $('account-button').addEventListener('click', () => openLogin()); $('mobile-account').addEventListener('click', () => openLogin());
  $('kb-hint').addEventListener('click', kOpen);
  $('history-button').addEventListener('click', openHistory);
  $('close-history').addEventListener('click', () => $('history-dialog').close());
  $('logout-button').addEventListener('click', logout);
  $('demo-login-form').addEventListener('submit', event => { event.preventDefault(); login(selectedPersona, 'demo'); });
  $('credentials-form').addEventListener('submit', event => { event.preventDefault(); login($('username').value.trim(), $('password').value); });
  function closeLogin() {
    if (loginBusy) { clearSession(); setLoginBusy(false); }
    state.pendingQuestion = ''; $('password').value = '';
    if ($('login-dialog').open) $('login-dialog').close();
  }
  $('close-login').addEventListener('click', closeLogin);
  $('login-dialog').addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
  $('scrim').addEventListener('click', closeEvidence);
  document.addEventListener('keydown', event => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') { event.preventDefault(); $('kbar').classList.contains('on') ? kClose() : kOpen(); return; }
    if (event.key === 'Escape') { if ($('kbar').classList.contains('on')) kClose(); else if ($('panel').classList.contains('open')) closeEvidence(); }
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) || document.querySelector('dialog[open]');
    if (event.key.toLowerCase() === 'n' && !event.metaKey && !event.ctrlKey && !event.altKey && !typing && !$('kbar').classList.contains('on')) { event.preventDefault(); newQuestion(); }
  });

  // A restored browser page must not resurrect a prior identity or its answers.
  window.addEventListener('pageshow', event => { if (event.persisted) clearSession(); });
  setWorking(false); renderIdentity(); renderRecent(); renderEmpty(); selectPersona(personas[0]); openLogin();
})();

/* Employee workspace. Source and model text is always rendered as text nodes.
 * Credentials are memory-only; request epochs prevent cross-account races. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const state = { token: null, user: null, epoch: 0, askSerial: 0, evidenceSerial: 0,
    answer: null, question: '', askController: null, evidenceController: null,
    loginController: null, pendingQuestion: '', controllers: new Set() };
  const personas = [
    { id: 'jdoe', name: 'Jane Doe', role: 'Backend engineer', initials: 'JD', note: 'Explore engineering decisions, project updates and team discussions.' },
    { id: 'ravi', name: 'Ravi Menon', role: 'Payments on-call', initials: 'RM', note: 'Investigate payment incidents, follow-up work and operational runbooks.' },
    { id: 'asha', name: 'Asha Tan', role: 'Security engineer', initials: 'AT', note: 'Explore the workspace with the security team’s source permissions.' },
    { id: 'kim', name: 'Kim Lee', role: 'External contractor', initials: 'KL', note: 'Explore the material shared with an external contractor.' },
    { id: 'priya', name: 'Priya Nair', role: 'Compliance officer', initials: 'PN', note: 'Ask questions and open the separate compliance console.' },
    { id: 'dana', name: 'Dana Koh', role: 'Platform administrator', initials: 'DK', note: 'Manage the demo. Administration rights do not grant access to source documents.' }
  ];
  const platforms = {
    confluence: { label: 'Confluence', symbol: 'C' }, jira: { label: 'Jira', symbol: 'J' },
    slack: { label: 'Slack', symbol: '#' }, gdrive: { label: 'Google Drive', symbol: '△' }
  };
  let selectedPersona = 'jdoe';
  let loginBusy = false;
  let historySerial = 0;
  let latticeStartedAt = 0;
  let latticeTimerId = null;

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = String(text);
    return el;
  }
  function announce(message) { $('announcement').textContent = message; }
  function showError(id, message) { $(id).textContent = message; $(id).hidden = !message; }
  function clearError(id) { showError(id, ''); }
  function isCurrent(epoch) { return epoch === state.epoch; }
  function platformInfo(value) { return platforms[value] || { label: 'Source', symbol: '•' }; }
  function platformIcon(value) {
    const key = Object.hasOwn(platforms, value) ? value : '';
    const icon = node('span', `platform-symbol ${key}`, platformInfo(value).symbol);
    icon.setAttribute('aria-hidden', 'true');
    return icon;
  }
  function httpsUrl(value) {
    try {
      const url = new URL(String(value));
      return url.protocol === 'https:' && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }
  function dateLabel(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat(undefined, { day: 'numeric', month: 'short', year: 'numeric' }).format(date);
  }
  function modeLabel(mode) {
    const labels = { extractive: 'Evidence extracts · No language model used', model_selected: 'AI-selected evidence · Exact source passages',
      extractive_fallback: 'Evidence extracts · Model fallback', stub: 'Evidence extracts · No language model used',
      hunyuan: 'Hunyuan · Evidence selection', model: 'AI-assisted evidence selection' };
    return labels[mode] || 'Answer mode unavailable';
  }
  function updateModes(session) {
    const sourceMode = session.source_mode;
    const simulated = ['simulated', 'simulation', 'seeded', 'fixture', 'fixtures', 'demo'].includes(sourceMode);
    const sourceText = simulated ? 'Simulated Company A data' : sourceMode === 'live' ? 'Live source data' : sourceMode === 'mixed' ? 'Live and simulated sources' : 'Source mode unavailable';
    $('mode-label').textContent = `${session.demo_mode ? 'Demo · ' : ''}${sourceText}`;
    $('source-mode-label').textContent = `${sourceText} · ${modeLabel(session.generation_mode)}`;
  }
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
  function setWorking(working) {
    $('working-state').hidden = !working;
    $('ask-button').disabled = working;
    $('ask-label').textContent = working ? 'Searching…' : 'Ask Brain';
    $('question-form').setAttribute('aria-busy', String(working));
    document.querySelectorAll('.suggestion-card').forEach(button => { button.disabled = working; });
    if (latticeTimerId !== null) window.clearInterval(latticeTimerId);
    latticeTimerId = null;
    if (working) {
      latticeStartedAt = performance.now();
      $('lattice-timer').textContent = '0.0s';
      latticeTimerId = window.setInterval(() => {
        $('lattice-timer').textContent = `${((performance.now() - latticeStartedAt) / 1000).toFixed(1)}s`;
      }, 100);
    }
  }
  function initShapeWaves() {
    const canvas = $('shape-waves');
    const context = canvas && canvas.getContext('2d');
    if (!canvas || !context) return;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    let width = 1, height = 1, frameId = 0, visible = true;
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, rect.width); height = Math.max(1, rect.height);
      canvas.width = Math.round(width * ratio); canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw(0);
    };
    const draw = now => {
      context.clearRect(0, 0, width, height);
      const cell = width < 500 ? 18 : 20;
      const time = reducedMotion ? 0 : now * 0.00035;
      for (let y = cell / 2; y < height; y += cell) {
        for (let x = cell / 2; x < width; x += cell) {
          const wave = (Math.sin(x * 0.032 + time * 4) + Math.cos(y * 0.045 - time * 3)) * 0.5;
          const edge = Math.min(1, x / (width * 0.36), (width - x) / (width * 0.2), y / (height * 0.35), (height - y) / (height * 0.35));
          const alpha = Math.max(0, edge) * (0.08 + (wave + 1) * 0.08);
          const size = 2 + (wave + 1) * 1.4;
          context.fillStyle = `rgba(15,159,145,${alpha.toFixed(3)})`;
          if ((Math.round(x / cell) + Math.round(y / cell)) % 3 === 0) {
            context.beginPath(); context.arc(x, y, size, 0, Math.PI * 2); context.fill();
          } else context.fillRect(x - size / 2, y - size / 2, size, size);
        }
      }
    };
    const animate = now => {
      if (!visible) return;
      draw(now);
      if (!reducedMotion) frameId = window.requestAnimationFrame(animate);
    };
    const resizeObserver = new ResizeObserver(resize);
    const intersectionObserver = new IntersectionObserver(entries => {
      visible = entries.some(entry => entry.isIntersecting);
      window.cancelAnimationFrame(frameId);
      if (visible && !reducedMotion) frameId = window.requestAnimationFrame(animate);
    });
    resizeObserver.observe(canvas); intersectionObserver.observe(canvas); resize();
    if (!reducedMotion) frameId = window.requestAnimationFrame(animate);
    window.addEventListener('pagehide', () => {
      window.cancelAnimationFrame(frameId); resizeObserver.disconnect(); intersectionObserver.disconnect();
    }, { once: true });
  }
  function clearAnswer() {
    state.answer = null; state.question = '';
    $('answer-section').hidden = true;
    $('answer-body').replaceChildren(); $('source-list').replaceChildren();
    $('asked-question').textContent = ''; $('query-reference').textContent = '';
    $('answer-note').textContent = ''; $('answer-note').hidden = true;
    $('evidence-content').replaceChildren();
    if ($('evidence-dialog').open) $('evidence-dialog').close();
    $('copy-label').textContent = 'Copy';
    document.querySelector('.content').classList.remove('has-answer');
    $('suggestions').hidden = false;
  }
  function renderIdentity() {
    const user = state.user;
    $('identity-name').textContent = user ? user.name : 'Your workspace awaits';
    $('identity-role').textContent = user ? user.title : 'Sign in to ask a question';
    $('avatar').textContent = user ? String(user.name || user.username).split(/\s+/).map(part => part[0]).join('').slice(0, 2).toUpperCase() : '?';
    $('account-button').replaceChildren(document.createTextNode(user ? 'Switch account' : 'Sign in'), node('span', '', '↗'));
    $('mobile-account').textContent = user ? user.name.split(' ')[0] + ' · Account' : 'Sign in';
    $('history-button').hidden = !user;
    $('logout-button').hidden = !user; $('dialog-logout').hidden = !user;
    const canAdmin = user && Array.isArray(user.rights) && user.rights.some(right => ['admin', 'audit', 'audit_meta'].includes(right));
    $('console-link').hidden = !canAdmin; $('mobile-console-link').hidden = !canAdmin;
  }
  function clearSession() {
    state.epoch++; state.askSerial++; state.evidenceSerial++;
    closeHistory();
    state.controllers.forEach(controller => controller.abort()); state.controllers.clear();
    state.askController = null; state.evidenceController = null; state.loginController = null;
    state.token = null; state.user = null; state.pendingQuestion = '';
    $('question').value = ''; updateCount(); $('password').value = '';
    clearAnswer(); clearError('form-error'); setWorking(false); renderIdentity();
    $('mode-label').textContent = 'Sign in to explore';
    $('source-mode-label').textContent = 'Source and answer modes appear after sign-in.';
    $('announcement').textContent = '';
  }
  function logout() {
    clearSession();
    if ($('login-dialog').open) $('login-dialog').close();
    announce('Signed out. The previous answer has been cleared.');
    $('question').focus();
  }
  function openLogin() {
    clearError('login-error');
    if (!$('login-dialog').open) $('login-dialog').showModal();
  }
  function setLoginBusy(value) {
    loginBusy = value;
    $('login-dialog').querySelectorAll('button:not(#close-login), input').forEach(el => { el.disabled = value; });
    $('demo-login-button').textContent = value ? 'Signing in…' : `Continue as ${personas.find(persona => persona.id === selectedPersona).name.split(' ')[0]}`;
  }
  async function login(username, password) {
    if (loginBusy) return;
    const pending = state.user ? '' : state.pendingQuestion;
    clearSession(); clearError('login-error'); setLoginBusy(true);
    const epoch = state.epoch;
    const controller = new AbortController(); state.loginController = controller;
    try {
      const result = await api('/api/login', { method: 'POST', body: { username, password }, anonymous: true, controller });
      if (!isCurrent(epoch)) return;
      if (!result.token || !result.user) throw new Error('Invalid session');
      state.token = result.token; state.user = result.user; renderIdentity();
      updateModes(result);
      try {
        const session = await api('/api/session', { controller });
        if (!isCurrent(epoch)) return;
        if (session.user) state.user = session.user;
        renderIdentity(); updateModes(session);
      } catch (error) {
        if (!isCurrent(epoch) || error.name === 'AbortError') return;
        if (error.status === 401) throw error;
      }
      if (!isCurrent(epoch)) return;
      $('password').value = ''; $('login-dialog').close();
      announce(`Signed in as ${state.user.name}.`);
      if (pending) { $('question').value = pending; updateCount(); }
      $('question').focus();
      if (pending) ask();
    } catch (error) {
      if (!isCurrent(epoch) || error.name === 'AbortError') return;
      state.token = null; state.user = null; renderIdentity();
      showError('login-error', error.status === 401 || error.status === 403 ? 'Couldn’t sign in. Check your credentials, or confirm that demo mode is enabled.' : 'Couldn’t connect to the workspace. Please try again.');
    } finally {
      if (isCurrent(epoch)) { setLoginBusy(false); state.loginController = null; }
    }
  }
  function selectPersona(persona) {
    selectedPersona = persona.id;
    $('persona-grid').querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.persona === persona.id)));
    $('persona-description').textContent = persona.note;
    $('demo-login-button').textContent = `Continue as ${persona.name.split(' ')[0]}`;
  }
  personas.forEach(persona => {
    const button = node('button', 'persona-option'); button.type = 'button'; button.dataset.persona = persona.id;
    const details = node('span'); details.append(node('strong', '', persona.name), node('span', 'persona-role', persona.role));
    const avatar = node('span', 'avatar', persona.initials); avatar.setAttribute('aria-hidden', 'true');
    button.append(avatar, details); button.addEventListener('click', () => selectPersona(persona)); $('persona-grid').append(button);
  });
  selectPersona(personas[0]);
  initShapeWaves();

  function updateCount() { $('character-count').textContent = `${$('question').value.length.toLocaleString()} / 2,000`; }
  function cancelAsk() {
    state.askSerial++;
    if (state.askController) state.askController.abort();
    state.askController = null; setWorking(false); $('suggestions').hidden = false;
    announce('Search cancelled.');
  }
  function requestError(error) {
    if (error.status === 401) {
      clearSession(); showError('form-error', 'Your session has ended. Sign in again to continue.'); return;
    }
    showError('form-error', error.status === 429 ? 'The workspace is receiving too many requests. Please try again shortly.' :
      error.status === 422 ? 'Please enter a question between 1 and 2,000 characters.' :
      'We couldn’t complete this question. Please try again.');
  }
  async function ask() {
    const question = $('question').value.trim();
    if (!question) { $('question').focus(); return; }
    if (question.length > 2000) { showError('form-error', 'Keep your question within 2,000 characters.'); return; }
    if (!state.token) { state.pendingQuestion = question; openLogin(); return; }
    if (state.askController) state.askController.abort();
    if (state.evidenceController) state.evidenceController.abort();
    const epoch = state.epoch; const serial = ++state.askSerial;
    state.evidenceSerial++;
    const controller = new AbortController(); state.askController = controller;
    clearAnswer(); clearError('form-error'); setWorking(true); $('suggestions').hidden = true;
    try {
      const result = await api('/api/ask', { method: 'POST', body: { question }, controller });
      if (!isCurrent(epoch) || serial !== state.askSerial) return;
      renderAnswer(result, question);
      announce(result.status === 'answered' ? 'Your answer is ready. Source evidence follows the answer.' : 'Your question has been processed.');
    } catch (error) {
      if (!isCurrent(epoch) || serial !== state.askSerial || error.name === 'AbortError') return;
      requestError(error); $('suggestions').hidden = false;
    } finally {
      if (isCurrent(epoch) && serial === state.askSerial) { setWorking(false); state.askController = null; }
    }
  }
  function appendCitedText(parent, value, citationMap) {
    const text = String(value || ''); const pattern = /\[(S\d+)\]/g; let start = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(start, match.index)));
      if (citationMap.has(match[1])) {
        const button = node('button', 'inline-citation', match[1]); button.type = 'button';
        button.setAttribute('aria-label', `Inspect source ${match[1]}`);
        button.addEventListener('click', () => openEvidence(match[1])); parent.append(button);
      } else parent.append(document.createTextNode(match[0]));
      start = match.index + match[0].length;
    }
    parent.append(document.createTextNode(text.slice(start)));
  }
  function renderAnswer(result, question) {
    const citations = Array.isArray(result.citations) ? result.citations.filter(citation => /^S\d+$/.test(citation.ref)) : [];
    state.answer = { ...result, citations }; state.question = question;
    const map = new Map(citations.map(citation => [citation.ref, citation]));
    $('asked-question').textContent = question;
    const noAnswer = result.status === 'no_answer' || result.status === 'blocked' || result.blocked;
    $('answer-heading').textContent = noAnswer ? 'A note from your workspace' : 'From your workspace';
    $('answer-mode').textContent = noAnswer ? 'No answer available' : modeLabel(result.quality && result.quality.mode);
    for (const paragraph of String(result.answer || 'I couldn’t find enough information to answer that question.').split(/\n\s*\n/)) {
      const element = node('p', 'answer-paragraph'); appendCitedText(element, paragraph, map); $('answer-body').append(element);
    }
    if (result.quality && result.quality.mode === 'extractive_fallback') {
      $('answer-note').textContent = 'This answer uses source excerpts because an acceptable model response wasn’t available.'; $('answer-note').hidden = false;
    }
    for (const citation of citations) {
      const card = node('button', 'source-card'); card.type = 'button';
      card.setAttribute('aria-label', `Inspect ${citation.ref}: ${citation.title}`);
      const info = node('span', 'source-info');
      const updated = dateLabel(citation.updated_iso);
      info.append(node('span', 'source-title', citation.title), node('span', 'source-subtitle',
        [platformInfo(citation.platform).label, citation.container, updated ? `Updated ${updated}` : ''].filter(Boolean).join(' · ')));
      card.append(platformIcon(citation.platform), info, node('span', 'source-ref', citation.ref), node('span', 'source-arrow', '↗'));
      card.addEventListener('click', () => openEvidence(citation.ref)); $('source-list').append(card);
    }
    $('sources-section').hidden = citations.length === 0;
    $('query-reference').textContent = result.query_id ? `Query ${String(result.query_id).slice(0, 8)}` : '';
    $('answer-section').hidden = false; $('suggestions').hidden = true;
    document.querySelector('.content').classList.add('has-answer');
  }
  async function openEvidence(ref) {
    if (!state.answer || !state.token) return;
    if (state.evidenceController) state.evidenceController.abort();
    const serial = ++state.evidenceSerial; const epoch = state.epoch; const queryId = state.answer.query_id;
    const controller = new AbortController(); state.evidenceController = controller;
    const content = $('evidence-content'); content.replaceChildren();
    const title = node('h2', '', 'Loading source…'); title.id = 'evidence-title';
    content.append(title, node('p', 'evidence-empty', 'Checking current access and loading the supporting passages.'));
    if (!$('evidence-dialog').open) $('evidence-dialog').showModal();
    try {
      const evidence = await api(`/api/evidence/${encodeURIComponent(queryId)}/${encodeURIComponent(ref)}`, { controller });
      if (!isCurrent(epoch) || serial !== state.evidenceSerial || !$('evidence-dialog').open) return;
      content.replaceChildren();
      const platform = node('div', 'evidence-platform'); platform.append(platformIcon(evidence.platform), document.createTextNode(`${platformInfo(evidence.platform).label} · ${ref}`));
      const heading = node('h2', '', evidence.title); heading.id = 'evidence-title';
      content.append(platform, heading);
      const updated = dateLabel(evidence.updated_iso);
      content.append(node('div', 'evidence-metadata', [updated ? `Updated ${updated}` : '', evidence.version !== undefined ? `Version ${evidence.version}` : ''].filter(Boolean).join(' · ')));
      const url = httpsUrl(evidence.url);
      if (url) { const link = node('a', 'evidence-link', 'Open original source ↗'); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; content.append(link); }
      content.append(node('div', 'section-label passages-label', 'SUPPORTING PASSAGES'));
      const passages = Array.isArray(evidence.passages) ? evidence.passages : [];
      passages.forEach((passage, index) => {
        const quote = node('blockquote', 'evidence-passage');
        quote.append(node('span', 'passage-id', `Passage ${index + 1}`), document.createTextNode(String(passage.text || ''))); content.append(quote);
      });
      if (!passages.length) content.append(node('p', 'evidence-empty', 'No supporting passages are available.'));
      content.append(node('p', 'evidence-disclaimer', 'Access is checked when this source is opened. Ask again to refresh the answer when source content changes.'));
    } catch (error) {
      if (!isCurrent(epoch) || serial !== state.evidenceSerial || error.name === 'AbortError') return;
      content.replaceChildren();
      if (error.status === 401) { requestError(error); return; }
      const heading = node('h2', '', 'Source unavailable'); heading.id = 'evidence-title';
      content.append(heading, node('p', 'evidence-empty', 'This source is unavailable. Ask your question again to retrieve current evidence.'));
    } finally { if (serial === state.evidenceSerial) state.evidenceController = null; }
  }
  function closeEvidence() {
    state.evidenceSerial++;
    if (state.evidenceController) state.evidenceController.abort();
    state.evidenceController = null;
    if ($('evidence-dialog').open) $('evidence-dialog').close();
    $('evidence-content').replaceChildren();
  }
  function closeHistory() {
    historySerial++;
    if ($('history-dialog').open) $('history-dialog').close();
    $('history-content').replaceChildren();
  }
  async function openHistory() {
    if (!state.user) return;
    const epoch = state.epoch, serial = ++historySerial;
    const content = $('history-content');
    content.replaceChildren(node('p', '', 'Loading previous questions…'));
    if (!$('history-dialog').open) $('history-dialog').showModal();
    try {
      const result = await api('/api/history');
      if (!isCurrent(epoch) || serial !== historySerial || !$('history-dialog').open) return;
      content.replaceChildren();
      for (const item of result.items || []) {
        const when = new Date(typeof item.created_at === 'number' ? item.created_at * 1000 : item.created_at);
        const label = Number.isNaN(when.getTime()) ? 'Previous question' : when.toLocaleString();
        const button = node('button', 'source-card', `Revisit question · ${label}`);
        button.type = 'button';
        button.addEventListener('click', () => replayQuestion(item.query_id));
        content.append(button);
      }
      if (!content.children.length) content.append(node('p', '', 'No previous questions are available.'));
    } catch (error) {
      if (isCurrent(epoch) && serial === historySerial) content.replaceChildren(node('p', '', 'Previous questions could not be loaded.'));
    }
  }
  async function replayQuestion(queryId) {
    closeHistory(); cancelAsk(); closeEvidence(); clearAnswer(); clearError('form-error');
    const epoch = state.epoch, serial = ++state.askSerial;
    const controller = new AbortController(); state.askController = controller;
    setWorking(true);
    try {
      const result = await api(`/api/history/${encodeURIComponent(queryId)}/replay`, { method: 'POST', controller });
      if (!isCurrent(epoch) || serial !== state.askSerial) return;
      renderAnswer(result, 'Previous question · checked against your current access');
      announce('Your previous question has been answered with current evidence.');
    } catch (error) {
      if (isCurrent(epoch) && serial === state.askSerial && error.name !== 'AbortError') requestError(error);
    } finally {
      if (isCurrent(epoch) && serial === state.askSerial) { setWorking(false); state.askController = null; }
    }
  }
  $('history-button').addEventListener('click', openHistory);
  $('close-history').addEventListener('click', closeHistory);
  $('history-dialog').addEventListener('cancel', closeHistory);
  async function copyAnswer() {
    if (!state.answer) return;
    const epoch = state.epoch; const answer = state.answer;
    const sources = answer.citations.map(source => { const url = httpsUrl(source.url); return `[${source.ref}] ${source.title}${url ? ` | ${url}` : ''}`; });
    const text = [answer.answer, sources.length ? `Sources\n${sources.join('\n')}` : ''].filter(Boolean).join('\n\n');
    try {
      await navigator.clipboard.writeText(text);
      if (!isCurrent(epoch) || state.answer !== answer) return;
      $('copy-label').textContent = 'Copied'; announce('Answer copied.');
      window.setTimeout(() => { if (isCurrent(epoch) && state.answer === answer) $('copy-label').textContent = 'Copy'; }, 2000);
    } catch (_) { if (isCurrent(epoch)) announce('Copy is unavailable in this browser. Select the answer text to copy it.'); }
  }
  $('question-form').addEventListener('submit', event => { event.preventDefault(); ask(); });
  $('question').addEventListener('input', updateCount);
  $('question').addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); if (!$('ask-button').disabled) $('question-form').requestSubmit(); }
  });
  document.querySelectorAll('.suggestion-card').forEach(button => button.addEventListener('click', () => {
    $('question').value = button.dataset.question; updateCount(); $('question').focus(); ask();
  }));
  $('cancel-request').addEventListener('click', cancelAsk);
  $('new-question').addEventListener('click', () => { cancelAsk(); closeEvidence(); clearAnswer(); clearError('form-error'); $('question').value = ''; updateCount(); $('question').focus(); });
  $('account-button').addEventListener('click', openLogin); $('mobile-account').addEventListener('click', openLogin);
  $('logout-button').addEventListener('click', logout); $('dialog-logout').addEventListener('click', logout);
  $('demo-login-form').addEventListener('submit', event => { event.preventDefault(); login(selectedPersona, 'demo'); });
  $('credentials-form').addEventListener('submit', event => { event.preventDefault(); login($('username').value.trim(), $('password').value); });
  function closeLogin() {
    if (loginBusy) { clearSession(); setLoginBusy(false); }
    state.pendingQuestion = ''; $('password').value = '';
    if ($('login-dialog').open) $('login-dialog').close();
  }
  $('close-login').addEventListener('click', closeLogin);
  $('login-dialog').addEventListener('cancel', event => { event.preventDefault(); closeLogin(); });
  $('close-evidence').addEventListener('click', closeEvidence);
  $('evidence-dialog').addEventListener('cancel', event => { event.preventDefault(); closeEvidence(); });
  $('copy-answer').addEventListener('click', copyAnswer);

  // A restored browser page must not resurrect a prior identity or its answer.
  window.addEventListener('pageshow', event => { if (event.persisted) clearSession(); });
})();


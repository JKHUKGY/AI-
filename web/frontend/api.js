const API = (() => {
  async function req(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    if (res.status === 401 && path !== '/api/login') {
      const next = encodeURIComponent(location.pathname + location.search + location.hash);
      location.href = `/login.html?next=${next}`;
      return new Promise(() => {}); // 页面即将跳转，调用方不需要再处理这个结果
    }
    let data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
    return data;
  }
  const enc = encodeURIComponent;
  return {
    projects: () => req('GET', '/api/projects'),
    contentChange: (p, action, body) => req('POST', `/api/projects/${enc(p)}/content/${action}`, body),
    contentTrash: (p) => req('GET', `/api/projects/${enc(p)}/content/trash`),
    helpQuestion: (body) => req('POST', '/api/help/question', body),
    tasks: () => req('GET', '/api/tasks'),
    startPromptTask: (p, body) => req('POST', `/api/projects/${enc(p)}/prompt_tasks`, body),
    createProject: (body) => req('POST', '/api/projects', body),
    setup: (p) => req('GET', `/api/projects/${enc(p)}/setup`),
    startSetup: (p) => req('POST', `/api/projects/${enc(p)}/setup/start`, {}),
    setupFile: (p, path) => req('GET', `/api/projects/${enc(p)}/setup/file?path=${enc(path)}`),
    guide: () => req('GET', '/api/guide'),

    characters: (p) => req('GET', `/api/projects/${enc(p)}/characters`),
    patchCharacter: (p, title, text) => req('PATCH', `/api/projects/${enc(p)}/characters/${enc(title)}`, { text }),
    scenes: (p) => req('GET', `/api/projects/${enc(p)}/scenes`),
    patchScene: (p, title, text) => req('PATCH', `/api/projects/${enc(p)}/scenes/${enc(title)}`, { text }),
    styleBible: (p) => req('GET', `/api/projects/${enc(p)}/style-bible`),
    patchStyleBible: (p, text) => req('PATCH', `/api/projects/${enc(p)}/style-bible`, { text }),

    episodeList: (p) => req('GET', `/api/projects/${enc(p)}/episodes`),
    episode: (p, n) => req('GET', `/api/projects/${enc(p)}/episodes/${n}`),
    patchShot: (p, n, shot, updates) =>
      req('PATCH', `/api/projects/${enc(p)}/episodes/${n}/shots/${enc(shot)}`, updates),

    keyframes: (p, n) => req('GET', `/api/projects/${enc(p)}/keyframes/${n}`),

    videos: (p, n) => req('GET', `/api/projects/${enc(p)}/videos/${n}`),
    patchVideoShot: (p, n, shot, updates) =>
      req('PATCH', `/api/projects/${enc(p)}/videos/${n}/shots/${enc(shot)}`, updates),
    requestVideoRegen: (p, n, shot_no, note) =>
      req('POST', `/api/projects/${enc(p)}/videos/${n}/request_regen`, { shot_no, note }),

    comments: (p, resolved) =>
      req('GET', `/api/projects/${enc(p)}/comments${resolved !== undefined ? `?resolved=${resolved}` : ''}`),
    addComment: (p, target, text, author) =>
      req('POST', `/api/projects/${enc(p)}/comments`, { target, text, author }),
    resolveComment: (p, id) => req('POST', `/api/projects/${enc(p)}/comments/${enc(id)}/resolve`),

    select: (p, job_id, file) => req('POST', `/api/projects/${enc(p)}/select`, { job_id, file }),

    regenerate: (p, body) => req('POST', `/api/projects/${enc(p)}/regenerate`, body),
    previewRegenerate: (p, body) => req('POST', `/api/projects/${enc(p)}/regenerate/preview`, body),
    savePromptVersion: (p, body) => req('POST', `/api/projects/${enc(p)}/prompt_history`, body),
    regenerateStatus: (p, token) => req('GET', `/api/projects/${enc(p)}/regenerate/${enc(token)}`),
    lastPrompt: (p, jobId, kind, episode) => {
      const qs = new URLSearchParams({ job_id: jobId, kind: kind || 'asset' });
      if (episode) qs.set('episode', episode);
      return req('GET', `/api/projects/${enc(p)}/last_prompt?${qs.toString()}`);
    },
    aiRewritePrompt: (p, body) => req('POST', `/api/projects/${enc(p)}/ai_rewrite_prompt`, body),

    inbox: () => req('GET', '/api/inbox'),

    me: () => req('GET', '/api/me'),
    logout: () => req('POST', '/api/logout'),

    mediaUrl: (relPath) => `/media/${relPath.split('/').map(enc).join('/')}`,
  };
})();

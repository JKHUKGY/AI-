const API = (() => {
  async function req(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) throw new Error(data.error || `请求失败 (${res.status})`);
    return data;
  }
  const enc = encodeURIComponent;
  return {
    projects: () => req('GET', '/api/projects'),
    guide: () => req('GET', '/api/guide'),

    characters: (p) => req('GET', `/api/projects/${enc(p)}/characters`),
    scenes: (p) => req('GET', `/api/projects/${enc(p)}/scenes`),
    styleBible: (p) => req('GET', `/api/projects/${enc(p)}/style-bible`),

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
    regenerateStatus: (p, token) => req('GET', `/api/projects/${enc(p)}/regenerate/${enc(token)}`),

    inbox: () => req('GET', '/api/inbox'),

    mediaUrl: (relPath) => `/media/${relPath.split('/').map(enc).join('/')}`,
  };
})();

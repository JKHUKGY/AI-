window.Views = window.Views || {};

Views.setup = async function setup(app, project) {
  const routeHash = location.hash;
  app.innerHTML = `<h1>${UI.esc(project)} · 项目筹备</h1>
    <div class="card"><h2>文字基础文件</h2><p class="setup-progress" role="status">正在加载…</p>
      <progress class="setup-meter" max="1" value="0"></progress>
      <p class="setup-error notice error" hidden></p><button class="primary setup-start" hidden>开始生成文字文件</button>
      <button class="setup-cancel" hidden>终止生成</button>
      <p class="muted">文字生成在后台进行，关闭页面不会停止。未完成时可回来继续；已完成的文件不会被重写。</p>
      <div class="setup-files"></div></div>
    <div class="card setup-document" hidden><h2 class="document-title"></h2><pre></pre><button class="close-document">收起</button></div>
    <div class="card"><h2>图片审批</h2><p>每项任务需先检查完整提示词、参考图与张数，再明确批准。后续关键帧图片也使用同样的审批流程。</p><div class="setup-image-tasks"></div></div>
    <div class="card"><h2>视频与租卡审批</h2><p class="setup-gpu"></p></div>`;
  const start = app.querySelector('.setup-start');
  const stop = app.querySelector('.setup-cancel');
  const error = app.querySelector('.setup-error');
  let active = false;
  let fileSignature = '';
  let taskSignature = '';
  let timer;
  const fileTitles = {
    'README.md': '项目说明', 'project.json': '项目设置', 'source/script.txt': '原始剧本',
    'storyboard/style_bible.md': '风格简报', 'storyboard/outline.md': '故事与分集规划',
    'storyboard/characters.md': '人物设计', 'storyboard/scenes.md': '场景设计',
    'assets/jobs_initial.json': '图片任务草案', 'assets/selected.md': '图片选片记录',
    'keyframes/README.md': '关键帧制作说明', 'videos/README.md': '视频制作说明',
    'production_plan.md': '后续制作与审批清单',
  };
  function fileTitle(path) {
    const episode = path.match(/^storyboard\/ep(\d+)\.md$/);
    return fileTitles[path] || (episode ? `第 ${Number(episode[1])} 集分镜` : path);
  }
  function stillHere() { return app.isConnected && location.hash === routeHash && app.querySelector('.setup-progress'); }
  async function refresh() {
    if (!stillHere()) return;
    clearTimeout(timer);
    try {
      const data = await API.setup(project);
      if (!stillHere()) return;
      if (!data.setup) {
        app.querySelector('.setup-progress').textContent = '此项目已有内容，可通过人物、场景和分镜页面继续制作。';
        app.querySelector('.setup-gpu').textContent = '所有图片需逐次审批。视频制作仍需准备具体方案后单独审批。';
        return;
      }
      const s = data.setup;
      active = s.status === 'running';
      app.querySelector('.setup-progress').textContent = `${s.step}（${s.completed}/${s.total}）`;
      const meter = app.querySelector('.setup-meter'); meter.max = s.total; meter.value = s.completed;
      error.hidden = !s.error; error.textContent = s.error || '';
      start.hidden = active || s.status === 'done' || s.can_resume === false;
      stop.hidden = !['running', 'failed', 'interrupted'].includes(s.status);
      if (s.can_resume === false) app.querySelector('.setup-progress').textContent += ' · 已改为手动编辑，不再自动补写旧规划';
      start.textContent = s.status === 'ready' ? '开始生成文字文件' : '继续生成未完成的文字';
      app.querySelector('.setup-gpu').textContent = data.gpu.message;
      const files = JSON.stringify(s.files);
      if (files !== fileSignature) {
        fileSignature = files;
        const box = app.querySelector('.setup-files'); box.innerHTML = '';
        s.files.forEach((path) => {
          const button = document.createElement('button'); button.className = 'small'; button.textContent = fileTitle(path); button.title = path;
          button.addEventListener('click', async () => {
            try {
              const file = await API.setupFile(project, path);
              if (!stillHere()) return;
              const doc = app.querySelector('.setup-document'); doc.hidden = false;
              doc.querySelector('.document-title').textContent = fileTitle(file.path);
              doc.querySelector('pre').textContent = file.text;
              doc.scrollIntoView({behavior:'smooth',block:'start'});
            } catch (err) { UI.toast(err.message, 'error'); }
          });
          box.appendChild(button);
        });
      }
      const tasks = JSON.stringify(data.image_tasks);
      if (tasks !== taskSignature) {
        taskSignature = tasks;
        const box = app.querySelector('.setup-image-tasks'); box.innerHTML = '';
        if (!data.image_tasks.length) box.textContent = '人物与场景文字完成后，将在这里列出待审批的图片任务。';
        data.image_tasks.forEach((task) => {
          const item = document.createElement('div'); item.className = 'setup-task';
          const title = document.createElement('h3'); title.textContent = task.id.replaceAll('_', ' · ');
          const button = document.createElement('button'); button.textContent = '检查提示词与参考图…'; button.className = 'small';
          const panel = document.createElement('div'); panel.className = 'regen-panel'; panel.hidden = true;
          const gallery = document.createElement('div'); gallery.className = 'img-grid';
          item.append(title, button, panel, gallery); box.appendChild(item);
          button.addEventListener('click', () => {
            panel.hidden = !panel.hidden;
            if (!panel.hidden) UI.attachRegenPanel(panel, project, task.id, {files:[]},
              {kind:'asset',baseDirHint:'assets'}, (path) => {
                const img = document.createElement('img'); img.src = API.mediaUrl(path); img.alt = task.id; gallery.appendChild(img);
              });
          });
        });
      }
      if (active) timer = setTimeout(refresh, 4000);
    } catch (err) {
      if (!stillHere()) return;
      error.hidden = false; error.textContent = '获取进度失败：' + err.message;
      timer = setTimeout(refresh, 8000);
    }
  }
  app.querySelector('.close-document').addEventListener('click', () => { app.querySelector('.setup-document').hidden = true; });
  start.addEventListener('click', async () => {
    start.disabled = true;
    try { await API.startSetup(project); await refresh(); }
    catch (err) { error.hidden = false; error.textContent = err.message; }
    finally { start.disabled = false; }
  });
  stop.addEventListener('click', async () => {
    stop.disabled = true; stop.textContent = '正在终止…';
    try { await API.cancelSetup(project); await refresh(); await TaskUI.refresh(); }
    catch (err) { error.hidden = false; error.textContent = err.message; }
    finally { stop.disabled = false; stop.textContent = '终止生成'; }
  });
  await refresh();
};

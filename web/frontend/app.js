function parseHash() {
  const hash = location.hash.replace(/^#\/?/, '');
  const parts = hash.split('/').filter(Boolean);
  if (parts.length === 0) return { name: 'home' };
  if (parts[0] === 'guide') return { name: 'guide' };
  if (parts[0] === 'inbox') return { name: 'inbox' };
  if (parts[0] === 'p' && parts[1]) {
    const project = decodeURIComponent(parts[1]);
    const section = parts[2] || 'characters';
    if (section === 'setup') return { name: 'setup', project };
    if (section === 'characters') return { name: 'characters', project };
    if (section === 'scenes') return { name: 'scenes', project };
    if (section === 'style') return { name: 'style', project };
    if (section === 'episodes') return { name: 'episode', project, ep: Number(parts[3]) || 1 };
    if (section === 'keyframes') return { name: 'keyframes', project, ep: Number(parts[3]) || 1 };
    if (section === 'videos') return { name: 'videos', project, ep: Number(parts[3]) || 1 };
  }
  return { name: 'home' };
}

let currentUser = null;

function navHtml(route) {
  const items = [['#/guide', '指南', route.name === 'guide']];
  if (route.project) {
    const p = encodeURIComponent(route.project);
    items.push([`#/p/${p}/setup`, '项目筹备', route.name === 'setup']);
    items.push([`#/p/${p}/characters`, '人物', route.name === 'characters']);
    items.push([`#/p/${p}/scenes`, '场景', route.name === 'scenes']);
    items.push([`#/p/${p}/style`, '风格简报', route.name === 'style']);
    items.push([`#/p/${p}/episodes/${route.ep || 1}`, '分镜表', route.name === 'episode']);
    items.push([`#/p/${p}/keyframes/${route.ep || 1}`, '关键帧', route.name === 'keyframes']);
    items.push([`#/p/${p}/videos/${route.ep || 1}`, '视频', route.name === 'videos']);
  }
  // 反馈汇总是跨剧的管理视角，普通剧本家账号只能看到自己被授权的那几部剧，
  // 汇总页对他们意义不大，只给管理员账号看。
  if (currentUser && currentUser.is_admin) {
    items.push(['#/inbox', '反馈汇总', route.name === 'inbox']);
  }
  items.push(['#/', '切换项目', route.name === 'home']);
  return items.map(([href, label, active]) => `<a href="${href}" class="${active ? 'active' : ''}">${UI.esc(label)}</a>`).join('');
}

async function render() {
  const route = parseHash();
  document.getElementById('topNav').innerHTML = navHtml(route);
  const app = document.getElementById('app');
  app.innerHTML = '<div class="empty-hint">加载中…</div>';
  try {
    if (route.name === 'home') await Views.home(app);
    else if (route.name === 'setup') await Views.setup(app, route.project);
    else if (route.name === 'guide') await Views.guide(app);
    else if (route.name === 'inbox') await Views.inbox(app);
    else if (route.name === 'characters') await Views.characters(app, route.project);
    else if (route.name === 'scenes') await Views.scenes(app, route.project);
    else if (route.name === 'style') await Views.styleBible(app, route.project);
    else if (route.name === 'episode') await Views.episode(app, route.project, route.ep);
    else if (route.name === 'keyframes') await Views.keyframes(app, route.project, route.ep);
    else if (route.name === 'videos') await Views.videos(app, route.project, route.ep);
    else await Views.home(app);
  } catch (e) {
    app.innerHTML = `<div class="notice error">加载失败：${UI.esc(e.message)}</div>`;
  }
}

async function initAuthBar() {
  try {
    const me = await API.me();
    currentUser = me;
    TaskUI.init();
    HelpUI.init(me.username);
    document.getElementById('whoami').textContent = `已登录：${me.display_name}`;
    const logoutBtn = document.getElementById('logoutBtn');
    logoutBtn.hidden = false;
    logoutBtn.addEventListener('click', async (e) => {
      e.preventDefault();
      await API.logout();
      location.href = '/login.html';
    });
  } catch (e) {
    // API.me() 401 时 api.js 已经直接跳转登录页了，这里不需要额外处理
  }
}

window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', async () => { await initAuthBar(); render(); });

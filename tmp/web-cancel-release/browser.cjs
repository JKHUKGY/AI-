const {chromium} = require('/tmp/web-reference-browser/node_modules/playwright');
const assert = require('node:assert/strict');
const root='/workspaces/AI-/tmp/web-cancel-release';
(async()=>{
 const browser=await chromium.launchPersistentContext(root+'/profile',{
  executablePath:'/home/codespace/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome',
  headless:true,viewport:{width:1300,height:950},args:['--no-sandbox']});
 try {
  const page=await browser.newPage(), errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const project='终止验收';
  const route=s=>'http://127.0.0.1:18010/#/p/'+encodeURIComponent(project)+'/'+s;
  await page.goto(route('characters'));
  await page.evaluate(()=>localStorage.clear());
  await page.reload();
  await page.locator('.regen-toggle').first().click();
  const panel=page.locator('.regen-panel').first();
  await panel.locator('.ai-instruction').fill('只修改头发，保留其他内容');
  const before=await panel.locator('textarea').first().inputValue();
  await panel.locator('.ai-rewrite-btn').click();
  await panel.locator('.stop-generation').waitFor({state:'visible'});
  await page.goto(route('scenes'));
  await page.locator('.global-tasks > summary').click();
  await page.locator('.task-row').filter({hasText:'提示词'}).getByRole('button',{name:'终止生成'}).click();
  await page.waitForFunction(async()=>!(await API.tasks()).tasks.some(t=>t.status==='running'));
  await page.goto(route('characters'));
  await page.locator('.regen-toggle').first().click();
  await panel.locator('.ai-rewrite-btn').waitFor();
  await page.waitForFunction(expected=>document.querySelector('.regen-panel textarea')?.value===expected,before);
  assert.equal(await panel.locator('textarea').first().inputValue(),before);
  assert.equal(await panel.locator('.ai-instruction').inputValue(),'只修改头发，保留其他内容');
  assert.equal(await panel.locator('.ai-rewrite-btn').isEnabled(),true);
  await panel.locator('.ai-rewrite-btn').click();
  await panel.locator('.stop-generation').waitFor({state:'visible'});
  await panel.locator('.stop-generation').click();
  await page.waitForFunction(async()=>!(await API.tasks()).tasks.some(t=>t.status==='running'));
  await page.reload(); await page.locator('.regen-toggle').first().click();
  await page.waitForFunction(expected=>document.querySelector('.regen-panel textarea')?.value===expected,before);
  assert.equal(await panel.locator('textarea').first().inputValue(),before);
  assert.equal(await panel.locator('.ai-rewrite-btn').isEnabled(),true);
  await panel.locator('.go-regen').click();
  await page.locator('.approval-check').check(); await page.locator('.approve-image').click();
  await panel.locator('.stop-generation').waitFor({state:'visible'});
  await panel.locator('.stop-generation').click();
  await page.waitForFunction(async()=>!(await API.tasks()).tasks.some(t=>t.status==='running'));
  await panel.locator('.go-regen').click();
  await page.locator('.approval-dialog').waitFor(); // 重试必须重新审批。
  await page.locator('.cancel-approval').click();
  const setupName='停止筹备'+Date.now();
  await page.evaluate(async name=>{
    await API.createProject({name,script:'小雨推开旧书店的门。小雨说：“我来取父亲留下的信。”店主从柜台下取出一个信封。',duration:15});
    await API.startSetup(name);
  },setupName);
  await page.goto('http://127.0.0.1:18010/#/p/'+encodeURIComponent(setupName)+'/setup');
  await page.locator('.setup-cancel').waitFor({state:'visible'});
  await page.locator('.setup-cancel').click();
  await page.waitForFunction(async name=>(await API.setup(name)).setup.status==='cancelled',setupName);
  await page.reload();
  await page.locator('.setup-start').waitFor({state:'visible'});
  assert.match(await page.locator('.setup-progress').textContent(),/已终止/);
  assert.equal(await page.locator('.setup-cancel').isVisible(),false);
  await page.screenshot({path:root+'/cancelled-setup.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  assert.deepEqual(errors,[]);
  console.log('PASS: cross-page prompt stop, retry, drafts after reload, image stop and re-approval, setup stop, mobile; no model/API generation');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

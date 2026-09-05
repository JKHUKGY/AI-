const { chromium } = require('/tmp/web-reference-browser/node_modules/playwright');
const fs = require('fs');
(async () => {
  const base = 'https://scriptwriter-jia.northcentralus.cloudapp.azure.com';
  const browser = await chromium.launch({headless: true, executablePath: "/home/codespace/.cache/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-linux64/chrome-headless-shell"});
  try {
    const context = await browser.newContext({viewport:{width:1440,height:1100}});
    const cookie = fs.readFileSync('tmp/skills-release/browser-cookie.txt','utf8').trim();
    await context.addCookies([{name:'sw_session',value:cookie,url:base,httpOnly:true,secure:true}]);
    const page = await context.newPage(); const errors=[]; page.on('pageerror',err=>errors.push(err.message));
    await page.goto(base+'/#/p/'+encodeURIComponent('Skills调用测试_20260905')+'/skills');
    await page.locator('#skillCatalog button').last().waitFor();
    if(await page.locator('#skillCatalog button').count()!==14) throw Error('catalog count mismatch');
    await page.getByRole('button',{name:'关键帧生成与筛选',exact:true}).click();
    if(await page.locator('#skillMode option').count()!==2) throw Error('missing modes');
    await page.locator('#skillDetail summary').click();
    await page.waitForFunction(()=>document.querySelector('#skillSource').textContent.includes('short-drama-keyframe-gen'));
    await page.screenshot({path:'tmp/skills-release/skills-desktop.png',fullPage:false});
    await page.setViewportSize({width:390,height:844});
    await page.screenshot({path:'tmp/skills-release/skills-mobile.png',fullPage:false});
    const overflow = await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
    await page.getByRole('button',{name:'H3 视频生成（已停用）',exact:true}).click();
    if(!await page.locator('#skillPreview').isDisabled()) throw Error('H3 should be disabled');
    if(errors.length) throw Error(errors.join('\n'));
    const report={catalog:14,keyframe_modes:2,source_loaded:true,h3_disabled:true,js_errors:errors,mobile_horizontal_overflow:overflow};
    fs.writeFileSync('tmp/skills-release/browser-report.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
  } finally { await browser.close();fs.unlinkSync('tmp/skills-release/browser-cookie.txt'); }
})().catch(e=>{console.error(e.message);process.exit(1);});

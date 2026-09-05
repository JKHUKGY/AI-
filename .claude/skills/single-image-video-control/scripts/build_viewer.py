"""Build an offline HTML viewing page from actual files, never invented results."""
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import subprocess


def browser_copy(source):
    target = source.with_suffix('.webm')
    if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        temporary = target.with_name(target.stem + '.partial.webm')
        try:
            subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-threads','2',
                '-i',str(source),'-an','-c:v','libvpx-vp9','-deadline','realtime',
                '-cpu-used','8','-threads','2','-lag-in-frames','0','-crf','30','-b:v','0',str(temporary)],check=True)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
    return target


def build(root):
    root = Path(root)
    view, machine = root/'给人看', root/'机器文件'
    cloud = json.loads((machine/'point_cloud_preview.json').read_text())
    camera = json.loads((machine/'camera_path.json').read_text())
    videos = [
        ('A · 普通图生视频', 'A_baseline.mp4', '首帧与文字。是否通过内容审查请看报告。'),
        ('B · 增加深度控制', 'B_depth_control.mp4', '同首帧、同文字，增加控制视频及适配器。'),
        ('几何重投影预览', 'reprojection_preview.mp4', '由原图和深度计算；边缘补洞不是AI成片。'),
        ('深度控制视频', '../素材/depth_control.mp4', '亮处近、暗处远；这是模型输入。'),
    ]
    cards = []
    for title, file, desc in videos:
        p = view/file
        fallback = ''
        if p.exists():
            webm = browser_copy(p)
            fallback = f'<source src="{html.escape(str(Path(file).with_suffix(".webm")))}" type="video/webm">'
        media = (f'<video class="sync" controls muted playsinline preload="metadata"><source src="{html.escape(file)}" type="video/mp4">{fallback}</video>'
            f'<a download href="{html.escape(file)}">下载原视频</a>') if p.exists() else '<div class="missing">尚未生成结果</div>'
        cards.append(f'<article><h3>{title}</h3>{media}<p>{desc}</p></article>')
    model_done = all((view/f).exists() for f in ['A_baseline.mp4','B_depth_control.mp4'])
    status = 'A/B 模型输出已落地 · 质量结论见报告' if model_done else '控制素材已落地 · A/B 模型输出尚未齐备'
    results = (machine/'viewer_summary.txt').read_text() if (machine/'viewer_summary.txt').exists() else '本页展示文件状态，不自动判定内容质量；请结合独立审查阅读。'
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>单图可控视频 · 研究与 Demo</title><style>
:root{color-scheme:dark;--bg:#10171d;--card:#1a252e;--ink:#eaf1f5;--muted:#a4b5c0;--accent:#7fe0c5}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1350px;margin:auto;padding:40px 28px}h1{font-size:clamp(28px,4vw,44px);line-height:1.2;margin:16px 0}h2{font-size:25px;margin:48px 0 16px}h3{margin:0 0 12px;font-size:18px}p{color:var(--muted)}a{color:var(--accent)}.eyebrow{color:var(--accent);letter-spacing:2px;font-size:13px}.badge{display:inline-block;padding:5px 12px;border:1px solid #38574f;border-radius:18px;font-size:13px;color:var(--accent)}.summary{border-left:3px solid var(--accent);padding:12px 20px;background:var(--card);white-space:pre-line}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}.three{display:grid;grid-template-columns:1fr 1fr 1.3fr;gap:20px}article{background:var(--card);padding:18px;border-radius:12px}video{display:block;width:100%;aspect-ratio:4/7;object-fit:contain;background:#070b0e;border-radius:6px;margin-bottom:10px}img{display:block;width:100%;height:auto;border-radius:6px}canvas{display:block;width:100%;max-width:384px;margin:auto;background:#070b0e;border-radius:6px}button{background:var(--accent);border:0;border-radius:7px;color:#10251f;padding:10px 16px;font-size:15px;cursor:pointer}input[type=range]{width:100%;accent-color:var(--accent)}label{display:block;color:var(--muted);margin-top:12px}.toolbar{display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin:15px 0}.toolbar input{width:min(430px,50vw)}.small{font-size:13px}.missing{aspect-ratio:4/7;display:grid;place-items:center;background:#121a21;color:var(--muted)}details{margin:20px 0;background:var(--card);padding:18px;border-radius:10px}summary{cursor:pointer}.note{color:#f0c98b}footer{border-top:1px solid #34444e;margin-top:40px;padding:20px 0;color:var(--muted);font-size:13px}@media(max-width:950px){.grid{grid-template-columns:repeat(2,1fr)}.three{grid-template-columns:1fr 1fr}.three article:last-child{grid-column:1/-1}}@media(max-width:570px){main{padding:24px 16px}.pair,.three{grid-template-columns:1fr}.grid{gap:8px}.grid article{padding:10px}h3{font-size:15px}}
</style><main><div class="eyebrow">可复现研究 · __DATE__</div><h1>一张图，给摄影机一条明确的路。</h1>
<p>原图 → 相对深度 → 2.5D 点云 → 控制视频 → LTX A/B 实验。本页展示单图小幅运镜控制素材与已落地的实验结果。</p>
<span class="badge">__STATUS__</span><p><a href="../可行性报告.md">阅读完整可行性报告</a> · <a href="../机器文件/review_control.md">控制素材独立审查</a> · <a href="../机器文件/review_video.md">AI 视频独立审查</a></p>
<div class="summary">__SUMMARY__</div>
<h2>同一个镜头，四种视图</h2><div class="toolbar"><button id="play">同步播放</button><button id="reset">回到开头</button><input id="timeline" type="range" min="0" max="__SPAN__" step="0.01" value="0" aria-label="同步时间轴"><span id="time">0.00 秒</span></div><div class="grid">__CARDS__</div>
<p class="small">同步按钮用于浏览对比，浏览器解码可能有轻微时间差；精确逐帧核对请看抽帧与原视频。默认静音，本轮不评价音频。</p>
<h2>原图如何变成空间指示</h2><div class="three"><article><h3>输入的唯一图片</h3><img src="../素材/first_frame.png" alt="选定的单图输入"><p>复用已有场景图，中心裁切和缩放。没有额外视角照片。</p></article><article><h3>AI 估计的相对远近</h3><img src="depth.png" alt="单目相对深度，近白远黑"><p>Depth Anything V2 Small。没有真实米制尺度，也没有补出物体背面。</p></article><article><h3>可交互点云</h3><canvas id="cloud" width="384" height="__CANVAS_H__" aria-label="可交互点云投影"></canvas><label>相机横移 <input id="cx" type="range" min="-0.08" max="0.08" value="0" step="0.002"></label><label>相机前移 <input id="cz" type="range" min="0" max="0.12" value="0" step="0.002"></label><button id="cameraReset">重置视角</button><p class="small">拖动滑条查看不同深度的视差。黑色空缺代表没有样本；坐标为假定单位。<a href="../素材/scene.ply" download>下载 PLY 点云</a></p></article></div>
<details><summary>单张图没有提供什么信息？</summary><p>相机一移动，门框后面原先看不见的区域就会露出来。几何预览用附近已有像素填洞，只为了让控制片连续，不能保证填补区域真实。</p><p class="note">本次 2×2 点投影后的最大未覆盖率：__HOLES__。它不是3D重建完整率。</p><video style="max-width:320px" controls muted preload="metadata" src="coverage_mask.mp4"></video><p>白色是投影未覆盖区域。此实验没有验证人物、口型、360度环绕或完整多镜头一次生成。</p></details>
<footer>几何预览与AI成片分开标注。报告保留模型版本、调用次数、成本及失败；一组样例无法证明首轮成功率。</footer></main><script>
const cloud=__CLOUD__;const canvas=document.getElementById('cloud'),ctx=canvas.getContext('2d');const sorted=cloud.points.sort((a,b)=>b[2]-a[2]);
function draw(){ctx.fillStyle='#070b0e';ctx.fillRect(0,0,canvas.width,canvas.height);const x=+document.getElementById('cx').value,z=+document.getElementById('cz').value,s=384/cloud.width;for(const p of sorted){const zz=p[2]-z;if(zz<=0)continue;const u=(cloud.focal*(p[0]-x)/zz+(cloud.width-1)/2)*s,v=(cloud.focal*p[1]/zz+(cloud.height-1)/2)*s;if(u<0||u>canvas.width||v<0||v>canvas.height)continue;ctx.fillStyle=`rgb(${p[3]},${p[4]},${p[5]})`;ctx.fillRect(u,v,3.2,3.2)}}
document.getElementById('cx').oninput=draw;document.getElementById('cz').oninput=draw;document.getElementById('cameraReset').onclick=()=>{document.getElementById('cx').value=0;document.getElementById('cz').value=0;draw()};draw();
const videos=[...document.querySelectorAll('video.sync')],timeline=document.getElementById('timeline'),play=document.getElementById('play');let running=false;
play.onclick=async()=>{if(running){videos.forEach(v=>v.pause());running=false;play.textContent='同步播放';return;}const t=+timeline.value;videos.forEach(v=>{v.currentTime=t>=+timeline.max?0:t});const results=await Promise.allSettled(videos.map(v=>v.play()));running=results.some(r=>r.status==='fulfilled');play.textContent=running?'暂停':'同步播放'};
timeline.oninput=()=>{videos.forEach(v=>{v.pause();v.currentTime=+timeline.value});running=false;play.textContent='同步播放';document.getElementById('time').textContent=(+timeline.value).toFixed(2)+' 秒'};
document.getElementById('reset').onclick=()=>{timeline.value=0;timeline.oninput()};if(videos[0]){videos[0].ontimeupdate=()=>{if(running){timeline.value=videos[0].currentTime;document.getElementById('time').textContent=videos[0].currentTime.toFixed(2)+' 秒'}};videos[0].onended=()=>{running=false;play.textContent='同步播放'}};
</script></html>'''
    page = page.replace('__DATE__', datetime.now(timezone.utc).date().isoformat()).replace('__SPAN__', str((camera['num_frames']-1)/camera['fps'])).replace('__CANVAS_H__', str(round(384*cloud['height']/cloud['width'])))
    page = page.replace('aspect-ratio:4/7', f"aspect-ratio:{cloud['width']}/{cloud['height']}")
    page = page.replace('__STATUS__', html.escape(status)).replace('__SUMMARY__', html.escape(results))
    page = page.replace('__CARDS__', '\n'.join(cards)).replace('__CLOUD__', json.dumps(cloud, ensure_ascii=False, separators=(',', ':')))
    page = page.replace('__HOLES__', f'{camera["max_unobserved_fraction"]:.3%}')
    if (root/'可行性报告.html').exists():
        page = page.replace('../可行性报告.md', '../可行性报告.html')
    for review in ['review_control', 'review_video']:
        if (machine/(review+'.html')).exists():
            page = page.replace('../机器文件/'+review+'.md', '../机器文件/'+review+'.html')
    mask = view/'coverage_mask.mp4'
    if mask.exists():
        mask_webm = browser_copy(mask)
        page = page.replace('src="coverage_mask.mp4"></video>', '><source src="coverage_mask.mp4" type="video/mp4"><source src="coverage_mask.webm" type="video/webm"></video>')
    (view/'演示首页.html').write_text(page, encoding='utf-8')
    print(view/'演示首页.html')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    build(ap.parse_args().root)

"""2026-09-05 initial manual shot design. After creation, maintain shot_cards.json.
This bootstrap writes cards, never model prompts. Prompts use the skill builder.
"""
import json, math, re
from pathlib import Path

ROOT = Path('/workspaces/AI-')
PROJECT = ROOT / 'output/出狱后我成为了非洲矿王_v3'
OUT = PROJECT / 'videos/ep01'
rows = json.loads((OUT / 'storyboard_snapshot.json').read_text())
registry = {}
for line in (PROJECT / 'keyframes/ep01/keyframes.md').read_text().splitlines():
    if line.startswith('|ep01_镜'):
        c = line.strip('|').split('|')
        registry[int(c[0][-2:])] = c

# Observations below were recorded by opening the 38 selected images.
states = {
1:'全身双人，江砚右中部已迈过敞开的铁门，一脚在前、低头；陈野左前景车旁，右手低持有盖水瓶。铁门不是关闭状态。',
2:'江砚左前景侧背，陈野右侧面对他；陈野左掌已抬起接近江砚肩，右手低持有盖水瓶。拍肩尚未完成。',
3:'陈野右侧右臂已伸出递有盖水瓶；江砚左前景左掌在瓶下摊开，右臂垂下。瓶尚在陈野手中。',
4:'陈野右侧胸上近景，眉间收紧、嘴微张，江砚左缘虚化肩头；手和水瓶在画外。',
5:'江砚右侧近景，低头看瓶盖，右手指已捏住白盖、左手持瓶；盖仍扣在瓶口。',
6:'陈野右侧近景，认真看向左侧江砚，嘴微张；双手在裁切外。',
7:'江砚右侧闭嘴听，右手指停在白瓶盖上，瓶下部裁出画面；盖未取下。',
8:'陈野右侧较宽反打，江砚左前景双手与有盖瓶可见；持瓶/拧盖手序与05、07存在已知差异，按本图保留并登记剪辑风险。',
9:'江砚右侧近景，闭嘴、喉部可见，双手和瓶均在下边界外；尚未在喝水。瓶盖未开仅由07/08接续推定，不是本图可见事实。',
10:'陈野右侧反打，嘴微张、惊讶；江砚左前景背影与已开盖的瓶口可见。',
11:'江砚右侧近景，嘴微张、冷静看陈野，左缘为陈野虚化肩头，手和瓶在画外。',
12:'陈野右侧中景双臂放低，江砚左前景左手持开盖水瓶、右手低持白盖。',
13:'江砚右侧近景，嘴闭合，认真看左侧陈野；双手裁出画面。',
14:'江砚右侧胸上近景，朝左看陈野，嘴闭合，神色沉着；与13角度近似，尚未摇头。',
15:'双人反打，陈野右侧双臂低垂，眼神开始明亮，尚未拍腿；江砚左前景左手开盖瓶、右手白盖。',
16:'全身双人，陈野左侧靠车、江砚右侧面向他；江砚左手瓶、右手白盖靠近瓶口。车仅在最左露出部分车身，副驾门与车内均不可见。',
17:'机场外全景，江砚左前景已经站在玻璃门外，双肩背包，右手箱杆、左手地址纸，低头看纸；苏慧远处右侧，三名旅客位于中远景。',
18:'机场反打全景，苏慧左侧已经走到较近处，双脚落地；江砚右前景侧背、背包仍在肩上。原有旅客在中远景。',
19:'江砚近景，双肩背包带可见，闭嘴看向右侧母亲，双手画外。',
20:'苏慧左侧近景，已经站在儿子面前，闭嘴、眼眶湿润，灰发髻、米色衣裙和灰围裙；江砚右前景虚化。',
21:'江砚较紧近景，背包带仍在，闭嘴看右侧母亲。此时是初到非洲的年轻江砚，未来遭遇只由成年回望旁白叙述。',
22:'苏慧左侧已伸出两掌但尚未接包；江砚右侧三分之二背面，背包仍在肩，右手箱杆、左手纸靠近胸前。',
23:'江砚近景，肩上已没有背包带，闭嘴看右侧母亲，带心疼；手在画外。',
24:'苏慧左侧近景，右手指已触右眼外角，湿眼、闭唇强笑；江砚右缘虚化。左手背包在裁切外，来自前镜接续推定。',
25:'后方全景，苏慧右中已在向纵深走，左手拿背包；江砚左后已跟随，右手拉箱、肩上无包。路径沿画面纵深而非横向右边界。',
26:'客厅全景，母子已在左中站定、不是刚进门；江砚右手拉箱，苏慧右手拿包。刘兰右侧沙发看指甲，顾瑶看手机。母亲持包手与25/32相反。',
27:'沙发双人中景，刘兰左侧右手举在胸前看指甲，顾瑶右侧双手持手机低头。',
28:'苏慧右中胸上近景，已经露上齿陪笑；刘兰左前景侧背，顾瑶左后景手机，江砚右后景带箱站立，四人都在。',
29:'刘兰左侧近景，右手指甲抬在胸前、垂眼看手；顾瑶右侧前景和手机部分入画。尚未吹指甲。',
30:'江砚中右近景朝左，苏慧右前景、刘兰左前景、顾瑶左下后景手机，四人俱在；江砚尚未开口。',
31:'顾瑶右侧近景，低头看画面下方的手机，手机本体在裁切外；刘兰左侧后景虚化，顾瑶尚未抬眼扫视。',
32:'江砚居中站立右手箱杆可见，苏慧右前景背影、左手拿包；刘兰左前景、顾瑶左后景手机。江砚眉间已有紧张。',
33:'右手与黑色箱杆特写，手掌搭着箱杆、四指松垂，拇指在另一侧；还未攥紧。背景为暖色大理石虚化。',
34:'客厅全景，江砚左前已朝左侧楼梯旁过道转身，苏慧跟后且右掌已贴上背肩、左手拿包；两名主人右侧沙发。箱杆与手遮挡，握箱手别不作已核实结论。',
35:'日间客房，苏慧左侧右掌已贴半开门、左手拿包；江砚右侧背影右手拉箱、左手停胸前；左边桌面空，床大多在画外。',
36:'苏慧左侧中景，双手已叠在腹部，门已关；江砚右前景肩头较低、已在坐姿高度，不能重新站起入座。',
37:'江砚坐姿近景，闭嘴向右上看站立母亲，右缘母亲虚化；右后窗外是白天，双手膝盖不在画内。',
38:'江砚左中胸上坐姿近景，闭嘴略仰视右前景站立母亲；右后窗光为白天，尚未点头。',
}

# Manually selected clause boundaries. Joining them exactly reproduces the source.
splits = {
4:['这阵子我查明白了，','你这事根本就是顾浩那小子给你做的局。'],
6:['他和本地矿商马库斯俩人串通好，','伪造了签你英文名的交易合同，'],
12:['这兔崽子也太缺德了！','你前脚刚帮他们家找出三吨储量的金矿，后脚他就卸磨杀驴！'],
15:['好！我就等你这句话呢！','设备、工人我都能搞到，','咱自己找矿自己干，不受他顾家的鸟气！'],
18:['母亲为了供我读书，远赴非洲投奔我远房表叔顾万通，','一去就是七年。'],
24:['这边太阳大，显的，快走吧，','你表叔家都等着呢，特意给你做了接风饭。'],
29:['哟，来了啊，','听你妈说你是名牌大学毕业？'],
31:['妈，人家好不容易从国内来，','不得好好见识见识非洲的好日子？'],
36:['小砚，在人家里住着，多一事不如少一事，','别跟她们顶嘴，啊？'],
37:['你表叔这些年收留我，供你上大学，','咱们得懂得感恩。'],
}

# One authored action/end-state per unit unless an explicitly timed sequence follows.
motions = {
1:['Jiang continues his forward step through the already open gate, raises his chin toward Chen and stops within greeting distance. Chen turns his head toward Jiang, his right hand carrying the capped bottle low.'],
2:['Chen completes one firm pat with his raised left palm on Jiang\'s shoulder, then lowers that hand. Jiang settles his feet facing Chen; Chen\'s right hand carries the capped bottle beside his hip.'],
3:['As Chen speaks, Jiang closes his open left fingers around the offered bottle. Chen releases it and draws his right hand back; Jiang brings his right fingertips to the white cap and glances down at it.'],
4:['Chen\'s brows draw together as his lips articulate the opening clause; his gaze stays on Jiang at the left edge. He ends with a short breath through parted lips.','Chen\'s jaw advances slightly as he identifies the culprit, then settles; his eyes remain on Jiang while his lips finish the accusation.'],
5:['Jiang\'s right fingertips give the cap a small partial twist, then stop with the cap still seated. His eyes lift toward Chen and his mouth remains closed. His left hand supports the bottle.'],
6:['Chen\'s lips move evenly as he names the accomplice; his head inclines a few degrees toward Jiang and then steadies.','Chen\'s brows lower as his lips form the words about the forged signature; his head stays directed toward Jiang and settles at the clause break.'],
7:['Jiang\'s eyes settle on Chen and his eyelids close and open once. His fingertips rest on the seated bottle cap and his lips remain closed as he listens.'],
8:['Chen leans his shoulders slightly toward Jiang while his lips finish the account of planting evidence and calling the police, then settles upright. Jiang maintains the bottle and cap grip visible in the opening image.'],
9:[],
10:['Chen\'s eyebrows lift and his chin draws back a fraction as his lips form the short question; his mouth settles slightly open. Jiang holds the uncapped bottle low in the left foreground.'],
11:['Jiang\'s eyes narrow slightly toward Chen and his lips shape the short answer with a level jaw. His lips close at the end; his shoulders remain settled.'],
12:['Chen\'s jaw tightens and his shoulders rise slightly with an indignant breath as he speaks, then lower. Jiang\'s left hand holds the uncapped bottle and his right holds the white cap low.','Chen\'s lips articulate the contrast between the gold discovery and the betrayal, his brows pressing inward. He ends with his jaw set, both hands low. Jiang keeps bottle and cap in their respective hands.'],
13:['Jiang\'s eyes stay on Chen, his chin dips slightly during the pause before the question, then steadies. His lips remain closed throughout the off-screen question.'],
14:[],
15:['Chen\'s eyes widen; his right palm strikes his own thigh once as he gives the opening exclamation, then rests against the thigh. Jiang listens with bottle in his left hand and white cap in his right.','With his right palm resting on his thigh, Chen\'s shoulders lean forward slightly as his lips offer equipment and workers; he settles at the clause break.','Chen\'s chin lifts a fraction as he voices their plan; his lips finish firmly and close. His right hand remains resting at his thigh while Jiang brings the cap nearer the bottle neck.'],
16:[],
17:['Already outside the terminal, Jiang lifts his eyes from the address paper toward the woman approaching on his right; his lips remain closed. The paper corner flutters in his left hand, his right hand holds the suitcase handle, and both backpack straps stay over his shoulders.'],
18:['Su Hui takes one small remaining step toward Jiang and stops facing him, her shoulders drawing inward. Her eyes lift toward his face while her lips stay closed; Jiang remains in the right foreground with both backpack straps in place.','Standing at the distance reached in the previous segment, Su Hui blinks slowly, her shoulders lifting and settling with a breath. She looks toward Jiang with closed lips; the existing travelers make small weight shifts in the background.'],
19:['Jiang\'s eyes move upward along his mother\'s face and gray hair beyond the right edge, then settle on her eyes. His lips stay closed and his shoulders rise slightly with a quiet breath, backpack straps resting on both shoulders.'],
20:['Already face to face with her son, Su Hui\'s lower eyelids lift and her chin trembles slightly; she takes a shallow breath with closed lips. Jiang remains at the right edge.'],
21:['Jiang\'s brows soften as his gaze rests on his mother to the right. He swallows once and his lips remain closed; the young man\'s expression conveys concern for her fatigue.'],
22:[],
23:['Jiang\'s eyes trace his mother\'s gray hair above the right edge, his throat moves with a small swallow, and his lips articulate his concern. His bare shoulders settle as he finishes looking at her face.'],
24:['Her right fingertips continue the wipe already begun at the outer corner of her eye, then lower beneath the crop. Su Hui\'s lips articulate her explanation, their corners held in a small strained curve while her brows stay pinched.','With her right hand lowered, Su Hui\'s lips form the invitation to the meal. Her small strained smile briefly falters at one corner, then returns; her wet eyes stay directed toward her son.'],
25:['Su Hui continues a few slow steps away along the walkway into the existing depth, the backpack swinging slightly from her left hand. Jiang follows with short steps, his right hand pulling the suitcase along the same path; their distance stays close.'],
26:['Already stopped in the living room, Su Hui draws her shoulders inward and leans forward a fraction. Jiang settles the suitcase upright at his right side; Liu Lan flexes her raised fingertips while Gu Yao\'s thumbs move on her phone.'],
27:['Liu Lan slowly turns her raised right wrist to inspect the nails. Beside her, Gu Yao moves one thumb across her phone screen; both women keep their eyes lowered toward their own hands.'],
28:['Su Hui maintains the tentative smile already on her face as her lips introduce her son, her chin dipping slightly toward the seated women. Jiang stays standing behind her with the suitcase; Liu Lan looks at her nails and Gu Yao looks at her phone.'],
29:['Liu Lan brings her raised nails a little closer and gives them one small puff of breath, then her lips form the short greeting. Her lowered eyes stay on the fingertips.','Her right hand remains lifted after the puff; Liu Lan\'s lips draw out the question while her wrist tilts slightly to inspect another nail. Her gaze stays lowered toward her hand.'],
30:['Jiang\'s lips press into a narrow line as his eyes stay on Liu Lan at the left. His throat shifts with a restrained breath. Su Hui remains at the right foreground; the seated women maintain their places.'],
31:['Gu Yao lifts her eyes from the phone below the crop, briefly scans Jiang toward the left and gives one short nasal scoff. She angles her chin toward her mother behind the left edge as her lips begin the remark.','Still addressing her mother, Gu Yao\'s lips finish the mocking question with one raised mouth corner, then her eyes lower back toward the phone below the crop. Her mother remains seated at the left.'],
32:['Su Hui turns her head slightly toward her son while holding the backpack in her left hand. Jiang\'s brows draw inward and his gaze lowers toward his suitcase; his right fingers remain loose on the handle. Gu Yao stays seated with her phone.'],
33:['Jiang\'s four loose right fingers curl around the black suitcase handle one joint at a time; his thumb braces the opposite side and the knuckles grow pale. His hand holds the completed tight grip through the ending.'],
34:['Su Hui continues the gentle guiding pressure of the right palm already on Jiang\'s upper back. He takes short steps toward the left corridor beside the stairs, the suitcase rolling beside him; her left hand carries the backpack as she follows and speaks. The seated women stay on the sofa.'],
35:[],
36:['With her hands already folded at her abdomen, Su Hui\'s thumbs rub together and her head inclines toward her seated son as her lips quietly begin the advice. Her shoulders stay drawn inward.','Su Hui\'s fingers press together as her lips finish the caution and softly add the final question. She lifts her eyes toward her seated son and holds the expectant look.'],
37:['Seated Jiang keeps his lips closed as his eyes lift toward his standing mother at the upper right. His throat moves with a small swallow and his brows soften.','Continuing the listening posture, Jiang\'s eyelids lower in a slow blink, then open toward his mother. His lower lip presses lightly against the upper lip and his shoulders settle.'],
38:[],
}

camera = {}
for n in range(1,39):
    if n <=16:
        pos = ('From the red-dirt road toward the open prison gate, looking past Chen toward Jiang' if n in (1,5,7,9,11,13,14,16) else 'From the gate side looking past Jiang on the left toward Chen on the road')
    elif n<=25:
        pos = ('From the terminal-side walkway toward the curb, facing Su Hui with Jiang at the right edge' if n in (18,20,22,24) else 'From the pickup area beside Su Hui toward Jiang and the terminal glass')
    elif n<=34:
        pos = ('From beside the stairs toward the living-room window and the sofa on the right' if n in (26,34) else 'From the sofa side toward the standing guests near the stairs' if n in (28,30,32,33) else 'From the west side of the sofa area toward Liu Lan and Gu Yao seated against the marble wall')
    else:
        pos = ('From the window side of the guest room toward Su Hui and the door' if n in (35,36) else 'From the door side of the guest room toward seated Jiang with Su Hui at the right edge')
    framing = 'A steady chest-up close-up retaining the partner at the frame edge'
    if n in (1,16,17,18,25,26,34): framing='A full-body wide composition retaining the established spatial relationships'
    if n in (2,3,8,10,12,15,22,27,32,35): framing='A steady medium two-person composition with the existing hands and props visible'
    if n==19: framing='A steady close-up retaining both backpack straps'
    if n==33: framing='A tight detail of the right hand and suitcase handle against the blurred marble floor'
    camera[n]={'position':pos,'rig':'The camera is locked off at eye level','framing_path':framing,'move':None}
camera[25]['position']='From behind mother and son along the airport walkway toward its existing vanishing point'
camera[33]['rig']='The camera is locked off at hand height'
camera[33]['position']='Beside Jiang at suitcase-handle height on the guest side of the living room'
camera[1].update(rig='The camera rides a slow dolly at eye level', framing_path='Full shot easing toward a medium shot with gate posts still at the sides', move='A small slow push only as far as the medium composition with gate posts visible, then holds at that size')
camera[38].update(rig='The camera rides a slow dolly at seated eye level', framing_path='Chest-up close-up easing to a shoulder close-up', move='A small slow push only as far as a shoulder close-up, then holds at that size with the top of the head comfortably inside the frame')

subjects={
'SC05':'Jiang Yan in a faded blue shirt faces Chen Ye in a brown work shirt and dark neck towel',
'SC06':'Young Jiang Yan in a faded blue shirt reunites with Su Hui in a cream dress, gray apron and gray hair bun',
'SC01':'Jiang Yan and Su Hui are the standing guests; Liu Lan in navy satin and Gu Yao in a white top are the seated hosts',
'SC03日':'Jiang Yan in a faded blue shirt listens to his mother Su Hui in her cream dress and gray apron',
}
env={
'SC05':'the same open rusted prison gate, peeling walls and red-dirt road under hard midday sunlight',
'SC06':'the same terminal glass, concrete canopy and curb under daytime sunlight',
'SC01':'the same double-height living room, black leather sofa and marble TV wall under cool daylight',
'SC03日':'the same guest-room door, plain walls and dark wood floor under daylight from the window',
}
voices={
'陈野':'Chen speaks in Mandarin Chinese with a rough medium-low male voice, direct and emphatic',
'江砚':'Jiang speaks in Mandarin Chinese with a low steady young male voice, measured and restrained',
'苏慧':'Su Hui speaks in Mandarin Chinese with a soft middle-aged female voice, quiet and slightly breathy',
'刘兰':'Liu Lan speaks in Mandarin Chinese with a smooth lower female voice, slow and condescending',
'顾瑶':'Gu Yao speaks in Mandarin Chinese with a brighter young female voice, languid and mocking',
'江砚 OS':'Adult Jiang narrates in Mandarin Chinese with the same low steady male voice, reflective and measured',
}
profiles='角色依据：江砚24岁、地质专业优等生，内敛孝顺；陈野讲义气且直率；苏慧48岁、长期寄人篱下而谨慎；刘兰傲慢、顾瑶轻视穷亲戚。监狱段江砚已遭背叛，机场至客房是初到非洲闪回，不预演后续知情。'
cards=[]

def duration(seconds):
    frames=8*math.ceil((max(4.0,seconds)*24-1)/8)+1
    return frames,round(frames/24,6)

def dlg(text, speaker, slow, off):
    return {'speaker':speaker,'text_zh':text,'delivery_en':voices[speaker], 'pace':'slow' if slow else 'normal','onscreen':not off}

def beat(a,b,motion,dialogue=None):
    return {'t':[round(a,6),round(b,6)],'motion_en':motion,'dialogue':dialogue}

def add_card(n,j,total,part,motion,seconds,extra_beats=None):
    row=rows[n-1]; reg=registry[n]; full=row['台词/旁白']; off='画外音' in full or '旁白' in full
    speaker=full.split('（')[0] if full!='无' else None
    slow=(speaker in ('江砚','苏慧','刘兰','顾瑶') or n==13) and n!=34
    speech=dlg(part,speaker,slow,off) if part else None
    need=(len(re.findall(r'[\u3400-\u9fff]',part))/(3 if slow else 4)+.8) if part else 0
    frames,d=duration(max(seconds,need))
    if d>8.05: raise ValueError((n,j,d,part))
    ident=f'ep01_镜{n:02}'+(f'_u{j}' if total>1 else '')
    path=re.search(r'\((.*?)\)',reg[5]).group(1)
    state=states[n] if j==1 else '计划接续状态（上一段视频尚未生成，需生成后抽尾帧并实际核对）：'+cards[-1]['end_state_zh']
    c={'id':ident,'shot_no':n,'scene':row['场景编号'],'tier':reg[6], 'intent_zh':reg[4],
       'script_ref':row['剧本原文锚点']+'\n'+profiles+'\n验收标准：'+reg[4],
       'scene_plate':reg[2], 'first_frame':str(PROJECT/'keyframes/ep01'/path) if j==1 else None,
       'first_frame_from':f'{cards[-1]["id"]}:last' if j>1 else None,'first_frame_strength':1.0,
       'first_frame_state_zh':state,'first_frame_state_basis':'observed_selected_image' if j==1 else 'planned_previous_tail',
       'camera_en':camera[n].copy(),'subject_lock_en':subjects[row['场景编号']],
       'props_en':['bottle','cap','paper','backpack','suitcase','handle','phone','door','tear'],
       'beats':extra_beats(d) if extra_beats else [beat(0,d,motion,speech)],
       'preserve_en':'the visible faces, hairstyles and clothing match the first frame; the scene remains '+env[row['场景编号']],
       'style_tail_en':'Photorealistic modern African mining drama, natural skin and fabric texture, restrained performance, vertical composition',
       'duration_sec':d,'fps':24,'num_frames':frames,'width':576,'height':1024,'seed':90501000+n*10+j,
       'last_frame':None,'source_duration_sec':float(row['时长(秒)']),
       'end_state_zh':'本段最后动作达成后停留，供后段接续；具体结束态见本卡最后一拍 motion_en。',
       'notes':'仅提示词准备；576×1024测试档，正式档待测试后再出。台词逐字保留；英文正文由技能脚本装配。',
       'readiness':{'status':'prepared_for_export_review','video_generated':False}}
    if total>1: c.update(unit_of=f'ep01_镜{n:02}',unit_index=[j,total])
    sfx='Light dry wind and distant road noise' if n<=16 else 'Distant curb traffic and indistinct terminal ambience' if n<=25 else 'Quiet indoor room tone'
    c['beats'][0]['sfx_en']=sfx
    if j>1: c['readiness']['status']='waiting_previous_tail'
    cards.append(c)
    return c

for n,row in enumerate(rows,1):
    full=row['台词/旁白']; text=full.split('：',1)[1] if full!='无' else ''
    nominal=float(row['时长(秒)'])
    if n==9:
        c=add_card(n,1,1,text,'',7.7,lambda d:[
            beat(0,2.5,'Below the lower crop Jiang\'s right fingers finish unscrewing the cap; his left hand raises the open bottle into view until its rim touches his lips. A faint cap-thread click precedes the lift.'),
            beat(2.5,5,'Jiang tilts the bottle for one small sip, lowers it beneath the crop and swallows, his throat moving once. His gaze settles on Chen at the left edge.'),
            beat(5,d,'Jiang\'s lips form the short answer with a level jaw, then close; his eyes remain on Chen.',dlg(text,'江砚',True,False))])
    elif n==14:
        c=add_card(n,1,1,text,'',4,lambda d:[beat(0,.8,'Jiang turns his head a few degrees left and right once, then settles facing Chen.'),beat(.8,d,'Jiang\'s lips articulate the decision evenly, then close as his gaze remains steady on Chen.',dlg(text,'江砚',True,False))])
    elif n==16:
        c=add_card(n,1,2,'','Jiang gives one small nod, his right fingers tighten the white cap onto the bottle in his left hand, then he turns his shoulders toward the SUV at the left edge. He takes two short steps toward the visible vehicle edge and pauses beside it.',5)
        c['end_state_zh']='江砚已拧紧瓶盖、左手低持瓶，走到画面左缘车辆旁；右手空出，未开副驾门。'
        c=add_card(n,2,2,text,'',7.7,lambda d:[beat(0,4.2,'Jiang pulls the passenger door open with his right hand, bends his knees and lowers himself onto the visible seat. His left hand carries the capped bottle low; the door remains open.'),beat(4.2,d,'Seated Jiang turns his head slightly toward Chen beside the open doorway and his lips form the request, then close.',dlg(text,'江砚',True,False))])
        c.update(first_frame=None,first_frame_from=None,first_frame_state_zh='待补首帧，尚未生成或看图，不是观察结论。补帧设计需求：车外副驾侧中景，江砚站在关闭的副驾门旁，左手持已盖瓶、右手靠近门把；门与车窗内座椅可见，陈野在门外对话方向。')
        c['required_first_frame_zh']='沿用江砚/陈野/车辆身份和正午光，补副驾车门与座椅可读的机位；生成后实际看图，再填写 first_frame 与状态，并重装配。'
        c['first_frame_state_basis']='missing_supplemental_image'
        c['camera_en']={'position':'Outside the SUV passenger side, facing Jiang and the passenger doorway with Chen beside it','rig':'The camera is locked off at seated eye level','framing_path':'A medium view retaining the passenger door and seat','move':None}
        c['scene_plate']='SC05_副驾侧_待补机位'
        c['readiness']['status']='blocked_missing_first_frame'
        c['notes']+=' 镜16第二段仅条件草案，缺副驾首帧，禁止提交；不是上一段尾帧直接续接。'
    elif n==22:
        c=add_card(n,1,1,text,'',7.7,lambda d:[
            beat(0,1.2,'Jiang slides the address paper into his shirt pocket with his left hand and releases the upright suitcase handle with his right. Su Hui keeps both palms extended.'),
            beat(1.2,5.1,'As Su Hui speaks, Jiang slips the backpack straps off his shoulders, lifts the bag forward with both hands, and lowers it into her waiting hands.',dlg('小砚，可算到了，累不累？','苏慧',True,False)),
            beat(5.1,d,'Su Hui settles the backpack handle into her left hand as she finishes the invitation; Jiang releases the bag and returns his right hand to the suitcase handle.',dlg('快跟我回家。','苏慧',True,False))])
    elif n==35:
        c=add_card(n,1,1,'','',7,lambda d:[
            beat(0,2.5,'Su Hui continues pressing the partly open door closed with her right palm until the latch clicks. Jiang lowers his left hand from his chest while holding the suitcase with his right.'),
            beat(2.5,5,'Su Hui lifts the backpack from her left hand onto the existing empty table at the left, releases its handle and turns her shoulders toward her son.'),
            beat(5,d,'Jiang rolls the suitcase a short distance toward the bed foot beyond the crop and bends his knees to sit at the bed edge. Su Hui brings her hands together at her abdomen facing him.')])
    elif n==38:
        c=add_card(n,1,1,text,'',5,lambda d:[beat(0,1.2,'Jiang lowers and raises his chin in one small nod toward his standing mother; his eyes remain angled toward her at the upper right.'),beat(1.2,d,'Jiang\'s lips form the quiet answer, then press gently together. His brows stay softly drawn and his eyes remain on his mother as the camera reaches its final shoulder close-up.',dlg(text,'江砚',True,False))])
    else:
        parts=splits.get(n,[text]); assert ''.join(parts)==text,(n,parts,text)
        assert len(parts)==len(motions[n]),n
        for j,(part,motion) in enumerate(zip(parts,motions[n]),1):
            secs=min(7.7,nominal/len(parts))
            if n==29 and j==1: secs=4.7
            if n==31 and j==1: secs=max(secs,6)
            c=add_card(n,j,len(parts),part,motion,secs)

endings={
4:['陈野仍看江砚，开场句说完短换气、嘴微张，手在画外。','陈野说完指控收口，保持对江砚视线。'],
6:['陈野说完同谋身份，头略向前，嘴在分句间停顿。','陈野说完伪造合同，眉低、头朝江砚、双手画外。'],
12:['陈野说完斥骂，肩落回、双手低；江砚左瓶右盖。','陈野说完金矿与背叛，颌部收紧、双手低。'],
15:['陈野已拍过一次大腿，右掌留在腿侧；江砚左瓶右盖。','陈野已承诺设备工人，右掌仍在腿侧；不得再拍腿。','陈野说完结盟收口；江砚左手持瓶，右手瓶盖靠近瓶口供16拧上。'],
18:['苏慧已走完最后一小步、站定面对儿子，嘴闭合；江砚右前景仍背包。','苏慧站定湿眼看儿子、嘴闭合，不重复走近。'],
24:['苏慧已擦完眼，右手降到画外，小幅强笑、湿眼看儿子；左手包在画外。','苏慧说完接风饭，右手低、左手包，准备带路。'],
29:['刘兰已吹过一次指甲，右手仍举着，低眼，短招呼已说完。','刘兰说完问话，继续看指甲，口型收束。'],
31:['顾瑶已扫过江砚并嗤笑一次，脸略转母亲，首句说完；手机在画外。','顾瑶说完反问后视线落回手机，不再第二次扫视嗤笑。'],
36:['苏慧说完多一事不如少一事，手叠腹前、拇指轻压，面向坐着的儿子。','苏慧说完劝阻抬眼等儿子反应，双手叠着。'],
37:['江砚已吞咽一下，嘴闭、眼看右上母亲，保持坐姿。','江砚闭嘴听完、肩稍落，仍仰看母亲，供38点头。'],
}
for n,values in endings.items():
    group=[c for c in cards if c['shot_no']==n]
    for j,c in enumerate(group):
        c['end_state_zh']=values[j]
        if j: c['first_frame_state_zh']='计划接续状态（上一段视频尚未生成，需抽尾帧后实际核对）：'+values[j-1]

# Record actual staging differences and known project pipeline limits rather than claim text cures them.
risks={
8:'07→08瓶与盖的手序有已选图差异；保持08实图，剪辑需用面部切点遮开换手，效果待视频验证。不得镜像翻图。',
9:'拧盖起点在画外；视频需实际看到瓶入口、吞咽和瓶退出，喝完才说话。',
13:'13→14近似同机位；用问句后的停顿接单次摇头，不新增推镜。',
16:'原分镜上车动作被拆为走到车旁+副驾补机位；u2缺首帧。保留坐下后说原台词，不改为站着说。',
18:'原图母亲已走近；仅补最后一小步，接20已经面对面的状态。',
22:'纸收入口袋及暂放箱杆是为现有双肩包状态安排的道具转移方案；手部复杂，先检查交接完整性，包交接后固定左手。',
25:'已选图朝纵深离开；提示词沿实际路径继续，未按分镜横向右出画重摆。',
26:'25母亲左手包、26右手包、32又左手包，原图存在连戏差异；需剪辑遮开或补图，文字不保证修复。',
27:'原分镜27/29重复吹指甲描述；合并为29一次，27仅检查指甲。保留原文动作一次并登记调整。',
28:'原图已露齿陪笑，从该状态开口；四人必须保留位置。',
31:'嗤笑只在u1一次，32画外继续其下一句，不重演扫视；手机在裁切外。',
32:'母亲左手包；接33时江砚右手仍松搭箱杆，愤怒握紧留给33。',
34:'母亲右掌已贴背，继续推行不再抬手；箱杆遮挡手别存疑，需检查33→34→35，不能宣称已修复。走楼梯旁过道，不上楼。',
35:'桌上放包、床脚停箱和入座补足到36坐姿高度的动作桥；床脚部分画外，先验动作空间，受阻则补客房宽镜。',
36:'已关门、手已叠腹前、儿子已低位，直接劝忍不重复关门入座。',
}
for c in cards:
    n=c['shot_no']
    if n in risks: c['notes']+=' '+risks[n]
    if n in (14,22,23,24,28,29,31,36,38):
        c['known_limit']={'item':'A1：本项目旧LTX管线中，带台词的克制/混合表情易收敛成通用笑容',
          'evidence':'.agents/skills/short-drama-video-gen/references/model_capability_ledger.md A1，旧版ep01镜14/18多轮实测；不是本批生成结果。',
          'decision':'保留原台词与原情绪作为导演目标；这些卡暂停distilled批量提交，交接时改走DFR管线预检并先测24。DFR情绪效果尚未验证，未证明有效前不得批量烧重试或把强笑验成开心。此包不执行切换或生成。'}
        c['readiness']['pipeline_gate']='A1_requires_alternative_pipeline_preflight_and_pilot'
    if n in (1,38):
        c['notes']+=' A8推镜终点限定景别后停住；A9朝向漂移用可见对手视线约束仅为待验证方案，不声称措辞能修好。'
    if any(b.get('dialogue') for b in c['beats']):
        c['notes']+=' A5跨镜同角色声线需听审；文字声线声明不保证音色一致，必要时统一后期配音但保持原台词。'

blocked=[c for c in cards if c['readiness']['status']=='blocked_missing_first_frame']
prepared=[c for c in cards if c not in blocked]
(OUT/'shot_cards.json').write_text(json.dumps(prepared,ensure_ascii=False,indent=2)+'\n')
(OUT/'blocked_shot_cards.json').write_text(json.dumps(blocked,ensure_ascii=False,indent=2)+'\n')
# The missing-image card is deliberately outside the validated runnable-card file.
# Unit counts there describe only the current prepared component; the complete plan keeps the original grouping.
for c in prepared:
    if c['shot_no']==16:
        c.pop('unit_of',None); c.pop('unit_index',None)
        c['planned_unit_index']=[1,2]
        c['notes']+=' 完整镜16共两段；另一段见 blocked_shot_cards.json，当前清单不是完整可批量提交全集。'
(OUT/'shot_cards.json').write_text(json.dumps(prepared,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'prepared_cards':len(prepared),'blocked_cards':len(blocked),'shots':len(set(c['shot_no'] for c in cards)),'tail_dependencies':sum(bool(c.get('first_frame_from')) for c in prepared)},ensure_ascii=False))

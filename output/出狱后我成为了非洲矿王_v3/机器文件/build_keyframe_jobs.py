"""Project adapter for explicit reference choice and consistent framing geometry.

All original skill validation and mechanical assembly are reused unchanged.
Source cards can opt into plate_plus_master anchoring, full-body height measured
head-to-feet, or cropped geometry measured from an explicit primary subject's
headroom. This resolves contradictory framing clauses while preserving the
approved scene, characters, camera direction and body crop.
"""
from pathlib import Path
import importlib.util

ROOT=Path(__file__).resolve().parents[3]
SOURCE=ROOT/'.agents/skills/short-drama-keyframe-gen/scripts/build_keyframe_prompt.py'
spec=importlib.util.spec_from_file_location('v3_keyframe_builder', SOURCE)
builder=importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
_original_anchor=builder.anchor_of
_original_prompt=builder.build_prompt

def anchor_of(card, beat):
    strategy=card.get('reference_strategy')
    if strategy is None:
        return _original_anchor(card, beat)
    if strategy=='plate_only':
        plate=card.get('plate_image')
        if not plate:
            raise ValueError('plate_only requires the approved camera plate')
        return plate, None, 'plate'
    if strategy!='plate_plus_master':
        raise ValueError(f"Unsupported reference_strategy: {strategy}")
    plate=card.get('plate_image'); master=(beat or {}).get('master_frame')
    if not plate or not master:
        raise ValueError('plate_plus_master requires a real plate and selected master')
    return plate, master, 'plate_plus_master'

def build_prompt(card, beat=None):
    prompt=_original_prompt(card, beat)
    if card.get('reference_strategy')=='plate_plus_master':
        prompt=prompt.replace(
            '主帧是从另一个机位拍的，**它的左右关系不适用于本镜**',
            '主帧的取景范围与本镜不同，**它只约束人物身份、服装、道具与光线状态**')
    framing=card.get('framing') or {}
    mode=framing.get('subject_measurement')
    if mode:
        original=(f"画面里最靠前的主体从头顶到画面底边占画幅高度约"
                  f"{round(float(framing['subject_frac'])*100)}%")
        if mode=='full_body':
            replacement=(f"画面里最靠前的完整人物从头顶到鞋底的全身高度占画幅高度约"
                         f"{round(float(framing['subject_frac'])*100)}%")
        elif mode=='detail':
            detail=framing.get('detail_subject_zh')
            if not detail:
                raise ValueError('Detail framing must name its visible subject')
            replacement=(f"画面中特写主体{detail}的可见高度占画幅高度约"
                         f"{round(float(framing['subject_frac'])*100)}%，上下边界按下述局部裁切")
        elif mode=='cropped':
            headroom=float(framing['headroom_frac'])
            if not 0<=headroom<=0.2:
                raise ValueError('Explicit cropped headroom must be between 0 and 0.2')
            subject=framing.get('primary_subject')
            if subject not in {p['name'] for p in card.get('people',[])}:
                raise ValueError('Cropped primary_subject must name a foreground subject')
            replacement=(f"清晰主体{subject}的头顶距画面上边缘约{round(headroom*100)}%；"
                         f"从该人物头顶到画面下边缘占画幅高度约{round((1-headroom)*100)}%，"
                         "下边缘严格按下述身体部位截断；虚焦过肩仅按边缘局部显示")
        else:
            raise ValueError(f'Unsupported subject_measurement: {mode}')
        if original not in prompt:
            raise ValueError('Expected framing measurement clause was not assembled')
        prompt=prompt.replace(original,replacement,1)
    return prompt

builder.anchor_of=anchor_of
builder.build_prompt=build_prompt
if __name__=='__main__':
    builder.main()

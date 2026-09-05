"""Check actual decoded control media and provenance; not a visual-quality judge."""
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess


def verify(root):
    import cv2
    import numpy as np
    from PIL import Image
    root = Path(root)
    machine, assets, view = root / '机器文件', root / '素材', root / '给人看'
    errors, warnings, media = [], [], {}
    required = [machine/'camera_path.json', machine/'depth_provenance.json',
        assets/'first_frame.png', assets/'original.png', assets/'relative_inverse_depth.npy',
        assets/'scene.ply', assets/'depth_control.mp4', view/'reprojection_preview.mp4', view/'coverage_mask.mp4']
    for p in required:
        if not p.is_file() or not p.stat().st_size:
            errors.append(f'Missing or empty: {p}')
    if errors:
        return {'passed': False, 'errors': errors, 'warnings': warnings}
    camera = json.loads((machine/'camera_path.json').read_text())
    provenance = json.loads((machine/'depth_provenance.json').read_text())
    w, h, n, fps = [camera[k] for k in ['width', 'height', 'num_frames', 'fps']]
    if Image.open(assets/'first_frame.png').size != (w, h):
        errors.append('First image size differs from control metadata')
    if hashlib.sha256((assets/'original.png').read_bytes()).hexdigest() != provenance['source_sha256']:
        errors.append('Original image checksum differs from provenance')
    depth = np.load(assets/'relative_inverse_depth.npy')
    if depth.shape != (h,w) or not np.isfinite(depth).all() or depth.min() < 0 or depth.max() > 1:
        errors.append('Relative depth must be finite HxW array in [0,1]')
    for p in [assets/'depth_control.mp4', view/'reprojection_preview.mp4', view/'coverage_mask.mp4', view/'A_baseline.mp4', view/'B_depth_control.mp4']:
        if not p.exists():
            continue
        raw = subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
            '-show_entries', 'stream=width,height,r_frame_rate,nb_read_frames,duration', '-of', 'json', str(p)], text=True)
        info = json.loads(raw)['streams'][0]
        media[p.name] = info
        if (int(info['width']), int(info['height']), int(info['nb_read_frames'])) != (w,h,n):
            errors.append(f'{p.name}: decoded dimensions/frame count mismatch')
        if Fraction(info['r_frame_rate']) != Fraction(fps):
            errors.append(f'{p.name}: fps mismatch')
        if abs(float(info.get('duration', n/fps)) - n/fps) > 1/fps:
            errors.append(f'{p.name}: duration mismatch')
    cap = cv2.VideoCapture(str(assets/'depth_control.mp4'))
    ok, first = cap.read()
    cap.release()
    mae = None
    if ok and depth.shape == (h,w):
        mae = float(np.abs(first[:,:,0].astype(float) - depth*255).mean())
        if mae > 3:
            errors.append(f'First control frame does not match original relative depth: MAE={mae:.2f}')
    else:
        errors.append('Cannot decode first depth frame')
    fraction = camera['max_unobserved_fraction']
    if fraction > 0:
        warnings.append(f'Splat coverage holes reach {fraction:.3%}; nearest-neighbor filling is not hidden-surface reconstruction')
    for filename in ['A_baseline.mp4', 'B_depth_control.mp4']:
        if not (view/filename).exists():
            warnings.append(f'{filename} absent: no actual model output to verify')
    return {'passed': not errors, 'scope': 'file integrity and alignment only; not content or perceptual quality',
        'errors': errors, 'warnings': warnings, 'first_depth_mae_255': mae, 'media': media}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('root', type=Path)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    result = verify(args.root)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    if args.out:
        args.out.write_text(output, encoding='utf-8')
    raise SystemExit(0 if result['passed'] else 1)

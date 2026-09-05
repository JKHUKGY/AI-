"""Single-image relative-depth reconstruction and camera-control material.

This is a 2.5D reconstruction, not a completed 360-degree scene. The RGB preview
is a deterministic reprojection, NOT an AI-generated video. Missing pixels are
filled from nearby known samples; the raw coverage mask is saved separately.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
M = ROOT / '机器文件'
ASSETS = ROOT / '素材'
VIEW = ROOT / '给人看'
W, H, N, FPS = 512, 896, 121, 24
CAM_X, CAM_Z, FOV = 0.06, 0.08, 50.0
MODEL_REVISION = None
CAMERA_KEYS = None


def save_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def infer(source):
    import numpy as np
    import torch
    from PIL import Image, ImageOps
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation
    os.environ.setdefault('HF_HOME', str(M / 'model_cache'))
    torch.set_num_threads(4)
    shutil.copy2(source, ASSETS / 'original.png')
    im = ImageOps.fit(Image.open(source).convert('RGB'), (W, H), method=Image.Resampling.LANCZOS)
    im.save(ASSETS / 'first_frame.png')
    model_id = 'depth-anything/Depth-Anything-V2-Small-hf'
    processor = AutoImageProcessor.from_pretrained(model_id, cache_dir=str(M / 'model_cache'), revision=MODEL_REVISION)
    model = AutoModelForDepthEstimation.from_pretrained(model_id, cache_dir=str(M / 'model_cache'), revision=MODEL_REVISION)
    model.eval()
    start = time.monotonic()
    with torch.inference_mode():
        output = model(**processor(images=im, return_tensors='pt'))
        pred = torch.nn.functional.interpolate(output.predicted_depth.unsqueeze(1), size=(H, W), mode='bicubic', align_corners=False)[0, 0].numpy()
    lo, hi = np.percentile(pred, [1, 99])
    relative_inverse_depth = np.clip((pred - lo) / (hi - lo), 0, 1)
    np.save(ASSETS / 'relative_inverse_depth.npy', relative_inverse_depth)
    Image.fromarray((relative_inverse_depth * 65535).astype(np.uint16)).save(ASSETS / 'depth16.png')
    Image.fromarray((relative_inverse_depth * 255).astype(np.uint8)).save(VIEW / 'depth.png')
    save_json(M / 'depth_provenance.json', {
        'model': model_id, 'revision': getattr(model.config, '_commit_hash', None),
        'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'inference_seconds': time.monotonic() - start, 'device': 'cpu',
        'semantics': 'relative inverse depth; white is near; not metric distance',
        'normalization_percentiles': [1, 99], 'normalization_values': [float(lo), float(hi)],
        'image_preparation': f'center crop to {W}:{H}; Lanczos resize to {W}x{H}',
        'width': W, 'height': H,
    })
    print('Depth inference finished', flush=True)


def writer(path, channels=3):
    return subprocess.Popen(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
        '-f', 'rawvideo', '-pix_fmt', 'rgb24' if channels == 3 else 'gray',
        '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-', '-an',
        '-c:v', 'libx264', '-crf', '16', '-preset', 'fast', '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart', str(path)], stdin=subprocess.PIPE)


def render():
    import numpy as np
    import cv2
    from PIL import Image
    rgb = np.array(Image.open(ASSETS / 'first_frame.png').convert('RGB'))
    inv = np.load(ASSETS / 'relative_inverse_depth.npy')
    # Unknown intrinsics and scale are explicit artistic assumptions.
    fx = (W / 2) / np.tan(np.deg2rad(FOV / 2))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    z = 1.0 / (0.25 + inv)
    x = (xx - (W - 1) / 2) * z / fx
    y = (yy - (H - 1) / 2) * z / fx
    points = np.stack([x, y, z], -1).reshape(-1, 3)
    colors = rgb.reshape(-1, 3)
    # Export a real colored point cloud with the chosen camera coordinates.
    sparse = np.arange(W * H).reshape(H, W)[::4, ::4].ravel()
    cloud = np.concatenate([points[sparse], colors[sparse]], axis=1)
    with (ASSETS / 'scene.ply').open('w') as f:
        f.write(f'ply\nformat ascii 1.0\nelement vertex {len(cloud)}\nproperty float x\nproperty float y\nproperty float z\nproperty uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n')
        np.savetxt(f, cloud, fmt='%.5f %.5f %.5f %d %d %d')
    save_json(M / 'point_cloud_preview.json', {'points': np.round(cloud, 4).tolist(), 'focal': float(fx), 'width': W, 'height': H})
    paths = [(VIEW / 'reprojection_preview.mp4', 3), (ASSETS / 'depth_control.mp4', 1), (VIEW / 'coverage_mask.mp4', 1)]
    pipes = [writer(p, c) for p, c in paths]
    frame_meta = []
    frames_dir = VIEW / 'control_frames'
    frames_dir.mkdir(exist_ok=True)
    try:
        for frame in range(N):
            t = frame / (N - 1)
            ease = t * t * (3 - 2 * t)
            cam = np.array([CAM_X * ease, 0, CAM_Z * ease], np.float32)
            if CAMERA_KEYS:
                for left, right in zip(CAMERA_KEYS, CAMERA_KEYS[1:]):
                    if left['frame'] <= frame <= right['frame']:
                        a = (frame-left['frame'])/(right['frame']-left['frame'])
                        a = a*a*(3-2*a)
                        cam = np.array(left['xyz'], np.float32)*(1-a)+np.array(right['xyz'], np.float32)*a
                        break
            p = points - cam
            u = fx * p[:, 0] / p[:, 2] + (W - 1) / 2
            v = fx * p[:, 1] / p[:, 2] + (H - 1) / 2
            ui, vi = np.floor(u).astype(int), np.floor(v).astype(int)
            # A z-buffer selects the nearest visible surface at every pixel.
            zbuf = np.full(W * H, np.inf, dtype=np.float32)
            splats = []
            for dx, dy in [(0, 0), (1, 0), (0, 1), (1, 1)]:
                a, b = ui + dx, vi + dy
                valid = (a >= 0) & (a < W) & (b >= 0) & (b < H) & (p[:, 2] > 0)
                src = np.flatnonzero(valid)
                dst = b[valid] * W + a[valid]
                np.minimum.at(zbuf, dst, p[src, 2])
                splats.append((src, dst))
            out = np.zeros((W * H, 3), np.uint8)
            for src, dst in splats:
                front = p[src, 2] <= zbuf[dst] + 1e-6
                out[dst[front]] = colors[src[front]]
            valid = np.isfinite(zbuf).reshape(H, W)
            holes = (~valid).astype(np.uint8)
            # Nearest-known fill is explicitly tracked. It cannot reveal hidden surfaces.
            if holes.any():
                _, labels = cv2.distanceTransformWithLabels(holes, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
                known = np.flatnonzero(valid.ravel())
                fill_indices = known[np.maximum(labels.ravel() - 1, 0)]
                out[holes.ravel().astype(bool)] = out[fill_indices[holes.ravel().astype(bool)]]
                zbuf[holes.ravel().astype(bool)] = zbuf[fill_indices[holes.ravel().astype(bool)]]
            gray = np.clip(((1.0 / zbuf) - .25) * 255, 0, 255).astype(np.uint8).reshape(H, W)
            out = out.reshape(H, W, 3)
            if frame == 0:
                # Exact RGB anchor; forward splats would otherwise slightly dilate contours.
                out = rgb.copy()
                gray = (inv * 255).astype(np.uint8)
            for pipe, data in zip(pipes, [out, gray, holes * 255]):
                pipe.stdin.write(data.tobytes())
            frame_meta.append({'frame': frame, 'time': frame / FPS, 'camera_xyz': cam.tolist(), 'unobserved_fraction': float(holes.mean())})
            if frame in {round(k * (N - 1) / 4) for k in range(5)}:
                Image.fromarray(out).save(frames_dir / f'rgb_{frame:03d}.png')
                Image.fromarray(gray).save(frames_dir / f'depth_{frame:03d}.png')
            if frame % 30 == 0:
                print(f'Rendered {frame}/{N-1}, missing={holes.mean():.3%}', flush=True)
    finally:
        for pipe in pipes:
            pipe.stdin.close()
        codes = [pipe.wait() for pipe in pipes]
    if any(codes):
        raise RuntimeError(f'Video encoding failed: {codes}')
    save_json(M / 'camera_path.json', {
        'projection': 'pinhole', 'coordinate_system': 'x right, y down, z forward',
        'horizontal_fov_degrees_assumed': FOV, 'distance_units': 'arbitrary, non-metric',
        'relative_depth_mapping': 'z = 1 / (0.25 + normalized_inverse_depth)',
        'movement': 'explicit camera keyframes; orientation fixed; piecewise smoothstep' if CAMERA_KEYS else f'camera x {CAM_X}, z {CAM_Z}; orientation fixed; smoothstep interpolation',
        'camera_keyframes': CAMERA_KEYS,
        'frames': frame_meta, 'width': W, 'height': H, 'fps': FPS,
        'num_frames': N, 'sample_time_span_sec': (N-1)/FPS, 'encoded_duration_sec': N/FPS,
        'max_unobserved_fraction': max(f['unobserved_fraction'] for f in frame_meta),
        'hole_fill': 'nearest observed sample; not generative completion',
    })
    print('Control videos and point cloud finished', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', type=Path)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--width', type=int, default=512)
    ap.add_argument('--height', type=int, default=896)
    ap.add_argument('--num-frames', type=int, default=121)
    ap.add_argument('--fps', type=int, default=24)
    ap.add_argument('--camera-x', type=float, default=0.06)
    ap.add_argument('--camera-z', type=float, default=0.08)
    ap.add_argument('--fov', type=float, default=50)
    ap.add_argument('--model-revision', help='Hugging Face commit SHA for repeatable depth inference')
    ap.add_argument('--camera-keyframes', type=Path, help='JSON list of {frame:int, xyz:[x,y,z]} in assumed units')
    ap.add_argument('--render-only', action='store_true')
    args = ap.parse_args()
    if args.width < 128 or args.height < 128 or args.width % 64 or args.height % 64:
        ap.error('LTX demo dimensions must be >=128 and divisible by 64')
    if args.num_frames < 9 or (args.num_frames - 1) % 8 or args.fps <= 0:
        ap.error('Require num_frames=8k+1 >=9 and positive fps')
    if not 10 <= args.fov <= 100 or abs(args.camera_x) > .2 or abs(args.camera_z) > .2:
        ap.error('This limited 2.5D demo supports fov 10..100 and camera offsets up to 0.2 arbitrary units')
    ROOT = args.out.resolve()
    M, ASSETS, VIEW = ROOT / '机器文件', ROOT / '素材', ROOT / '给人看'
    W, H, N, FPS = args.width, args.height, args.num_frames, args.fps
    CAM_X, CAM_Z, FOV = args.camera_x, args.camera_z, args.fov
    MODEL_REVISION = args.model_revision
    if args.camera_keyframes:
        CAMERA_KEYS = json.loads(args.camera_keyframes.read_text())
        if len(CAMERA_KEYS)<2 or CAMERA_KEYS[0]['frame']!=0 or CAMERA_KEYS[-1]['frame']!=N-1:
            ap.error('Camera keyframes must span frame 0 through num_frames-1')
        if any(a['frame']>=b['frame'] for a,b in zip(CAMERA_KEYS,CAMERA_KEYS[1:])):
            ap.error('Camera keyframes must have strictly increasing frame indices')
        if any(len(k['xyz'])!=3 or max(abs(float(v)) for v in k['xyz'])>.2 for k in CAMERA_KEYS):
            ap.error('Camera keyframes require three coordinates with absolute values <=0.2')
    if args.render_only:
        import numpy as np
        from PIL import Image
        if np.load(ASSETS / 'relative_inverse_depth.npy').shape != (H, W) or Image.open(ASSETS / 'first_frame.png').size != (W, H):
            ap.error('Existing depth/image dimensions must match --width/--height')
    for folder in [M, ASSETS, VIEW]:
        folder.mkdir(parents=True, exist_ok=True)
    if not args.render_only:
        if not args.source:
            ap.error('--source is required for depth inference')
        infer(args.source)
    render()

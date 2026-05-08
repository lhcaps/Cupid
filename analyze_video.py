import cv2
import os
import numpy as np

# Check video file exists
video_path = 'e:/Macro/Cupid/MedalTVRoblox20260509053121278-trim-1778279513526.mp4'
output_dir = 'e:/Macro/Cupid/datasets/raw_videos/frames/'

print(f'Video exists: {os.path.exists(video_path)}')

# Create output directory
os.makedirs(output_dir, exist_ok=True)
print(f'Output directory: {output_dir}')

# Open video
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print('ERROR: Cannot open video')
else:
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration = frame_count / fps if fps > 0 else 0
    
    print(f'\n=== Video Metadata ===')
    print(f'FPS: {fps}')
    print(f'Resolution: {width}x{height}')
    print(f'Total frames: {frame_count}')
    print(f'Duration: {duration:.2f} seconds ({duration/60:.2f} minutes)')
    
    # Extract frames at specific timestamps
    key_times = [0, 5, 10, 15, 20, 25, 30]
    print(f'\n=== Extracting frames at key timestamps ===')
    
    for t in key_times:
        if t < duration:
            frame_num = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if ret:
                filename = f'frame_t{t:02d}s.png'
                filepath = os.path.join(output_dir, filename)
                cv2.imwrite(filepath, frame)
                print(f'Saved: {filename} (frame {frame_num})')
            else:
                print(f'Failed to read frame at t={t}s')
        else:
            print(f't={t}s exceeds duration ({duration:.2f}s)')
    
    # Extract frames every 0.5 seconds for first 10 seconds
    print(f'\n=== Extracting frames every 0.5s (first 10s) ===')
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    for t in np.arange(0, min(10.5, duration), 0.5):
        frame_num = int(t * fps)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = cap.read()
        if ret:
            filename = f'frame_t{t:.1f}s.png'
            filepath = os.path.join(output_dir, filename)
            cv2.imwrite(filepath, frame)
    
    print(f'Done! Frames saved to {output_dir}')
    cap.release()

# Now analyze frames for UI elements
print('\n=== Analyzing frames for UI elements ===')

frame_files = sorted([f for f in os.listdir(output_dir) if f.endswith('.png')])
print(f'Found {len(frame_files)} frames')

# Load a few key frames to analyze
for frame_name in ['frame_t00s.png', 'frame_t05s.png', 'frame_t10s.png']:
    filepath = os.path.join(output_dir, frame_name)
    if os.path.exists(filepath):
        frame = cv2.imread(filepath)
        print(f'\n--- Analyzing {frame_name} ---')
        print(f'Frame shape: {frame.shape}')
        
        # Analyze top-left region (progress UI)
        h, w = frame.shape[:2]
        top_left = frame[:int(h*0.15), :int(w*0.3)]
        print(f'Top-left region (potential progress UI): {top_left.shape}')
        
        # Analyze top-center region (compass)
        top_center = frame[:int(h*0.1), int(w*0.3):int(w*0.7)]
        print(f'Top-center region (potential compass): {top_center.shape}')
        
        # Save cropped regions for inspection
        base_name = frame_name.replace('.png', '')
        cv2.imwrite(os.path.join(output_dir, f'{base_name}_top_left.png'), top_left)
        cv2.imwrite(os.path.join(output_dir, f'{base_name}_compass.png'), top_center)
        print(f'Saved cropped regions')

print('\n=== Analysis complete ===')

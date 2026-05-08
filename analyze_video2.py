import cv2
import os
import numpy as np

video_path = 'e:/Macro/Cupid/MedalTVRoblox20260509053121278-trim-1778279513526.mp4'
output_dir = 'e:/Macro/Cupid/datasets/raw_videos/frames/'

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
duration = frame_count / fps if fps > 0 else 0

cap.release()

cap = cv2.VideoCapture(video_path)

# Extract frames every second for first 35 seconds
print('=== Extracting frames every second (0-35s) ===')
for t in range(0, 35):
    frame_num = int(t * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
    ret, frame = cap.read()
    if ret:
        filename = f'frame_t{t:02d}s.png'
        filepath = os.path.join(output_dir, filename)
        cv2.imwrite(filepath, frame)

cap.release()

# Analyze frames for the counter pattern
print('\n=== Analyzing frame progression ===')

# Analyze frames at different times to see counter change
print('\n=== Counter Detection Analysis ===')
for t in [0, 5, 10, 15, 20, 25, 30]:
    filepath = os.path.join(output_dir, f'frame_t{t:02d}s.png')
    if os.path.exists(filepath):
        frame = cv2.imread(filepath)
        if frame is not None:
            h, w = frame.shape[:2]
            
            # Look at the counter region (refined based on UI inspection)
            # Progress UI counter appears to be in top-left area
            counter = frame[75:150, 30:300]
            
            # Save the counter region
            cv2.imwrite(os.path.join(output_dir, f'counter_t{t:02d}s.png'), counter)
            print(f'Counter at t={t}s saved')

            # Also save a compass region
            compass = frame[50:100, 900:1600]
            cv2.imwrite(os.path.join(output_dir, f'compass_t{t:02d}s.png'), compass)
            print(f'Compass at t={t}s saved')

# Analyze brightness/color of key UI elements
print('\n=== UI Color Analysis ===')
sample_frame = cv2.imread(os.path.join(output_dir, 'frame_t05s.png'))
if sample_frame is not None:
    h, w = sample_frame.shape[:2]
    
    # Analyze progress counter area
    counter_area = sample_frame[75:150, 30:300]
    avg_brightness = np.mean(counter_area)
    print(f'Counter area avg brightness: {avg_brightness:.1f}')
    
    # Analyze compass area
    compass_area = sample_frame[50:100, 900:1600]
    avg_brightness = np.mean(compass_area)
    print(f'Compass area avg brightness: {avg_brightness:.1f}')
    
    # Analyze full top bar
    top_bar = sample_frame[0:200, 0:w]
    avg_brightness = np.mean(top_bar)
    print(f'Top bar (y=0-200) avg brightness: {avg_brightness:.1f}')

print('\n=== Frame analysis complete ===')
print(f'Resolution: {width}x{height}')
print(f'FPS: {fps:.2f}')
print(f'Duration: {duration:.2f}s')

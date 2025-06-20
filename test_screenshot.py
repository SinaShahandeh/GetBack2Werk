import mss
import os
from datetime import datetime

screenshots_dir = os.path.join(os.getcwd(), 'screenshots')
os.makedirs(screenshots_dir, exist_ok=True)

with mss.mss() as sct:
    # Capture the entire virtual screen
    sct_img = sct.grab(sct.monitors[0])
    
    # Save to file
    filename = os.path.join(screenshots_dir, f'test_screenshot_{datetime.now().strftime("%Y%m%d_%H%M%S")}.png')
    mss.tools.to_png(sct_img.rgb, sct_img.size, output=filename)
    print(f'Screenshot saved to: {filename}')
    print(f'Screenshot size: {sct_img.size}')


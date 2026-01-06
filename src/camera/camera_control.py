"""Platform-specific camera control using v4l2-ctl (Linux) or uvc-util (macOS)."""

import platform
import subprocess
import logging

logger = logging.getLogger('arudart.camera_control')


def apply_camera_settings(device_index, exposure_time_ms=3, auto_exposure=False, 
                          auto_white_balance=False, auto_focus=False):
    """Apply camera settings using platform-specific tools.
    
    Args:
        device_index: Camera device index (0, 1, 2)
        exposure_time_ms: Fixed exposure time in milliseconds
        auto_exposure: Enable auto exposure (default: False)
        auto_white_balance: Enable auto white balance (default: False)
        auto_focus: Enable auto focus (default: False)
    
    Returns:
        bool: True if successful, False otherwise
    """
    system = platform.system()
    
    if system == 'Linux':
        return _apply_v4l2_settings(device_index, exposure_time_ms, auto_exposure, 
                                    auto_white_balance, auto_focus)
    elif system == 'Darwin':  # macOS
        return _apply_uvc_settings(device_index, exposure_time_ms, auto_exposure,
                                   auto_white_balance, auto_focus)
    else:
        logger.warning(f"Unsupported platform: {system}")
        return False


def _apply_v4l2_settings(device_index, exposure_time_ms, auto_exposure, 
                         auto_white_balance, auto_focus):
    """Apply settings using v4l2-ctl (Linux)."""
    device = f"/dev/video{device_index}"
    
    try:
        # Disable auto features
        subprocess.run([
            'v4l2-ctl', '-d', device,
            '--set-ctrl', f'auto_exposure={"1" if auto_exposure else "3"}',  # 1=auto, 3=manual
            '--set-ctrl', f'white_balance_automatic={"1" if auto_white_balance else "0"}',
            '--set-ctrl', f'focus_automatic_continuous={"1" if auto_focus else "0"}',
        ], check=True, capture_output=True)
        
        # Set exposure time (in microseconds, so 3ms = 3000µs)
        exposure_value = int(exposure_time_ms * 1000)
        subprocess.run([
            'v4l2-ctl', '-d', device,
            '--set-ctrl', f'exposure_absolute={exposure_value}',
        ], check=True, capture_output=True)
        
        logger.info(f"Applied v4l2 settings to {device}: exposure={exposure_time_ms}ms ({exposure_value}µs)")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply v4l2 settings to {device}: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error("v4l2-ctl not found - install with: sudo apt-get install v4l-utils")
        return False


def _apply_uvc_settings(device_index, exposure_time_ms, auto_exposure,
                        auto_white_balance, auto_focus):
    """Apply settings using uvc-util (macOS)."""
    device = str(device_index)
    
    # Use local uvc-util binary (in project root)
    import os
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    uvc_util_path = os.path.join(script_dir, 'uvc-util')
    
    # Fall back to system uvc-util if local not found
    if not os.path.exists(uvc_util_path):
        uvc_util_path = 'uvc-util'
    
    try:
        # Build command with all settings in one call
        # IMPORTANT: auto-exposure-mode must be set to manual (1) before exposure-time-abs works
        auto_exposure_mode = '2' if auto_exposure else '1'
        exposure_value = int(exposure_time_ms * 1000)
        
        cmd = [uvc_util_path, '-I', device,
               '-s', f'auto-exposure-mode={auto_exposure_mode}',
               '-s', f'exposure-time-abs={exposure_value}']
        
        # Add white balance if disabled
        if not auto_white_balance:
            cmd.extend(['-s', 'auto-white-balance-temp=0'])
        
        subprocess.run(cmd, check=True, capture_output=True)
        
        logger.info(f"Applied uvc-util settings to device {device}: exposure={exposure_time_ms}ms ({exposure_value}µs), auto_exposure={auto_exposure}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply uvc-util settings to device {device}: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error(f"uvc-util not found at {uvc_util_path} - copy to project root or install system-wide")
        return False

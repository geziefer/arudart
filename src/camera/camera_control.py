"""Platform-specific camera control using v4l2-ctl (Linux) or uvc-util (macOS)."""

import platform
import subprocess
import logging

logger = logging.getLogger('arudart.camera_control')


def apply_camera_settings(device_index, exposure_time_ms=3, contrast=30, gamma=200,
                          auto_exposure=False, auto_white_balance=False, auto_focus=False):
    """Apply camera settings using platform-specific tools.
    
    Args:
        device_index: Camera device index (0, 1, 2)
        exposure_time_ms: Fixed exposure time in milliseconds
        contrast: Image contrast (typically 10-50)
        gamma: Gamma correction (typically 100-400)
        auto_exposure: Enable auto exposure (default: False)
        auto_white_balance: Enable auto white balance (default: False)
        auto_focus: Enable auto focus (default: False)
    
    Returns:
        bool: True if successful, False otherwise
    """
    system = platform.system()
    
    if system == 'Linux':
        return _apply_v4l2_settings(device_index, exposure_time_ms, contrast, gamma,
                                    auto_exposure, auto_white_balance, auto_focus)
    elif system == 'Darwin':  # macOS
        return _apply_uvc_settings(device_index, exposure_time_ms, contrast, gamma,
                                   auto_exposure, auto_white_balance, auto_focus)
    else:
        logger.warning(f"Unsupported platform: {system}")
        return False


def _apply_v4l2_settings(device_index, exposure_time_ms, contrast, gamma,
                         auto_exposure, auto_white_balance, auto_focus):
    """Apply settings using v4l2-ctl (Linux)."""
    device = f"/dev/video{device_index}"
    
    try:
        # Set auto features and fixed values
        exposure_value = int(exposure_time_ms * 1000)
        
        subprocess.run([
            'v4l2-ctl', '-d', device,
            '--set-ctrl', 'auto_exposure=3',  # Always manual (3=manual)
            '--set-ctrl', f'exposure_absolute={exposure_value}',
            '--set-ctrl', 'brightness=-64',  # Fixed: darkest
            '--set-ctrl', f'contrast={contrast}',
            '--set-ctrl', f'gamma={gamma}',
            '--set-ctrl', f'white_balance_automatic={"1" if auto_white_balance else "0"}',
            '--set-ctrl', f'focus_automatic_continuous={"1" if auto_focus else "0"}',
        ], check=True, capture_output=True)
        
        logger.info(f"Applied v4l2 to {device}: exposure={exposure_time_ms}ms, contrast={contrast}, gamma={gamma}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply v4l2 settings to {device}: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error("v4l2-ctl not found - install with: sudo apt-get install v4l-utils")
        return False


def _apply_uvc_settings(device_index, exposure_time_ms, contrast, gamma,
                        auto_exposure, auto_white_balance, auto_focus):
    """Apply settings using uvc-util (macOS)."""
    device = str(device_index)
    
    # Use local uvc-util binary (in project root, same level as main.py)
    import os
    # Get the project root (parent of src/)
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(script_dir)  # Go up one more level from src/camera/
    uvc_util_path = os.path.join(project_root, 'uvc-util')
    
    # Fall back to system uvc-util if local not found
    if not os.path.exists(uvc_util_path):
        uvc_util_path = 'uvc-util'
        logger.warning(f"Local uvc-util not found at {uvc_util_path}, trying system PATH")
    else:
        logger.debug(f"Using local uvc-util at {uvc_util_path}")
    
    try:
        # Build command with all settings in one call
        # IMPORTANT: auto-exposure-mode must be set to manual (1) before exposure-time-abs works
        auto_exposure_mode = '2' if auto_exposure else '1'
        exposure_value = int(exposure_time_ms * 1000)
        
        cmd = [uvc_util_path, '-I', device,
               '-s', 'auto-exposure-mode=1',  # Always manual
               '-s', f'exposure-time-abs={exposure_value}',
               '-s', 'brightness=-0.64',  # Fixed: darkest
               '-s', f'contrast={contrast}',
               '-s', f'gamma={gamma}']
        
        # Add white balance if disabled
        if not auto_white_balance:
            cmd.extend(['-s', 'auto-white-balance-temp=0'])
        
        result = subprocess.run(cmd, check=True, capture_output=True)
        
        logger.info(f"Applied uvc-util to device {device}: exposure={exposure_time_ms}ms, contrast={contrast}, gamma={gamma}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply uvc-util settings to device {device}: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        logger.error(f"uvc-util not found at {uvc_util_path} - copy to project root or install system-wide")
        return False

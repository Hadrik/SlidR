#!/usr/bin/env python3
"""
Comprehensive test script for ESP32 Volume Controller
Tests all communication functions systematically
"""

import sys
import time
from tester import VolumeControllerPC, DeviceConfig, SegmentConfig
from PIL import Image
import io

def create_test_image(width: int, height: int, color: tuple) -> str:
    """Create a test image in memory and return path"""
    img = Image.new('RGB', (width, height), color)
    filename = f'test_img_{color[0]}_{color[1]}_{color[2]}.png'
    img.save(filename)
    return filename

def print_test_header(test_name: str):
    """Print a formatted test header"""
    print(f"\n{'='*60}")
    print(f"TEST: {test_name}")
    print(f"{'='*60}")

def print_result(passed: bool, message: str = ""):
    """Print test result"""
    status = "✓ PASS" if passed else "✗ FAIL"
    print(f"{status}: {message}" if message else status)
    return passed

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else 'COM4'
    
    print("="*60)
    print("ESP32 Volume Controller - Comprehensive Function Test")
    print("="*60)
    print(f"Port: {port}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize controller
    print("Initializing controller...")
    controller = VolumeControllerPC(port)
    time.sleep(0.5)
    
    # Track test results
    tests_passed = 0
    tests_failed = 0
    
    # ========================================================================
    # TEST 1: PING/PONG
    # ========================================================================
    print_test_header("PING/PONG Communication")
    try:
        result = controller.ping()
        if print_result(result, "Device responds to PING"):
            tests_passed += 1
        else:
            tests_failed += 1
            print("Cannot continue without basic communication. Exiting.")
            return 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
        return 1
    
    # ========================================================================
    # TEST 2: GET_STATUS (before configuration)
    # ========================================================================
    print_test_header("GET_STATUS (Initial)")
    try:
        status = controller.get_status()
        if status is not None:
            print(f"  Device Status:")
            print(f"    Awake: {status['awake']}")
            print(f"    Backlight: {status['backlight']}")
            print(f"    Segments: {status['num_segments']}")
            if print_result(True, "Successfully retrieved status"):
                tests_passed += 1
        else:
            print_result(False, "Failed to get status")
            tests_failed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 3: SET_BACKLIGHT
    # ========================================================================
    print_test_header("SET_BACKLIGHT")
    try:
        print("  Setting backlight to 100...")
        controller.set_backlight(100)
        time.sleep(0.2)
        
        print("  Setting backlight to 200...")
        controller.set_backlight(200)
        time.sleep(0.2)
        
        print("  Setting backlight to 50...")
        controller.set_backlight(50)
        time.sleep(0.2)
        
        print("  Setting backlight to 255...")
        controller.set_backlight(255)
        time.sleep(0.2)
        
        if print_result(True, "Backlight commands sent (verify visually if hardware present)"):
            tests_passed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 4: SET_CONFIG
    # ========================================================================
    print_test_header("SET_CONFIG")
    try:
        config = DeviceConfig(
            spi_clk_pin=-1,  # Use HW SPI
            spi_data_pin=-1,
            tft_dc_pin=5,
            tft_backlight_pin=39,
            segments=[
                SegmentConfig(
                    tft_cs_pin=8,
                    pot_pin=34,
                    pot_min_value=0,
                    pot_max_value=4095,
                    image_path='/test_img0.bin'
                ),
                SegmentConfig(
                    tft_cs_pin=6,
                    pot_pin=35,
                    pot_min_value=100,
                    pot_max_value=3995,
                    image_path='/test_img1.bin'
                ),
            ]
        )
        
        print(f"  Uploading config with {len(config.segments)} segments...")
        result = controller.set_config(config)
        
        if print_result(result, "Configuration uploaded successfully"):
            tests_passed += 1
        else:
            print_result(False, "Failed to upload configuration")
            tests_failed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 5: GET_CONFIG
    # ========================================================================
    print_test_header("GET_CONFIG")
    try:
        print("  Requesting configuration from device...")
        retrieved_config = controller.get_config()
        
        if retrieved_config is not None:
            print(f"  Retrieved Config:")
            print(f"    SPI CLK: {retrieved_config.spi_clk_pin}")
            print(f"    SPI DATA: {retrieved_config.spi_data_pin}")
            print(f"    TFT DC: {retrieved_config.tft_dc_pin}")
            print(f"    TFT Backlight: {retrieved_config.tft_backlight_pin}")
            print(f"    Segments: {len(retrieved_config.segments)}")
            
            # Verify it matches what we uploaded
            matches = (
                retrieved_config.spi_clk_pin == config.spi_clk_pin and
                retrieved_config.spi_data_pin == config.spi_data_pin and
                retrieved_config.tft_dc_pin == config.tft_dc_pin and
                retrieved_config.tft_backlight_pin == config.tft_backlight_pin and
                len(retrieved_config.segments) == len(config.segments)
            )
            
            if matches:
                print("  ✓ Retrieved config matches uploaded config")
                for i, seg in enumerate(retrieved_config.segments):
                    print(f"    Segment {i}:")
                    print(f"      CS: {seg.tft_cs_pin}, POT: {seg.pot_pin}")
                    print(f"      Range: {seg.pot_min_value}-{seg.pot_max_value}")
                    print(f"      Image: {seg.image_path}")
                
                if print_result(True, "Configuration verified"):
                    tests_passed += 1
            else:
                print_result(False, "Retrieved config doesn't match uploaded config")
                tests_failed += 1
        else:
            print_result(False, "Failed to get configuration")
            tests_failed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 6: UPLOAD_IMAGE
    # ========================================================================
    print_test_header("UPLOAD_IMAGE")
    try:
        # Create test images
        print("  Creating test images...")
        img_red = create_test_image(128, 128, (255, 0, 0))    # Red
        img_blue = create_test_image(128, 128, (0, 0, 255))   # Blue
        
        print(f"  Uploading {img_red} to /test_img0.bin...")
        result1 = controller.upload_image(img_red, '/test_img0.bin', (128, 128))
        
        print(f"  Uploading {img_blue} to /test_img1.bin...")
        result2 = controller.upload_image(img_blue, '/test_img1.bin', (128, 128))
        
        if result1 and result2:
            if print_result(True, "Images uploaded successfully"):
                tests_passed += 1
        else:
            print_result(False, f"Image upload failed (red={result1}, blue={result2})")
            tests_failed += 1
            
        # Cleanup test images
        import os
        try:
            os.remove(img_red)
            os.remove(img_blue)
        except:
            pass
            
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 7: GET_STATUS (after configuration)
    # ========================================================================
    print_test_header("GET_STATUS (After Configuration)")
    try:
        status = controller.get_status()
        if status is not None:
            print(f"  Device Status:")
            print(f"    Awake: {status['awake']}")
            print(f"    Backlight: {status['backlight']}")
            print(f"    Segments: {status['num_segments']}")
            
            # Should now show 2 segments
            if status['num_segments'] == 2:
                if print_result(True, "Status shows correct number of segments"):
                    tests_passed += 1
            else:
                print_result(False, f"Expected 2 segments, got {status['num_segments']}")
                tests_failed += 1
        else:
            print_result(False, "Failed to get status")
            tests_failed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 8: Multiple PING/PONG (stress test)
    # ========================================================================
    print_test_header("Multiple PING/PONG (Stress Test)")
    try:
        print("  Sending 10 PINGs rapidly...")
        failures = 0
        for i in range(10):
            if not controller.ping():
                failures += 1
            time.sleep(0.05)  # Small delay between pings
        
        if failures == 0:
            if print_result(True, "All 10 PINGs successful"):
                tests_passed += 1
        else:
            print_result(False, f"{failures}/10 PINGs failed")
            tests_failed += 1
    except Exception as e:
        print_result(False, f"Exception: {e}")
        tests_failed += 1
    
    # ========================================================================
    # TEST 9: SLIDER_VALUE monitoring (if hardware present)
    # ========================================================================
    print_test_header("SLIDER_VALUE Monitoring (Optional)")
    print("  Note: This test requires physical potentiometers")
    print("  Listening for slider changes for 10 seconds...")
    print("  (Move your potentiometers if connected)")
    
    slider_changes_detected = []
    
    def on_slider_change(segment_id: int, volume: int):
        slider_changes_detected.append((segment_id, volume))
        print(f"    → Segment {segment_id}: {volume}%")
    
    controller.on_slider_change = on_slider_change
    controller.start()
    
    time.sleep(10)
    
    if len(slider_changes_detected) > 0:
        print_result(True, f"Detected {len(slider_changes_detected)} slider changes")
        tests_passed += 1
    else:
        print("  ℹ No slider changes detected (hardware may not be connected)")
        print("  Skipping this test (not counted as pass or fail)")
    
    controller.stop()
    
    # ========================================================================
    # FINAL RESULTS
    # ========================================================================
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    print(f"Tests Passed: {tests_passed}")
    print(f"Tests Failed: {tests_failed}")
    print(f"Total Tests:  {tests_passed + tests_failed}")
    
    if tests_failed == 0:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\nYour ESP32 volume controller is working perfectly!")
        print("You can now safely remove the debug Serial.println() statements.")
        return 0
    else:
        print(f"\n⚠ {tests_failed} test(s) failed")
        print("Please review the failures above.")
        return 1

if __name__ == '__main__':
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

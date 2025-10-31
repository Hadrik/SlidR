#!/usr/bin/env python3
"""
Interactive test menu for ESP32 Volume Controller
Keeps device awake and allows you to run individual tests
"""

import sys
import time
from tester import VolumeControllerPC, DeviceConfig, SegmentConfig
from PIL import Image
import threading

def test_basic_communication(controller):
    """Test 1: Basic PING/PONG"""
    print("\n[TEST 1] PING/PONG Communication...")
    for i in range(3):
        if controller.ping():
            print(f"  ✓ PING {i+1}/3 successful")
        else:
            print(f"  ✗ PING {i+1}/3 failed")
            return False
        time.sleep(0.1)
    return True

def test_status(controller, expected_segments=None):
    """Test 2: GET_STATUS"""
    print("\n[TEST 2] GET_STATUS...")
    status = controller.get_status()
    if status:
        print(f"  Awake: {status['awake']}")
        print(f"  Backlight: {status['backlight']}")
        print(f"  Segments: {status['num_segments']}")
        if expected_segments is not None and status['num_segments'] != expected_segments:
            print(f"  ✗ Expected {expected_segments} segments, got {status['num_segments']}")
            return False
        print("  ✓ Status retrieved successfully")
        return True
    else:
        print("  ✗ Failed to get status")
        return False

def test_backlight(controller):
    """Test 3: SET_BACKLIGHT"""
    print("\n[TEST 3] SET_BACKLIGHT...")
    for level in [50, 150, 255]:
        controller.set_backlight(level)
        print(f"  Set backlight to {level}")
        time.sleep(0.2)
    print("  ✓ Backlight commands sent")
    return True

def test_configuration(controller):
    """Test 4 & 5: SET_CONFIG and GET_CONFIG"""
    print("\n[TEST 4] SET_CONFIG...")
    
    config = DeviceConfig(
        spi_clk_pin=-1,
        spi_data_pin=-1,
        tft_dc_pin=5,
        tft_backlight_pin=39,
        segments=[
            SegmentConfig(8, 34, 0, 4095, '/test0.bin'),
            SegmentConfig(6, 35, 0, 4095, '/test1.bin'),
        ]
    )
    
    print(f"  Uploading config with {len(config.segments)} segments...")
    if not controller.set_config(config):
        print("  ✗ Configuration upload failed")
        return False
    print("  ✓ Configuration uploaded")
    
    time.sleep(1)  # Give device time to process
    
    print("\n[TEST 5] GET_CONFIG...")
    retrieved = controller.get_config()
    if not retrieved:
        print("  ✗ Failed to retrieve configuration")
        return False
    
    if len(retrieved.segments) == len(config.segments):
        print(f"  ✓ Configuration verified ({len(retrieved.segments)} segments)")
        return True
    else:
        print(f"  ✗ Config mismatch: expected {len(config.segments)}, got {len(retrieved.segments)}")
        return False

def test_image_upload(controller):
    """Test 6: UPLOAD_IMAGE"""
    print("\n[TEST 6] UPLOAD_IMAGE...")
    
    # Create simple test images
    print("  Creating test images...")
    img_red = Image.new('RGB', (64, 64), (255, 0, 0))
    img_blue = Image.new('RGB', (64, 64), (0, 0, 255))
    
    img_red.save('test_red.png')
    img_blue.save('test_blue.png')
    
    print("  Uploading red image...")
    if not controller.upload_image('test_red.png', '/test0.bin', (64, 64)):
        print("  ✗ Red image upload failed")
        return False
    
    print("  Uploading blue image...")
    if not controller.upload_image('test_blue.png', '/test1.bin', (64, 64)):
        print("  ✗ Blue image upload failed")
        return False
    
    print("  ✓ Images uploaded successfully")
    
    # Cleanup
    import os
    try:
        os.remove('test_red.png')
        os.remove('test_blue.png')
    except:
        pass
    
    return True

def main():
    port = sys.argv[1] if len(sys.argv) > 1 else 'COM4'
    
    print("="*60)
    print("ESP32 Volume Controller - Interactive Test Menu")
    print("="*60)
    print(f"Port: {port}\n")
    
    controller = VolumeControllerPC(port)
    
    # Flush any garbage from the serial buffer
    time.sleep(1)
    if controller.serial.in_waiting > 0:
        garbage = controller.serial.read(controller.serial.in_waiting)
        print(f"Flushed {len(garbage)} bytes from buffer")
    
    # Quick connection test before starting background threads
    print("Testing connection...")
    retries = 3
    connected = False
    for attempt in range(retries):
        if controller.ping():
            connected = True
            break
        print(f"  Attempt {attempt+1}/{retries} failed, retrying...")
        time.sleep(0.5)
    
    if not connected:
        print("✗ Failed to connect to device!")
        print("Check that:")
        print("  - Device is connected to", port)
        print("  - Firmware is uploaded and running")
        print("  - No other program is using the port")
        print("  - Try pressing RESET button on the ESP32")
        return 1
    
    print("✓ Connected to device")
    
    # DON'T start background threads - they interfere with manual commands
    # The device will stay awake because we'll be sending commands regularly
    print("Device will stay awake while menu is active\n")
    
    # Menu loop
    last_ping = time.time()
    
    while True:
        # Send periodic ping to keep device awake (every 4 seconds)
        if time.time() - last_ping > 4:
            controller.ping()
            last_ping = time.time()
        
        print("\n" + "="*60)
        print("TEST MENU")
        print("="*60)
        print("1. PING/PONG Test (3x)")
        print("2. Get Device Status")
        print("3. Set Backlight (cycle through levels)")
        print("4. Upload Configuration (2 segments)")
        print("5. Get Configuration")
        print("6. Upload Test Images (red & blue, 64x64)")
        print("7. Upload Custom Images (from files)")
        print("8. Run All Tests")
        print("0. Exit")
        print("="*60)
        
        try:
            choice = input("\nSelect test (0-8): ").strip()
            
            if choice == '0':
                print("\nExiting...")
                break
            
            elif choice == '1':
                test_basic_communication(controller)
            
            elif choice == '2':
                test_status(controller)
            
            elif choice == '3':
                test_backlight(controller)
            
            elif choice == '4':
                test_configuration(controller)
            
            elif choice == '5':
                print("\n[TEST] GET_CONFIG...")
                retrieved = controller.get_config()
                if retrieved:
                    print(f"\n  Configuration:")
                    print(f"    SPI CLK Pin: {retrieved.spi_clk_pin}")
                    print(f"    SPI DATA Pin: {retrieved.spi_data_pin}")
                    print(f"    TFT DC Pin: {retrieved.tft_dc_pin}")
                    print(f"    TFT Backlight Pin: {retrieved.tft_backlight_pin}")
                    print(f"    Number of Segments: {len(retrieved.segments)}")
                    for i, seg in enumerate(retrieved.segments):
                        print(f"\n    Segment {i}:")
                        print(f"      TFT CS Pin: {seg.tft_cs_pin}")
                        print(f"      POT Pin: {seg.pot_pin}")
                        print(f"      POT Range: {seg.pot_min_value} - {seg.pot_max_value}")
                        print(f"      Image Path: {seg.image_path}")
                    print("  ✓ Configuration retrieved successfully")
                else:
                    print("  ✗ Failed to retrieve configuration")
            
            elif choice == '6':
                test_image_upload(controller)
                print("\n>>> Check your displays now! <<<")
                print(">>> Display 0 should be RED <<<")
                print(">>> Display 1 should be BLUE <<<")
                input("\nPress Enter when you've verified the displays...")
            
            elif choice == '7':
                print("\n[TEST] Upload Custom Images...")
                segments = int(input("How many images to upload? "))
                
                for i in range(segments):
                    img_path = input(f"Image file for segment {i}: ").strip()
                    device_path = input(f"Device path (e.g., /img{i}.bin): ").strip() or f'/img{i}.bin'
                    width = int(input(f"Width (default 128): ").strip() or "128")
                    height = int(input(f"Height (default 128): ").strip() or "128")
                    
                    print(f"  Uploading {img_path} to {device_path}...")
                    if controller.upload_image(img_path, device_path, (width, height)):
                        print(f"  ✓ {device_path} uploaded successfully")
                    else:
                        print(f"  ✗ Failed to upload {device_path}")
                
                print("\n>>> Check your displays now! <<<")
                input("\nPress Enter when you've verified the displays...")
            
            elif choice == '8':
                print("\n" + "="*60)
                print("RUNNING ALL TESTS")
                print("="*60)
                
                tests = [
                    ("Basic Communication", lambda: test_basic_communication(controller)),
                    ("Status", lambda: test_status(controller)),
                    ("Backlight Control", lambda: test_backlight(controller)),
                    ("Configuration", lambda: test_configuration(controller)),
                    ("Status (After Config)", lambda: test_status(controller, expected_segments=2)),
                    ("Image Upload", lambda: test_image_upload(controller)),
                ]
                
                passed = 0
                failed = 0
                
                for name, test_func in tests:
                    try:
                        if test_func():
                            passed += 1
                        else:
                            failed += 1
                    except Exception as e:
                        print(f"  ✗ Exception: {e}")
                        failed += 1
                
                print("\n" + "="*60)
                print(f"RESULTS: {passed} passed, {failed} failed")
                print("="*60)
                
                if failed == 0:
                    print("\n🎉 ALL TESTS PASSED!")
                    print("\n>>> Check your displays now! <<<")
                    print(">>> Display 0 should be RED <<<")
                    print(">>> Display 1 should be BLUE <<<")
                    input("\nPress Enter to continue...")
            
            else:
                print("Invalid choice. Please select 0-8.")
        
        except KeyboardInterrupt:
            print("\n\nExiting...")
            break
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
    
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

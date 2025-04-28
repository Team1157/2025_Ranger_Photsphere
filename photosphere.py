import PySpin
import cv2
import os
import time
import numpy as np

# === CONFIG ===
SAVE_DIR = "rov_photosphere"
ROTATION_ANGLES = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]
TILT_ANGLES = [-30, 0, 30]  # You rotate the ROV manually or via code between these
STITCHED_IMG = "stitched.jpg"

def create_save_dir():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)

def acquire_images(cam):
    nodemap = cam.GetNodeMap()
    cam.BeginAcquisition()

    image = cam.GetNextImage()
    if image.IsIncomplete():
        print("Image incomplete")
        return None
    else:
        img_converted = image.Convert(PySpin.PixelFormat_BGR8, PySpin.HQ_LINEAR)
        np_image = img_converted.GetNDArray()
        image.Release()
        return np_image

    cam.EndAcquisition()

def run_capture():
    create_save_dir()
    system = PySpin.System.GetInstance()
    cam_list = system.GetCameras()
    if cam_list.GetSize() == 0:
        print("No camera detected.")
        system.ReleaseInstance()
        return

    cam = cam_list[0]
    cam.Init()

    print("Start capturing images...")

    for tilt in TILT_ANGLES:
        input(f"\nSet ROV tilt to {tilt}°, then press ENTER.")
        for yaw in ROTATION_ANGLES:
            input(f"Rotate ROV to yaw {yaw}°, then press ENTER to capture.")
            frame = acquire_images(cam)
            if frame is not None:
                filename = f"{SAVE_DIR}/tilt{tilt}_yaw{yaw}.jpg"
                cv2.imwrite(filename, frame)
                print(f"Saved {filename}")
            time.sleep(0.5)

    cam.DeInit()
    del cam
    cam_list.Clear()
    system.ReleaseInstance()

    print("\nCapture complete.")

def stitch_photosphere():
    print("Stitching images...")
    images = []
    for tilt in TILT_ANGLES:
        row = []
        for yaw in ROTATION_ANGLES:
            filename = f"{SAVE_DIR}/tilt{tilt}_yaw{yaw}.jpg"
            if os.path.exists(filename):
                img = cv2.imread(filename)
                row.append(img)
        if row:
            row_strip = cv2.hconcat(row)
            images.append(row_strip)
    
    if images:
        final = cv2.vconcat(images)
        cv2.imwrite(STITCHED_IMG, final)
        print(f"Stitched image saved as {STITCHED_IMG}")
        return final
    else:
        print("No images found to stitch.")
        return None

def view_photosphere(img):
    print("Opening photosphere viewer (drag with mouse)...")
    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_MOUSEMOVE:
            offset = x % img.shape[1]
            view = np.roll(img, -offset, axis=1)
            cv2.imshow("Photosphere", view)

    cv2.namedWindow("Photosphere", cv2.WINDOW_NORMAL)
    cv2.setMouseCallback("Photosphere", on_mouse)
    cv2.imshow("Photosphere", img)
    print("Press ESC to exit viewer.")
    while True:
        if cv2.waitKey(20) & 0xFF == 27:
            break
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_capture()
    stitched = stitch_photosphere()
    if stitched is not None:
        view_photosphere(stitched)

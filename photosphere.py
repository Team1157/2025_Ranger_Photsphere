#!/usr/bin/env python3

import cv2
import numpy as np
import time
import threading
import queue
from collections import deque
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import math
import os

class ContinuousPanoramaGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("BHS Robotics photosphere")
        self.root.geometry("1400x900")
        self.root.configure(bg='#000000')
        
        self.cap = None
        # Use cylindrical stitcher for 360-degree panoramas cause otherwise it gets reeeeal confused
        self.stitcher = cv2.Stitcher.create(cv2.Stitcher_SCANS)
        self.frames = []
        self.running = False
        self.auto_mode = False
        self.frame_queue = queue.Queue(maxsize=5)
        self.current_frame = None
        self.previous_frame = None
        self.total_frames = 0
        
        self.current_panorama = None
        self.panorama_lock = threading.Lock()
        
        self.scene_change_threshold = 25.0
        self.capture_interval = 1.5
        self.last_capture_time = 0
        self.min_frames_before_stitch = 3
        self.brightness = 0
        self.contrast = 1.0
        self.camera_source = "webcam"
        
        # 360-degree specific settings, given that im not sure if we'll use these
        self.enable_360_mode = True
        self.cylindrical_projection = True
        self.max_frames_for_360 = 50  # Limit frames to prevent memory issues maybe a non issue
        self.overlap_threshold = 0.3  # For detecting full circle completion
        
        self.continuous_stitching = True
        self.stitch_queue = queue.Queue()
        self.stitching_in_progress = False
        
        self.camera_display_width = 640
        self.camera_display_height = 480
        self.pano_display_height = 350
        
        # Feature detector for the newish 360 mode
        self.feature_detector = cv2.SIFT_create()
        self.feature_matcher = cv2.BFMatcher()
        
        self.setup_ui()
        
    def setup_ui(self):
        main_frame = tk.Frame(self.root, bg='#000000')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.setup_header_section(main_frame)
        self.setup_camera_section(main_frame)
        self.setup_panorama_section(main_frame)
        
    def setup_header_section(self, parent):
        header_frame = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(header_frame, text="🔄 BHS Robosharks photosphere", font=('SF Pro Display', 16, 'bold'), 
                bg='#1c1c1e', fg='#ffffff').pack(pady=10)
        
        button_frame = tk.Frame(header_frame, bg='#1c1c1e')
        button_frame.pack(pady=10)
        
        self.settings_btn = tk.Button(button_frame, text="⚙️ Settings", 
                                    command=self.show_settings,
                                    font=('SF Pro Display', 12),
                                    bg='#8E8E93', fg='#ffffff', relief=tk.FLAT,
                                    width=15, height=1, cursor='hand2')
        self.settings_btn.pack(side=tk.LEFT, padx=5)
        
        self.connect_btn = tk.Button(button_frame, text="🔌 Start Capture", 
                                   command=self.toggle_connection,
                                   font=('SF Pro Display', 14, 'bold'),
                                   bg='#007AFF', fg='#ffffff', relief=tk.FLAT,
                                   height=2, cursor='hand2')
        self.connect_btn.pack(side=tk.LEFT, padx=5)
        
    def setup_camera_section(self, parent):
        self.camera_container = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        self.camera_container.pack(fill=tk.X, pady=(0, 10))
        
        self.left_frame = tk.Frame(self.camera_container, bg='#1c1c1e')
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.right_frame = tk.Frame(self.camera_container, bg='#1c1c1e')
        self.right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        tk.Label(self.left_frame, text="📹 Live Camera Feed", font=('SF Pro Display', 14, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(anchor=tk.W, pady=(0, 5))
        
        self.camera_frame = tk.Frame(self.left_frame, bg='#000000', 
                                   width=self.camera_display_width, 
                                   height=self.camera_display_height)
        self.camera_frame.pack(pady=5)
        self.camera_frame.pack_propagate(False)
        
        self.camera_label = tk.Label(self.camera_frame, bg='#000000', 
                                   text="Camera view will appear here",
                                   font=('SF Pro Display', 18), fg='#3a3a3c')
        self.camera_label.pack(fill=tk.BOTH, expand=True)
        
        tk.Label(self.right_frame, text="📊 Status", font=('SF Pro Display', 14, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(anchor=tk.W, pady=(0, 10))
        
        self.status_label = tk.Label(self.right_frame, 
                                   text="Configure settings\nthen start capture",
                                   font=('SF Pro Display', 12), bg='#1c1c1e', fg='#8e8e93',
                                   wraplength=200, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, pady=5)
        
        self.frame_count_label = tk.Label(self.right_frame, text="Frames: 0", 
                                        font=('SF Pro Display', 12, 'bold'),
                                        bg='#1c1c1e', fg='#34C759')
        self.frame_count_label.pack(anchor=tk.W, pady=5)
        
        self.stitch_status_label = tk.Label(self.right_frame, text="Stitching: Idle", 
                                          font=('SF Pro Display', 12),
                                          bg='#1c1c1e', fg='#FF9500')
        self.stitch_status_label.pack(anchor=tk.W, pady=5)
        
        # Add 360-degree progress indicator
        self.progress_label = tk.Label(self.right_frame, text="360° Progress: 0%", 
                                     font=('SF Pro Display', 12),
                                     bg='#1c1c1e', fg='#007AFF')
        self.progress_label.pack(anchor=tk.W, pady=5)
        
        self.setup_control_buttons(self.right_frame)
        
    def setup_control_buttons(self, parent):
        btn_frame = tk.Frame(parent, bg='#1c1c1e')
        btn_frame.pack(pady=20, anchor=tk.W)
        
        self.end_btn = tk.Button(btn_frame, text="⏹️ End & Save", 
                               command=self.end_and_save,
                               font=('SF Pro Display', 14, 'bold'),
                               bg='#FF3B30', fg='#ffffff', relief=tk.FLAT,
                               width=15, height=2, cursor='hand2',
                               state=tk.DISABLED)
        self.end_btn.pack(pady=5)
        
        self.clear_btn = tk.Button(btn_frame, text="🗑️ Clear", 
                                 command=self.clear_panorama,
                                 font=('SF Pro Display', 12),
                                 bg='#FF9500', fg='#ffffff', relief=tk.FLAT,
                                 width=15, height=1, cursor='hand2',
                                 state=tk.DISABLED)
        self.clear_btn.pack(pady=5)
        
    def setup_panorama_section(self, parent):
        self.pano_frame = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        self.pano_frame.pack(fill=tk.BOTH, expand=True)
        
        header_frame = tk.Frame(self.pano_frame, bg='#1c1c1e')
        header_frame.pack(fill=tk.X, pady=10, padx=10)
        
        tk.Label(header_frame, text="🖼️ Growing  Panorama", font=('SF Pro Display', 16, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(side=tk.LEFT)
        
        self.setup_scrollable_panorama(self.pano_frame)
        
    def setup_scrollable_panorama(self, parent):
        self.scroll_frame = tk.Frame(parent, bg='#1c1c1e')
        self.scroll_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        self.pano_canvas = tk.Canvas(self.scroll_frame, bg='#000000', height=self.pano_display_height)
        self.pano_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.h_scrollbar = tk.Scrollbar(self.scroll_frame, orient=tk.HORIZONTAL, command=self.pano_canvas.xview)
        self.h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.pano_canvas.configure(xscrollcommand=self.h_scrollbar.set)
        
        self.v_scrollbar = tk.Scrollbar(self.scroll_frame, orient=tk.VERTICAL, command=self.pano_canvas.yview)
        self.v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pano_canvas.configure(yscrollcommand=self.v_scrollbar.set)
        
        self.pano_canvas.create_text(400, 150, text=" will grow here as you rotate",
                                   font=('SF Pro Display', 16), fill='#3a3a3c')
            
    def toggle_connection(self):
        if not self.running:
            self.connect_and_start()
        else:
            self.disconnect_and_stop()
            
    def connect_and_start(self):
        try:
            if self.camera_source.lower() == "webcam":
                self.cap = cv2.VideoCapture(0)
                connection_type = "webcam"
            else:
                self.cap = cv2.VideoCapture(self.camera_source)
                connection_type = "MJPEG stream"
                
            if not self.cap.isOpened():
                if self.camera_source.lower() == "webcam":
                    self.cap = cv2.VideoCapture(1)
                    if not self.cap.isOpened():
                        raise ConnectionError("No camera found")
                else:
                    raise ConnectionError(f"Connection error on {connection_type}")
                    
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            if self.camera_source.lower() == "webcam":
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            self.running = True
            self.auto_mode = True
            self.frames.clear()
            self.current_panorama = None
            self.total_frames = 0
            
            self.pano_canvas.delete("all")
            
            self.connect_btn.configure(text="🔌 Disconnect", bg='#8E8E93')
            self.end_btn.configure(state=tk.NORMAL)
            self.clear_btn.configure(state=tk.NORMAL)
            self.status_label.configure(text="Taking initial capture...")
            
            self.capture_thread = threading.Thread(target=self.capture_frames, daemon=True)
            self.capture_thread.start()
            
            time.sleep(0.5)
            self.take_initial_capture()
            
            self.auto_thread = threading.Thread(target=self.auto_capture_loop, daemon=True)
            self.auto_thread.start()
            
            self.stitch_thread = threading.Thread(target=self.continuous_stitch_loop, daemon=True)
            self.stitch_thread.start()
            
            self.update_camera_view()
            
        except Exception as e:
            messagebox.showerror("Error", f"Connection failed: {str(e)}")
            
    def take_initial_capture(self):
        if self.current_frame is not None:
            self.capture_frame_for_panorama()
            self.status_label.configure(text="Initial frame captured!\nRotate slowly for 360°")
        else:
            ret, frame = self.cap.read()
            if ret:
                self.current_frame = frame
                self.capture_frame_for_panorama()
                self.status_label.configure(text="Initial frame captured!\nRotate slowly for 360°")
            
    def disconnect_and_stop(self):
        self.running = False
        self.auto_mode = False
        
        if self.cap:
            self.cap.release()
        
        self.connect_btn.configure(text="🔌 Start Capture", bg='#007AFF')
        self.end_btn.configure(state=tk.DISABLED)
        self.clear_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="Configure settings\nthen start capture")
        self.camera_label.configure(image='', text="Camera view will appear here")
        self.frame_count_label.configure(text="Frames: 0")
        self.stitch_status_label.configure(text="Stitching: Idle")
        self.progress_label.configure(text="360° Progress: 0%")
        
    def apply_brightness_contrast(self, frame):
        if self.brightness != 0 or self.contrast != 1.0:
            frame = cv2.convertScaleAbs(frame, alpha=self.contrast, beta=self.brightness)
        return frame
        
    def capture_frames(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                frame = self.apply_brightness_contrast(frame)
                try:
                    self.frame_queue.put(frame, block=False)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put(frame, block=False)
                    except queue.Empty:
                        pass
            time.sleep(0.03)
            
    def update_camera_view(self):
        if not self.running:
            return
            
        try:
            frame = self.frame_queue.get_nowait()
            self.current_frame = frame.copy()
            
            display_frame = self.resize_for_display(frame, 
                                                  max_width=self.camera_display_width, 
                                                  max_height=self.camera_display_height)
            
            if self.auto_mode:
                display_frame = self.add_capture_overlay(display_frame)
            
            image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(image)
            photo = ImageTk.PhotoImage(image)
            
            self.camera_label.configure(image=photo, text='')
            self.camera_label.image = photo
            
        except queue.Empty:
            pass
            
        self.root.after(33, self.update_camera_view)
        
    def resize_for_display(self, frame, max_width=600, max_height=400):
        h, w = frame.shape[:2]
        scale = min(max_width/w, max_height/h)
        if scale < 1:
            new_w, new_h = int(w*scale), int(h*scale)
            return cv2.resize(frame, (new_w, new_h))
        return frame
        
    def add_capture_overlay(self, frame):
        overlay = frame.copy()
        h, w = frame.shape[:2]
        
        circle_radius = 8
        font_scale = 0.6
        thickness = 2
        
        cv2.circle(overlay, (20, 20), circle_radius, (0, 0, 255), -1)
        cv2.putText(overlay, "Recording", (35, 25), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 0, 255), thickness)
        
        text = f"Frames: {self.total_frames}"
        cv2.putText(overlay, text, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (0, 255, 0), thickness)
        
        # Add rotation indicator
        progress = min(100, (self.total_frames / 30) * 100)  # Estimate progress, thisll change with the actual bot but this is what it is for my 480p webcam
        cv2.putText(overlay, f"Progress: {progress:.0f}%", (10, h-30), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 0), thickness)
        
        return overlay
        
    def auto_capture_loop(self):
        while self.auto_mode and self.running:
            try:
                if self.current_frame is not None:
                    self.process_frame_for_capture()
                    
                time.sleep(0.1)
                
            except Exception as e:
                print(f"Auto capture loop error: {e}")
                
    def process_frame_for_capture(self):
        current_time = time.time()
        
        if current_time - self.last_capture_time < self.capture_interval:
            return
            
        # Stop capturing if we have too many frames so no memory issues please :3
        if self.total_frames >= self.max_frames_for_360:
            return
            
        if self.previous_frame is not None:
            change_score = self.calculate_scene_change(self.previous_frame, self.current_frame)
            
            if change_score > self.scene_change_threshold:
                self.capture_frame_for_panorama()
                self.last_capture_time = current_time
                
        self.previous_frame = self.current_frame.copy()
        
    def calculate_scene_change(self, frame1, frame2):
        h1, w1 = frame1.shape[:2]
        if w1 > 320:
            scale = 320 / w1
            new_w, new_h = int(w1 * scale), int(h1 * scale)
            frame1 = cv2.resize(frame1, (new_w, new_h))
            frame2 = cv2.resize(frame2, (new_w, new_h))
        
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        diff = cv2.absdiff(gray1, gray2)
        
        mean_diff = np.mean(diff)
        
        return mean_diff
        
    def apply_cylindrical_projection(self, frame):
        """Apply cylindrical projection to the frame for better 360-degree stitching"""
        if not self.cylindrical_projection:
            return frame
            
        h, w = frame.shape[:2]
        
        # Calculate focal length (aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa)
        focal_length = w / (2 * np.tan(np.pi / 6.85))  # Assuming 68.5-degree FOV cause there's one chiefdelphi thread from a while ago saying that
        
        # Create coordinate matrices
        x, y = np.meshgrid(np.arange(w), np.arange(h))
        
        # Convert to cylindrical coordinates
        x_c = x - w / 2
        y_c = y - h / 2
        
        # Apply cylindrical projection
        theta = x_c / focal_length
        h_cyl = y_c / np.sqrt(x_c**2 + focal_length**2) * focal_length
        
        # Convert back to image coordinates
        x_new = focal_length * theta + w / 2
        y_new = h_cyl + h / 2
        
        # Create maps for remapping
        map_x = x_new.astype(np.float32)
        map_y = y_new.astype(np.float32)
        
        # Remap the image
        projected = cv2.remap(frame, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
        
        return projected
        
    def capture_frame_for_panorama(self):
        if self.current_frame is None:
            return
            
        frame = self.current_frame.copy()
        h, w = frame.shape[:2]
        if w > 800:
            scale = 800 / w
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
        
        # Apply cylindrical projection for 360-degree mode
        if self.enable_360_mode:
            frame = self.apply_cylindrical_projection(frame)
            
        self.frames.append(frame)
        self.total_frames += 1
        
        # Calculate approximate progress
        progress = min(100, (self.total_frames / 30) * 100)
        
        self.root.after(0, lambda: self.frame_count_label.configure(text=f"Frames: {self.total_frames}"))
        self.root.after(0, lambda: self.progress_label.configure(text=f"360° Progress: {progress:.0f}%"))
        
        if len(self.frames) >= self.min_frames_before_stitch:
            try:
                self.stitch_queue.put("stitch", block=False)
            except queue.Full:
                pass
        
        if self.total_frames == 1:
            status = "First frame captured!\nRotate slowly in one direction"
        elif self.total_frames < 5:
            status = f"Frame {self.total_frames} captured\nKeep rotating slowly"
        elif self.total_frames < 15:
            status = f"Frame {self.total_frames} captured\n360° panorama building..."
        else:
            status = f"Frame {self.total_frames} captured\nNearly complete circle!"
            
        self.root.after(0, lambda: self.status_label.configure(text=status))
        
    def continuous_stitch_loop(self):
        while self.running:
            try:
                self.stitch_queue.get(timeout=1.0)
                
                if not self.stitching_in_progress and len(self.frames) >= self.min_frames_before_stitch:
                    self.stitch_current_frames()
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Stitch loop error: {e}")
                
    def stitch_current_frames(self):
        if self.stitching_in_progress or len(self.frames) < self.min_frames_before_stitch:
            return
            
        self.stitching_in_progress = True
        self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Working...", fg='#FF9500'))
        
        try:
            frame_list = self.frames.copy()
            
            # For 360-degree panoramas, we might need to handle wraparound
            if self.enable_360_mode and len(frame_list) > 10:
                # Try to detect if we've completed a full circle
                if self.detect_full_circle(frame_list):
                    # Add some frames from the beginning to the end for better wraparound
                    frame_list.extend(frame_list[:3])
            
            status, panorama = self.stitcher.stitch(frame_list)
            
            if status == cv2.Stitcher_OK:
                # Post-process for 360-degree panorama
                if self.enable_360_mode:
                    panorama = self.post_process_360_panorama(panorama)
                
                with self.panorama_lock:
                    self.current_panorama = panorama
                
                self.root.after(0, lambda: self.update_panorama_display(panorama))
                self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Success", fg='#34C759'))
                
            else:
                error_msg = self.get_stitch_error_message(status)
                print(f"Stitching failed: {error_msg}")
                self.root.after(0, lambda: self.stitch_status_label.configure(text=f"Stitching: {error_msg}", fg='#FF3B30'))
                
        except Exception as e:
            print(f"Stitching error: {e}")
            self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Error", fg='#FF3B30'))
            
        finally:
            self.stitching_in_progress = False
            
    def detect_full_circle(self, frames):
        """Detect if we've completed a full 360-degree rotation by comparing first and last frames"""
        if len(frames) < 10:
            return False
            
        try:
            # Compare first few frames with last few frames
            first_frame = frames[0]
            last_frame = frames[-1]
            
            # Convert to grayscale
            gray1 = cv2.cvtColor(first_frame, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(last_frame, cv2.COLOR_BGR2GRAY)
            
            # Detect features
            kp1, des1 = self.feature_detector.detectAndCompute(gray1, None)
            kp2, des2 = self.feature_detector.detectAndCompute(gray2, None)
            
            if des1 is not None and des2 is not None and len(des1) > 10 and len(des2) > 10:
                # Match features
                matches = self.feature_matcher.knnMatch(des1, des2, k=2)
                
                # Filter good matches
                good_matches = []
                for match_pair in matches:
                    if len(match_pair) == 2:
                        m, n = match_pair
                        if m.distance < 0.7 * n.distance:
                            good_matches.append(m)
                
                # If we have enough good matches, we might have completed a circle
                if len(good_matches) > 20:
                    return True
                    
        except Exception as e:
            print(f"Circle detection error: {e}")
            
        return False
        
    def post_process_360_panorama(self, panorama):
        """Post-process the panorama for better 360-degree viewing"""
#        try:
            # Remove black borders
#            gray = cv2.cvtColor(panorama, cv2.COLOR_BGR2GRAY)
#            _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
#            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
#            if contours:
                # Find the largest contour (the panorama content)
#                largest_contour = max(contours, key=cv2.contourArea)
#                x, y, w, h = cv2.boundingRect(largest_contour)
                
                # Crop to remove black borders
#TODO                panorama = panorama[y:y+h, x:x+w]
                
#            return panorama
        return panorama            
#        except Exception as e:
#            print(f"Post-processing error: {e}")
#            return panorama
        
    def get_stitch_error_message(self, status):
        error_messages = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS: "Need more images",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "Poor overlap - rotate slower",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "Camera adjust fail"
        }
        return error_messages.get(status, f"Error {status}")
        
    def update_panorama_display(self, panorama):
        try:
            self.pano_canvas.delete("all")
            
            h, w = panorama.shape[:2]
            scale = self.pano_display_height / h
            new_w, new_h = int(w * scale), int(h * scale)
            display_pano = cv2.resize(panorama, (new_w, new_h))
            
            image = cv2.cvtColor(display_pano, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(image)
            photo = ImageTk.PhotoImage(image)
            
            self.pano_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            self.pano_canvas.image = photo
            
            self.pano_canvas.configure(scrollregion=self.pano_canvas.bbox("all"))
            
            # For 360-degree panoramas, don't auto-scroll to the end
            if not self.enable_360_mode:
                self.pano_canvas.xview_moveto(1.0)
            
        except Exception as e:
            print(f"Display update error: {e}")
               
    def end_and_save(self):
        if self.current_panorama is None:
            messagebox.showwarning("Warning", "No panorama to save")
            return
            
        self.auto_mode = False
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG files", "*.jpg"), ("PNG files", "*.png")],
            title="Save Continuous Panorama"
        )
        
        if filename:
            with self.panorama_lock:
                cv2.imwrite(filename, self.current_panorama)
            messagebox.showinfo("Success", f"Panorama saved as {filename}")
            
        self.status_label.configure(text=f"Capture ended\nPanorama saved\n{self.total_frames} frames used")
        self.stitch_status_label.configure(text="Stitching: Complete", fg='#34C759')
        
    def clear_panorama(self):
        self.frames.clear()
        self.current_panorama = None
        self.total_frames = 0
        
        self.pano_canvas.delete("all")
        self.pano_canvas.create_text(400, 150, text="Panorama will grow here as frames are captured",
                                   font=('SF Pro Display', 16), fill='#3a3a3c')
        
        self.frame_count_label.configure(text="Frames: 0")
        self.stitch_status_label.configure(text="Stitching: Idle", fg='#FF9500')
        self.status_label.configure(text="Cleared! Ready for\nnew panorama")
        
    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Continuous Panorama Settings")
        settings_window.geometry("500x500")
        settings_window.configure(bg='#1c1c1e')
        settings_window.resizable(False, False)
        
        tk.Label(settings_window, text="Camera Source:", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=(20,5))
        
        source_var = tk.StringVar(value=self.camera_source)
        source_entry = tk.Entry(settings_window, textvariable=source_var, font=('SF Pro Display', 12),
                               bg='#2c2c2e', fg='#ffffff', insertbackground='#ffffff', 
                               relief=tk.FLAT, bd=5, width=40)
        source_entry.pack(pady=5)
        
        tk.Label(settings_window, text="'webcam' for device camera or MJPEG URL for ROV",
                font=('SF Pro Display', 10), bg='#1c1c1e', fg='#8e8e93').pack(pady=(2,15))
        
        tk.Label(settings_window, text="Scene Change Threshold:", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=(10,5))
        threshold_var = tk.DoubleVar(value=self.scene_change_threshold)
        threshold_scale = tk.Scale(settings_window, from_=10.0, to=80.0, resolution=5.0,
                                 variable=threshold_var, orient=tk.HORIZONTAL, 
                                 bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        threshold_scale.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(settings_window, text="Capture Interval (seconds):", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=(10,5))
        interval_var = tk.DoubleVar(value=self.capture_interval)
        interval_scale = tk.Scale(settings_window, from_=0.5, to=5.0, resolution=0.5,
                                variable=interval_var, orient=tk.HORIZONTAL, 
                                bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        interval_scale.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(settings_window, text="Brightness:", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=(10,5))
        brightness_var = tk.IntVar(value=self.brightness)
        brightness_scale = tk.Scale(settings_window, from_=-100, to=100, resolution=5,
                                   variable=brightness_var, orient=tk.HORIZONTAL, 
                                   bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        brightness_scale.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(settings_window, text="Contrast:", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=(10,5))
        contrast_var = tk.DoubleVar(value=self.contrast)
        contrast_scale = tk.Scale(settings_window, from_=0.5, to=3.0, resolution=0.1,
                                 variable=contrast_var, orient=tk.HORIZONTAL, 
                                 bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        contrast_scale.pack(fill=tk.X, padx=20, pady=5)
        
        def apply_settings():
            self.camera_source = source_var.get().strip()
            self.scene_change_threshold = threshold_var.get()
            self.capture_interval = interval_var.get()
            self.brightness = brightness_var.get()
            self.contrast = contrast_var.get()
            settings_window.destroy()
            messagebox.showinfo("Settings", "Settings applied successfully!")
            
        tk.Button(settings_window, text="Apply Settings", command=apply_settings,
                 bg='#007AFF', fg='#ffffff', relief=tk.FLAT, 
                 font=('SF Pro Display', 14, 'bold'), height=2).pack(pady=30)
        
    def on_closing(self):
        self.running = False
        self.auto_mode = False
        if self.cap:
            self.cap.release()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = ContinuousPanoramaGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    root.minsize(1200, 800)
    
    root.mainloop()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Continuous MJPEG Panorama GUI App
Continuously stitches frames and displays growing panorama in real-time
"""

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
        self.root.title("Wobbegong pano creator")
        self.root.geometry("1400x900")
        self.root.configure(bg='#000000')
        
        # Initialize variables
        self.cap = None
        self.stitcher = cv2.Stitcher.create(cv2.Stitcher_PANORAMA)
        self.frames = []  # Store all captured frames
        self.running = False
        self.auto_mode = False
        self.frame_queue = queue.Queue(maxsize=5)
        self.current_frame = None
        self.previous_frame = None
        self.total_frames = 0
        
        # Panorama tracking
        self.current_panorama = None
        self.panorama_lock = threading.Lock()
        
        # Auto-detection parameters
        self.scene_change_threshold = 25.0  # Minimum change to trigger capture
        self.capture_interval = 1.5  # Minimum seconds between captures
        self.last_capture_time = 0
        self.min_frames_before_stitch = 2  # Minimum frames before attempting stitch
        
        # Stitching control
        self.continuous_stitching = True
        self.stitch_queue = queue.Queue()
        self.stitching_in_progress = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Create the continuous panorama UI"""
        # Main container
        main_frame = tk.Frame(self.root, bg='#000000')
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Top section - Connection
        self.setup_connection_section(main_frame)
        
        # Middle section - Camera and panorama views
        self.setup_camera_section(main_frame)
        
        # Bottom section - Panorama display
        self.setup_panorama_section(main_frame)
        
    def setup_connection_section(self, parent):
        """Setup connection controls"""
        conn_frame = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        conn_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(conn_frame, text="🔄 Continuous Panorama Creator", font=('SF Pro Display', 16, 'bold'), 
                bg='#1c1c1e', fg='#ffffff').pack(pady=10)
        
        # URL input
        url_frame = tk.Frame(conn_frame, bg='#1c1c1e')
        url_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(url_frame, text="Camera Source:", font=('SF Pro Display', 12), 
                bg='#1c1c1e', fg='#ffffff').pack(anchor=tk.W)
        
        self.url_var = tk.StringVar(value="webcam")
        self.url_entry = tk.Entry(url_frame, textvariable=self.url_var, font=('SF Pro Display', 12),
                                 bg='#2c2c2e', fg='#ffffff', insertbackground='#ffffff', 
                                 relief=tk.FLAT, bd=5)
        self.url_entry.pack(fill=tk.X, pady=5)
        
        # Helper text
        helper_text = tk.Label(url_frame, text="💡 'webcam' for device camera or MJPEG URL for wobby", 
                              font=('SF Pro Display', 10), bg='#1c1c1e', fg='#8e8e93')
        helper_text.pack(anchor=tk.W, pady=(2, 0))
        
        # Connect button
        self.connect_btn = tk.Button(conn_frame, text="🔌 start capture ", 
                                   command=self.toggle_connection,
                                   font=('SF Pro Display', 14, 'bold'),
                                   bg='#007AFF', fg='#ffffff', relief=tk.FLAT,
                                   height=2, cursor='hand2')
        self.connect_btn.pack(pady=10)
        
    def setup_camera_section(self, parent):
        """Setup camera view section"""
        camera_container = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        camera_container.pack(fill=tk.X, pady=(0, 10))
        
        # Split into two columns
        left_frame = tk.Frame(camera_container, bg='#1c1c1e')
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        right_frame = tk.Frame(camera_container, bg='#1c1c1e')
        right_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)
        
        # Left: Camera view
        tk.Label(left_frame, text="📹 Live Camera Feed", font=('SF Pro Display', 14, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(anchor=tk.W, pady=(0, 5))
        
        self.camera_label = tk.Label(left_frame, bg='#000000', 
                                   text="Camera view will appear here",
                                   font=('SF Pro Display', 18), fg='#3a3a3c',
                                   width=50, height=15)
        self.camera_label.pack(pady=5)
        
        # Right: Status and controls
        tk.Label(right_frame, text="📊 Status", font=('SF Pro Display', 14, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(anchor=tk.W, pady=(0, 10))
        
        self.status_label = tk.Label(right_frame, 
                                   text="Ready to start\ncontinuous pano",
                                   font=('SF Pro Display', 12), bg='#1c1c1e', fg='#8e8e93',
                                   wraplength=200, justify=tk.LEFT)
        self.status_label.pack(anchor=tk.W, pady=5)
        
        # Frame counter
        self.frame_count_label = tk.Label(right_frame, text="Frames: 0", 
                                        font=('SF Pro Display', 12, 'bold'),
                                        bg='#1c1c1e', fg='#34C759')
        self.frame_count_label.pack(anchor=tk.W, pady=5)
        
        # Stitching status
        self.stitch_status_label = tk.Label(right_frame, text="Stitching: Idle", 
                                          font=('SF Pro Display', 12),
                                          bg='#1c1c1e', fg='#FF9500')
        self.stitch_status_label.pack(anchor=tk.W, pady=5)
        
        # Control buttons
        self.setup_control_buttons(right_frame)
        
    def setup_control_buttons(self, parent):
        """Setup control buttons"""
        btn_frame = tk.Frame(parent, bg='#1c1c1e')
        btn_frame.pack(pady=20, anchor=tk.W)
        
        # End button (main control)
        self.end_btn = tk.Button(btn_frame, text="⏹️ End & Save", 
                               command=self.end_and_save,
                               font=('SF Pro Display', 14, 'bold'),
                               bg='#FF3B30', fg='#ffffff', relief=tk.FLAT,
                               width=15, height=2, cursor='hand2',
                               state=tk.DISABLED)
        self.end_btn.pack(pady=5)
        
        # Settings button
        self.settings_btn = tk.Button(btn_frame, text="⚙️ Settings", 
                                    command=self.show_settings,
                                    font=('SF Pro Display', 12),
                                    bg='#8E8E93', fg='#ffffff', relief=tk.FLAT,
                                    width=15, height=1, cursor='hand2')
        self.settings_btn.pack(pady=5)
        
        # Clear button
        self.clear_btn = tk.Button(btn_frame, text="🗑️ Clear", 
                                 command=self.clear_panorama,
                                 font=('SF Pro Display', 12),
                                 bg='#FF9500', fg='#ffffff', relief=tk.FLAT,
                                 width=15, height=1, cursor='hand2',
                                 state=tk.DISABLED)
        self.clear_btn.pack(pady=5)
        
    def setup_panorama_section(self, parent):
        """Setup panorama display section"""
        pano_frame = tk.Frame(parent, bg='#1c1c1e', relief=tk.RAISED, bd=2)
        pano_frame.pack(fill=tk.BOTH, expand=True)
        
        # Header
        header_frame = tk.Frame(pano_frame, bg='#1c1c1e')
        header_frame.pack(fill=tk.X, pady=10, padx=10)
        
        tk.Label(header_frame, text="🖼️ Growing Panorama", font=('SF Pro Display', 16, 'bold'),
                bg='#1c1c1e', fg='#ffffff').pack(side=tk.LEFT)
        
        # Panorama display with scrolling
        self.setup_scrollable_panorama(pano_frame)
        
    def setup_scrollable_panorama(self, parent):
        """Setup scrollable panorama display"""
        # Create frame for scrollable content
        scroll_frame = tk.Frame(parent, bg='#1c1c1e')
        scroll_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
        # Create canvas and scrollbars
        self.pano_canvas = tk.Canvas(scroll_frame, bg='#000000', height=300)
        self.pano_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Horizontal scrollbar
        h_scrollbar = tk.Scrollbar(scroll_frame, orient=tk.HORIZONTAL, command=self.pano_canvas.xview)
        h_scrollbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.pano_canvas.configure(xscrollcommand=h_scrollbar.set)
        
        # Vertical scrollbar
        v_scrollbar = tk.Scrollbar(scroll_frame, orient=tk.VERTICAL, command=self.pano_canvas.yview)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.pano_canvas.configure(yscrollcommand=v_scrollbar.set)
        
        # Initial placeholder
        self.pano_canvas.create_text(400, 150, text="Panorama will grow here as frames are captured",
                                   font=('SF Pro Display', 16), fill='#3a3a3c')
        
    def toggle_connection(self):
        """Connect/disconnect and start/stop continuous """
        if not self.running:
            self.connect_and_start()
        else:
            self.disconnect_and_stop()
            
    def connect_and_start(self):
        """Connect to stream and start continuous mode"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "not a url smh")
            return
            
        try:
            # Connect to camera
            if url.lower() == "webcam":
                self.cap = cv2.VideoCapture(0)
                connection_type = "webcam"
            else:
                self.cap = cv2.VideoCapture(url)
                connection_type = "MJPEG stream"
                
            if not self.cap.isOpened():
                # Try secondary webcam if primary fails
                if url.lower() == "webcam":
                    self.cap = cv2.VideoCapture(1)
                    if not self.cap.isOpened():
                        raise ConnectionError("No camera :megamind:")
                else:
                    raise ConnectionError(f"connection error on {connection_type}")
                    
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            # Set webcam properties if using webcam
            if url.lower() == "webcam":
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
            
            # Start everything
            self.running = True
            self.auto_mode = True
            self.frames.clear()
            self.current_panorama = None
            self.total_frames = 0
            
            # Clear the panorama display
            self.pano_canvas.delete("all")
            
            # Update UI
            self.connect_btn.configure(text="🔌 Disconnect", bg='#8E8E93')
            self.end_btn.configure(state=tk.NORMAL)
            self.clear_btn.configure(state=tk.NORMAL)
            self.status_label.configure(text="Scanning for scene changes...\N rotate wobby sorta slowly")
            
            # Start threads
            self.capture_thread = threading.Thread(target=self.capture_frames, daemon=True)
            self.capture_thread.start()
            
            self.auto_thread = threading.Thread(target=self.auto_capture_loop, daemon=True)
            self.auto_thread.start()
            
            self.stitch_thread = threading.Thread(target=self.continuous_stitch_loop, daemon=True)
            self.stitch_thread.start()
            
            # Start UI updates
            self.update_camera_view()
            
        except Exception as e:
            messagebox.showerror("Error", f" {str(e)}")
            
    def disconnect_and_stop(self):
        """Disconnect and stop all operations"""
        self.running = False
        self.auto_mode = False
        
        if self.cap:
            self.cap.release()
        
        # Reset UI
        self.connect_btn.configure(text="🔌 Start Continuous Mode", bg='#007AFF')
        self.end_btn.configure(state=tk.DISABLED)
        self.clear_btn.configure(state=tk.DISABLED)
        self.status_label.configure(text="Ready to start\ncontinuous pano")
        self.camera_label.configure(image='', text="Camera view will appear here")
        self.frame_count_label.configure(text="Frames: 0")
        self.stitch_status_label.configure(text="Stitching: Idle")
        
    def capture_frames(self):
        """Background thread for capturing frames"""
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                try:
                    self.frame_queue.put(frame, block=False)
                except queue.Full:
                    try:
                        self.frame_queue.get_nowait()
                        self.frame_queue.put(frame, block=False)
                    except queue.Empty:
                        pass
            time.sleep(0.03)  # ~30 FPS
            
    def update_camera_view(self):
        """Update camera view in GUI"""
        if not self.running:
            return
            
        try:
            frame = self.frame_queue.get_nowait()
            self.current_frame = frame.copy()
            
            # Resize for display
            display_frame = self.resize_for_display(frame, max_width=400, max_height=300)
            
            # Add overlay
            if self.auto_mode:
                display_frame = self.add_capture_overlay(display_frame)
            
            # Convert to PhotoImage
            image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(image)
            photo = ImageTk.PhotoImage(image)
            
            self.camera_label.configure(image=photo, text='')
            self.camera_label.image = photo
            
        except queue.Empty:
            pass
            
        # Schedule next update
        self.root.after(33, self.update_camera_view)  # ~30 FPS
        
    def resize_for_display(self, frame, max_width=600, max_height=400):
        """Resize frame for display"""
        h, w = frame.shape[:2]
        scale = min(max_width/w, max_height/h)
        if scale < 1:
            new_w, new_h = int(w*scale), int(h*scale)
            return cv2.resize(frame, (new_w, new_h))
        return frame
        
    def add_capture_overlay(self, frame):
        """Add capture mode overlay"""
        overlay = frame.copy()
        h, w = frame.shape[:2]
        
        # Add recording indicator
        cv2.circle(overlay, (20, 20), 8, (0, 0, 255), -1)
        cv2.putText(overlay, "CAPTURING", (35, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # Add frame count
        text = f"Frames: {self.total_frames}"
        cv2.putText(overlay, text, (10, h-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return overlay
        
    def auto_capture_loop(self):
        """Main automatic capture loop"""
        while self.auto_mode and self.running:
            try:
                if self.current_frame is not None:
                    self.process_frame_for_capture()
                    
                time.sleep(0.1)  # 10 FPS processing
                
            except Exception as e:
                print(f"Auto capture loop error: {e}")
                
    def process_frame_for_capture(self):
        """Process current frame for capture decision"""
        current_time = time.time()
        
        # Skip if too soon since last capture
        if current_time - self.last_capture_time < self.capture_interval:
            return
            
        # Calculate scene change
        if self.previous_frame is not None:
            change_score = self.calculate_scene_change(self.previous_frame, self.current_frame)
            
            if change_score > self.scene_change_threshold:
                self.capture_frame_for_panorama()
                self.last_capture_time = current_time
                
        self.previous_frame = self.current_frame.copy()
        
    def calculate_scene_change(self, frame1, frame2):
        """Calculate scene change score between two frames"""
        # Resize frames for faster processing
        h1, w1 = frame1.shape[:2]
        if w1 > 320:
            scale = 320 / w1
            new_w, new_h = int(w1 * scale), int(h1 * scale)
            frame1 = cv2.resize(frame1, (new_w, new_h))
            frame2 = cv2.resize(frame2, (new_w, new_h))
        
        # Convert to grayscale
        gray1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
        
        # Calculate absolute difference
        diff = cv2.absdiff(gray1, gray2)
        
        # Calculate mean difference
        mean_diff = np.mean(diff)
        
        return mean_diff
        
    def capture_frame_for_panorama(self):
        """Capture current frame for panorama"""
        if self.current_frame is None:
            return
            
        # Resize frame for processing
        frame = self.current_frame.copy()
        h, w = frame.shape[:2]
        if w > 800:
            scale = 800 / w
            new_w, new_h = int(w * scale), int(h * scale)
            frame = cv2.resize(frame, (new_w, new_h))
            
        self.frames.append(frame)
        self.total_frames += 1
        
        # Update UI
        self.root.after(0, lambda: self.frame_count_label.configure(text=f"Frames: {self.total_frames}"))
        
        # Queue for stitching if we have enough frames
        if len(self.frames) >= self.min_frames_before_stitch:
            try:
                self.stitch_queue.put("stitch", block=False)
            except queue.Full:
                pass  # Already queued
        
        # Update status
        if self.total_frames == 1:
            status = "First frame captured!\nContinue moving camera"
        elif self.total_frames < 5:
            status = f"Frame {self.total_frames} captured\nKeep moving for panorama"
        else:
            status = f"Frame {self.total_frames} captured\nPanorama growing..."
            
        self.root.after(0, lambda: self.status_label.configure(text=status))
        
    def continuous_stitch_loop(self):
        """Continuous stitching loop"""
        while self.running:
            try:
                # Wait for stitch request
                self.stitch_queue.get(timeout=1.0)
                
                if not self.stitching_in_progress and len(self.frames) >= self.min_frames_before_stitch:
                    self.stitch_current_frames()
                    
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Stitch loop error: {e}")
                
    def stitch_current_frames(self):
        """Stitch current frames into panorama"""
        if self.stitching_in_progress or len(self.frames) < self.min_frames_before_stitch:
            return
            
        self.stitching_in_progress = True
        self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Working...", fg='#FF9500'))
        
        try:
            # Use all available frames
            frame_list = self.frames.copy()
            
            # Attempt stitching
            status, panorama = self.stitcher.stitch(frame_list)
            
            if status == cv2.Stitcher_OK:
                with self.panorama_lock:
                    self.current_panorama = panorama
                
                # Update display
                self.root.after(0, lambda: self.update_panorama_display(panorama))
                self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Success", fg='#34C759'))
                
            else:
                # Handle stitching errors
                error_msg = self.get_stitch_error_message(status)
                print(f"Stitching failed: {error_msg}")
                self.root.after(0, lambda: self.stitch_status_label.configure(text=f"Stitching: {error_msg}", fg='#FF3B30'))
                
        except Exception as e:
            print(f"Stitching error: {e}")
            self.root.after(0, lambda: self.stitch_status_label.configure(text="Stitching: Error", fg='#FF3B30'))
            
        finally:
            self.stitching_in_progress = False
            
    def get_stitch_error_message(self, status):
        """Get human-readable error message"""
        error_messages = {
            cv2.Stitcher_ERR_NEED_MORE_IMGS: "Need more images",
            cv2.Stitcher_ERR_HOMOGRAPHY_EST_FAIL: "Poor overlap",
            cv2.Stitcher_ERR_CAMERA_PARAMS_ADJUST_FAIL: "Camera adjust fail"
        }
        return error_messages.get(status, f"Error {status}")
        
    def update_panorama_display(self, panorama):
        """Update the panorama display"""
        try:
            # Clear previous panorama
            self.pano_canvas.delete("all")
            
            # Resize panorama for display
            display_height = 280
            h, w = panorama.shape[:2]
            scale = display_height / h
            new_w, new_h = int(w * scale), int(h * scale)
            display_pano = cv2.resize(panorama, (new_w, new_h))
            
            # Convert to PhotoImage
            image = cv2.cvtColor(display_pano, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(image)
            photo = ImageTk.PhotoImage(image)
            
            # Display in canvas
            self.pano_canvas.create_image(0, 0, anchor=tk.NW, image=photo)
            self.pano_canvas.image = photo  # Keep reference
            
            # Update scroll region
            self.pano_canvas.configure(scrollregion=self.pano_canvas.bbox("all"))
            
            # Auto-scroll to show the latest part (right side)
            self.pano_canvas.xview_moveto(1.0)
            
        except Exception as e:
            print(f"Display update error: {e}")
            
    def end_and_save(self):
        """End capture and save panorama"""
        if self.current_panorama is None:
            messagebox.showwarning("Warning", "No panorama to save")
            return
            
        # Stop capture but keep display
        self.auto_mode = False
        
        # Save panorama
        filename = filedialog.asksaveasfilename(
            defaultextension=".jpg",
            filetypes=[("JPEG files", "*.jpg"), ("PNG files", "*.png")],
            title="Save Continuous Panorama"
        )
        
        if filename:
            with self.panorama_lock:
                cv2.imwrite(filename, self.current_panorama)
            messagebox.showinfo("Success", f"Panorama saved as {filename}")
            
        # Update UI
        self.status_label.configure(text=f"Capture ended\nPanorama saved\n{self.total_frames} frames used")
        self.stitch_status_label.configure(text="Stitching: Complete", fg='#34C759')
        
    def clear_panorama(self):
        """Clear current panorama and start fresh"""
        self.frames.clear()
        self.current_panorama = None
        self.total_frames = 0
        
        # Clear display
        self.pano_canvas.delete("all")
        self.pano_canvas.create_text(400, 150, text="Panorama will grow here as frames are captured",
                                   font=('SF Pro Display', 16), fill='#3a3a3c')
        
        # Update UI
        self.frame_count_label.configure(text="Frames: 0")
        self.stitch_status_label.configure(text="Stitching: Idle", fg='#FF9500')
        self.status_label.configure(text="Cleared! Ready for\nnew panorama")
        
    def show_settings(self):
        """Show settings dialog"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Continuous Panorama Settings")
        settings_window.geometry("400x300")
        settings_window.configure(bg='#1c1c1e')
        settings_window.resizable(False, False)
        
        # Scene change threshold
        tk.Label(settings_window, text="Scene Change Threshold:", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=10)
        threshold_var = tk.DoubleVar(value=self.scene_change_threshold)
        threshold_scale = tk.Scale(settings_window, from_=10.0, to=80.0, resolution=5.0,
                                 variable=threshold_var, orient=tk.HORIZONTAL, 
                                 bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        threshold_scale.pack(fill=tk.X, padx=20)
        
        # Capture interval
        tk.Label(settings_window, text="Capture Interval (seconds):", 
                bg='#1c1c1e', fg='#ffffff', font=('SF Pro Display', 12)).pack(pady=10)
        interval_var = tk.DoubleVar(value=self.capture_interval)
        interval_scale = tk.Scale(settings_window, from_=0.5, to=5.0, resolution=0.5,
                                variable=interval_var, orient=tk.HORIZONTAL, 
                                bg='#2c2c2e', fg='#ffffff', font=('SF Pro Display', 10))
        interval_scale.pack(fill=tk.X, padx=20)
        
        # Apply button
        def apply_settings():
            self.scene_change_threshold = threshold_var.get()
            self.capture_interval = interval_var.get()
            settings_window.destroy()
            messagebox.showinfo("Settings", "Settings applied successfully!")
            
        tk.Button(settings_window, text="Apply Settings", command=apply_settings,
                 bg='#007AFF', fg='#ffffff', relief=tk.FLAT, 
                 font=('SF Pro Display', 14, 'bold'), height=2).pack(pady=30)
        
    def on_closing(self):
        """Handle window closing"""
        self.running = False
        self.auto_mode = False
        if self.cap:
            self.cap.release()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = ContinuousPanoramaGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Set minimum window size
    root.minsize(1200, 800)
    
    root.mainloop()

if __name__ == "__main__":
    main()

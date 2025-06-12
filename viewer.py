import cv2
import numpy as np
import argparse
import sys

class CylindricalViewer:
    def __init__(self, image_path):
        self.image = cv2.imread(image_path)
        if self.image is None:
            raise ValueError(f"Could not load image from {image_path}")
        
        self.height, self.width = self.image.shape[:2]
        
        # Viewer parameters
        self.view_width = 800
        self.view_height = 600
        self.fov = 90  # Field of view in degrees
        
        # Navigation parameters
        self.yaw = 0.0  # Horizontal rotation
        self.pitch = 0.0  # Vertical rotation
        self.max_pitch = 45.0  # Limit vertical rotation
        
        # Mouse control
        self.mouse_x = 0
        self.mouse_y = 0
        self.mouse_pressed = False
        self.sensitivity = 0.5
        
        # Create window
        cv2.namedWindow('Cylindrical Viewer', cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback('Cylindrical Viewer', self.mouse_callback)
        
        # Generate coordinate maps
        self.generate_maps()
    
    def mouse_callback(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.mouse_pressed = True
            self.mouse_x = x
            self.mouse_y = y
        elif event == cv2.EVENT_LBUTTONUP:
            self.mouse_pressed = False
        elif event == cv2.EVENT_MOUSEMOVE and self.mouse_pressed:
            dx = x - self.mouse_x
            dy = y - self.mouse_y
            
            # Update yaw and pitch based on mouse movement
            self.yaw += dx * self.sensitivity
            self.pitch -= dy * self.sensitivity
            
            # Wrap yaw around 360 degrees
            self.yaw = self.yaw % 360
            
            # Clamp pitch
            self.pitch = np.clip(self.pitch, -self.max_pitch, self.max_pitch)
            
            self.mouse_x = x
            self.mouse_y = y
            
            # Regenerate maps with new view angles
            self.generate_maps()
    
    def generate_maps(self):
        # Create coordinate grids for the output view
        u = np.arange(self.view_width, dtype=np.float32)
        v = np.arange(self.view_height, dtype=np.float32)
        u, v = np.meshgrid(u, v)
        
        # Convert to normalized coordinates (-1 to 1)
        u_norm = (u - self.view_width / 2) / (self.view_width / 2)
        v_norm = (v - self.view_height / 2) / (self.view_height / 2)
        
        # Convert FOV to radians
        fov_rad = np.radians(self.fov)
        
        # Calculate 3D coordinates on unit sphere
        # Perspective projection
        focal_length = 1.0 / np.tan(fov_rad / 2)
        
        x = u_norm / focal_length
        y = v_norm / focal_length
        z = np.ones_like(x)
        
        # Normalize to unit sphere
        norm = np.sqrt(x*x + y*y + z*z)
        x /= norm
        y /= norm
        z /= norm
        
        # Apply rotation based on yaw and pitch
        yaw_rad = np.radians(self.yaw)
        pitch_rad = np.radians(self.pitch)
        
        # Rotation matrices
        cos_yaw, sin_yaw = np.cos(yaw_rad), np.sin(yaw_rad)
        cos_pitch, sin_pitch = np.cos(pitch_rad), np.sin(pitch_rad)
        
        # Apply yaw rotation (around Y axis)
        x_rot = x * cos_yaw + z * sin_yaw
        z_rot = -x * sin_yaw + z * cos_yaw
        y_rot = y
        
        # Apply pitch rotation (around X axis)
        y_final = y_rot * cos_pitch - z_rot * sin_pitch
        z_final = y_rot * sin_pitch + z_rot * cos_pitch
        x_final = x_rot
        
        # Convert to cylindrical coordinates
        # For cylindrical projection, we map:
        # - azimuth (horizontal angle) to image width
        # - height (y coordinate) to image height
        
        azimuth = np.arctan2(x_final, z_final)
        elevation = np.arcsin(np.clip(y_final, -1, 1))
        
        # Convert to image coordinates
        # Map azimuth from [-π, π] to [0, width]
        src_x = ((azimuth + np.pi) / (2 * np.pi)) * self.width
        
        # Map elevation from [-π/2, π/2] to [0, height]
        # For cylindrical images, typically the full height represents a limited vertical range
        elevation_range = np.pi / 3  # Adjust this based on your image's vertical coverage
        src_y = ((elevation + elevation_range/2) / elevation_range) * self.height
        
        # Clamp coordinates to image bounds
        src_x = np.clip(src_x, 0, self.width - 1)
        src_y = np.clip(src_y, 0, self.height - 1)
        
        # Store maps for remapping
        self.map_x = src_x.astype(np.float32)
        self.map_y = src_y.astype(np.float32)
    
    def render_view(self):
        # Use remap to sample the cylindrical image
        view = cv2.remap(self.image, self.map_x, self.map_y, 
                        cv2.INTER_LINEAR, borderMode=cv2.BORDER_WRAP)
        return view
    
    def run(self):
        print("Cylindrical Image Viewer")
        print("Controls:")
        print("- Click and drag to look around")
        print("- Press 'q' or ESC to quit")
        print("- Press 'r' to reset view")
        print("- Press '+'/'-' to adjust FOV")
        
        while True:
            # Render the current view
            view = self.render_view()
            
            # Add UI overlay
            info_text = f"Yaw: {self.yaw:.1f} Pitch: {self.pitch:.1f} FOV: {self.fov}"
            cv2.putText(view, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (255, 255, 255), 2)
            cv2.putText(view, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 
                       0.7, (0, 0, 0), 1)
            
            cv2.imshow('Cylindrical Viewer', view)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:  # 'q' or ESC
                break
            elif key == ord('r'):  # Reset view
                self.yaw = 0.0
                self.pitch = 0.0
                self.generate_maps()
            elif key == ord('+') or key == ord('='):  # Increase FOV
                self.fov = min(self.fov + 5, 150)
                self.generate_maps()
            elif key == ord('-'):  # Decrease FOV
                self.fov = max(self.fov - 5, 30)
                self.generate_maps()
            elif key == 81:  # Left arrow
                self.yaw = (self.yaw - 5) % 360
                self.generate_maps()
            elif key == 83:  # Right arrow
                self.yaw = (self.yaw + 5) % 360
                self.generate_maps()
            elif key == 82:  # Up arrow
                self.pitch = np.clip(self.pitch + 5, -self.max_pitch, self.max_pitch)
                self.generate_maps()
            elif key == 84:  # Down arrow
                self.pitch = np.clip(self.pitch - 5, -self.max_pitch, self.max_pitch)
                self.generate_maps()

        cv2.destroyAllWindows()

def main():
    parser = argparse.ArgumentParser(description='Interactive Cylindrical Projection Viewer')
    parser.add_argument('image', help='Path to the cylindrical projection image')
    parser.add_argument('--width', type=int, default=800, help='Viewer width (default: 800)')
    parser.add_argument('--height', type=int, default=600, help='Viewer height (default: 600)')
    parser.add_argument('--fov', type=int, default=90, help='Initial field of view (default: 90)')
    
    args = parser.parse_args()
    
    try:
        viewer = CylindricalViewer(args.image)
        viewer.view_width = args.width
        viewer.view_height = args.height
        viewer.fov = args.fov
        viewer.generate_maps()  # Regenerate with new parameters
        viewer.run()
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExiting...")
        sys.exit(0)

if __name__ == "__main__":
    main()

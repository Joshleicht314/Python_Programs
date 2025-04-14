import sys
from PyQt5.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QPushButton, QFileDialog, QLineEdit, QHBoxLayout, QFormLayout, QGroupBox, QComboBox, QFrame, QMessageBox
from PyQt5.QtGui import QPixmap
from PyQt5.QtCore import Qt
from PIL import Image
import io
from PyQt5.QtGui import QFont


class BackgroundRemoverApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Background Remover")
        self.setGeometry(100, 100, 800, 600)

        # Initialize variables
        self.input_image_path = ""
        self.output_image = None  # To hold the image after background removal
        self.min_r, self.min_g, self.min_b = "", "", ""
        self.max_r, self.max_g, self.max_b = "", "", ""

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Open Image Section
        self.input_image_path_line = QLineEdit(self)
        self.input_image_path_line.setPlaceholderText("Choose an image (PNG, JPG, JPEG)")
        self.input_image_path_line.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 8px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        
        self.open_image_btn = QPushButton("Browse", self)
        self.open_image_btn.setStyleSheet("""
            QPushButton {
                padding: 5px;
                background-color: #4CAF50;
                color: white;
                border-radius: 8px;
                font-size: 20px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        self.open_image_btn.clicked.connect(self.open_image)

        open_image_layout = QHBoxLayout()
        open_image_layout.addWidget(self.input_image_path_line)
        open_image_layout.addWidget(self.open_image_btn)

        layout.addLayout(open_image_layout)
        
        # Preview Section (Side by Side)
        preview_layout = QHBoxLayout()

        # Original Image Preview
        self.original_preview_label = QLabel(self)
        self.original_preview_label.setAlignment(Qt.AlignCenter)
        self.original_preview_label.setStyleSheet("""
            border: 1px solid #4CAF50; 
            padding: 5px; 
            border-radius: 10px;
        """)
        preview_layout.addWidget(self.original_preview_label)

        # Processed Image Preview (after background removal)
        self.processed_preview_label = QLabel(self)
        self.processed_preview_label.setAlignment(Qt.AlignCenter)
        self.processed_preview_label.setStyleSheet("""
            border: 1px solid #4CAF50; 
            padding: 5px; 
            border-radius: 10px;
        """)
        preview_layout.addWidget(self.processed_preview_label)

        layout.addLayout(preview_layout)
        
        # RGB Input Section (Using QFormLayout for consistent alignment)
        self.rgb_groupbox = QGroupBox("RGB Thresholds", self)
        self.rgb_groupbox.setStyleSheet("""
            QGroupBox {
                padding: 5px;
                border-radius: 10px;
                font-size: 20px;
                border: 2px solid #4CAF50;
                color: #4CAF50;
            }
        """)
        
        rgb_layout = QFormLayout()

        # Preset Dropdown (White, Black, Custom)
        self.preset_combobox = QComboBox(self)
        self.preset_combobox.addItem("White")
        self.preset_combobox.addItem("Black")
        self.preset_combobox.addItem("Custom")
        self.preset_combobox.currentIndexChanged.connect(self.update_rgb_from_preset)
        rgb_layout.addRow("Preset:", self.preset_combobox)

        # Min RGB inputs
        self.min_r_input = QLineEdit(self)
        self.min_g_input = QLineEdit(self)
        self.min_b_input = QLineEdit(self)
        self.min_r_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        self.min_g_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        self.min_b_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        rgb_layout.addRow("Min R:", self.min_r_input)
        rgb_layout.addRow("Min G:", self.min_g_input)
        rgb_layout.addRow("Min B:", self.min_b_input)

        # Max RGB inputs
        self.max_r_input = QLineEdit(self)
        self.max_g_input = QLineEdit(self)
        self.max_b_input = QLineEdit(self)
        self.max_r_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        self.max_g_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
            }
        """)
        self.max_b_input.setStyleSheet("""
            QLineEdit {
                padding: 5px;
                border-radius: 5px;
                font-size: 20px;
                border: 1px solid #3b7a57;
                background-color: #e1f3e1;
                color: #006633;
                text-align: center;
            }
        """)
        rgb_layout.addRow("Max R:", self.max_r_input)
        rgb_layout.addRow("Max G:", self.max_g_input)
        rgb_layout.addRow("Max B:", self.max_b_input)

        self.rgb_groupbox.setLayout(rgb_layout)
        layout.addWidget(self.rgb_groupbox)

        # Remove Background Button
        self.remove_background_btn = QPushButton("Remove Background", self)
        self.remove_background_btn.setStyleSheet("""
            QPushButton {
                padding: 5px;
                background-color: #388E3C;
                color: white;
                border-radius: 8px;
                font-size: 20px;
                border: 1px solid #4CAF50;
            }
            QPushButton:hover {
                background-color: #2E7D32;
            }
        """)
        self.remove_background_btn.clicked.connect(self.remove_background)
        layout.addWidget(self.remove_background_btn)

        # Save Image Button
        self.save_image_btn = QPushButton("Save Image", self)
        self.save_image_btn.setStyleSheet("""
            QPushButton {
                padding: 10px;
                background-color: #81C784;
                color: white;
                border-radius: 8px;
                font-size: 20px;
                border: 1px solid #4CAF50;
            }
            QPushButton:hover {
                background-color: #66BB6A;
            }
        """)
        self.save_image_btn.clicked.connect(self.save_image)
        layout.addWidget(self.save_image_btn)

        # Set default preset to "White"
        self.preset_combobox.setCurrentIndex(0)  # 0 corresponds to "White"
        self.update_rgb_from_preset()  # Set RGB values for White preset

        self.setLayout(layout)

    def open_image(self):
        """Open the image and display it in the preview."""
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Image Files (*.png *.jpg *.jpeg)")
        if file_path:
            self.input_image_path = file_path
            self.input_image_path_line.setText(file_path)
            self.preview_image(file_path)

    def preview_image(self, image_path):
        """Load and display the selected image as a preview with resizing."""
        try:
            img = Image.open(image_path)
            img.thumbnail((250, 250))  # Maximum size for preview (250x250)
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.read())
            self.original_preview_label.setPixmap(pixmap)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load image preview: {e}")

    def update_rgb_from_preset(self):
        """Update the RGB values based on the selected preset."""
        selected_preset = self.preset_combobox.currentText()

        if selected_preset == "White":
            # Set RGB values for White (with range 240 to 255)
            self.min_r_input.setText("150")
            self.min_g_input.setText("150")
            self.min_b_input.setText("150")
            self.max_r_input.setText("256")
            self.max_g_input.setText("256")
            self.max_b_input.setText("256")
        elif selected_preset == "Black":
            # Set RGB values for Black (with range 0 to 30)
            self.min_r_input.setText("0")
            self.min_g_input.setText("0")
            self.min_b_input.setText("0")
            self.max_r_input.setText("50")
            self.max_g_input.setText("50")
            self.max_b_input.setText("50")
        elif selected_preset == "Custom":
            # Allow user to enter custom RGB values (no changes needed here)
            pass

    def remove_background(self):
        """Process the image, remove background, and update the preview."""
        if not self.input_image_path:
            QMessageBox.warning(self, "No image", "Please open an image first!")
            return

        try:
            # Convert RGB input to integer values
            min_rgb = (int(self.min_r_input.text()), int(self.min_g_input.text()), int(self.min_b_input.text()))
            max_rgb = (int(self.max_r_input.text()), int(self.max_g_input.text()), int(self.max_b_input.text()))
        except ValueError:
            QMessageBox.warning(self, "Invalid input", "Please enter valid RGB values.")
            return

        # Open the image and convert it to RGBA (to support transparency)
        image = Image.open(self.input_image_path).convert("RGBA")
        pixels = image.load()

        # Unpack the min and max RGB values
        min_r, min_g, min_b = min_rgb
        max_r, max_g, max_b = max_rgb

        # Get image dimensions
        width, height = image.size

        # Loop through each pixel and remove background if it matches the RGB range
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                if min_r <= r <= max_r and min_g <= g <= max_g and min_b <= b <= max_b:
                    pixels[x, y] = (255, 255, 255, 0)  # Make pixel transparent

        # Store the resulting image to update the preview
        self.output_image = image
        self.update_preview(image)

    def update_preview(self, image):
        """Update the preview with the image after background removal."""
        try:
            # Resize processed image to fit the preview area, maintaining the aspect ratio
            img_bytes = io.BytesIO()
            image.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            pixmap = QPixmap()
            pixmap.loadFromData(img_bytes.read())
            pixmap = pixmap.scaled(250, 250, Qt.KeepAspectRatio)
            self.processed_preview_label.setPixmap(pixmap)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update preview: {e}")

    def save_image(self):
        """Save the image after background removal."""
        if not self.output_image:
            QMessageBox.warning(self, "No background removed", "Please remove the background first!")
            return

        # Ask for save location and filename
        output_path, _ = QFileDialog.getSaveFileName(self, "Save Image", "", "PNG Files (*.png)")
        if output_path:
            try:
                self.output_image.save(output_path)
                QMessageBox.information(self, "Success", "Image saved successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"An error occurred while saving: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Arial", 20))  # Set global font size here (try 14 or 16 if you want it bigger)
    
    window = BackgroundRemoverApp()
    window.show()
    sys.exit(app.exec_())


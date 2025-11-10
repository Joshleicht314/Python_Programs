import sys
import PyPDF2
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog, QLabel, QHBoxLayout, QListWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class PDFCombinerApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('PDF Combiner')
        # Set the window size to 675px width and 460px height
        self.resize(675, 460)

        self.pdf_paths = []  # List to store selected PDF paths

        self.init_ui()

    def init_ui(self):
        # Set background color and window style
        self.setStyleSheet("background-color: #f4f4f4;")
        
        # Create widgets
        self.label = QLabel('Select PDFs to merge:', self)
        self.label.setStyleSheet("font-size: 20px; font-weight: bold; color: #333; margin-bottom: 10px;")
        
        # Create a list widget to display selected PDFs
        self.pdf_list_widget = QListWidget(self)
        self.pdf_list_widget.setStyleSheet("""
            background-color: #ffffff;
            border: 1px solid #ccc;
            padding: 5px;
            font-size: 20px;
            color: #333;
        """)
        
        # Create the "Add PDF" button
        self.add_pdf_btn = QPushButton('Add PDF', self)
        self.add_pdf_btn.setStyleSheet("""
            background-color: #4CAF50;
            color: white;
            font-size: 20px;
            padding: 10px;
            border: none;
            border-radius: 5px;
            margin-top: 10px;
        """)
        self.add_pdf_btn.clicked.connect(self.add_pdf)

        # Create the "Move Up" button
        self.move_up_btn = QPushButton('Move Up', self)
        self.move_up_btn.setStyleSheet("""
            background-color: #FF9800;
            color: white;
            font-size: 20px;
            padding: 10px;
            border: none;
            border-radius: 5px;
	    margin-top: 10px;
        """)
        self.move_up_btn.setEnabled(False)  # Initially disabled
        self.move_up_btn.clicked.connect(self.move_up)

        # Create the "Move Down" button
        self.move_down_btn = QPushButton('Move Down', self)
        self.move_down_btn.setStyleSheet("""
            background-color: #FF9800;
            color: white;
            font-size: 20px;
            padding: 10px;
            border: none;
            border-radius: 5px;
	    margin-top: 10px
        """)
        self.move_down_btn.setEnabled(False)  # Initially disabled
        self.move_down_btn.clicked.connect(self.move_down)

        # Create the "Merge and Save PDF" button
        self.save_btn = QPushButton('Merge and Save PDF', self)
        self.save_btn.setStyleSheet("""
            background-color: #2196F3;
            color: white;
            font-size: 20px;
            padding: 10px;
            border: none;
            border-radius: 5px;
            margin-top: 10px;
        """)
        self.save_btn.clicked.connect(self.merge_and_save_pdf)
        self.save_btn.setEnabled(False)  # Initially disable the button

        # Layouts
        layout = QVBoxLayout()
        
        # Add the label at the top
        layout.addWidget(self.label)
        
        # Add the list widget that will show the selected PDFs
        layout.addWidget(self.pdf_list_widget)
        
        # Add the buttons for adding PDFs and reordering them
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.add_pdf_btn)
        button_layout.addWidget(self.move_up_btn)
        button_layout.addWidget(self.move_down_btn)
        layout.addLayout(button_layout)
        
        # Add the "Merge and Save PDF" button
        layout.addWidget(self.save_btn)

        # Set layout to the window
        self.setLayout(layout)

    def add_pdf(self):
        # File dialog to select a PDF
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select PDF', '', 'PDF Files (*.pdf)')
        if file_path:
            self.pdf_paths.append(file_path)
            self.pdf_list_widget.addItem(file_path)  # Add the file path to the list widget
            self.check_ready_for_merge()

    def check_ready_for_merge(self):
        # Enable the save button if at least one PDF is added
        if len(self.pdf_paths) > 0:
            self.save_btn.setEnabled(True)
            self.move_up_btn.setEnabled(True)  # Enable move buttons
            self.move_down_btn.setEnabled(True)

    def move_up(self):
        # Get selected item index
        selected_index = self.pdf_list_widget.currentRow()
        
        if selected_index > 0:
            # Swap the selected item with the previous item in the list
            self.pdf_paths[selected_index], self.pdf_paths[selected_index - 1] = self.pdf_paths[selected_index - 1], self.pdf_paths[selected_index]
            self.update_pdf_list()

            # Select the item that was moved up
            self.pdf_list_widget.setCurrentRow(selected_index - 1)

    def move_down(self):
        # Get selected item index
        selected_index = self.pdf_list_widget.currentRow()
        
        if selected_index < len(self.pdf_paths) - 1:
            # Swap the selected item with the next item in the list
            self.pdf_paths[selected_index], self.pdf_paths[selected_index + 1] = self.pdf_paths[selected_index + 1], self.pdf_paths[selected_index]
            self.update_pdf_list()

            # Select the item that was moved down
            self.pdf_list_widget.setCurrentRow(selected_index + 1)

    def update_pdf_list(self):
        # Clear the list widget and update the order
        self.pdf_list_widget.clear()
        self.pdf_list_widget.addItems(self.pdf_paths)

    def merge_and_save_pdf(self):
        # Merge PDFs and save directly
        try:
            pdf_writer = PyPDF2.PdfWriter()

            # Loop through all selected PDFs
            for pdf_path in self.pdf_paths:
                with open(pdf_path, 'rb') as pdf_file:
                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                    for page_num in range(len(pdf_reader.pages)):
                        pdf_writer.add_page(pdf_reader.pages[page_num])

            # Open file dialog to choose where to save the combined PDF
            output_path, _ = QFileDialog.getSaveFileName(self, 'Save Combined PDF', '', 'PDF Files (*.pdf)')
            if output_path:
                # Save the merged PDF directly to the output path
                with open(output_path, 'wb') as output_pdf:
                    pdf_writer.write(output_pdf)

                self.label.setText(f'PDFs combined successfully! Saved to {output_path}')
            else:
                self.label.setText('Save operation canceled.')

        except Exception as e:
            self.label.setText(f'Error merging PDFs: {str(e)}')


if __name__ == '__main__':
    app = QApplication(sys.argv)

    # Set the application-wide font
    app.setFont(QFont("Arial", 20))

    window = PDFCombinerApp()
    window.show()
    sys.exit(app.exec_())

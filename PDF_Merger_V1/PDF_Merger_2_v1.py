import sys
import PyPDF2
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog, QLabel, QHBoxLayout, QLineEdit
from PyQt5.QtCore import Qt

class PDFCombinerApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle('PDF Combiner')
        # Set the window size to 675px width and 460px height
        self.resize(675, 375)

        self.pdf1_path = ''
        self.pdf2_path = ''

        self.init_ui()

    def init_ui(self):
        # Create widgets
        self.label = QLabel('Select two PDFs to merge:', self)
        self.label.setStyleSheet("font-size: 14px; margin-bottom: 10px;")

        self.pdf1_location = QLineEdit(self)
        self.pdf1_location.setPlaceholderText("Select First PDF")
        self.pdf1_location.setReadOnly(True)

        self.pdf1_browse_btn = QPushButton('Browse', self)
        self.pdf1_browse_btn.clicked.connect(self.select_pdf1)

        self.pdf2_location = QLineEdit(self)
        self.pdf2_location.setPlaceholderText("Select Second PDF")
        self.pdf2_location.setReadOnly(True)

        self.pdf2_browse_btn = QPushButton('Browse', self)
        self.pdf2_browse_btn.clicked.connect(self.select_pdf2)

        self.save_btn = QPushButton('Merge and Save PDF', self)
        self.save_btn.clicked.connect(self.merge_and_save_pdf)
        self.save_btn.setEnabled(False)

        # Layouts
        layout = QVBoxLayout()

        layout.addWidget(self.label)

        # First file location and button
        layout.addWidget(self.pdf1_location)
        layout.addWidget(self.pdf1_browse_btn)

        # Second file location and button
        layout.addWidget(self.pdf2_location)
        layout.addWidget(self.pdf2_browse_btn)

        layout.addWidget(self.save_btn)

        self.setLayout(layout)

    def select_pdf1(self):
        # File dialog to select the first PDF
        self.pdf1_path, _ = QFileDialog.getOpenFileName(self, 'Select First PDF', '', 'PDF Files (*.pdf)')
        if self.pdf1_path:
            self.pdf1_location.setText(self.pdf1_path)
            self.check_ready_for_merge()

    def select_pdf2(self):
        # File dialog to select the second PDF
        self.pdf2_path, _ = QFileDialog.getOpenFileName(self, 'Select Second PDF', '', 'PDF Files (*.pdf)')
        if self.pdf2_path:
            self.pdf2_location.setText(self.pdf2_path)
            self.check_ready_for_merge()

    def check_ready_for_merge(self):
        # Enable the save button if both PDFs are selected
        if self.pdf1_path and self.pdf2_path:
            self.save_btn.setEnabled(True)

    def merge_and_save_pdf(self):
        # Merge PDFs and save directly
        try:
            pdf_writer = PyPDF2.PdfWriter()

            # Add the pages from the first PDF
            with open(self.pdf1_path, 'rb') as pdf1_file:
                pdf_reader = PyPDF2.PdfReader(pdf1_file)
                for page_num in range(len(pdf_reader.pages)):
                    pdf_writer.add_page(pdf_reader.pages[page_num])

            # Add the pages from the second PDF
            with open(self.pdf2_path, 'rb') as pdf2_file:
                pdf_reader = PyPDF2.PdfReader(pdf2_file)
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
    window = PDFCombinerApp()
    window.show()
    sys.exit(app.exec_())

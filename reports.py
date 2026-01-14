from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget,
    QDialog, QLineEdit, QLabel, QFormLayout, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter, QHeaderView,
    QFrame, QStackedWidget, QDateEdit, QGridLayout, QRadioButton, QHBoxLayout,
    QComboBox, QTextBrowser
)
from PyQt6.QtGui import QAction, QTextDocument
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
import webbrowser # Added for opening in browser
import tempfile # Added for temporary file creation
import os # Added for path manipulation

from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal, QDate
from sqlalchemy import text, inspect
from sqlalchemy.orm import sessionmaker # Import text and inspect for migration

from db import (
    SessionLocal, engine, Base, get_machine_config,
    update_single_machine_config, insert_result_details,
    MachineConfig, ResultDetails, create_patient_for_result,
    get_patient_by_result_id, get_result_by_id,
    search_patients, get_patient_with_all_results, search_results,
    get_patient_by_patient_id, Patient, Doctor, # Added Doctor
    get_next_doctor_id, add_doctor, get_all_doctors, search_doctors, # Added Doctor functions
    get_doctors_by_type, update_result_verification, update_result_finalization, get_result_by_id_with_patient_and_doctor # Added Verification and Finalization functions
)


class ReportPreviewWindow(QDialog):


    def __init__(self, result_id, parent=None):


        super().__init__(parent)


        self.result_id = result_id


        self.setWindowTitle("Print Preview")





        # Set the window size and position based on the parent (main window)


        if parent and hasattr(parent, 'main_window') and parent.main_window:


            self.setGeometry(parent.main_window.geometry())


            self.move(parent.main_window.frameGeometry().topLeft())


        else:


            self.setGeometry(100, 100, 800, 700)





        self.layout = QVBoxLayout()


        self.setLayout(self.layout)





        self.db_session = SessionLocal()


        self.result = get_result_by_id_with_patient_and_doctor(self.db_session, self.result_id)


        


        if not self.result:


            QMessageBox.critical(self, "Error", "Result not found.")


            self.close()


            return





        self.report_viewer = QTextBrowser()


        self.report_viewer.setReadOnly(True)


        self.layout.addWidget(self.report_viewer)





        self.generate_report_html()

        self.print_button = QPushButton("Print Report")
        self.print_button.clicked.connect(self.print_report)
        self.layout.addWidget(self.print_button)

        self.open_browser_button = QPushButton("Open in Browser")
        self.open_browser_button.clicked.connect(self.open_in_browser)
        self.layout.addWidget(self.open_browser_button)

    def generate_report_html(self):
        patient = self.result.patient
        verified_by = self.result.verified_by_doctor
        finalized_by = self.result.finalized_by_doctor

        html_content = f"""
        <html>
        <head>
        <style>
            body {{
                font-family: Arial, Helvetica, sans-serif;
                font-size: 13px;
                margin: 25px;
                color: #000;
            }}

            /* MAIN TITLE */
            .report-title {{
                text-align: center;
                font-size: 26px;
                font-weight: bold;
                background-color: #d9ecff;
                padding: 10px;
                border: 1px solid #000;
                margin-bottom: 20px;
            }}

            /* SECTION HEADERS */
            .section-title {{
                font-size: 18px;
                font-weight: bold;
                background-color: #d9ecff;
                padding: 6px 10px;
                border: 1px solid #000;
                margin-top: 20px;
                margin-bottom: 10px;
            }}

            /* PATIENT INFO BOX */
            .box {{
                border: 1px solid #000;
                padding: 10px;
                margin-bottom: 15px;
                width: 100%;
            }}

            .patient-table {{
                width: 100%;
                border-collapse: collapse;
            }}

            .patient-table td {{
                width: 33%;
                padding: 5px;
            }}

            .label {{
                font-weight: bold;
            }}

            /* RESULT TABLE */
            .result-table-wrapper {{
                width: 100%;
                text-align: center;
            }}

            .result-table {{
                width: 100%;
                border-collapse: collapse;
                margin: 0 auto;
                table-layout: fixed;
            }}

            .result-table th {{
                background-color: #d9ecff;
                border: 1px solid #000;
                padding: 8px;
                text-align: center;
                font-weight: bold;
            }}

            .result-table td {{
                border: 1px solid #000;
                padding: 8px;
                text-align: center;
            }}

            /* INTERPRETATION */
            .interpretation {{
                border: 1px solid #000;
                padding: 10px;
                width: 100%;
            }}
        </style>
        </head>

        <body>

            <div class="report-title">
                Hemoglobin Electrophoresis Report
            </div>

            <div class="box">
                <table class="patient-table">
                    <tr>
                        <td><span class="label">Patient ID:</span> {patient.patient_id if patient else 'N/A'}</td>
                        <td><span class="label">Name:</span> {patient.name if patient else 'N/A'}</td>
                        <td><span class="label">Gender:</span> {patient.gender if patient else 'N/A'}</td>
                    </tr>
                    <tr>
                        <td><span class="label">Age:</span> {patient.age if patient else 'N/A'}</td>
                        <td><span class="label">Phone:</span> {patient.phone_number if patient else 'N/A'}</td>
                        <td><span class="label">Sample ID:</span> {self.result.sample_id}</td>
                    </tr>
                </table>
            </div>

            <div class="section-title">Test Result</div>

            <div class="result-table-wrapper">
                <table class="result-table">
                    <thead>
                        <tr>
                            <th>Test Name</th>
                            <th>Result</th>
                            <th>Unit</th>
                            <th>Reference Range</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td>{self.result.test_name}</td>
                            <td><strong>{self.result.test_result}</strong></td>
                            <td>{self.result.unit}</td>
                            <td>{self.result.reference_range}</td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <div class="section-title">Method</div>
            <p>
                Hemoglobin fractions were analyzed by electrophoresis using
                an automated HbA1c analyzer.
            </p>

            <div class="section-title">Interpretation</div>
            <div class="interpretation">
                HbA1c reflects the average blood glucose level over the previous
                2–3 months and is used for diagnosis and monitoring of diabetes mellitus.
            </div>

            <!-- FOOTER : LEFT = VERIFIED , RIGHT = FINALIZED -->
            <table style="width:100%; margin-top:90px; border-collapse:collapse;">
                <tr>
                    <td style="width:50%; text-align:left; vertical-align:top;">
                        <div style="width:70%; border-top:1px solid #000; margin-top:40px;"></div>
                        <p><strong>Verified By</strong></p>
                        <p>{verified_by.name if verified_by else 'N/A'}</p>
                        <p>{verified_by.doctor_id if verified_by else ''}</p>
                    </td>

                    <td style="width:50%; text-align:right; vertical-align:top;">
                        <div style="width:70%; border-top:1px solid #000; margin-top:40px; margin-left:auto;"></div>
                        <p><strong>Finalized By</strong></p>
                        <p>{finalized_by.name if finalized_by else 'N/A'}</p>
                        <p>{finalized_by.doctor_id if finalized_by else ''}</p>
                    </td>
                </tr>
            </table>

        </body>
        </html>
        """

        self.report_viewer.setHtml(html_content)



    def open_in_browser(self):
        import webbrowser
        import tempfile
        import os

        # Get the HTML content
        html_content = self.report_viewer.toHtml()

        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(html_content)
            temp_path = tmp_file.name

        # Open the file in the default web browser
        webbrowser.open_new_tab(f"file:///{temp_path}")

        # Note: The temporary file will be deleted when the app closes or the Python process ends,
        # unless deleted=False is used and then explicitly deleted later.
        # For simplicity here, we rely on the OS or user to clean temp files, or delete it later.
        # For a robust solution, consider a more managed temp file lifecycle.

    def print_report(self):


        printer = QPrinter(QPrinter.PrinterMode.HighResolution)


        print_dialog = QPrintDialog(printer, self)


        if print_dialog.exec() == QPrintDialog.DialogCode.Accepted:


            self.report_viewer.print(printer)





    def closeEvent(self, event):


        self.db_session.close()


        super().closeEvent(event)








class ReportsViewWidget(QWidget):


    def __init__(self, main_window=None):


        super().__init__()


        self.main_window = main_window


        self.layout = QVBoxLayout(self)





        # Search Frame (similar to other views)


        search_frame = QFrame()


        search_frame.setFrameShape(QFrame.Shape.StyledPanel)


        search_grid_layout = QGridLayout(search_frame)


        


        self.sample_id_search_input = QLineEdit()


        self.patient_id_search_input = QLineEdit()


        self.patient_name_search_input = QLineEdit()


        self.test_name_search_input = QLineEdit()


        self.from_date_input = QDateEdit(self)


        self.from_date_input.setCalendarPopup(True)


        self.from_date_input.setDate(QDate.currentDate().addDays(-30))


        self.to_date_input = QDateEdit(self)


        self.to_date_input.setCalendarPopup(True)


        self.to_date_input.setDate(QDate.currentDate())


        


        search_button = QPushButton("Search")


        search_button.clicked.connect(self.perform_search)


        


        search_grid_layout.addWidget(QLabel("Sample ID:"), 0, 0)


        search_grid_layout.addWidget(self.sample_id_search_input, 0, 1)


        search_grid_layout.addWidget(QLabel("Patient ID:"), 0, 2)


        search_grid_layout.addWidget(self.patient_id_search_input, 0, 3)





        search_grid_layout.addWidget(QLabel("Patient Name:"), 1, 0)


        search_grid_layout.addWidget(self.patient_name_search_input, 1, 1)


        search_grid_layout.addWidget(QLabel("Test Name:"), 1, 2)


        search_grid_layout.addWidget(self.test_name_search_input, 1, 3)





        search_grid_layout.addWidget(QLabel("From Date:"), 2, 0)


        search_grid_layout.addWidget(self.from_date_input, 2, 1)


        search_grid_layout.addWidget(QLabel("To Date:"), 2, 2)


        search_grid_layout.addWidget(self.to_date_input, 2, 3)





        search_grid_layout.addWidget(search_button, 3, 3) # Placed on the last row


        


        self.layout.addWidget(search_frame)





        # Results Table


        self.results_table = QTreeWidget()


        self.results_table.setHeaderLabels(["Sample ID", "Patient ID", "Patient Name", "Test Name", "Value", "Unit", "Reference Range", "DateTime", "Status", "Verified By", "Finalized By", "Result ID"]) # Same headers as Finalization


        self.results_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)


        self.results_table.setColumnHidden(11, True) # Hide result ID


        self.results_table.itemClicked.connect(self.open_report_preview_window) # Connect click to open report preview


        


        self.layout.addWidget(self.results_table)


        self.perform_search() # Load initial data





    def perform_search(self):


        sample_id = self.sample_id_search_input.text()


        patient_id = self.patient_id_search_input.text()


        patient_name = self.patient_name_search_input.text()


        test_name = self.test_name_search_input.text()


        from_date = self.from_date_input.date().toPyDate()


        to_date = self.to_date_input.date().toPyDate()





        db = SessionLocal()


        try:


            results = search_results(db, 


                                     sample_id=sample_id, 


                                     patient_id=patient_id, 


                                     patient_name=patient_name, 


                                     test_name=test_name, 


                                     from_date=from_date, 


                                     to_date=to_date,


                                     status="Finalized") # Implicitly filter by Finalized


            self.results_table.clear()


            for result in results:


                patient = result.patient


                verified_by = result.verified_by_doctor.name if result.verified_by_doctor else "N/A"


                finalized_by = result.finalized_by_doctor.name if result.finalized_by_doctor else "N/A"


                date_time_str = QDateTime(result.date_time).toString('yyyy-MM-dd hh:mm:ss')


                item = QTreeWidgetItem([


                    result.sample_id,


                    patient.patient_id if patient else "",


                    patient.name if patient else "",


                    result.test_name,


                    result.test_result,


                    result.unit,


                    result.reference_range,


                    date_time_str,


                    result.status,


                    verified_by,


                    finalized_by,


                    str(result.id) # Store result ID in hidden column


                ])


                self.results_table.addTopLevelItem(item)


        finally:


            db.close()





    def open_report_preview_window(self, item):


        result_id = int(item.text(11)) # Get ID from hidden column (index 11)


        preview_window = ReportPreviewWindow(result_id, self)


        preview_window.exec()




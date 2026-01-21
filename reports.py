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

        # Window size and position
        if parent and hasattr(parent, 'main_window') and parent.main_window:
            self.setGeometry(parent.main_window.geometry())
            self.move(parent.main_window.frameGeometry().topLeft())
        else:
            self.setGeometry(100, 100, 800, 700)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.db_session = SessionLocal()
        self.result = get_result_by_id_with_patient_and_doctor(self.db_session, self.result_id)
        
        # Fetch all results for the same sample_id to show peaks/fractions
        self.all_results = []
        if self.result:
            self.all_results = self.db_session.query(ResultDetails)\
                .filter(ResultDetails.sample_id == self.result.sample_id)\
                .order_by(ResultDetails.id).all()

        if not self.result:
            QMessageBox.critical(self, "Error", "Result not found.")
            self.close()
            return

        self.report_viewer = QTextBrowser()
        self.report_viewer.setReadOnly(True)
        self.layout.addWidget(self.report_viewer)

        self.current_html = ""
        self.generate_report_html()

        # Button
        self.open_browser_button = QPushButton("Open in Browser")
        self.open_browser_button.clicked.connect(self.open_in_browser)
        self.layout.addWidget(self.open_browser_button)

    def generate_report_html(self):
        patient = self.result.patient
        verified_by = self.result.verified_by_doctor
        finalized_by = self.result.finalized_by_doctor

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Biochemistry Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            color: #000;
            font-size: 11px;
        }}
        .report-container {{
            width: 800px;
            margin: 0 auto;
        }}
        .header-section {{
            border: 2px solid #000;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 15px;
            text-align: center;
        }}
        .title {{
            font-size: 20px;
            font-weight: bold;
            margin-bottom: 20px;
        }}
        .patient-info-table {{
            width: 100%;
            border: 1px solid #000;
            border-collapse: collapse;
            margin: 10px auto;
        }}
        .patient-info-table td {{
            padding: 8px;
            vertical-align: top;
            text-align: left;
        }}
        .label {{
            font-weight: bold;
        }}
        .value {{
            border-bottom: 1px solid #000;
        }}
        .hplc-note {{
            text-align: center;
            color: #0000CD;
            font-size: 10px;
            margin-top: 15px;
        }}
        .hb-conc {{
            font-size: 14px;
            font-weight: bold;
            margin: 20px 0;
            padding-left: 10px;
        }}
        .results-table {{
            width: 95%;
            border-collapse: collapse;
            margin: 20px auto;
        }}
        .results-table th {{
            border: 1px solid #000;
            padding: 10px;
            text-align: left;
            background-color: #f2f2f2;
            font-weight: bold;
        }}
        .results-table td {{
            border: 1px solid #000;
            padding: 8px;
            text-align: left;
        }}
        .comments-section, .advice-section {{
            margin: 20px 10px;
            font-size: 13px;
        }}
        .section-title {{
            font-weight: bold;
            font-size: 15px;
        }}
        .footer-table {{
            width: 100%;
            margin-top: 50px;
            border-collapse: collapse;
        }}
        .footer-table td {{
            width: 50%;
            vertical-align: top;
            padding: 10px;
        }}
        .signature-line-box {{
            border-top: 1px solid #000;
            padding-top: 5px;
            width: 180px;
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header-section">
            <div class="title">BIOCHEMISTRY REPORT</div>
            
            <table class="patient-info-table">
                <tr>
                    <td width="35%">
                        <div><span class="label">ID No :</span> <span class="value">{patient.patient_id if patient else 'N/A'}</span></div>
                        <div style="margin-top:5px;"><span class="label">Name :</span> <span class="value">{patient.name if patient else 'N/A'}</span></div>
                        <div style="margin-top:5px;"><span class="label">Ref By :</span> <span class="value">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span></div>
                    </td>
                    <td width="35%">
                        <div><span class="label">Bill On:</span> <span class="value">{self.result.date_time.strftime('%d/%m/%y %I:%M %p') if self.result.date_time else ''}</span></div>
                        <div style="margin-top:5px;"><span class="label">Print on:</span> <span class="value">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span></div>
                        <div style="margin-top:5px;"><span class="label">Admission:</span> <span class="value">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span></div>
                    </td>
                    <td width="30%">
                        <div><span class="label">Age/Sex:</span> <span class="value">{patient.age if patient else 'N/A'} / {patient.gender if patient else 'N/A'}</span></div>
                        <div style="margin-top:5px;"><span class="label">Specimen:</span> <span class="value">Blood</span></div>
                        <div style="margin-top:5px;"><span class="label">Admission:</span> <span class="value">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</span></div>
                    </td>
                </tr>
            </table>

            <div class="hplc-note">
                Estimations are carried out by fully automated System
            </div>
        </div>

        <div class="hb-conc">
            Result: {self.result.test_result} {self.result.unit if self.result.unit else ''}
        </div>

        <table class="results-table">
            <thead>
                <tr>
                    <th width="40%">Test Name</th>
                    <th width="20%">Result</th>
                    <th width="40%">Ref. Values</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>{self.result.test_name}</td>
                    <td>{self.result.test_result} {self.result.unit if self.result.unit else ''}</td>
                    <td>{self.result.reference_range}</td>
                </tr>
            </tbody>
        </table>

        <div class="comments-section">
            <span class="section-title">Comments :</span> Consistent with patterns.
        </div>

        <div class="advice-section">
            <span class="section-title">Advice :</span> Clinically correlate with other findings.
        </div>

        <table class="footer-table">
            <tr>
                <td align="center">
                    <div style="height: 40px;"></div>
                    <div class="signature-line-box" style="margin: 0 auto; text-align: center;">
                        <div><strong>{verified_by.name if verified_by else 'N/A'}</strong></div>
                        <div style="font-size: 10px;">{verified_by.designation if verified_by and verified_by.designation else ''}</div>
                        <div><strong>Verified By</strong></div>
                    </div>
                </td>
                <td align="right">
                    <div style="height: 40px;"></div>
                    <div class="signature-line-box" style="text-align: center; margin-left: auto;">
                        <div><strong>{finalized_by.name if finalized_by else 'N/A'}</strong></div>
                        <div style="font-size: 10px;">{finalized_by.designation if finalized_by and finalized_by.designation else ''}</div>
                        <div><strong>Finalized By</strong></div>
                    </div>
                </td>
            </tr>
        </table>
    </div>
</body>
</html>
"""

        self.current_html = html_content
        self.report_viewer.setHtml(html_content)

    def open_in_browser(self):
        if not self.current_html:
            return
        with tempfile.NamedTemporaryFile(delete=False, suffix=".html", mode="w", encoding="utf-8") as tmp_file:
            tmp_file.write(self.current_html)
            temp_path = tmp_file.name
        webbrowser.open_new_tab(f"file:///{temp_path}")

    def closeEvent(self, event):
        self.db_session.close()
        super().closeEvent(event)



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




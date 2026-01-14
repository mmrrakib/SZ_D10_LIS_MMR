import sys
import socket
import threading
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget,
    QDialog, QLineEdit, QLabel, QFormLayout, QMessageBox,
    QTreeWidget, QTreeWidgetItem, QTextEdit, QSplitter, QHeaderView,
    QFrame, QStackedWidget, QDateEdit, QGridLayout, QRadioButton, QHBoxLayout,
    QComboBox, QTextBrowser, QStyle
)
from PyQt6.QtGui import QAction, QTextDocument, QIcon, QFont
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtCore import Qt, QDateTime, QThread, pyqtSignal, QDate
from sqlalchemy import text, inspect
from sqlalchemy.orm import sessionmaker # Import text and inspect for migration

from astm_parser import parse_astm
from reports import ReportPreviewWindow, ReportsViewWidget
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

STYLE_SHEET = """
    QMainWindow {
        background-color: #f0f0f0; /* Light grey for main window */
    }
    QLabel {
        color: #00008B; /* Dark Blue */
        border: none; /* Ensure no border for general labels */
    }
    QLabel#header {
        color: black; /* Changed to black */
        font-size: 16px; 
        font-weight: bold;
        border: none; /* Ensure no border for header labels */
    }
    QFrame {
        background-color: #F8F8F8; /* Very light grey for frames */
        border: none; /* SteelBlue Border */
        border-radius: 5px;
    }
    QFrame#header_frame {
        background-color: transparent; /* No background for header frames */
        border: none; /* No border for header frames */
    }
    QTreeWidget {
        border: 1px solid #4682B4; /* SteelBlue Border */
        border-radius: 5px;
    }
    QMenuBar {
        background-color: #f0f0f0;
        color: black; /* Set menu bar text to black */
    }
    QMenu {
        background-color: #f0f0f0;
        color: black; /* Set menu text to black */
    }
    QPushButton {
        background-color: #ADD8E6;
        color: #00008B;
        border: 1px solid #00008B;
        padding: 5px;
        border-radius: 3px;
    }
    QPushButton:hover {
        background-color: #00008B;
        color: #ADD8E6;
    }
    QPushButton#start_stop_button {
        min-width: 80px; /* Make it a bit shorter */
        min-height: 25px; /* Make it a bit shorter */
        background-color: #4CAF50; /* Green */
        color: white; /* Ensure text is visible */
        font-weight: bold; /* Keep text bolder */
    }
    QLineEdit, QDateEdit, QComboBox {
        border: 1px solid #00008B;
        padding: 2px;
        border-radius: 3px;
    }
"""


# --- Database Migration Function ---
def perform_finalization_migration(engine, base):
    """
    Performs a migration to add the finalized_by_doctor_id and status columns to the result_details table
    if they do not already exist.
    """
    inspector = inspect(engine)
    if inspector.has_table("result_details"):
        columns = [col['name'] for col in inspector.get_columns('result_details')]
        if "finalized_by_doctor_id" not in columns:
            print("Database migration: 'finalized_by_doctor_id' column missing from 'result_details'. Initiating migration...")
            with engine.connect() as connection:
                connection.execute(text("ALTER TABLE result_details ADD COLUMN finalized_by_doctor_id INTEGER"))
                connection.commit()
            print("Database migration for result_details (finalized_by_doctor_id) completed successfully.")
        else:
            print("Database migration: 'finalized_by_doctor_id' column already exists in 'result_details'. No migration needed.")

        if "status" not in columns:
            print("Database migration: 'status' column missing from 'result_details'. Initiating migration...")
            with engine.connect() as connection:
                connection.execute(text("ALTER TABLE result_details ADD COLUMN status VARCHAR DEFAULT 'Pending'"))
                connection.commit()
            print("Database migration for result_details (status) completed successfully.")
        else:
            print("Database migration: 'status' column already exists in 'result_details'. No migration needed.")

def perform_verification_migration(engine, base):
    """
    Performs a migration to add the verified_by_doctor_id column to the result_details table
    if it does not already exist.
    """
    inspector = inspect(engine)
    if inspector.has_table("result_details"):
        columns = [col['name'] for col in inspector.get_columns('result_details')]
        if "verified_by_doctor_id" not in columns:
            print("Database migration: 'verified_by_doctor_id' column missing from 'result_details'. Initiating migration...")
            with engine.connect() as connection:
                connection.execute(text("ALTER TABLE result_details ADD COLUMN verified_by_doctor_id INTEGER"))
                # You might need to add a foreign key constraint separately depending on SQLite version
                # For SQLite, it's often easier to recreate table or manage in application logic
                connection.commit()
            print("Database migration for result_details (verified_by_doctor_id) table completed successfully.")
        else:
            print("Database migration: 'verified_by_doctor_id' column already exists in 'result_details'. No migration needed.")

def perform_result_details_migration(engine, base):
    """
    Performs a migration to add the patient_id column to the result_details table
    if it does not already exist, preserving existing data.
    """
    inspector = inspect(engine)

    # 1. Check if 'result_details' table exists and if 'patient_id' column exists
    needs_migration = False
    if inspector.has_table("result_details"):
        columns = [col['name'] for col in inspector.get_columns('result_details')]
        if "patient_id" not in columns:
            needs_migration = True
    else:
        # If the table doesn't exist, Base.metadata.create_all will create it correctly.
        print("Database: 'result_details' table does not exist. Creating fresh schema.")
        base.metadata.create_all(engine)
        return

    if not needs_migration:
        print("Database migration: 'result_details' table already has 'patient_id' column. No migration needed.")
        return

    print("Database migration: 'patient_id' column missing from 'result_details'. Initiating migration...")
    
    # Create a session specific for migration to control transactions
    MigrationSession = sessionmaker(bind=engine)
    with MigrationSession() as session:
        try:
            # Step 1: Rename the old result_details table
            session.execute(text("ALTER TABLE result_details RENAME TO old_result_details;"))
            print("Renamed 'result_details' to 'old_result_details'.")

            # NEW STEP: Drop the index from the old table before creating new one
            session.execute(text("DROP INDEX IF EXISTS ix_result_details_sample_id;"))
            print("Dropped index 'ix_result_details_sample_id' from the old table.")

            # Step 2: Create the new 'result_details' and 'patients' tables
            # Since 'result_details' was renamed, Base.metadata.create_all will now create it with the new schema.
            # It will also create 'patients' table if it doesn't exist.
            # We call this within the transaction to ensure atomicity.
            base.metadata.create_all(engine)
            print("Created new 'result_details' and 'patients' tables with updated schema.")

            # Step 3: Copy data from 'old_result_details' to the new 'result_details'
            # Only copy columns that existed in the old schema. patient_id will be NULL by default.
            session.execute(text("""
                INSERT INTO result_details (id, sample_id, test_name, test_result, unit, reference_range, date_time)
                SELECT id, sample_id, test_name, test_result, unit, reference_range, date_time
                FROM old_result_details;
            """))
            print("Copied data from 'old_result_details' to 'result_details'.")

            # Step 4: Drop the 'old_result_details' table
            session.execute(text("DROP TABLE old_result_details;"))
            print("Dropped 'old_result_details' table.")

            session.commit() # Commit the transaction
            print("Database migration completed successfully.")

        except Exception as e:
            session.rollback() # Rollback on error
            print(f"Error during database migration: {e}")
            raise # Re-raise to prevent application from starting with corrupted state

def perform_patient_migration(engine, base):
    """
    Performs a migration to add the patient_id column to the patients table
    if it does not already exist.
    """
    inspector = inspect(engine)
    if inspector.has_table("patients"):
        columns = [col['name'] for col in inspector.get_columns('patients')]
        if "patient_id" not in columns:
            print("Database migration: 'patient_id' column missing from 'patients'. Initiating migration...")
            with engine.connect() as connection:
                connection.execute(text("ALTER TABLE patients ADD COLUMN patient_id VARCHAR"))
                connection.commit()
            print("Database migration for patients table completed successfully.")

# --- End Database Migration Function ---

class ResultDetailsWindow(QDialog):
    patient_info_saved = pyqtSignal() # New signal

    def __init__(self, result_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Result and Patient Details")
        self.result_id = result_id
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.db_session = SessionLocal()
        
        self.result = get_result_by_id(self.db_session, self.result_id)
        if not self.result:
            QMessageBox.critical(self, "Error", "Result not found.")
            self.close()
            return

        # --- Result Details ---
        result_frame = QFrame()
        result_frame.setFrameShape(QFrame.Shape.StyledPanel)
        result_layout = QFormLayout(result_frame)
        result_header = QLabel("Result Details")
        result_header.setObjectName("header")
        self.layout.addWidget(result_header)
        self.layout.addWidget(result_frame)

        result_layout.addRow("Sample ID:", QLabel(self.result.sample_id))
        result_layout.addRow("Test Name:", QLabel(self.result.test_name))
        result_layout.addRow("Test Result:", QLabel(self.result.test_result))
        result_layout.addRow("Unit:", QLabel(self.result.unit))
        result_layout.addRow("Reference Range:", QLabel(self.result.reference_range))
        result_layout.addRow("Date/Time:", QLabel(self.result.date_time.strftime('%Y-%m-%d %H:%M:%S')))

        # --- Patient Details ---
        self.patient_frame = QFrame()
        self.patient_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.patient_layout = QFormLayout(self.patient_frame)
        patient_header = QLabel("Patient Details")
        patient_header.setObjectName("header")
        self.layout.addWidget(patient_header)
        self.layout.addWidget(self.patient_frame)

        self.patient_name_input = QLineEdit()
        self.patient_age_input = QLineEdit()
        self.patient_gender_input = QLineEdit()
        self.patient_phone_input = QLineEdit()
        self.patient_id_label = QLabel("") # To display existing patient ID

        self.patient_layout.addRow("Patient Name:", self.patient_name_input)
        self.patient_layout.addRow("Age:", self.patient_age_input)
        self.patient_layout.addRow("Gender:", self.patient_gender_input)
        self.patient_layout.addRow("Phone Number:", self.patient_phone_input)
        self.patient_layout.addRow("Patient ID:", self.patient_id_label) # Display, not editable

        self.save_patient_button = QPushButton("Save Patient Info")
        self.save_patient_button.clicked.connect(self.save_patient_info)
        self.layout.addWidget(self.save_patient_button)
        self.layout.addStretch(1) # Add stretch to push content up
        self.adjustSize() # Adjust dialog size to fit contents
        self.setMinimumSize(self.size()) # Set minimum size to current size
        
        self.load_patient_data()

    def load_patient_data(self):
        if self.result.patient:
            patient = self.result.patient
            self.patient_name_input.setText(patient.name)
            self.patient_age_input.setText(patient.age)
            self.patient_gender_input.setText(patient.gender)
            self.patient_phone_input.setText(patient.phone_number)
            self.patient_id_label.setText(patient.patient_id)
        else:
            self.patient_id_label.setText("N/A (New Patient)")
            
    def save_patient_info(self):
        name = self.patient_name_input.text()
        age = self.patient_age_input.text()
        gender = self.patient_gender_input.text()
        phone = self.patient_phone_input.text()

        try:
            # create_patient_for_result function handles both creating new and updating existing patient
            create_patient_for_result(self.db_session, self.result.id, name, age, gender, phone)
            self.db_session.commit()
            # Refresh the result object to get the updated patient relationship
            self.db_session.refresh(self.result)
            QMessageBox.information(self, "Success", "Patient information saved successfully!")
            self.patient_info_saved.emit() # Emit signal
            self.accept() # Close the dialog
        except Exception as e:
            self.db_session.rollback()
            QMessageBox.critical(self, "Error", f"Failed to save patient information: {e}")

    def closeEvent(self, event):
        self.db_session.close()
        super().closeEvent(event)

class PatientDetailsWindow(QDialog):
    def __init__(self, result_id):
        super().__init__()
        self.setWindowTitle("Patient Details")
        self.setGeometry(400, 200, 400, 450)
        self.result_id = result_id

        self.layout = QVBoxLayout()

        # Test Details Section
        self.test_details_frame = QFrame()
        self.test_details_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.test_details_layout = QFormLayout()

        self.sample_id_label = QLabel()
        self.test_name_label = QLabel()
        self.result_label = QLabel()
        self.unit_label = QLabel()
        self.ref_range_label = QLabel()

        self.test_details_layout.addRow("Sample ID:", self.sample_id_label)
        self.test_details_layout.addRow("Test Name:", self.test_name_label)
        self.test_details_layout.addRow("Result:", self.result_label)
        self.test_details_layout.addRow("Unit:", self.unit_label)
        self.test_details_layout.addRow("Reference Range:", self.ref_range_label)
        
        
        self.test_details_frame.setLayout(self.test_details_layout)
        self.layout.addWidget(self.test_details_frame)

        # Patient Information Section
        self.patient_info_frame = QFrame()
        self.patient_info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.patient_info_layout = QFormLayout()

        self.patient_name_input = QLineEdit()
        self.age_input = QLineEdit()
        self.gender_input = QLineEdit()
        self.phone_input = QLineEdit()

        self.patient_info_layout.addRow("Patient's Name:", self.patient_name_input)
        self.patient_info_layout.addRow("Age:", self.age_input)
        self.patient_info_layout.addRow("Gender:", self.gender_input)
        self.patient_info_layout.addRow("Phone Number:", self.phone_input)

        self.patient_info_frame.setLayout(self.patient_info_layout)
        self.layout.addWidget(self.patient_info_frame)

        self.save_button = QPushButton("Save Patient Info")
        self.save_button.clicked.connect(self.save_patient_data)
        self.layout.addWidget(self.save_button)

        self.status_label = QLabel("")
        self.layout.addWidget(self.status_label)

        self.setLayout(self.layout)

        self.load_data()

    def load_data(self):
        db = SessionLocal()
        try:
            result = get_result_by_id(db, self.result_id)
            if result:
                self.sample_id_label.setText(result.sample_id)
                self.test_name_label.setText(result.test_name)
                self.result_label.setText(result.test_result)
                self.unit_label.setText(result.unit)
                self.ref_range_label.setText(result.reference_range)

                if result.patient:
                    self.patient_name_input.setText(result.patient.name)
                    self.age_input.setText(result.patient.age)
                    self.gender_input.setText(result.patient.gender)
                    self.phone_input.setText(result.patient.phone_number)
            else:
                self.status_label.setText("Could not load result details.")
        finally:
            db.close()

    def save_patient_data(self):
        name = self.patient_name_input.text()
        age = self.age_input.text()
        gender = self.gender_input.text()
        phone = self.phone_input.text()

        db = SessionLocal()
        try:
            create_patient_for_result(db, self.result_id, name, age, gender, phone)
            self.status_label.setText("Patient information saved successfully!")
            QMessageBox.information(self, "Success", "Patient information saved.")
            self.accept()
        except Exception as e:
            self.status_label.setText(f"Error saving patient info: {e}")
            QMessageBox.critical(self, "Error", f"Could not save patient information: {e}")
        finally:
            db.close()

class PatientsViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Search Frame
        search_frame = QFrame()
        search_frame.setFrameShape(QFrame.Shape.StyledPanel)
        search_layout = QFormLayout(search_frame)
        
        self.name_search_input = QLineEdit()
        self.phone_search_input = QLineEdit()
        self.sample_id_search_input = QLineEdit()
        self.patient_id_search_input = QLineEdit()
        search_button = QPushButton("Search")
        search_button.clicked.connect(self.perform_search)
        
        search_layout.addRow("Name:", self.name_search_input)
        search_layout.addRow("Phone Number:", self.phone_search_input)
        search_layout.addRow("Sample ID:", self.sample_id_search_input)
        search_layout.addRow("Patient ID:", self.patient_id_search_input)
        search_layout.addRow(search_button)
        
        self.layout.addWidget(search_frame)

        # Splitter for results and details
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Results Table
        self.results_table = QTreeWidget()
        self.results_table.setHeaderLabels(["Patient Name", "Phone Number", "Patient ID"])
        self.results_table.itemClicked.connect(self.display_patient_details)
        splitter.addWidget(self.results_table)

        # Details Frame
        self.details_frame = QFrame()
        self.details_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.details_frame_layout = QVBoxLayout(self.details_frame)
        splitter.addWidget(self.details_frame)
        self.details_content_widget = None # To hold the content
        
        self.layout.addWidget(splitter)

    def perform_search(self):
        name = self.name_search_input.text()
        phone = self.phone_search_input.text()
        sample_id = self.sample_id_search_input.text()
        patient_id = self.patient_id_search_input.text()

        db = SessionLocal()
        try:
            patients = search_patients(db, name=name, phone_number=phone, sample_id=sample_id, patient_id=patient_id)
            self.results_table.clear()
            for patient in patients:
                item = QTreeWidgetItem([patient.name, patient.phone_number, patient.patient_id])
                self.results_table.addTopLevelItem(item)
        finally:
            db.close()

    def display_patient_details(self, item):
        patient_id_str = item.text(2)

        db = SessionLocal()
        try:
            patient = get_patient_by_patient_id(db, patient_id_str)
            if not patient:
                return

            # Clear previous details by deleting the old content widget
            if self.details_content_widget:
                self.details_content_widget.setParent(None)
                self.details_content_widget = None # Clear reference

            # Create a new container widget for the details
            self.details_content_widget = QWidget()
            details_layout = QVBoxLayout(self.details_content_widget)

            # Patient Info
            info_layout = QFormLayout()
            info_layout.addRow("Name:", QLabel(patient.name))
            info_layout.addRow("Age:", QLabel(patient.age))
            info_layout.addRow("Gender:", QLabel(patient.gender))
            info_layout.addRow("Phone Number:", QLabel(patient.phone_number))
            info_layout.addRow("Patient ID:", QLabel(patient.patient_id))
            details_layout.addLayout(info_layout)
            
            # Results Table
            results_table = QTreeWidget()
            results_table.setHeaderLabels(["Sample ID", "Test Name", "Value", "Unit", "Reference Range", "DateTime"])
            results_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch) # Make results table stretch
            for result in patient.results:
                date_time_str = QDateTime(result.date_time).toString('yyyy-MM-dd hh:mm:ss')
                item = QTreeWidgetItem([result.sample_id, result.test_name, result.test_result, result.unit, result.reference_range, date_time_str])
                results_table.addTopLevelItem(item)
            
            details_layout.addWidget(results_table)
            
            # Add the new content widget to the details frame's layout
            self.details_frame_layout.addWidget(self.details_content_widget)

        finally:
            db.close()

class AllResultsViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Search Frame
        search_frame = QFrame()
        search_frame.setFrameShape(QFrame.Shape.StyledPanel)
        
        # Using QGridLayout for side-by-side fields
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
        
        self.without_patient_info_radio = QRadioButton("Without patient info")
        self.without_patient_info_radio.toggled.connect(self.perform_search) # Trigger search on toggle

        search_button = QPushButton("Search")
        search_button.clicked.connect(self.perform_search)
        
        # Arrange widgets in the grid layout
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

        search_grid_layout.addWidget(self.without_patient_info_radio, 3, 0, 1, 2) # Span 2 columns
        search_grid_layout.addWidget(search_button, 3, 3)
        
        self.layout.addWidget(search_frame)

        # Results Table
        self.results_table = QTreeWidget()
        self.results_table.setHeaderLabels(["Sample ID", "Patient ID", "Patient Name", "Test Name", "Value", "Unit", "Reference Range", "DateTime", "Result ID"]) # Added Result ID for easier lookup
        self.results_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnHidden(8, True) # Hide result ID
        self.results_table.itemClicked.connect(self.open_result_details_window) # Connect double click
        
        self.layout.addWidget(self.results_table)

    def perform_search(self):
        sample_id = self.sample_id_search_input.text()
        patient_id = self.patient_id_search_input.text()
        patient_name = self.patient_name_search_input.text()
        test_name = self.test_name_search_input.text()
        from_date = self.from_date_input.date().toPyDate()
        to_date = self.to_date_input.date().toPyDate()
        without_patient_info = self.without_patient_info_radio.isChecked()

        db = SessionLocal()
        try:
            results = search_results(db, 
                                     sample_id=sample_id, 
                                     patient_id=patient_id, 
                                     patient_name=patient_name, 
                                     test_name=test_name, 
                                     from_date=from_date, 
                                     to_date=to_date,
                                     without_patient_info=without_patient_info)
            self.results_table.clear()
            for result in results:
                patient = result.patient
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
                    str(result.id) # Store result ID in hidden column
                ])
                self.results_table.addTopLevelItem(item)
        finally:
            db.close()

    def open_result_details_window(self, item):
        result_id = int(item.text(8)) # Get ID from hidden column
        details_window = ResultDetailsWindow(result_id, self)
        details_window.patient_info_saved.connect(self.perform_search) # Connect signal to refresh table
        details_window.exec()

class DoctorPanelWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # --- Add Doctor Form ---
        form_frame = QFrame()
        form_frame.setFrameShape(QFrame.Shape.StyledPanel)
        form_layout = QFormLayout(form_frame)

        self.doctor_id_label = QLabel("Auto-Generated")
        self.name_input = QLineEdit()
        self.designation_input = QLineEdit()
        self.age_input = QLineEdit()
        self.gender_combo = QComboBox()
        self.gender_combo.addItems(["Male", "Female", "Others"])
        self.phone_input = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Verification", "Finalization", "Both"])

        form_layout.addRow("Doctor ID:", self.doctor_id_label)
        form_layout.addRow("Name:", self.name_input)
        form_layout.addRow("Designation:", self.designation_input)
        form_layout.addRow("Age:", self.age_input)
        form_layout.addRow("Gender:", self.gender_combo)
        form_layout.addRow("Phone Number:", self.phone_input)
        form_layout.addRow("Type:", self.type_combo)

        add_doctor_button = QPushButton("Add Doctor")
        add_doctor_button.clicked.connect(self.add_doctor_to_db)
        form_layout.addRow(add_doctor_button)

        self.layout.addWidget(form_frame)
        self.refresh_doctor_id() # Generate initial ID

        # --- All Doctors List ---
        self.doctor_table = QTreeWidget()
        self.doctor_table.setHeaderLabels(["Doctor ID", "Name", "Designation", "Age", "Gender", "Phone", "Type"])
        self.doctor_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.doctor_table)

        # --- Search Options ---
        search_frame = QFrame()
        search_frame.setFrameShape(QFrame.Shape.StyledPanel)
        search_layout = QFormLayout(search_frame)

        self.search_name_input = QLineEdit()
        self.search_id_input = QLineEdit()
        self.search_phone_input = QLineEdit()

        search_layout.addRow("Search Name:", self.search_name_input)
        search_layout.addRow("Search ID:", self.search_id_input)
        search_layout.addRow("Search Phone:", self.search_phone_input)

        search_button = QPushButton("Search Doctors")
        search_button.clicked.connect(self.perform_doctor_search)
        search_layout.addRow(search_button)

        self.layout.addWidget(search_frame)

        self.load_doctors_to_table() # Load initial data

    def refresh_doctor_id(self):
        db = SessionLocal()
        try:
            self.doctor_id_label.setText(get_next_doctor_id(db))
        finally:
            db.close()

    def add_doctor_to_db(self):
        name = self.name_input.text()
        designation = self.designation_input.text()
        age = self.age_input.text()
        gender = self.gender_combo.currentText()
        phone = self.phone_input.text()
        doctor_type = self.type_combo.currentText()

        if not all([name, designation, age, phone]):
            QMessageBox.warning(self, "Input Error", "Please fill all doctor details.")
            return

        try:
            age = int(age)
        except ValueError:
            QMessageBox.warning(self, "Input Error", "Age must be a number.")
            return

        db = SessionLocal()
        try:
            add_doctor(db, name, designation, age, gender, phone, doctor_type)
            QMessageBox.information(self, "Success", "Doctor added successfully!")
            self.clear_form()
            self.load_doctors_to_table() # Refresh table
            self.refresh_doctor_id() # Generate new ID
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to add doctor: {e}")
        finally:
            db.close()

    def clear_form(self):
        self.name_input.clear()
        self.designation_input.clear()
        self.age_input.clear()
        self.phone_input.clear()
        self.gender_combo.setCurrentIndex(0)
        self.type_combo.setCurrentIndex(0)

    def load_doctors_to_table(self):
        self.doctor_table.clear()
        db = SessionLocal()
        try:
            doctors = get_all_doctors(db)
            for doctor in doctors:
                item = QTreeWidgetItem([
                    doctor.doctor_id,
                    doctor.name,
                    doctor.designation,
                    str(doctor.age),
                    doctor.gender,
                    doctor.phone_number,
                    doctor.type
                ])
                self.doctor_table.addTopLevelItem(item)
        finally:
            db.close()

    def perform_doctor_search(self):
        name = self.search_name_input.text()
        doctor_id = self.search_id_input.text()
        phone = self.search_phone_input.text()

        self.doctor_table.clear()
        db = SessionLocal()
        try:
            doctors = search_doctors(db, name=name, doctor_id=doctor_id, phone_number=phone)
            for doctor in doctors:
                item = QTreeWidgetItem([
                    doctor.doctor_id,
                    doctor.name,
                    doctor.designation,
                    str(doctor.age),
                    doctor.gender,
                    doctor.phone_number,
                    doctor.type
                ])
                self.doctor_table.addTopLevelItem(item)
        finally:
            db.close()

class VerificationDetailsWindow(QDialog):
    verification_updated = pyqtSignal()

    def __init__(self, result_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Verify Result")
        self.result_id = result_id
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.db_session = SessionLocal()
        self.result = get_result_by_id_with_patient_and_doctor(self.db_session, self.result_id)
        
        if not self.result:
            QMessageBox.critical(self, "Error", "Result not found.")
            self.close()
            return

        # --- Patient Details ---
        patient_frame = QFrame()
        patient_frame.setFrameShape(QFrame.Shape.StyledPanel)
        patient_layout = QFormLayout(patient_frame)
        patient_header = QLabel("Patient Details")
        patient_header.setObjectName("header")
        self.layout.addWidget(patient_header)
        self.layout.addWidget(patient_frame)

        if self.result.patient:
            patient_layout.addRow("Patient Name:", QLabel(self.result.patient.name))
            patient_layout.addRow("Age:", QLabel(self.result.patient.age))
            patient_layout.addRow("Gender:", QLabel(self.result.patient.gender))
            patient_layout.addRow("Phone Number:", QLabel(self.result.patient.phone_number))
            patient_layout.addRow("Patient ID:", QLabel(self.result.patient.patient_id))
        else:
            patient_layout.addRow("Patient Info:", QLabel("N/A"))

        # --- Result Details ---
        result_frame = QFrame()
        result_frame.setFrameShape(QFrame.Shape.StyledPanel)
        result_layout = QFormLayout(result_frame)
        result_header = QLabel("Result Details")
        result_header.setObjectName("header")
        self.layout.addWidget(result_header)
        self.layout.addWidget(result_frame)

        result_layout.addRow("Sample ID:", QLabel(self.result.sample_id))
        result_layout.addRow("Test Name:", QLabel(self.result.test_name))
        result_layout.addRow("Test Result:", QLabel(self.result.test_result))
        result_layout.addRow("Unit:", QLabel(self.result.unit))
        result_layout.addRow("Reference Range:", QLabel(self.result.reference_range))
        result_layout.addRow("Date/Time:", QLabel(self.result.date_time.strftime('%Y-%m-%d %H:%M:%S')))
        
        verified_by_text = self.result.verified_by_doctor.name if self.result.verified_by_doctor else "Not Verified"
        result_layout.addRow("Verified By:", QLabel(verified_by_text))

        # --- Doctor Selection for Verification ---
        doctor_selection_frame = QFrame()
        doctor_selection_frame.setFrameShape(QFrame.Shape.StyledPanel)
        doctor_selection_layout = QFormLayout(doctor_selection_frame)
        doctor_selection_header = QLabel("Select Doctor for Verification")
        doctor_selection_header.setObjectName("header")
        self.layout.addWidget(doctor_selection_header)
        self.layout.addWidget(doctor_selection_frame)

        self.doctor_combo = QComboBox()
        self.doctor_combo.addItem("Select Doctor", userData=None) # Default "empty" selection
        self.load_doctors_for_verification()
        doctor_selection_layout.addRow("Doctor:", self.doctor_combo)

        self.verify_button = QPushButton("Verify Result")
        self.verify_button.clicked.connect(self.perform_verification)
        doctor_selection_layout.addRow(self.verify_button)

        self.layout.addStretch(1)
        self.adjustSize()
        self.setMinimumSize(self.size())
        
    def load_doctors_for_verification(self):
        doctors = get_doctors_by_type(self.db_session, "Verification")
        for doctor in doctors:
            self.doctor_combo.addItem(f"{doctor.name} ({doctor.doctor_id})", userData=doctor.id)
        
        # Set current doctor if already verified
        if self.result.verified_by_doctor_id:
            index = self.doctor_combo.findData(self.result.verified_by_doctor_id)
            if index != -1:
                self.doctor_combo.setCurrentIndex(index)

    def perform_verification(self):
        selected_doctor_id = self.doctor_combo.currentData()

        if selected_doctor_id is None:
            QMessageBox.warning(self, "Selection Error", "Please select a doctor for verification.")
            return

        try:
            update_result_verification(self.db_session, self.result_id, selected_doctor_id)
            self.db_session.commit()
            QMessageBox.information(self, "Success", "Result verified successfully!")
            self.verification_updated.emit() # Emit signal
            self.accept() # Close the dialog
        except Exception as e:
            self.db_session.rollback()
            QMessageBox.critical(self, "Error", f"Failed to verify result: {e}")

    def closeEvent(self, event):
        self.db_session.close()
        super().closeEvent(event)

class VerificationViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Search Frame (similar to AllResultsViewWidget)
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

        search_grid_layout.addWidget(search_button, 3, 3)
        
        self.layout.addWidget(search_frame)

        # Results Table
        self.results_table = QTreeWidget()
        self.results_table.setHeaderLabels(["Sample ID", "Patient ID", "Patient Name", "Test Name", "Value", "Unit", "Reference Range", "DateTime", "Verified By", "Result ID"]) # Added Verified By and Result ID
        self.results_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnHidden(9, True) # Hide result ID
        self.results_table.itemClicked.connect(self.open_verification_details_window) # Connect click to open verification window
        
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
            # Reusing search_results, which includes joinedload for patient and verified_by_doctor
            results = search_results(db, 
                                     sample_id=sample_id, 
                                     patient_id=patient_id, 
                                     patient_name=patient_name, 
                                     test_name=test_name, 
                                     from_date=from_date, 
                                     to_date=to_date,
                                     without_patient_info=False) # Show all results for verification
            self.results_table.clear()
            for result in results:
                patient = result.patient
                verified_by = result.verified_by_doctor.name if result.verified_by_doctor else "N/A"
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
                    verified_by,
                    str(result.id) # Store result ID in hidden column
                ])
                self.results_table.addTopLevelItem(item)
        finally:
            db.close()

    def open_verification_details_window(self, item):
        result_id = int(item.text(9)) # Get ID from hidden column (index 9)
        details_window = VerificationDetailsWindow(result_id, self)
        details_window.verification_updated.connect(self.perform_search) # Refresh table on update
        details_window.exec()

class FinalizationDetailsWindow(QDialog):
    finalization_updated = pyqtSignal()

    def __init__(self, result_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Finalize Result")
        self.result_id = result_id
        
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        self.db_session = SessionLocal()
        self.result = get_result_by_id_with_patient_and_doctor(self.db_session, self.result_id)
        
        if not self.result:
            QMessageBox.critical(self, "Error", "Result not found.")
            self.close()
            return

        # --- Patient Details ---
        patient_frame = QFrame()
        patient_frame.setFrameShape(QFrame.Shape.StyledPanel)
        patient_layout = QFormLayout(patient_frame)
        patient_header = QLabel("Patient Details")
        patient_header.setObjectName("header")
        self.layout.addWidget(patient_header)
        self.layout.addWidget(patient_frame)

        if self.result.patient:
            patient_layout.addRow("Patient Name:", QLabel(self.result.patient.name))
            patient_layout.addRow("Age:", QLabel(self.result.patient.age))
            patient_layout.addRow("Gender:", QLabel(self.result.patient.gender))
            patient_layout.addRow("Phone Number:", QLabel(self.result.patient.phone_number))
            patient_layout.addRow("Patient ID:", QLabel(self.result.patient.patient_id))
        else:
            patient_layout.addRow("Patient Info:", QLabel("N/A"))

        # --- Result Details ---
        result_frame = QFrame()
        result_frame.setFrameShape(QFrame.Shape.StyledPanel)
        result_layout = QFormLayout(result_frame)
        result_header = QLabel("Result Details")
        result_header.setObjectName("header")
        self.layout.addWidget(result_header)
        self.layout.addWidget(result_frame)

        result_layout.addRow("Sample ID:", QLabel(self.result.sample_id))
        result_layout.addRow("Test Name:", QLabel(self.result.test_name))
        result_layout.addRow("Test Result:", QLabel(self.result.test_result))
        result_layout.addRow("Unit:", QLabel(self.result.unit))
        result_layout.addRow("Reference Range:", QLabel(self.result.reference_range))
        result_layout.addRow("Date/Time:", QLabel(self.result.date_time.strftime('%Y-%m-%d %H:%M:%S')))
        result_layout.addRow("Status:", QLabel(self.result.status))
        
        verified_by_text = self.result.verified_by_doctor.name if self.result.verified_by_doctor else "Not Verified"
        result_layout.addRow("Verified By:", QLabel(verified_by_text))
        finalized_by_text = self.result.finalized_by_doctor.name if self.result.finalized_by_doctor else "Not Finalized"
        result_layout.addRow("Finalized By:", QLabel(finalized_by_text))

        # --- Doctor Selection for Finalization ---
        doctor_selection_frame = QFrame()
        doctor_selection_frame.setFrameShape(QFrame.Shape.StyledPanel)
        doctor_selection_layout = QFormLayout(doctor_selection_frame)
        doctor_selection_header = QLabel("Select Doctor for Finalization")
        doctor_selection_header.setObjectName("header")
        self.layout.addWidget(doctor_selection_header)
        self.layout.addWidget(doctor_selection_frame)

        self.finalization_doctor_combo = QComboBox()
        self.finalization_doctor_combo.addItem("Select Doctor", userData=None) # Default "empty" selection
        self.load_doctors_for_finalization()
        doctor_selection_layout.addRow("Finalizing Doctor:", self.finalization_doctor_combo)

        self.finalize_button = QPushButton("Finalize Result")
        self.finalize_button.clicked.connect(self.perform_finalization)
        doctor_selection_layout.addRow(self.finalize_button)

        # Conditional logic based on result status
        if self.result.status == "Finalized":
            self.finalization_doctor_combo.setEnabled(False)
            self.finalize_button.setEnabled(False)
        elif self.result.status == "Pending":
            # If pending, can also verify from here, but the request was specifically for Finalization
            # Keeping it focused on finalization as per explicit request for now.
            # If user asks for combined Verify/Finalize in this dialog, we'd add another combo/button.
            pass # Keep enabled
        elif self.result.status == "Verified":
            pass # Keep enabled

        self.layout.addStretch(1)
        self.adjustSize()
        self.setMinimumSize(self.size())
        
    def load_doctors_for_finalization(self):
        doctors = get_doctors_by_type(self.db_session, "Finalization")
        for doctor in doctors:
            self.finalization_doctor_combo.addItem(f"{doctor.name} ({doctor.doctor_id})", userData=doctor.id)
        
        # Set current doctor if already finalized
        if self.result.finalized_by_doctor_id:
            index = self.finalization_doctor_combo.findData(self.result.finalized_by_doctor_id)
            if index != -1:
                self.finalization_doctor_combo.setCurrentIndex(index)

    def perform_finalization(self):
        selected_doctor_id = self.finalization_doctor_combo.currentData()

        if selected_doctor_id is None:
            QMessageBox.warning(self, "Selection Error", "Please select a doctor for finalization.")
            return

        try:
            update_result_finalization(self.db_session, self.result_id, selected_doctor_id)
            self.db_session.commit()
            QMessageBox.information(self, "Success", "Result finalized successfully!")
            self.finalization_updated.emit() # Emit signal
            self.accept() # Close the dialog
        except Exception as e:
            self.db_session.rollback()
            QMessageBox.critical(self, "Error", f"Failed to finalize result: {e}")

    def closeEvent(self, event):
        self.db_session.close()
        super().closeEvent(event)

class FinalizationViewWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)

        # Search Frame
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

        # Radio buttons for status
        self.status_radio_group = QHBoxLayout()
        self.all_radio = QRadioButton("All")
        self.all_radio.setChecked(True)
        self.pending_radio = QRadioButton("Pending")
        self.verified_radio = QRadioButton("Verified")
        self.finalized_radio = QRadioButton("Finalized")
        
        self.status_radio_group.addWidget(self.all_radio)
        self.status_radio_group.addWidget(self.pending_radio)
        self.status_radio_group.addWidget(self.verified_radio)
        self.status_radio_group.addWidget(self.finalized_radio)
        
        self.all_radio.toggled.connect(self.perform_search)
        self.pending_radio.toggled.connect(self.perform_search)
        self.verified_radio.toggled.connect(self.perform_search)
        self.finalized_radio.toggled.connect(self.perform_search)

        search_grid_layout.addLayout(self.status_radio_group, 3, 0, 1, 3)
        search_grid_layout.addWidget(search_button, 3, 3)
        
        self.layout.addWidget(search_frame)

        # Results Table
        self.results_table = QTreeWidget()
        self.results_table.setHeaderLabels(["Sample ID", "Patient ID", "Patient Name", "Test Name", "Value", "Unit", "Reference Range", "DateTime", "Status", "Verified By", "Finalized By", "Result ID"])
        self.results_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.results_table.setColumnHidden(11, True) # Hide result ID
        self.results_table.itemClicked.connect(self.open_finalization_details_window)
        
        self.layout.addWidget(self.results_table)
        self.perform_search() # Load initial data

    def perform_search(self):
        sample_id = self.sample_id_search_input.text()
        patient_id = self.patient_id_search_input.text()
        patient_name = self.patient_name_search_input.text()
        test_name = self.test_name_search_input.text()
        from_date = self.from_date_input.date().toPyDate()
        to_date = self.to_date_input.date().toPyDate()

        status = None
        if self.pending_radio.isChecked():
            status = "Pending"
        elif self.verified_radio.isChecked():
            status = "Verified"
        elif self.finalized_radio.isChecked():
            status = "Finalized"

        db = SessionLocal()
        try:
            results = search_results(db, 
                                     sample_id=sample_id, 
                                     patient_id=patient_id, 
                                     patient_name=patient_name, 
                                     test_name=test_name, 
                                     from_date=from_date, 
                                     to_date=to_date,
                                     status=status,
                                     without_patient_info=False)
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

    def open_finalization_details_window(self, item):
        result_id = int(item.text(11)) # Get ID from hidden column (index 11)
        details_window = FinalizationDetailsWindow(result_id, self)
        details_window.finalization_updated.connect(self.perform_search) # Refresh table on update
        details_window.exec()
        
class ServerThread(QThread):
    data_received = pyqtSignal(str)
    log_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.host = 'localhost'
        self.port = 6000 # Default port
        self.running = False
        self.server_socket = None

    def load_config(self):
        db = SessionLocal()
        config = get_machine_config(db)
        if config:
            self.host = config.ip
            self.port = int(config.port)
        db.close()

    def run(self):
        self.load_config()
        self.running = True
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(1)
            self.log_message.emit(f"Server listening on {self.host}:{self.port}")

            while self.running:
                try:
                    self.server_socket.settimeout(0.5)
                    conn, addr = self.server_socket.accept()
                    with conn:
                        self.log_message.emit(f"Connected by {addr}")
                        data = conn.recv(4096)
                        if data:
                            stx = data.find(b'\x02')
                            etx = data.find(b'\x03')
                            if stx != -1 and etx != -1:
                                astm_message = data[stx+1:etx].decode('utf-8')
                                self.data_received.emit(astm_message)
                            else:
                                self.log_message.emit("Received malformed ASTM message.")
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log_message.emit(f"Error during connection: {e}")
        except Exception as e:
            self.log_message.emit(f"Server error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
            self.log_message.emit("Server stopped.")

    def stop(self):
        self.running = False
        if self.server_socket:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(1)
                    s.connect((self.host, self.port))
            except Exception as e:
                self.log_message.emit(f"Error while stopping server: {e}")
        self.wait()

class MachineConfigWindow(QDialog):
    config_saved = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Machine Configuration")
        self.setGeometry(500, 250, 300, 200)

        self.layout = QVBoxLayout()
        self.form_layout = QFormLayout()

        self.machine_id_input = QLineEdit()
        self.ip_input = QLineEdit()
        self.port_input = QLineEdit()

        self.form_layout.addRow("Machine ID:", self.machine_id_input)
        self.form_layout.addRow("IP:", self.ip_input)
        self.form_layout.addRow("Port:", self.port_input)

        self.save_button = QPushButton("Save Configuration")
        self.save_button.clicked.connect(self.save_config)

        self.status_label = QLabel("Enter machine details and click Save.")

        self.layout.addLayout(self.form_layout)
        self.layout.addWidget(self.save_button)
        self.layout.addWidget(self.status_label)
        self.setLayout(self.layout)
        
        self.load_config()

    def save_config(self):
        db = SessionLocal()
        try:
            update_single_machine_config(db, self.machine_id_input.text(), self.ip_input.text(), self.port_input.text())
            self.status_label.setText("Configuration saved successfully!")
            self.config_saved.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save configuration: {e}")
        finally:
            db.close()

    def load_config(self):
        db = SessionLocal()
        try:
            config = get_machine_config(db)
            if config:
                self.machine_id_input.setText(config.machine_id)
                self.ip_input.setText(config.ip)
                self.port_input.setText(config.port)
                self.status_label.setText("Existing configuration loaded.")
            else:
                self.status_label.setText("No configuration found.")
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Could not load configuration: {e}")
        finally:
            db.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("LIS System")
        self.setGeometry(250, 60, 800, 600)
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.create_menu()

        self.stacked_widget = QStackedWidget()
        self.layout.addWidget(self.stacked_widget)

        # Create and add views with headers
        self.live_results_view = self._create_live_results_view()
        self.patients_view = self._create_view("Patients", PatientsViewWidget())
        self.all_results_view = self._create_view("All Results", AllResultsViewWidget())
        self.doctor_panel_view = self._create_view("Doctor Panel", DoctorPanelWidget())
        self.verification_view = self._create_view("Verification", VerificationViewWidget())
        self.finalization_view = self._create_view("Finalization", FinalizationViewWidget())
        self.reports_view = self._create_view("Reports", ReportsViewWidget(main_window=self))


        self.stacked_widget.addWidget(self.live_results_view)
        self.stacked_widget.addWidget(self.patients_view)
        self.stacked_widget.addWidget(self.all_results_view)
        self.stacked_widget.addWidget(self.doctor_panel_view)
        self.stacked_widget.addWidget(self.verification_view)
        self.stacked_widget.addWidget(self.finalization_view)
        self.stacked_widget.addWidget(self.reports_view)


        self.server_thread = ServerThread()
        self.server_thread.data_received.connect(self.handle_astm_data)
        self.server_thread.log_message.connect(self.log_message)

    def get_icon_for_title(self, title):
        style = self.style()
        if title == "Patients":
            return style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        if title == "All Results":
            return style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView)
        if title == "Doctor Panel":
            return style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton)
        if title == "Verification":
            return style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        if title == "Finalization":
            return style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        if title == "Reports":
            return style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        if title == "Live Results":
            return style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight)
        return QIcon() # Return an empty icon if no match

    def _create_view(self, title, content_widget):
        container = QWidget()
        layout = QVBoxLayout(container)
        
        header = QFrame()
        header.setObjectName("header_frame") # Set object name
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header)
        
        icon_label = QLabel()
        icon = self.get_icon_for_title(title) # I will create this helper function
        icon_label.setPixmap(icon.pixmap(16, 16))
        icon_label.setStyleSheet("border: none;") # Ensure no border for the icon
        header_layout.addWidget(icon_label)

        title_label = QLabel(title)
        title_label.setObjectName("header")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        layout.addWidget(header)
        layout.addWidget(content_widget)
        
        return container

    def _create_live_results_view(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        header = QFrame()
        header.setObjectName("header_frame")
        header.setFrameShape(QFrame.Shape.StyledPanel)
        header_layout = QHBoxLayout(header)

        icon_label = QLabel()
        icon = self.get_icon_for_title("Live Results") # I will create this helper function
        icon_label.setPixmap(icon.pixmap(16, 16))
        icon_label.setStyleSheet("border: none;") # Ensure no border for the icon
        header_layout.addWidget(icon_label)

        title_label = QLabel("Live Results")
        title_label.setObjectName("header")
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        self.start_stop_button = QPushButton("Start")
        self.start_stop_button.setObjectName("start_stop_button")
        self.start_stop_button.clicked.connect(self.toggle_communication)
        header_layout.addWidget(self.start_stop_button)

        layout.addWidget(header)

        # Original Live Results Content
        self.live_results_widget = QWidget()
        live_layout = QVBoxLayout(self.live_results_widget)

        self.data_table = QTreeWidget()
        self.data_table.setHeaderLabels(["Sample ID", "Test Name", "Value", "Unit", "Reference Range", "DateTime", "Status", "ID"])
        self.data_table.header().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.data_table.setColumnHidden(7, True)
        self.data_table.itemClicked.connect(self.open_patient_details_window)
        
        self.status_box = QTextEdit()
        self.status_box.setReadOnly(True)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.data_table)
        
        log_box_container = QWidget()
        log_box_layout = QVBoxLayout(log_box_container)
        log_box_layout.addWidget(QLabel("Log Box"))
        log_box_layout.addWidget(self.status_box)
        log_box_layout.setContentsMargins(0,0,0,0)
        splitter.addWidget(log_box_container)

        splitter.setSizes([400, 200])
        live_layout.addWidget(splitter)
        
        layout.addWidget(self.live_results_widget)
        
        return container

    def create_menu(self):
        self.menu_bar = self.menuBar()
        style = self.style()

        # View Menu
        view_menu = self.menu_bar.addMenu("View")
        
        live_results_action = QAction("Live Results", self)
        live_results_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowRight))
        live_results_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(0))
        view_menu.addAction(live_results_action)
        
        patients_action = QAction("Patients", self)
        patients_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
        patients_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(1))
        view_menu.addAction(patients_action)

        all_results_action = QAction("All Results", self)
        all_results_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
        all_results_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(2))
        view_menu.addAction(all_results_action)

        # Settings Menu
        settings_menu = self.menu_bar.addMenu("Settings")
        self.mc_action = QAction("Machine Config", self)
        self.mc_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.mc_action.triggered.connect(self.open_mc_window)
        settings_menu.addAction(self.mc_action)

        # Doctor Panel Menu
        doctor_panel_menu = self.menu_bar.addMenu("Doctor Panel")
        
        add_doctor_action = QAction("Add Doctor", self)
        add_doctor_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogYesButton))
        add_doctor_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(3))
        doctor_panel_menu.addAction(add_doctor_action)

        # Verification sub-menu
        verification_action = QAction("Verification", self)
        verification_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton))
        verification_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(4))
        doctor_panel_menu.addAction(verification_action)

        # Finalization sub-menu
        finalization_action = QAction("Finalization", self)
        finalization_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        finalization_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(5))
        doctor_panel_menu.addAction(finalization_action)

        # Reports Menu
        reports_menu = self.menu_bar.addMenu("Reports")
        view_reports_action = QAction("View Reports", self)
        view_reports_action.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon))
        view_reports_action.triggered.connect(lambda: self.stacked_widget.setCurrentIndex(6))
        reports_menu.addAction(view_reports_action)

    def open_mc_window(self):
        mc_window = MachineConfigWindow()
        mc_window.config_saved.connect(self.handle_machine_config_saved)
        mc_window.exec()

    def open_patient_details_window(self, item):
        result_id = int(item.text(7)) # Get ID from hidden column
        patient_window = ResultDetailsWindow(result_id, self)
        patient_window.exec()

    def toggle_communication(self):
        if self.start_stop_button.text() == "Start":
            self.start_communication()
        else:
            self.stop_communication()

    def start_communication(self):
        self.start_stop_button.setText("Stop")
        self.start_stop_button.setStyleSheet("background-color: red; color: white;") # Set to red
        self.server_thread.start()

    def stop_communication(self):
        self.start_stop_button.setText("Start")
        self.start_stop_button.setStyleSheet("background-color: #4CAF50; color: white;") # Set to green
        self.server_thread.stop()

    def handle_astm_data(self, data):
        self.log_message(f"Received ASTM data: {data}")
        parsed_data = parse_astm(data)
        if parsed_data:
            db = SessionLocal()
            try:
                date_time_str = parsed_data.get('datetime', QDateTime.currentDateTime().toString('yyyyMMddhhmmss'))
                db_result = insert_result_details(
                    db,
                    sample_id=parsed_data.get('sample_id', ''),
                    test_name=parsed_data.get('test_name', ''),
                    test_result=parsed_data.get('value', ''),
                    unit=parsed_data.get('unit', ''),
                    reference_range=parsed_data.get('ref_range', ''),
                    date_time=QDateTime.fromString(date_time_str, 'yyyyMMddhhmmss').toPyDateTime()
                )
                self.log_message("Result details saved to database.")
                
                display_date_time = QDateTime(db_result.date_time).toString('yyyy-MM-dd hh:mm:ss')
                self.add_data_to_table(db_result, display_date_time, parsed_data.get('status', ''))
            except Exception as e:
                self.log_message(f"Error processing ASTM data: {e}")
            finally:
                db.close()

    def log_message(self, message):
        self.status_box.append(f"{QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')} - {message}")

    def handle_machine_config_saved(self):
        self.log_message("Machine configuration updated. Restarting server...")
        if self.server_thread.isRunning():
            self.stop_communication()
            self.start_communication()

    def add_data_to_table(self, db_result, display_date_time, status):
        item = QTreeWidgetItem([
            db_result.sample_id, 
            db_result.test_name, 
            db_result.test_result, 
            db_result.unit,
            db_result.reference_range, 
            display_date_time, 
            status,
            str(db_result.id) # Add ID to hidden column
        ])
        self.data_table.addTopLevelItem(item)
        
    def closeEvent(self, event):
        self.stop_communication()
        self.server_thread.quit()
        self.server_thread.wait()
        event.accept()

if __name__ == "__main__":
    # --- Database Migration Step ---
    perform_finalization_migration(engine, Base) # Call new finalization migration
    perform_verification_migration(engine, Base) 
    perform_result_details_migration(engine, Base)
    perform_patient_migration(engine, Base)
    # --- End Database Migration Step ---

    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if not get_machine_config(db):
            update_single_machine_config(db, "default", "localhost", "6000")
            print("Default machine configuration created.")
    finally:
        db.close()
    
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE_SHEET)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())
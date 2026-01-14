STYLE_SHEET = """
    QMainWindow {
        background-color: #f0f0f0; /* Light grey for main window */
    }
    QLabel {
        color: #00008B; /* Dark Blue */
        border: none; /* Ensure no border for general labels */
    }
    QLabel#header {
        color: #ADD8E6; /* Light Blue */
        font-size: 16px; 
        font-weight: bold;
        border: none; /* Ensure no border for header labels */
    }
    QFrame {
        background-color: #F8F8F8; /* Very light grey for frames */
        border: 1px solid #4682B4; /* SteelBlue Border */
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
    }
    QMenu {
        background-color: #f0f0f0;
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
    QLineEdit, QDateEdit, QComboBox {
        border: 1px solid #00008B;
        padding: 2px;
        border-radius: 3px;
    }
"""

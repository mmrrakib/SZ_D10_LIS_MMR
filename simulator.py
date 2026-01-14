import sys
import socket
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget, QTextEdit
from PyQt6.QtCore import QDateTime

class SimulatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ASTM Simulator")
        self.setGeometry(100, 100, 400, 500)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)

        self.astm_display = QTextEdit()
        self.astm_display.setReadOnly(True)
        self.layout.addWidget(self.astm_display)

        self.send_button = QPushButton("Send ASTM Message")
        self.send_button.clicked.connect(self.send_astm_message)
        self.layout.addWidget(self.send_button)
    
    def generate_astm_message(self):
        # Simplified ASTM message for demonstration
        # H - Header, P - Patient, O - Order, R - Result, L - Terminator
        # Each segment is on a new line. The message should start with STX and end with ETX,
        # but for simplicity, we'll send the raw string and handle framing on the server side.
        
        patient_id = "12345"
        sample_id = "S001"
        test_name = "Glucose"
        value = "10.5"
        units = "mg/dL"
        ref_range = "4.0-6.0"
        status = "F" # Final result
        
        # ASTM format: segments separated by \r
        message = (
            f"H|\^&|||LIS-Simulator|||||||LIS||P|1\r"
            f"P|1|{patient_id}\r"
            f"O|1|{sample_id}||^^^{test_name}|R\r"
            f"R|1|^^^{test_name}|{value}|{units}|{ref_range}|N||{status}|||{QDateTime.currentDateTime().toString('yyyyMMddhhmmss')}\r"
            f"L|1|N\r"
        )
        return message

    def send_astm_message(self):
        astm_message = self.generate_astm_message()
        self.astm_display.setText(astm_message)

        # Standard ASTM framing: <STX> [message] <ETX> <CR> <LF>
        # STX = 0x02, ETX = 0x03
        framed_message = f"\x02{astm_message}\x03\r\n"

        host = 'localhost'
        port = 6000

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((host, port))
                s.sendall(framed_message.encode('utf-8'))
            self.astm_display.append("\n--- Message sent successfully! ---")
        except ConnectionRefusedError:
            self.astm_display.append("\n--- Connection refused. Is the LIS server running? ---")
        except Exception as e:
            self.astm_display.append(f"\n--- Error sending message: {e} ---")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    sim_win = SimulatorWindow()
    sim_win.show()
    sys.exit(app.exec())

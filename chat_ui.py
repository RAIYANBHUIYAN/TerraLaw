import sys
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QLineEdit, QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont

API_URL = "http://127.0.0.1:8000/ask"


# ============================
# Worker Thread for API calls
# ============================
class ApiWorker(QThread):
    result_signal = pyqtSignal(str)

    def __init__(self, question):
        super().__init__()
        self.question = question

    def run(self):
        try:
            response = requests.get(API_URL, params={"question": self.question})
            data = response.json()
            answer = data.get("answer", "No answer available.")
        except Exception as e:
            answer = f"API Error: {e}"

        self.result_signal.emit(answer)


# ============================
# Chat Bubble Widget
# ============================
class ChatBubble(QLabel):
    def __init__(self, text, is_user=False):
        super().__init__(text)
        self.setWordWrap(True)
        self.setFont(QFont("Segoe UI", 11))

        if is_user:
            self.setStyleSheet("""
                background-color: #0B93F6;
                color: white;
                padding: 12px;
                border-radius: 12px;
            """)
        else:
            self.setStyleSheet("""
                background-color: #EAEAEA;
                color: #000;
                padding: 12px;
                border-radius: 12px;
            """)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)


# ============================
# Main Chat Window
# ============================
class ChatWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ChatGPT-Style RAG Chatbot")
        self.setGeometry(200, 100, 700, 800)
        self.setStyleSheet("background-color: white;")

        # Main Layout
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.add_header()
        self.add_chat_area()
        self.add_input_area()

    # Header Bar
    def add_header(self):
        header = QFrame()
        header.setStyleSheet("background-color: #1E1E1E;")
        header.setFixedHeight(60)

        title = QLabel("🤖 RAG Chatbot — ChatGPT Style")
        title.setStyleSheet("color: white;")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        hbox = QVBoxLayout(header)
        hbox.addWidget(title)

        self.layout.addWidget(header)

    # Scrollable Chat Area
    def add_chat_area(self):
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("border: none;")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll.setWidget(self.chat_container)
        self.layout.addWidget(self.scroll)

    # Input Area
    def add_input_area(self):
        bottom = QHBoxLayout()

        self.input = QLineEdit()
        self.input.setPlaceholderText("Ask something...")
        self.input.setFont(QFont("Segoe UI", 12))
        self.input.setStyleSheet("""
            QLineEdit {
                border: 2px solid #CCC;
                border-radius: 10px;
                padding: 10px;
                margin: 10px;
            }
            QLineEdit:focus {
                border: 2px solid #0B93F6;
            }
        """)

        self.input.returnPressed.connect(self.handle_send)

        self.send_btn = QPushButton("Send")
        self.send_btn.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        self.send_btn.setStyleSheet("""
            QPushButton {
                background-color: #0B93F6;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                margin-right: 10px;
            }
            QPushButton:hover {
                background-color: #007BDA;
            }
        """)

        self.send_btn.clicked.connect(self.handle_send)

        bottom.addWidget(self.input)
        bottom.addWidget(self.send_btn)

        bottom_frame = QFrame()
        bottom_frame.setLayout(bottom)

        self.layout.addWidget(bottom_frame)

    # Send Handler
    def handle_send(self):
        text = self.input.text().strip()
        if not text:
            return

        self.add_message(text, is_user=True)
        self.input.clear()

        # Worker Thread
        self.worker = ApiWorker(text)
        self.worker.result_signal.connect(self.handle_response)
        self.worker.start()

    # Add User/Bot Message
    def add_message(self, text, is_user=False):
        bubble = ChatBubble(text, is_user=is_user)

        wrapper = QHBoxLayout()
        if is_user:
            wrapper.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            wrapper.setAlignment(Qt.AlignmentFlag.AlignLeft)

        wrapper.addWidget(bubble)

        container = QFrame()
        container.setLayout(wrapper)

        self.chat_layout.addWidget(container)
        QApplication.processEvents()
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())

    # Handle API Response
    def handle_response(self, text):
        self.add_message(text, is_user=False)


# Run App
app = QApplication(sys.argv)
window = ChatWindow()
window.show()
sys.exit(app.exec())

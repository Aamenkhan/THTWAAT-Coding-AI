from PySide6 import QtCore
import threading

class AIWorker(QtCore.QThread):
    token_received = QtCore.Signal(str)
    finished = QtCore.Signal()
    error_occurred = QtCore.Signal(str)

    def __init__(self, provider_router, prompt, model, system=None, parent=None):
        super().__init__(parent)
        self.provider_router = provider_router
        self.prompt = prompt
        self.model = model
        self.system = system
        self.stop_event = threading.Event()
        
    def stop(self):
        self.stop_event.set()

    def run(self):
        try:
            print(f"AIWorker started. Prompt: {self.prompt}, Model: {self.model}", flush=True)
            generator = self.provider_router.generate_stream(
                prompt=self.prompt,
                model=self.model,
                system=self.system,
                stop_event=self.stop_event
            )
            print(f"Generator created: {generator}", flush=True)
            for token in generator:
                if self.stop_event.is_set():
                    print("AIWorker stop event is set, breaking.")
                    break
                print(f"AIWorker yielded token: {token!r}")
                self.token_received.emit(token)
            print("AIWorker finished iterating.")
            self.finished.emit()
        except Exception as e:
            print(f"AI Worker encountered an error: {e}")
            self.error_occurred.emit(str(e))

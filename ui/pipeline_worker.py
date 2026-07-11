from PySide6 import QtCore
import threading
from typing import Dict, Optional
from ai.pipeline import PipelineRun, Stage, Pipeline
from ai.agent import AIAgent
from packager.packager import ConfigManager

class PipelineWorker(QtCore.QThread):
    stage_changed = QtCore.Signal(str, int)  # label, progress
    finished = QtCore.Signal(bool, str)      # success, result_message
    review_requested = QtCore.Signal()       # trigger UI review dialog
    
    def __init__(self, run_instance: PipelineRun, diff_engine, parent=None):
        super().__init__(parent)
        self.run_instance = run_instance
        self.diff_engine = diff_engine
        self._resume_event = threading.Event()
        self._approval_result = False

    def run(self):
        try:
            config = ConfigManager().load()
            project_dir = config.get("project_root", ".")
            model = config.get("model", "qwen2.5-coder:3b")
            
            # Instantiate agent for pipeline
            agent = AIAgent(model=model, project_dir=project_dir)
            agent.diff_engine = self.diff_engine
            agent.planner.diff_engine = self.diff_engine
            
            pipeline = Pipeline(agent)
            
            def on_progress(run: PipelineRun, stage: Stage, msg: str, data: Optional[Dict] = None):
                self.run_instance = run
                self.stage_changed.emit(msg, run.progress_percent)
                
            def on_approval(run: PipelineRun, stage: Stage) -> bool:
                self.run_instance = run
                self._resume_event.clear()
                self.review_requested.emit()
                self._resume_event.wait()
                return self._approval_result
                
            # Start the synchronous pipeline execution
            run_result = pipeline.start(
                self.run_instance.goal,
                on_progress=on_progress,
                on_approval=on_approval
            )
            
            if run_result.stage == Stage.FAILED:
                self.finished.emit(False, f"Pipeline failed: {run_result.stage_results.get(Stage.FAILED, 'Unknown error')}")
            else:
                self.finished.emit(True, "Pipeline completed successfully.")
                
        except Exception as e:
            self.finished.emit(False, str(e))

    def resume(self, approved: bool):
        self._approval_result = approved
        self._resume_event.set()

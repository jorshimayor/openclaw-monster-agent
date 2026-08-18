from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..core.config import Settings
from ..core.logging import get_logger
from ..core.types import AgentRole, PipelineStep, Task, TaskStatus
from . import steps as pipeline_steps
from .patterns import PATTERN_CONFIGS, WorkflowPattern, match_pattern

if TYPE_CHECKING:
    from ..knowledge.memory import ExperienceMemory
    from ..knowledge.store import CrystallizedKnowledgeStore
    from ..llm.router import LLMRouter
    from ..mcp.manager import McpServerManager

logger = get_logger(__name__)


class PipelineExecutor:
    def __init__(
        self,
        settings: Settings,
        llm: Optional["LLMRouter"],
        manager: Optional["McpServerManager"],
        store: Optional["CrystallizedKnowledgeStore"],
        memory: Optional["ExperienceMemory"],
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.mcp_manager = manager
        self.store = store
        self.memory = memory
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self._cancelled: set = set()

    def _make_event(
        self,
        task_id: str,
        step: Optional[str],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "task_id": task_id,
            "step": step,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _emit(
        self,
        task: Task,
        step_name: str,
        data: Dict[str, Any],
        event_callback: Optional[Callable],
    ) -> None:
        event = self._make_event(str(task.id), step_name, data)
        tid = str(task.id)
        state = self.tasks.get(tid, {})
        buf: List[Dict[str, Any]] = state.setdefault("event_buffer", [])
        buf.append(event)
        state["events"] = buf
        self.tasks[tid] = state
        if event_callback is not None:
            try:
                cb = event_callback(event)
                if asyncio.iscoroutine(cb):
                    loop = asyncio.get_event_loop()
                    loop.create_task(cb)
            except Exception as exc:
                logger.warning("event_callback_failed", error=str(exc))

    async def run(
        self,
        task: Task,
        event_callback: Optional[Callable[[Dict[str, Any]], Any]] = None,
    ) -> Task:
        tid = str(task.id)
        self._cancelled.discard(tid)
        self.tasks[tid] = {
            "current_step": None,
            "outputs": {},
            "events": [],
            "event_buffer": [],
            "cancelled": False,
        }
        task.status = TaskStatus.RUNNING
        logger.info("pipeline_run_start", task_id=tid)
        self._emit(task, "pipeline_start", {"status": task.status}, event_callback)

        outputs: Dict[str, Any] = {}
        try:
            task.step = PipelineStep.COMPLEXITY_CHECK
            self.tasks[tid]["current_step"] = task.step
            sr1, ss1 = await pipeline_steps.step1_complexity_check(task)
            outputs["step1"] = {"status": sr1, "state": ss1}
            self._emit(task, "step1_complexity", ss1, event_callback)
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.PATTERN_MATCH
            self.tasks[tid]["current_step"] = task.step
            pattern_id, ss2 = await pipeline_steps.step2_pattern_match(task.description)
            outputs["step2"] = {"status": pattern_id, "state": ss2}
            self._emit(task, "step2_pattern", ss2, event_callback)
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            cfg = PATTERN_CONFIGS.get(pattern_id) or PATTERN_CONFIGS[WorkflowPattern.GENERIC]

            task.step = PipelineStep.EXPERIENCE_RECALL
            self.tasks[tid]["current_step"] = task.step
            experience_lessons: List[str] = []
            if self.memory is not None:
                _, ss3 = await pipeline_steps.step3_experience_recall(
                    pattern_id, task.description, self.memory
                )
                experience_lessons = list(ss3.get("lessons", []))
                outputs["step3"] = {"status": "OK", "state": ss3}
                self._emit(task, "step3_experience", ss3, event_callback)
            else:
                outputs["step3"] = {"status": "SKIP", "state": {"lessons": [], "recalled_count": 0}}
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.TEAM_ASSEMBLY
            self.tasks[tid]["current_step"] = task.step
            registry = self.mcp_manager.registry if self.mcp_manager is not None else None
            _, ss4 = await pipeline_steps.step4_team_assembly(cfg, experience_lessons, registry)
            outputs["step4"] = {"status": "OK", "state": ss4}
            self._emit(task, "step4_team", ss4, event_callback)
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            waves_cfg = ss4.get("agent_waves_cfg", [])
            task.step = PipelineStep.PROMPT_INJECTION
            self.tasks[tid]["current_step"] = task.step
            shared_ctx = {
                "task_description": task.description,
                "experience_lessons": experience_lessons,
                "pattern": pattern_id,
            }
            _, ss5 = await pipeline_steps.step5_prompt_injection(waves_cfg, shared_ctx)
            outputs["step5"] = {"status": "OK", "state": ss5}
            self._emit(task, "step5_prompt", {"waves": len(waves_cfg)}, event_callback)
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.PARALLEL_EXECUTION
            self.tasks[tid]["current_step"] = task.step
            waves_with_prompts = ss5.get("agent_waves_with_prompts", [])
            _, ss6 = await pipeline_steps.step6_parallel_execution(
                waves_with_prompts, self.llm, None
            )
            outputs["step6"] = {"status": "OK", "state": ss6}
            all_outputs = ss6.get("all_outputs", [])
            self._emit(
                task,
                "step6_execution",
                {"outputs": len(all_outputs), "seconds": ss6.get("execution_seconds")},
                event_callback,
            )
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.VERIFIER
            self.tasks[tid]["current_step"] = task.step
            _, ss7 = await pipeline_steps.step7_verifier(
                all_outputs, None, self.llm, None
            )
            outputs["step7"] = {"status": "OK", "state": ss7}
            verified = ss7.get("verified_outputs", [])
            self._emit(
                task,
                "step7_verifier",
                {"passed": ss7.get("passed_count"), "failed": ss7.get("failed_count")},
                event_callback,
            )
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.QUALITY_GATE
            self.tasks[tid]["current_step"] = task.step
            review_team = ss4.get("review_team", [])
            gate, ss8 = await pipeline_steps.step8_p6_quality_gate(
                verified, review_team, self.llm, None
            )
            outputs["step8"] = {"status": gate, "state": ss8}
            self._emit(
                task,
                "step8_quality_gate",
                {"overall": gate, "aggregate": ss8.get("aggregate_score")},
                event_callback,
            )
            approved_outputs = list(ss8.get("approved_outputs", []))
            failed_outputs = list(ss8.get("failed_outputs", []))

            if gate != pipeline_steps.PASS and failed_outputs:
                if self._is_cancelled(tid):
                    task.status = TaskStatus.CANCELLED
                    return task
                task.step = PipelineStep.FIX_REVALIDATE
                self.tasks[tid]["current_step"] = task.step
                _, ss9 = await pipeline_steps.step9_fix_and_revalidate(
                    failed_outputs, [], self.llm, None, single_rework=True
                )
                outputs["step9"] = {"status": "OK", "state": ss9}
                self._emit(
                    task,
                    "step9_fix",
                    {"reworked": len(ss9.get("reworked_outputs", []))},
                    event_callback,
                )
                reworked = ss9.get("reworked_outputs", [])
                if reworked:
                    task.step = PipelineStep.VERIFIER
                    self.tasks[tid]["current_step"] = task.step
                    _, ss7b = await pipeline_steps.step7_verifier(
                        reworked, None, self.llm, None
                    )
                    outputs["step7b"] = {"status": "OK", "state": ss7b}
                    for v in ss7b.get("verified_outputs", []):
                        if v["passed"]:
                            approved_outputs.append(v["original_output"])
                        else:
                            logger.info(
                                "rework_still_failed",
                                role=v["agent_role"],
                                feedback=v.get("feedback"),
                            )
                    self._emit(
                        task,
                        "step7b_reverify",
                        {
                            "passed": ss7b.get("passed_count"),
                            "failed": ss7b.get("failed_count"),
                        },
                        event_callback,
                    )

            task.step = PipelineStep.SYNTHESIZER
            self.tasks[tid]["current_step"] = task.step
            orchestrator_agent = None
            _, ss10 = await pipeline_steps.step10_synthesizer(
                approved_outputs,
                orchestrator_agent,
                self.llm,
                None,
                task.description,
            )
            outputs["step10"] = {"status": "OK", "state": ss10}
            final_report = ss10.get("final_report", "")
            task.outputs["final_report"] = final_report
            task.outputs["overall_confidence"] = ss10.get("overall_confidence", 0.0)
            task.outputs["confidence_ratings"] = ss10.get("confidence_ratings", {})
            self._emit(
                task,
                "step10_synthesizer",
                {"report_chars": len(final_report)},
                event_callback,
            )
            if self._is_cancelled(tid):
                task.status = TaskStatus.CANCELLED
                return task

            task.step = PipelineStep.POST_TASK_REFLECTION
            self.tasks[tid]["current_step"] = task.step
            try:
                crystallizer_agent = None
                _, ss11 = await pipeline_steps.step11_post_task_reflection(
                    final_report,
                    task,
                    crystallizer_agent,
                    self.llm,
                    None,
                    self.store,
                    self.memory,
                )
                outputs["step11"] = {"status": "OK", "state": ss11}
                task.outputs["crystal_id"] = ss11.get("saved_crystal_id")
                task.outputs["lessons_stored"] = ss11.get("lessons_stored", [])
                self._emit(
                    task,
                    "step11_reflection",
                    {"crystal_id": ss11.get("saved_crystal_id")},
                    event_callback,
                )
            except Exception as exc:
                logger.exception("step11_reflection_failed", error=str(exc))
                outputs["step11"] = {"status": "ERROR", "error": str(exc)}

            task.status = TaskStatus.COMPLETED
            self._emit(
                task,
                "pipeline_end",
                {"status": task.status, "final_report_chars": len(final_report)},
                event_callback,
            )
        except Exception as exc:
            logger.exception("pipeline_run_error", task_id=tid, error=str(exc))
            task.status = TaskStatus.FAILED
            task.outputs["error"] = str(exc)
            self._emit(
                task,
                "pipeline_error",
                {"status": task.status, "error": str(exc)},
                event_callback,
            )
        finally:
            task.step = None
            self.tasks[tid]["outputs"] = outputs
            self.tasks[tid]["current_step"] = None
        task.outputs["step_outputs"] = outputs
        return task

    def _is_cancelled(self, task_id: str) -> bool:
        return task_id in self._cancelled

    def get_state(self, task_id: str) -> Optional[Dict[str, Any]]:
        return self.tasks.get(str(task_id))

    def cancel(self, task_id: str) -> bool:
        tid = str(task_id)
        if tid not in self.tasks:
            return False
        self._cancelled.add(tid)
        self.tasks[tid]["cancelled"] = True
        logger.info("pipeline_task_cancelled", task_id=tid)
        return True

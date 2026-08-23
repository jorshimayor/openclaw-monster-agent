from __future__ import annotations

from typing import Any, Dict, List

import networkx as nx

from ..core.logging import get_logger
from ..core.types import PipelineStep
from .patterns import PATTERN_CONFIGS, WorkflowPattern

logger = get_logger(__name__)


class WorkflowGraphBuilder:
    def build(self, pattern: WorkflowPattern) -> nx.DiGraph:
        cfg = PATTERN_CONFIGS.get(pattern)
        if cfg is None:
            raise ValueError(f"Unknown workflow pattern: {pattern}")
        wave_count = len(cfg.agent_waves)

        graph = nx.DiGraph()

        graph.add_node("task_input", step=None, label="Task Input")

        nodes_order: List[str] = ["task_input"]

        graph.add_node(
            "step1_complexity",
            step=PipelineStep.COMPLEXITY_CHECK,
            label="Step 1: Complexity Check",
        )
        nodes_order.append("step1_complexity")

        graph.add_node(
            "step2_pattern",
            step=PipelineStep.PATTERN_MATCH,
            label="Step 2: Pattern Match",
        )
        nodes_order.append("step2_pattern")

        graph.add_node(
            "step3_experience",
            step=PipelineStep.EXPERIENCE_RECALL,
            label="Step 3: Experience Recall",
        )
        nodes_order.append("step3_experience")

        graph.add_node(
            "step4_team",
            step=PipelineStep.TEAM_ASSEMBLY,
            label="Step 4: Team Assembly",
        )
        nodes_order.append("step4_team")

        graph.add_node(
            "step5_prompt",
            step=PipelineStep.PROMPT_INJECTION,
            label="Step 5: Prompt Injection",
        )
        nodes_order.append("step5_prompt")

        for i in range(wave_count):
            wave_idx = i + 1
            node_id = f"step6_execute_wave{wave_idx}"
            graph.add_node(
                node_id,
                step=PipelineStep.PARALLEL_EXECUTION,
                label=f"Step 6: Execute Wave {wave_idx}",
                wave_index=i,
            )
            nodes_order.append(node_id)

        graph.add_node(
            "step7_verify",
            step=PipelineStep.VERIFIER,
            label="Step 7: Verifier",
        )
        nodes_order.append("step7_verify")

        graph.add_node(
            "step8_quality_gate",
            step=PipelineStep.QUALITY_GATE,
            label="Step 8: P6 Quality Gate",
        )
        nodes_order.append("step8_quality_gate")

        graph.add_node(
            "step9_fix",
            step=PipelineStep.FIX_REVALIDATE,
            label="Step 9: Fix and Revalidate",
        )
        nodes_order.append("step9_fix")

        graph.add_node(
            "step10_synthesize",
            step=PipelineStep.SYNTHESIZER,
            label="Step 10: Synthesizer",
        )
        nodes_order.append("step10_synthesize")

        graph.add_node(
            "step11_reflect",
            step=PipelineStep.POST_TASK_REFLECTION,
            label="Step 11: Post-Task Reflection",
        )
        nodes_order.append("step11_reflect")

        graph.add_node("final_output", step=None, label="Final Output")
        nodes_order.append("final_output")

        for i in range(len(nodes_order) - 1):
            src = nodes_order[i]
            dst = nodes_order[i + 1]
            if src == "step8_quality_gate":
                continue
            if src == "step9_fix":
                continue
            graph.add_edge(src, dst, condition="default")

        graph.add_edge(
            "step8_quality_gate",
            "step10_synthesize",
            condition="PASS",
        )
        graph.add_edge(
            "step8_quality_gate",
            "step9_fix",
            condition="FAIL",
        )
        # Rework is a BOUNDED second verifier pass (the executor emits it as
        # "step7b_reverify"), not a loop back to step 7 — a literal back-edge
        # made the graph cyclic and failed DAG validation.
        graph.add_node(
            "step7b_reverify",
            step=PipelineStep.VERIFIER,
            label="Step 7b: Re-verify Reworked Outputs",
        )
        graph.add_edge(
            "step9_fix",
            "step7b_reverify",
            condition="REWORK",
        )
        graph.add_edge(
            "step7b_reverify",
            "step10_synthesize",
            condition="default",
        )

        cycles = list(nx.simple_cycles(graph))
        if cycles:
            raise ValueError(
                f"Workflow graph is not acyclic; cycles detected: {cycles}"
            )

        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("Workflow graph has a cycle; failed DAG validation")

        logger.info(
            "workflow_graph_built",
            pattern=pattern,
            nodes=graph.number_of_nodes(),
            edges=graph.number_of_edges(),
            waves=wave_count,
        )
        return graph

"""Generate Camunda-compatible BPMN 2.0 XML.

generate_bpmn()        – per-solution linear BPMN (kept for backwards compat)
generate_master_bpmn() – single master BPMN with XOR exclusive gateways for all
                         solution groups; stage IDs = stage_name so the frontend
                         can map AuditStep.stage_name → diagram element for highlighting.
"""

from __future__ import annotations

from typing import List, Tuple

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
TASK_W, TASK_H = 130, 52
GW_SZ = 50           # gateway square side
H_GAP = 44           # horizontal gap between shapes
V_GAP = 18           # vertical gap between branches
ROW_H = TASK_H + V_GAP
CENTER_Y = 420       # vertical centre of the whole diagram (enough for 7 rows)
START_R = 18         # start/end event radius


# ---------------------------------------------------------------------------
# Master BPMN definition
# ---------------------------------------------------------------------------
# Each group: (group_id, [ (branch_label, [stage_name, ...]), ... ])
# An empty stage list means "skip / bypass" path.
_MASTER_GROUPS: List[Tuple[str, List[Tuple[str, List[str]]]]] = [
    ("native_pdf", [
        ("pymupdf",    ["pymupdf_native"]),
        ("pdfplumber", ["pdfplumber_native"]),
        ("skip",       []),
    ]),
    ("preprocessing", [
        ("opencv", ["preprocess_opencv", "layout_ruled_table"]),
        ("skip",   []),
    ]),
    ("ocr", [
        ("tesseract",         ["ocr_tesseract"]),
        ("easyocr",           ["ocr_easyocr"]),
        ("doctr",             ["ocr_doctr"]),
        ("paddleocr",         ["ocr_paddleocr"]),
        ("trocr",             ["ocr_trocr"]),
        ("deepdoc",           ["ocr_deepdoc"]),
        ("skip",              []),
    ]),
    ("img2table", [
        ("tess",   ["tables_img2table_tesseract"]),
        ("easy",   ["tables_img2table_easyocr"]),
        ("doctr",  ["tables_img2table_doctr"]),
        ("paddle", ["tables_img2table_paddle"]),
        ("skip",   []),
    ]),
    ("vector_tables", [
        ("camelot",         ["tables_camelot"]),
        ("camelot_lattice", ["tables_camelot_lattice"]),
        ("camelot_stream",  ["tables_camelot_stream"]),
        ("tabula",          ["tables_tabula"]),
        ("tabula_lattice",  ["tables_tabula_lattice"]),
        ("tabula_stream",   ["tables_tabula_stream"]),
        ("skip",            []),
    ]),
    ("vision_llm", [
        ("claude",        ["vision_claude"]),
        ("openai",        ["vision_openai"]),
        ("gemini",        ["vision_gemini"]),
        ("paddle",        ["vision_paddle_structure"]),
        ("docling",       ["vision_docling"]),
        ("layout_parser",     ["layout_parser_detect"]),
        ("layout_parser_pdf", ["layout_parser_pdf_detect"]),
        ("skip",              []),
    ]),
]

_COMMON_TAIL: List[str] = [
    "pii_presidio",
    "layout_doc_format",
    "layout_custom_table",
    "table_crop",
    "table_obfuscate",
    "annotate_render",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _label(stage_name: str) -> str:
    return stage_name.replace("_", " ").title()


def _edge_xml(flow_id: str, waypoints: List[Tuple[float, float]]) -> str:
    pts = "".join(f'<di:waypoint x="{int(x)}" y="{int(y)}"/>' for x, y in waypoints)
    return f'      <bpmndi:BPMNEdge id="edge_{flow_id}" bpmnElement="{flow_id}">{pts}</bpmndi:BPMNEdge>'


def _task_shape(stage: str, x: float, y: float) -> str:
    return (
        f'      <bpmndi:BPMNShape id="shape_{stage}" bpmnElement="{stage}">'
        f'<dc:Bounds x="{int(x)}" y="{int(y)}" width="{TASK_W}" height="{TASK_H}"/>'
        f'<bpmndi:BPMNLabel/></bpmndi:BPMNShape>'
    )


def _gw_shape(gw_id: str, cx: float, cy: float) -> str:
    return (
        f'      <bpmndi:BPMNShape id="shape_{gw_id}" bpmnElement="{gw_id}" isMarkerVisible="true">'
        f'<dc:Bounds x="{int(cx - GW_SZ/2)}" y="{int(cy - GW_SZ/2)}" width="{GW_SZ}" height="{GW_SZ}"/>'
        f'<bpmndi:BPMNLabel/></bpmndi:BPMNShape>'
    )


def _event_shape(ev_id: str, cx: float, cy: float, stroke: str = "#1a7f37") -> str:
    return (
        f'      <bpmndi:BPMNShape id="shape_{ev_id}" bpmnElement="{ev_id}">'
        f'<dc:Bounds x="{int(cx - START_R)}" y="{int(cy - START_R)}" width="{START_R*2}" height="{START_R*2}"/>'
        f'<bpmndi:BPMNLabel/></bpmndi:BPMNShape>'
    )


# ---------------------------------------------------------------------------
# Per-solution BPMN (unchanged interface)
# ---------------------------------------------------------------------------
def generate_bpmn(solution_name: str, display_name: str, stages: List[str]) -> str:
    """Return a linear BPMN 2.0 XML string for a single solution.

    SpiffWorkflow v3 note:
      - Start/end event IDs MUST NOT be "Start"/"End" — those clash with
        BpmnProcessSpec's synthetic StartTask/EndTask.
      - Tasks use <bpmn:task> (NoneTask) so SpiffWorkflow can intercept them
        via get_tasks(READY); <bpmn:serviceTask> needs a script engine.
      - We keep the camunda:field extension for stage_name lookup.
    """
    # Unique IDs that won't collide with SpiffWorkflow's synthetic nodes
    start_id = f"StartEvent_{solution_name}"
    end_id   = f"EndEvent_{solution_name}"

    n = len(stages)
    task_x = [100 + 18 + H_GAP + i * (TASK_W + H_GAP) for i in range(n)]
    end_cx = task_x[-1] + TASK_W + H_GAP + START_R if n else 200
    cy = 108

    flows_xml: List[str] = []
    flows_xml.append(f'<bpmn:sequenceFlow id="flow_Start_{stages[0]}" sourceRef="{start_id}" targetRef="{stages[0]}"/>')
    for i in range(n - 1):
        flows_xml.append(f'<bpmn:sequenceFlow id="flow_{stages[i]}_{stages[i+1]}" sourceRef="{stages[i]}" targetRef="{stages[i+1]}"/>')
    flows_xml.append(f'<bpmn:sequenceFlow id="flow_{stages[-1]}_End" sourceRef="{stages[-1]}" targetRef="{end_id}"/>')

    tasks_xml: List[str] = []
    for s in stages:
        tasks_xml.append(
            f'    <bpmn:task id="{s}" name="{_label(s)}">'
            f'<bpmn:extensionElements>'
            f'<camunda:field name="stage_name"><camunda:string>{s}</camunda:string></camunda:field>'
            f'</bpmn:extensionElements>'
            f'</bpmn:task>'
        )

    shapes: List[str] = [_event_shape(start_id, 100, cy)]
    for i, s in enumerate(stages):
        shapes.append(_task_shape(s, task_x[i], cy - TASK_H / 2))
    shapes.append(_event_shape(end_id, end_cx, cy))

    edges: List[str] = []
    edges.append(_edge_xml(f"flow_Start_{stages[0]}", [(100 + START_R, cy), (task_x[0], cy)]))
    for i in range(n - 1):
        edges.append(_edge_xml(
            f"flow_{stages[i]}_{stages[i+1]}",
            [(task_x[i] + TASK_W, cy), (task_x[i+1], cy)],
        ))
    edges.append(_edge_xml(
        f"flow_{stages[-1]}_End",
        [(task_x[-1] + TASK_W, cy), (end_cx - START_R, cy)],
    ))

    inner_proc = (
        f'    <bpmn:startEvent id="{start_id}" name="Start"/>\n'
        + "\n".join(f'    {f}' for f in flows_xml) + "\n"
        + "\n".join(tasks_xml) + "\n"
        + f'    <bpmn:endEvent id="{end_id}" name="End"/>'
    )
    return _wrap_bpmn(
        proc_id=solution_name,
        proc_name=display_name,
        inner_proc=inner_proc,
        shapes=shapes,
        edges=edges,
    )


# ---------------------------------------------------------------------------
# Master BPMN
# ---------------------------------------------------------------------------
def generate_master_bpmn() -> str:
    """Single master BPMN with XOR gateways for each solution group."""

    flows_proc: List[str] = []   # process-level XML fragments
    shapes: List[str] = []
    edges: List[str] = []

    # Must not use "Start"/"End" — those clash with SpiffWorkflow's synthetic nodes
    MASTER_START_ID = "StartEvent_master"
    MASTER_END_ID   = "EndEvent_master"

    start_cx = 80
    shapes.append(_event_shape(MASTER_START_ID, start_cx, CENTER_Y))

    cursor_x = start_cx + START_R
    prev_id = MASTER_START_ID
    prev_cx = start_cx
    prev_cy = CENTER_Y

    for group_id, branches in _MASTER_GROUPS:
        n_branches = len(branches)
        max_tasks = max((len(tasks) for _, tasks in branches), default=0)

        # ---- split gateway ----
        split_cx = cursor_x + H_GAP + GW_SZ / 2
        split_cy = CENTER_Y
        split_id = f"gw_split_{group_id}"
        shapes.append(_gw_shape(split_id, split_cx, split_cy))
        flows_proc.append(
            f'    <bpmn:inclusiveGateway id="{split_id}" name="" gatewayDirection="Diverging"/>'
        )
        flow_id = f"flow_{prev_id}_{split_id}"
        flows_proc.append(f'    <bpmn:sequenceFlow id="{flow_id}" sourceRef="{prev_id}" targetRef="{split_id}"/>')
        edges.append(_edge_xml(flow_id, [(prev_cx + (START_R if prev_id == MASTER_START_ID else 0), prev_cy), (split_cx - GW_SZ / 2, split_cy)]))

        # ---- join gateway position ----
        tasks_block_w = max_tasks * (TASK_W + H_GAP) if max_tasks > 0 else H_GAP
        join_cx = split_cx + GW_SZ / 2 + H_GAP + tasks_block_w + H_GAP + GW_SZ / 2
        join_cy = CENTER_Y
        join_id = f"gw_join_{group_id}"

        # ---- branch Y centres ----
        branch_ys = [
            CENTER_Y + (i - (n_branches - 1) / 2) * ROW_H
            for i in range(n_branches)
        ]

        for b_idx, ((blabel, tasks), branch_cy) in enumerate(zip(branches, branch_ys)):
            if not tasks:
                # skip path — route above/below the group
                bypass_y = CENTER_Y + (n_branches / 2 + 0.8) * ROW_H
                skip_flow_id = f"flow_{split_id}_skip{b_idx}_{join_id}"
                flows_proc.append(
                    f'    <bpmn:sequenceFlow id="{skip_flow_id}" name="skip" sourceRef="{split_id}" targetRef="{join_id}"/>'
                )
                edges.append(_edge_xml(skip_flow_id, [
                    (split_cx, split_cy + GW_SZ / 2),
                    (split_cx, bypass_y),
                    (join_cx, bypass_y),
                    (join_cx, join_cy + GW_SZ / 2),
                ]))
            else:
                # tasks in sequence for this branch
                task_xs = [
                    split_cx + GW_SZ / 2 + H_GAP + t_idx * (TASK_W + H_GAP)
                    for t_idx in range(len(tasks))
                ]
                for t_idx, stage in enumerate(tasks):
                    tx = task_xs[t_idx]
                    ty = branch_cy - TASK_H / 2
                    shapes.append(_task_shape(stage, tx, ty))
                    flows_proc.append(
                        f'    <bpmn:task id="{stage}" name="{_label(stage)}">'
                        f'<bpmn:extensionElements>'
                        f'<camunda:field name="stage_name"><camunda:string>{stage}</camunda:string></camunda:field>'
                        f'</bpmn:extensionElements>'
                        f'</bpmn:task>'
                    )

                # split → first task
                f0 = f"flow_{split_id}_{tasks[0]}"
                flows_proc.append(f'    <bpmn:sequenceFlow id="{f0}" sourceRef="{split_id}" targetRef="{tasks[0]}"/>')
                edges.append(_edge_xml(f0, [
                    (split_cx + GW_SZ / 2, split_cy),
                    (split_cx + GW_SZ / 2 + H_GAP / 2, split_cy),
                    (split_cx + GW_SZ / 2 + H_GAP / 2, branch_cy),
                    (task_xs[0], branch_cy),
                ]))

                # task → task
                for t_idx in range(len(tasks) - 1):
                    fi = f"flow_{tasks[t_idx]}_{tasks[t_idx+1]}"
                    flows_proc.append(f'    <bpmn:sequenceFlow id="{fi}" sourceRef="{tasks[t_idx]}" targetRef="{tasks[t_idx+1]}"/>')
                    edges.append(_edge_xml(fi, [
                        (task_xs[t_idx] + TASK_W, branch_cy),
                        (task_xs[t_idx + 1], branch_cy),
                    ]))

                # last task → join
                fl = f"flow_{tasks[-1]}_{join_id}"
                flows_proc.append(f'    <bpmn:sequenceFlow id="{fl}" sourceRef="{tasks[-1]}" targetRef="{join_id}"/>')
                edges.append(_edge_xml(fl, [
                    (task_xs[-1] + TASK_W, branch_cy),
                    (join_cx - GW_SZ / 2 - H_GAP / 2, branch_cy),
                    (join_cx - GW_SZ / 2 - H_GAP / 2, join_cy),
                    (join_cx - GW_SZ / 2, join_cy),
                ]))

        # ---- join gateway ----
        shapes.append(_gw_shape(join_id, join_cx, join_cy))
        flows_proc.append(
            f'    <bpmn:inclusiveGateway id="{join_id}" name="" gatewayDirection="Converging"/>'
        )

        cursor_x = join_cx + GW_SZ / 2
        prev_id = join_id
        prev_cx = join_cx
        prev_cy = join_cy

    # ---- common tail ----
    tail_y = CENTER_Y
    tail_xs = [cursor_x + H_GAP + t_idx * (TASK_W + H_GAP) for t_idx in range(len(_COMMON_TAIL))]
    for t_idx, stage in enumerate(_COMMON_TAIL):
        tx = tail_xs[t_idx]
        shapes.append(_task_shape(stage, tx, tail_y - TASK_H / 2))
        flows_proc.append(
            f'    <bpmn:task id="{stage}" name="{_label(stage)}">'
            f'<bpmn:extensionElements>'
            f'<camunda:field name="stage_name"><camunda:string>{stage}</camunda:string></camunda:field>'
            f'</bpmn:extensionElements>'
            f'</bpmn:task>'
        )

    # prev → first tail task
    f0 = f"flow_{prev_id}_{_COMMON_TAIL[0]}"
    flows_proc.append(f'    <bpmn:sequenceFlow id="{f0}" sourceRef="{prev_id}" targetRef="{_COMMON_TAIL[0]}"/>')
    edges.append(_edge_xml(f0, [(prev_cx + GW_SZ / 2, prev_cy), (tail_xs[0], tail_y)]))

    for t_idx in range(len(_COMMON_TAIL) - 1):
        fi = f"flow_{_COMMON_TAIL[t_idx]}_{_COMMON_TAIL[t_idx+1]}"
        flows_proc.append(f'    <bpmn:sequenceFlow id="{fi}" sourceRef="{_COMMON_TAIL[t_idx]}" targetRef="{_COMMON_TAIL[t_idx+1]}"/>')
        edges.append(_edge_xml(fi, [
            (tail_xs[t_idx] + TASK_W, tail_y),
            (tail_xs[t_idx + 1], tail_y),
        ]))

    end_cx = tail_xs[-1] + TASK_W + H_GAP + START_R
    fl = f"flow_{_COMMON_TAIL[-1]}_End"
    flows_proc.append(f'    <bpmn:sequenceFlow id="{fl}" sourceRef="{_COMMON_TAIL[-1]}" targetRef="{MASTER_END_ID}"/>')
    edges.append(_edge_xml(fl, [(tail_xs[-1] + TASK_W, tail_y), (end_cx - START_R, tail_y)]))

    shapes.append(_event_shape(MASTER_END_ID, end_cx, CENTER_Y))
    flows_proc.append(f'    <bpmn:startEvent id="{MASTER_START_ID}" name="Start"/>')
    flows_proc.append(f'    <bpmn:endEvent id="{MASTER_END_ID}" name="End"/>')

    return _wrap_bpmn(
        proc_id="master_pipeline",
        proc_name="SOF Table Extraction — Master Pipeline",
        inner_proc="\n".join(flows_proc),
        shapes=shapes,
        edges=edges,
    )


def _wrap_bpmn(proc_id: str, proc_name: str, inner_proc: str, shapes: List[str], edges: List[str]) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions
  xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
  xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
  xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
  xmlns:di="http://www.omg.org/spec/DD/20100524/DI"
  xmlns:camunda="http://camunda.org/schema/1.0/bpmn"
  id="Definitions_{proc_id}"
  targetNamespace="http://sof-table-extract"
  exporter="sof-table-extract" exporterVersion="0.2">

  <bpmn:process id="{proc_id}" name="{proc_name}" isExecutable="true">
{inner_proc}
  </bpmn:process>

  <bpmndi:BPMNDiagram id="BPMNDiagram_1">
    <bpmndi:BPMNPlane id="BPMNPlane_1" bpmnElement="{proc_id}">
{chr(10).join(shapes)}
{chr(10).join(edges)}
    </bpmndi:BPMNPlane>
  </bpmndi:BPMNDiagram>
</bpmn:definitions>
"""


# ---------------------------------------------------------------------------
# CLI: python -m app.bpmn.generator   (re-generate all .bpmn files on disk)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from pathlib import Path

    out_dir = Path(__file__).parent
    written: List[str] = []

    # Master
    path = out_dir / "master_pipeline.bpmn"
    path.write_text(generate_master_bpmn(), encoding="utf-8")
    written.append(str(path))

    # Per-solution (requires solutions to be registered)
    try:
        import app.solutions  # noqa: F401 — triggers registration
        from app.pipeline.base import registered
        for name, sol in sorted(registered().items()):
            p = out_dir / f"{name}.bpmn"
            p.write_text(generate_bpmn(sol.name, sol.display_name, [s.name for s in sol.stages]), encoding="utf-8")
            written.append(str(p))
    except Exception as exc:
        print(f"Warning: could not generate per-solution files: {exc}", file=sys.stderr)

    for w in written:
        print(f"  wrote {w}")
    print(f"Done — {len(written)} file(s).")

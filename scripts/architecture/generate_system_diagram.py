"""
Claude Workflow Engine - Complete System Architecture Diagram Generator

Generates a professional draw.io diagram showing the entire system:
  - 4 pipeline levels (Level -1 through Level 3)
  - All 15 execution steps with routing decisions
  - External integrations (GitHub, Jira, Figma, Jenkins, SonarQube)
  - Supporting systems (CallGraph, MCP servers, Hook scripts)
  - Hook Mode vs Full Mode execution paths

Output: drawio/system-architecture.drawio

Usage:
    python scripts/architecture/generate_system_diagram.py

# v1.15.2: removed TOON Compress node from Level 1 zone.
#           removed Step 4 (TOON Refinement), Step 5 (Skill & Agent Selection),
#           Step 6 (Skill Validation), Step 7 (Final Prompt Generation) from Level 3.
#           Steps 4-7 were removed from the active pipeline in v1.13.0.
"""

import sys
from pathlib import Path

# ======================================================================
# XML helpers
# ======================================================================


def _esc(text):
    s = str(text)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    return s


class _IDs:
    def __init__(self):
        self._n = 2

    def __call__(self):
        v = str(self._n)
        self._n += 1
        return v


_id = _IDs()


def box(x, y, w, h, label, style, parent="1"):
    return (
        '    <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">'
        '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
        "</mxCell>" % (_id(), _esc(label), style, parent, x, y, w, h)
    )


def child(parent_id, x, y, w, h, label, style):
    return (
        '    <mxCell id="%s" value="%s" style="%s" vertex="1" parent="%s">'
        '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
        "</mxCell>" % (_id(), _esc(label), style, parent_id, x, y, w, h)
    )


def arrow(src, tgt, label="", style="", parent="1"):
    s = style or "endArrow=classic;html=1;strokeColor=#000000;strokeWidth=2;edgeStyle=orthogonalEdgeStyle;"
    return (
        '    <mxCell id="%s" value="%s" style="%s" edge="1" source="%s" target="%s" parent="%s">'
        '<mxGeometry relative="1" as="geometry"/>'
        "</mxCell>" % (_id(), _esc(label), s, src, tgt, parent)
    )


def arrow_pts(x1, y1, x2, y2, label="", style="", parent="1"):
    s = style or "endArrow=classic;html=1;strokeColor=#555555;strokeWidth=1;dashed=1;"
    return (
        '    <mxCell id="%s" value="%s" style="%s" edge="1" parent="%s">'
        '<mxGeometry relative="1" as="geometry">'
        '<mxPoint x="%s" y="%s" as="sourcePoint"/>'
        '<mxPoint x="%s" y="%s" as="targetPoint"/>'
        "</mxGeometry>"
        "</mxCell>" % (_id(), _esc(label), s, parent, x1, y1, x2, y2)
    )


def zone(x, y, w, h, label, fill, stroke, font_style=1):
    style = (
        "swimlane;startSize=28;fontStyle=%d;fontSize=12;fillColor=%s;"
        "strokeColor=%s;strokeWidth=2;html=1;collapsible=0;"
    ) % (font_style, fill, stroke)
    cid = _id()
    cell = (
        '    <mxCell id="%s" value="%s" style="%s" vertex="1" parent="1">'
        '<mxGeometry x="%s" y="%s" width="%s" height="%s" as="geometry"/>'
        "</mxCell>" % (cid, _esc(label), style, x, y, w, h)
    )
    return cid, cell


def step_node(x, y, w, h, label, fill="#E1D5E7", stroke="#9673A6"):
    style = ("rounded=1;whiteSpace=wrap;html=1;fontSize=10;" "fillColor=%s;strokeColor=%s;strokeWidth=2;") % (
        fill,
        stroke,
    )
    cid = _id()
    cell = box(x, y, w, h, label, style)
    return cid, cell


def diamond(x, y, w, h, label, fill="#FFFFFF", stroke="#000000"):
    style = (
        "rhombus;html=1;whiteSpace=wrap;fontSize=10;"
        "fillColor=%s;strokeColor=%s;strokeWidth=2;perimeter=rhombusPerimeter;"
    ) % (fill, stroke)
    cid = _id()
    cell = box(x, y, w, h, label, style)
    return cid, cell


def terminal(x, y, label, fill="#000000", stroke="#000000"):
    style = ("ellipse;html=1;fillColor=%s;strokeColor=%s;fontColor=#FFFFFF;" "fontStyle=1;fontSize=10;") % (
        fill,
        stroke,
    )
    cid = _id()
    cell = box(x, y, 120, 40, label, style)
    return cid, cell


def ext_system(x, y, label, fill="#F5F5F5", stroke="#666666"):
    style = (
        "rounded=1;whiteSpace=wrap;html=1;fontSize=10;fontStyle=1;" "fillColor=%s;strokeColor=%s;strokeWidth=1;"
    ) % (fill, stroke)
    cid = _id()
    cell = box(x, y, 155, 44, label, style)
    return cid, cell


def section_label(x, y, w, h, label, color="#555555"):
    style = (
        "text;html=1;align=center;fontStyle=3;fontSize=11;" "fontColor=%s;fillColor=none;strokeColor=none;"
    ) % color
    return box(x, y, w, h, label, style)


def note(x, y, w, h, label):
    style = (
        "shape=mxgraph.general.note;html=1;whiteSpace=wrap;fontSize=9;"
        "fillColor=#FFF9C4;strokeColor=#D6B656;align=left;spacingLeft=6;"
    )
    cid = _id()
    cell = box(x, y, w, h, label, style)
    return cid, cell


FLOW_ARROW = "endArrow=classic;endFill=1;html=1;strokeColor=#000000;strokeWidth=2;edgeStyle=orthogonalEdgeStyle;"
DASHED_ARROW = (
    "endArrow=open;endSize=8;html=1;strokeColor=#999999;strokeWidth=1;dashed=1;edgeStyle=orthogonalEdgeStyle;"
)
OPT_ARROW = "endArrow=open;endSize=8;html=1;strokeColor=#D79B00;strokeWidth=1;dashed=1;"
BACK_ARROW = "endArrow=classic;endFill=1;html=1;strokeColor=#B85450;strokeWidth=2;curved=1;"


# ======================================================================
# Build diagram
# ======================================================================


def build():
    cells = []
    C = []  # collector

    # ------------------------------------------------------------------
    # TITLE
    # ------------------------------------------------------------------
    C.append(
        box(
            10,
            8,
            1660,
            44,
            "Claude Workflow Engine  \u2014  Complete System Architecture  (v1.5.0)",
            "text;html=1;align=center;fontStyle=1;fontSize=16;" "fillColor=#1e3a5f;fontColor=#FFFFFF;strokeColor=none;",
        )
    )

    # ------------------------------------------------------------------
    # RIGHT PANEL: External Systems  (x=1230)
    # ------------------------------------------------------------------
    RX = 1240
    R_W = 175

    C.append(
        box(
            RX - 12,
            62,
            R_W + 28,
            1680,
            "External Systems & Integrations",
            "swimlane;startSize=28;fontStyle=1;fontSize=11;fillColor=#f5f5f5;"
            "strokeColor=#666666;strokeWidth=2;html=1;collapsible=0;",
        )
    )

    def rsys(y, label, fill, stroke):
        cid = _id()
        C.append(
            box(
                RX,
                y,
                R_W,
                42,
                label,
                "rounded=1;whiteSpace=wrap;html=1;fontSize=10;fontStyle=1;"
                "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (fill, stroke),
            )
        )
        return cid

    gh_id = rsys(100, "GitHub API\n(PR / Issue / Branch / Merge)", "#DAE8FC", "#6C8EBF")
    git_id = rsys(155, "Git (local)\nbranch / commit / push", "#DAE8FC", "#6C8EBF")
    jira_id = rsys(215, "Jira API  [ENABLE_JIRA=1]\nCreate / Transition / Link", "#FFF2CC", "#D6B656")
    figma_id = rsys(270, "Figma API  [ENABLE_FIGMA=1]\nComponents / Tokens / Review", "#D5E8D4", "#82B366")
    jenk_id = rsys(325, "Jenkins  [ENABLE_JENKINS=1]\nTrigger Build / Poll Queue", "#FFE6CC", "#D79B00")
    rsys(380, "SonarQube  [ENABLE_SONARQUBE=1]\nQuality Gate / Scan", "#F8CECC", "#B85450")
    llm_id = rsys(450, "LLM Providers (2)\nClaude CLI / Anthropic", "#E1D5E7", "#9673A6")
    cg_id = rsys(505, "CallGraph Engine\nPython/Java/TS/Kotlin (578 cls)", "#E1D5E7", "#9673A6")
    rsys(555, "14 MCP Servers  (295 tools)\nAll registered in settings.json", "#F0F0F0", "#666666")

    # Separator label
    C.append(section_label(RX, 610, R_W, 18, "\u2015\u2015  Hook Layer  \u2015\u2015"))
    rsys(632, "pre-tool-enforcer.py\nBlocks Write/Edit until L1/L2 done", "#FDEBD0", "#D79B00")
    rsys(687, "post-tool-tracker.py\nProgress / GitHub / Skill Enforce", "#FDEBD0", "#D79B00")
    rsys(742, "stop-notifier.py\nSession save on stop", "#FDEBD0", "#D79B00")

    C.append(section_label(RX, 800, R_W, 18, "\u2015\u2015  Output  \u2015\u2015"))
    out_md = rsys(822, "uml/*.md\nMermaid diagrams (13 types)", "#F0F0F0", "#666666")
    out_dio = rsys(877, "drawio/*.drawio\nProfessional draw.io (12 types)", "#D5E8D4", "#82B366")
    rsys(932, "prompts/\nsystem + user + assistant (3 files)", "#E1D5E7", "#9673A6")
    out_log = rsys(987, "~/.claude/logs/\nsessions / telemetry / errors", "#F0F0F0", "#666666")

    # ------------------------------------------------------------------
    # MAIN COLUMN  x=60..1200
    # ------------------------------------------------------------------
    MX = 60  # main x start
    MW = 1160  # main width

    # ---- ENTRY ZONE ----
    ez_y = 62
    C.append(
        box(
            MX,
            ez_y,
            MW,
            80,
            "ENTRY POINT",
            "swimlane;startSize=22;fontStyle=1;fontSize=11;fillColor=#1e3a5f;"
            "strokeColor=#1e3a5f;fontColor=#FFFFFF;html=1;collapsible=0;",
        )
    )

    user_id, uc = step_node(MX + 10, ez_y + 28, 130, 42, "User Prompt\n(Claude Code IDE)", "#FFFFFF", "#1e3a5f")
    C.append(uc)
    pre_id, pc = step_node(
        MX + 180, ez_y + 28, 175, 42, "pre-tool-enforcer.py\n(PreToolUse hook)", "#FDEBD0", "#D79B00"
    )
    C.append(pc)
    entry_id, ec = step_node(
        MX + 395, ez_y + 28, 200, 42, "3-level-flow.py\n(Entry / session_id / FlowState)", "#DAE8FC", "#6C8EBF"
    )
    C.append(ec)
    pipe_id, pic = step_node(
        MX + 635, ez_y + 28, 185, 42, "PipelineBuilder\n(add_level*().build())", "#E1D5E7", "#9673A6"
    )
    C.append(pic)
    graph_id, gic = step_node(
        MX + 860, ez_y + 28, 200, 42, "LangGraph StateGraph\n(SQLite checkpointer)", "#E1D5E7", "#9673A6"
    )
    C.append(gic)

    C.append(arrow(user_id, pre_id, "", FLOW_ARROW))
    C.append(arrow(pre_id, entry_id, "", FLOW_ARROW))
    C.append(arrow(entry_id, pipe_id, "", FLOW_ARROW))
    C.append(arrow(pipe_id, graph_id, "", FLOW_ARROW))

    # ---- LEVEL -1 ZONE ----
    L1Y = ez_y + 90
    C.append(
        box(
            MX,
            L1Y,
            MW,
            155,
            "LEVEL \u22121  \u2014  AUTO-FIX ENFORCEMENT  (3 checks every run)",
            "swimlane;startSize=26;fontStyle=1;fontSize=11;"
            "fillColor=#FFE6CC;strokeColor=#D79B00;strokeWidth=2;html=1;collapsible=0;",
        )
    )

    u_id, uc2 = step_node(MX + 10, L1Y + 34, 148, 42, "Unicode Fix\nUTF-8 / Windows", "#FFF2CC", "#D79B00")
    e_id, ec2 = step_node(MX + 178, L1Y + 34, 148, 42, "Encoding Fix\nASCII-only .py", "#FFF2CC", "#D79B00")
    wp_id, wc = step_node(MX + 346, L1Y + 34, 148, 42, "WinPath Fix\nBackslash check", "#FFF2CC", "#D79B00")
    lm1_merge_id, lmc = step_node(MX + 524, L1Y + 34, 100, 42, "Merge", "#FFF2CC", "#D79B00")
    ask_id, akc = step_node(MX + 654, L1Y + 34, 130, 42, "Ask Fix?\n(user choice)", "#FFFFFF", "#D79B00")
    fix_id, fxc = step_node(MX + 814, L1Y + 34, 110, 42, "Auto Fix\n(apply patch)", "#FFD580", "#D79B00")
    ok_out_id, okc = step_node(MX + 954, L1Y + 88, 110, 32, "OK\n(proceed)", "#D5E8D4", "#82B366")
    C.extend([uc2, ec2, wc, lmc, akc, fxc, okc])
    C.append(arrow(graph_id, u_id, "", FLOW_ARROW))
    C.append(arrow(u_id, e_id, "", FLOW_ARROW))
    C.append(arrow(e_id, wp_id, "", FLOW_ARROW))
    C.append(arrow(wp_id, lm1_merge_id, "", FLOW_ARROW))
    C.append(arrow(lm1_merge_id, ask_id, "[issues found]", OPT_ARROW))
    C.append(arrow(lm1_merge_id, ok_out_id, "[OK]", FLOW_ARROW))
    C.append(arrow(ask_id, fix_id, "[yes]", FLOW_ARROW))
    C.append(arrow(ask_id, ok_out_id, "[skip]", OPT_ARROW))
    C.append(arrow(fix_id, u_id, "retry \u2191", BACK_ARROW))

    # ---- LEVEL 1 ZONE ----
    # v1.15.2: TOON Compress node removed (TOON removed in v1.15.0).
    #          cx_id and ct_id now feed directly into m1_id (merge).
    L2Y = L1Y + 165
    C.append(
        box(
            MX,
            L2Y,
            MW,
            130,
            "LEVEL 1  \u2014  CONTEXT SYNC  (session + parallel analysis)",
            "swimlane;startSize=26;fontStyle=1;fontSize=11;"
            "fillColor=#D5E8D4;strokeColor=#82B366;strokeWidth=2;html=1;collapsible=0;",
        )
    )

    sess_id, sc = step_node(MX + 10, L2Y + 34, 148, 42, "Session Create\n~/.claude/logs/...", "#EAFAF1", "#82B366")
    cx_id, cxc = step_node(MX + 190, L2Y + 20, 148, 28, "Complexity\nAnalysis", "#EAFAF1", "#82B366")
    ct_id, ctc = step_node(MX + 190, L2Y + 56, 148, 28, "Context Loader\n(README/SRS/CLAUDE)", "#EAFAF1", "#82B366")
    m1_id, m1c = step_node(MX + 370, L2Y + 34, 110, 42, "Merge", "#EAFAF1", "#82B366")
    cl_id, clc = step_node(MX + 510, L2Y + 34, 130, 42, "Cleanup\n(memory free)", "#EAFAF1", "#82B366")
    C.extend([sc, cxc, ctc, m1c, clc])
    C.append(arrow(sess_id, cx_id, "[parallel]", FLOW_ARROW))
    C.append(arrow(sess_id, ct_id, "", FLOW_ARROW))
    C.append(arrow(cx_id, m1_id, "", FLOW_ARROW))
    C.append(arrow(ct_id, m1_id, "", FLOW_ARROW))
    C.append(arrow(m1_id, cl_id, "", FLOW_ARROW))
    # Level -1 -> Level 1 entry
    C.append(arrow(ok_out_id, sess_id, "[OK]", FLOW_ARROW))

    # ---- LEVEL 2 ZONE ----
    L3Y = L2Y + 140
    C.append(
        box(
            MX,
            L3Y,
            MW,
            170,
            "LEVEL 2  \u2014  STANDARDS SYSTEM  (parallel load + Java detection + context optimisation)",
            "swimlane;startSize=26;fontStyle=1;fontSize=11;"
            "fillColor=#DAE8FC;strokeColor=#6C8EBF;strokeWidth=2;html=1;collapsible=0;",
        )
    )

    arc_id, acc = step_node(MX + 10, L3Y + 34, 118, 32, "Archive\n(>95% ctx)", "#EBF5FB", "#6C8EBF")
    tlo_id, tlc = step_node(MX + 10, L3Y + 74, 118, 32, "Tool Opt\n(MCP pattern)", "#EBF5FB", "#6C8EBF")
    mcp2_id, mc2 = step_node(MX + 10, L3Y + 114, 118, 32, "MCP Discovery\n(list servers)", "#EBF5FB", "#6C8EBF")
    cst_id, csc = step_node(MX + 165, L3Y + 46, 148, 42, "Common Stds\n(policies/02-..)", "#EBF5FB", "#6C8EBF")
    djv_id, djc = diamond(MX + 340, L3Y + 52, 90, 44, "Java?", "#FFFFFF", "#6C8EBF")
    jav_id, jac = step_node(MX + 460, L3Y + 30, 135, 32, "Java Standards\n(pom/gradle detect)", "#EBF5FB", "#6C8EBF")
    m2_id, m2c = step_node(MX + 620, L3Y + 46, 100, 42, "Merge", "#EBF5FB", "#6C8EBF")
    sls_id, slc = step_node(MX + 748, L3Y + 46, 140, 42, "Select Stds\n(applicable filter)", "#EBF5FB", "#6C8EBF")
    oc_id, occ = step_node(MX + 915, L3Y + 46, 145, 42, "Optimise Ctx\n(post-standards clean)", "#EBF5FB", "#6C8EBF")
    C.extend([acc, tlc, mc2, csc, djc, jac, m2c, slc, occ])
    C.append(arrow(cl_id, arc_id, "[parallel]", FLOW_ARROW))
    C.append(arrow(cl_id, tlo_id, "", FLOW_ARROW))
    C.append(arrow(cl_id, mcp2_id, "", FLOW_ARROW))
    C.append(arrow(arc_id, cst_id, "", FLOW_ARROW))
    C.append(arrow(tlo_id, m2_id, "", FLOW_ARROW))
    C.append(arrow(mcp2_id, m2_id, "", FLOW_ARROW))
    C.append(arrow(cst_id, djv_id, "", FLOW_ARROW))
    C.append(arrow(djv_id, jav_id, "[Java]", FLOW_ARROW))
    C.append(arrow(djv_id, m2_id, "[no]", FLOW_ARROW))
    C.append(arrow(jav_id, m2_id, "", FLOW_ARROW))
    C.append(arrow(m2_id, sls_id, "", FLOW_ARROW))
    C.append(arrow(sls_id, oc_id, "", FLOW_ARROW))

    # ---- LEVEL 3 ZONE ----
    L4Y = L3Y + 180
    L4H = 1270
    C.append(
        box(
            MX,
            L4Y,
            MW,
            L4H,
            "LEVEL 3  \u2014  EXECUTION PIPELINE  |  Hook Mode: Steps 0\u20139  |  Full Mode: Steps 0\u201314",
            "swimlane;startSize=26;fontStyle=1;fontSize=11;"
            "fillColor=#E1D5E7;strokeColor=#9673A6;strokeWidth=2;html=1;collapsible=0;",
        )
    )

    cur_y = L4Y + 36  # running y tracker (absolute)

    # ---- Helper to place a step node ----
    def step(x, y, w, h, label, fill="#F3EAF7", stroke="#9673A6"):
        cid = _id()
        C.append(
            box(
                x,
                y,
                w,
                h,
                label,
                "rounded=1;whiteSpace=wrap;html=1;fontSize=10;"
                "fillColor=%s;strokeColor=%s;strokeWidth=2;" % (fill, stroke),
            )
        )
        return cid

    def extern_link(node_id, sys_id, label=""):
        C.append(arrow(node_id, sys_id, label, DASHED_ARROW))

    # --- Step 0 group ---
    s_gap = 52  # vertical gap between steps

    # Row 1: Step 0.0, 0.1, Step 0
    s00_id = step(MX + 10, cur_y, 190, 42, "Step 0.0\nLoad README/CHANGELOG/AUTHORS")
    s01_id = step(MX + 215, cur_y, 190, 42, "Step 0.1\nSnapshot CallGraph (baseline)")
    s0_id = step(MX + 420, cur_y, 230, 42, "Step 0  Task Analysis\n[LLM] task_type / complexity", "#E8D5F5")
    C.append(arrow(oc_id, s00_id, "", FLOW_ARROW))
    C.append(arrow(s00_id, s01_id, "", FLOW_ARROW))
    C.append(arrow(s01_id, s0_id, "", FLOW_ARROW))
    extern_link(s01_id, cg_id, "build()")
    extern_link(s0_id, llm_id, "task_type")
    cur_y += s_gap

    # Step 1
    sh1_id = step(MX + 10, cur_y, 145, 42, "Standards Hook\n(inject L2 context)")
    s1_id = step(MX + 170, cur_y, 220, 42, "Step 1  Plan Decision\n[LLM]  plan_required?", "#E8D5F5")
    C.append(arrow(s0_id, sh1_id, "", FLOW_ARROW))
    C.append(arrow(sh1_id, s1_id, "", FLOW_ARROW))
    extern_link(s1_id, llm_id)

    d_plan_id = step(MX + 410, cur_y, 110, 42, "Plan\nRequired?", "#FFFFFF", "#9673A6")  # diamond-ish
    C.append(arrow(s1_id, d_plan_id, "", FLOW_ARROW))
    cur_y += s_gap

    # Step 2 (optional)
    s2_id = step(
        MX + 10, cur_y, 230, 42, "Step 2  Plan Execution  [optional]\n[LLM + CallGraph impact analysis]", "#E8D5F5"
    )
    C.append(arrow(d_plan_id, s2_id, "[plan=True]", FLOW_ARROW))
    extern_link(s2_id, llm_id)
    extern_link(s2_id, cg_id, "analyze_impact")
    cur_y += s_gap

    # Step 3
    s3_id = step(
        MX + 10, cur_y, 260, 42, "Step 3  Task Breakdown\n[LLM]  phases + [Figma comps if ENABLE_FIGMA]", "#E8D5F5"
    )
    C.append(arrow(s2_id, s3_id, "", FLOW_ARROW))
    # "skip plan" arrow: from d_plan_id to s3_id
    C.append(arrow(d_plan_id, s3_id, "[plan=False]", DASHED_ARROW))
    extern_link(s3_id, llm_id)
    extern_link(s3_id, figma_id, "[Figma comps]")
    cur_y += s_gap

    # Steps 4-7 removed in v1.13.0 (TOON Refinement, Skill & Agent Selection,
    # Skill Validation, Final Prompt Generation).
    # Step 3 now connects directly to Step 8.

    # Step 8
    s8_id = step(
        MX + 10, cur_y, 260, 42, "Step 8  GitHub Issue + [Jira if ENABLE_JIRA]\n(cross-linked, issue_number stored)"
    )
    C.append(arrow(s3_id, s8_id, "", FLOW_ARROW))
    extern_link(s8_id, gh_id, "create issue")
    extern_link(s8_id, jira_id, "[create + cross-link]")
    cur_y += s_gap

    # Step 9
    s9_id = step(MX + 10, cur_y, 260, 42, "Step 9  Branch Creation\n(feature/{JIRA_KEY} if Jira enabled)")
    C.append(arrow(s8_id, s9_id, "", FLOW_ARROW))
    extern_link(s9_id, git_id, "create branch")
    extern_link(s9_id, jira_id, "[key extract]")
    cur_y += s_gap

    # === HOOK MODE EXIT BANNER ===
    C.append(
        box(
            MX + 10,
            cur_y,
            MW - 20,
            28,
            "\u25b6  HOOK MODE EXIT  (CLAUDE_HOOK_MODE=1)   \u2014   Steps 10\u201314 skipped   \u2014   User reads prompts and implements code",
            "rounded=0;html=1;fillColor=#1e3a5f;fontColor=#FFFFFF;strokeColor=#1e3a5f;"
            "fontStyle=1;fontSize=10;align=center;",
        )
    )

    hook_exit_y = cur_y + 14
    C.append(
        arrow_pts(
            MX + 870,
            hook_exit_y,
            RX,
            987 + 21,
            "",
            "endArrow=open;endSize=8;html=1;strokeColor=#1e3a5f;strokeWidth=2;dashed=1;",
        )
    )
    cur_y += 36

    # === FULL MODE BANNER ===
    C.append(
        box(
            MX + 10,
            cur_y,
            MW - 20,
            28,
            "\u25bc  FULL MODE  (CLAUDE_HOOK_MODE=0)   \u2014   Steps 10\u201314 continue below",
            "rounded=0;html=1;fillColor=#4a235a;fontColor=#FFFFFF;strokeColor=#4a235a;"
            "fontStyle=1;fontSize=10;align=center;",
        )
    )
    full_entry_y = cur_y + 14
    cur_y += 36

    # Step 10
    s10_id = step(
        MX + 10,
        cur_y,
        280,
        42,
        "Step 10  Implementation\n[CallGraph snapshot]  + [Jira \u2192 In Progress]  + [Figma started]",
        "#C9B3D4",
        "#6A4080",
    )
    C.append(arrow_pts(MX + 280, full_entry_y, MX + 150, cur_y, "", FLOW_ARROW))
    C.append(arrow(s9_id, s10_id, "[Full Mode]", DASHED_ARROW))
    extern_link(s10_id, cg_id, "snapshot pre-change")
    extern_link(s10_id, jira_id, "In Progress")
    extern_link(s10_id, figma_id, "started comment")
    cur_y += s_gap

    # Step 11
    s11_id = step(
        MX + 10,
        cur_y,
        310,
        42,
        "Step 11  PR + Code Review + Merge\n[GitHub] + [CallGraph diff] + [Jenkins CI] + [Figma review]",
        "#C9B3D4",
        "#6A4080",
    )
    C.append(arrow(s10_id, s11_id, "", FLOW_ARROW))
    extern_link(s11_id, gh_id, "create PR / merge")
    extern_link(s11_id, cg_id, "compare pre/post")
    extern_link(s11_id, jenk_id, "[CI build]")
    extern_link(s11_id, jira_id, "[In Review \u2192 link PR]")
    extern_link(s11_id, figma_id, "[design review]")
    cur_y += s_gap

    # Review decision
    d_rev_id = step(MX + 10, cur_y, 150, 42, "Review\nPassed?", "#FFFFFF", "#6A4080")
    C.append(arrow(s11_id, d_rev_id, "", FLOW_ARROW))

    retry_id = step(MX + 220, cur_y, 175, 42, "Increment Retry\n(retry_count += 1 / max 3)", "#F8CECC", "#B85450")
    C.append(arrow(d_rev_id, retry_id, "[failed && <3]", OPT_ARROW))
    C.append(
        arrow(
            retry_id,
            s10_id,
            "retry \u2191",
            "endArrow=classic;endFill=1;html=1;strokeColor=#B85450;strokeWidth=1;dashed=1;"
            "exitX=1;exitY=0.5;entryX=1;entryY=0.5;edgeStyle=orthogonalEdgeStyle;",
        )
    )
    cur_y += s_gap

    # Step 12
    s12_id = step(
        MX + 10,
        cur_y,
        285,
        42,
        "Step 12  Issue Closure\n[GitHub close] + [Jira Done] + [Figma complete]",
        "#C9B3D4",
        "#6A4080",
    )
    C.append(arrow(d_rev_id, s12_id, "[passed || \u22653 retries]", FLOW_ARROW))
    extern_link(s12_id, gh_id, "close issue")
    extern_link(s12_id, jira_id, "Done transition")
    extern_link(s12_id, figma_id, "complete comment")
    cur_y += s_gap

    # Step 13
    s13_id = step(
        MX + 10,
        cur_y,
        310,
        42,
        "Step 13  Documentation Update\nCLAUDE.md / SRS / CHANGELOG + UML Mermaid + draw.io (12 types)",
        "#C9B3D4",
        "#6A4080",
    )
    C.append(arrow(s12_id, s13_id, "", FLOW_ARROW))
    extern_link(s13_id, out_md, "uml/*.md")
    extern_link(s13_id, out_dio, "drawio/*.drawio")
    cur_y += s_gap

    # Step 14
    s14_id = step(
        MX + 10, cur_y, 260, 42, "Step 14  Final Summary\n(voice notification + session close)", "#C9B3D4", "#6A4080"
    )
    C.append(arrow(s13_id, s14_id, "", FLOW_ARROW))
    extern_link(s14_id, out_log, "telemetry.jsonl")
    cur_y += s_gap

    # END terminal
    end_id = step(MX + 10, cur_y, 120, 38, "END", "#1e3a5f", "#1e3a5f")
    C.append(arrow(s14_id, end_id, "", FLOW_ARROW))
    # Also hook mode end
    C.append(arrow(s9_id, end_id, "[hook exit]", DASHED_ARROW))

    # ---- LEGEND ----
    leg_y = L4Y + L4H + 10
    C.append(
        box(
            MX,
            leg_y,
            800,
            80,
            "LEGEND",
            "swimlane;startSize=22;fontStyle=1;fontSize=10;"
            "fillColor=#FDFEFE;strokeColor=#999999;html=1;collapsible=0;",
        )
    )
    legend_items = [
        (MX + 10, leg_y + 30, "#E8D5F5", "#9673A6", "LLM eligible step"),
        (MX + 210, leg_y + 30, "#C9B3D4", "#6A4080", "Full Mode only (Steps 10-14)"),
        (MX + 430, leg_y + 30, "#F8CECC", "#B85450", "Retry / error path"),
        (MX + 10, leg_y + 55, "#D5E8D4", "#82B366", "Integration optional (ENABLE_* flag)"),
        (MX + 210, leg_y + 55, "#FFFFFF", "#999999", "Decision / routing point"),
        (MX + 430, leg_y + 55, "#DAE8FC", "#6C8EBF", "External system"),
    ]
    for lx, ly, fill, stroke, lbl in legend_items:
        C.append(box(lx, ly, 18, 18, "", "rounded=0;fillColor=%s;strokeColor=%s;" % (fill, stroke)))
        C.append(
            box(lx + 22, ly - 2, 180, 22, lbl, "text;html=1;fontSize=9;align=left;fillColor=none;strokeColor=none;")
        )

    cells.extend(C)
    return cells


# ======================================================================
# Assemble multi-page mxfile
# ======================================================================


def wrap_page(cells, page_name, page_id):
    body = "\n".join(cells)
    return (
        '  <diagram id="%s" name="%s">\n'
        '    <mxGraphModel dx="1800" dy="900" grid="1" gridSize="10" guides="1" '
        'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
        'pageWidth="1800" pageHeight="2400" math="0" shadow="0">\n'
        "      <root>\n"
        '        <mxCell id="0" />\n'
        '        <mxCell id="1" parent="0" />\n'
        "%s\n"
        "      </root>\n"
        "    </mxGraphModel>\n"
        "  </diagram>"
    ) % (page_id, page_name, body)


def generate():
    cells = build()
    page = wrap_page(cells, "System Architecture", "arch-main")

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<mxfile host="app.diagrams.net" type="diagram" version="24.0.0">\n'
        "%s\n"
        "</mxfile>"
    ) % page

    return xml


# ======================================================================
# Main
# ======================================================================

if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent.parent
    import os as _os

    _env = _os.environ.get("DRAWIO_OUTPUT_DIR", "").strip()
    out_dir = Path(_env) if (_env and Path(_env).is_absolute()) else project_root / (_env or "drawio")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "system-architecture.drawio"

    xml = generate()
    out_path.write_text(xml, encoding="utf-8")

    # Validate XML
    import xml.etree.ElementTree as ET

    tree = ET.parse(str(out_path))
    root = tree.getroot()
    cells = list(root.iter("mxCell"))
    print("Generated: %s" % out_path)
    print("File size: %d bytes" % out_path.stat().st_size)
    print("Total mxCell elements: %d" % len(cells))
    print()
    print("Shareable URL:")
    sys.path.insert(0, str(project_root / "scripts"))
    try:
        from langgraph_engine.diagrams.drawio_converter import get_shareable_url

        url = get_shareable_url(xml)
        print(url[:120] + "..." if len(url) > 120 else url)
    except Exception:
        print("(Run from project root to generate shareable URL)")

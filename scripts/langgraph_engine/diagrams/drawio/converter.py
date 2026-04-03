"""drawio/converter.py - DrawioConverter class.
Windows-safe: ASCII only.
"""

# ruff: noqa: F821

from .xml_helpers import _edge, _edge_points, _esc, _IDGen, _vertex, _vertex_child, _wrap_mxfile


class DrawioConverter:
    """Convert analysis_data dicts to professional draw.io XML.

    All 12 UML diagram types supported. Output is valid draw.io XML
    that opens in draw.io desktop, app.diagrams.net, or VS Code extension.

    Usage:
        c = DrawioConverter()
        xml = c.convert("class", analysis_data)
    """

    SUPPORTED_TYPES = [
        "class",
        "sequence",
        "activity",
        "state",
        "component",
        "package",
        "deployment",
        "usecase",
        "object",
        "communication",
        "composite",
        "interaction",
    ]

    def convert(self, diagram_type, analysis_data):
        """Convert analysis_data to professional draw.io XML.

        Args:
            diagram_type: One of SUPPORTED_TYPES.
            analysis_data: Dict from AST/CallGraph analyzer.

        Returns:
            draw.io XML string. Save as .drawio file.
        """
        nid = _IDGen()
        data = analysis_data or {}

        _generators = {
            "class": self._class_diagram,
            "sequence": self._sequence_diagram,
            "activity": self._activity_diagram,
            "state": self._state_diagram,
            "component": self._component_diagram,
            "package": self._package_diagram,
            "deployment": self._deployment_diagram,
            "usecase": self._usecase_diagram,
            "object": self._object_diagram,
            "communication": self._communication_diagram,
            "composite": self._composite_diagram,
            "interaction": self._interaction_diagram,
        }

        gen = _generators.get(diagram_type, self._generic_diagram)
        try:
            cells = gen(data, nid)
        except Exception as exc:
            logger.warning("DrawioConverter[%s]: %s", diagram_type, exc, exc_info=True)
            cells = [_vertex(nid(), "Error: %s" % exc, S_ACT_ACTION, 100, 100, 400, 50)]

        title = diagram_type.replace("-", " ").title() + " Diagram"
        return _wrap_mxfile(cells, title)

    # ------------------------------------------------------------------
    # 1. CLASS DIAGRAM
    # ------------------------------------------------------------------
    # Layout: Grid (max 4 columns), 3-section boxes with dividers.
    # Relationships: inheritance (hollow triangle), composition (filled diamond),
    #                aggregation (open diamond), association (open arrow).

    def _class_diagram(self, data, nid):
        classes = data.get("classes") or []
        cells = []

        # Layout constants
        MAX_COLS = 4
        BOX_W = 220  # class box width
        HDR_H = 26  # swimlane header height
        ROW_H = 20  # per-attribute/method row height
        DIV_H = 8  # divider height
        MIN_SEC = 24  # minimum section height (empty section)
        GAP_X = 70  # horizontal gap
        GAP_Y = 80  # vertical gap
        ORIGIN_X = 40
        ORIGIN_Y = 40

        id_map = {}  # class name -> cell id

        for idx, cls in enumerate(classes[:40]):
            name = cls.get("name", "Class%d" % idx)
            attrs = cls.get("attributes", [])[:10]
            meths = cls.get("methods", [])[:12]
            cls.get("bases", [])
            is_iface = cls.get("is_interface", "interface" in name.lower())
            is_abst = cls.get("is_abstract", False)

            attr_h = max(len(attrs) * ROW_H, MIN_SEC) + 4
            meth_h = max(len(meths) * ROW_H, MIN_SEC) + 4
            total_h = HDR_H + attr_h + DIV_H + meth_h

            col = idx % MAX_COLS
            row = idx // MAX_COLS
            x = ORIGIN_X + col * (BOX_W + GAP_X)
            y = ORIGIN_Y + row * (total_h + GAP_Y)

            # Choose header style
            if is_iface:
                hdr_style = S_IFACE_HDR
                label = "&lt;&lt;interface&gt;&gt;&#xa;" + name
            elif is_abst:
                hdr_style = S_ABST_HDR
                label = "&lt;&lt;abstract&gt;&gt;&#xa;" + name
            else:
                hdr_style = S_CLASS_HDR
                label = name

            cid = nid()
            id_map[name] = cid

            # Container (swimlane = class box)
            cells.append(_vertex(cid, label, hdr_style, x, y, BOX_W, total_h))

            # Attributes section (child of container)
            attr_lines = []
            for a in attrs:
                vis = a.get("visibility", "+")
                hint = a.get("type_hint", "")
                t = (": " + hint) if hint else ""
                attr_lines.append("%s %s%s" % (vis, a["name"], t))
            attr_text = "&#xa;".join(attr_lines) if attr_lines else " "
            cells.append(_vertex_child(nid(), attr_text, S_CLASS_ROW, 0, HDR_H, BOX_W, attr_h, cid))

            # Divider between attributes and methods
            cells.append(_vertex_child(nid(), "", S_CLASS_DIV, 0, HDR_H + attr_h, BOX_W, DIV_H, cid))

            # Methods section
            meth_lines = []
            for m in meths:
                vis = m.get("visibility", "+")
                params = ", ".join(m.get("params", [])[:4])
                ret = (": " + m["return_type"]) if m.get("return_type") else ""
                meth_lines.append("%s %s(%s)%s" % (vis, m["name"], params, ret))
            meth_text = "&#xa;".join(meth_lines) if meth_lines else " "
            cells.append(_vertex_child(nid(), meth_text, S_CLASS_ROW, 0, HDR_H + attr_h + DIV_H, BOX_W, meth_h, cid))

        # Relationships
        for cls in classes[:40]:
            src_id = id_map.get(cls.get("name", ""))
            if not src_id:
                continue
            # Inheritance
            for base in cls.get("bases", [])[:3]:
                tgt_id = id_map.get(base)
                if tgt_id:
                    cells.append(_edge(nid(), "", S_INHERIT, src_id, tgt_id))
            # Explicit relationships list
            for rel in cls.get("relationships", [])[:4]:
                tgt_id = id_map.get(rel.get("target", ""))
                if not tgt_id:
                    continue
                rtype = rel.get("type", "associate").lower()
                if rtype == "compose":
                    cells.append(_edge(nid(), "", S_COMPOSE, src_id, tgt_id))
                elif rtype == "aggregate":
                    cells.append(_edge(nid(), "", S_AGGREGATE, src_id, tgt_id))
                elif rtype == "realize":
                    cells.append(_edge(nid(), "", S_REALIZE, src_id, tgt_id))
                elif rtype == "depend":
                    cells.append(_edge(nid(), "", S_DEPEND, src_id, tgt_id))
                else:
                    cells.append(_edge(nid(), "", S_ASSOCIATE, src_id, tgt_id))

        if not cells:
            cells.append(_vertex(nid(), "No classes found", S_ACT_ACTION, 100, 100, 200, 50))

        return cells

    # ------------------------------------------------------------------
    # 2. SEQUENCE DIAGRAM
    # ------------------------------------------------------------------
    # Layout: Participants across top. mxgraph.uml.lifeline cells span
    # the full diagram height (participant box + dashed line in one shape).
    # Messages are point-to-point edges at specific Y coordinates.

    def _sequence_diagram(self, data, nid):
        cells = []
        call_chains = data.get("call_chains") or []
        participants = data.get("participants") or []

        # Derive participants from call_chains if not explicit
        if not participants and call_chains:
            seen = []
            for chain in call_chains[:25]:
                for key in ("caller", "from", "source"):
                    p = chain.get(key, "")
                    if p and p not in seen:
                        seen.append(p)
                        break
                for key in ("callee", "to", "target"):
                    p = chain.get(key, "")
                    if p and p not in seen:
                        seen.append(p)
                        break
            participants = seen[:10]

        if not participants:
            participants = ["Client", "Service", "Repository", "Database"]

        MAX_PARTS = 8
        participants = participants[:MAX_PARTS]

        PART_W = 140  # lifeline cell width
        PART_HDR = 40  # participant box height (startSize)
        GAP_X = 80  # gap between lifeline centers
        MSG_GAP = 60  # vertical gap between messages
        MARGIN_Y = 20  # top margin
        MSGS_TOP = MARGIN_Y + PART_HDR + 40  # Y where first message starts
        N_MSGS = max(len(call_chains), 3)
        LIFE_H = MSGS_TOP + N_MSGS * MSG_GAP + 80  # total lifeline height

        # X centers for each participant
        centers = []
        for i in range(len(participants)):
            cx = 60 + i * (PART_W + GAP_X) + PART_W // 2
            centers.append(cx)

        # Lifeline cells (participant box + dashed line)
        part_ids = {}
        for i, p in enumerate(participants):
            lid = nid()
            part_ids[p] = lid
            px = 60 + i * (PART_W + GAP_X)
            cells.append(_vertex(lid, p, S_LIFELINE, px, MARGIN_Y, PART_W, LIFE_H))

        # Messages (point-to-point edges at explicit Y positions)
        for j, chain in enumerate(call_chains[:25]):
            msg_y = MSGS_TOP + j * MSG_GAP

            # Caller
            src_name = ""
            for key in ("caller", "from", "source"):
                src_name = chain.get(key, "")
                if src_name:
                    break
            # Callee
            tgt_name = ""
            for key in ("callee", "to", "target"):
                tgt_name = chain.get(key, "")
                if tgt_name:
                    break
            # Label
            label = chain.get("method", chain.get("label", chain.get("message", "")))

            # Determine style
            is_return = chain.get("is_return", False)
            is_async = chain.get("is_async", False)
            if is_return:
                style = S_MSG_RETURN
            elif is_async:
                style = S_MSG_ASYNC
            else:
                style = S_MSG_SYNC

            # Self-message
            if src_name == tgt_name:
                src_idx = participants.index(src_name) if src_name in participants else 0
                sx = centers[src_idx]
                sy = msg_y
                # Self-loop via waypoints
                cid = nid()
                cells.append(
                    '    <mxCell id="%s" value="%s" style="%s" edge="1" parent="1">\n'
                    '      <mxGeometry relative="1" as="geometry">\n'
                    '        <mxPoint x="%s" y="%s" as="sourcePoint" />\n'
                    '        <mxPoint x="%s" y="%s" as="targetPoint" />\n'
                    '        <Array as="points">\n'
                    '          <mxPoint x="%s" y="%s" />\n'
                    '          <mxPoint x="%s" y="%s" />\n'
                    "        </Array>\n"
                    "      </mxGeometry>\n"
                    "    </mxCell>" % (cid, _esc(label), style, sx, sy, sx, sy + 30, sx + 80, sy, sx + 80, sy + 30)
                )
                continue

            # Cross-participant message
            src_idx = participants.index(src_name) if src_name in participants else -1
            tgt_idx = participants.index(tgt_name) if tgt_name in participants else -1
            if src_idx == -1 or tgt_idx == -1:
                continue

            sx = centers[src_idx]
            tx = centers[tgt_idx]
            cells.append(_edge_points(nid(), label, style, sx, msg_y, tx, msg_y))

        if not call_chains:
            # Show placeholder messages
            for j, (src, tgt, msg) in enumerate(
                [
                    (
                        (participants[0], participants[1], "request()")
                        if len(participants) > 1
                        else (participants[0], participants[0], "self()")
                    ),
                    (participants[-1], participants[0], "response()"),
                ]
            ):
                msg_y = MSGS_TOP + j * MSG_GAP
                s_idx = participants.index(src) if src in participants else 0
                t_idx = participants.index(tgt) if tgt in participants else 0
                sx, tx = centers[s_idx], centers[t_idx]
                st = S_MSG_SYNC if j == 0 else S_MSG_RETURN
                cells.append(_edge_points(nid(), msg, st, sx, msg_y, tx, msg_y))

        return cells

    # ------------------------------------------------------------------
    # 3. ACTIVITY DIAGRAM
    # ------------------------------------------------------------------
    # Top-to-bottom flow. Initial (filled circle) -> Actions (rounded rect)
    # -> Decisions (diamond) -> Fork/Join (black bar) -> Final (doubleEllipse).

    def _activity_diagram(self, data, nid):
        cells = []
        steps = data.get("steps") or data.get("activities") or []

        # Derive steps from class methods if none provided
        if not steps:
            for cls in (data.get("classes") or [])[:3]:
                for m in cls.get("methods", [])[:6]:
                    steps.append({"name": m.get("name", "action"), "type": "action"})

        if not steps:
            steps = [
                {"name": "Receive Request", "type": "action"},
                {"name": "Validate Input", "type": "decision"},
                {"name": "Process Business Logic", "type": "action"},
                {"name": "Persist to DB", "type": "action"},
                {"name": "Send Response", "type": "action"},
            ]

        CX = 420  # center X
        AW, AH = 200, 50  # action width, height
        DW, DH = 80, 80  # decision diamond
        FW, FH = 140, 10  # fork/join bar
        GAP = 40
        START_Y = 30

        # Initial node
        init_id = nid()
        cells.append(_vertex(init_id, "", S_ACT_INIT, CX - 15, START_Y, 30, 30))

        prev_id = init_id
        y = START_Y + 30 + GAP
        node_ids = []

        for step in steps[:15]:
            sname = step.get("name", str(step)) if isinstance(step, dict) else str(step)
            stype = step.get("type", "action") if isinstance(step, dict) else "action"

            if stype in ("decision", "condition", "check"):
                cid = nid()
                cells.append(_vertex(cid, sname, S_ACT_DIAMOND, CX - DW // 2, y, DW, DH))
                cells.append(_edge(nid(), "", S_ACT_ARROW, prev_id, cid))
                # Yes branch (continues down), No branch (to the right)
                yes_y = y + DH + GAP
                yes_id = nid()
                cells.append(
                    _vertex(yes_id, "[yes] " + sname.split()[-1] + " ok", S_ACT_ACTION, CX - AW // 2, yes_y, AW, AH)
                )
                cells.append(_edge(nid(), "[yes]", S_ACT_ARROW, cid, yes_id))
                node_ids.append(yes_id)
                prev_id = yes_id
                y = yes_y + AH + GAP
            elif stype in ("fork", "join"):
                fid = nid()
                cells.append(_vertex(fid, "", S_ACT_FORK, CX - FW // 2, y, FW, FH))
                cells.append(_edge(nid(), "", S_ACT_ARROW, prev_id, fid))
                prev_id = fid
                y += FH + GAP
            else:
                cid = nid()
                cells.append(_vertex(cid, sname, S_ACT_ACTION, CX - AW // 2, y, AW, AH))
                cells.append(_edge(nid(), "", S_ACT_ARROW, prev_id, cid))
                node_ids.append(cid)
                prev_id = cid
                y += AH + GAP

        # Final node
        fin_id = nid()
        cells.append(_vertex(fin_id, "", S_ACT_FINAL, CX - 15, y, 30, 30))
        cells.append(_edge(nid(), "", S_ACT_ARROW, prev_id, fin_id))

        return cells

    # ------------------------------------------------------------------
    # 4. STATE DIAGRAM
    # ------------------------------------------------------------------
    # States (rounded rect, green) + transitions (arrows with guard labels).
    # Initial pseudostate (black circle) + Final state (double ellipse).

    def _state_diagram(self, data, nid):
        cells = []
        states = data.get("states") or []
        transitions = data.get("transitions") or []

        if not states:
            states = ["Idle", "Running", "Paused", "Error", "Completed"]
            transitions = [
                ("Idle", "Running", "start()"),
                ("Running", "Paused", "pause()"),
                ("Paused", "Running", "resume()"),
                ("Running", "Completed", "finish()"),
                ("Running", "Error", "fail()"),
                ("Error", "Idle", "reset()"),
            ]

        MAX_COLS = 3
        SW, SH = 160, 60
        GAP_X = 80
        GAP_Y = 80
        OX, OY = 40, 100

        # Initial pseudostate
        init_id = nid()
        cells.append(_vertex(init_id, "", S_ST_INIT, OX + SW // 2 - 12, 20, 24, 24))

        state_ids = {}
        for idx, s in enumerate(states[:18]):
            sname = s if isinstance(s, str) else s.get("name", str(s))
            is_comp = isinstance(s, dict) and s.get("is_composite", False)

            col = idx % MAX_COLS
            row = idx // MAX_COLS
            x = OX + col * (SW + GAP_X)
            y = OY + row * (SH + GAP_Y)

            sid = nid()
            state_ids[sname] = sid

            if is_comp:
                sub_states = s.get("sub_states", [])
                comp_h = max(SH, 30 + len(sub_states) * 50)
                cells.append(_vertex(sid, sname, S_ST_COMP, x, y, SW, comp_h))
                for k, ss in enumerate(sub_states[:4]):
                    ss_id = nid()
                    ssname = ss if isinstance(ss, str) else ss.get("name", str(ss))
                    cells.append(_vertex_child(ss_id, ssname, S_ST_BOX, 10, 36 + k * 52, SW - 20, 44, sid))
            else:
                cells.append(_vertex(sid, sname, S_ST_BOX, x, y, SW, SH))

        # Arrow from initial to first state
        if state_ids:
            first = list(state_ids.values())[0]
            cells.append(_edge(nid(), "", S_ST_ARROW, init_id, first))

        # Transitions
        for t in transitions[:30]:
            if isinstance(t, (list, tuple)) and len(t) >= 2:
                src_n, tgt_n = str(t[0]), str(t[1])
                label = str(t[2]) if len(t) > 2 else ""
            elif isinstance(t, dict):
                src_n = t.get("from", t.get("source", ""))
                tgt_n = t.get("to", t.get("target", ""))
                label = t.get("label", t.get("event", t.get("guard", "")))
            else:
                continue

            src_id = state_ids.get(src_n)
            tgt_id = state_ids.get(tgt_n)
            if not (src_id and tgt_id):
                continue

            style = S_ST_SELF if src_id == tgt_id else S_ST_ARROW
            cells.append(_edge(nid(), label, style, src_id, tgt_id))

        # Final state
        if state_ids:
            last = list(state_ids.values())[-1]
            last_col = (len(states) - 1) % MAX_COLS
            last_row = (len(states) - 1) // MAX_COLS
            fx = OX + last_col * (SW + GAP_X) + SW + 40
            fy = OY + last_row * (SH + GAP_Y) + SH // 2 - 15
            fin_id = nid()
            cells.append(_vertex(fin_id, "", S_ST_FINAL, fx, fy, 30, 30))
            cells.append(_edge(nid(), "", S_ST_ARROW, last, fin_id))

        return cells

    # ------------------------------------------------------------------
    # 5. COMPONENT DIAGRAM
    # ------------------------------------------------------------------
    # Components (mxgraph.uml.component) + dependency arrows.
    # Optional provided (lollipop) and required (socket) interfaces.

    def _component_diagram(self, data, nid):
        cells = []
        components = data.get("components") or []

        # Derive from class modules
        if not components:
            seen = {}
            for cls in (data.get("classes") or [])[:30]:
                mod = cls.get("module", cls.get("file", "Unknown"))
                top = str(mod).replace("\\", "/").split("/")[0]
                if top not in seen:
                    seen[top] = {"name": top, "provides": [], "requires": []}
                seen[top]["provides"].append(cls["name"])
            components = list(seen.values())[:12]

        if not components:
            components = [
                {"name": "Frontend", "provides": ["UIService"], "requires": ["APIService"]},
                {"name": "API", "provides": ["APIService"], "requires": ["DataService"]},
                {"name": "DataLayer", "provides": ["DataService"], "requires": []},
            ]

        MAX_COLS = 3
        CW, CH = 200, 120
        GAP_X = 80
        GAP_Y = 80

        comp_ids = {}

        for i, comp in enumerate(components[:15]):
            name = comp.get("name", str(comp)) if isinstance(comp, dict) else str(comp)
            provides = comp.get("provides", []) if isinstance(comp, dict) else []
            label = (
                "&lt;&lt;component&gt;&gt;&#xa;"
                + name
                + (("&#xa;" + "&#xa;".join(str(p) for p in provides[:3])) if provides else "")
            )
            col = i % MAX_COLS
            row = i // MAX_COLS
            x = 40 + col * (CW + GAP_X)
            y = 40 + row * (CH + GAP_Y)
            cid = nid()
            comp_ids[name] = cid
            cells.append(_vertex(cid, label, S_COMP_BOX, x, y, CW, CH))

            # Provided interfaces (lollipop on right side)
            for k, prov in enumerate(provides[:2]):
                pid = nid()
                cells.append(_vertex(pid, prov, S_COMP_PROV, x + CW + 5, y + 20 + k * 40, 20, 20))

        # Dependencies
        for dep in (data.get("dependencies") or [])[:20]:
            if isinstance(dep, (list, tuple)) and len(dep) >= 2:
                src_n, tgt_n = str(dep[0]), str(dep[1])
                label = str(dep[2]) if len(dep) > 2 else "uses"
            elif isinstance(dep, dict):
                src_n = dep.get("from", dep.get("source", ""))
                tgt_n = dep.get("to", dep.get("target", ""))
                label = dep.get("label", "uses")
            else:
                continue
            src_id = comp_ids.get(src_n)
            tgt_id = comp_ids.get(tgt_n)
            if src_id and tgt_id:
                cells.append(_edge(nid(), label, S_COMP_DEP, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 6. PACKAGE DIAGRAM
    # ------------------------------------------------------------------
    # Packages (shape=folder) + import/access arrows.

    def _package_diagram(self, data, nid):
        cells = []
        packages = data.get("packages") or []

        if not packages:
            seen = {}
            for cls in (data.get("classes") or [])[:30]:
                mod = cls.get("module", cls.get("file", "Unknown"))
                top = str(mod).replace("\\", "/").split("/")[0]
                top2 = str(mod).replace("\\", "/").split("/")[1] if "/" in str(mod) else top
                if top not in seen:
                    seen[top] = {"name": top, "sub": set()}
                seen[top]["sub"].add(top2)
            packages = [{"name": k, "contents": list(v["sub"])[:5]} for k, v in seen.items()]

        if not packages:
            packages = [
                {"name": "core", "contents": ["Orchestrator", "PipelineBuilder"]},
                {"name": "diagrams", "contents": ["DiagramFactory", "ClassDiagram"]},
                {"name": "integrations", "contents": ["GitHub", "Jira"]},
                {"name": "mcp", "contents": ["DrawioServer", "UMLServer"]},
            ]

        MAX_COLS = 3
        PW, PH = 200, 120
        GAP_X = 80
        GAP_Y = 80
        pkg_ids = {}

        for i, pkg in enumerate(packages[:18]):
            name = pkg.get("name", str(pkg)) if isinstance(pkg, dict) else str(pkg)
            contents = pkg.get("contents", []) if isinstance(pkg, dict) else []
            label = name + (("&#xa;" + "&#xa;".join(str(c) for c in contents[:4])) if contents else "")
            col = i % MAX_COLS
            row = i // MAX_COLS
            x = 40 + col * (PW + GAP_X)
            y = 40 + row * (PH + GAP_Y)
            pid = nid()
            pkg_ids[name] = pid
            cells.append(_vertex(pid, label, S_PKG_BOX, x, y, PW, PH))

        # Import relationships
        for imp in (data.get("imports") or data.get("dependencies") or [])[:25]:
            if isinstance(imp, (list, tuple)) and len(imp) >= 2:
                src_n, tgt_n = str(imp[0]), str(imp[1])
                label = str(imp[2]) if len(imp) > 2 else "&lt;&lt;import&gt;&gt;"
            elif isinstance(imp, dict):
                src_n = imp.get("from", "")
                tgt_n = imp.get("to", imp.get("import", ""))
                label = imp.get("label", "&lt;&lt;import&gt;&gt;")
            else:
                continue
            src_id = pkg_ids.get(src_n)
            tgt_id = pkg_ids.get(tgt_n)
            if src_id and tgt_id:
                cells.append(_edge(nid(), label, S_PKG_IMPORT, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 7. DEPLOYMENT DIAGRAM
    # ------------------------------------------------------------------
    # Nodes (shape=cube, 3D box), artifacts inside nodes, connections.

    def _deployment_diagram(self, data, nid):
        cells = []
        nodes = data.get("nodes") or data.get("deployments") or []

        if not nodes:
            nodes = [
                {"name": "Web Server", "type": "server", "artifacts": ["nginx:80", "Frontend App"]},
                {"name": "Application Server", "type": "server", "artifacts": ["Python API", "Worker Process"]},
                {"name": "Database Server", "type": "database", "artifacts": ["PostgreSQL:5432", "Redis:6379"]},
            ]

        MAX_COLS = 3
        NW = 240
        HDR_H = 60  # node header (cube label zone)
        ART_H = 32  # artifact height
        ART_GAP = 6
        GAP_X = 80
        GAP_Y = 80
        node_ids = {}

        for i, node in enumerate(nodes[:12]):
            name = node.get("name", str(node)) if isinstance(node, dict) else str(node)
            artifacts = node.get("artifacts", []) if isinstance(node, dict) else []
            ntype = node.get("type", "server") if isinstance(node, dict) else "server"
            total_h = HDR_H + len(artifacts) * (ART_H + ART_GAP) + 20
            col = i % MAX_COLS
            row = i // MAX_COLS
            x = 40 + col * (NW + GAP_X)
            y = 40 + row * (total_h + GAP_Y)

            nid_ = nid()
            node_ids[name] = nid_
            label = "&lt;&lt;%s&gt;&gt;&#xa;%s" % (ntype, name)
            style = S_DEP_DEVICE if ntype == "database" else S_DEP_NODE
            cells.append(_vertex(nid_, label, style, x, y, NW, total_h))

            # Artifacts inside node
            for j, art in enumerate(artifacts[:6]):
                art_y = HDR_H + j * (ART_H + ART_GAP)
                cells.append(_vertex_child(nid(), str(art), S_DEP_COMP, 10, art_y, NW - 20, ART_H, nid_))

        # Connections between nodes
        for conn in (data.get("connections") or data.get("links") or [])[:15]:
            if isinstance(conn, (list, tuple)) and len(conn) >= 2:
                src_n, tgt_n = str(conn[0]), str(conn[1])
                label = str(conn[2]) if len(conn) > 2 else ""
            elif isinstance(conn, dict):
                src_n = conn.get("from", conn.get("source", ""))
                tgt_n = conn.get("to", conn.get("target", ""))
                label = conn.get("protocol", conn.get("label", ""))
            else:
                continue
            src_id = node_ids.get(src_n)
            tgt_id = node_ids.get(tgt_n)
            if src_id and tgt_id:
                cells.append(_edge(nid(), label, S_DEP_CONN, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 8. USE CASE DIAGRAM
    # ------------------------------------------------------------------
    # System boundary (rectangle) with use cases (ellipses) inside.
    # Actors (mxgraph.uml.actor) outside on left.

    def _usecase_diagram(self, data, nid):
        cells = []
        actors = data.get("actors") or ["User", "Admin"]
        use_cases = data.get("use_cases") or data.get("usecases") or []
        system_name = data.get("system_name", "System")
        assocs = data.get("associations") or []

        if not use_cases:
            use_cases = [
                "Login",
                "View Dashboard",
                "Create Record",
                "Edit Record",
                "Delete Record",
                "Generate Report",
                "Manage Users",
                "Configure Settings",
            ]

        MAX_UCS = 14
        use_cases = use_cases[:MAX_UCS]
        N_UC = len(use_cases)

        # System boundary box
        UCW, UCH_UNIT = 200, 60  # use case ellipse
        UC_GAP = 20
        SYS_MARGIN = 30
        SYS_HDR = 36

        sys_w = UCW + 2 * SYS_MARGIN
        sys_h = SYS_HDR + N_UC * (UCH_UNIT + UC_GAP) + SYS_MARGIN
        sys_x = 160
        sys_y = 20

        sys_id = nid()
        cells.append(_vertex(sys_id, system_name, S_UC_SYSTEM, sys_x, sys_y, sys_w, sys_h))

        # Use cases (inside system)
        uc_ids = {}
        for j, uc in enumerate(use_cases):
            ucname = uc if isinstance(uc, str) else uc.get("name", str(uc))
            ucx = SYS_MARGIN
            ucy = SYS_HDR + j * (UCH_UNIT + UC_GAP)
            ucid = nid()
            uc_ids[ucname] = ucid
            cells.append(_vertex_child(ucid, ucname, S_UC_CASE, ucx, ucy, UCW, UCH_UNIT, sys_id))

        # Actors (outside system, left side)
        ACTOR_W, ACTOR_H = 50, 90
        actor_ids = {}
        for k, actor in enumerate(actors[:6]):
            aname = actor if isinstance(actor, str) else actor.get("name", str(actor))
            ax = sys_x - ACTOR_W - 50
            ay = sys_y + k * 130 + 50
            aid = nid()
            actor_ids[aname] = aid
            cells.append(_vertex(aid, aname, S_UC_ACTOR, ax, ay, ACTOR_W, ACTOR_H))

        # Associations (actor -> use case)
        if assocs:
            for assoc in assocs[:30]:
                if isinstance(assoc, (list, tuple)) and len(assoc) >= 2:
                    a_name, uc_name = str(assoc[0]), str(assoc[1])
                    label = str(assoc[2]) if len(assoc) > 2 else ""
                elif isinstance(assoc, dict):
                    a_name = assoc.get("actor", "")
                    uc_name = assoc.get("use_case", assoc.get("usecase", ""))
                    label = assoc.get("label", "")
                else:
                    continue
                aid = actor_ids.get(a_name)
                ucid = uc_ids.get(uc_name)
                if aid and ucid:
                    cells.append(_edge(nid(), label, S_UC_ASSOC, aid, ucid))
        else:
            # Default: first actor connects to first 4 use cases
            if actor_ids and uc_ids:
                first_actor = list(actor_ids.values())[0]
                for ucid in list(uc_ids.values())[:4]:
                    cells.append(_edge(nid(), "", S_UC_ASSOC, first_actor, ucid))

        # Include / Extend relationships
        for rel in (data.get("relationships") or [])[:15]:
            if isinstance(rel, dict):
                src_n = rel.get("from", "")
                tgt_n = rel.get("to", "")
                rtype = rel.get("type", "include").lower()
                label = "&lt;&lt;%s&gt;&gt;" % rtype
                src_id = uc_ids.get(src_n)
                tgt_id = uc_ids.get(tgt_n)
                if src_id and tgt_id:
                    style = S_UC_EXTEND if rtype == "extend" else S_UC_INCL
                    cells.append(_edge(nid(), label, style, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 9. OBJECT DIAGRAM
    # ------------------------------------------------------------------
    # Like class diagram but underlined names and attribute=value format.

    def _object_diagram(self, data, nid):
        cells = []
        objects = data.get("objects") or data.get("instances") or []

        if not objects:
            for cls in (data.get("classes") or [])[:4]:
                obj = {
                    "name": cls["name"][0].lower() + cls["name"][1:] + "1",
                    "class": cls["name"],
                    "values": {a["name"]: '"example"' for a in cls.get("attributes", [])[:4]},
                }
                objects.append(obj)

        if not objects:
            objects = [
                {"name": "obj1", "class": "MyClass", "values": {"id": "1", "name": '"test"', "active": "true"}},
                {"name": "obj2", "class": "MyClass", "values": {"id": "2", "name": '"prod"', "active": "false"}},
            ]

        MAX_COLS = 3
        OW = 220
        HDR_H = 26
        ROW_H = 22
        DIV_H = 8
        GAP_X = 80
        GAP_Y = 80
        obj_ids = {}

        for i, obj in enumerate(objects[:20]):
            oname = obj.get("name", "obj%d" % i) if isinstance(obj, dict) else str(obj)
            oclss = obj.get("class", "") if isinstance(obj, dict) else ""
            values = obj.get("values", {}) if isinstance(obj, dict) else {}

            n_vals = len(values)
            val_h = max(n_vals * ROW_H, ROW_H) + 4
            total_h = HDR_H + DIV_H + val_h

            col = i % MAX_COLS
            row = i // MAX_COLS
            x = 40 + col * (OW + GAP_X)
            y = 40 + row * (total_h + GAP_Y)

            oid = nid()
            obj_ids[oname] = oid
            header = ("%s : %s" % (oname, oclss)) if oclss else oname
            cells.append(_vertex(oid, header, S_OBJ_HDR, x, y, OW, total_h))
            cells.append(_vertex_child(nid(), "", S_OBJ_DIV, 0, HDR_H, OW, DIV_H, oid))
            if values:
                val_lines = "&#xa;".join("%s = %s" % (k, v) for k, v in list(values.items())[:8])
                cells.append(_vertex_child(nid(), val_lines, S_OBJ_ROW, 0, HDR_H + DIV_H, OW, val_h, oid))

        # Links between objects
        for link in (data.get("links") or [])[:15]:
            if isinstance(link, (list, tuple)) and len(link) >= 2:
                src_n, tgt_n = str(link[0]), str(link[1])
                label = str(link[2]) if len(link) > 2 else ""
            elif isinstance(link, dict):
                src_n = link.get("from", "")
                tgt_n = link.get("to", "")
                label = link.get("label", "")
            else:
                continue
            src_id = obj_ids.get(src_n)
            tgt_id = obj_ids.get(tgt_n)
            if src_id and tgt_id:
                cells.append(_edge(nid(), label, S_OBJ_LINK, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 10. COMMUNICATION DIAGRAM
    # ------------------------------------------------------------------
    # Objects in circular/network layout. Numbered messages on edges.

    def _communication_diagram(self, data, nid):
        import math

        cells = []
        participants = data.get("participants") or []
        messages = data.get("messages") or data.get("call_chains") or []

        if not participants:
            for cls in (data.get("classes") or [])[:8]:
                participants.append(cls["name"])
        if not participants:
            participants = ["Client", "Controller", "Service", "Repository", "Database"]

        OW, OH = 140, 50
        N = min(len(participants), 8)
        R = max(200, N * 55)
        CX, CY = 420, 350
        part_ids = {}

        for i, p in enumerate(participants[:8]):
            pname = p if isinstance(p, str) else p.get("name", str(p))
            angle = (2 * math.pi * i / N) - math.pi / 2
            x = int(CX + R * math.cos(angle) - OW / 2)
            y = int(CY + R * math.sin(angle) - OH / 2)
            pid = nid()
            part_ids[pname] = pid
            cells.append(_vertex(pid, pname, S_COMM_OBJ, x, y, OW, OH))

        for j, msg in enumerate(messages[:15]):
            if isinstance(msg, (list, tuple)) and len(msg) >= 2:
                src_n, tgt_n = str(msg[0]), str(msg[1])
                label = str(msg[2]) if len(msg) > 2 else ""
            elif isinstance(msg, dict):
                src_n = msg.get("caller", msg.get("from", ""))
                tgt_n = msg.get("callee", msg.get("to", ""))
                label = msg.get("method", msg.get("label", ""))
            else:
                continue
            src_id = part_ids.get(src_n)
            tgt_id = part_ids.get(tgt_n)
            if src_id and tgt_id:
                cells.append(_edge(nid(), "%d: %s" % (j + 1, label), S_COMM_MSG, src_id, tgt_id))

        return cells

    # ------------------------------------------------------------------
    # 11. COMPOSITE STRUCTURE DIAGRAM
    # ------------------------------------------------------------------
    # Classes with internal parts and ports.

    def _composite_diagram(self, data, nid):
        cells = []
        components = data.get("components") or []

        if not components:
            for cls in (data.get("classes") or [])[:4]:
                components.append(
                    {
                        "name": cls["name"],
                        "parts": [m["name"] for m in cls.get("methods", [])[:4]],
                        "ports": cls.get("interfaces", [cls["name"] + "Port"]),
                    }
                )

        if not components:
            components = [
                {"name": "OrderService", "parts": ["OrderValidator", "PriceCalculator"], "ports": ["IOrderService"]},
                {"name": "PaymentService", "parts": ["PaymentGateway", "FraudDetector"], "ports": ["IPaymentService"]},
            ]

        COLS = 2
        CW = 280
        CH = 180
        GAP_X = 100
        GAP_Y = 80

        for i, comp in enumerate(components[:8]):
            name = comp.get("name", str(comp)) if isinstance(comp, dict) else str(comp)
            parts = comp.get("parts", []) if isinstance(comp, dict) else []
            ports = comp.get("ports", []) if isinstance(comp, dict) else []
            col = i % COLS
            row = i // COLS
            x = 40 + col * (CW + GAP_X)
            y = 40 + row * (CH + GAP_Y)

            cid = nid()
            cells.append(_vertex(cid, name, S_CS_CLASS, x, y, CW, CH))

            # Internal parts
            for k, part in enumerate(parts[:4]):
                pw = (CW - 30) // 2
                ph = 36
                pcol = k % 2
                prow = k // 2
                px = 10 + pcol * (pw + 10)
                py = 36 + prow * (ph + 10)
                cells.append(_vertex_child(nid(), str(part), S_CS_PART, px, py, pw, ph, cid))

            # Ports (small squares on the border)
            for m, port in enumerate(ports[:3]):
                pox = -6
                poy = 30 + m * 40
                cells.append(_vertex_child(nid(), "", S_CS_PORT, pox, poy, 12, 12, cid))
                # Port label
                cells.append(_vertex(nid(), str(port), S_OBJ_ROW, x - 80, y + 30 + m * 40, 75, 20))

        return cells

    # ------------------------------------------------------------------
    # 12. INTERACTION OVERVIEW DIAGRAM
    # ------------------------------------------------------------------
    # Activity-style diagram where nodes are interaction references (ref frames).

    def _interaction_diagram(self, data, nid):
        cells = []
        steps = data.get("steps") or data.get("interactions") or []

        if not steps:
            steps = [
                {"type": "init"},
                {"type": "ref", "name": "Authentication Flow"},
                {"type": "decision", "label": "Auth OK?"},
                {"type": "ref", "name": "Main Business Flow"},
                {"type": "ref", "name": "Error Handling"},
                {"type": "end"},
            ]

        CX = 440
        RW = 260  # ref frame width
        RH = 60  # ref frame height
        DW = 80  # decision diamond
        DH = 80
        GAP = 40
        y = 30
        prev = None

        for step in steps[:15]:
            stype = step.get("type", "ref") if isinstance(step, dict) else "ref"
            sname = step.get("name", step.get("label", "")) if isinstance(step, dict) else str(step)

            if stype in ("init", "start"):
                sid = nid()
                cells.append(_vertex(sid, "", S_IO_INIT, CX - 15, y, 30, 30))
                if prev:
                    cells.append(_edge(nid(), "", S_IO_ARROW, prev, sid))
                prev = sid
                y += 30 + GAP

            elif stype in ("end", "final"):
                eid = nid()
                cells.append(_vertex(eid, "", S_IO_FINAL, CX - 15, y, 30, 30))
                if prev:
                    cells.append(_edge(nid(), "", S_IO_ARROW, prev, eid))
                prev = eid
                y += 30 + GAP

            elif stype == "decision":
                did = nid()
                cells.append(_vertex(did, sname, S_IO_DECISION, CX - DW // 2, y, DW, DH))
                if prev:
                    cells.append(_edge(nid(), "", S_IO_ARROW, prev, did))
                prev = did
                y += DH + GAP

            else:  # "ref", "interaction"
                ref_id = nid()
                cells.append(_vertex(ref_id, "ref&#xa;" + sname, S_IO_REF, CX - RW // 2, y, RW, RH))
                if prev:
                    cells.append(_edge(nid(), "", S_IO_ARROW, prev, ref_id))
                prev = ref_id
                y += RH + GAP

        return cells

    # ------------------------------------------------------------------
    # Generic fallback
    # ------------------------------------------------------------------

    def _generic_diagram(self, data, nid):
        cells = []
        items = []
        for k, v in data.items():
            if isinstance(v, list):
                items.extend([str(x) for x in v[:6]])
            else:
                items.append("%s: %s" % (k, v))
        for i, item in enumerate(items[:20]):
            cells.append(_vertex(nid(), item[:100], S_ACT_ACTION, 80, 80 + i * 70, 320, 50))
        if not cells:
            cells.append(_vertex(nid(), "No data available", S_ACT_ACTION, 100, 100, 240, 50))
        return cells


# ======================================================================
# Shareable URL helpers
# ======================================================================

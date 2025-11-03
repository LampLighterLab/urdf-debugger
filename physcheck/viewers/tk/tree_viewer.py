from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import tkinter as tk
from tkinter import font as tkfont

import numpy as np

from physcheck.visualization import TreeScene
from physcheck.visualization.scene import _estimate_collision_eigenvalues

Position = Tuple[float, float]

_JOINT_LABELS = {
    "revolute": "Joint: revolute",
    "continuous": "Joint: continuous",
    "prismatic": "Joint: prismatic",
    "planar": "Joint: planar",
    "fixed": "Joint: fixed",
}

_STATUS_ICONS = {
    "OK": "🟢",
    "WARN": "🟡",
    "FAIL": "🔴",
    "INFO": "🔹",
}


def _inertia_tensor_to_matrix(
    entries: Tuple[float, float, float, float, float, float],
) -> np.ndarray:
    ixx, ixy, ixz, iyy, iyz, izz = entries
    return np.array(
        [
            [ixx, ixy, ixz],
            [ixy, iyy, iyz],
            [ixz, iyz, izz],
        ],
        dtype=float,
    )
class TkTreeViewer:
    """Render a kinematic tree scene using Tkinter."""

    def __init__(
        self,
        scene: TreeScene,
        title: str,
        *,
        maximize: bool = True,
    ) -> None:
        self.scene = scene
        self.title = title
        self.maximize = maximize

    def run(self, output: Path | None = None) -> None:
        root = tk.Tk()
        root.withdraw()
        root.title(self.title)
        if self.maximize:
            try:
                root.state("zoomed")
            except tk.TclError:
                root.attributes("-zoomed", True)

        node_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        edge_font = tkfont.Font(family="Helvetica", size=14)
        info_font = tkfont.Font(family="Helvetica", size=12)
        legend_font = tkfont.Font(family="Helvetica", size=12)

        container = tk.Frame(root, background="#f0f0f0")
        container.pack(fill="both", expand=True)

        tree_frame = tk.Frame(container, background="#ffffff")
        tree_frame.pack(side=tk.LEFT, fill="both", expand=True)

        info_frame = tk.Frame(container, background="#fafafa", width=640)
        info_frame.pack(side=tk.RIGHT, fill="both")
        info_frame.pack_propagate(False)

        info_panel = _InfoPanel(info_frame, node_font=node_font, info_font=info_font)
        info_panel.pack(side=tk.TOP, fill="both", expand=True, padx=12, pady=(12, 6))

        legend_canvas = _LegendCanvas(info_frame, legend_font=legend_font)
        legend_canvas.pack(side=tk.TOP, fill="x", padx=12, pady=(0, 12))

        detail_window = _DetailWindow(
            root,
            node_font=node_font,
            info_font=info_font,
        )
        info_panel.register_click_handler(detail_window.show_entry)

        tree_canvas = _TreeCanvas(
            tree_frame,
            self.scene,
            info_panel=info_panel,
            node_font=node_font,
            edge_font=edge_font,
        )
        tree_canvas.pack(fill="both", expand=True)

        legend_canvas.render(self.scene)

        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.focus_force()

        if output:
            try:
                tree_canvas.save_postscript(output)
            except tk.TclError as exc:
                print(f"Failed to save canvas: {exc}")

        root.mainloop()


class _TreeCanvas(tk.Canvas):
    """Canvas that draws tree nodes and edges and reports hover events."""

    def __init__(
        self,
        master: tk.Misc,
        scene: TreeScene,
        *,
        info_panel: "_InfoPanel",
        node_font: tkfont.Font,
        edge_font: tkfont.Font,
        **kwargs,
    ) -> None:
        super().__init__(master, background="white", highlightthickness=0, **kwargs)
        self.scene = scene
        self.info_panel = info_panel
        self.node_font = node_font
        self.edge_font = edge_font
        self.node_boxes: Dict[str, Tuple[float, float, float, float]] = {}
        self.node_entries: Dict[str, List[Dict[str, Any]]] = {}
        self._current_hover: Optional[str] = None
        self._last_selection: Optional[str] = None

        self.bind("<Configure>", self._on_resize)
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<Leave>", self._on_mouse_leave)

        self._draw(self.winfo_reqwidth(), self.winfo_reqheight())

    def save_postscript(self, destination: Path) -> None:
        self.update_idletasks()
        self.postscript(file=str(destination))

    def _on_resize(self, event: tk.Event) -> None:
        self._draw(event.width, event.height)

    def _draw(self, width: int, height: int) -> None:
        self.delete("all")
        self.node_boxes.clear()
        self.node_entries.clear()

        if not self.scene.nodes:
            return

        xs = [node.position[0] for node in self.scene.nodes]
        ys = [node.position[1] for node in self.scene.nodes]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        margin_x = 80
        margin_y = 80
        avail_w = max(width - 2 * margin_x, 1)
        avail_h = max(height - 2 * margin_y, 1)
        span_x = max(max_x - min_x, 1e-3)
        span_y = max(max_y - min_y, 1e-3)

        def map_position(position: Position) -> Position:
            x, y = position
            px = margin_x + ((x - min_x) / span_x) * avail_w
            py = margin_y + ((max_y - y) / span_y) * avail_h
            return px, py

        # Render nodes and capture bounding boxes.
        for node in self.scene.nodes:
            px, py = map_position(node.position)
            text_width = self.node_font.measure(node.name)
            text_height = self.node_font.metrics("linespace")
            padding_x = 16
            padding_y = 10
            half_w = (text_width / 2) + padding_x
            half_h = (text_height / 2) + padding_y
            x0 = px - half_w
            y0 = py - half_h
            x1 = px + half_w
            y1 = py + half_h
            self.node_boxes[node.name] = (x0, y0, x1, y1)
            style = node.visual_style or {}
            shape = style.get("shape", "rectangle")
            fill = style.get("fill", "#e3f2fd")
            outline = style.get("outline", "#1565c0")
            outline_width = style.get("outline_width", 2)
            if shape == "ellipse":
                self.create_oval(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline=outline,
                    width=outline_width,
                    fill=fill,
                )
            else:
                self.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline=outline,
                    width=outline_width,
                    fill=fill,
                )
            self.create_text(
                px,
                py,
                text=node.name,
                fill="#000000",
                font=self.node_font,
            )
            raw_entries = (
                node.payload.get("check_entries") or self.info_panel.default_entries
            )
            enriched_entries = [
                self._augment_entry(entry, node.payload) for entry in raw_entries
            ]
            self.node_entries[node.name] = enriched_entries

        for edge in self.scene.edges:
            parent_box = self.node_boxes.get(edge.parent)
            child_box = self.node_boxes.get(edge.child)
            if not parent_box or not child_box:
                continue
            start_x = (parent_box[0] + parent_box[2]) / 2
            start_y = parent_box[3] - 4
            end_x = (child_box[0] + child_box[2]) / 2
            end_y = child_box[1] + 4
            style = edge.visual_style or {}
            stroke = style.get("stroke", "#424242")
            width = style.get("width", 3)
            self.create_line(
                start_x,
                start_y,
                end_x,
                end_y,
                width=width,
                fill=stroke,
                arrow=tk.LAST,
            )
            if edge.label:
                mid_x = (start_x + end_x) / 2
                mid_y = (start_y + end_y) / 2 - 12
                text_width = self.edge_font.measure(edge.label)
                text_height = self.edge_font.metrics("linespace")
                padding_x = 6
                padding_y = 4
                x0 = mid_x - text_width / 2 - padding_x
                y0 = mid_y - text_height / 2 - padding_y
                x1 = mid_x + text_width / 2 + padding_x
                y1 = mid_y + text_height / 2 + padding_y
                self.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    fill="white",
                    outline="",
                )
                self.create_text(
                    mid_x,
                    mid_y,
                    text=edge.label,
                    fill="#000000",
                    font=self.edge_font,
                )

        if self._last_selection and self._last_selection not in self.node_entries:
            self._last_selection = None

        selection = self._current_hover or self._last_selection
        if selection and selection in self.node_entries:
            self.info_panel.show_entries(selection, self.node_entries[selection])
        elif self._last_selection is None:
            self.info_panel.show_default()

    def _on_mouse_move(self, event: tk.Event) -> None:
        x, y = event.x, event.y
        for name, (x0, y0, x1, y1) in self.node_boxes.items():
            if x0 <= x <= x1 and y0 <= y <= y1:
                if self._current_hover != name:
                    self._current_hover = name
                    self._last_selection = name
                    entries = self.node_entries.get(
                        name, self.info_panel.default_entries
                    )
                    self.info_panel.show_entries(name, entries)
                return
        if self._current_hover is not None:
            self._current_hover = None
            if self._last_selection is None:
                self.info_panel.show_default()

    def _on_mouse_leave(self, _: tk.Event) -> None:
        if self._current_hover is not None:
            self._current_hover = None
            if self._last_selection is None:
                self.info_panel.show_default()

    def _augment_entry(
        self, entry_data: Dict[str, Any], node_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        result = dict(entry_data)
        if "details" in result and isinstance(result["details"], dict):
            result["details"] = dict(result["details"])
        link = node_payload.get("link")
        result.setdefault("link", link)
        inertial = node_payload.get("inertial")
        if inertial is not None:
            result.setdefault("mass", getattr(inertial, "mass", None))
            tensor = getattr(inertial, "inertia", None)
            if tensor is not None:
                result.setdefault(
                    "inertia_matrix",
                    _inertia_tensor_to_matrix(tensor).tolist(),
                )
        result.setdefault("visualization", node_payload.get("visualization", {}))
        return result


class _InfoPanel(tk.Frame):
    """Panel that displays hover information for the selected link."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        node_font: tkfont.Font,
        info_font: tkfont.Font,
    ) -> None:
        super().__init__(master, background="#fafafa", borderwidth=1, relief=tk.FLAT)
        self.node_font = node_font
        self.info_font = info_font
        self._default_entries: List[Dict[str, Any]] = [
            {
                "status": "INFO",
                "severity": "info",
                "headline": "No selection",
                "summary": "Hover a link to inspect inertia checks.",
                "detail_text": "Hover a link to inspect inertia checks.",
                "details": {},
                "passed": True,
                "raw_check": None,
            },
        ]
        self._entry_frames: List[tk.Frame] = []
        self._message_labels: List[tk.Label] = []
        self._click_handler: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._summary_font = tkfont.Font(
            family=info_font.actual("family"),
            size=info_font.actual("size"),
            weight="bold",
        )

        self.bind("<Configure>", lambda _event: self._update_wraplength())

        self._title_label = tk.Label(
            self,
            text="Inertia Checks",
            font=self.node_font,
            anchor="w",
            background="#fafafa",
            fg="#000000",
        )
        self._title_label.pack(fill="x", padx=4, pady=(0, 12))

        self._content = tk.Frame(self, background="#fafafa")
        self._content.pack(fill="both", expand=True, padx=4)

        self.show_default()

    @property
    def default_entries(self) -> List[Dict[str, Any]]:
        return [dict(entry) for entry in self._default_entries]

    @property
    def entry_frames(self) -> List[tk.Frame]:
        return list(self._entry_frames)

    def register_click_handler(
        self, handler: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        self._click_handler = handler

    def show_entries(self, link_name: str, entries: List[Dict[str, Any]]) -> None:
        self._title_label.configure(text=link_name)
        self._render_entries(entries)

    def show_default(self) -> None:
        self._title_label.configure(text="Inertia Checks")
        self._render_entries(self.default_entries)

    def _render_entries(self, entries: List[Dict[str, Any]]) -> None:
        for child in self._content.winfo_children():
            child.destroy()

        if not entries:
            entries = self.default_entries

        self._entry_frames.clear()
        self._message_labels.clear()

        for entry_data in entries:
            status = entry_data.get("status", "INFO")
            headline = entry_data.get("headline", status)
            summary_text = (
                entry_data.get("summary") or entry_data.get("detail_text") or ""
            )
            card = tk.Frame(
                self._content,
                background="#ffffff",
                borderwidth=1,
                relief=tk.SOLID,
                highlightbackground="#cfd8dc",
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            card.pack(fill="x", pady=4, padx=2)
            self._entry_frames.append(card)

            icon_label = tk.Label(
                card,
                text=_STATUS_ICONS.get(status, "🔹"),
                font=self.info_font,
                background="#ffffff",
                fg="#000000",
            )
            icon_label.pack(side=tk.LEFT)

            text_container = tk.Frame(card, background="#ffffff")
            text_container.pack(side=tk.LEFT, fill="x", expand=True, padx=(12, 0))

            summary_label = tk.Label(
                text_container,
                text=headline,
                font=self._summary_font,
                background="#ffffff",
                fg="#000000",
                anchor="w",
            )
            summary_label.pack(fill="x")

            message_label = tk.Label(
                text_container,
                text=summary_text,
                font=self.info_font,
                background="#ffffff",
                fg="#000000",
                justify=tk.LEFT,
                wraplength=1,
            )
            message_label.pack(fill="x", expand=True, pady=(4, 0))
            self._message_labels.append(message_label)

            if self._click_handler and entry_data.get("raw_check") is not None:
                for widget in (
                    card,
                    icon_label,
                    text_container,
                    summary_label,
                    message_label,
                ):
                    widget.configure(cursor="hand2")
                    widget.bind(
                        "<Button-1>",
                        lambda _event, entry_payload=entry_data: self._click_handler(
                            self._title_label.cget("text"), entry_payload
                        ),
                    )

        self.after_idle(self._update_wraplength)

    def _update_wraplength(self) -> None:
        if not self._message_labels:
            return
        width = max(self.winfo_width() - 120, 200)
        for label in self._message_labels:
            label.configure(wraplength=width)


class _LegendCanvas(tk.Canvas):
    """Canvas that renders the legend for link and joint styles."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        legend_font: tkfont.Font,
    ) -> None:
        super().__init__(master, background="#ffffff", highlightthickness=0)
        self.legend_font = legend_font
        self.configure(height=1)

    def render(self, scene: TreeScene) -> None:
        self.delete("all")

        nodes = scene.nodes
        edges = scene.edges

        entries: List[Tuple[str, Dict[str, str], str]] = []

        combo_map: Dict[Tuple[bool, bool], Dict[str, str]] = {}
        for node in nodes:
            has_inertia = bool(node.payload.get("has_inertia"))
            has_collision = bool(node.payload.get("has_collision"))
            key = (has_inertia, has_collision)
            combo_map.setdefault(key, node.visual_style or {})

        combo_labels = {
            (True, True): "Link: inertia + collision",
            (True, False): "Link: inertia only",
            (False, True): "Link: collision only",
            (False, False): "Link: no inertia",
        }

        for key, style in combo_map.items():
            has_inertia, has_collision = key
            shape = style.get("shape", "rectangle")
            entry_shape = shape
            if not has_inertia and not has_collision:
                entry_shape = "empty_rectangle"
            entries.append((entry_shape, style, combo_labels.get(key, "Link")))

        joint_styles: Dict[str, str] = {}
        for edge in edges:
            joint_type = (
                edge.payload.get("joint_type")
                if isinstance(edge.payload, dict)
                else None
            )
            if joint_type:
                joint_styles.setdefault(
                    joint_type, edge.visual_style.get("stroke", "#424242")
                )

        joint_order = ["revolute", "continuous", "prismatic", "planar", "fixed"]
        for jt in joint_order:
            if jt in joint_styles:
                entries.append(("line", {"color": joint_styles[jt]}, _JOINT_LABELS[jt]))
        for jt, color in joint_styles.items():
            if jt not in joint_order:
                entries.append(("line", {"color": color}, f"Joint: {jt}"))

        if not entries:
            self.configure(height=1)
            return

        legend_padding = 16
        legend_line_height = 28
        icon_width = 32
        text_width = max(self.legend_font.measure(entry[2]) for entry in entries)
        legend_width = legend_padding * 2 + icon_width + 12 + text_width
        legend_height = legend_padding * 2 + legend_line_height * len(entries)

        self.configure(width=int(legend_width + 4), height=int(legend_height + 4))

        self.create_rectangle(
            2,
            2,
            2 + legend_width,
            2 + legend_height,
            fill="#ffffff",
            outline="#b0bec5",
        )

        x0 = 2 + legend_padding
        y0 = 2 + legend_padding

        for shape, style, label in entries:
            if shape == "ellipse":
                fill = style.get("fill", "#e3f2fd")
                outline = style.get("outline", "#1565c0")
                self.create_oval(
                    x0,
                    y0,
                    x0 + icon_width,
                    y0 + 20,
                    fill=fill,
                    outline=outline,
                    width=style.get("outline_width", 2),
                )
            elif shape == "empty_rectangle":
                outline = style.get("outline", "#90a4ae")
                fill = style.get("fill", "#eceff1")
                self.create_rectangle(
                    x0,
                    y0,
                    x0 + icon_width,
                    y0 + 20,
                    fill=fill,
                    outline=outline,
                    width=2,
                )
            elif shape == "rectangle":
                fill = style.get("fill", "#e3f2fd")
                outline = style.get("outline", "#1565c0")
                self.create_rectangle(
                    x0,
                    y0,
                    x0 + icon_width,
                    y0 + 20,
                    fill=fill,
                    outline=outline,
                    width=style.get("outline_width", 2),
                )
            elif shape == "line":
                color = style.get("color", "#424242")
                self.create_line(
                    x0,
                    y0 + 10,
                    x0 + icon_width,
                    y0 + 10,
                    fill=color,
                    width=3,
                )
            else:
                fill = style.get("fill", "#e3f2fd")
                outline = style.get("outline", "#1565c0")
                self.create_rectangle(
                    x0,
                    y0,
                    x0 + icon_width,
                    y0 + 20,
                    fill=fill,
                    outline=outline,
                    width=style.get("outline_width", 2),
                )

            self.create_text(
                x0 + icon_width + 12,
                y0 + 10,
                anchor="w",
                text=label,
                font=self.legend_font,
                fill="#000000",
            )
            y0 += legend_line_height


class _DetailWindow:
    """Dedicated window that surfaces check details and future tools."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        node_font: tkfont.Font,
        info_font: tkfont.Font,
    ) -> None:
        self._master = master
        node_size = int(node_font.actual("size"))
        info_size = int(info_font.actual("size"))
        family = node_font.actual("family")
        info_family = info_font.actual("family")
        self._title_font = tkfont.Font(family=family, size=node_size + 6, weight="bold")
        self._section_font = tkfont.Font(
            family=family, size=node_size + 2, weight="bold"
        )
        self._status_font = tkfont.Font(
            family=info_family, size=info_size + 1, weight="bold"
        )
        self._body_font = tkfont.Font(family=info_family, size=info_size + 2)
        self._mono_font = tkfont.Font(family="Courier", size=max(info_size + 1, 11))

        self._toplevel: Optional[tk.Toplevel] = None
        self._detail_panel: Optional[tk.Frame] = None
        self._viz_panel: Optional[tk.Frame] = None
        self._detail_text_labels: List[tk.Label] = []
        self._figure: Optional[Any] = None
        self._axes: Optional[Any] = None
        self._canvas: Optional[Any] = None

    def show_entry(self, link_name: str, entry: Dict[str, Any]) -> None:
        self._ensure_window()
        assert self._toplevel is not None and self._detail_panel is not None
        self._toplevel.title(f"{link_name} – {entry.get('headline', 'Check detail')}")
        self._render_detail(link_name, entry)
        self._toplevel.deiconify()
        self._toplevel.lift()
        self._toplevel.focus_force()

    def _ensure_window(self) -> None:
        if self._toplevel is not None and self._toplevel.winfo_exists():
            return

        top = tk.Toplevel(self._master)
        top.withdraw()
        top.configure(background="#f5f5f5")
        top.geometry("1024x720")
        top.minsize(820, 560)
        top.title("Physcheck – Check detail")
        top.protocol("WM_DELETE_WINDOW", top.withdraw)

        container = tk.Frame(top, background="#f5f5f5")
        container.pack(fill="both", expand=True, padx=20, pady=20)

        detail_panel = tk.Frame(
            container, background="#ffffff", borderwidth=1, relief=tk.SOLID
        )
        detail_panel.pack(side=tk.LEFT, fill="both", expand=True)
        detail_panel.columnconfigure(0, weight=1)

        viz_panel = tk.Frame(
            container,
            background="#e3f2fd",
            borderwidth=1,
            relief=tk.SOLID,
            width=360,
        )
        viz_panel.pack(side=tk.RIGHT, fill="both", expand=False, padx=(20, 0))
        viz_panel.pack_propagate(False)

        canvas = tk.Canvas(
            viz_panel,
            background="#ffffff",
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill="both", expand=True, padx=12, pady=12)
        canvas.bind(
            "<Configure>",
            lambda event: self._draw_placeholder(canvas, event.width, event.height),
        )
        canvas.after(
            50,
            lambda: self._draw_placeholder(canvas, canvas.winfo_width(), canvas.winfo_height()),
        )

        self._figure = None
        self._axes = None
        self._canvas = canvas

        self._toplevel = top
        self._detail_panel = detail_panel
        self._viz_panel = viz_panel
        self._detail_panel.bind(
            "<Configure>", lambda _event: self._update_detail_wraplength()
        )

    def _render_detail(self, link_name: str, entry: Dict[str, Any]) -> None:
        assert self._detail_panel is not None
        panel = self._detail_panel
        for child in panel.winfo_children():
            child.destroy()
        self._detail_text_labels.clear()

        header = tk.Label(
            panel,
            text=link_name,
            font=self._title_font,
            anchor="w",
            background="#ffffff",
            fg="#000000",
        )
        header.grid(row=0, column=0, sticky="w", padx=24, pady=(24, 6))

        headline = entry.get("headline", "Check")
        subheader = tk.Label(
            panel,
            text=headline,
            font=self._section_font,
            anchor="w",
            background="#ffffff",
            fg="#37474f",
        )
        subheader.grid(row=1, column=0, sticky="w", padx=24, pady=(0, 12))

        status_line = tk.Frame(panel, background="#ffffff")
        status_line.grid(row=2, column=0, sticky="we", padx=24)
        status_line.columnconfigure(1, weight=1)

        status_text = {
            "OK": "Pass",
            "WARN": "Warning",
            "FAIL": "Issue",
            "INFO": "Info",
        }
        status = entry.get("status", "INFO")
        icon_label = tk.Label(
            status_line,
            text=_STATUS_ICONS.get(status, "🔹"),
            font=self._section_font,
            background="#ffffff",
            fg="#000000",
        )
        icon_label.grid(row=0, column=0, sticky="w")

        status_label = tk.Label(
            status_line,
            text=f"Status: {status_text.get(status, status)}",
            font=self._status_font,
            background="#ffffff",
            fg="#000000",
            anchor="w",
        )
        status_label.grid(row=0, column=1, sticky="w", padx=(12, 0))

        summary = entry.get("summary", "")
        summary_label = tk.Label(
            panel,
            text=summary,
            font=self._body_font,
            background="#ffffff",
            fg="#000000",
            justify=tk.LEFT,
            wraplength=1,
        )
        summary_label.grid(row=3, column=0, sticky="we", padx=24, pady=(18, 0))
        self._detail_text_labels.append(summary_label)

        detail_text = entry.get("detail_text")
        if detail_text and detail_text != summary:
            detail_label = tk.Label(
                panel,
                text=detail_text,
                font=self._body_font,
                background="#ffffff",
                fg="#424242",
                justify=tk.LEFT,
                wraplength=1,
            )
            detail_label.grid(row=4, column=0, sticky="we", padx=24, pady=(12, 0))
            self._detail_text_labels.append(detail_label)
            next_row = 5
        else:
            next_row = 4

        details = entry.get("details") or {}
        if details:
            section_label = tk.Label(
                panel,
                text="Details",
                font=self._section_font,
                background="#ffffff",
                fg="#000000",
                anchor="w",
            )
            section_label.grid(
                row=next_row, column=0, sticky="we", padx=24, pady=(24, 8)
            )
            next_row += 1

            detail_container = tk.Frame(panel, background="#ffffff")
            detail_container.grid(row=next_row, column=0, sticky="we", padx=24)
            detail_container.columnconfigure(1, weight=1)

            for idx, (key, value) in enumerate(details.items()):
                row = tk.Frame(detail_container, background="#ffffff")
                row.grid(row=idx, column=0, sticky="we", pady=4)
                key_label = tk.Label(
                    row,
                    text=str(key),
                    font=self._status_font,
                    background="#ffffff",
                    fg="#000000",
                    anchor="nw",
                )
                key_label.pack(side=tk.LEFT, anchor="nw")

                value_frame = tk.Frame(row, background="#ffffff")
                value_frame.pack(side=tk.LEFT, fill="both", expand=True, padx=(16, 0))
                self._render_detail_value(value_frame, value)

        # pad bottom to keep spacing pleasant
        panel.grid_rowconfigure(99, weight=1)
        spacer = tk.Frame(panel, background="#ffffff")
        spacer.grid(row=98, column=0, pady=12)

        self._render_visualization(entry)
        self._update_detail_wraplength()

    def _render_detail_value(self, parent: tk.Misc, value: Any) -> None:
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                sub_row = tk.Frame(parent, background="#ffffff")
                sub_row.pack(fill="x", pady=2)
                sub_label = tk.Label(
                    sub_row,
                    text=str(sub_key),
                    font=self._status_font,
                    background="#ffffff",
                    fg="#000000",
                    anchor="nw",
                )
                sub_label.pack(side=tk.LEFT, anchor="nw")
                sub_value_frame = tk.Frame(sub_row, background="#ffffff")
                sub_value_frame.pack(side=tk.LEFT, fill="x", expand=True, padx=(12, 0))
                self._render_detail_value(sub_value_frame, sub_value)
            return

        if isinstance(value, (list, tuple)):
            if all(isinstance(item, (int, float)) for item in value):
                for idx, item in enumerate(value):
                    label = tk.Label(
                        parent,
                        text=f"{idx + 1}: {self._format_number(item)}",
                        font=self._mono_font,
                        background="#ffffff",
                        fg="#000000",
                        anchor="w",
                        justify=tk.LEFT,
                    )
                    label.pack(anchor="w")
                    self._detail_text_labels.append(label)
            else:
                for item in value:
                    self._render_detail_value(parent, item)
            return

        text = self._format_value(value)
        label = tk.Label(
            parent,
            text=text,
            font=self._body_font,
            background="#ffffff",
            fg="#000000",
            justify=tk.LEFT,
            anchor="w",
            wraplength=1,
        )
        label.pack(fill="x", pady=1)
        self._detail_text_labels.append(label)

    def _update_detail_wraplength(self) -> None:
        if (
            not self._detail_text_labels
            or self._detail_panel is None
            or not self._detail_panel.winfo_exists()
        ):
            return
        width = max(self._detail_panel.winfo_width() - 200, 260)
        for label in list(self._detail_text_labels):
            if label.winfo_exists():
                label.configure(wraplength=width)

    @staticmethod
    def _format_number(value: float) -> str:
        try:
            return f"{float(value):.3e}"
        except (TypeError, ValueError):
            return str(value)

    def _format_value(self, value: Any) -> str:
        if isinstance(value, (int, float)):
            return self._format_number(value)
        return str(value)

    def _render_visualization(self, entry: Dict[str, Any]) -> None:
        if self._canvas is None or self._viz_panel is None:
            return

        matrix_data = entry.get("inertia_matrix")
        viz_payload = entry.get("visualization") or {}
        mass = viz_payload.get("mass") or entry.get("mass")
        details = dict(entry.get("details") or {})
        if not details.get("expected_eigenvalues") and viz_payload.get("expected_eigenvalues"):
            details["expected_eigenvalues"] = viz_payload.get("expected_eigenvalues")

        if matrix_data is None or mass is None:
            self._show_viz_message("Inertia data unavailable.")
            return

        matrix = np.array(matrix_data, dtype=float)
        if matrix.shape != (3, 3):
            self._show_viz_message("Inertia tensor malformed.")
            return

        if not np.isfinite(mass) or mass <= 0.0:
            self._show_viz_message("Mass must be positive to visualize.")
            return

        try:
            eigvals, eigvecs = np.linalg.eigh(matrix)
        except np.linalg.LinAlgError:
            self._show_viz_message("Failed to compute principal axes.")
            return

        if np.min(eigvals) < -1e-9:
            self._show_viz_message("Negative eigenvalues detected.")
            return

        eigvals = np.clip(eigvals, 0.0, None)
        actual_axes = self._moments_to_axes(mass, eigvals)
        if actual_axes is None:
            self._show_viz_message("Unable to derive ellipsoid axes.")
            return

        expected_axes = None
        expected_eigs = details.get("expected_eigenvalues")
        if expected_eigs is None:
            link_obj = entry.get("link")
            collisions = getattr(link_obj, "collisions", ()) if link_obj is not None else ()
            estimated = _estimate_collision_eigenvalues(collisions, float(mass))
            if estimated is not None:
                expected_eigs = estimated
        if expected_eigs is not None:
            expected_eigs = np.array(expected_eigs, dtype=float)
            expected_eigs = np.clip(expected_eigs, 0.0, None)
            expected_axes = self._moments_to_axes(mass, expected_eigs)

        projected_actual = self._compute_projected_ellipse(actual_axes, eigvecs)
        if projected_actual is None:
            self._show_viz_message("Unable to project inertia ellipsoid.")
            return

        projected_expected = (
            self._compute_projected_ellipse(expected_axes, eigvecs)
            if expected_axes is not None
            else None
        )

        self._draw_flattened_view(projected_actual, projected_expected)

    def _show_viz_message(self, message: str) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("viz")
        width = canvas.winfo_width()
        height = canvas.winfo_height()
        if width <= 0 or height <= 0:
            return
        canvas.create_rectangle(
            0,
            0,
            width,
            height,
            fill="#ffffff",
            outline="",
            tags="viz",
        )
        canvas.create_text(
            width / 2,
            height / 2,
            text=message,
            fill="#0d47a1",
            font=self._section_font,
            width=width - 40,
            justify=tk.CENTER,
            tags="viz",
        )

    @staticmethod
    def _moments_to_axes(mass: float, moments: np.ndarray) -> Optional[np.ndarray]:
        moments = np.asarray(moments, dtype=float)
        if moments.size != 3 or not np.all(np.isfinite(moments)):
            return None
        m = float(mass)
        if m <= 0.0 or not np.isfinite(m):
            return None
        coeff = 5.0 / (2.0 * m)
        a2 = coeff * (moments[1] + moments[2] - moments[0])
        b2 = coeff * (moments[0] + moments[2] - moments[1])
        c2 = coeff * (moments[0] + moments[1] - moments[2])
        values = np.array([a2, b2, c2], dtype=float)
        if np.any(values < -1e-9):
            return None
        values = np.clip(values, 0.0, None)
        return np.sqrt(values)

    def _compute_projected_ellipse(
        self, semiaxes: np.ndarray | None, rotation: np.ndarray
    ) -> Optional[Dict[str, Any]]:
        if semiaxes is None:
            return None

        rotation = np.array(rotation, dtype=float)
        if rotation.shape != (3, 3):
            rotation = np.eye(3)

        radii = np.asarray(semiaxes, dtype=float)
        if radii.size != 3:
            return None

        transform = rotation @ np.diag(radii)
        proj = transform[:2, :]
        cov = proj @ proj.T
        try:
            values, vectors = np.linalg.eigh(cov)
        except np.linalg.LinAlgError:
            return None
        values = np.clip(values, 0.0, None)
        radii_2d = np.sqrt(values)

        # Sort descending for consistent drawing
        order = np.argsort(radii_2d)[::-1]
        radii_2d = radii_2d[order]
        vectors = vectors[:, order]

        params = np.linspace(0.0, 2.0 * np.pi, 240)
        circle = np.stack([np.cos(params), np.sin(params)])
        outline = vectors @ (np.diag(radii_2d) @ circle)

        axis_projections: list[Tuple[float, float]] = []
        for idx in range(3):
            vec = rotation[:, idx] * radii[idx]
            axis_projections.append((vec[0], vec[1]))

        return {
            "outline": outline,
            "axes": axis_projections,
            "radii_2d": radii_2d,
        }

    def _draw_flattened_view(
        self,
        actual: Dict[str, Any],
        expected: Optional[Dict[str, Any]],
    ) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        canvas.delete("viz")
        width = max(canvas.winfo_width(), 10)
        height = max(canvas.winfo_height(), 10)
        center_x = width / 2
        center_y = height / 2

        scale_base = min(width, height) * 0.45
        max_radius = float(np.max(actual["radii_2d"]))
        if expected is not None:
            max_radius = max(max_radius, float(np.max(expected["radii_2d"])))
        if not np.isfinite(max_radius) or max_radius <= 0.0:
            max_radius = 1.0
        scale = scale_base / max_radius

        canvas.create_rectangle(
            0,
            0,
            width,
            height,
            fill="#ffffff",
            outline="",
            tags="viz",
        )

        outline = actual["outline"]
        x_vals, y_vals = outline[0], outline[1]
        points = []
        for x, y in zip(x_vals, y_vals):
            points.append(center_x + x * scale)
            points.append(center_y - y * scale)
        canvas.create_polygon(
            *points,
            fill="#ef6c00",
            outline="#bf360c",
            width=2,
            stipple="gray50",
            tags="viz",
        )

        # Draw projected principal axes for actual inertia
        for dx, dy in actual["axes"]:
            if np.hypot(dx, dy) < 1e-9:
                continue
            canvas.create_line(
                center_x,
                center_y,
                center_x + dx * scale,
                center_y - dy * scale,
                fill="#bf360c",
                width=3,
                tags="viz",
            )

        if expected is not None:
            outline = expected["outline"]
            x_vals, y_vals = outline[0], outline[1]
            points = []
            for x, y in zip(x_vals, y_vals):
                points.append(center_x + x * scale)
                points.append(center_y - y * scale)
            canvas.create_polygon(
                *points,
                fill="",
                outline="#004d40",
                width=2,
                dash=(6, 4),
                tags="viz",
            )

            for dx, dy in expected["axes"]:
                if np.hypot(dx, dy) < 1e-9:
                    continue
                canvas.create_line(
                    center_x,
                    center_y,
                    center_x + dx * scale,
                    center_y - dy * scale,
                    fill="#004d40",
                    width=2,
                    dash=(4, 4),
                    tags="viz",
                )

        canvas.create_text(
            center_x,
            20,
            text="Actual (solid) vs Expected (dashed)",
            fill="#0d47a1",
            font=self._status_font,
            tags="viz",
        )

    @staticmethod
    def _draw_placeholder(canvas: tk.Canvas, width: int, height: int) -> None:
        canvas.delete("viz")
        if width <= 0 or height <= 0:
            return
        canvas.create_rectangle(0, 0, width, height, fill="#ffffff", outline="", tags="viz")
        canvas.create_text(
            width / 2,
            height / 2,
            text="Select a link to view inertia projection",
            fill="#0d47a1",
            justify=tk.CENTER,
            width=width - 40,
            tags="viz",
        )

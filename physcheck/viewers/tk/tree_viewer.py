from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import tkinter as tk
from tkinter import font as tkfont

from physcheck.visualization import TreeEdge, TreeNode, TreeScene

Position = Tuple[float, float]

_JOINT_LABELS = {
    "revolute": "Joint: revolute",
    "continuous": "Joint: continuous",
    "prismatic": "Joint: prismatic",
    "planar": "Joint: planar",
    "fixed": "Joint: fixed",
}


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
        canvas = _TreeCanvas(root, self.scene)
        root.update_idletasks()
        root.deiconify()
        root.lift()
        root.focus_force()
        if output:
            try:
                canvas.save_postscript(output)
            except tk.TclError as exc:
                print(f"Failed to save canvas: {exc}")
        root.mainloop()


class _TreeCanvas(tk.Canvas):
    """Internal canvas to draw tree nodes and edges."""

    def __init__(self, master: tk.Misc, scene: TreeScene, **kwargs) -> None:
        super().__init__(master, background="white", highlightthickness=0, **kwargs)
        self.scene = scene
        self.node_font = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.edge_font = tkfont.Font(family="Helvetica", size=14)
        self.legend_font = tkfont.Font(family="Helvetica", size=12)
        self.node_boxes: Dict[str, Tuple[float, float, float, float]] = {}
        self.pack(fill="both", expand=True)
        self.bind("<Configure>", self._on_resize)
        self._draw(self.winfo_reqwidth(), self.winfo_reqheight())
        self._draw_legend()

    def _on_resize(self, event: tk.Event) -> None:
        self.delete("all")
        self.node_boxes.clear()
        self._draw(event.width, event.height)
        self._draw_legend()

    def _draw(self, width: int, height: int) -> None:
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
            if shape == "ellipse":
                self.create_oval(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline=outline,
                    width=2,
                    fill=fill,
                )
            else:
                self.create_rectangle(
                    x0,
                    y0,
                    x1,
                    y1,
                    outline=outline,
                    width=2,
                    fill=fill,
                )
            text_color = style.get("font_color", "#263238")
            self.create_text(
                px,
                py,
                text=node.name,
                fill=text_color,
                font=self.node_font,
            )

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
            width = style.get("width", 2)
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
                    fill="#424242",
                    font=self.edge_font,
                )

    def save_postscript(self, destination: Path) -> None:
        self.update_idletasks()
        self.postscript(file=str(destination))

    def _draw_legend(self) -> None:
        self.delete("legend")

        nodes = self.scene.nodes
        edges = self.scene.edges

        entries: list[tuple[str, dict[str, str], str]] = []

        combo_map: Dict[tuple[bool, bool], TreeNode] = {}
        for node in nodes:
            key = (
                bool(node.payload.get("has_inertia")),
                bool(node.payload.get("has_collision")),
            )
            combo_map.setdefault(key, node)

        combo_labels = {
            (True, True): "Link: inertia + collision",
            (True, False): "Link: inertia only",
            (False, True): "Link: collision only",
            (False, False): "Link: no inertia",
        }

        for key, node in combo_map.items():
            has_inertia, has_collision = key
            style = node.visual_style
            shape = style.get("shape", "rectangle")
            entry_shape = shape
            if not has_inertia and not has_collision:
                entry_shape = "empty_rectangle"
            entries.append((entry_shape, style, combo_labels.get(key, "Link")))

        joint_styles: Dict[str, str] = {}
        for edge in edges:
            jt = edge.payload.get("joint_type") or "fixed"
            joint_styles[jt] = edge.visual_style.get("stroke", "#424242")

        joint_order = ["revolute", "continuous", "prismatic", "planar", "fixed"]
        for jt in joint_order:
            if jt in joint_styles:
                entries.append(("line", {"color": joint_styles[jt]}, _JOINT_LABELS[jt]))
        for jt, color in joint_styles.items():
            if jt not in joint_order:
                entries.append(("line", {"color": color}, f"Joint: {jt}"))

        if not entries:
            return

        legend_padding = 16
        legend_line_height = 28
        icon_width = 32
        text_width = max(self.legend_font.measure(entry[2]) for entry in entries)
        legend_width = legend_padding * 2 + icon_width + 10 + text_width
        legend_height = legend_padding * 2 + legend_line_height * len(entries)

        self.create_rectangle(
            8,
            8,
            8 + legend_width,
            8 + legend_height,
            fill="#ffffff",
            outline="#b0bec5",
            tags="legend",
        )

        x0 = 8 + legend_padding
        y0 = 8 + legend_padding

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
                    tags="legend",
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
                    tags="legend",
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
                    tags="legend",
                )

            self.create_text(
                x0 + icon_width + 10,
                y0 + 10,
                anchor="w",
                text=label,
                fill="#212121",
                font=self.legend_font,
                tags="legend",
            )
            y0 += legend_line_height

import json
import os
import re
import threading
import time
import tkinter as tk
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

SESSION_PATH = Path.home() / ".banana_vision_session.json"
DEFAULT_PROJECT_PATH = Path.home() / ".banana_vision_project.json"


def load_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def save_text_file(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def split_blocks(text: str, mode: str, tag: str = "", regex: str = "") -> list[str]:
    if mode == "line":
        return text.splitlines()
    if mode == "blank_lines":
        blocks = []
        current = []
        for line in text.splitlines():
            if line.strip() == "":
                if current:
                    blocks.append("\n".join(current))
                    current = []
                continue
            current.append(line)
        if current:
            blocks.append("\n".join(current))
        return blocks
    if mode == "tag" and tag:
        return [block for block in text.split(tag) if block != ""]
    if mode == "regex" and regex:
        parts = re.split(regex, text)
        return [part for part in parts if part != ""]
    return [text]


def apply_line_break_tags(text: str, tags: list[str]) -> str:
    for tag in tags:
        text = text.replace(tag, "\n")
    return text


def strip_hidden_tags(text: str, pattern: str) -> str:
    if not pattern:
        return text
    return re.sub(pattern, "", text)


def extract_background_tag(text: str, tag_map: dict[str, str]) -> str | None:
    for tag, path in tag_map.items():
        if tag in text:
            return path
    return None


def replace_icon_tags(text: str, icon_map: dict[str, str]) -> str:
    for tag, replacement in icon_map.items():
        text = text.replace(tag, replacement)
    return text


@dataclass
class FontSettings:
    family: str = "Arial"
    size: int = 18
    path: str | None = None
    spacing: int = 4
    outline: int = 0
    shadow: int = 0
    shadow_offset: tuple[int, int] = (2, 2)
    color: str = "#ffffff"
    outline_color: str = "#000000"
    shadow_color: str = "#000000"


@dataclass
class BitmapFontSettings:
    enabled: bool = False
    image_path: str | None = None
    grid_width: int = 16
    grid_height: int = 16
    characters: str = ""
    tint_color: str = "#ffffff"
    background_color: str = "#000000"
    transparent_color: str = "#000000"


@dataclass
class PreviewSettings:
    width: int = 320
    height: int = 120
    zoom: float = 1.0
    background_color: str = "#1e1e1e"
    background_image: str | None = None
    dynamic_backgrounds: dict[str, str] = field(default_factory=dict)
    margin_x: int = 10
    margin_y: int = 10
    align: str = "left"
    position_x: int = 0
    position_y: int = 0


@dataclass
class OverflowSettings:
    max_chars: int = 0
    max_width: int = 0
    max_height: int = 0
    byte_limit: int = 0
    bytes_map: dict[str, int] = field(default_factory=dict)
    compare_limit: bool = False


@dataclass
class ProjectSettings:
    split_mode: str = "blank_lines"
    split_tag: str = ""
    split_regex: str = ""
    line_break_tags: list[str] = field(default_factory=lambda: ["<br>"])
    hide_tag_regex: str = ""
    preview_mode: str = "single"
    font: FontSettings = field(default_factory=FontSettings)
    bitmap_font: BitmapFontSettings = field(default_factory=BitmapFontSettings)
    preview: PreviewSettings = field(default_factory=PreviewSettings)
    overflow: OverflowSettings = field(default_factory=OverflowSettings)
    icon_tags: dict[str, str] = field(default_factory=dict)
    glossary: dict[str, str] = field(default_factory=dict)
    theme: str = "Dark"
    project_name: str = "Banana Vision"


@dataclass
class ScriptData:
    name: str
    blocks: list[str]
    originals_1: list[str] = field(default_factory=list)
    originals_2: list[str] = field(default_factory=list)


class BananaVisionApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Banana Vision - Python Edition")
        self.settings = ProjectSettings()
        self.scripts: list[ScriptData] = []
        self.current_script_index = 0
        self.current_block_index = 0
        self.preview_image: Image.Image | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.session_thread = threading.Thread(target=self._autosave_loop, daemon=True)
        self.session_thread.start()

        self._build_ui()
        self._apply_theme()
        self._load_session()

    def _build_ui(self) -> None:
        self.root.geometry("1200x800")

        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Load Script", command=self.load_script)
        file_menu.add_command(label="Load Original 1", command=lambda: self.load_original(1))
        file_menu.add_command(label="Load Original 2", command=lambda: self.load_original(2))
        file_menu.add_command(label="Save Project", command=self.save_project)
        file_menu.add_command(label="Load Project", command=self.load_project)
        file_menu.add_separator()
        file_menu.add_command(label="Export Preview PNG", command=self.export_preview)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Find/Replace", command=self.open_find_replace)
        tools_menu.add_command(label="Glossary Check", command=self.glossary_check)
        tools_menu.add_command(label="GitHub Sync", command=self.open_github_sync)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Tutorial", command=self.show_tutorial)
        help_menu.add_command(label="Manual", command=self.show_manual)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

        self.main_pane = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        self.left_frame = ttk.Frame(self.main_pane, padding=6)
        self.main_pane.add(self.left_frame, weight=1)

        self.right_frame = ttk.Frame(self.main_pane, padding=6)
        self.main_pane.add(self.right_frame, weight=2)

        self._build_left_panel()
        self._build_right_panel()

    def _build_left_panel(self) -> None:
        header = ttk.Label(self.left_frame, text="Scripts")
        header.pack(anchor=tk.W)

        self.script_listbox = tk.Listbox(self.left_frame, height=6)
        self.script_listbox.pack(fill=tk.X)
        self.script_listbox.bind("<<ListboxSelect>>", self.on_script_select)

        self.block_listbox = tk.Listbox(self.left_frame)
        self.block_listbox.pack(fill=tk.BOTH, expand=True, pady=6)
        self.block_listbox.bind("<<ListboxSelect>>", self.on_block_select)

        navigation = ttk.Frame(self.left_frame)
        navigation.pack(fill=tk.X)
        ttk.Button(navigation, text="Prev", command=self.prev_block).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(navigation, text="Next", command=self.next_block).pack(side=tk.LEFT, expand=True, fill=tk.X)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(self.left_frame, variable=self.progress_var)
        self.progress.pack(fill=tk.X, pady=6)

    def _build_right_panel(self) -> None:
        tabs = ttk.Notebook(self.right_frame)
        tabs.pack(fill=tk.BOTH, expand=True)

        self.editor_tab = ttk.Frame(tabs)
        self.preview_tab = ttk.Frame(tabs)
        self.settings_tab = ttk.Frame(tabs)
        self.fonts_tab = ttk.Frame(tabs)
        self.system_tab = ttk.Frame(tabs)

        tabs.add(self.editor_tab, text="Editor")
        tabs.add(self.preview_tab, text="Preview")
        tabs.add(self.fonts_tab, text="Fonts")
        tabs.add(self.settings_tab, text="Settings")
        tabs.add(self.system_tab, text="System")

        self._build_editor_tab()
        self._build_preview_tab()
        self._build_fonts_tab()
        self._build_settings_tab()
        self._build_system_tab()

    def _build_editor_tab(self) -> None:
        self.editor_text = tk.Text(self.editor_tab, height=12, wrap=tk.WORD)
        self.editor_text.pack(fill=tk.BOTH, expand=True)
        self.editor_text.bind("<KeyRelease>", self.on_editor_change)

        originals_frame = ttk.Frame(self.editor_tab)
        originals_frame.pack(fill=tk.BOTH, expand=True, pady=6)

        self.original_1_text = tk.Text(originals_frame, height=6, wrap=tk.WORD)
        self.original_1_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.original_1_text.configure(state=tk.DISABLED)

        self.original_2_text = tk.Text(originals_frame, height=6, wrap=tk.WORD)
        self.original_2_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.original_2_text.configure(state=tk.DISABLED)

    def _build_preview_tab(self) -> None:
        controls = ttk.Frame(self.preview_tab)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="Mode").pack(side=tk.LEFT)
        self.preview_mode_var = tk.StringVar(value=self.settings.preview_mode)
        ttk.Combobox(controls, textvariable=self.preview_mode_var, values=["single", "all"], width=8).pack(
            side=tk.LEFT
        )
        ttk.Button(controls, text="Render", command=self.render_preview).pack(side=tk.LEFT, padx=4)

        ttk.Label(controls, text="Zoom").pack(side=tk.LEFT, padx=4)
        self.zoom_var = tk.DoubleVar(value=self.settings.preview.zoom)
        ttk.Scale(controls, from_=0.5, to=2.5, orient=tk.HORIZONTAL, variable=self.zoom_var, command=self.on_zoom).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        self.preview_canvas = tk.Label(self.preview_tab)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, pady=6)

        self.preview_status = ttk.Label(self.preview_tab, text="Overflow: OK | Bytes: 0")
        self.preview_status.pack(anchor=tk.W)

    def _build_fonts_tab(self) -> None:
        container = ttk.Frame(self.fonts_tab)
        container.pack(fill=tk.BOTH, expand=True)

        font_frame = ttk.LabelFrame(container, text="System Font")
        font_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(font_frame, text="Family").grid(row=0, column=0, sticky=tk.W)
        self.font_family_var = tk.StringVar(value=self.settings.font.family)
        ttk.Entry(font_frame, textvariable=self.font_family_var).grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(font_frame, text="Size").grid(row=1, column=0, sticky=tk.W)
        self.font_size_var = tk.IntVar(value=self.settings.font.size)
        ttk.Spinbox(font_frame, from_=8, to=96, textvariable=self.font_size_var).grid(row=1, column=1, sticky=tk.EW)

        ttk.Button(font_frame, text="Load TTF/OTF", command=self.load_font).grid(row=0, column=2, padx=4)

        font_frame.columnconfigure(1, weight=1)

        effects_frame = ttk.LabelFrame(container, text="Effects")
        effects_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(effects_frame, text="Outline").grid(row=0, column=0, sticky=tk.W)
        self.outline_var = tk.IntVar(value=self.settings.font.outline)
        ttk.Spinbox(effects_frame, from_=0, to=8, textvariable=self.outline_var).grid(row=0, column=1)

        ttk.Label(effects_frame, text="Shadow").grid(row=1, column=0, sticky=tk.W)
        self.shadow_var = tk.IntVar(value=self.settings.font.shadow)
        ttk.Spinbox(effects_frame, from_=0, to=8, textvariable=self.shadow_var).grid(row=1, column=1)

        bitmap_frame = ttk.LabelFrame(container, text="Bitmap Font")
        bitmap_frame.pack(fill=tk.X, padx=6, pady=6)

        self.bitmap_enabled_var = tk.BooleanVar(value=self.settings.bitmap_font.enabled)
        ttk.Checkbutton(bitmap_frame, text="Enable", variable=self.bitmap_enabled_var).grid(row=0, column=0)
        ttk.Button(bitmap_frame, text="Load Bitmap", command=self.load_bitmap_font).grid(row=0, column=1, padx=4)
        ttk.Label(bitmap_frame, text="Grid W").grid(row=1, column=0)
        self.bitmap_grid_w_var = tk.IntVar(value=self.settings.bitmap_font.grid_width)
        ttk.Spinbox(bitmap_frame, from_=4, to=64, textvariable=self.bitmap_grid_w_var).grid(row=1, column=1)
        ttk.Label(bitmap_frame, text="Grid H").grid(row=2, column=0)
        self.bitmap_grid_h_var = tk.IntVar(value=self.settings.bitmap_font.grid_height)
        ttk.Spinbox(bitmap_frame, from_=4, to=64, textvariable=self.bitmap_grid_h_var).grid(row=2, column=1)
        ttk.Label(bitmap_frame, text="Characters").grid(row=3, column=0, sticky=tk.W)
        self.bitmap_chars_var = tk.StringVar(value=self.settings.bitmap_font.characters)
        ttk.Entry(bitmap_frame, textvariable=self.bitmap_chars_var).grid(row=3, column=1, sticky=tk.EW)
        bitmap_frame.columnconfigure(1, weight=1)

    def _build_settings_tab(self) -> None:
        frame = ttk.Frame(self.settings_tab)
        frame.pack(fill=tk.BOTH, expand=True)

        split_frame = ttk.LabelFrame(frame, text="Block Splitting")
        split_frame.pack(fill=tk.X, padx=6, pady=6)

        self.split_mode_var = tk.StringVar(value=self.settings.split_mode)
        ttk.Combobox(
            split_frame, textvariable=self.split_mode_var, values=["line", "blank_lines", "tag", "regex"]
        ).grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(split_frame, text="Mode").grid(row=0, column=0, sticky=tk.W)
        ttk.Label(split_frame, text="Tag").grid(row=1, column=0, sticky=tk.W)
        self.split_tag_var = tk.StringVar(value=self.settings.split_tag)
        ttk.Entry(split_frame, textvariable=self.split_tag_var).grid(row=1, column=1, sticky=tk.EW)
        ttk.Label(split_frame, text="Regex").grid(row=2, column=0, sticky=tk.W)
        self.split_regex_var = tk.StringVar(value=self.settings.split_regex)
        ttk.Entry(split_frame, textvariable=self.split_regex_var).grid(row=2, column=1, sticky=tk.EW)
        split_frame.columnconfigure(1, weight=1)

        preview_frame = ttk.LabelFrame(frame, text="Preview")
        preview_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(preview_frame, text="Width").grid(row=0, column=0)
        self.preview_width_var = tk.IntVar(value=self.settings.preview.width)
        ttk.Spinbox(preview_frame, from_=64, to=1024, textvariable=self.preview_width_var).grid(row=0, column=1)
        ttk.Label(preview_frame, text="Height").grid(row=1, column=0)
        self.preview_height_var = tk.IntVar(value=self.settings.preview.height)
        ttk.Spinbox(preview_frame, from_=64, to=1024, textvariable=self.preview_height_var).grid(row=1, column=1)
        ttk.Label(preview_frame, text="Background Color").grid(row=2, column=0)
        self.preview_bg_var = tk.StringVar(value=self.settings.preview.background_color)
        ttk.Entry(preview_frame, textvariable=self.preview_bg_var).grid(row=2, column=1, sticky=tk.EW)
        ttk.Button(preview_frame, text="Load Background", command=self.load_background).grid(row=2, column=2, padx=4)
        preview_frame.columnconfigure(1, weight=1)

        tag_frame = ttk.LabelFrame(frame, text="Tags")
        tag_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(tag_frame, text="Line break tags (comma)").grid(row=0, column=0, sticky=tk.W)
        self.line_break_var = tk.StringVar(value=",".join(self.settings.line_break_tags))
        ttk.Entry(tag_frame, textvariable=self.line_break_var).grid(row=0, column=1, sticky=tk.EW)

        ttk.Label(tag_frame, text="Hide tag regex").grid(row=1, column=0, sticky=tk.W)
        self.hide_tag_var = tk.StringVar(value=self.settings.hide_tag_regex)
        ttk.Entry(tag_frame, textvariable=self.hide_tag_var).grid(row=1, column=1, sticky=tk.EW)
        tag_frame.columnconfigure(1, weight=1)

        overflow_frame = ttk.LabelFrame(frame, text="Overflow")
        overflow_frame.pack(fill=tk.X, padx=6, pady=6)

        ttk.Label(overflow_frame, text="Max chars").grid(row=0, column=0)
        self.max_chars_var = tk.IntVar(value=self.settings.overflow.max_chars)
        ttk.Spinbox(overflow_frame, from_=0, to=9999, textvariable=self.max_chars_var).grid(row=0, column=1)
        ttk.Label(overflow_frame, text="Byte limit").grid(row=1, column=0)
        self.byte_limit_var = tk.IntVar(value=self.settings.overflow.byte_limit)
        ttk.Spinbox(overflow_frame, from_=0, to=9999, textvariable=self.byte_limit_var).grid(row=1, column=1)

    def _build_system_tab(self) -> None:
        frame = ttk.Frame(self.system_tab)
        frame.pack(fill=tk.BOTH, expand=True)

        theme_frame = ttk.LabelFrame(frame, text="Themes")
        theme_frame.pack(fill=tk.X, padx=6, pady=6)

        self.theme_var = tk.StringVar(value=self.settings.theme)
        ttk.Combobox(theme_frame, textvariable=self.theme_var, values=["Light", "Dark", "Banana", "Custom"]).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(theme_frame, text="Apply", command=self._apply_theme).pack(side=tk.LEFT, padx=4)

        addon_frame = ttk.LabelFrame(frame, text="Add-ons")
        addon_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(addon_frame, text="Load Add-on JSON", command=self.load_addon).pack(side=tk.LEFT)

        profile_frame = ttk.LabelFrame(frame, text="Profiles")
        profile_frame.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(profile_frame, text="Save Profile", command=self.save_profile).pack(side=tk.LEFT)
        ttk.Button(profile_frame, text="Load Profile", command=self.load_profile).pack(side=tk.LEFT, padx=4)

    def load_script(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not paths:
            return
        for path in paths:
            text = load_text_file(path)
            blocks = split_blocks(text, self.split_mode_var.get(), self.split_tag_var.get(), self.split_regex_var.get())
            blocks = [apply_line_break_tags(block, self._line_break_tags()) for block in blocks]
            self.scripts.append(ScriptData(name=os.path.basename(path), blocks=blocks))
            self.script_listbox.insert(tk.END, os.path.basename(path))
        self.current_script_index = len(self.scripts) - 1
        self.refresh_blocks()

    def load_original(self, slot: int) -> None:
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All", "*.*")])
        if not path or not self.scripts:
            return
        text = load_text_file(path)
        blocks = split_blocks(text, self.split_mode_var.get(), self.split_tag_var.get(), self.split_regex_var.get())
        blocks = [apply_line_break_tags(block, self._line_break_tags()) for block in blocks]
        script = self.scripts[self.current_script_index]
        if slot == 1:
            script.originals_1 = blocks
        else:
            script.originals_2 = blocks
        self.refresh_editor()

    def refresh_blocks(self) -> None:
        self.block_listbox.delete(0, tk.END)
        if not self.scripts:
            return
        script = self.scripts[self.current_script_index]
        for idx, _block in enumerate(script.blocks):
            self.block_listbox.insert(tk.END, f"Block {idx + 1}")
        self.current_block_index = 0
        if script.blocks:
            self.block_listbox.selection_set(0)
        self.refresh_editor()
        self.update_progress()

    def refresh_editor(self) -> None:
        if not self.scripts:
            return
        script = self.scripts[self.current_script_index]
        if not script.blocks:
            return
        self.editor_text.delete("1.0", tk.END)
        self.editor_text.insert(tk.END, script.blocks[self.current_block_index])

        self._set_text_widget(self.original_1_text, self._get_original_text(script.originals_1))
        self._set_text_widget(self.original_2_text, self._get_original_text(script.originals_2))

        self.render_preview()

    def _get_original_text(self, blocks: list[str]) -> str:
        if self.current_block_index < len(blocks):
            return blocks[self.current_block_index]
        return ""

    def on_script_select(self, _event: tk.Event) -> None:
        selection = self.script_listbox.curselection()
        if not selection:
            return
        self.current_script_index = selection[0]
        self.refresh_blocks()

    def on_block_select(self, _event: tk.Event) -> None:
        selection = self.block_listbox.curselection()
        if not selection:
            return
        self.current_block_index = selection[0]
        self.refresh_editor()

    def on_editor_change(self, _event: tk.Event) -> None:
        if not self.scripts:
            return
        content = self.editor_text.get("1.0", tk.END).rstrip("\n")
        self.scripts[self.current_script_index].blocks[self.current_block_index] = content
        self.render_preview()
        self.update_progress()

    def prev_block(self) -> None:
        if self.current_block_index > 0:
            self.current_block_index -= 1
            self.block_listbox.selection_clear(0, tk.END)
            self.block_listbox.selection_set(self.current_block_index)
            self.refresh_editor()

    def next_block(self) -> None:
        if not self.scripts:
            return
        script = self.scripts[self.current_script_index]
        if self.current_block_index < len(script.blocks) - 1:
            self.current_block_index += 1
            self.block_listbox.selection_clear(0, tk.END)
            self.block_listbox.selection_set(self.current_block_index)
            self.refresh_editor()

    def update_progress(self) -> None:
        if not self.scripts:
            self.progress_var.set(0)
            return
        script = self.scripts[self.current_script_index]
        translated = sum(1 for block in script.blocks if block.strip())
        total = max(len(script.blocks), 1)
        self.progress_var.set(translated / total * 100)

    def render_preview(self) -> None:
        if not self.scripts:
            return
        self._sync_settings()
        script = self.scripts[self.current_script_index]
        self.settings.preview_mode = self.preview_mode_var.get()
        if self.settings.preview_mode == "all":
            self.preview_image = self._render_all_blocks(script)
        else:
            self.preview_image = self._render_block(script.blocks[self.current_block_index])
        self._update_preview_canvas()

    def _render_block(self, text: str) -> Image.Image:
        settings = self.settings
        width = settings.preview.width
        height = settings.preview.height

        background = self._load_background_for_text(text)
        image = background.copy()
        draw = ImageDraw.Draw(image)

        processed = self._process_text_for_preview(text)
        font = self._get_font()

        if settings.font.shadow:
            self._draw_text(draw, processed, font, (settings.preview.margin_x + settings.font.shadow_offset[0],
                                                   settings.preview.margin_y + settings.font.shadow_offset[1]),
                            settings.font.shadow_color, outline=0)

        if settings.font.outline:
            self._draw_text(draw, processed, font, (settings.preview.margin_x, settings.preview.margin_y),
                            settings.font.outline_color, outline=settings.font.outline)

        self._draw_text(draw, processed, font, (settings.preview.margin_x, settings.preview.margin_y), settings.font.color)

        overflow = self._check_overflow(processed, font, width, height)
        bytes_used = self._count_bytes(processed)
        status = f"Overflow: {'YES' if overflow else 'OK'} | Bytes: {bytes_used}"
        self.preview_status.configure(text=status)

        return image

    def _render_all_blocks(self, script: ScriptData) -> Image.Image:
        settings = self.settings
        cols = 3
        cell_w = settings.preview.width
        cell_h = settings.preview.height
        rows = max(1, (len(script.blocks) + cols - 1) // cols)
        image = Image.new("RGBA", (cell_w * cols, cell_h * rows), settings.preview.background_color)
        for idx, block in enumerate(script.blocks):
            row = idx // cols
            col = idx % cols
            block_image = self._render_block(block)
            image.paste(block_image, (col * cell_w, row * cell_h))
        return image

    def _process_text_for_preview(self, text: str) -> str:
        processed = apply_line_break_tags(text, self._line_break_tags())
        processed = strip_hidden_tags(processed, self.settings.hide_tag_regex)
        processed = replace_icon_tags(processed, self.settings.icon_tags)
        return processed

    def _load_background_for_text(self, text: str) -> Image.Image:
        settings = self.settings
        background_path = extract_background_tag(text, settings.preview.dynamic_backgrounds) or settings.preview.background_image
        if background_path and os.path.exists(background_path):
            image = Image.open(background_path).convert("RGBA").resize((settings.preview.width, settings.preview.height))
        else:
            image = Image.new("RGBA", (settings.preview.width, settings.preview.height), settings.preview.background_color)
        return image

    def _get_font(self) -> ImageFont.FreeTypeFont:
        if self.settings.bitmap_font.enabled and self.settings.bitmap_font.image_path:
            return ImageFont.load_default()
        if self.settings.font.path:
            return ImageFont.truetype(self.settings.font.path, self.settings.font.size)
        return ImageFont.truetype(self.settings.font.family, self.settings.font.size)

    def _draw_text(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        font: ImageFont.FreeTypeFont,
        position: tuple[int, int],
        color: str,
        outline: int = 0,
    ) -> None:
        x, y = position
        if outline > 0:
            for ox in range(-outline, outline + 1):
                for oy in range(-outline, outline + 1):
                    draw.text((x + ox, y + oy), text, font=font, fill=color)
        else:
            draw.text((x, y), text, font=font, fill=color)

    def _check_overflow(self, text: str, font: ImageFont.FreeTypeFont, width: int, height: int) -> bool:
        if self.settings.overflow.max_chars and len(text) > self.settings.overflow.max_chars:
            return True
        if self.settings.overflow.max_width or self.settings.overflow.max_height:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            if self.settings.overflow.max_width and text_w > self.settings.overflow.max_width:
                return True
            if self.settings.overflow.max_height and text_h > self.settings.overflow.max_height:
                return True
        if width and height:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            if text_w > width - self.settings.preview.margin_x * 2:
                return True
            if text_h > height - self.settings.preview.margin_y * 2:
                return True
        if self.settings.overflow.byte_limit and self._count_bytes(text) > self.settings.overflow.byte_limit:
            return True
        return False

    def _count_bytes(self, text: str) -> int:
        if not self.settings.overflow.bytes_map:
            return len(text.encode("utf-8"))
        return sum(self.settings.overflow.bytes_map.get(char, 1) for char in text)

    def _update_preview_canvas(self) -> None:
        if not self.preview_image:
            return
        zoom = self.zoom_var.get()
        size = (int(self.preview_image.width * zoom), int(self.preview_image.height * zoom))
        display_image = self.preview_image.resize(size, Image.NEAREST)
        self.preview_photo = ImageTk.PhotoImage(display_image)
        self.preview_canvas.configure(image=self.preview_photo)

    def on_zoom(self, _value: str) -> None:
        self.render_preview()

    def export_preview(self) -> None:
        if not self.preview_image:
            messagebox.showinfo("Preview", "Nothing to export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG", "*.png")])
        if not path:
            return
        self.preview_image.save(path)
        messagebox.showinfo("Preview", f"Saved to {path}.")

    def load_font(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Font", "*.ttf *.otf")])
        if not path:
            return
        self.settings.font.path = path
        self.render_preview()

    def load_bitmap_font(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Image", "*.png *.bmp")])
        if not path:
            return
        self.settings.bitmap_font.image_path = path
        self.render_preview()

    def load_background(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Image", "*.png *.jpg *.jpeg")])
        if not path:
            return
        self.settings.preview.background_image = path
        self.render_preview()

    def open_find_replace(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Find/Replace")
        ttk.Label(dialog, text="Find").grid(row=0, column=0)
        find_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=find_var).grid(row=0, column=1)
        ttk.Label(dialog, text="Replace").grid(row=1, column=0)
        replace_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=replace_var).grid(row=1, column=1)
        scope_var = tk.StringVar(value="current")
        ttk.Combobox(dialog, textvariable=scope_var, values=["current", "script", "all"]).grid(row=2, column=1)

        def run_replace() -> None:
            target = find_var.get()
            replacement = replace_var.get()
            if not target:
                return
            if scope_var.get() == "current":
                content = self.editor_text.get("1.0", tk.END)
                self.editor_text.delete("1.0", tk.END)
                self.editor_text.insert(tk.END, content.replace(target, replacement))
                self.on_editor_change(None)
            elif scope_var.get() == "script":
                script = self.scripts[self.current_script_index]
                script.blocks = [block.replace(target, replacement) for block in script.blocks]
                self.refresh_editor()
            else:
                for script in self.scripts:
                    script.blocks = [block.replace(target, replacement) for block in script.blocks]
                self.refresh_editor()
            dialog.destroy()

        ttk.Button(dialog, text="Replace", command=run_replace).grid(row=3, column=1)

    def glossary_check(self) -> None:
        if not self.settings.glossary:
            messagebox.showinfo("Glossary", "No glossary loaded.")
            return
        missing = []
        script = self.scripts[self.current_script_index]
        for term, translation in self.settings.glossary.items():
            if term in script.blocks[self.current_block_index] and translation not in script.blocks[self.current_block_index]:
                missing.append(term)
        if missing:
            messagebox.showwarning("Glossary", f"Missing translations for: {', '.join(missing)}")
        else:
            messagebox.showinfo("Glossary", "Glossary terms applied.")

    def open_github_sync(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("GitHub Sync")
        ttk.Label(dialog, text="Repo (owner/name)").grid(row=0, column=0)
        repo_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=repo_var).grid(row=0, column=1)
        ttk.Label(dialog, text="File path").grid(row=1, column=0)
        path_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=path_var).grid(row=1, column=1)
        ttk.Label(dialog, text="Token").grid(row=2, column=0)
        token_var = tk.StringVar()
        ttk.Entry(dialog, textvariable=token_var, show="*").grid(row=2, column=1)

        def load_file() -> None:
            import base64
            import urllib.request

            repo = repo_var.get().strip()
            path = path_var.get().strip()
            token = token_var.get().strip()
            if not repo or not path:
                return
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            req = urllib.request.Request(url)
            if token:
                req.add_header("Authorization", f"token {token}")
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = base64.b64decode(data["content"]).decode("utf-8")
            blocks = split_blocks(content, self.split_mode_var.get(), self.split_tag_var.get(), self.split_regex_var.get())
            self.scripts.append(ScriptData(name=os.path.basename(path), blocks=blocks))
            self.script_listbox.insert(tk.END, os.path.basename(path))
            self.current_script_index = len(self.scripts) - 1
            self.refresh_blocks()
            dialog.destroy()

        def save_file() -> None:
            import base64
            import urllib.request

            repo = repo_var.get().strip()
            path = path_var.get().strip()
            token = token_var.get().strip()
            if not repo or not path or not token:
                return
            script = self.scripts[self.current_script_index]
            content = "\n\n".join(script.blocks)
            payload = {
                "message": "Update from Banana Vision",
                "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
            }
            url = f"https://api.github.com/repos/{repo}/contents/{path}"
            req = urllib.request.Request(url, method="PUT")
            req.add_header("Authorization", f"token {token}")
            req.add_header("Content-Type", "application/json")
            req.data = json.dumps(payload).encode("utf-8")
            with urllib.request.urlopen(req) as response:
                response.read()
            dialog.destroy()

        ttk.Button(dialog, text="Load", command=load_file).grid(row=3, column=0)
        ttk.Button(dialog, text="Save", command=save_file).grid(row=3, column=1)

    def show_tutorial(self) -> None:
        messagebox.showinfo(
            "Tutorial",
            "1. Load your script files.\n2. Choose a block and edit the translation.\n3. Configure the preview settings and fonts.\n4. Export previews or save your project.",
        )

    def show_manual(self) -> None:
        messagebox.showinfo(
            "Manual",
            "Banana Vision (Python) supports block splitting, previews, overflow checks, and GitHub sync.\n"
            "Use the Settings tab to configure tags, preview box, and overflow limits.",
        )

    def save_project(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if not path:
            return
        self._sync_settings()
        data = {
            "settings": self._settings_to_dict(),
            "scripts": [self._script_to_dict(script) for script in self.scripts],
        }
        save_text_file(path, json.dumps(data, indent=2))

    def load_project(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Project", "*.json")])
        if not path:
            return
        data = json.loads(load_text_file(path))
        self.settings = self._settings_from_dict(data.get("settings", {}))
        self.scripts = [self._script_from_dict(item) for item in data.get("scripts", [])]
        self._sync_ui_from_settings()
        self.script_listbox.delete(0, tk.END)
        for script in self.scripts:
            self.script_listbox.insert(tk.END, script.name)
        self.current_script_index = 0
        self.refresh_blocks()

    def save_profile(self) -> None:
        path = filedialog.asksaveasfilename(defaultextension=".json")
        if not path:
            return
        self._sync_settings()
        save_text_file(path, json.dumps(self._settings_to_dict(), indent=2))

    def load_profile(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("Profile", "*.json")])
        if not path:
            return
        settings_data = json.loads(load_text_file(path))
        self.settings = self._settings_from_dict(settings_data)
        self._sync_ui_from_settings()
        self.render_preview()

    def load_addon(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        addon = json.loads(load_text_file(path))
        theme = addon.get("theme", {})
        self._apply_custom_theme(theme)

    def _apply_theme(self) -> None:
        theme = self.theme_var.get() if hasattr(self, "theme_var") else self.settings.theme
        self.settings.theme = theme
        if theme == "Light":
            self.root.configure(bg="#f5f5f5")
        elif theme == "Banana":
            self.root.configure(bg="#ffe066")
        elif theme == "Custom":
            self.root.configure(bg="#2e2e2e")
        else:
            self.root.configure(bg="#1e1e1e")

    def _apply_custom_theme(self, theme: dict[str, str]) -> None:
        background = theme.get("background", "#1e1e1e")
        self.root.configure(bg=background)

    def _sync_settings(self) -> None:
        self.settings.split_mode = self.split_mode_var.get()
        self.settings.split_tag = self.split_tag_var.get()
        self.settings.split_regex = self.split_regex_var.get()
        self.settings.preview.width = self.preview_width_var.get()
        self.settings.preview.height = self.preview_height_var.get()
        self.settings.preview.background_color = self.preview_bg_var.get()
        self.settings.line_break_tags = self._line_break_tags()
        self.settings.hide_tag_regex = self.hide_tag_var.get()
        self.settings.preview.zoom = self.zoom_var.get()
        self.settings.font.family = self.font_family_var.get()
        self.settings.font.size = self.font_size_var.get()
        self.settings.font.outline = self.outline_var.get()
        self.settings.font.shadow = self.shadow_var.get()
        self.settings.bitmap_font.enabled = self.bitmap_enabled_var.get()
        self.settings.bitmap_font.grid_width = self.bitmap_grid_w_var.get()
        self.settings.bitmap_font.grid_height = self.bitmap_grid_h_var.get()
        self.settings.bitmap_font.characters = self.bitmap_chars_var.get()
        self.settings.overflow.max_chars = self.max_chars_var.get()
        self.settings.overflow.byte_limit = self.byte_limit_var.get()

    def _sync_ui_from_settings(self) -> None:
        self.split_mode_var.set(self.settings.split_mode)
        self.split_tag_var.set(self.settings.split_tag)
        self.split_regex_var.set(self.settings.split_regex)
        self.preview_width_var.set(self.settings.preview.width)
        self.preview_height_var.set(self.settings.preview.height)
        self.preview_bg_var.set(self.settings.preview.background_color)
        self.line_break_var.set(",".join(self.settings.line_break_tags))
        self.hide_tag_var.set(self.settings.hide_tag_regex)
        self.zoom_var.set(self.settings.preview.zoom)
        self.font_family_var.set(self.settings.font.family)
        self.font_size_var.set(self.settings.font.size)
        self.outline_var.set(self.settings.font.outline)
        self.shadow_var.set(self.settings.font.shadow)
        self.bitmap_enabled_var.set(self.settings.bitmap_font.enabled)
        self.bitmap_grid_w_var.set(self.settings.bitmap_font.grid_width)
        self.bitmap_grid_h_var.set(self.settings.bitmap_font.grid_height)
        self.bitmap_chars_var.set(self.settings.bitmap_font.characters)
        self.max_chars_var.set(self.settings.overflow.max_chars)
        self.byte_limit_var.set(self.settings.overflow.byte_limit)
        self.theme_var.set(self.settings.theme)

    def _line_break_tags(self) -> list[str]:
        tags = [tag.strip() for tag in self.line_break_var.get().split(",") if tag.strip()]
        return tags

    def _settings_to_dict(self) -> dict:
        return json.loads(json.dumps(self.settings, default=lambda o: o.__dict__))

    def _settings_from_dict(self, data: dict) -> ProjectSettings:
        font = FontSettings(**data.get("font", {}))
        bitmap = BitmapFontSettings(**data.get("bitmap_font", {}))
        preview = PreviewSettings(**data.get("preview", {}))
        overflow = OverflowSettings(**data.get("overflow", {}))
        return ProjectSettings(
            split_mode=data.get("split_mode", "blank_lines"),
            split_tag=data.get("split_tag", ""),
            split_regex=data.get("split_regex", ""),
            line_break_tags=data.get("line_break_tags", ["<br>"]),
            hide_tag_regex=data.get("hide_tag_regex", ""),
            preview_mode=data.get("preview_mode", "single"),
            font=font,
            bitmap_font=bitmap,
            preview=preview,
            overflow=overflow,
            icon_tags=data.get("icon_tags", {}),
            glossary=data.get("glossary", {}),
            theme=data.get("theme", "Dark"),
            project_name=data.get("project_name", "Banana Vision"),
        )

    def _script_to_dict(self, script: ScriptData) -> dict:
        return {
            "name": script.name,
            "blocks": script.blocks,
            "originals_1": script.originals_1,
            "originals_2": script.originals_2,
        }

    def _script_from_dict(self, data: dict) -> ScriptData:
        return ScriptData(
            name=data.get("name", "Script"),
            blocks=data.get("blocks", []),
            originals_1=data.get("originals_1", []),
            originals_2=data.get("originals_2", []),
        )

    def _set_text_widget(self, widget: tk.Text, content: str) -> None:
        widget.configure(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, content)
        widget.configure(state=tk.DISABLED)

    def _autosave_loop(self) -> None:
        while True:
            time.sleep(10)
            self._autosave_session()

    def _autosave_session(self) -> None:
        data = {
            "settings": self._settings_to_dict(),
            "scripts": [self._script_to_dict(script) for script in self.scripts],
            "current_script_index": self.current_script_index,
            "current_block_index": self.current_block_index,
        }
        try:
            save_text_file(SESSION_PATH, json.dumps(data))
        except OSError:
            return

    def _load_session(self) -> None:
        if not SESSION_PATH.exists():
            return
        try:
            data = json.loads(load_text_file(str(SESSION_PATH)))
        except json.JSONDecodeError:
            return
        self.settings = self._settings_from_dict(data.get("settings", {}))
        self.scripts = [self._script_from_dict(item) for item in data.get("scripts", [])]
        self.current_script_index = data.get("current_script_index", 0)
        self.current_block_index = data.get("current_block_index", 0)
        self._sync_ui_from_settings()
        self.script_listbox.delete(0, tk.END)
        for script in self.scripts:
            self.script_listbox.insert(tk.END, script.name)
        self.refresh_blocks()


def main() -> None:
    root = tk.Tk()
    BananaVisionApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()

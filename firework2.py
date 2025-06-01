import tkinter as tk
from tkinter import ttk
from tkinter import filedialog, messagebox, simpledialog
import math
import uuid
import copy # For deep copying states
import json
from collections import defaultdict

try:
    from PIL import ImageGrab, Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Pillow library not found. Export to image feature will be disabled.")
    print("Install Pillow with: pip install Pillow")

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
        self.widget.bind("<ButtonPress>", self.hide_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.text:
            return
        if not event: 
            return

        x = event.x_root + 15
        y = event.y_root + 10

        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tooltip_window, text=self.text, justify=tk.LEFT,
                          background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                          font=("tahoma", "8", "normal"), padding=(5, 3))
        label.pack(ipadx=1)

    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
        self.tooltip_window = None

class TubeRecolorDialog(tk.Toplevel):
    """
    Dialog window for individually recoloring tubes of a selected rack.
    """
    def __init__(self, parent, rack_config_original, planner_instance, visual_rotation_angle, 
                 global_start_tube_number_for_rack=0, use_global_numbering_in_dialog=False):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()

        self.rack_config_original = rack_config_original 
        self.planner = planner_instance
        self.visual_rotation_angle = visual_rotation_angle
        self.global_start_tube_number_for_rack = global_start_tube_number_for_rack
        self.use_global_numbering_in_dialog = use_global_numbering_in_dialog

        self.current_tubes_data_copy = copy.deepcopy(rack_config_original['tubes'])
        self.num_tubes = len(self.current_tubes_data_copy)
        self.selected_indices_in_dialog = set() 
        self.tube_canvas_mapping = {} 

        self.title(f"Recolor Tubes for Rack: {rack_config_original.get('name', rack_config_original['id'][-6:])}")
        self.resizable(False, False)

        self._padding = 10
        self._tube_size = 25
        self._spacing = 5
        self._segment_visual_spacing = 8 
        self._font_size = 7 if self._tube_size < 25 else 8
        self._text_offset = self._tube_size / 2

        self._setup_widgets()
        self._draw_tubes_on_dialog_canvas_initial() 

        self.update_idletasks() 
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        max_dialog_width = parent_width * 0.9
        max_dialog_height = parent_height * 0.9

        if dialog_width > max_dialog_width:
            dialog_width = int(max_dialog_width)
        if dialog_height > max_dialog_height:
            dialog_height = int(max_dialog_height)
        
        self.geometry(f"{dialog_width}x{dialog_height}")
        self.update_idletasks() 

        current_dialog_width = self.winfo_width()
        current_dialog_height = self.winfo_height()

        x_pos = parent_x + (parent_width - current_dialog_width) // 2
        y_pos = parent_y + (parent_height - current_dialog_height) // 2
        self.geometry(f"+{x_pos}+{y_pos}")


    def _setup_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        controls_frame = ttk.Frame(main_frame, padding="5")
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(controls_frame, text="Select Color:").pack(side=tk.LEFT, padx=(0, 5))
        self.color_var = tk.StringVar(value=self.planner.FUSE_COLOR_CHOICES[0])
        color_combo = ttk.Combobox(controls_frame, textvariable=self.color_var,
                                   values=self.planner.FUSE_COLOR_CHOICES, state="readonly", width=15)
        color_combo.pack(side=tk.LEFT, padx=5)
        ToolTip(color_combo, "Choose the color to apply to selected tubes.")
        apply_btn = ttk.Button(controls_frame, text="Apply to Selected Tubes",
                               command=self._apply_color_to_selected_dialog_tubes)
        apply_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(apply_btn, "Applies the chosen color to all currently selected tubes in this dialog.")

        canvas_outer_frame = ttk.Frame(main_frame) 
        canvas_outer_frame.pack(expand=True, fill=tk.BOTH, pady=5)
        self.tubes_canvas = tk.Canvas(canvas_outer_frame, bg="white", highlightthickness=0)
        self.tubes_canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=2, pady=2) 
        ToolTip(self.tubes_canvas, "Click on tubes to select/deselect them for recoloring.")

        action_buttons_frame = ttk.Frame(main_frame, padding="5")
        action_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        action_buttons_frame.columnconfigure(0, weight=1) 
        action_buttons_frame.columnconfigure(1, weight=1)
        self.select_all_btn = ttk.Button(action_buttons_frame, text="Select All", command=self._select_all_tubes)
        self.select_all_btn.grid(row=0, column=0, sticky=tk.E, padx=5)
        ToolTip(self.select_all_btn, "Selects all tubes in this dialog.")
        self.deselect_all_btn = ttk.Button(action_buttons_frame, text="Deselect All", command=self._deselect_all_tubes)
        self.deselect_all_btn.grid(row=0, column=1, sticky=tk.W, padx=5)
        ToolTip(self.deselect_all_btn, "Deselects all currently selected tubes.")

        dialog_buttons_frame = ttk.Frame(main_frame, padding="5")
        dialog_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        dialog_buttons_frame.columnconfigure(0, weight=1) 
        dialog_buttons_frame.columnconfigure(1, weight=0) 
        dialog_buttons_frame.columnconfigure(2, weight=0) 
        dialog_buttons_frame.columnconfigure(3, weight=1) 
        done_btn = ttk.Button(dialog_buttons_frame, text="Done", command=self._confirm_changes, style="Accent.TButton")
        done_btn.grid(row=0, column=1, padx=5)
        ToolTip(done_btn, "Apply all changes made in this dialog to the rack and close.")
        cancel_btn = ttk.Button(dialog_buttons_frame, text="Cancel", command=self.destroy)
        cancel_btn.grid(row=0, column=2, padx=5)
        ToolTip(cancel_btn, "Close this dialog without applying any changes.")

    def _update_tube_visual(self, tube_idx):
        if tube_idx in self.tube_canvas_mapping:
            rect_id, _ = self.tube_canvas_mapping[tube_idx]
            fill_color = self.current_tubes_data_copy[tube_idx]['color'] 
            outline_color = "blue" if tube_idx in self.selected_indices_in_dialog else "grey"
            outline_width = 2 if tube_idx in self.selected_indices_in_dialog else 1
            self.tubes_canvas.itemconfig(rect_id, fill=fill_color, outline=outline_color, width=outline_width)

    def _draw_tubes_on_dialog_canvas_initial(self):
        self.tubes_canvas.delete("all")
        self.tube_canvas_mapping.clear()

        original_configured_cols = self.rack_config_original['x_tubes'] 
        original_configured_rows = self.rack_config_original['y_tubes'] 
        rack_type = self.rack_config_original['type']

        if rack_type == "Crate":
            if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                dialog_display_cols = original_configured_rows 
                dialog_display_rows = original_configured_cols
            else: # 0 or 180
                dialog_display_cols = original_configured_cols
                dialog_display_rows = original_configured_rows
            canvas_width = (2 * self._padding + dialog_display_cols * (self._tube_size + self._spacing) - self._spacing)
            canvas_height = (2 * self._padding + dialog_display_rows * (self._tube_size + self._spacing) - self._spacing)

        elif rack_type == "Fan":
            num_fans_original = original_configured_cols
            tubes_per_fan_original = original_configured_rows

            if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                dialog_display_cols = tubes_per_fan_original
                dialog_display_rows = num_fans_original
                # Width is based on tubes_per_fan (new columns), height on num_fans (new rows)
                canvas_width = (2 * self._padding + dialog_display_cols * self._tube_size +
                                    max(0, dialog_display_cols - 1) * self._spacing) # Spacing between tubes
                canvas_height = (2 * self._padding + dialog_display_rows * self._tube_size +
                                     max(0, dialog_display_rows - 1) * self._segment_visual_spacing) # Spacing between original segments (now rows)
            else: # 0 or 180 degrees
                dialog_display_cols = num_fans_original
                dialog_display_rows = tubes_per_fan_original
                canvas_width = (2 * self._padding + dialog_display_cols * self._tube_size +
                                    max(0, dialog_display_cols - 1) * self._segment_visual_spacing) # Spacing between segments
                canvas_height = (2 * self._padding + dialog_display_rows * self._tube_size +
                                max(0, dialog_display_rows - 1) * self._spacing) # Spacing between tubes vertically
        
        self.tubes_canvas.config(width=max(150, canvas_width), height=max(80, canvas_height)) 

        for i in range(self.num_tubes):
            original_col_idx = i % original_configured_cols
            original_row_idx = i // original_configured_cols 

            clickable_group_tag = f"clickable_tube_area_{i}" 

            if rack_type == "Crate":
                if self.visual_rotation_angle == 0: 
                    dialog_visual_col = original_col_idx
                    dialog_visual_row = original_row_idx
                elif self.visual_rotation_angle == 90: 
                    dialog_visual_col = original_row_idx 
                    dialog_visual_row = original_configured_cols - 1 - original_col_idx
                elif self.visual_rotation_angle == 180: 
                    dialog_visual_col = original_configured_cols - 1 - original_col_idx
                    dialog_visual_row = original_configured_rows - 1 - original_row_idx
                elif self.visual_rotation_angle == 270: 
                    dialog_visual_col = original_configured_rows - 1 - original_row_idx
                    dialog_visual_row = original_col_idx
                
                x1 = self._padding + dialog_visual_col * (self._tube_size + self._spacing)
                y1 = self._padding + dialog_visual_row * (self._tube_size + self._spacing)

            elif rack_type == "Fan":
                num_fans = original_configured_cols
                tubes_per_fan = original_configured_rows
                segment_idx = i // tubes_per_fan 
                tube_in_segment_idx = i % tubes_per_fan
                
                # Determine visual column and row based on rotation
                if self.visual_rotation_angle == 0:
                    dialog_visual_col = segment_idx
                    dialog_visual_row = tube_in_segment_idx
                elif self.visual_rotation_angle == 90:
                    dialog_visual_col = tube_in_segment_idx
                    dialog_visual_row = num_fans - 1 - segment_idx
                elif self.visual_rotation_angle == 180:
                    dialog_visual_col = num_fans - 1 - segment_idx
                    dialog_visual_row = tubes_per_fan - 1 - tube_in_segment_idx
                elif self.visual_rotation_angle == 270:
                    dialog_visual_col = tubes_per_fan - 1 - tube_in_segment_idx
                    dialog_visual_row = segment_idx
                else: # Default to 0 degree orientation
                    dialog_visual_col = segment_idx
                    dialog_visual_row = tube_in_segment_idx
                
                # Determine x1, y1 based on the *dialog's* display columns/rows and appropriate spacing
                if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                    # When rotated, the "columns" in the dialog are tubes_per_fan, "rows" are num_fans
                    x1 = self._padding + dialog_visual_col * (self._tube_size + self._spacing) # Spacing between tubes
                    y1 = self._padding + dialog_visual_row * (self._tube_size + self._segment_visual_spacing) # Spacing between original segments
                else: # 0 or 180
                    x1 = self._padding + dialog_visual_col * (self._tube_size + self._segment_visual_spacing)
                    y1 = self._padding + dialog_visual_row * (self._tube_size + self._spacing)

            x2 = x1 + self._tube_size
            y2 = y1 + self._tube_size
            color_val = self.current_tubes_data_copy[i]['color'] 

            if self.use_global_numbering_in_dialog:
                # Display the global number based on the original tube index 'i'
                display_tube_number = str(self.global_start_tube_number_for_rack + i + 1)
            else:
                display_tube_number = str(i + 1)

            rect_id = self.tubes_canvas.create_rectangle(x1, y1, x2, y2, fill=color_val, outline="grey", width=1, tags=(f"rect_for_tube_{i}", clickable_group_tag))
            text_id = self.tubes_canvas.create_text(x1 + self._text_offset, y1 + self._text_offset, text=display_tube_number, fill="black", tags=(f"text_for_tube_{i}", clickable_group_tag), font=("Arial", self._font_size))

            self.tube_canvas_mapping[i] = (rect_id, text_id)
            self.tubes_canvas.tag_raise(text_id, rect_id) 
            self.tubes_canvas.tag_bind(clickable_group_tag, "<Button-1>", lambda e, idx=i: self._handle_specific_tube_click(idx))
            self._update_tube_visual(i) 

    def _handle_specific_tube_click(self, tube_idx):
        if tube_idx in self.selected_indices_in_dialog:
            self.selected_indices_in_dialog.remove(tube_idx)
        else:
            self.selected_indices_in_dialog.add(tube_idx)
        self._update_tube_visual(tube_idx)

    def _apply_color_to_selected_dialog_tubes(self):
        selected_color_name = self.color_var.get()
        if not selected_color_name:
            messagebox.showwarning("No Color Selected", "Please select a color from the dropdown first.", parent=self)
            return
        actual_color = self.planner.FUSE_COLORS_MAP[selected_color_name] 
        if not self.selected_indices_in_dialog:
            messagebox.showinfo("No Tubes Selected", "Please select one or more tubes in the diagram to apply color.", parent=self)
            return

        for idx in list(self.selected_indices_in_dialog): 
            self.current_tubes_data_copy[idx]['color'] = actual_color 
            self._update_tube_visual(idx) 

    def _select_all_tubes(self):
        for i in range(self.num_tubes):
            is_newly_selected = i not in self.selected_indices_in_dialog
            self.selected_indices_in_dialog.add(i)
            if is_newly_selected: 
                 self._update_tube_visual(i)    

    def _deselect_all_tubes(self):
        currently_selected = list(self.selected_indices_in_dialog) 
        self.selected_indices_in_dialog.clear()
        for i in currently_selected: 
            self._update_tube_visual(i)

    def _confirm_changes(self):
        self.rack_config_original['tubes'] = copy.deepcopy(self.current_tubes_data_copy)
        self.planner._update_canvas_summary_info() 
        self.planner.redraw_canvas() 
        self.planner.status_var.set(f"Tube colors updated for rack ...{self.rack_config_original['id'][-6:]}.")
        self.planner._update_ui_for_selection_state() 
        self.destroy() 

class TubeTypeDialog(tk.Toplevel):
    """
    Dialog window for individually editing firework types of tubes in a rack.
    """
    def __init__(self, parent, rack_config_original, planner_instance, visual_rotation_angle):
        super().__init__(parent)
        self.transient(parent)
        self.grab_set()

        self.rack_config_original = rack_config_original
        self.planner = planner_instance
        self.visual_rotation_angle = visual_rotation_angle

        self.current_tubes_data_copy = copy.deepcopy(rack_config_original['tubes'])
        self.num_tubes = len(self.current_tubes_data_copy)
        self.selected_indices_in_dialog = set()
        self.tube_canvas_mapping = {}

        self.title(f"Edit Firework Types for Rack: {rack_config_original.get('name', rack_config_original['id'][-6:])}")
        self.resizable(False, False)

        self._padding = 10
        self._tube_size = 25
        self._spacing = 5
        self._font_size = 7 if self._tube_size < 25 else 8
        self._text_offset = self._tube_size / 2

        # Define visual spacing for Fan racks, similar to TubeRecolorDialog
        self._segment_visual_spacing = 8 

        # Define available firework types
        # Ensure "Standard" or a similar default is present
        self.FIREWORK_TYPE_CHOICES = ["Whistling Tail", "Tiger Tail", "Ring", "Nishiki", "Standard"]  # Add your types here

        self._setup_widgets()
        self._draw_tubes_on_dialog_canvas_initial()

        # ... (Rest of the __init__ method for dialog positioning - same as TubeRecolorDialog) ...
        self.update_idletasks() 
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        max_dialog_width = parent_width * 0.9
        max_dialog_height = parent_height * 0.9

        if dialog_width > max_dialog_width:
            dialog_width = int(max_dialog_width)
        if dialog_height > max_dialog_height:
            dialog_height = int(max_dialog_height)
        
        self.geometry(f"{dialog_width}x{dialog_height}")
        self.update_idletasks() 

        current_dialog_width = self.winfo_width()
        current_dialog_height = self.winfo_height()

        x_pos = parent_x + (parent_width - current_dialog_width) // 2
        y_pos = parent_y + (parent_height - current_dialog_height) // 2
        self.geometry(f"+{x_pos}+{y_pos}")

    def _setup_widgets(self):
        main_frame = ttk.Frame(self, padding="10")
        main_frame.pack(expand=True, fill=tk.BOTH)

        controls_frame = ttk.Frame(main_frame, padding="5")
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(controls_frame, text="Select Type:").pack(side=tk.LEFT, padx=(0, 5))
        self.type_var = tk.StringVar(value=self.FIREWORK_TYPE_CHOICES[0])
        type_combo = ttk.Combobox(controls_frame, textvariable=self.type_var, values=self.FIREWORK_TYPE_CHOICES, state="readonly", width=15)
        type_combo.pack(side=tk.LEFT, padx=5)
        ToolTip(type_combo, "Choose the firework type to apply to selected tubes.")
        apply_btn = ttk.Button(controls_frame, text="Apply to Selected Tubes", command=self._apply_type_to_selected_dialog_tubes)
        apply_btn.pack(side=tk.LEFT, padx=5)
        ToolTip(apply_btn, "Applies the chosen firework type to all currently selected tubes.")

        canvas_outer_frame = ttk.Frame(main_frame) 
        canvas_outer_frame.pack(expand=True, fill=tk.BOTH, pady=5)
        self.tubes_canvas = tk.Canvas(canvas_outer_frame, bg="white", highlightthickness=0)
        self.tubes_canvas.pack(side=tk.LEFT, expand=True, fill=tk.BOTH, padx=2, pady=2) 

        action_buttons_frame = ttk.Frame(main_frame, padding="5")
        action_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        action_buttons_frame.columnconfigure(0, weight=1) 
        action_buttons_frame.columnconfigure(1, weight=1)
        self.select_all_btn = ttk.Button(action_buttons_frame, text="Select All", command=self._select_all_tubes)
        self.select_all_btn.grid(row=0, column=0, sticky=tk.E, padx=5)
        ToolTip(self.select_all_btn, "Selects all tubes in this dialog.")
        self.deselect_all_btn = ttk.Button(action_buttons_frame, text="Deselect All", command=self._deselect_all_tubes)
        self.deselect_all_btn.grid(row=0, column=1, sticky=tk.W, padx=5)
        ToolTip(self.deselect_all_btn, "Deselects all currently selected tubes.")

        dialog_buttons_frame = ttk.Frame(main_frame, padding="5")
        dialog_buttons_frame.pack(fill=tk.X, pady=(10, 0))
        dialog_buttons_frame.columnconfigure(0, weight=1) 
        dialog_buttons_frame.columnconfigure(1, weight=0) 
        dialog_buttons_frame.columnconfigure(2, weight=0) 
        dialog_buttons_frame.columnconfigure(3, weight=1) 
        done_btn = ttk.Button(dialog_buttons_frame, text="Done", command=self._confirm_changes, style="Accent.TButton")
        done_btn.grid(row=0, column=1, padx=5)
        ToolTip(done_btn, "Apply all changes and close.")
        cancel_btn = ttk.Button(dialog_buttons_frame, text="Cancel", command=self.destroy)
        cancel_btn.grid(row=0, column=2, padx=5)
        ToolTip(cancel_btn, "Close without applying changes.")

        ToolTip(self.tubes_canvas, "Click on tubes to select/deselect them for type editing. Tube color is shown, outline indicates type/selection.")

    def _draw_tubes_on_dialog_canvas_initial(self):
        self.tubes_canvas.delete("all")
        self.tube_canvas_mapping.clear()

        original_configured_cols = self.rack_config_original['x_tubes']
        original_configured_rows = self.rack_config_original['y_tubes']
        rack_type = self.rack_config_original['type']

        # Calculate canvas dimensions based on rack type and rotation (same logic as TubeRecolorDialog)
        if rack_type == "Crate":
            if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                dialog_display_cols = original_configured_rows
                dialog_display_rows = original_configured_cols
            else: # 0 or 180
                dialog_display_cols = original_configured_cols
                dialog_display_rows = original_configured_rows
            canvas_width = (2 * self._padding + dialog_display_cols * (self._tube_size + self._spacing) - self._spacing)
            canvas_height = (2 * self._padding + dialog_display_rows * (self._tube_size + self._spacing) - self._spacing)
        elif rack_type == "Fan":
            num_fans_original = original_configured_cols
            tubes_per_fan_original = original_configured_rows
            if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                dialog_display_cols = tubes_per_fan_original
                dialog_display_rows = num_fans_original
                canvas_width = (2 * self._padding + dialog_display_cols * self._tube_size +
                                    max(0, dialog_display_cols - 1) * self._spacing)
                canvas_height = (2 * self._padding + dialog_display_rows * self._tube_size +
                                     max(0, dialog_display_rows - 1) * self._segment_visual_spacing)
            else: # 0 or 180 degrees
                dialog_display_cols = num_fans_original
                dialog_display_rows = tubes_per_fan_original
                canvas_width = (2 * self._padding + dialog_display_cols * self._tube_size +
                                    max(0, dialog_display_cols - 1) * self._segment_visual_spacing)
                canvas_height = (2 * self._padding + dialog_display_rows * self._tube_size +
                                max(0, dialog_display_rows - 1) * self._spacing)
        
        self.tubes_canvas.config(width=max(150, canvas_width), height=max(80, canvas_height))

        for i in range(self.num_tubes):
            original_col_idx = i % original_configured_cols
            original_row_idx = i // original_configured_cols
            clickable_group_tag = f"clickable_tube_area_{i}"

            if rack_type == "Crate":
                if self.visual_rotation_angle == 0:
                    dialog_visual_col, dialog_visual_row = original_col_idx, original_row_idx
                elif self.visual_rotation_angle == 90:
                    dialog_visual_col, dialog_visual_row = original_row_idx, original_configured_cols - 1 - original_col_idx
                elif self.visual_rotation_angle == 180:
                    dialog_visual_col, dialog_visual_row = original_configured_cols - 1 - original_col_idx, original_configured_rows - 1 - original_row_idx
                elif self.visual_rotation_angle == 270:
                    dialog_visual_col, dialog_visual_row = original_configured_rows - 1 - original_row_idx, original_col_idx
                x1 = self._padding + dialog_visual_col * (self._tube_size + self._spacing)
                y1 = self._padding + dialog_visual_row * (self._tube_size + self._spacing)
            elif rack_type == "Fan":
                num_fans = original_configured_cols
                tubes_per_fan = original_configured_rows
                segment_idx = i // tubes_per_fan
                tube_in_segment_idx = i % tubes_per_fan
                if self.visual_rotation_angle == 0:
                    dialog_visual_col, dialog_visual_row = segment_idx, tube_in_segment_idx
                elif self.visual_rotation_angle == 90:
                    dialog_visual_col, dialog_visual_row = tube_in_segment_idx, num_fans - 1 - segment_idx
                elif self.visual_rotation_angle == 180:
                    dialog_visual_col, dialog_visual_row = num_fans - 1 - segment_idx, tubes_per_fan - 1 - tube_in_segment_idx
                elif self.visual_rotation_angle == 270:
                    dialog_visual_col, dialog_visual_row = tubes_per_fan - 1 - tube_in_segment_idx, segment_idx
                else: # Default to 0
                    dialog_visual_col, dialog_visual_row = segment_idx, tube_in_segment_idx
                
                if self.visual_rotation_angle == 90 or self.visual_rotation_angle == 270:
                    x1 = self._padding + dialog_visual_col * (self._tube_size + self._spacing)
                    y1 = self._padding + dialog_visual_row * (self._tube_size + self._segment_visual_spacing)
                else: # 0 or 180
                    x1 = self._padding + dialog_visual_col * (self._tube_size + self._segment_visual_spacing)
                    y1 = self._padding + dialog_visual_row * (self._tube_size + self._spacing)

            x2 = x1 + self._tube_size
            y2 = y1 + self._tube_size
            
            # Tube number display (local 1-based for this dialog)
            display_tube_number = str(i + 1) 

            # Create rectangle (fill color will be set by _update_tube_visual)
            rect_id = self.tubes_canvas.create_rectangle(x1, y1, x2, y2, outline="grey", width=1, tags=(f"rect_for_tube_{i}", clickable_group_tag))
            text_id = self.tubes_canvas.create_text(x1 + self._text_offset, y1 + self._text_offset, text=display_tube_number, fill="black", tags=(f"text_for_tube_{i}", clickable_group_tag), font=("Arial", self._font_size))

            self.tube_canvas_mapping[i] = (rect_id, text_id)
            self.tubes_canvas.tag_raise(text_id, rect_id)
            self.tubes_canvas.tag_bind(clickable_group_tag, "<Button-1>", lambda e, idx=i: self._handle_specific_tube_click(idx))
            self._update_tube_visual(i) # Apply initial type-specific visuals

    def _handle_specific_tube_click(self, tube_idx):
        if tube_idx in self.selected_indices_in_dialog:
            self.selected_indices_in_dialog.remove(tube_idx)
        else:
            self.selected_indices_in_dialog.add(tube_idx)
        self._update_tube_visual(tube_idx)

    def _apply_type_to_selected_dialog_tubes(self):
        selected_type = self.type_var.get()
        if not selected_type:
            messagebox.showwarning("No Type Selected", "Please select a type.", parent=self)
            return
        if not self.selected_indices_in_dialog:
            messagebox.showinfo("No Tubes Selected", "Please select tubes.", parent=self)
            return
        for idx in list(self.selected_indices_in_dialog):
            self.current_tubes_data_copy[idx]['type'] = selected_type
            self._update_tube_visual(idx)

    def _update_tube_visual(self, tube_idx):
        if tube_idx in self.tube_canvas_mapping:
            rect_id, text_id = self.tube_canvas_mapping[tube_idx]
            tube_data = self.current_tubes_data_copy[tube_idx]
            
            fill_color = tube_data['color'] # Keep the original color of the tube
            current_outline_color = "grey" 
            current_outline_width = 1

            tube_type = tube_data.get('type', "Standard") 
            if tube_type == "Whistling Tail":
                current_outline_color = "darkorange"
                current_outline_width = 2
            elif tube_type == "Tiger Tail":
                current_outline_color = "saddlebrown"
                current_outline_width = 2
            elif tube_type == "Ring":
                current_outline_color = "darkviolet"
                current_outline_width = 2
            elif tube_type == "Nishiki":
                current_outline_color = "goldenrod"
                current_outline_width = 2

            if tube_idx in self.selected_indices_in_dialog:
                current_outline_color = "blue" 
                current_outline_width = 2
            
            self.tubes_canvas.itemconfig(rect_id, fill=fill_color, outline=current_outline_color, width=current_outline_width)

    def _select_all_tubes(self):
        for i in range(self.num_tubes):
            is_newly_selected = i not in self.selected_indices_in_dialog
            self.selected_indices_in_dialog.add(i)
            if is_newly_selected:
                 self._update_tube_visual(i)

    def _deselect_all_tubes(self):
        currently_selected = list(self.selected_indices_in_dialog)
        self.selected_indices_in_dialog.clear()
        for i in currently_selected:
            self._update_tube_visual(i)

    def _confirm_changes(self):
        self.rack_config_original['tubes'] = copy.deepcopy(self.current_tubes_data_copy)
        self.planner.redraw_canvas()  # Redraw to reflect type changes
        self.planner.status_var.set(f"Firework types updated for rack ...{self.rack_config_original['id'][-6:]}.")
        self.planner._update_ui_for_selection_state()
        self.destroy()


class FireworkRackPlanner:
    """
    Main application class for the Firework Rack Planner.
    Handles UI setup, canvas drawing, rack and line management,
    user interactions, and file operations.
    """
    def __init__(self, root):
        self.root = root
        self.root.title("Firework Rack Planner - Pro+ v1.8") # Version bump
        self.CANVAS_WIDTH=900;self.CANVAS_HEIGHT=700;self.CANVAS_BG_COLOR="ivory"
        self.UI_PADDING=10;self.DEFAULT_TUBE_DIAMETER=20 # World units
        self.DEFAULT_TUBE_SPACING_RATIO=0.2;self.DEFAULT_FAN_PADDING_RATIO=0.2;self.DEFAULT_INTER_FAN_SPACING_RATIO=0.5
        self.RACK_OUTER_PADDING=5;self.RACK_OUTLINE_COLOR="black";self.RACK_OUTLINE_WIDTH=1.5
        self.SELECTED_RACK_OUTLINE_COLOR="blue";self.SELECTED_RACK_OUTLINE_WIDTH=3;self.SNAP_THRESHOLD=10
        self.ROTATION_DEGREES=[0,90,180,270];self.DUPLICATE_OFFSET_X=20;self.DUPLICATE_OFFSET_Y=20
        self.DUPLICATE_OFFSET_INCREMENT=5; self.NUDGE_AMOUNT = 2

        self.FUSE_COLORS_MAP={
            # Name: "color_value_for_drawing_and_burn_rate_key"
            # Ensure color_value_for_drawing_and_burn_rate_key exists as a key in FUSE_BURN_RATES_SPF
            # if you want burn time calculations for it.
            # Tkinter color names or hex codes can be used for drawing.
            "White":"white", "Yellow":"yellow", "Pink":"pink", 
            "Blue":"lightblue", "Orange":"orange", "Green":"lightgreen" 
        }
        self.FUSE_COLOR_CHOICES=list(self.FUSE_COLORS_MAP.keys())
        self.default_new_tube_color_value = self.FUSE_COLORS_MAP.get("Pink", "pink") 

        self.FUSE_BURN_RATES_SPF = { 
            # color_value: seconds_per_foot
            "white": 0.75, "yellow": 1.5, "pink": 10.0,
            "lightblue": 15.0, "orange": 18.0, "lightgreen": 30.0 
        }

        self.racks_on_canvas=[];self.selected_rack_ids=[];self.dragging_rack_id=None
        self.selected_flow_line_id = None 
        self.drag_offset_x=0;self.drag_offset_y=0;
        self.drag_start_positions = {} 

        # UI related constants
        self.WIDGET_PADY = 3
        self.LABEL_STICKY = tk.W
        self.ENTRY_STICKY = (tk.W, tk.E)
        self.INPUT_WIDTH_SHORT = 8
        self.INPUT_WIDTH_LONG = 18

        self.snap_to_grid_enabled = tk.BooleanVar(value=False)
        self.grid_size_var = tk.StringVar(value="20")
        self.show_rack_names_var = tk.BooleanVar(value=False)
        self.show_tube_numbers_var = tk.BooleanVar(value=True) # Automatically show tube numbers
        self.snap_to_racks_enabled = tk.BooleanVar(value=False)

        self.DEFAULT_CRATE_FUSE_INCHES = 70.0 
        self.FAN_CHAIN_INTER_TUBE_ALLOWANCE_INCHES = 3.0 
        self.FAN_CHAIN_INTER_SEGMENT_ALLOWANCE_INCHES = 0.0 
        self.FAN_CHAIN_LEAD_INCHES = 3.0 
        self.FAN_CHAIN_TAIL_INCHES = 3.0 
        self.FUSE_ESTIMATE_UNIT = "ft." 
        self.FUSE_LENGTH_SCALE_FACTOR = 0.9 # Reduce fuse length estimates by 10%
        self.INCHES_PER_FOOT = 12.0

        # Physical dimension constants (world units, assumed inches)
        self.PHYSICAL_TUBE_DIAMETER_INCHES = 2.0
        self.PHYSICAL_CRATE_SPACING_INCHES = 0.5
        self.PHYSICAL_FAN_TUBE_SPACING_INCHES = 0.75 
        self.PHYSICAL_FAN_SEGMENT_WIDTH_INCHES = 3.0 
        self.PHYSICAL_FAN_INTER_SEGMENT_SPACING_INCHES = 3.75 

        self.flow_lines_on_canvas = [] 
        self.drawing_flow_line_mode = False
        self.flow_line_start_point = None 
        self.LINE_CAP_LENGTH = 6 
        self.LINE_TOOL_COLOR_DEFAULT = "darkred"
        self.LINE_TOOL_WIDTH = 2.0
        self.SELECTED_LINE_COLOR = "cyan"
        self.LINE_CLICK_HALO = 5 

        self.tube_connections = [] 
        self.connecting_tubes_mode = False
        self.first_tube_for_connection = None 

        self.undo_stack = []
        self.redo_stack = []
        self.MAX_UNDO_STEPS = 50
        self.drag_operation_pending_undo_state = None 

        # Zoom and Pan State
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.MIN_ZOOM = 0.1
        self.MAX_ZOOM = 5.0
        self.ZOOM_STEP = 1.2 
        self._is_panning = False
        self._pan_start_x = 0
        self._pan_start_y = 0
        self._pan_initial_offset_x = 0
        self._pan_initial_offset_y = 0
        
        # Default positions for new racks (world coordinates)
        self.DEFAULT_RACK_POS_X_WORLD = 50
        self.DEFAULT_RACK_POS_Y_WORLD = 50
        self.DEFAULT_RACK_SEPARATION_WORLD = 20 # Spacing for suggesting next rack position
        self.rack_global_start_indices = {} # For global tube numbering

        self.DEFAULT_TUBE_OUTLINE_WIDTH_WORLD = 1.0
        self.FIREWORK_TYPE_VISUALS = {
            "Whistling Tail": {"outline": "darkorange", "width_factor": 1.5, "shape": "rectangle"},
            "Tiger Tail": {"outline": "saddlebrown", "width_factor": 1.5, "shape": "oval"},
            "Ring": {"outline": "darkviolet", "width_factor": 1.5, "shape": "rectangle"},
            "Nishiki": {"outline": "goldenrod", "width_factor": 1.5, "shape": "oval"},
            "Standard": {"outline": "black", "width_factor": 1.0, "shape": "oval"}, # Default
        }

        self._setup_styles()
        self._setup_main_layout()
        self._setup_control_panel_tabs()
        self._setup_canvas_area()
        self._setup_status_bar()
        self._bind_global_events()
        self._initialize_ui_state()

    def _setup_styles(self):
        style = ttk.Style()
        style.configure("Accent.TButton", font=('Arial', 10, 'bold'))
        style.configure("TLabelframe.Label", font=('Arial', 10, 'bold'))
        style.configure("TLabelframe", padding=(10, 5, 10, 10))
        style.configure("TNotebook.Tab", font=('Arial', 9, 'bold'), padding=[8, 3])

    def _setup_main_layout(self):
        self.main_paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.main_paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _setup_control_panel_tabs(self):
        controls_outer_frame = ttk.Frame(self.main_paned_window, padding="5")
        self.main_paned_window.add(controls_outer_frame, weight=0) 

        title_label = ttk.Label(controls_outer_frame, text="Rack Designer Pro+", font=("Arial", 16, "bold"))
        title_label.pack(pady=(0, 10), anchor="center")

        self.control_notebook = ttk.Notebook(controls_outer_frame)
        self.control_notebook.pack(expand=True, fill="both")

        self._setup_file_view_tab()
        self._setup_item_properties_tab()
        self._setup_tools_actions_tab()

    def _setup_file_view_tab(self):
        tab_file_view = ttk.Frame(self.control_notebook, padding="5")
        self.control_notebook.add(tab_file_view, text="File & View")
        tab_file_view.columnconfigure(0, weight=1) 

        file_ops_frame=ttk.LabelFrame(tab_file_view,text="File Operations")
        file_ops_frame.grid(row=0,column=0,sticky=(tk.W,tk.E,tk.N),pady=(5,10),padx=5);file_ops_frame.columnconfigure(0,weight=1)
        
        undo_redo_frame = ttk.Frame(file_ops_frame)
        undo_redo_frame.pack(fill=tk.X, pady=3, padx=0)
        self.undo_btn = ttk.Button(undo_redo_frame, text="Undo", command=self.undo_action, width=8)
        self.undo_btn.pack(side=tk.LEFT, padx=(0, 2))
        ToolTip(self.undo_btn, "Undo the last action (Ctrl+Z eventually).")
        self.redo_btn = ttk.Button(undo_redo_frame, text="Redo", command=self.redo_action, width=8)
        self.redo_btn.pack(side=tk.LEFT, padx=(2,5))
        ToolTip(self.redo_btn, "Redo the last undone action (Ctrl+Y eventually).")

        save_btn=ttk.Button(file_ops_frame,text="Save Layout",command=self.save_layout)
        save_btn.pack(fill=tk.X,pady=(5,3),padx=5);ToolTip(save_btn,"Save the current rack layout to a file (JSON).")
        load_btn = ttk.Button(file_ops_frame, text="Load Layout", command=self.load_layout)
        load_btn.pack(fill=tk.X, pady=3, padx=5); ToolTip(load_btn, "Load a previously saved rack layout from a file.")
        export_image_btn = ttk.Button(file_ops_frame, text="Export as Image", command=self.export_canvas_as_image)
        export_image_btn.pack(fill=tk.X, pady=(3, 0), padx=5)
        ToolTip(export_image_btn, "Export the current canvas view as a PNG image.")
        if not PIL_AVAILABLE: export_image_btn.config(state=tk.DISABLED)

        view_ops_frame = ttk.LabelFrame(tab_file_view, text="Canvas View Options")
        view_ops_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=5, padx=5)
        view_ops_frame.columnconfigure(0, weight=0); view_ops_frame.columnconfigure(1, weight=0); view_ops_frame.columnconfigure(2, weight=0); view_ops_frame.columnconfigure(3, weight=1) 
        snap_grid_cb = ttk.Checkbutton(view_ops_frame, text="Snap to Grid", variable=self.snap_to_grid_enabled, command=self.redraw_canvas)
        snap_grid_cb.grid(row=0, column=0, padx=5, pady=self.WIDGET_PADY, sticky=self.LABEL_STICKY)
        ToolTip(snap_grid_cb, "Snap racks to the visual grid when dragging.")
        ttk.Label(view_ops_frame, text="Grid Size:").grid(row=0, column=1, padx=(10,0), pady=self.WIDGET_PADY, sticky=self.LABEL_STICKY)
        self.grid_size_entry = ttk.Entry(view_ops_frame, textvariable=self.grid_size_var, width=4)
        self.grid_size_entry.grid(row=0, column=2, padx=(0,5), pady=self.WIDGET_PADY, sticky=self.LABEL_STICKY)
        ToolTip(self.grid_size_entry, "Size of the grid cells in world units. Press Enter to apply.")
        self.grid_size_entry.bind("<Return>", lambda e: self.redraw_canvas_if_valid_grid(e, True)) 
        self.grid_size_var.trace_add("write", self.redraw_canvas_if_valid_grid) 

        reset_view_btn = ttk.Button(view_ops_frame, text="Reset View", command=self.reset_canvas_view)
        reset_view_btn.grid(row=0, column=3, padx=5, pady=self.WIDGET_PADY, sticky=tk.E)
        ToolTip(reset_view_btn, "Resets canvas zoom to 100% and centers the view.")

        show_names_cb = ttk.Checkbutton(view_ops_frame, text="Show Names", variable=self.show_rack_names_var, command=self.redraw_canvas)
        show_names_cb.grid(row=1, column=0, columnspan=3, padx=5, pady=self.WIDGET_PADY, sticky=self.LABEL_STICKY)
        ToolTip(show_names_cb, "Display rack names on the canvas.")
        show_tube_numbers_cb = ttk.Checkbutton(view_ops_frame, text="Show Tube Numbers/Cues", variable=self.show_tube_numbers_var, command=self.redraw_canvas)
        show_tube_numbers_cb.grid(row=2, column=0, columnspan=3, padx=5, pady=self.WIDGET_PADY, sticky=self.LABEL_STICKY)
        ToolTip(show_tube_numbers_cb, "Display tube numbers (or cues, if set) on each tube on the canvas (1-based).")

    def _setup_item_properties_tab(self):
        self.tab_item_props = ttk.Frame(self.control_notebook, padding="5") 
        self.control_notebook.add(self.tab_item_props, text="Item Properties")
        self.tab_item_props.columnconfigure(0, weight=1)

        # --- Rack Properties Frame ---
        self.rack_props_frame = ttk.LabelFrame(self.tab_item_props, text="Rack Properties / Add New")
        self.rack_props_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=5, padx=5)
        self.rack_props_frame.columnconfigure(1, weight=1)
        
        current_row=0
        ttk.Label(self.rack_props_frame, text="Name:").grid(row=current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.rack_name_var = tk.StringVar()
        self.rack_name_entry = ttk.Entry(self.rack_props_frame, textvariable=self.rack_name_var, width=self.INPUT_WIDTH_LONG)
        self.rack_name_entry.grid(row=current_row, column=1, columnspan=2, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        ToolTip(self.rack_name_entry, "Optional name for the selected rack. Press Enter or lose focus to apply.")
        self.rack_name_entry.bind("<Return>", self.apply_rack_name_from_ui)
        self.rack_name_entry.bind("<FocusOut>", self.apply_rack_name_from_ui)
        current_row +=1

        ttk.Label(self.rack_props_frame,text="Rack Type:").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.rack_type_var=tk.StringVar(value="Crate")
        self.rack_type_dropdown=ttk.Combobox(self.rack_props_frame,textvariable=self.rack_type_var,values=["Crate","Fan"],state="readonly",width=self.INPUT_WIDTH_LONG)
        self.rack_type_dropdown.grid(row=current_row,column=1,columnspan=2,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.rack_type_dropdown,"Choose the type of rack: Crate (grid) or Fan.")
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Tubes X (Cols/Fans):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.x_tubes_var=tk.StringVar(value="3")
        self.x_tubes_entry=ttk.Entry(self.rack_props_frame,textvariable=self.x_tubes_var,width=self.INPUT_WIDTH_SHORT)
        self.x_tubes_entry.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.x_tubes_entry,"Number of tubes horizontally (columns for Crate, number of fan segments for Fan).")
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Tubes Y (Rows/Tubes per Fan):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.y_tubes_var=tk.StringVar(value="2")
        self.y_tubes_entry=ttk.Entry(self.rack_props_frame,textvariable=self.y_tubes_var,width=self.INPUT_WIDTH_SHORT)
        self.y_tubes_entry.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.y_tubes_entry,"Number of tubes vertically (rows for Crate, tubes per fan segment for Fan).")
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Position X (World):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.pos_x_var=tk.StringVar(value=str(self.DEFAULT_RACK_POS_X_WORLD))
        self.pos_x_entry=ttk.Entry(self.rack_props_frame,textvariable=self.pos_x_var,width=self.INPUT_WIDTH_SHORT)
        self.pos_x_entry.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.pos_x_entry,"World X-coordinate. Can be edited to move selected rack. Press Enter to apply.")
        self.pos_x_entry.bind("<Return>", self.apply_position_from_ui)
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Position Y (World):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.pos_y_var=tk.StringVar(value=str(self.DEFAULT_RACK_POS_Y_WORLD))
        self.pos_y_entry=ttk.Entry(self.rack_props_frame,textvariable=self.pos_y_var,width=self.INPUT_WIDTH_SHORT)
        self.pos_y_entry.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.pos_y_entry,"World Y-coordinate. Can be edited to move selected rack. Press Enter to apply.")
        self.pos_y_entry.bind("<Return>", self.apply_position_from_ui)
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Tube Diameter (World):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.tube_diameter_var=tk.StringVar(value=str(self.DEFAULT_TUBE_DIAMETER))
        self.tube_diameter_entry=ttk.Entry(self.rack_props_frame,textvariable=self.tube_diameter_var,width=self.INPUT_WIDTH_SHORT)
        self.tube_diameter_entry.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.tube_diameter_entry,"Diameter of each firework tube in world units.")
        current_row+=1
        ttk.Label(self.rack_props_frame,text="Rotation (°):").grid(row=current_row,column=0,sticky=self.LABEL_STICKY,pady=self.WIDGET_PADY,padx=5)
        self.rotation_var=tk.IntVar(value=0) 
        self.rotation_dropdown=ttk.Combobox(self.rack_props_frame,textvariable=self.rotation_var,values=self.ROTATION_DEGREES,state="readonly",width=self.INPUT_WIDTH_SHORT)
        self.rotation_dropdown.grid(row=current_row,column=1,sticky=self.ENTRY_STICKY,pady=self.WIDGET_PADY,padx=5);ToolTip(self.rotation_dropdown,"Rotation angle for the rack (0, 90, 180, 270 degrees).")
        self.rotation_dropdown.bind("<<ComboboxSelected>>", self.apply_rotation_from_ui)
        current_row+=1

        ttk.Label(self.rack_props_frame, text="Est. Internal Size (in):").grid(row=current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.physical_dims_var = tk.StringVar(value="N/A")
        self.physical_dims_label = ttk.Label(self.rack_props_frame, textvariable=self.physical_dims_var, width=self.INPUT_WIDTH_LONG)
        self.physical_dims_label.grid(row=current_row, column=1, columnspan=2, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        ToolTip(self.physical_dims_label, "Estimated physical dimensions of the selected rack based on typical tube sizes and spacing.")
        current_row+=1

        ttk.Label(self.rack_props_frame, text="Colors:").grid(row=current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.tube_color_breakdown_var = tk.StringVar(value="N/A")
        self.tube_color_breakdown_label = ttk.Label(self.rack_props_frame, textvariable=self.tube_color_breakdown_var, width=self.INPUT_WIDTH_LONG, wraplength=200) 
        self.tube_color_breakdown_label.grid(row=current_row, column=1, columnspan=2, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        ToolTip(self.tube_color_breakdown_label, "Breakdown of tube colors for the selected rack.")
        current_row+=1
        
        add_rack_btn=ttk.Button(self.rack_props_frame,text="Add Rack to Canvas",command=self.add_rack_to_list,style="Accent.TButton")
        add_rack_btn.grid(row=current_row, column=0, columnspan=3, sticky=tk.EW, pady=(10,self.WIDGET_PADY), padx=5)
        ToolTip(add_rack_btn,"Adds a new rack to the canvas using the current configuration settings.")
        current_row+=1

        # --- Flow Line Properties Frame (initially hidden) ---
        self.line_props_frame = ttk.LabelFrame(self.tab_item_props, text="Flow Line Properties")
        self.line_props_frame.columnconfigure(1, weight=1)
        
        line_current_row = 0
        ttk.Label(self.line_props_frame, text="Label:").grid(row=line_current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.flow_line_label_var = tk.StringVar()
        self.flow_line_label_entry = ttk.Entry(self.line_props_frame, textvariable=self.flow_line_label_var, width=self.INPUT_WIDTH_LONG)
        self.flow_line_label_entry.grid(row=line_current_row, column=1, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        ToolTip(self.flow_line_label_entry, "Optional label for the selected flow line. Press Enter or lose focus to apply.")
        self.flow_line_label_entry.bind("<Return>", self.apply_flow_line_label_from_ui)
        self.flow_line_label_entry.bind("<FocusOut>", self.apply_flow_line_label_from_ui)
        line_current_row += 1

        ttk.Label(self.line_props_frame, text="Length:").grid(row=line_current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.flow_line_length_var = tk.StringVar(value="N/A")
        ttk.Label(self.line_props_frame, textvariable=self.flow_line_length_var).grid(row=line_current_row, column=1, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        line_current_row += 1

        ttk.Label(self.line_props_frame, text="Est. Burn Time:").grid(row=line_current_row, column=0, sticky=self.LABEL_STICKY, pady=self.WIDGET_PADY, padx=5)
        self.flow_line_burn_time_var = tk.StringVar(value="N/A")
        ttk.Label(self.line_props_frame, textvariable=self.flow_line_burn_time_var).grid(row=line_current_row, column=1, sticky=self.ENTRY_STICKY, pady=self.WIDGET_PADY, padx=5)
        line_current_row += 1

        self.input_widgets_for_state_change=[ 
            self.rack_name_entry, self.rack_type_dropdown,self.x_tubes_entry,self.y_tubes_entry,
            self.tube_diameter_entry,self.rotation_dropdown, self.physical_dims_label, 
            self.tube_color_breakdown_label, self.pos_x_entry, self.pos_y_entry, 
            self.flow_line_label_entry 
        ] 

    def _setup_tools_actions_tab(self):
        tab_tools_actions = ttk.Frame(self.control_notebook, padding="5")
        self.control_notebook.add(tab_tools_actions, text="Tools & Actions")
        tab_tools_actions.columnconfigure(0, weight=1)

        action_frame=ttk.LabelFrame(tab_tools_actions,text="Rack & Canvas Actions")
        action_frame.grid(row=0,column=0,sticky=(tk.W,tk.E,tk.N),pady=5,padx=5);action_frame.columnconfigure(0,weight=1)
        btn_pady=3;btn_padx=5
        
        self.recolor_tubes_btn=ttk.Button(action_frame,text="Recolor Selected Rack Tubes...",command=self.open_tube_recolor_dialog)
        self.recolor_tubes_btn.pack(fill=tk.X,pady=btn_pady,padx=btn_padx);ToolTip(self.recolor_tubes_btn,"Opens a dialog to individually recolor tubes for the single selected rack (Enabled only for one selection).")
        self.edit_types_btn = ttk.Button(action_frame, text="Edit Firework Types...", command=self.open_tube_type_dialog)
        self.edit_types_btn.pack(fill=tk.X, pady=btn_pady, padx=btn_padx)
        ToolTip(self.edit_types_btn, "Opens a dialog to edit firework types for the single selected rack.")
        rotate_btn=ttk.Button(action_frame,text="Rotate Selected Rack(s)",command=self.rotate_selected_racks_action)
        rotate_btn.pack(fill=tk.X,pady=btn_pady,padx=btn_padx);ToolTip(rotate_btn,"Rotates all selected rack(s) by 90 degrees clockwise (Shortcut: R).")
        duplicate_btn=ttk.Button(action_frame,text="Duplicate Selected Rack(s)",command=self.duplicate_selected_racks)
        duplicate_btn.pack(fill=tk.X,pady=btn_pady,padx=btn_padx);ToolTip(duplicate_btn,"Creates copies of all selected rack(s) slightly offset from the originals (Shortcut: Ctrl+D).")
        snap_racks_cb=ttk.Checkbutton(action_frame,text="Snap to Other Racks",variable=self.snap_to_racks_enabled)
        snap_racks_cb.pack(fill=tk.X,pady=btn_pady,padx=btn_padx);ToolTip(snap_racks_cb,"If checked, dragged racks will attempt to snap to the edges of other racks.")

        ttk.Separator(action_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5) 
        self.draw_line_btn=ttk.Button(action_frame,text="Draw Flow Line (Off)",command=self.toggle_draw_flow_line_mode)
        self.draw_line_btn.pack(fill=tk.X, pady=btn_pady, padx=btn_padx)
        ToolTip(self.draw_line_btn, "Toggle mode to draw a flow line. Click canvas for start, click again for end.")

        self.connect_tubes_btn = ttk.Button(action_frame, text="Connect Tubes (Off)", command=self.toggle_connect_tubes_mode)
        self.connect_tubes_btn.pack(fill=tk.X, pady=btn_pady, padx=btn_padx)
        ToolTip(self.connect_tubes_btn, "Toggle mode to connect individual tubes across racks. Click source tube, then target tube.")

        clear_lines_btn = ttk.Button(action_frame, text="Clear All Flow Lines", command=self.clear_all_flow_lines)
        clear_lines_btn.pack(fill=tk.X, pady=btn_pady, padx=btn_padx)
        ToolTip(clear_lines_btn, "Removes all manually drawn flow lines from the canvas.")

        clear_tube_connections_btn = ttk.Button(action_frame, text="Clear All Tube Connections", command=self.clear_all_tube_connections)
        clear_tube_connections_btn.pack(fill=tk.X, pady=btn_pady, padx=btn_padx)
        ToolTip(clear_tube_connections_btn, "Removes all tube-to-tube connection lines from the canvas.")
        
        ttk.Separator(action_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5) 
        clear_all_btn=ttk.Button(action_frame,text="Clear All Racks",command=self.clear_all_racks)
        clear_all_btn.pack(fill=tk.X,pady=btn_pady,padx=btn_padx);ToolTip(clear_all_btn,"Removes all racks from the canvas (requires confirmation).")

    def _setup_canvas_area(self):
        right_pane_frame = ttk.Frame(self.main_paned_window)
        self.main_paned_window.add(right_pane_frame, weight=1) 
        right_pane_frame.rowconfigure(0, weight=1);right_pane_frame.rowconfigure(1, weight=0, minsize=100) 
        right_pane_frame.columnconfigure(0, weight=1)

        self.canvas=tk.Canvas(right_pane_frame,width=self.CANVAS_WIDTH,height=self.CANVAS_HEIGHT,bg=self.CANVAS_BG_COLOR,relief=tk.SUNKEN,borderwidth=1)
        self.canvas.grid(row=0,column=0,sticky=(tk.W,tk.E,tk.N,tk.S),padx=(5,0),pady=(0,5))
        rack_list_frame = ttk.LabelFrame(right_pane_frame, text="Rack Inspector", padding=5)
        rack_list_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5,0), padx=(5,0))
        rack_list_frame.rowconfigure(0, weight=1); rack_list_frame.columnconfigure(0, weight=1)

        columns = ("id", "type", "dims", "tubes", "rot", "global_start")
        self.rack_inspector_tree = ttk.Treeview(rack_list_frame, columns=columns, show="headings", height=6, selectmode="extended")
        
        self.rack_inspector_tree.heading("#0", text="Name", anchor=tk.W) # Implicit first column for item text
        self.rack_inspector_tree.heading("id", text="ID", anchor=tk.W)
        self.rack_inspector_tree.heading("type", text="Type", anchor=tk.W)
        self.rack_inspector_tree.heading("dims", text="Dims", anchor=tk.W)
        self.rack_inspector_tree.heading("tubes", text="Tubes", anchor=tk.W)
        self.rack_inspector_tree.heading("rot", text="Rot°", anchor=tk.W)
        self.rack_inspector_tree.heading("global_start", text="Global #", anchor=tk.W)

        self.rack_inspector_tree.column("#0", width=150, stretch=tk.YES)
        self.rack_inspector_tree.column("id", width=70, stretch=tk.NO, anchor=tk.W)
        self.rack_inspector_tree.column("type", width=60, stretch=tk.NO, anchor=tk.W)
        self.rack_inspector_tree.column("dims", width=60, stretch=tk.NO, anchor=tk.CENTER)
        self.rack_inspector_tree.column("tubes", width=50, stretch=tk.NO, anchor=tk.CENTER)
        self.rack_inspector_tree.column("rot", width=40, stretch=tk.NO, anchor=tk.CENTER)
        self.rack_inspector_tree.column("global_start", width=70, stretch=tk.NO, anchor=tk.CENTER)

        self.rack_inspector_tree.grid(row=0, column=0, sticky=(tk.W,tk.E,tk.N,tk.S))
        ToolTip(self.rack_inspector_tree, "List of all racks on the canvas. Click to select. Ctrl+Click or Shift+Click for multiple.")
        listbox_scrollbar = ttk.Scrollbar(rack_list_frame, orient="vertical", command=self.rack_inspector_tree.yview)
        listbox_scrollbar.grid(row=0, column=1, sticky=(tk.N,tk.S))
        self.rack_inspector_tree.config(yscrollcommand=listbox_scrollbar.set)
        self.rack_inspector_tree.bind("<<TreeviewSelect>>", self.on_rack_inspector_select)

    def _bind_global_events(self):
        # Canvas specific binds
        self.canvas.bind("<ButtonPress-1>",self.on_canvas_press)
        self.canvas.bind("<B1-Motion>",self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>",self.on_canvas_release)
        self.canvas.bind("<Shift-ButtonPress-1>",self.on_canvas_shift_click) 
        self.canvas.bind("<Button-3>", self.show_context_menu) 
        self.canvas.bind("<Motion>", self.on_canvas_mouse_motion) 
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel) # Windows/macOS
        self.canvas.bind("<Button-4>", self.on_mouse_wheel) # Linux scroll up
        self.canvas.bind("<Button-5>", self.on_mouse_wheel) # Linux scroll down
        self.canvas.bind("<ButtonPress-2>", self.on_pan_start) # Middle mouse button press
        self.canvas.bind("<B2-Motion>", self.on_pan_motion)
        self.canvas.bind("<ButtonRelease-2>", self.on_pan_end)

        # Root window binds for global shortcuts
        self.root.bind("<Left>", lambda e: self.nudge_selected_racks(-self.NUDGE_AMOUNT,0))
        self.root.bind("<Right>", lambda e: self.nudge_selected_racks(self.NUDGE_AMOUNT,0))
        self.root.bind("<Up>", lambda e: self.nudge_selected_racks(0,-self.NUDGE_AMOUNT))
        self.root.bind("<Down>", lambda e: self.nudge_selected_racks(0,self.NUDGE_AMOUNT))
        self.root.bind("<Delete>",self.delete_selected_item) 
        self.root.bind("<BackSpace>",self.delete_selected_item) 
        self.root.bind("<KeyPress-r>", self.handle_rotate_shortcut) 
        self.root.bind("<KeyPress-R>", self.handle_rotate_shortcut) 
        self.root.bind("<Control-d>", self.duplicate_selected_racks_shortcut_handler)
        self.root.bind("<Control-D>", self.duplicate_selected_racks_shortcut_handler)

        # Context Menus
        self.rack_context_menu = tk.Menu(self.root, tearoff=0)
        self.rack_context_menu.add_command(label="Recolor Tubes...", command=self.open_tube_recolor_dialog_ctx)
        self.rack_context_menu.add_command(label="Edit Firework Types...", command=self.open_tube_type_dialog_ctx)
        self.rack_context_menu.add_command(label="Rotate (R)", command=self.rotate_selected_racks_action_ctx)
        self.rack_context_menu.add_command(label="Duplicate (Ctrl+D)", command=self.duplicate_selected_racks_ctx)
        self.rack_context_menu.add_separator()
        self.rack_context_menu.add_command(label="Delete Rack", command=self.delete_selected_item_ctx)
        self.context_menu_rack_id = None 

        self.line_context_menu = tk.Menu(self.root, tearoff=0)
        line_color_menu = tk.Menu(self.line_context_menu, tearoff=0)
        self.LINE_CONTEXT_COLORS = {"Dark Red": "darkred", "Blue": "blue", "Green": "darkgreen", "Black": "black"}
        for color_name, color_val in self.LINE_CONTEXT_COLORS.items():
            line_color_menu.add_command(label=color_name, command=lambda c=color_val: self.change_selected_line_color(c))
        self.line_context_menu.add_cascade(label="Change Color", menu=line_color_menu)
        self.line_context_menu.add_separator()
        self.line_context_menu.add_command(label="Delete Line", command=self.delete_selected_item_ctx)
        self.context_menu_line_id = None 

    def _setup_status_bar(self):
        status_frame=ttk.Frame(root);status_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=5, pady=(0,5))
        status_frame.columnconfigure(0,weight=0) 
        status_frame.columnconfigure(1,weight=0) 
        status_frame.columnconfigure(2,weight=0) 
        status_frame.columnconfigure(3,weight=1) 

        self.tube_count_var=tk.StringVar(value="Total Tubes: 0")
        tube_count_label=ttk.Label(status_frame,textvariable=self.tube_count_var,font=("Arial",9,"bold"),foreground="navy")
        tube_count_label.grid(row=0,column=0,sticky=tk.W,padx=(0,10));ToolTip(tube_count_label,"Total number of firework tubes currently on the canvas.")

        self.fuse_estimation_var = tk.StringVar(value="Est. Fuse: N/A")
        fuse_estimation_label = ttk.Label(status_frame, textvariable=self.fuse_estimation_var, font=("Arial", 9), foreground="darkgreen", wraplength=400) 
        fuse_estimation_label.grid(row=0, column=1, sticky=tk.W, padx=(0,10)) 
        ToolTip(fuse_estimation_label, f"Estimated connecting fuse length per color in {self.FUSE_ESTIMATE_UNIT} (based on assumed dimensions).")

        self.show_duration_var = tk.StringVar(value="Est. Duration: 0s")
        show_duration_label = ttk.Label(status_frame, textvariable=self.show_duration_var, font=("Arial", 9), foreground="purple")
        show_duration_label.grid(row=0, column=2, sticky=tk.W, padx=(0, 20))
        ToolTip(show_duration_label, "Estimated total show duration based on fuse lengths and burn rates.")

        self.status_var=tk.StringVar();status_label=ttk.Label(status_frame,textvariable=self.status_var,foreground="slate gray")
        status_label.grid(row=0,column=3,sticky=(tk.W,tk.E)) 

    def _initialize_ui_state(self):
        self._update_ui_for_selection_state()
        self._update_canvas_summary_info()
        self.redraw_canvas()
        self._update_undo_redo_buttons_state()
        self.status_var.set("Welcome to Firework Rack Designer Pro+!")
        self._update_rack_list_panel() 
        ToolTip(self.canvas, "Ctrl+Scroll to Zoom. Middle-Mouse-Drag to Pan. Right-click for context menu.")


    def world_to_canvas(self, world_x, world_y):
        canvas_x = (world_x - self.pan_offset_x) * self.zoom_level
        canvas_y = (world_y - self.pan_offset_y) * self.zoom_level
        return canvas_x, canvas_y

    def canvas_to_world(self, canvas_x, canvas_y):
        world_x = (canvas_x / self.zoom_level) + self.pan_offset_x
        world_y = (canvas_y / self.zoom_level) + self.pan_offset_y
        return world_x, world_y

    def on_mouse_wheel(self, event):
        # Ctrl+Scroll for zoom
        if not (event.state & 0x0004): # Check if Control key is pressed
            return

        world_x_before_zoom, world_y_before_zoom = self.canvas_to_world(event.x, event.y)

        if event.delta > 0 or event.num == 4:  # Scroll up
            self.zoom_level *= self.ZOOM_STEP
        elif event.delta < 0 or event.num == 5:  # Scroll down
            self.zoom_level /= self.ZOOM_STEP
        
        self.zoom_level = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self.zoom_level))

        # Adjust pan offset to keep point under cursor fixed
        world_x_after_zoom, world_y_after_zoom = self.canvas_to_world(event.x, event.y)
        
        self.pan_offset_x += (world_x_before_zoom - world_x_after_zoom)
        self.pan_offset_y += (world_y_before_zoom - world_y_after_zoom)
        
        self.redraw_canvas()

    def on_pan_start(self, event):
        self._is_panning = True
        self._pan_start_x = event.x
        self._pan_start_y = event.y
        self._pan_initial_offset_x = self.pan_offset_x
        self._pan_initial_offset_y = self.pan_offset_y
        self.canvas.config(cursor="fleur")

    def on_pan_motion(self, event):
        if self._is_panning:
            dx = event.x - self._pan_start_x
            dy = event.y - self._pan_start_y
            self.pan_offset_x = self._pan_initial_offset_x - (dx / self.zoom_level)
            self.pan_offset_y = self._pan_initial_offset_y - (dy / self.zoom_level)
            self.redraw_canvas()

    def on_pan_end(self, event):
        self._is_panning = False
        self.canvas.config(cursor="")

    def reset_canvas_view(self):
        self.zoom_level = 1.0
        self.pan_offset_x = 0.0
        self.pan_offset_y = 0.0
        self.redraw_canvas()
        self.status_var.set("Canvas view reset.")

    def handle_rotate_shortcut(self, event=None):
        if self.selected_rack_ids and not self.selected_flow_line_id: 
            self.rotate_selected_racks_action()
        elif self.selected_flow_line_id:
            self.status_var.set("Rotation not applicable to flow lines.")
        else:
            self.status_var.set("No racks selected to rotate.")

    def duplicate_selected_racks_shortcut_handler(self, event=None):
        if self.selected_rack_ids and not self.selected_flow_line_id:
            self.duplicate_selected_racks()
        elif self.selected_flow_line_id:
            self.status_var.set("Duplication not applicable to flow lines.")
        else:
            self.status_var.set("No racks selected to duplicate.")


    def _calculate_physical_dimensions(self, rack_config):
        if not rack_config: return "N/A"
        x_tubes = rack_config.get('x_tubes', 0); y_tubes = rack_config.get('y_tubes', 0)
        rack_type = rack_config.get('type'); width_in = 0.0; height_in = 0.0
        if rack_type == "Crate":
            width_in = (x_tubes * self.PHYSICAL_TUBE_DIAMETER_INCHES + max(0, x_tubes - 1) * self.PHYSICAL_CRATE_SPACING_INCHES)
            height_in = (y_tubes * self.PHYSICAL_TUBE_DIAMETER_INCHES + max(0, y_tubes - 1) * self.PHYSICAL_CRATE_SPACING_INCHES)
        elif rack_type == "Fan":
            width_in = (x_tubes * self.PHYSICAL_FAN_SEGMENT_WIDTH_INCHES + max(0, x_tubes - 1) * self.PHYSICAL_FAN_INTER_SEGMENT_SPACING_INCHES)
            height_in = (y_tubes * self.PHYSICAL_TUBE_DIAMETER_INCHES + max(0, y_tubes - 1) * self.PHYSICAL_FAN_TUBE_SPACING_INCHES)
        return f"{width_in:.1f}\" x {height_in:.1f}\""

    def _calculate_tube_color_breakdown(self, rack_config):
        if not rack_config or 'tubes' not in rack_config: return "N/A" 
        color_counts = defaultdict(int)
        for tube_data in rack_config['tubes']: 
            color_value = tube_data['color']
            color_name = next((name for name, val in self.FUSE_COLORS_MAP.items() if val == color_value), "Unknown")
            color_counts[color_name] += 1
        if not color_counts: return "No colors"
        sorted_colors = sorted(color_counts.items(), key=lambda item: (-item[1], item[0]))
        return ", ".join([f"{name}: {count}" for name, count in sorted_colors])

    def on_canvas_mouse_motion(self, event):
        if self._is_panning: # If panning, motion is handled by on_pan_motion
            return
        if self.drawing_flow_line_mode or self.connecting_tubes_mode:
            if not self.flow_line_start_point and not self.first_tube_for_connection: 
                 self.canvas.config(cursor="crosshair")
            return
        
        # Convert event coords to world for hit detection logic
        world_x, world_y = self.canvas_to_world(event.x, event.y)
        line_id_under_mouse = self._get_line_under_mouse(world_x, world_y) # Use world coords
        self.canvas.config(cursor="hand2" if line_id_under_mouse else "")
            
    def toggle_draw_flow_line_mode(self):
        self.drawing_flow_line_mode = not self.drawing_flow_line_mode
        if self.drawing_flow_line_mode and self.connecting_tubes_mode: self.toggle_connect_tubes_mode(force_off=True) 
        if self.drawing_flow_line_mode:
            self.draw_line_btn.config(text="Draw Flow Line (ON)")
            self.status_var.set("Line drawing mode ON. Click canvas for line start point.")
            self.selected_rack_ids.clear(); self.selected_flow_line_id = None; self.first_tube_for_connection = None 
            self.canvas.delete("temp_source_tube_highlight", "temp_connection_preview_line")
            self._update_ui_for_selection_state(); self.redraw_canvas() 
            self.canvas.unbind("<ButtonPress-1>"); self.canvas.unbind("<B1-Motion>")
            self.canvas.unbind("<ButtonRelease-1>"); self.canvas.unbind("<Shift-ButtonPress-1>")
            self.canvas.bind("<ButtonPress-1>", self.on_canvas_press_line_mode)
            self.canvas.bind("<B1-Motion>", self.on_flow_line_drag_preview) 
            self.canvas.config(cursor="crosshair")
        else: 
            self.draw_line_btn.config(text="Draw Flow Line (Off)")
            self.status_var.set("Line drawing mode OFF.")
            self.flow_line_start_point = None 
            self.canvas.delete("temp_flow_line", "temp_flow_line_start_marker") 
            self.canvas.config(cursor="") 
            self.canvas.unbind("<ButtonPress-1>"); self.canvas.unbind("<B1-Motion>")
            self.canvas.bind("<ButtonPress-1>", self.on_canvas_press); self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release); self.canvas.bind("<Shift-ButtonPress-1>", self.on_canvas_shift_click)

    def toggle_connect_tubes_mode(self, force_off=False):
        if force_off: self.connecting_tubes_mode = False
        else: self.connecting_tubes_mode = not self.connecting_tubes_mode
        if self.connecting_tubes_mode and self.drawing_flow_line_mode: self.toggle_draw_flow_line_mode() 
        if self.connecting_tubes_mode:
            self.connect_tubes_btn.config(text="Connect Tubes (ON)")
            self.status_var.set("Tube connect mode ON. Click source tube.")
            self.selected_rack_ids.clear(); self.selected_flow_line_id = None; self.flow_line_start_point = None 
            self.canvas.delete("temp_flow_line", "temp_flow_line_start_marker")
            self._update_ui_for_selection_state(); self.redraw_canvas() 
            self.canvas.unbind("<ButtonPress-1>"); self.canvas.unbind("<B1-Motion>") 
            self.canvas.unbind("<ButtonRelease-1>"); self.canvas.unbind("<Shift-ButtonPress-1>")
            self.canvas.bind("<ButtonPress-1>", self.on_canvas_press_connect_tubes_mode)
            self.canvas.bind("<Motion>", self.on_connect_tubes_drag_preview) 
            self.canvas.config(cursor="crosshair")
        else: 
            self.connect_tubes_btn.config(text="Connect Tubes (Off)")
            if not self.drawing_flow_line_mode: self.status_var.set("Tube connect mode OFF.")
            self.first_tube_for_connection = None 
            self.canvas.delete("temp_source_tube_highlight", "temp_connection_preview_line")
            self.canvas.config(cursor="") 
            self.canvas.unbind("<ButtonPress-1>"); self.canvas.unbind("<Motion>") 
            self.canvas.bind("<ButtonPress-1>", self.on_canvas_press); self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
            self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release); self.canvas.bind("<Shift-ButtonPress-1>", self.on_canvas_shift_click)
            self.canvas.bind("<Motion>", self.on_canvas_mouse_motion) 
        self.redraw_canvas() 

    def on_connect_tubes_drag_preview(self, event):
        if self.connecting_tubes_mode and self.first_tube_for_connection:
            world_x, world_y = self.canvas_to_world(event.x, event.y) # Convert for drawing logic if it expects world
            self._draw_temporary_connection_line(world_x, world_y) # Pass world coords
        # Call general mouse motion, which now also uses world coords for its internal checks
        self.on_canvas_mouse_motion(event) 


    def on_flow_line_drag_preview(self, event):
        if self.drawing_flow_line_mode and self.flow_line_start_point:
            self.canvas.delete("temp_flow_line") 
            # Start point is already in world coords if set in on_canvas_press_line_mode
            wx1_start, wy1_start = self.flow_line_start_point 
            # Current mouse position is canvas, convert to world for preview end
            wx2, wy2 = self.canvas_to_world(event.x, event.y)
            
            # Convert back to canvas for drawing the temp line
            cx1, cy1 = self.world_to_canvas(wx1_start, wy1_start)
            cx2, cy2 = self.world_to_canvas(wx2, wy2) # This is just event.x, event.y
            
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill="gray", width=max(1, self.LINE_TOOL_WIDTH * self.zoom_level), dash=(3,3), tags="temp_flow_line")


    def _get_tube_at_canvas_coords(self, canvas_x, canvas_y): # Input is canvas coords
        world_x, world_y = self.canvas_to_world(canvas_x, canvas_y)
        for rack_config in reversed(self.racks_on_canvas): 
            tube_center_points_info, _, _, _, _ = self._get_rack_dimensions_and_points(rack_config) # This returns world coords
            for tube_idx, tube_cx_world, tube_cy_world, tube_dia_world in tube_center_points_info:
                # Compare in world coordinates
                if (world_x - tube_cx_world)**2 + (world_y - tube_cy_world)**2 <= (tube_dia_world / 2)**2:
                    return rack_config['id'], tube_idx 
        return None, None 

    def on_canvas_press_connect_tubes_mode(self, event):
        if not self.connecting_tubes_mode: return
        clicked_rack_id, clicked_tube_idx = self._get_tube_at_canvas_coords(event.x, event.y)
        if clicked_rack_id is None: 
            self.first_tube_for_connection = None 
            self.canvas.delete("temp_source_tube_highlight", "temp_connection_preview_line")
            self.status_var.set("Tube connect mode: Click source tube."); self.redraw_canvas() 
            return
        if not self.first_tube_for_connection: 
            self.first_tube_for_connection = (clicked_rack_id, clicked_tube_idx)
            self._highlight_source_tube() 
            self.status_var.set(f"Source tube selected (Rack ...{clicked_rack_id[-6:]}, Tube {clicked_tube_idx+1}). Click target tube.")
        else: 
            source_rack_id, source_tube_idx = self.first_tube_for_connection
            if source_rack_id == clicked_rack_id and source_tube_idx == clicked_tube_idx:
                self.status_var.set("Cannot connect a tube to itself. Click a different target tube."); return
            connection = {'id': str(uuid.uuid4()), 'source_rack_id': source_rack_id, 'source_tube_idx': source_tube_idx,
                          'target_rack_id': clicked_rack_id, 'target_tube_idx': clicked_tube_idx, 'color': '#00FF00'}
            self.tube_connections.append(connection); self._record_state_for_undo() 
            self.status_var.set(f"Connected Rack ...{source_rack_id[-6:]} T{source_tube_idx+1} to Rack ...{clicked_rack_id[-6:]} T{clicked_tube_idx+1}.")
            self.first_tube_for_connection = None 
            self.canvas.delete("temp_source_tube_highlight", "temp_connection_preview_line"); self.redraw_canvas() 
            self.status_var.set("Tube connected. Click another source tube or turn off mode.") 

    def _highlight_source_tube(self):
        self.canvas.delete("temp_source_tube_highlight") 
        if self.first_tube_for_connection:
            rack_id, tube_idx = self.first_tube_for_connection
            source_rack = next((r for r in self.racks_on_canvas if r['id'] == rack_id), None)
            if source_rack:
                all_tubes_info, _, _, _, _ = self._get_rack_dimensions_and_points(source_rack) # Returns world coords
                tube_info_match = None
                for ti_idx, ti_cx_world, ti_cy_world, ti_dia_world in all_tubes_info:
                    if ti_idx == tube_idx:
                        tube_info_match = (ti_idx, ti_cx_world, ti_cy_world, ti_dia_world)
                        break
                if tube_info_match:
                    _, cx_w, cy_w, dia_w = tube_info_match 
                    # Convert world center and diameter to canvas for drawing highlight
                    cx_c, cy_c = self.world_to_canvas(cx_w, cy_w)
                    dia_c = dia_w * self.zoom_level # Diameter also needs scaling
                    
                    self.canvas.create_oval(cx_c - dia_c/2 -1, cy_c - dia_c/2 -1, cx_c + dia_c/2 +1, cy_c + dia_c/2+1, 
                                            outline="orange", width=3 * self.zoom_level, tags="temp_source_tube_highlight")


    def _draw_temporary_connection_line(self, world_mouse_x, world_mouse_y): # Expects world mouse coords
        self.canvas.delete("temp_connection_preview_line") 
        if self.first_tube_for_connection:
            rack_id, tube_idx = self.first_tube_for_connection
            source_rack = next((r for r in self.racks_on_canvas if r['id'] == rack_id), None)
            if source_rack:
                all_tubes_info, _, _, _, _ = self._get_rack_dimensions_and_points(source_rack) # World coords
                tube_info_match = None
                for ti_idx, ti_cx_w, ti_cy_w, ti_dia_w in all_tubes_info:
                    if ti_idx == tube_idx:
                        tube_info_match = (ti_idx, ti_cx_w, ti_cy_w, ti_dia_w)
                        break
                if tube_info_match:
                    _, x1_w, y1_w, _ = tube_info_match # World coords of source tube center
                    # Convert to canvas for drawing
                    x1_c, y1_c = self.world_to_canvas(x1_w, y1_w)
                    x2_c, y2_c = self.world_to_canvas(world_mouse_x, world_mouse_y)
                    
                    self.canvas.create_line(x1_c, y1_c, x2_c, y2_c, fill="gray", width=1.5 * self.zoom_level, dash=(3,3), tags="temp_connection_preview_line")


    def on_canvas_press_line_mode(self, event):
        if not self.drawing_flow_line_mode: return
        
        world_x, world_y = self.canvas_to_world(event.x, event.y) # Convert click to world coords

        if not self.flow_line_start_point: 
            self.flow_line_start_point = (world_x, world_y) # Store world coords
            self.status_var.set("Line start point set. Move mouse and click for end point.")
            self.canvas.delete("temp_flow_line_start_marker") 
            # Marker drawn at canvas coords
            marker_size_c = 3 * self.zoom_level
            self.canvas.create_oval(event.x - marker_size_c, event.y - marker_size_c, 
                                    event.x + marker_size_c, event.y + marker_size_c, 
                                    fill=self.LINE_TOOL_COLOR_DEFAULT, outline=self.LINE_TOOL_COLOR_DEFAULT, 
                                    tags="temp_flow_line_start_marker")
        else: 
            wx1, wy1 = self.flow_line_start_point # World coords
            wx2, wy2 = world_x, world_y # World coords
            
            if math.hypot(wx2-wx1, wy2-wy1) * self.zoom_level < 5 : # Check visual length on canvas
                self.status_var.set("Line too short. Click further away for end point."); return

            line_id = str(uuid.uuid4())
            line_data = {'id': line_id, 'x1': wx1, 'y1': wy1, 'x2': wx2, 'y2': wy2, # Store world coords
                         'color': self.LINE_TOOL_COLOR_DEFAULT, 'width': self.LINE_TOOL_WIDTH, 'label': ''} 
            self.flow_lines_on_canvas.append(line_data); self._record_state_for_undo() 
            self.flow_line_start_point = None 
            self.canvas.delete("temp_flow_line", "temp_flow_line_start_marker"); self.redraw_canvas() 
            self.status_var.set(f"Flow line added. To draw another, click 'Draw Flow Line (Off)' to re-enable.")
            self.toggle_draw_flow_line_mode() 

    def clear_all_flow_lines(self):
        if not self.flow_lines_on_canvas: self.status_var.set("No flow lines to clear."); return
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear ALL flow lines?\nThis action cannot be undone via the Undo button.", icon='warning'):
            self._record_state_for_undo(); self.flow_lines_on_canvas.clear(); self.selected_flow_line_id = None 
            self.redraw_canvas(); self.status_var.set("All flow lines cleared."); self._update_ui_for_selection_state() 

    def clear_all_tube_connections(self):
        if not self.tube_connections: self.status_var.set("No tube connections to clear."); return
        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear ALL tube connections?\nThis action cannot be undone via the Undo button.", icon='warning'):
            self._record_state_for_undo(); self.tube_connections.clear(); self.first_tube_for_connection = None 
            self.canvas.delete("temp_source_tube_highlight", "temp_connection_preview_line")
            self.redraw_canvas(); self.status_var.set("All tube connections cleared."); self._update_ui_for_selection_state()     

    def _get_line_under_mouse(self, world_x, world_y): # Expects world coords
        for line_data in reversed(self.flow_lines_on_canvas): 
            wx1, wy1, wx2, wy2 = line_data['x1'], line_data['y1'], line_data['x2'], line_data['y2'] # World coords
            
            # Bounding box check in world coords, halo needs to be scaled from canvas to world
            world_halo = self.LINE_CLICK_HALO / self.zoom_level
            min_wx, max_wx = min(wx1, wx2), max(wx1, wx2)
            min_wy, max_wy = min(wy1, wy2), max(wy1, wy2)
            if not (min_wx - world_halo <= world_x <= max_wx + world_halo and \
                    min_wy - world_halo <= world_y <= max_wy + world_halo):
                continue

            dx_w, dy_w = wx2 - wx1, wy2 - wy1
            if dx_w == 0 and dy_w == 0: dist_w = math.hypot(world_x - wx1, world_y - wy1)
            else:
                t = ((world_x - wx1) * dx_w + (world_y - wy1) * dy_w) / (dx_w*dx_w + dy_w*dy_w)
                t = max(0, min(1, t)); closest_wx, closest_wy = wx1 + t * dx_w, wy1 + t * dy_w
                dist_w = math.hypot(world_x - closest_wx, world_y - closest_wy)
            
            if dist_w <= world_halo: return line_data['id']
        return None

    def _draw_flow_lines(self):
        for line_data in self.flow_lines_on_canvas:
            wx1, wy1, wx2, wy2 = line_data['x1'], line_data['y1'], line_data['x2'], line_data['y2']
            cx1, cy1 = self.world_to_canvas(wx1, wy1)
            cx2, cy2 = self.world_to_canvas(wx2, wy2)
            
            current_color = line_data.get('color', self.LINE_TOOL_COLOR_DEFAULT)
            current_width_world = float(line_data.get('width', self.LINE_TOOL_WIDTH))
            current_width_canvas = max(1, current_width_world * self.zoom_level) # Ensure minimum 1px width
            
            if self.selected_flow_line_id == line_data['id']:
                current_color = self.SELECTED_LINE_COLOR; current_width_canvas += 1 
            
            line_id_tag = f"flow_line_{line_data['id']}"; tags = (line_id_tag, "flow_line") 
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=current_color, width=current_width_canvas, tags=tags, capstyle=tk.ROUND, smooth=tk.TRUE)
            
            if math.hypot(wx2-wx1, wy2-wy1) == 0: continue 
            
            angle = math.atan2(cy2 - cy1, cx2 - cx1); # Use canvas coords for angle of drawn line
            cap_len_canvas = self.LINE_CAP_LENGTH * self.zoom_level
            cap_angle_offset = math.pi / 2 
            
            csx_offset = cap_len_canvas * math.cos(angle + cap_angle_offset)
            csy_offset = cap_len_canvas * math.sin(angle + cap_angle_offset)
            self.canvas.create_line(cx1 - csx_offset, cy1 - csy_offset, cx1 + csx_offset, cy1 + csy_offset, 
                                    fill=current_color, width=current_width_canvas, tags=tags, capstyle=tk.ROUND)
            cex_offset = cap_len_canvas * math.cos(angle + cap_angle_offset)
            cey_offset = cap_len_canvas * math.sin(angle + cap_angle_offset)
            self.canvas.create_line(cx2 - cex_offset, cy2 - cey_offset, cx2 + cex_offset, cy2 + cey_offset, 
                                    fill=current_color, width=current_width_canvas, tags=tags, capstyle=tk.ROUND)
            
            line_label = line_data.get('label', '')
            if line_label:
                mid_cx, mid_cy = (cx1 + cx2) / 2, (cy1 + cy2) / 2
                font_size = max(6, int(8 * self.zoom_level)) # Scale font size
                self.canvas.create_text(mid_cx, mid_cy - (10 * self.zoom_level), text=line_label, fill="purple", 
                                        font=("Arial", font_size, "italic"), anchor=tk.S, tags=tags)

    def _draw_tube_connections(self):
        for conn in self.tube_connections:
            source_rack = next((r for r in self.racks_on_canvas if r['id'] == conn['source_rack_id']), None)
            target_rack = next((r for r in self.racks_on_canvas if r['id'] == conn['target_rack_id']), None)
            if not source_rack or not target_rack: continue
            source_tubes_info, _, _, _, _ = self._get_rack_dimensions_and_points(source_rack) # World coords
            target_tubes_info, _, _, _, _ = self._get_rack_dimensions_and_points(target_rack) # World coords
            
            source_tube_center_w = None
            for idx, cx_w, cy_w, _ in source_tubes_info:
                if idx == conn['source_tube_idx']: source_tube_center_w = (cx_w,cy_w); break
            
            target_tube_center_w = None
            for idx, cx_w, cy_w, _ in target_tubes_info:
                if idx == conn['target_tube_idx']: target_tube_center_w = (cx_w,cy_w); break

            if source_tube_center_w and target_tube_center_w:
                x1_c, y1_c = self.world_to_canvas(*source_tube_center_w)
                x2_c, y2_c = self.world_to_canvas(*target_tube_center_w)
                arrow_width = max(1, 1.5 * self.zoom_level)
                arrow_shape = (max(4, int(8*self.zoom_level)), max(5, int(10*self.zoom_level)), max(1, int(3*self.zoom_level)))

                self.canvas.create_line(x1_c, y1_c, x2_c, y2_c, fill=conn.get('color', '#00FF00'), 
                                        width=arrow_width, arrow=tk.LAST, arrowshape=arrow_shape, 
                                        tags=(f"tube_conn_{conn['id']}", "tube_connection"))

    def _update_canvas_summary_info(self):
        total_tubes = 0; fuse_lengths_by_color_value = defaultdict(float); total_show_duration_seconds = 0.0
        for rack_config in self.racks_on_canvas:
            num_tubes_in_rack = rack_config.get('x_tubes', 0) * rack_config.get('y_tubes', 0)
            total_tubes += num_tubes_in_rack
            if num_tubes_in_rack == 0: continue 
            rack_type = rack_config.get('type'); current_rack_total_fuse_length_inches = 0.0 
            if rack_type == "Crate":
                base_crate_tubes = 5*5 
                scale_factor = num_tubes_in_rack / base_crate_tubes if base_crate_tubes > 0 else 1
                current_rack_total_fuse_length_inches = self.DEFAULT_CRATE_FUSE_INCHES * scale_factor
            elif rack_type == "Fan":
                num_segments = rack_config.get('x_tubes', 0); tubes_per_segment = rack_config.get('y_tubes', 0)
                if num_segments > 0 and tubes_per_segment > 0:
                    fuse_within_all_segments = num_segments * max(0, tubes_per_segment - 1) * self.FAN_CHAIN_INTER_TUBE_ALLOWANCE_INCHES
                    fuse_linking_segments = max(0, num_segments - 1) * self.FAN_CHAIN_INTER_SEGMENT_ALLOWANCE_INCHES
                    current_rack_total_fuse_length_inches = (self.FAN_CHAIN_LEAD_INCHES + fuse_within_all_segments + 
                                              fuse_linking_segments + self.FAN_CHAIN_TAIL_INCHES)
            if current_rack_total_fuse_length_inches > 0 and num_tubes_in_rack > 0:
                fuse_per_tube_in_rack_inches = (current_rack_total_fuse_length_inches * self.FUSE_LENGTH_SCALE_FACTOR) / num_tubes_in_rack
                for tube_data in rack_config.get('tubes', []): 
                    fuse_lengths_by_color_value[tube_data['color']] += fuse_per_tube_in_rack_inches
        self.tube_count_var.set(f"Total Tubes: {total_tubes}")
        for color_val, total_length_inches in fuse_lengths_by_color_value.items():
            if color_val in self.FUSE_BURN_RATES_SPF:
                burn_rate_spf = self.FUSE_BURN_RATES_SPF[color_val]
                length_feet = total_length_inches / self.INCHES_PER_FOOT
                total_show_duration_seconds += length_feet * burn_rate_spf
        self.show_duration_var.set(f"Est. Duration: {total_show_duration_seconds:.1f}s")
        if not self.racks_on_canvas and not self.flow_lines_on_canvas : 
            self.fuse_estimation_var.set(f"Est. Fuse ({self.FUSE_ESTIMATE_UNIT}): N/A")
        else:
            fuse_strings = []
            for color_name, color_value_map in sorted(self.FUSE_COLORS_MAP.items()):
                length_for_this_color_inches = fuse_lengths_by_color_value[color_value_map]
                if length_for_this_color_inches > 0.001:
                    length_for_this_color_feet = length_for_this_color_inches / self.INCHES_PER_FOOT
                    fuse_strings.append(f"{color_name}: {length_for_this_color_feet:.2f}") # Show more precision for feet
            base_str = f"Est. Fuse ({self.FUSE_ESTIMATE_UNIT}): "
            if not fuse_strings and total_tubes == 0 : self.fuse_estimation_var.set(base_str + "N/A")
            elif not fuse_strings and total_tubes > 0 : self.fuse_estimation_var.set(base_str + "(No calc. fuse)")
            else: self.fuse_estimation_var.set(base_str + ", ".join(fuse_strings))

    def redraw_canvas(self):
        self.canvas.delete("all") 
        # Grid needs to be drawn relative to current pan and zoom
        if self.snap_to_grid_enabled.get():
            try:
                grid_s_world = int(self.grid_size_var.get()) # Grid size is in world units
                if grid_s_world > 0:
                    grid_s_canvas = grid_s_world * self.zoom_level
                    # Calculate start/end based on visible canvas area in world coords
                    world_x_start, world_y_start = self.canvas_to_world(0,0)
                    world_x_end, world_y_end = self.canvas_to_world(self.CANVAS_WIDTH, self.CANVAS_HEIGHT)

                    start_grid_x = math.floor(world_x_start / grid_s_world) * grid_s_world
                    start_grid_y = math.floor(world_y_start / grid_s_world) * grid_s_world

                    # Only draw lines that would be visible or nearly visible
                    for i in range(int((world_x_end - start_grid_x) / grid_s_world) + 2):
                        wx = start_grid_x + i * grid_s_world
                        cx, _ = self.world_to_canvas(wx, 0) # Y doesn't matter for vertical line x-pos
                        self.canvas.create_line(cx, 0, cx, self.CANVAS_HEIGHT, fill="lightgrey", dash=(2,2), tags="gridline")
                    
                    for i in range(int((world_y_end - start_grid_y) / grid_s_world) + 2):
                        wy = start_grid_y + i * grid_s_world
                        _, cy = self.world_to_canvas(0, wy) # X doesn't matter for horiz line y-pos
                        self.canvas.create_line(0, cy, self.CANVAS_WIDTH, cy, fill="lightgrey", dash=(2,2), tags="gridline")
            except ValueError: pass 

        if not self.racks_on_canvas and not self.flow_lines_on_canvas and not self.tube_connections:
            # Center text on canvas, independent of zoom/pan for this message
            self.canvas.create_text(self.CANVAS_WIDTH/2,self.CANVAS_HEIGHT/2,text="Canvas empty. Add racks or load a layout.",fill="darkgray",font=("Arial",12))
        else: # Racks, lines or connections exist
            # Pre-calculate global tube numbering offsets if enabled
            self.rack_global_start_indices.clear() # Clear previous calculations
            if self.show_tube_numbers_var.get():
                current_global_idx = 0
                try:
                    # Sort racks by visual position (top-to-bottom, then left-to-right)
                    # The 'pos_x' and 'pos_y' are world coordinates of the rack's anchor.
                    # Changed to left-to-right, then top-to-bottom
                    sorted_racks_for_numbering = sorted( # Use a local var for sorting, then populate instance var
                        self.racks_on_canvas,
                        key=lambda r_cfg: (float(r_cfg['pos_x']), float(r_cfg['pos_y']))
                    )
                    for r_cfg in sorted_racks_for_numbering:
                        self.rack_global_start_indices[r_cfg['id']] = current_global_idx
                        num_tubes_in_rack = r_cfg.get('x_tubes', 0) * r_cfg.get('y_tubes', 0)
                        current_global_idx += num_tubes_in_rack
                except (ValueError, TypeError) as e:
                    print(f"Warning: Could not sort racks for global numbering due to invalid position data: {e}")
                    self.rack_global_start_indices.clear() # Fallback to local numbering

            # Draw racks (iterate in current order, numbering will use the map)
            for rack_config in self.racks_on_canvas:
                # Check if rack is roughly in view before detailed drawing (basic culling)
                # This is a very simple culling, more precise would use full rotated bounding box
                rack_cx_w, rack_cy_w = float(rack_config['pos_x']), float(rack_config['pos_y'])
                # A more accurate culling would consider rack dimensions + zoom
                # For now, draw all. Could be optimized later if performance is an issue.

                start_num_for_this_rack = 0
                use_global_numbering_for_this_rack = False
                if self.show_tube_numbers_var.get() and rack_config['id'] in self.rack_global_start_indices:
                    start_num_for_this_rack = self.rack_global_start_indices[rack_config['id']]
                    use_global_numbering_for_this_rack = True
                
                if rack_config['type']=="Crate":
                    self._draw_crate_rack(rack_config, start_num_for_this_rack, use_global_numbering_for_this_rack)
                elif rack_config['type']=="Fan":
                    self._draw_fan_rack(rack_config, start_num_for_this_rack, use_global_numbering_for_this_rack)
                
                self._draw_rack_name(rack_config) 
            self._draw_flow_lines()
            self._draw_tube_connections() 
        self._update_canvas_summary_info() 
        if self.first_tube_for_connection: self._highlight_source_tube() 

    def save_layout(self):
        filepath=filedialog.asksaveasfilename(defaultextension=".json",filetypes=[("JSON files","*.json"),("All files","*.*")],title="Save Firework Layout")
        if not filepath:return
        try:
            racks_to_save=[{**r,'pos_x':float(r['pos_x']),'pos_y':float(r['pos_y'])} for r in self.racks_on_canvas]
            # Add canvas view state to save file
            layout_data = {'racks': racks_to_save, 
                           'flow_lines': self.flow_lines_on_canvas, 
                           'tube_connections': self.tube_connections,
                           'canvas_view': {
                               'zoom_level': self.zoom_level,
                               'pan_offset_x': self.pan_offset_x,
                               'pan_offset_y': self.pan_offset_y
                           }}
            with open(filepath,'w') as f:json.dump(layout_data,f,indent=4)
            self.status_var.set(f"Layout saved to {filepath.split('/')[-1]}")
        except Exception as e:messagebox.showerror("Save Error",f"Failed to save layout: {e}");self.status_var.set(f"Error saving layout: {e}")

    def load_layout(self):
        filepath=filedialog.askopenfilename(filetypes=[("JSON files","*.json"),("All files","*.*")],title="Load Firework Layout")
        if not filepath:return
        try:
            with open(filepath,'r') as f:loaded_data=json.load(f)
            if isinstance(loaded_data, list): 
                loaded_racks_raw = loaded_data; self.flow_lines_on_canvas = []; self.tube_connections = [] 
                # Reset view for old format files
                self.zoom_level = 1.0; self.pan_offset_x = 0.0; self.pan_offset_y = 0.0
            elif isinstance(loaded_data, dict): 
                loaded_racks_raw = loaded_data.get('racks', [])
                self.flow_lines_on_canvas = loaded_data.get('flow_lines', [])
                self.tube_connections = loaded_data.get('tube_connections', [])
                canvas_view_data = loaded_data.get('canvas_view', {})
                self.zoom_level = canvas_view_data.get('zoom_level', 1.0)
                self.pan_offset_x = canvas_view_data.get('pan_offset_x', 0.0)
                self.pan_offset_y = canvas_view_data.get('pan_offset_y', 0.0)
            else: raise ValueError("Invalid file format.")
            loaded_racks_validated=[]
            for i, rack_data_loaded in enumerate(loaded_racks_raw): 
                if not isinstance(rack_data_loaded,dict):continue 
                required_keys=['id','type','x_tubes','y_tubes','pos_x','pos_y'] 
                rack_data_loaded.setdefault('name', f"{rack_data_loaded.get('type', 'Rack')} {i+1}") 
                has_old_colors = 'tube_colors' in rack_data_loaded
                has_new_tubes = 'tubes' in rack_data_loaded
                if not (all(k in rack_data_loaded for k in required_keys if k not in ['tubes', 'tube_colors']) and (has_old_colors or has_new_tubes)):
                    print(f"Skipping rack due to missing essential keys: {rack_data_loaded.get('id','N/A')}")
                    continue
                rack_data_loaded.setdefault('rotation_angle',0)
                rack_data_loaded.setdefault('tube_diameter',self.DEFAULT_TUBE_DIAMETER)
                try:
                    rack_data_loaded['pos_x']=float(rack_data_loaded['pos_x'])
                    rack_data_loaded['pos_y']=float(rack_data_loaded['pos_y'])
                    rack_data_loaded['x_tubes']=int(rack_data_loaded['x_tubes'])
                    rack_data_loaded['y_tubes']=int(rack_data_loaded['y_tubes'])
                    rack_data_loaded['tube_diameter']=int(rack_data_loaded['tube_diameter'])
                    rack_data_loaded['rotation_angle']=int(rack_data_loaded['rotation_angle'])
                    num_total_tubes = rack_data_loaded['x_tubes'] * rack_data_loaded['y_tubes']
                    if has_new_tubes and isinstance(rack_data_loaded['tubes'], list):
                        validated_tubes = []
                        for tube_entry in rack_data_loaded['tubes']:
                            if isinstance(tube_entry, dict) and 'color' in tube_entry:
                                validated_tubes.append({
                                    'color': tube_entry['color'] if tube_entry['color'] in self.FUSE_COLORS_MAP.values() else self.default_new_tube_color_value,
                                    'angle': tube_entry.get('angle', 0), 
                                    'lift_time': tube_entry.get('lift_time', 0.0), # Load lift_time
                                    'type': tube_entry.get('type', "Standard"), # Load type
                                    'cue': tube_entry.get('cue', '') # Load cue
                                })
                            else: 
                                validated_tubes.append({'color': self.default_new_tube_color_value, 'angle': 0, 'lift_time': 0.0, 'cue': ''})
                        rack_data_loaded['tubes'] = validated_tubes
                        if 'tube_colors' in rack_data_loaded: del rack_data_loaded['tube_colors'] 
                    elif has_old_colors and isinstance(rack_data_loaded.get('tube_colors'), list):
                        rack_data_loaded['tubes'] = []
                        for color_val in rack_data_loaded['tube_colors']:
                            rack_data_loaded['tubes'].append({
                                'color': color_val if color_val in self.FUSE_COLORS_MAP.values() else self.default_new_tube_color_value,
                                'angle': 0, 'lift_time': 0.0, 'type': "Standard", 'cue': ''
                            })
                        del rack_data_loaded['tube_colors'] 
                    else: 
                        rack_data_loaded['tubes'] = self._generate_default_tube_data(num_total_tubes)
                        if 'tube_colors' in rack_data_loaded: del rack_data_loaded['tube_colors']
                except ValueError as ve:
                    print(f"Skipping rack due to data type error ({rack_data_loaded.get('id','N/A')}): {ve}")
                    continue
                loaded_racks_validated.append(rack_data_loaded)
            self.racks_on_canvas=loaded_racks_validated
            self.selected_rack_ids=[] 
            self.selected_flow_line_id = None
            self.redraw_canvas()
            self._update_ui_for_selection_state(); self._update_rack_list_panel()
            self.undo_stack.clear(); self.redo_stack.clear(); self._update_undo_redo_buttons_state()
            self.status_var.set(f"Layout loaded. {len(self.racks_on_canvas)} racks, {len(self.flow_lines_on_canvas)} lines, {len(self.tube_connections)} connections.")
        except Exception as e:
            messagebox.showerror("Load Error",f"Failed to load layout: {e}")
            self.status_var.set(f"Error loading layout: {e}")

    def redraw_canvas_if_valid_grid(self, *args, force_redraw=False):
        if force_redraw: self.redraw_canvas(); return
        try:
            if int(self.grid_size_var.get()) > 0: self.redraw_canvas()
        except ValueError: pass 

    def export_canvas_as_image(self):
        if not PIL_AVAILABLE: messagebox.showerror("Error", "Pillow library is not installed. Cannot export image."); return
        filepath = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG files", "*.png"), ("JPEG files", "*.jpg")], title="Export Canvas As Image")
        if not filepath: return
        try: 
            original_selected_racks = list(self.selected_rack_ids); original_selected_line = self.selected_flow_line_id
            self.selected_rack_ids.clear(); self.selected_flow_line_id = None
            self.redraw_canvas(); self.canvas.update_idletasks() 
            x1 = self.canvas.winfo_rootx(); y1 = self.canvas.winfo_rooty()
            x2 = x1 + self.canvas.winfo_width(); y2 = y1 + self.canvas.winfo_height()
            self.root.after(250, lambda: self._perform_grab_and_restore_selection(filepath, (x1, y1, x2, y2), original_selected_racks, original_selected_line))
        except Exception as e: messagebox.showerror("Export Error", f"Failed to export image: {e}"); self.status_var.set(f"Error exporting image: {e}")

    def _perform_grab_and_restore_selection(self, filepath, bbox, original_racks, original_line):
        try:
            ImageGrab.grab(bbox=bbox).save(filepath)
            self.status_var.set(f"Canvas exported to {filepath.split('/')[-1]}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to grab and save image: {e}.\nEnsure the window is fully visible.")
            self.status_var.set(f"Error grabbing image: {e}")
        finally:
            self.selected_rack_ids = original_racks; self.selected_flow_line_id = original_line
            self.redraw_canvas(); self._update_ui_for_selection_state()

    def apply_rack_name_from_ui(self,event=None): 
        if len(self.selected_rack_ids)==1 and not self.selected_flow_line_id: 
            rack=next((r for r in self.racks_on_canvas if r['id']==self.selected_rack_ids[0]),None)
            if rack and rack.get('name','') != self.rack_name_var.get().strip():
                rack['name']=self.rack_name_var.get().strip(); self._record_state_for_undo() 
                self.status_var.set(f"Rack '{rack['name']}' name updated.")
                self.redraw_canvas();self._update_rack_list_panel() 

    def apply_flow_line_label_from_ui(self, event=None):
        if self.selected_flow_line_id:
            line = next((ln for ln in self.flow_lines_on_canvas if ln['id'] == self.selected_flow_line_id), None)
            if line:
                new_label = self.flow_line_label_var.get().strip()
                if line.get('label', '') != new_label:
                    line['label'] = new_label
                    self._record_state_for_undo()
                    self.status_var.set(f"Flow line ...{line['id'][-6:]} label updated.")
                    self.redraw_canvas() 

    def apply_position_from_ui(self,event=None): 
        if len(self.selected_rack_ids)==1 and not self.selected_flow_line_id:
            rack=next((r for r in self.racks_on_canvas if r['id']==self.selected_rack_ids[0]),None)
            if rack:
                try:
                    new_x=int(self.pos_x_var.get());new_y=int(self.pos_y_var.get())
                    if float(rack['pos_x'])!=new_x or float(rack['pos_y'])!=new_y: 
                        rack['pos_x']=new_x;rack['pos_y']=new_y; self._record_state_for_undo()
                        self.status_var.set(f"Rack '{rack.get('name', 'Unnamed')}' position updated.")
                        self.redraw_canvas(); self._update_rack_list_panel() 
                except ValueError:
                    self.status_var.set("Error: Invalid X or Y position.");
                    self.pos_x_var.set(str(int(float(rack['pos_x']))));self.pos_y_var.set(str(int(float(rack['pos_y']))))

    def apply_rotation_from_ui(self,event=None): 
        if len(self.selected_rack_ids)==1 and not self.selected_flow_line_id:
            rack=next((r for r in self.racks_on_canvas if r['id']==self.selected_rack_ids[0]),None)
            if rack and rack.get('rotation_angle')!=int(self.rotation_var.get()):
                rack['rotation_angle']=int(self.rotation_var.get()); self._record_state_for_undo()
                self.status_var.set(f"Rack '{rack.get('name', 'Unnamed')}' rotation updated.")
                self.redraw_canvas()
            elif not rack: self.status_var.set("Error: Invalid rotation.");self.rotation_var.set(rack.get('rotation_angle',0))


    def nudge_selected_racks(self,dx,dy): 
        if self.selected_flow_line_id: self.status_var.set("Nudge not applicable to flow lines."); return
        if not self.selected_rack_ids:self.status_var.set("No racks selected to nudge.");return
        moved_count=0; self._record_state_for_undo() 
        for rack_id in self.selected_rack_ids:
            rack=next((r for r in self.racks_on_canvas if r['id']==rack_id),None)
            if rack:rack['pos_x']=float(rack['pos_x'])+dx;rack['pos_y']=float(rack['pos_y'])+dy;moved_count+=1
        if moved_count>0:
            self.redraw_canvas();
            if len(self.selected_rack_ids)==1:self._update_ui_for_selection_state() 
            self.status_var.set(f"Nudged {moved_count} rack(s)."); self._update_rack_list_panel() 

    def _update_rack_list_panel(self):
        for item in self.rack_inspector_tree.get_children():
            self.rack_inspector_tree.delete(item)
        
        for rack_config in self.racks_on_canvas:
            rack_id = rack_config['id']
            name = rack_config.get('name', f"Unnamed Rack ...{rack_id[-6:]}")
            type_val = rack_config.get('type', 'N/A')
            dims_val = f"{rack_config.get('x_tubes',0)}x{rack_config.get('y_tubes',0)}"
            num_tubes_val = rack_config.get('x_tubes',0) * rack_config.get('y_tubes',0)
            rot_val = rack_config.get('rotation_angle', 0)
            
            global_start_val = "N/A"
            if self.show_tube_numbers_var.get() and rack_id in self.rack_global_start_indices:
                global_start_val = self.rack_global_start_indices[rack_id] + 1

            # Use rack_id as iid for direct mapping
            self.rack_inspector_tree.insert("", tk.END, iid=rack_id, text=name, values=(
                rack_id[-6:], type_val, dims_val, num_tubes_val, rot_val, global_start_val
            ))
        self._update_rack_list_panel_selection() 

    def on_rack_inspector_select(self,event=None): 
        if not event: return 
        selected_iids = self.rack_inspector_tree.selection() # Returns a tuple of iids (which are our rack_ids)
        newly_selected_ids = list(selected_iids)
        if set(self.selected_rack_ids) != set(newly_selected_ids) or len(self.selected_rack_ids) != len(newly_selected_ids):
            self.selected_rack_ids=newly_selected_ids; self.selected_flow_line_id = None 
            self._update_ui_for_selection_state(); self.redraw_canvas() 

    def show_context_menu(self,event): 
        if self.drawing_flow_line_mode or self.connecting_tubes_mode: return
        
        world_x, world_y = self.canvas_to_world(event.x, event.y) # Convert to world for hit detection
        clicked_line_id = self._get_line_under_mouse(world_x, world_y)

        if clicked_line_id: 
            self.selected_flow_line_id = clicked_line_id; self.selected_rack_ids.clear() 
            self.context_menu_line_id = clicked_line_id; self.redraw_canvas() 
            self._update_ui_for_selection_state(); self.line_context_menu.tk_popup(event.x_root,event.y_root)
        else: 
            clicked_rack_config=None 
            for rack_config_iter in reversed(self.racks_on_canvas):
                # _get_rack_dimensions_and_points returns world outline, _is_point_in_polygon expects world points
                _,outline_points_world,_,_,_=self._get_rack_dimensions_and_points(rack_config_iter)
                if self._is_point_in_polygon(world_x, world_y, outline_points_world): 
                    clicked_rack_config=rack_config_iter; break
            if clicked_rack_config: 
                self.context_menu_rack_id=clicked_rack_config['id']
                if clicked_rack_config['id'] not in self.selected_rack_ids:
                    self.selected_rack_ids=[clicked_rack_config['id']]; self.selected_flow_line_id = None 
                    self._update_ui_for_selection_state(); self.redraw_canvas() 
                self.rack_context_menu.entryconfigure("Recolor Tubes...",state=tk.NORMAL if len(self.selected_rack_ids)==1 else tk.DISABLED)
                self.rack_context_menu.tk_popup(event.x_root,event.y_root)
                self.rack_context_menu.entryconfigure("Edit Firework Types...", state=tk.NORMAL if len(self.selected_rack_ids) == 1 else tk.DISABLED)

    def change_selected_line_color(self, new_color):
        line_id_to_change = self.context_menu_line_id if self.context_menu_line_id else self.selected_flow_line_id
        if line_id_to_change:
            for line_data in self.flow_lines_on_canvas:
                if line_data['id'] == line_id_to_change and line_data.get('color') != new_color:
                    line_data['color'] = new_color; self._record_state_for_undo() 
                    self.redraw_canvas(); self.status_var.set(f"Flow line ...{line_id_to_change[-6:]} color changed.")
                    self._update_ui_for_selection_state() 
                    break
        self.context_menu_line_id = None 

    def open_tube_recolor_dialog_ctx(self):
        if self.context_menu_rack_id and self.context_menu_rack_id in self.selected_rack_ids and len(self.selected_rack_ids)==1:
            self.open_tube_recolor_dialog()
        else:self.status_var.set("Recolor tubes requires a single rack selected via right-click.")
    def duplicate_selected_racks_ctx(self):
        if self.selected_rack_ids:self.duplicate_selected_racks()
        else:self.status_var.set("No rack selected for duplication.")
    def rotate_selected_racks_action_ctx(self):
        if self.selected_rack_ids:self.rotate_selected_racks_action()
        else:self.status_var.set("No rack selected for rotation.")
    def delete_selected_item_ctx(self): self.delete_selected_item() 
    
    def open_tube_recolor_dialog(self):
        if len(self.selected_rack_ids)!=1:messagebox.showinfo("Select Rack","Please select exactly one rack to recolor its tubes.",parent=self.root);return
        selected_rack_id=self.selected_rack_ids[0]
        rack_to_recolor=next((r for r in self.racks_on_canvas if r['id']==selected_rack_id),None)
        if rack_to_recolor:
            self._record_state_for_undo() 
            current_rotation = rack_to_recolor.get('rotation_angle', 0)

            use_global_num_in_dialog = self.show_tube_numbers_var.get()
            start_num_for_dialog = 0
            if use_global_num_in_dialog and selected_rack_id in self.rack_global_start_indices:
                start_num_for_dialog = self.rack_global_start_indices[selected_rack_id]
            else: # If not using global or rack not found in map (shouldn't happen if map is up-to-date)
                use_global_num_in_dialog = False # Force local if data missing

            TubeRecolorDialog(self.root, rack_to_recolor, self, current_rotation, start_num_for_dialog, use_global_num_in_dialog)
        else:messagebox.showerror("Error","Could not find the selected rack data.",parent=self.root)

    def open_tube_type_dialog(self):
        if len(self.selected_rack_ids) != 1:
            messagebox.showinfo("Select Rack", "Please select exactly one rack to edit its tube types.", parent=self.root)
            return
        selected_rack_id = self.selected_rack_ids[0]
        rack_to_edit = next((r for r in self.racks_on_canvas if r['id'] == selected_rack_id), None)
        if rack_to_edit:
            self._record_state_for_undo() 
            current_rotation = rack_to_edit.get('rotation_angle', 0)
            TubeTypeDialog(self.root, rack_to_edit, self, current_rotation)
        else:
            messagebox.showerror("Error", "Could not find the selected rack data.", parent=self.root)

    def open_tube_type_dialog_ctx(self):
        if self.context_menu_rack_id and self.context_menu_rack_id in self.selected_rack_ids and len(self.selected_rack_ids) == 1:
            self.open_tube_type_dialog()
        else: self.status_var.set("Edit types requires a single rack selected via right-click.")

    def _generate_default_tube_data(self, num_tubes): 
        return [{'color': self.default_new_tube_color_value, 'angle': 0, 'lift_time': 0.0, 'type': "Standard", 'cue': ''} for _ in range(num_tubes)]

    def add_rack_to_list(self):
        self.status_var.set("") 
        try:
            rack_type=self.rack_type_var.get();x_tubes=int(self.x_tubes_var.get());y_tubes=int(self.y_tubes_var.get())
            pos_x_world = float(self.pos_x_var.get()) # UI vars are now world coords
            pos_y_world = float(self.pos_y_var.get())
            tube_diameter_world=int(self.tube_diameter_var.get()) # Diameter is in world units
            rotation=int(self.rotation_var.get()) 
            rack_name = self.rack_name_var.get().strip() or f"{rack_type} Rack {len(self.racks_on_canvas) + 1}"
            if not rack_type or x_tubes<=0 or y_tubes<=0 or tube_diameter_world<=2:
                self.status_var.set("Error: Invalid rack parameters.");return
            
            num_total_tubes=x_tubes*y_tubes
            initial_tubes_data = self._generate_default_tube_data(num_total_tubes) 
            rack_config={'id':str(uuid.uuid4()), 'name': rack_name, 'type':rack_type,'x_tubes':x_tubes,'y_tubes':y_tubes,
                         'pos_x':pos_x_world,'pos_y':pos_y_world,'tube_diameter':tube_diameter_world,'rotation_angle':rotation,
                         'tubes':initial_tubes_data} 
            
            self._record_state_for_undo(); self.racks_on_canvas.append(rack_config)
            self.selected_rack_ids=[rack_config['id']]; self.selected_flow_line_id = None 
            if self.connecting_tubes_mode or self.drawing_flow_line_mode: 
                self.toggle_connect_tubes_mode(force_off=True); self.toggle_draw_flow_line_mode() 
            self.redraw_canvas()
            _,_,_,rack_w_rotated_world,rack_h_rotated_world =self._get_rack_dimensions_and_points(rack_config)
            suggested_next_x_world = pos_x_world + rack_w_rotated_world + self.DEFAULT_RACK_SEPARATION_WORLD
            self.pos_x_var.set(str(int(suggested_next_x_world))) # Suggest next X in world coords
            self.rack_name_var.set("") 
            self._update_ui_for_selection_state();self._update_rack_list_panel()
            self.status_var.set(f"'{rack_name}' ({rack_type}) added. Selected.")
        except ValueError:self.status_var.set("Error: Ensure all numeric inputs are valid integers and fields are not empty.")
        except Exception as e:self.status_var.set(f"An unexpected error occurred: {e}")

    def load_rack_config_to_ui(self,rack_config):
        self.rack_name_var.set(rack_config.get('name', ''))
        self.rack_type_var.set(rack_config['type']);self.x_tubes_var.set(str(rack_config['x_tubes']))
        self.y_tubes_var.set(str(rack_config['y_tubes']));
        # Rack positions are stored in world coords, display them as such
        self.pos_x_var.set(str(int(rack_config['pos_x']))) 
        self.pos_y_var.set(str(int(rack_config['pos_y'])))
        self.tube_diameter_var.set(str(rack_config['tube_diameter'])) # Diameter is world unit
        self.rotation_var.set(rack_config.get('rotation_angle',0))
        self.physical_dims_var.set(self._calculate_physical_dimensions(rack_config)) 
        self.tube_color_breakdown_var.set(self._calculate_tube_color_breakdown(rack_config)) 

    def load_line_config_to_ui(self, line_data):
        self.flow_line_label_var.set(line_data.get('label', ''))
        len_world = math.hypot(line_data['x2'] - line_data['x1'], line_data['y2'] - line_data['y1'])
        # Assume line length is in same 'world units' as racks. If these are inches:
        len_feet = len_world / self.INCHES_PER_FOOT
        self.flow_line_length_var.set(f"{len_feet:.2f} {self.FUSE_ESTIMATE_UNIT}") # Show more precision for feet
        burn_time_sec = 0.0
        line_color_value = line_data.get('color')
        matching_fuse_color_value = None
        # Find if the line's current color (e.g., 'darkred') matches a FUSE_COLOR_MAP value (e.g., 'red')
        # to then find its burn rate key (e.g., 'red')
        for fuse_name, fuse_val in self.FUSE_COLORS_MAP.items():
            if line_color_value == fuse_val: # If line's color is 'red', it matches FUSE_COLORS_MAP['Red']
                 if fuse_val in self.FUSE_BURN_RATES_SPF: # Check if 'red' (value) is a key in burn rates
                    matching_fuse_color_value = fuse_val
                    break
            elif line_color_value in self.FUSE_BURN_RATES_SPF: # Check if line_color_value is already a direct key
                 matching_fuse_color_value = line_color_value
                 break
        
        if matching_fuse_color_value:
            burn_rate_spf = self.FUSE_BURN_RATES_SPF[matching_fuse_color_value]
            # length_feet is already calculated above
            burn_time_sec = len_feet * burn_rate_spf
        self.flow_line_burn_time_var.set(f"{burn_time_sec:.1f}s" if burn_time_sec > 0 else "N/A")


    def _clear_input_fields_for_multi_or_no_selection(self,for_multi=False, item_type="rack"):
        if item_type == "line":
            self.rack_name_var.set("Flow Line Selected") 
            self.pos_x_var.set("---"); self.pos_y_var.set("---") 
            self.physical_dims_var.set("N/A"); self.tube_color_breakdown_var.set("N/A") 
            self.rack_type_var.set("---"); self.x_tubes_var.set("---"); self.y_tubes_var.set("---")
            self.tube_diameter_var.set("---"); self.rotation_dropdown.set("---")
        elif for_multi: 
            self.rack_name_var.set("Multiple Selected")
            self.pos_x_var.set("---"); self.pos_y_var.set("---")
            self.physical_dims_var.set("Multiple"); self.tube_color_breakdown_var.set("Multiple") 
            self.rack_type_var.set("---"); self.x_tubes_var.set("---"); self.y_tubes_var.set("---")
            self.tube_diameter_var.set("---"); self.rotation_dropdown.set("---")
        else: 
            self.rack_name_var.set("")
            self.physical_dims_var.set("N/A"); self.tube_color_breakdown_var.set("N/A") 
            self.rack_type_var.set("Crate"); self.x_tubes_var.set("3"); self.y_tubes_var.set("2")
            # Pos X/Y for new racks are suggested based on last added rack, or default if canvas empty
            self.pos_x_var.set(str(self.DEFAULT_RACK_POS_X_WORLD)) # Reset to default world pos
            self.pos_y_var.set(str(self.DEFAULT_RACK_POS_Y_WORLD))
            self.tube_diameter_var.set(str(self.DEFAULT_TUBE_DIAMETER)); self.rotation_var.set(0)
        
        if item_type != "line":
            self.flow_line_label_var.set(""); self.flow_line_length_var.set("N/A"); self.flow_line_burn_time_var.set("N/A")


    def _reset_input_fields_to_defaults(self): 
        self.rack_name_var.set(""); self.rack_type_var.set("Crate");self.x_tubes_var.set("3");self.y_tubes_var.set("2")
        # Keep self.pos_x_var and self.pos_y_var as they are for next placement suggestion
        self.pos_x_var.set(str(self.DEFAULT_RACK_POS_X_WORLD)); self.pos_y_var.set(str(self.DEFAULT_RACK_POS_Y_WORLD))
        self.tube_diameter_var.set(str(self.DEFAULT_TUBE_DIAMETER)); self.rotation_var.set(0)
        self.physical_dims_var.set("N/A"); self.tube_color_breakdown_var.set("N/A") 
        self.flow_line_label_var.set(""); self.flow_line_length_var.set("N/A"); self.flow_line_burn_time_var.set("N/A")


    def _set_input_fields_state(self,item_type="none"): 
        all_rack_input_widgets = [
            self.rack_name_entry, self.rack_type_dropdown, self.x_tubes_entry, self.y_tubes_entry,
            self.tube_diameter_entry, self.rotation_dropdown, self.pos_x_entry, self.pos_y_entry
        ]
        all_line_input_widgets = [self.flow_line_label_entry]
        # Disable all input fields first
        for widget in all_rack_input_widgets + all_line_input_widgets:
            if isinstance(widget, ttk.Combobox): widget.config(state=tk.DISABLED)
            else: widget.config(state=tk.DISABLED)
        
        if item_type == "rack": 
            for widget in all_rack_input_widgets:
                if isinstance(widget, ttk.Combobox): widget.config(state="readonly")
                else: widget.config(state=tk.NORMAL)
        elif item_type == "line": 
            self.flow_line_label_entry.config(state=tk.NORMAL)
        elif item_type == "none": # Preparing to add new rack
            for widget in all_rack_input_widgets:
                 if isinstance(widget, ttk.Combobox): widget.config(state="readonly")
                 else: widget.config(state=tk.NORMAL)
        # For "multi_rack", all relevant (rack) fields remain disabled.


    def _update_ui_for_selection_state(self):
        num_selected_racks =len(self.selected_rack_ids)
        if self.selected_flow_line_id: 
            self.rack_props_frame.grid_remove(); self.line_props_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N), pady=5, padx=5) 
            line_to_load = next((ln for ln in self.flow_lines_on_canvas if ln['id'] == self.selected_flow_line_id), None)
            if line_to_load: self.load_line_config_to_ui(line_to_load)
            else: self._clear_input_fields_for_multi_or_no_selection(item_type="line") # Clear if line not found
            self._set_input_fields_state(item_type="line")
            self.status_var.set(f"Flow line ...{self.selected_flow_line_id[-6:]} selected.")
            if hasattr(self,'recolor_tubes_btn'):self.recolor_tubes_btn.config(state=tk.DISABLED)
            if hasattr(self, 'edit_types_btn'): self.edit_types_btn.config(state=tk.DISABLED)
        elif num_selected_racks==1: 
            self.line_props_frame.grid_remove(); self.rack_props_frame.grid() 
            rack_to_load=next((r for r in self.racks_on_canvas if r['id']==self.selected_rack_ids[0]),None)
            if rack_to_load:self.load_rack_config_to_ui(rack_to_load) 
            self._set_input_fields_state(item_type="rack") 
            self.status_var.set(f"Selected: '{rack_to_load.get('name', 'Unnamed')}' (ID: ...{self.selected_rack_ids[0][-6:]}).")
            if hasattr(self,'recolor_tubes_btn'):self.recolor_tubes_btn.config(state=tk.NORMAL)
            if hasattr(self, 'edit_types_btn'): self.edit_types_btn.config(state=tk.NORMAL)
        elif num_selected_racks > 1: 
            self.line_props_frame.grid_remove(); self.rack_props_frame.grid()
            self._clear_input_fields_for_multi_or_no_selection(for_multi=True, item_type="rack")
            self._set_input_fields_state(item_type="multi_rack") 
            self.status_var.set(f"{num_selected_racks} racks selected. Batch actions apply.")
            if hasattr(self,'recolor_tubes_btn'):self.recolor_tubes_btn.config(state=tk.DISABLED)
            if hasattr(self, 'edit_types_btn'): self.edit_types_btn.config(state=tk.DISABLED)
        else: 
            self.line_props_frame.grid_remove(); self.rack_props_frame.grid()
            self._reset_input_fields_to_defaults() 
            self._set_input_fields_state(item_type="none") 
            self.status_var.set("Canvas active. No item selected.")
            if hasattr(self,'recolor_tubes_btn'):self.recolor_tubes_btn.config(state=tk.DISABLED)
            if hasattr(self, 'edit_types_btn'): self.edit_types_btn.config(state=tk.DISABLED)
        self._update_rack_list_panel_selection() 

    def _update_rack_list_panel_selection(self):
        current_selection = self.rack_inspector_tree.selection()
        ids_to_deselect = set(current_selection) - set(self.selected_rack_ids)
        ids_to_select = set(self.selected_rack_ids) - set(current_selection)

        if ids_to_deselect: self.rack_inspector_tree.selection_remove(*list(ids_to_deselect))
        if self.selected_rack_ids: 
            self.rack_inspector_tree.selection_add(*self.selected_rack_ids)
            if self.selected_rack_ids: self.rack_inspector_tree.see(self.selected_rack_ids[-1]) # Scroll to last selected

    def clear_all_racks(self):
        if messagebox.askyesno("Confirm Clear","Are you sure you want to clear all racks from the canvas?\nThis action cannot be undone via the Undo button for individual racks.",icon='warning'):
            self._record_state_for_undo(); deleted_rack_ids = {r['id'] for r in self.racks_on_canvas} 
            self.racks_on_canvas=[];self.selected_rack_ids=[];self.dragging_rack_id=None
            self.tube_connections = [c for c in self.tube_connections if c['source_rack_id'] not in deleted_rack_ids and c['target_rack_id'] not in deleted_rack_ids]
            self.redraw_canvas()
            self.pos_x_var.set(str(self.DEFAULT_RACK_POS_X_WORLD)) # Reset to default world pos
            self.pos_y_var.set(str(self.DEFAULT_RACK_POS_Y_WORLD))
            self._update_ui_for_selection_state();self._update_rack_list_panel()
            self.status_var.set("All racks cleared from canvas.")

    def on_canvas_press(self,event):
        if self.drawing_flow_line_mode or self.connecting_tubes_mode: return 
        
        world_event_x, world_event_y = self.canvas_to_world(event.x, event.y)
        clicked_line_id = self._get_line_under_mouse(world_event_x, world_event_y)
        is_ctrl_click=(event.state&0x0004)!=0; is_shift_click=(event.state&0x0001)!=0 
        clicked_on_rack_config = None 

        if clicked_line_id: 
            if not is_ctrl_click: self.selected_flow_line_id = clicked_line_id
            self.selected_rack_ids.clear(); self.dragging_rack_id = None; self.drag_operation_pending_undo_state = None 
        else: 
            for rack_config_iter in reversed(self.racks_on_canvas): 
                _,outline_points_world,_,_,_=self._get_rack_dimensions_and_points(rack_config_iter) # Outline is in world
                if self._is_point_in_polygon(world_event_x, world_event_y, outline_points_world): 
                    clicked_on_rack_config=rack_config_iter; break
            if clicked_on_rack_config: 
                self.selected_flow_line_id = None; self.drag_operation_pending_undo_state = self._capture_current_state() 
                self.dragging_rack_id=clicked_on_rack_config['id'] 
                # Drag offset is difference between mouse world pos and rack world pos
                self.drag_offset_x=world_event_x-float(clicked_on_rack_config['pos_x']); 
                self.drag_offset_y=world_event_y-float(clicked_on_rack_config['pos_y'])
                
                is_multi_drag_candidate = clicked_on_rack_config['id'] in self.selected_rack_ids and len(self.selected_rack_ids) > 1
                if is_multi_drag_candidate: 
                    self.drag_start_positions.clear()
                    for r_id in self.selected_rack_ids:
                        r_sel = next((r for r in self.racks_on_canvas if r['id'] == r_id), None)
                        if r_sel: self.drag_start_positions[r_id] = (float(r_sel['pos_x']), float(r_sel['pos_y']))
                else: 
                     self.drag_start_positions.clear()
                     if self.dragging_rack_id: self.drag_start_positions[self.dragging_rack_id] = (float(clicked_on_rack_config['pos_x']), float(clicked_on_rack_config['pos_y']))
                if is_ctrl_click and not is_shift_click: 
                    if clicked_on_rack_config['id'] in self.selected_rack_ids: self.selected_rack_ids.remove(clicked_on_rack_config['id'])
                    else: self.selected_rack_ids.append(clicked_on_rack_config['id'])
                elif not is_shift_click and (clicked_on_rack_config['id'] not in self.selected_rack_ids or len(self.selected_rack_ids) > 1):
                    self.selected_rack_ids=[clicked_on_rack_config['id']]
                if self.selected_rack_ids and clicked_on_rack_config and clicked_on_rack_config['id'] in self.selected_rack_ids: 
                    selected_racks_to_move = [r for r in self.racks_on_canvas if r['id'] in self.selected_rack_ids]
                    self.racks_on_canvas = [r for r in self.racks_on_canvas if r['id'] not in self.selected_rack_ids]
                    selected_racks_to_move.remove(clicked_on_rack_config); selected_racks_to_move.append(clicked_on_rack_config)
                    self.racks_on_canvas.extend(selected_racks_to_move)
            elif not is_shift_click: 
                if not is_ctrl_click: self.selected_rack_ids.clear(); self.selected_flow_line_id = None 
                self.dragging_rack_id=None; self.drag_operation_pending_undo_state = None; self.drag_start_positions.clear()
        if not is_shift_click or clicked_line_id : self._update_ui_for_selection_state()
        self.redraw_canvas()

    def on_canvas_drag(self,event):
        if self.selected_flow_line_id or self.drawing_flow_line_mode or self.connecting_tubes_mode or self._is_panning: return
        if not self.dragging_rack_id: return 
        primary_rack_dragged = next((r for r in self.racks_on_canvas if r['id'] == self.dragging_rack_id), None)
        if not primary_rack_dragged: return 
        
        world_event_x, world_event_y = self.canvas_to_world(event.x, event.y)
        proposed_primary_x_world = world_event_x - self.drag_offset_x; 
        proposed_primary_y_world = world_event_y - self.drag_offset_y
        
        orig_primary_start_x_w, orig_primary_start_y_w = self.drag_start_positions.get(self.dragging_rack_id, (proposed_primary_x_world, proposed_primary_y_world))
        
        snapped_x_world = proposed_primary_x_world; snapped_y_world = proposed_primary_y_world
        if self.snap_to_grid_enabled.get():
            try:
                grid_s_world = int(self.grid_size_var.get()) # Grid size is world units
                if grid_s_world > 0:
                    snapped_x_world = round(proposed_primary_x_world / grid_s_world) * grid_s_world
                    snapped_y_world = round(proposed_primary_y_world / grid_s_world) * grid_s_world
            except ValueError: pass 
        if self.snap_to_racks_enabled.get(): 
             snapped_x_world, snapped_y_world = self._snap_rack(primary_rack_dragged, snapped_x_world, snapped_y_world, self.dragging_rack_id if len(self.selected_rack_ids) > 1 else None)
        
        delta_x_world = snapped_x_world - orig_primary_start_x_w; 
        delta_y_world = snapped_y_world - orig_primary_start_y_w
        
        if self.drag_start_positions and len(self.selected_rack_ids) > 0 : 
            for r_id in self.selected_rack_ids: 
                rack_to_move = next((r for r in self.racks_on_canvas if r['id'] == r_id), None)
                if rack_to_move and r_id in self.drag_start_positions: 
                    original_pos_w = self.drag_start_positions[r_id]
                    rack_to_move['pos_x'] = original_pos_w[0] + delta_x_world; 
                    rack_to_move['pos_y'] = original_pos_w[1] + delta_y_world
        
        if len(self.selected_rack_ids)==1 and self.selected_rack_ids[0]==self.dragging_rack_id:
            moved_rack_config = next((r for r in self.racks_on_canvas if r['id'] == self.dragging_rack_id), None)
            if moved_rack_config: # Positions are world, display as world
                self.pos_x_var.set(str(int(moved_rack_config['pos_x']))); 
                self.pos_y_var.set(str(int(moved_rack_config['pos_y'])))
        self.redraw_canvas()

    def _snap_rack(self,dragged_rack_config,current_x_world,current_y_world, primary_drag_id_for_group=None):
        snapped_x_w,snapped_y_w = current_x_world,current_y_world
        temp_dragged_config = dragged_rack_config.copy()
        temp_dragged_config['pos_x']=current_x_world;temp_dragged_config['pos_y']=current_y_world
        _,dragged_outline_world,_,_,_=self._get_rack_dimensions_and_points(temp_dragged_config)
        if not dragged_outline_world:return current_x_world,current_y_world 
        
        drag_min_xw=min(p[0] for p in dragged_outline_world);drag_max_xw=max(p[0] for p in dragged_outline_world)
        drag_min_yw=min(p[1] for p in dragged_outline_world);drag_max_yw=max(p[1] for p in dragged_outline_world)
        
        ids_in_drag_group = set(self.selected_rack_ids) if primary_drag_id_for_group and len(self.selected_rack_ids) > 1 else {dragged_rack_config['id']}
        world_snap_threshold = self.SNAP_THRESHOLD / self.zoom_level # Convert canvas snap threshold to world

        for other_rack in self.racks_on_canvas:
            if other_rack['id'] in ids_in_drag_group:continue 
            _,other_outline_world,_,_,_=self._get_rack_dimensions_and_points(other_rack)
            if not other_outline_world:continue
            other_min_xw=min(p[0] for p in other_outline_world);other_max_xw=max(p[0] for p in other_outline_world)
            other_min_yw=min(p[1] for p in other_outline_world);other_max_yw=max(p[1] for p in other_outline_world)
            
            potential_snapped_xw = snapped_x_w 
            if abs(drag_min_xw - other_max_xw) < world_snap_threshold: potential_snapped_xw = current_x_world + (other_max_xw - drag_min_xw)
            elif abs(drag_max_xw - other_min_xw) < world_snap_threshold: potential_snapped_xw = current_x_world + (other_min_xw - drag_max_xw)
            elif abs(drag_min_xw - other_min_xw) < world_snap_threshold: potential_snapped_xw = current_x_world + (other_min_xw - drag_min_xw)
            elif abs(drag_max_xw - other_max_xw) < world_snap_threshold: potential_snapped_xw = current_x_world + (other_max_xw - drag_max_xw)
            
            potential_snapped_yw = snapped_y_w 
            if abs(drag_min_yw - other_max_yw) < world_snap_threshold: potential_snapped_yw = current_y_world + (other_max_yw - drag_min_yw)
            elif abs(drag_max_yw - other_min_yw) < world_snap_threshold: potential_snapped_yw = current_y_world + (other_min_yw - drag_max_yw)
            elif abs(drag_min_yw - other_min_yw) < world_snap_threshold: potential_snapped_yw = current_y_world + (other_min_yw - drag_min_yw)
            elif abs(drag_max_yw - other_max_yw) < world_snap_threshold: potential_snapped_yw = current_y_world + (other_max_yw - drag_max_yw)

            if potential_snapped_xw != snapped_x_w : snapped_x_w = potential_snapped_xw
            if potential_snapped_yw != snapped_y_w : snapped_y_w = potential_snapped_yw
        return snapped_x_w,snapped_y_w

    def on_canvas_release(self,event):
        if self.selected_flow_line_id or self.drawing_flow_line_mode or self.connecting_tubes_mode or self._is_panning: return
        if self.dragging_rack_id: 
            drag_ended_state_different = False
            if self.drag_operation_pending_undo_state and self.drag_start_positions:
                for rack_id in self.selected_rack_ids: 
                    current_rack_config = next((r for r in self.racks_on_canvas if r['id'] == rack_id), None)
                    if current_rack_config and rack_id in self.drag_start_positions:
                        start_x_w, start_y_w = self.drag_start_positions[rack_id]
                        if float(current_rack_config['pos_x']) != start_x_w or float(current_rack_config['pos_y']) != start_y_w:
                            drag_ended_state_different = True; break 
            if drag_ended_state_different and self.drag_operation_pending_undo_state:
                self._push_to_undo_stack(self.drag_operation_pending_undo_state) 
            self._update_ui_for_selection_state(); self._update_rack_list_panel() 
            self.status_var.set(f"Drag ended for selected rack(s).")
        self.dragging_rack_id=None; self.drag_start_positions.clear(); self.drag_operation_pending_undo_state = None

    def on_canvas_shift_click(self,event): 
        if self.drawing_flow_line_mode or self.connecting_tubes_mode: return 
        if len(self.selected_rack_ids)!=1:self.status_var.set("Shift+Click recolor: Select a single rack first.");return
        selected_rack_id=self.selected_rack_ids[0]
        selected_rack_config=next((r for r in self.racks_on_canvas if r['id']==selected_rack_id),None)
        if not selected_rack_config:return 
        
        # Need to check against world coordinates of tubes
        world_event_x, world_event_y = self.canvas_to_world(event.x, event.y)
        tube_points_world,_,_,_,_=self._get_rack_dimensions_and_points(selected_rack_config) # tube_points are (idx, world_cx, world_cy, world_dia)

        for i,tube_center_x_w,tube_center_y_w,tube_dia_w in tube_points_world: 
            if (world_event_x-tube_center_x_w)**2+(world_event_y-tube_center_y_w)**2<=(tube_dia_w/2)**2:
                if i<len(selected_rack_config['tubes']): 
                    current_color_value = selected_rack_config['tubes'][i]['color']
                    current_color_name=next((name for name,val in self.FUSE_COLORS_MAP.items() if val==current_color_value), self.FUSE_COLOR_CHOICES[0])
                    current_choice_idx = self.FUSE_COLOR_CHOICES.index(current_color_name)
                    new_color_name=self.FUSE_COLOR_CHOICES[(current_choice_idx+1)%len(self.FUSE_COLOR_CHOICES)] 
                    selected_rack_config['tubes'][i]['color']=self.FUSE_COLORS_MAP[new_color_name]
                    self._record_state_for_undo(); self.redraw_canvas(); 
                    self.status_var.set(f"Tube {i+1} on '{selected_rack_config.get('name', 'Unnamed')}' changed to {new_color_name}.")
                    self._update_ui_for_selection_state(); return 
        self.status_var.set("Shift+Click on a tube of the selected rack to cycle its color.")

    def delete_selected_item(self,event=None): 
        if self.selected_flow_line_id: 
            line_to_delete = next((line for line in self.flow_lines_on_canvas if line['id'] == self.selected_flow_line_id), None)
            if line_to_delete and messagebox.askyesno("Confirm Delete", "Are you sure you want to delete the selected flow line?", icon='warning', parent=self.root):
                self._record_state_for_undo(); self.flow_lines_on_canvas.remove(line_to_delete)
                self.selected_flow_line_id = None; self.redraw_canvas()
                self.status_var.set("Flow line deleted."); self._update_ui_for_selection_state() 
            elif not line_to_delete:
                self.selected_flow_line_id = None; self.status_var.set("Selected flow line not found."); 
                self._update_ui_for_selection_state(); self.redraw_canvas()
        elif self.selected_rack_ids: 
            num_to_delete = len(self.selected_rack_ids)
            name_preview = f" '{next((r for r in self.racks_on_canvas if r['id'] == self.selected_rack_ids[0]), {}).get('name', 'Unnamed Rack')}'" if num_to_delete == 1 else " selected racks"
            confirm_msg=f"Are you sure you want to delete {num_to_delete} rack(s){name_preview}?\nThis will also remove associated tube connections."
            if messagebox.askyesno("Confirm Delete",confirm_msg,icon='warning', parent=self.root):
                self._record_state_for_undo(); deleted_rack_ids_set = set(self.selected_rack_ids) 
                self.racks_on_canvas=[r for r in self.racks_on_canvas if r['id'] not in self.selected_rack_ids]
                if self.dragging_rack_id in self.selected_rack_ids:self.dragging_rack_id=None
                self.selected_rack_ids.clear() 
                self.tube_connections = [c for c in self.tube_connections if c['source_rack_id'] not in deleted_rack_ids_set and c['target_rack_id'] not in deleted_rack_ids_set]
                self.redraw_canvas(); self._update_ui_for_selection_state(); self._update_rack_list_panel()
                self.status_var.set(f"Deleted {num_to_delete} rack(s).")
            else:self.status_var.set("Deletion cancelled.")
        else: self.status_var.set("No item selected to delete.")

    def rotate_selected_racks_action(self): 
        if self.selected_flow_line_id: self.status_var.set("Rotation not applicable to flow lines."); return
        if not self.selected_rack_ids:self.status_var.set("No rack selected to rotate.");return
        rotated_count=0; self._record_state_for_undo() 
        for rack_id in self.selected_rack_ids:
            rack_config=next((r for r in self.racks_on_canvas if r['id']==rack_id),None)
            if rack_config:
                current_angle=rack_config.get('rotation_angle',0)
                try: current_angle_idx = self.ROTATION_DEGREES.index(current_angle); rack_config['rotation_angle']=self.ROTATION_DEGREES[(current_angle_idx+1)%len(self.ROTATION_DEGREES)]
                except ValueError: rack_config['rotation_angle']=self.ROTATION_DEGREES[0]
                rotated_count+=1
        if rotated_count>0: self.redraw_canvas(); self.status_var.set(f"{rotated_count} selected rack(s) rotated.")
        if len(self.selected_rack_ids)==1:
            rack_config=next((r for r in self.racks_on_canvas if r['id']==self.selected_rack_ids[0]),None)
            if rack_config:self.rotation_var.set(rack_config['rotation_angle'])
        elif len(self.selected_rack_ids)>1: self.rotation_dropdown.set("---")

    def duplicate_selected_racks(self):
        if self.selected_flow_line_id: self.status_var.set("Duplication not applicable to flow lines."); return
        if not self.selected_rack_ids:self.status_var.set("No racks selected to duplicate.");return
        newly_created_racks_configs=[];newly_selected_ids=[]; self._record_state_for_undo() 
        for i,rack_id_to_duplicate in enumerate(self.selected_rack_ids):
            original_rack=next((r for r in self.racks_on_canvas if r['id']==rack_id_to_duplicate),None)
            if original_rack:
                new_rack_config=copy.deepcopy(original_rack) 
                new_rack_config['id']=str(uuid.uuid4()) 
                new_rack_config['name'] = original_rack.get('name', 'Unnamed') + " (Copy)" 
                new_rack_config['pos_x']=float(original_rack['pos_x'])+ (self.DUPLICATE_OFFSET_X / self.zoom_level) + (i * self.DUPLICATE_OFFSET_INCREMENT / self.zoom_level)
                new_rack_config['pos_y']=float(original_rack['pos_y'])+ (self.DUPLICATE_OFFSET_Y / self.zoom_level) + (i * self.DUPLICATE_OFFSET_INCREMENT / self.zoom_level)
                newly_created_racks_configs.append(new_rack_config);newly_selected_ids.append(new_rack_config['id'])
        if newly_created_racks_configs:
            self.racks_on_canvas.extend(newly_created_racks_configs); self.selected_rack_ids=newly_selected_ids 
            self.selected_flow_line_id = None; self.redraw_canvas()
            self._update_ui_for_selection_state();self._update_rack_list_panel()
            self.status_var.set(f"{len(newly_created_racks_configs)} rack(s) duplicated and selected.")
        else:self.status_var.set("Error: Could not duplicate selected racks (original not found?).")

    def _capture_current_state(self):
        return {'racks': copy.deepcopy(self.racks_on_canvas), 'flow_lines': copy.deepcopy(self.flow_lines_on_canvas),
                'tube_connections': copy.deepcopy(self.tube_connections), 'selected_rack_ids': copy.deepcopy(self.selected_rack_ids),
                'selected_flow_line_id': self.selected_flow_line_id,
                'canvas_view': {'zoom': self.zoom_level, 'pan_x': self.pan_offset_x, 'pan_y': self.pan_offset_y}} # Save view state

    def _restore_state_from_history(self, history_entry):
        self.racks_on_canvas = history_entry['racks']; self.flow_lines_on_canvas = history_entry['flow_lines']
        self.tube_connections = history_entry['tube_connections']; self.selected_rack_ids = history_entry['selected_rack_ids']
        self.selected_flow_line_id = history_entry['selected_flow_line_id']
        
        canvas_view_state = history_entry.get('canvas_view', {'zoom': 1.0, 'pan_x': 0.0, 'pan_y': 0.0})
        self.zoom_level = canvas_view_state.get('zoom', 1.0)
        self.pan_offset_x = canvas_view_state.get('pan_x', 0.0)
        self.pan_offset_y = canvas_view_state.get('pan_y', 0.0)

        self.dragging_rack_id = None; self.drag_start_positions.clear(); self.drag_operation_pending_undo_state = None
        self.flow_line_start_point = None; self.first_tube_for_connection = None 
        self.redraw_canvas(); self._update_rack_list_panel(); self._update_ui_for_selection_state() 
        self._update_canvas_summary_info(); self._update_undo_redo_buttons_state() 

    def _push_to_undo_stack(self, state_to_push):
        self.undo_stack.append(state_to_push)
        if len(self.undo_stack) > self.MAX_UNDO_STEPS: self.undo_stack.pop(0) 
        self.redo_stack.clear(); self._update_undo_redo_buttons_state()

    def _record_state_for_undo(self): self._push_to_undo_stack(self._capture_current_state())

    def undo_action(self):
        if not self.undo_stack: self.status_var.set("Nothing to undo."); return
        self.redo_stack.append(self._capture_current_state())
        self._restore_state_from_history(self.undo_stack.pop()); self.status_var.set("Undo successful.")

    def redo_action(self):
        if not self.redo_stack: self.status_var.set("Nothing to redo."); return
        self.undo_stack.append(self._capture_current_state()) 
        self._restore_state_from_history(self.redo_stack.pop()); self.status_var.set("Redo successful.")

    def _update_undo_redo_buttons_state(self):
        self.undo_btn.config(state=tk.NORMAL if self.undo_stack else tk.DISABLED)
        self.redo_btn.config(state=tk.NORMAL if self.redo_stack else tk.DISABLED)

    def _draw_rack_name(self, rack_config):
        name = rack_config.get('name')
        if not name or not self.show_rack_names_var.get(): return
        _, _, (un_w, un_h), _, _ = self._get_rack_dimensions_and_points(rack_config) # Dims are world units
        bx_w, by_w = float(rack_config['pos_x']), float(rack_config['pos_y']); angle = rack_config.get('rotation_angle',0)
        nlx_w, nly_w = un_w / 2, un_h + (8 / self.zoom_level) # Offset in world units, scale by zoom
        clx_w, cly_w = un_w / 2, un_h / 2 
        rnlx_w, rnly_w = self._rotate_point(nlx_w, nly_w, angle, clx_w, cly_w)
        wnx_w, wny_w = bx_w - clx_w + rnlx_w, by_w - cly_w + rnly_w
        
        cx, cy = self.world_to_canvas(wnx_w, wny_w)
        font_size = max(6, int(8 * self.zoom_level)) # Scale font size
        self.canvas.create_text(cx, cy, text=name, fill="black", font=("Arial", font_size, "italic"), anchor=tk.N, tags=f"name_{rack_config['id']}")

    def _rotate_point(self,x,y,angle_deg,cx,cy):
        """Rotates a point (x,y) around a center (cx,cy) by angle_deg degrees."""
        angle_rad=math.radians(angle_deg);s,c=math.sin(angle_rad),math.cos(angle_rad)
        x-=cx;y-=cy; return x*c-y*s+cx,x*s+y*c+cy

    def _get_rack_dimensions_and_points(self,rack_config): # All calculations in World Coordinates
        """
        Calculates dimensions and tube center points for a given rack configuration.
        All calculations and returned coordinates/dimensions are in WORLD units.

        Returns:
            tuple: (
                tube_center_points_info_world (list of (idx, cx, cy, dia)),
                rotated_outline_points_absolute_world (list of (x,y) tuples for outline),
                (unrotated_rack_width_world, unrotated_rack_height_world),
                rotated_bbox_width_world,
                rotated_bbox_height_world
            )
        """
        cols_or_fans = rack_config['x_tubes']
        rows_or_tubes_per_fan = rack_config['y_tubes']
        tube_diameter_world = rack_config['tube_diameter'] # This is a world unit
        rack_type = rack_config['type']
        base_x_world, base_y_world = float(rack_config['pos_x']), float(rack_config['pos_y'])
        angle_deg = rack_config.get('rotation_angle', 0)

        tube_group_width_world, tube_group_height_world = 0, 0

        if rack_type == "Crate":
            spacing_world = self.DEFAULT_TUBE_SPACING_RATIO * tube_diameter_world
            tube_group_width_world = cols_or_fans * tube_diameter_world + max(0, cols_or_fans - 1) * spacing_world
            tube_group_height_world = rows_or_tubes_per_fan * tube_diameter_world + max(0, rows_or_tubes_per_fan - 1) * spacing_world
        elif rack_type == "Fan":
            fan_visual_padding_world = self.DEFAULT_FAN_PADDING_RATIO * tube_diameter_world
            fan_rect_width_per_segment_world = tube_diameter_world + 2 * fan_visual_padding_world
            spacing_x_between_fans_world = self.DEFAULT_INTER_FAN_SPACING_RATIO * tube_diameter_world
            tube_group_width_world = cols_or_fans * fan_rect_width_per_segment_world + max(0, cols_or_fans - 1) * spacing_x_between_fans_world
            
            spacing_y_in_fan_world = self.DEFAULT_TUBE_SPACING_RATIO * tube_diameter_world
            height_of_one_fan_tubes_world = rows_or_tubes_per_fan * tube_diameter_world + max(0, rows_or_tubes_per_fan - 1) * spacing_y_in_fan_world
            tube_group_height_world = height_of_one_fan_tubes_world + 2 * fan_visual_padding_world

        # Overall unrotated rack dimensions including outer padding
        unrotated_rack_width_world = tube_group_width_world + 2 * self.RACK_OUTER_PADDING
        unrotated_rack_height_world = tube_group_height_world + 2 * self.RACK_OUTER_PADDING

        # Local center for rotation
        center_local_x_world, center_local_y_world = unrotated_rack_width_world / 2, unrotated_rack_height_world / 2

        # Unrotated corner points relative to (0,0) of the unrotated rack
        corners_unrotated_local_world = [
            (0, 0), (unrotated_rack_width_world, 0),
            (unrotated_rack_width_world, unrotated_rack_height_world), (0, unrotated_rack_height_world)
        ]
        # Rotated corner points, still local (relative to unrotated rack's top-left)
        rotated_outline_points_local_world = [
            self._rotate_point(crx, cry, angle_deg, center_local_x_world, center_local_y_world)
            for crx, cry in corners_unrotated_local_world
        ]
        # Absolute world coordinates of rotated outline points
        rotated_outline_points_absolute_world = [
            (base_x_world - center_local_x_world + prx, base_y_world - center_local_y_world + pry)
            for prx, pry in rotated_outline_points_local_world
        ]

        # Bounding box of the rotated rack
        if rotated_outline_points_absolute_world:
            min_x_world = min(p[0] for p in rotated_outline_points_absolute_world)
            max_x_world = max(p[0] for p in rotated_outline_points_absolute_world)
            min_y_world = min(p[1] for p in rotated_outline_points_absolute_world)
            max_y_world = max(p[1] for p in rotated_outline_points_absolute_world)
        else: # Should not happen if rack has dimensions
            min_x_world, max_x_world = base_x_world, base_x_world + unrotated_rack_width_world
            min_y_world, max_y_world = base_y_world, base_y_world + unrotated_rack_height_world
            
        rotated_bbox_width_world = max_x_world - min_x_world
        rotated_bbox_height_world = max_y_world - min_y_world

        # Calculate tube center points
        tube_center_points_info_world = []
        effective_tube_diameter_world = max(tube_diameter_world, 10) # Ensure a minimum size for calculations
        tube_idx_counter = 0

        if rack_type == "Crate":
            spacing_world = self.DEFAULT_TUBE_SPACING_RATIO * tube_diameter_world
            for r_idx in range(rows_or_tubes_per_fan):
                for c_idx in range(cols_or_fans):
                    local_center_x_world = self.RACK_OUTER_PADDING + c_idx * (tube_diameter_world + spacing_world) + tube_diameter_world / 2
                    local_center_y_world = self.RACK_OUTER_PADDING + r_idx * (tube_diameter_world + spacing_world) + tube_diameter_world / 2
                    
                    rotated_x_world, rotated_y_world = self._rotate_point(local_center_x_world, local_center_y_world, angle_deg, center_local_x_world, center_local_y_world)
                    abs_tube_cx_world = base_x_world - center_local_x_world + rotated_x_world
                    abs_tube_cy_world = base_y_world - center_local_y_world + rotated_y_world
                    tube_center_points_info_world.append((tube_idx_counter, abs_tube_cx_world, abs_tube_cy_world, effective_tube_diameter_world))
                    tube_idx_counter += 1
        elif rack_type == "Fan":
            spacing_y_in_fan_world = self.DEFAULT_TUBE_SPACING_RATIO * tube_diameter_world
            fan_visual_padding_world = self.DEFAULT_FAN_PADDING_RATIO * tube_diameter_world
            fan_rect_width_per_segment_world = tube_diameter_world + 2 * fan_visual_padding_world
            spacing_x_between_fans_world = self.DEFAULT_INTER_FAN_SPACING_RATIO * tube_diameter_world
            
            for f_idx in range(cols_or_fans):
                fan_segment_content_start_x_local_world = self.RACK_OUTER_PADDING + f_idx * (fan_rect_width_per_segment_world + spacing_x_between_fans_world)
                fan_segment_content_start_y_local_world = self.RACK_OUTER_PADDING
                
                tube_center_x_in_segment_local_world = fan_segment_content_start_x_local_world + fan_visual_padding_world + tube_diameter_world / 2
                for t_idx in range(rows_or_tubes_per_fan):
                    tube_center_y_in_segment_local_world = fan_segment_content_start_y_local_world + fan_visual_padding_world + t_idx * (tube_diameter_world + spacing_y_in_fan_world) + tube_diameter_world / 2
                    
                    rotated_x_world, rotated_y_world = self._rotate_point(tube_center_x_in_segment_local_world, tube_center_y_in_segment_local_world, angle_deg, center_local_x_world, center_local_y_world)
                    abs_tube_cx_world = base_x_world - center_local_x_world + rotated_x_world
                    abs_tube_cy_world = base_y_world - center_local_y_world + rotated_y_world
                    tube_center_points_info_world.append((tube_idx_counter, abs_tube_cx_world, abs_tube_cy_world, effective_tube_diameter_world))
                    tube_idx_counter += 1

        return (tube_center_points_info_world, rotated_outline_points_absolute_world,
                (unrotated_rack_width_world, unrotated_rack_height_world),
                rotated_bbox_width_world, rotated_bbox_height_world)

    def _is_point_in_polygon(self,x_w,y_w,poly_v_w): # Expects world coordinates
        nv=len(poly_v_w); ins=False; p1x_w,p1y_w=poly_v_w[0]
        if nv<3:return False 
        for i in range(nv+1): 
            p2x_w,p2y_w=poly_v_w[i%nv] 
            if y_w>min(p1y_w,p2y_w) and y_w<=max(p1y_w,p2y_w) and x_w<=max(p1x_w,p2x_w):
                if p1y_w!=p2y_w: xi_w=(y_w-p1y_w)*(p2x_w-p1x_w)/(p2y_w-p1y_w)+p1x_w 
                if p1x_w==p2x_w or x_w<=xi_w: ins=not ins 
            p1x_w,p1y_w=p2x_w,p2y_w 
        return ins

    def _draw_rack_outline(self,rack_config,rotated_outline_points_world):
        oc=self.RACK_OUTLINE_COLOR;ow_world=self.RACK_OUTLINE_WIDTH
        if rack_config['id'] in self.selected_rack_ids: oc=self.SELECTED_RACK_OUTLINE_COLOR;ow_world=self.SELECTED_RACK_OUTLINE_WIDTH
        
        ow_canvas = max(1, ow_world * self.zoom_level) # Scale outline width
        if rotated_outline_points_world:
            # Convert world outline points to canvas points
            canvas_outline_points = [self.world_to_canvas(px_w, py_w) for px_w, py_w in rotated_outline_points_world]
            flat_points_canvas=[c for p in canvas_outline_points for c in p]; 
            self.canvas.create_polygon(flat_points_canvas,outline=oc,width=ow_canvas,fill='') 

    def _draw_tube_shape(self, cx_w, cy_w, diameter_w, angle_deg, fill_color,
                           outline_color="black", outline_width_world=1, shape_type="oval"):
        """
        Draws a specified shape (oval or rectangle) for a tube, rotated as needed.
        All input dimensions (cx_w, cy_w, diameter_w) are in world coordinates.
        """
        cx_c, cy_c = self.world_to_canvas(cx_w, cy_w)
        diameter_c = diameter_w * self.zoom_level
        outline_width_c = max(1, outline_width_world * self.zoom_level)

        if shape_type == "oval":
            rx_c, ry_c = diameter_c / 2, diameter_c / 2
            if angle_deg % 180 == 0: # Optimization for non-rotated or 180-deg rotated ovals
                self.canvas.create_oval(cx_c - rx_c, cy_c - ry_c, cx_c + rx_c, cy_c + ry_c,
                                        fill=fill_color, outline=outline_color, width=outline_width_c)
            else: # Draw as a polygon for other rotations
                ns = 20; pts_c = []
                for i in range(ns):
                    th = (i / ns) * 2 * math.pi
                    x0_c = rx_c * math.cos(th)
                    y0_c = ry_c * math.sin(th)
                    xr_c, yr_c = self._rotate_point(x0_c, y0_c, angle_deg, 0, 0)
                    pts_c.extend([xr_c + cx_c, yr_c + cy_c])
                self.canvas.create_polygon(pts_c, fill=fill_color, outline=outline_color,
                                           width=outline_width_c, smooth=tk.TRUE)
        elif shape_type == "rectangle":
            half_w_c, half_h_c = diameter_c / 2, diameter_c / 2 # Rectangles will be squares based on diameter
            
            # Define corners relative to center (0,0) in canvas scale
            local_corners_c = [
                (-half_w_c, -half_h_c), (half_w_c, -half_h_c),
                (half_w_c, half_h_c), (-half_w_c, half_h_c)
            ]
            
            rotated_corners_c = []
            for x_loc_c, y_loc_c in local_corners_c:
                # Rotate point around (0,0)
                xr_c, yr_c = self._rotate_point(x_loc_c, y_loc_c, angle_deg, 0, 0)
                # Translate to final canvas center
                rotated_corners_c.extend([xr_c + cx_c, yr_c + cy_c])
            
            self.canvas.create_polygon(rotated_corners_c, fill=fill_color, outline=outline_color,
                                       width=outline_width_c)
        # Add other shapes here with elif shape_type == "other_shape":


    def _draw_crate_rack(self, rack_config, global_start_tube_number=0, use_global_numbering=False):
        cols,rows=rack_config['x_tubes'],rack_config['y_tubes'];
        tube_diameter_w=rack_config['tube_diameter'];angle=rack_config.get('rotation_angle',0)
        if cols==0 or rows==0:return 
        
        # _get_rack_dimensions_and_points returns world coordinates for outline and tube centers
        tube_centers_world,rotated_outline_world,_,_,_=self._get_rack_dimensions_and_points(rack_config)
        self._draw_rack_outline(rack_config,rotated_outline_world) 
        
        # tube_diameter_w is the full diameter for the shape's bounding box
        for tube_idx, tube_data in enumerate(rack_config['tubes']): 
            # Find the pre-calculated world center for this tube_idx
            current_tube_info_w = next((info for info in tube_centers_world if info[0] == tube_idx), None)
            if not current_tube_info_w: continue
            
            _, world_cx, world_cy, _ = current_tube_info_w # World center and diameter

            tube_type = tube_data.get('type', "Standard")
            visual_props = self.FIREWORK_TYPE_VISUALS.get(tube_type, self.FIREWORK_TYPE_VISUALS["Standard"])
            tube_outline_color = visual_props["outline"]
            tube_outline_width_w = self.DEFAULT_TUBE_OUTLINE_WIDTH_WORLD * visual_props["width_factor"]
            shape_type = visual_props.get("shape", "oval") # Default to oval if not specified

            self._draw_tube_shape(world_cx, world_cy, tube_diameter_w, angle, tube_data['color'], outline_color=tube_outline_color, outline_width_world=tube_outline_width_w, shape_type=shape_type)

            if self.show_tube_numbers_var.get(): 
                canvas_cx, canvas_cy = self.world_to_canvas(world_cx, world_cy)
                font_size = max(6, int(8 * self.zoom_level)) # Scale font size
                display_text = tube_data.get('cue', '') 
                if not display_text: # If no cue, use number
                    if use_global_numbering:
                        display_text = str(global_start_tube_number + tube_idx + 1)
                    else:
                        display_text = str(tube_idx + 1) # Original local numbering
                self.canvas.create_text(canvas_cx, canvas_cy, text=display_text, fill="black", font=("Arial", font_size), anchor=tk.CENTER,
                                        tags=(f"rack_element_{rack_config['id']}", f"tube_num_text_{rack_config['id']}_{tube_idx}")) 

    def _draw_fan_rack(self, rack_config, global_start_tube_number=0, use_global_numbering=False):
        num_fans,tubes_per_fan=rack_config['x_tubes'],rack_config['y_tubes'];
        tube_diameter_w=rack_config['tube_diameter'];angle=rack_config.get('rotation_angle',0)
        if num_fans==0 or tubes_per_fan==0:return
        
        tube_centers_world,rotated_outline_world,(un_w_w,un_h_w),_,_=self._get_rack_dimensions_and_points(rack_config)
        self._draw_rack_outline(rack_config,rotated_outline_world) 
        
        # For drawing segment outlines (visual guides for fans)
        center_lx_w,center_ly_w=un_w_w/2,un_h_w/2 # Local center in world units
        base_x_w, base_y_w = float(rack_config['pos_x']), float(rack_config['pos_y'])
        spacing_y_in_fan_w=self.DEFAULT_TUBE_SPACING_RATIO*tube_diameter_w; 
        fan_visual_padding_w=self.DEFAULT_FAN_PADDING_RATIO*tube_diameter_w
        fan_rect_width_per_segment_w=tube_diameter_w+2*fan_visual_padding_w; 
        spacing_x_between_fans_w=self.DEFAULT_INTER_FAN_SPACING_RATIO*tube_diameter_w
        # tube_diameter_w is the full diameter for the shape's bounding box

        for f_idx in range(num_fans): 
            local_fan_rect_x1_w=self.RACK_OUTER_PADDING+f_idx*(fan_rect_width_per_segment_w+spacing_x_between_fans_w)
            local_fan_rect_y1_w=self.RACK_OUTER_PADDING
            local_fan_rect_x2_w=local_fan_rect_x1_w+fan_rect_width_per_segment_w
            height_of_tubes_in_fan_w=tubes_per_fan*tube_diameter_w+max(0,tubes_per_fan-1)*spacing_y_in_fan_w
            local_fan_rect_y2_w=local_fan_rect_y1_w+height_of_tubes_in_fan_w+2*fan_visual_padding_w 
            fan_corners_w=[(local_fan_rect_x1_w,local_fan_rect_y1_w),(local_fan_rect_x2_w,local_fan_rect_y1_w),
                         (local_fan_rect_x2_w,local_fan_rect_y2_w),(local_fan_rect_x1_w,local_fan_rect_y2_w)]
            rotated_poly_local_w=[self._rotate_point(px,py,angle,center_lx_w,center_ly_w) for px,py in fan_corners_w]
            rotated_poly_world_coords=[(base_x_w-center_lx_w+prx,base_y_w-center_ly_w+pry) for prx,pry in rotated_poly_local_w]
            # Convert segment outline to canvas coords
            canvas_segment_outline = [self.world_to_canvas(px_w, py_w) for px_w, py_w in rotated_poly_world_coords]
            flat_poly_canvas=[c for p in canvas_segment_outline for c in p] 
            if flat_poly_canvas: 
                self.canvas.create_polygon(flat_poly_canvas,outline="darkslateblue",width=max(1,1.5*self.zoom_level),dash=(4,2),fill='')

        for tube_idx, tube_data in enumerate(rack_config['tubes']): 
            current_tube_info_w = next((info for info in tube_centers_world if info[0] == tube_idx), None)
            if not current_tube_info_w: continue
            _, world_cx, world_cy, _ = current_tube_info_w

            tube_type = tube_data.get('type', "Standard")
            visual_props = self.FIREWORK_TYPE_VISUALS.get(tube_type, self.FIREWORK_TYPE_VISUALS["Standard"])
            tube_outline_color = visual_props["outline"]
            tube_outline_width_w = self.DEFAULT_TUBE_OUTLINE_WIDTH_WORLD * visual_props["width_factor"]
            shape_type = visual_props.get("shape", "oval") # Default to oval if not specified

            self._draw_tube_shape(world_cx, world_cy, tube_diameter_w, angle, tube_data['color'], outline_color=tube_outline_color, outline_width_world=tube_outline_width_w, shape_type=shape_type)

            if self.show_tube_numbers_var.get():
                canvas_cx, canvas_cy = self.world_to_canvas(world_cx, world_cy)
                font_size = max(6, int(8 * self.zoom_level))
                display_text = tube_data.get('cue', '')
                if not display_text: # If no cue, use number
                    if use_global_numbering:
                        display_text = str(global_start_tube_number + tube_idx + 1)
                    else:
                        display_text = str(tube_idx + 1) # Original local numbering
                self.canvas.create_text(canvas_cx, canvas_cy, text=display_text,fill="black", font=("Arial", font_size), anchor=tk.CENTER,
                                        tags=(f"rack_element_{rack_config['id']}",f"tube_num_text_{rack_config['id']}_{tube_idx}"))

if __name__ == '__main__':
    root = tk.Tk()
    root.geometry("1450x800") 
    app = FireworkRackPlanner(root)
    root.mainloop()

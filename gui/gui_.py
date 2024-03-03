import os.path
import re
import tkinter.filedialog
import pygame
import configparser
from queue import Queue
from threading import Event
from pygame import mixer
from time import sleep
from tkinter import (
    Label,
    Entry,
    LabelFrame,
    Button,
    Tk,
    WORD,
    END,
    BOTH,
    Y,
    LEFT,
    RIGHT,
)
from tkinter.scrolledtext import ScrolledText
from tkinter.messagebox import askokcancel


class _Sounds:
    def __init__(self):
        self.pygame = pygame
        self.pygame.init()
        self._mixer = mixer
        self._sounds_folder = os.path.abspath("gui")

        self._login_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_login1.ogg")
        )
        self._pointing_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_scroll1.ogg")
        )
        self._select_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_popup_select1.ogg")
        )
        self._success_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_button_on1.ogg")
        )
        self._error_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_button_ok1.ogg")
        )
        self._logout_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_logout1.ogg")
        )
        self._accept_sound = self._mixer.Sound(
            os.path.join(self._sounds_folder, "gui_popup_open1.ogg")
        )

    def login_sound(self):
        self._login_sound.play()

    def pointing_sound(self, _=None):
        self._pointing_sound.play()

    def select_sound(self):
        self._select_sound.play()

    def success_sound(self):
        self._select_sound.play()

    def error_sound(self):
        self._error_sound.play()

    def accept_sound(self):
        self._accept_sound.play()

    def logout_sound(self):
        self._logout_sound.play()


class _MainFrames:
    def __init__(self):
        self.main_frame = Tk()
        self.horizontal = str(pygame.display.Info().current_h)
        self.vertical = str(pygame.display.Info().current_w)
        self.main_frame.geometry(self.vertical + "x" + self.horizontal)
        self.main_frame.attributes("-fullscreen", True)
        self.main_frame.configure(bg="black")
        self.main_frame.resizable(False, False)
        self.main_frame.title("File synchronization options")


class _SubFrames:
    def __init__(self, main_frames: _MainFrames):
        self.main_frames = main_frames

        self.text_log_main_frame = LabelFrame(
            master=self.main_frames.main_frame,
            fg="white",
            text="log",
            background="black",
        )
        self.label_config_main_frame = LabelFrame(
            master=self.main_frames.main_frame,
            fg="white",
            text="configuration",
            background="black",
        )
        self.label_info_main_frame = LabelFrame(
            master=self.main_frames.main_frame,
            fg="white",
            text="message",
            background="black",
        )
        self.controller_main_frame = LabelFrame(
            master=self.main_frames.main_frame,
            fg="white",
            text="select",
            background="black",
        )


class _Texts:
    def __init__(self, sub_frames: _SubFrames):
        self.sub_frames = sub_frames
        self.text_log_main_frame_widget = ScrolledText(
            master=self.sub_frames.text_log_main_frame, wrap=WORD, state="disabled"
        )


class _Entries:
    def __init__(self, sub_frames: _SubFrames):
        self.sub_frames = sub_frames
        self.entry_widget = Entry(
            master=self.sub_frames.controller_main_frame,
            background="white",
            foreground="black",
            justify="center",
        )


class _Labels:
    def __init__(self, sub_frames: _SubFrames):
        self._sub_frames = sub_frames
        self.label_info_main_frame_widget = Label(
            master=self._sub_frames.label_info_main_frame,
            background="black",
            foreground="white",
            justify=LEFT,
            width=50,
        )
        self.label_config_main_frame_widget = Label(
            master=self._sub_frames.label_config_main_frame,
            background="black",
            foreground="white",
            justify=LEFT,
        )

    def label_info_change_message(self, color, msg):
        self.label_info_main_frame_widget.config(
            foreground=color,
            text=msg,
            width=len(msg) + sum(1 for char in msg if char.isupper()),
        )
        self.label_info_main_frame_widget["fg"] = color
        self.label_info_main_frame_widget["text"] = msg


class _Commands:
    def __init__(
        self,
        sounds: _Sounds,
        entries: _Entries,
        labels: _Labels,
        main_frames: _MainFrames,
        events_hash: dict[str, Event],
    ):
        self._events_hash = events_hash
        self._sounds = sounds
        self._entries = entries
        self._labels = labels
        self._main_frames = main_frames
        self._main_frames.main_frame.protocol("WM_DELETE_WINDOW", self.exit)
        self._parser = configparser.ConfigParser()

    def swap_widgets(self, widget_to_pack_forget, widgets_to_pack):
        for widget in widget_to_pack_forget:
            widget.pack_forget()
        for widget in widgets_to_pack:
            if isinstance(widget, Button):
                widget.bind("<Enter>", self._sounds.pointing_sound)
                widget.pack()
            elif isinstance(widget, Label):
                widget.pack(fill=BOTH)
            elif isinstance(widget, Entry):
                widget.pack(pady=10)
            else:
                widget.pack()

    def set_new_local_directory(self):
        self._main_frames.main_frame.grab_set()
        new_directory = tkinter.filedialog.askdirectory()
        if not new_directory:
            self._labels.label_info_change_message("white", "Main menu")
            self._sounds.error_sound()
        elif os.path.exists(new_directory) and os.path.isdir(new_directory):
            old_value = self.update_config("app_config", "local_path", new_directory)
            self._sounds.accept_sound()
            self._events_hash["local_folder_set_event"].set()
            self._labels.label_info_change_message(
                "green",
                f"Local path has been changed\n"
                f"FROM {old_value}\n"
                f"TO {new_directory}",
            )
        else:
            self._sounds.error_sound()
            self._labels.label_info_change_message(
                "red", f"Directory by path {new_directory} not found"
            )
        self.update_current_configuration()
        self._main_frames.main_frame.grab_release()

    def set_new_interval(self):
        try:
            new_value = float(self._entries.entry_widget.get())
            self._entries.entry_widget.delete(0, END)
            if not 0.1 <= new_value <= 86400:
                raise ValueError("Interval must be at 0.1 to 86400.0 seconds.")
            old_value = self.update_config("app_config", "interval", new_value)
            self._sounds.accept_sound()
            self._labels.label_info_change_message(
                "green", f"Interval has been changed from {old_value} to {new_value}"
            )
            self._events_hash["interval_set_event"].set()
        except ValueError as e:
            self._sounds.error_sound()
            self._labels.label_info_change_message("red", f"Incorrect interval.\n{e}")

    def set_new_token(self):
        new_value = self._entries.entry_widget.get()
        if askokcancel("Warning", "Token serves for connection to disk api."):
            self.update_config("api", "token", new_value)
            self._sounds.accept_sound()
            self._events_hash["token_set_event"].set()
            self._labels.label_info_change_message("green", f"Token has been changed")
        else:
            self._sounds.error_sound()
            self._labels.label_info_change_message("white", f"Main menu")

        self._entries.entry_widget.delete(0, END)

    def exit(self):
        self._labels.label_info_change_message("white", "Session termination")
        self._labels.label_info_main_frame_widget.update()
        self._sounds.logout_sound()
        self._events_hash["exit_event"].set()
        sleep(2)
        self._sounds.pygame.quit()
        self._main_frames.main_frame.destroy()

    def update_config(self, section, key, new_value):
        old_value = self._parser[section][key]
        self._parser[section][key] = str(new_value)
        with open("config.ini", "w", encoding="utf-8") as file:
            self._parser.write(file)
        return old_value

    def update_current_configuration(self):
        current_config = ""
        self._parser.read(os.path.abspath("config.ini"))
        local_path = self._parser.get("app_config", "local_path")
        interval = self._parser.get("app_config", "interval")

        current_config += f"Scanning local directory: {local_path}\n"
        current_config += f"Scanning interval: every {interval} seconds"

        self._labels.label_config_main_frame_widget.config(text=current_config)

    def toggle_full_screen(self):
        if self._main_frames.main_frame.attributes("-fullscreen"):
            self._main_frames.main_frame.attributes("-fullscreen", False)
            self._main_frames.main_frame.resizable(True, True)
        else:
            self._main_frames.main_frame.overrideredirect(False)
            self._main_frames.main_frame.geometry(
                self._main_frames.vertical + "x" + self._main_frames.horizontal
            )
            self._main_frames.main_frame.attributes("-fullscreen", True)
            self._main_frames.main_frame.resizable(False, False)


class _Buttons:
    def __init__(
        self,
        entries: _Entries,
        labels: _Labels,
        commands: _Commands,
        sounds: _Sounds,
        sub_frames: _SubFrames,
    ):
        self._entries = entries
        self._labels = labels
        self._commands = commands
        self._sounds = sounds
        self._sub_frames = sub_frames
        self._width_buttons = len("Change synchronization interval")

        self.button_get_set_token_window_menu = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._sounds.select_sound(),
                entries.entry_widget.config(width=65, show="*"),
                self._labels.label_info_change_message("white", "Set new token"),
                self._commands.swap_widgets(
                    widget_to_pack_forget=self.menu_buttons,
                    widgets_to_pack=(
                        entries.entry_widget,
                        self.button_set_token,
                        self.button_back,
                    ),
                ),
            ),
            text="Change token",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_set_local_directory_menu = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._sounds.select_sound(),
                self._commands.set_new_local_directory(),
            ),
            text="Change local directory",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_toggle_screen_menu = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._sounds.select_sound(),
                self._commands.toggle_full_screen(),
            ),
            text="Fullscreen/Window",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_exit_menu = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (self._commands.exit(),),
            text="Exit",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )
        self.button_get_set_change_interval_window_menu = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._sounds.select_sound(),
                entries.entry_widget.config(width=5),
                self._labels.label_info_change_message("white", "Set new interval"),
                self._commands.swap_widgets(
                    widget_to_pack_forget=self.all_controller_widgets,
                    widgets_to_pack=(
                        self._entries.entry_widget,
                        self.button_set_interval,
                        self.button_back,
                    ),
                ),
            ),
            text="Change synchronization interval",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_set_interval = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._commands.set_new_interval(),
                self._commands.swap_widgets(
                    widget_to_pack_forget=self.all_controller_widgets,
                    widgets_to_pack=self.menu_buttons,
                ),
                self._commands.update_current_configuration(),
            ),
            text="set",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_set_token = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._commands.set_new_token(),
                self._entries.entry_widget.config(show=""),
                self._commands.swap_widgets(
                    widget_to_pack_forget=self.all_controller_widgets,
                    widgets_to_pack=self.menu_buttons,
                ),
                self._commands.update_current_configuration(),
            ),
            text="set",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.button_back = Button(
            master=self._sub_frames.controller_main_frame,
            command=lambda: (
                self._sounds.error_sound(),
                self._entries.entry_widget.config(show=""),
                self._entries.entry_widget.delete(0, END),
                self._labels.label_info_change_message("white", "Main menu"),
                self._commands.swap_widgets(
                    widget_to_pack_forget=(self.all_controller_widgets),
                    widgets_to_pack=self.menu_buttons,
                ),
            ),
            text="back",
            foreground="black",
            background="white",
            activeforeground="white",
            activebackground="black",
            width=self._width_buttons,
        )

        self.menu_buttons = [
            self[attribute_name]
            for attribute_name in dir(self)[::-1]
            if attribute_name.endswith("menu")
        ]
        self.all_controller_widgets = [
            self[attribute_name]
            for attribute_name in dir(self)
            if attribute_name.startswith("button")
        ]
        self.all_controller_widgets.append(self._entries.entry_widget)

    def __getitem__(self, item):
        return getattr(self, item)


class Gui:
    def __init__(self, queue: Queue, events_hash: dict[str, Event]):
        self._queue = queue
        self._events_hash = events_hash
        self._sounds = _Sounds()
        self._main_frames = _MainFrames()
        self._sub_frames = _SubFrames(self._main_frames)
        self._texts = _Texts(self._sub_frames)
        self._entries = _Entries(self._sub_frames)
        self._labels = _Labels(self._sub_frames)
        self._commands = _Commands(
            self._sounds,
            self._entries,
            self._labels,
            self._main_frames,
            self._events_hash,
        )
        self._buttons = _Buttons(
            self._entries, self._labels, self._commands, self._sounds, self._sub_frames
        )

        self._create_menu_window()
        self._labels.label_info_change_message("white", "Main menu")

        self._commands.update_current_configuration()
        self._sounds.login_sound()

        self._main_frames.main_frame.after(1, self._refresh_log),
        self._main_frames.main_frame.mainloop()

    def _create_menu_window(self):
        self._sub_frames.text_log_main_frame.pack(fill=BOTH)
        self._texts.text_log_main_frame_widget.pack(fill=BOTH)

        self._sub_frames.label_config_main_frame.pack(side=LEFT, fill=BOTH)
        self._labels.label_config_main_frame_widget.pack()

        self._sub_frames.label_info_main_frame.pack(fill=Y)
        self._labels.label_info_main_frame_widget.pack()

        self._sub_frames.controller_main_frame.pack(fill=Y)
        for button_widget in self._buttons.menu_buttons:
            button_widget.bind("<Enter>", self._sounds.pointing_sound)
            button_widget.pack()

    def _colorize_word_in_last_line(self, word, color):
        last_line_text = self._texts.text_log_main_frame_widget.get(
            END + "-2 lines linestart", END
        ).strip()

        match = re.search(r"\b" + re.escape(word) + r"\b", last_line_text)
        if match:
            start_index = END + "-2 lines linestart" + "+{}c".format(match.start())
            end_index = start_index + "+{}c".format(len(word))

            self._texts.text_log_main_frame_widget.tag_add(word, start_index, end_index)
            self._texts.text_log_main_frame_widget.tag_configure(word, foreground=color)

    def _refresh_log(self):
        try:
            while not self._queue.empty():
                log = self._queue.get()

                self._texts.text_log_main_frame_widget.configure(state="normal")
                self._texts.text_log_main_frame_widget.insert(END, log.rstrip() + "\n")
                self._texts.text_log_main_frame_widget.configure(state="disabled")

                self._colorize_word_in_last_line("Detected", "#b8860b")
                self._colorize_word_in_last_line("Deleting", "green")
                self._colorize_word_in_last_line("Overwriting", "green")
                self._colorize_word_in_last_line("Writing", "green")
                self._colorize_word_in_last_line("Updating", "green")
                self._colorize_word_in_last_line("updated", "green")
                self._colorize_word_in_last_line("successfully", "green")
                self._colorize_word_in_last_line("unsuccessfully", "red")
                self._colorize_word_in_last_line("Initialize", "green")
                self._colorize_word_in_last_line("Initializing", "green")
                self._colorize_word_in_last_line("start", "green")

            self._texts.text_log_main_frame_widget.update_idletasks()
            self._main_frames.main_frame.after(1, self._refresh_log)
        except RecursionError:
            self._main_frames.main_frame.after(1, self._refresh_log)

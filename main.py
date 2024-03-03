from app import mainloop
from gui.gui_ import Gui
from threading import Thread, Event
from queue import Queue


def launch_app():
    queue = Queue()
    events_hash = {
        'token_set_event': Event(),
        'interval_set_event': Event(),
        'local_folder_set_event': Event(),
        'exit_event': Event(),
    }

    gui_thread = Thread(target=lambda: Gui(queue, events_hash))
    synch_thread = Thread(target=lambda: mainloop(queue, events_hash))
    gui_thread.start()
    synch_thread.start()


if __name__ == '__main__':
    launch_app()

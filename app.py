import configparser
import json
import logging
import os
import requests
from threading import Event
from time import time, sleep
from queue import Queue
from requests import Response
from datetime import datetime
from copy import copy

parser = configparser.ConfigParser()
parser.read('config.ini')
logging.basicConfig(
    filename=parser.get('app_config', 'log_path'),
    format='%(name)s | %(asctime)s | %(levelname)s | %(message)s',
    level=logging.INFO
)
logger = logging.getLogger('synchronizer')
CONFIG_PATH = 'config.ini'


class Synchronizer:
    def __init__(self, token: str, events_hash: dict[str, Event], queue: Queue):
        self._token = token
        self._events_hash = events_hash
        self._queue = queue
        self._headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'Authorization': f'OAuth {self._token}',
        }
        self._base_url = 'https://cloud-api.yandex.net/v1/disk/'

    def _check_local_folder_change(self):
        if self._events_hash['local_folder_set_event'].is_set():
            self._events_hash['local_folder_set_event'].clear()

            parser.read(CONFIG_PATH)
            local_folder_name = parser.get('app_config', 'local_path').split('/')[-1]
            create_folder_response_status_code = self.create_folder(local_folder_name).status_code

            if create_folder_response_status_code == 201:
                log = 'Remote folder created successfully'
                propagate_log(log, self._queue, False)
            elif create_folder_response_status_code == 401:
                log = f'Remote folder creating unsuccessfully. Authorization error. Please, set valid OAuth-token.'
                propagate_log(log, self._queue)
            elif create_folder_response_status_code == 409:
                f'Remote folder {local_folder_name} found on remote storage.'
            else:
                log = 'Remote folder creating unsuccessfully. Internal server error.'
                propagate_log(log, self._queue)

            return local_folder_name
        else:
            return parser.get('app_config', 'local_path').split('/')[-1]

    def _check_token_change(self):
        if self._events_hash['token_set_event'].is_set():
            self._events_hash['token_set_event'].clear()
            parser.read(CONFIG_PATH)
            new_token = parser.get('api', 'token')
            self._token = new_token
            self._headers['Authorization'] = f'OAuth {new_token}'
            # log = 'Detected changed token. Initialize new record keeping.'
            # propagate_log(log, self._queue, False)
            # first_synchronization(self, self._queue, self._events_hash)

    def load(self, abs_local_file_path) -> Response:
        self._check_token_change()
        local_folder_name = self._check_local_folder_change()
        file_name = abs_local_file_path.split("/")[-1]

        return requests.get(
            f'{self._base_url}resources/upload?path=%2F{local_folder_name}%2F{file_name}',
            headers=self._headers
        )

    def reload(self, abs_local_file_path) -> Response:
        self._check_token_change()
        local_folder_name = self._check_local_folder_change()
        file_name = abs_local_file_path.split("/")[-1]

        return requests.get(
            f'{self._base_url}resources/upload?path=%2F{local_folder_name}%2F{file_name}&overwrite=true',
            headers=self._headers
        )

    def delete(self, file_name, permanently: bool = False) -> Response:
        self._check_token_change()
        local_folder_name = self._check_local_folder_change()
        return requests.delete(
            f'{self._base_url}resources?path=%2F{local_folder_name}%2F{file_name}&permanently={str(permanently).lower()}',
            headers=self._headers
        )

    def get_info(self) -> Response:
        self._check_token_change()
        local_folder_name = self._check_local_folder_change()
        return requests.get(
            f'{self._base_url}resources?path=%2F{local_folder_name}',
            headers=self._headers
        )

    def create_folder(self, local_folder_name) -> Response:
        self._check_token_change()
        return requests.put(f'{self._base_url}resources?path=%2F{local_folder_name}', headers=self._headers)


def load_local_file(file_name: str, queue: Queue, synchronizer: Synchronizer, overwrite=False):
    parser.read(CONFIG_PATH)
    abs_local_file_path = parser.get('app_config', 'local_path') + '/' + file_name
    if overwrite:
        log = f'Detected change in file {file_name}'
        method = synchronizer.reload
    else:
        method = synchronizer.load
        log = f'Detected new file {file_name}'
    propagate_log(log, queue, False)

    response = method(abs_local_file_path)

    if response.status_code == 401:
        log = f'Authorization unsuccessfully. Please, set valid OAuth-token.'
        propagate_log(log, queue)
    elif response.status_code == 409:
        log = f'File {file_name} already load on remote storage. Updating local meta data.'
        propagate_log(log, queue, False)
        return True
    elif response.status_code == 200:
        with open(abs_local_file_path, 'rb') as file:
            while requests.put(response.json()['href'], data=file).status_code == 202:
                pass
            response = requests.put(response.json()['href'], data=file)
        if response.status_code == 201:
            log = f'{"Overwriting" if overwrite else "Writing"} file {file_name} successfully.'
            propagate_log(log, queue, False)
            return True
        elif response.status_code == 413:
            log = f'File size too large {file_name}'
            propagate_log(log, queue)
        elif response.status_code == 507:
            log = f'Remote storage is full. Writing denied.'
            propagate_log(log, queue)
        else:
            log = f'Unknown error. {response.text} {response.status_code}'
            propagate_log(log, queue)
    else:
        log = f'Unknown error. {response.text} {response.status_code}'
        propagate_log(log, queue)


def delete_remote_file(last_file_name, queue, synchronizer):
    log = f'Detected removed file {last_file_name}.'
    propagate_log(log, queue, False)

    response = synchronizer.delete(last_file_name)

    if response.status_code == 204:
        log = f'Deleting remote file {last_file_name} successfully.'
        propagate_log(log, queue, False)
        return True
    elif response.status_code == 404:
        log = f'File {last_file_name} not found on remote storage. Updating local record keeping.'
        propagate_log(log, queue, False)
        return True
    elif response.status_code == 401:
        log = f'Authorization unsuccessfully. Please, set valid OAuth-token.'
        propagate_log(log, queue)
    else:
        log = f'Unknown error. {response.text} {response.status_code}'
        propagate_log(log, queue)


def synchronization(synchronizer: Synchronizer, queue: Queue, events_hash: dict[str, Event]):
    changes_have_been_made = False
    local_data = get_meta_data_files_local_folder(queue, events_hash)
    record_keeping_path = parser.get('app_config', 'record_keeping_path')
    if os.path.getsize(os.path.abspath(record_keeping_path)) > 0:
        with open(record_keeping_path, 'r') as file:
            last_local_data = json.load(file)
            record_keeping = copy(last_local_data)
        for last_file_name, last_file_size in last_local_data.items():
            if last_file_name not in local_data and delete_remote_file(last_file_name, queue, synchronizer):
                changes_have_been_made = True
                record_keeping.pop(last_file_name)
            elif last_file_name in local_data and local_data[last_file_name] != last_file_size and load_local_file(last_file_name, queue, synchronizer, overwrite=True):
                changes_have_been_made = True
                record_keeping[last_file_name] = local_data[last_file_name]

        for local_file_name, local_file_size in local_data.items():
            if local_file_name not in last_local_data and load_local_file(local_file_name, queue, synchronizer):
                changes_have_been_made = True
                record_keeping[local_file_name] = local_file_size

        # if changes_have_been_made:
        #     log = 'Scanning is over. Changes have been made.'
        #     propagate_log(log, queue, False)
        # else:
        #     pass
            # log = 'Scanning is over. Changes not found.'
            # propagate_log(log, queue, False)

        with open(record_keeping_path, 'w') as file:
            json.dump(record_keeping, file, indent=4)
    else:
        first_synchronization(synchronizer, queue, events_hash)


def check_authorization(synchronizer: Synchronizer, queue: Queue, events_hash):
    detected_wrong_token = False
    while not events_hash['exit_event'].is_set():
        if not synchronizer.get_info().status_code == 401:
            break
        detected_wrong_token = True
        log = f'Authorization unsuccessfully. Please, set valid OAuth-token.'
        propagate_log(log, queue)
        sleep(10)
    if events_hash['exit_event'].is_set():
        exit()
    if detected_wrong_token:
        log = 'Token updated. Authorization successfully.'
        propagate_log(log, queue, False)


def get_meta_data_files_local_folder(queue: Queue, events_hash: dict[str, Event]) -> dict[str, int]:
    parser.read(CONFIG_PATH)
    local_path = parser.get('app_config', 'local_path')
    detected_wrong_folder = False
    while not events_hash['exit_event'].is_set():
        parser.read(CONFIG_PATH)
        local_path = parser.get('app_config', 'local_path')
        if os.path.exists(local_path):
            break
        else:
            detected_wrong_folder = True
            log = (f'Local directory {"not exists" if local_path else "not set"}.'
                   f' Press key "Change local directory and choose folder for synchronization')
            propagate_log(log, queue)
            sleep(10)

    if events_hash['exit_event'].is_set():
        exit()
    if detected_wrong_folder:
        log = 'Local directory updated.'
        propagate_log(log, queue, False)

    local_files_hash = {}
    for local_file_name in os.listdir(local_path):
        local_file_path = f'{local_path}/{local_file_name}'
        if os.path.isfile(local_file_path):
            local_files_hash[local_file_name] = os.path.getsize(local_file_path)
    try:
        local_files_hash.pop(parser.get('app_config', 'record_keeping_path').split('/')[-1])
    except KeyError:
        pass

    return local_files_hash


def first_synchronization(synchronizer: Synchronizer, queue: Queue, events_hash: dict[str, Event]):
    parser.read('config_ini')
    log = 'Initialize new record keeping.'
    propagate_log(log, queue, False)

    # vvv infinity validation user parameters vvv
    check_authorization(synchronizer, queue, events_hash)
    local_data = get_meta_data_files_local_folder(queue, events_hash)
    # ^^^ infinity validation user parameters ^^^

    local_folder_name = parser.get('app_config', 'local_path').split('/')[-1]
    synchronizer.create_folder(local_folder_name)

    record_keeping = local_data.copy()
    record_keeping_path = parser.get('app_config', 'record_keeping_path')
    record_keeping_abspath = os.path.abspath(record_keeping_path)
    if os.path.exists(record_keeping_abspath):
        os.remove(record_keeping_abspath)

    for local_file_name in local_data:
        abs_local_file_path = local_folder_name + '/' + local_file_name
        if load_local_file(local_file_name, queue, synchronizer):
            record_keeping[local_file_name] = os.path.getsize(abs_local_file_path)

    with open(record_keeping_path, 'w') as file:
        json.dump(record_keeping, file, indent=4)


def sleep_by_interval(events_hash: dict[str, Event]):
    start_wait = time()
    interval = float(parser.get('app_config', 'interval'))
    while time() - start_wait < interval and not events_hash['interval_set_event'].is_set() and not events_hash['exit_event'].is_set():
        pass
    events_hash['interval_set_event'].clear()


def propagate_log(log: str, queue: Queue, error: bool = True):
    if error:
        logger.error(log)
    else:
        logger.info(log)
    queue.put(datetime.now().strftime("%d.%m.%y %H:%M:%S ") + log)


def mainloop(queue: Queue, events_hash: dict[str, Event]):
    log = f'File synchronizer start working with directory: {parser.get("app_config", "local_path")}'
    propagate_log(log, queue, False)
    parser.read(CONFIG_PATH)
    synchronizer = Synchronizer(
        parser.get('api', 'token'),
        events_hash,
        queue,
    )

    try:
        if not os.path.exists(parser.get('app_config', 'record_keeping_path')):
            first_synchronization(synchronizer, queue, events_hash)
            log = 'Initializing record keeping is over.'
            propagate_log(log, queue, False)

        # vvv Main cycle vvv
        while not events_hash['exit_event'].is_set():
            parser.read(CONFIG_PATH)
            sleep_by_interval(events_hash)
            check_authorization(synchronizer, queue, events_hash)
            synchronization(synchronizer, queue, events_hash)
        # ^^^ Main cycle ^^^

    except requests.exceptions.ConnectionError:
        log = 'Connection error. Check the internet connection.'
        propagate_log(log, queue)
        mainloop(queue, events_hash)

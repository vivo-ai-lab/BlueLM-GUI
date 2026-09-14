"""评测数据接口客户端。

评测数据不来自本地文件，而是通过模拟器后端接口动态获取：
  1. GET /suite/reinitialize?n_task_combinations=1&seed={seed}&task_family=android_world
     重建任务 suite（按 seed 生成 golden 参数，保证可复现）。
  2. GET /suite/task_list?max_index=-1
     获取所有任务类型列表。
  3. GET /suite/task_length?task_type={task_name}
     获取每种任务类型的组合数量。
  4. GET /task/goal?task_type={task_name}&task_idx={task_idx}
     获取任务目标（作为评测指令 prompt）。
"""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

# task_type → complexity 完整映射
# android_world 单任务族（与训练侧 verl/experimental/agent_loop/gui/complexity_map.py 一致）
# + information_retrieval 任务族（默认 1.0，官方覆盖见 information_retrieval_registry.py）
COMPLEXITY_MAP: dict[str, float] = {
    # audio_recorder
    "AudioRecorderRecordAudio": 1.2,
    "AudioRecorderRecordAudioWithFileName": 2.0,
    # browser
    "BrowserDraw": 2.0,
    "BrowserMaze": 2.0,
    "BrowserMultiply": 2.2,
    # calendar
    "SimpleCalendarAddOneEvent": 3.4,
    "SimpleCalendarAddOneEventInTwoWeeks": 3.4,
    "SimpleCalendarAddOneEventRelativeDay": 3.4,
    "SimpleCalendarAddOneEventTomorrow": 3.4,
    "SimpleCalendarAddRepeatingEvent": 3.4,
    "SimpleCalendarDeleteEvents": 1.4,
    "SimpleCalendarDeleteEventsOnRelativeDay": 1.2,
    "SimpleCalendarDeleteOneEvent": 1.2,
    # camera
    "CameraTakePhoto": 1.0,
    "CameraTakeVideo": 1.0,
    # clock
    "ClockStopWatchPausedVerify": 1.0,
    "ClockStopWatchRunning": 1.0,
    "ClockTimerEntry": 1.0,
    # contacts
    "ContactsAddContact": 1.2,
    "ContactsNewContactDraft": 1.2,
    # expense
    "ExpenseAddMultiple": 3.0,
    "ExpenseAddMultipleFromGallery": 6.0,
    "ExpenseAddMultipleFromMarkor": 6.0,
    "ExpenseAddSingle": 1.2,
    "ExpenseDeleteDuplicates": 1.2,
    "ExpenseDeleteDuplicates2": 1.8,
    "ExpenseDeleteMultiple": 2.0,
    "ExpenseDeleteMultiple2": 2.0,
    "ExpenseDeleteSingle": 1.0,
    # files
    "FilesDeleteFile": 2.2,
    "FilesMoveFile": 2.0,
    # markor
    "MarkorAddNoteHeader": 1.2,
    "MarkorChangeNoteContent": 1.2,
    "MarkorCreateFolder": 1.0,
    "MarkorCreateNote": 1.6,
    "MarkorCreateNoteFromClipboard": 1.4,
    "MarkorDeleteAllNotes": 1.4,
    "MarkorDeleteNewestNote": 1.0,
    "MarkorDeleteNote": 1.0,
    "MarkorEditNote": 1.2,
    "MarkorMergeNotes": 7.8,
    "MarkorMoveNote": 1.4,
    "MarkorTranscribeReceipt": 1.8,
    "MarkorTranscribeVideo": 2.0,
    # markor_sms (composite)
    "MarkorCreateNoteAndSms": 1.8,
    # osmand
    "OsmAndFavorite": 1.3,
    "OsmAndMarker": 2.0,
    "OsmAndTrack": 12.0,
    # recipe
    "RecipeAddMultipleRecipes": 6.0,
    "RecipeAddMultipleRecipesFromImage": 6.0,
    "RecipeAddMultipleRecipesFromMarkor": 6.0,
    "RecipeAddMultipleRecipesFromMarkor2": 6.0,
    "RecipeAddSingleRecipe": 2.4,
    "RecipeDeleteDuplicateRecipes": 1.0,
    "RecipeDeleteDuplicateRecipes2": 2.4,
    "RecipeDeleteDuplicateRecipes3": 3.4,
    "RecipeDeleteMultipleRecipes": 2.4,
    "RecipeDeleteMultipleRecipesWithConstraint": 3.0,
    "RecipeDeleteMultipleRecipesWithNoise": 3.4,
    "RecipeDeleteSingleRecipe": 1.0,
    "RecipeDeleteSingleWithRecipeWithNoise": 2.0,
    # retro_music
    "RetroCreatePlaylist": 2.4,
    "RetroPlayingQueue": 3.2,
    "RetroPlaylistDuration": 3.0,
    "RetroSavePlaylist": 5.0,
    # simple_draw_pro
    "SimpleDrawProCreateDrawing": 1.8,
    # simple_gallery_pro
    "SaveCopyOfReceiptTaskEval": 1.6,
    # sms
    "SimpleSmsReply": 1.2,
    "SimpleSmsReplyMostRecent": 1.2,
    "SimpleSmsResend": 1.2,
    "SimpleSmsSend": 1.2,
    "SimpleSmsSendClipboardContent": 1.2,
    "SimpleSmsSendReceivedAddress": 1.8,
    # system
    "OpenAppTaskEval": 1.0,
    "SystemBluetoothTurnOff": 1.0,
    "SystemBluetoothTurnOffVerify": 1.0,
    "SystemBluetoothTurnOn": 1.0,
    "SystemBluetoothTurnOnVerify": 1.0,
    "SystemBrightnessMax": 1.0,
    "SystemBrightnessMaxVerify": 1.0,
    "SystemBrightnessMin": 1.0,
    "SystemBrightnessMinVerify": 1.0,
    "SystemCopyToClipboard": 1.0,
    "SystemWifiTurnOff": 1.0,
    "SystemWifiTurnOffVerify": 1.0,
    "SystemWifiTurnOn": 1.0,
    "SystemWifiTurnOnVerify": 1.0,
    # system_composite
    "TurnOffWifiAndTurnOnBluetooth": 2.0,
    "TurnOnWifiAndOpenApp": 2.0,
    # vlc
    "VlcCreatePlaylist": 2.8,
    "VlcCreateTwoPlaylists": 4.8,
    # information_retrieval
    "NotesIsTodo": 1.0,
    "NotesMeetingAttendeeCount": 1.0,
    "NotesRecipeIngredientCount": 1.0,
    "NotesTodoItemCount": 1.0,
    "SportsTrackerActivitiesCountForWeek": 1.0,
    "SportsTrackerActivitiesOnDate": 2.0,
    "SportsTrackerActivityDuration": 1.2,
    "SportsTrackerLongestDistanceActivity": 1.0,
    "SportsTrackerTotalDistanceForCategoryOverInterval": 2.2,
    "SportsTrackerTotalDurationForCategoryThisWeek": 1.6,
    "TasksCompletedTasksForDate": 1.0,
    "TasksDueNextWeek": 1.2,
    "TasksDueOnDate": 1.0,
    "TasksHighPriorityTasks": 1.0,
    "TasksHighPriorityTasksDueOnDate": 1.0,
    "TasksIncompleteTasksOnDate": 1.0,
    "SimpleCalendarAnyEventsOnDate": 1.0,
    "SimpleCalendarEventOnDateAtTime": 1.0,
    "SimpleCalendarEventsInNextWeek": 1.0,
    "SimpleCalendarEventsInTimeRange": 1.0,
    "SimpleCalendarEventsOnDate": 1.0,
    "SimpleCalendarFirstEventAfterStartTime": 1.0,
    "SimpleCalendarLocationOfEvent": 1.0,
    "SimpleCalendarNextEvent": 1.0,
    "SimpleCalendarNextMeetingWithPerson": 1.0,
}


# task_name → package_name 映射（与训练侧 ray_trainer_plus.py 保持一致）
TASK_NAME_TO_APP: dict[str, list[str]] = {
    "AudioRecorderRecordAudio": ["audio recorder"],
    "AudioRecorderRecordAudioWithFileName": ["audio recorder"],
    "BrowserDraw": ["files", "chrome"],
    "BrowserMaze": ["files", "chrome"],
    "BrowserMultiply": ["files", "chrome"],
    "CameraTakePhoto": ["camera"],
    "CameraTakeVideo": ["camera"],
    "ClockStopWatchPausedVerify": ["clock"],
    "ClockStopWatchRunning": ["clock"],
    "ClockTimerEntry": ["clock"],
    "ContactsAddContact": ["contacts"],
    "ContactsNewContactDraft": ["contacts"],
    "ExpenseAddMultiple": ["pro expense"],
    "ExpenseAddMultipleFromGallery": ["simple gallery pro", "pro expense"],
    "ExpenseAddMultipleFromMarkor": ["markor", "pro expense"],
    "ExpenseAddSingle": ["pro expense"],
    "ExpenseDeleteDuplicates": ["pro expense"],
    "ExpenseDeleteDuplicates2": ["pro expense"],
    "ExpenseDeleteMultiple": ["pro expense"],
    "ExpenseDeleteMultiple2": ["pro expense"],
    "ExpenseDeleteSingle": ["pro expense"],
    "FilesDeleteFile": ["files"],
    "FilesMoveFile": ["files"],
    "MarkorAddNoteHeader": ["markor"],
    "MarkorChangeNoteContent": ["markor"],
    "MarkorCreateFolder": ["markor"],
    "MarkorCreateNote": ["markor"],
    "MarkorCreateNoteAndSms": ["markor", "simple sms messenger"],
    "MarkorCreateNoteFromClipboard": ["markor"],
    "MarkorDeleteAllNotes": ["markor"],
    "MarkorDeleteNewestNote": ["markor"],
    "MarkorDeleteNote": ["markor"],
    "MarkorEditNote": ["markor"],
    "MarkorMergeNotes": ["markor"],
    "MarkorMoveNote": ["markor"],
    "MarkorTranscribeReceipt": ["simple gallery pro", "markor"],
    "MarkorTranscribeVideo": ["vlc", "markor"],
    "NotesIsTodo": ["joplin"],
    "NotesMeetingAttendeeCount": ["joplin"],
    "NotesRecipeIngredientCount": ["joplin"],
    "NotesTodoItemCount": ["joplin"],
    "OsmAndFavorite": ["osmand"],
    "OsmAndMarker": ["osmand"],
    "OsmAndTrack": ["osmand"],
    "RecipeAddMultipleRecipes": ["broccoli"],
    "RecipeAddMultipleRecipesFromImage": ["simple gallery pro", "broccoli"],
    "RecipeAddMultipleRecipesFromMarkor": ["markor", "broccoli"],
    "RecipeAddMultipleRecipesFromMarkor2": ["markor", "broccoli"],
    "RecipeAddSingleRecipe": ["broccoli"],
    "RecipeDeleteDuplicateRecipes": ["broccoli"],
    "RecipeDeleteDuplicateRecipes2": ["broccoli"],
    "RecipeDeleteDuplicateRecipes3": ["broccoli"],
    "RecipeDeleteMultipleRecipes": ["broccoli"],
    "RecipeDeleteMultipleRecipesWithConstraint": ["broccoli"],
    "RecipeDeleteMultipleRecipesWithNoise": ["broccoli"],
    "RecipeDeleteSingleRecipe": ["broccoli"],
    "RecipeDeleteSingleWithRecipeWithNoise": ["broccoli"],
    "RetroCreatePlaylist": ["retro music"],
    "RetroPlayingQueue": ["retro music"],
    "RetroPlaylistDuration": ["retro music"],
    "RetroSavePlaylist": ["retro music"],
    "SaveCopyOfReceiptTaskEval": ["simple gallery pro"],
    "SimpleCalendarAddOneEvent": ["simple calendar pro"],
    "SimpleCalendarAddOneEventInTwoWeeks": ["simple calendar pro"],
    "SimpleCalendarAddOneEventRelativeDay": ["simple calendar pro"],
    "SimpleCalendarAddOneEventTomorrow": ["simple calendar pro"],
    "SimpleCalendarAddRepeatingEvent": ["simple calendar pro"],
    "SimpleCalendarAnyEventsOnDate": ["simple calendar pro"],
    "SimpleCalendarDeleteEvents": ["simple calendar pro"],
    "SimpleCalendarDeleteEventsOnRelativeDay": ["simple calendar pro"],
    "SimpleCalendarDeleteOneEvent": ["simple calendar pro"],
    "SimpleCalendarEventOnDateAtTime": ["simple calendar pro"],
    "SimpleCalendarEventsInNextWeek": ["simple calendar pro"],
    "SimpleCalendarEventsInTimeRange": ["simple calendar pro"],
    "SimpleCalendarEventsOnDate": ["simple calendar pro"],
    "SimpleCalendarFirstEventAfterStartTime": ["simple calendar pro"],
    "SimpleCalendarLocationOfEvent": ["simple calendar pro"],
    "SimpleCalendarNextEvent": ["simple calendar pro"],
    "SimpleCalendarNextMeetingWithPerson": ["simple calendar pro"],
    "SimpleDrawProCreateDrawing": ["simple draw pro"],
    "SimpleSmsReply": ["simple sms messenger"],
    "SimpleSmsReplyMostRecent": ["simple sms messenger"],
    "SimpleSmsResend": ["simple sms messenger"],
    "SimpleSmsSend": ["simple sms messenger"],
    "SimpleSmsSendClipboardContent": ["simple sms messenger"],
    "SimpleSmsSendReceivedAddress": ["simple sms messenger"],
    "SportsTrackerActivitiesCountForWeek": ["open tracks"],
    "SportsTrackerActivitiesOnDate": ["open tracks"],
    "SportsTrackerActivityDuration": ["open tracks"],
    "SportsTrackerLongestDistanceActivity": ["open tracks"],
    "SportsTrackerTotalDistanceForCategoryOverInterval": ["open tracks"],
    "SportsTrackerTotalDurationForCategoryThisWeek": ["open tracks"],
    "SystemBluetoothTurnOff": ["settings"],
    "SystemBluetoothTurnOffVerify": ["settings"],
    "SystemBluetoothTurnOn": ["settings"],
    "SystemBluetoothTurnOnVerify": ["settings"],
    "SystemBrightnessMax": ["settings"],
    "SystemBrightnessMaxVerify": ["settings"],
    "SystemBrightnessMin": ["settings"],
    "SystemBrightnessMinVerify": ["settings"],
    "SystemCopyToClipboard": ["clipper"],
    "SystemWifiTurnOff": ["settings"],
    "SystemWifiTurnOffVerify": ["settings"],
    "SystemWifiTurnOn": ["settings"],
    "SystemWifiTurnOnVerify": ["settings"],
    "TasksCompletedTasksForDate": ["tasks"],
    "TasksDueNextWeek": ["tasks"],
    "TasksDueOnDate": ["tasks"],
    "TasksHighPriorityTasks": ["tasks"],
    "TasksHighPriorityTasksDueOnDate": ["tasks"],
    "TasksIncompleteTasksOnDate": ["tasks"],
    "TurnOffWifiAndTurnOnBluetooth": ["settings"],
    "TurnOnWifiAndOpenApp": ["settings"],
    "VlcCreatePlaylist": ["vlc"],
    "VlcCreateTwoPlaylists": ["vlc"],
}


def fetch_eval_samples(
    base_url: str,
    seed: int = 42,
    max_index: int = -1,
    max_retries: int = 3,
    timeout: int = 240,
) -> list[dict]:
    """通过模拟器接口动态获取评测样本。

    Args:
        base_url: 模拟器后端地址（如 http://host:port）。
        seed: 随机种子，传给 reinitialize_suite 确保可复现。
        max_index: 传给 get_suite_task_list 的最大索引，-1 表示全部。
        max_retries: 接口失败重试次数。
        timeout: 请求超时（秒）。

    Returns:
        list[dict]: 每条含 prompt / task_type / task_id / package_name / seed。
    """
    base_url = base_url.rstrip("/")
    rows: list[dict] = []

    # 1. reinitialize_suite（带重试）
    reinit_url = f"{base_url}/suite/reinitialize"
    reinit_ok = False
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                reinit_url,
                params={"n_task_combinations": 1, "seed": seed, "task_family": "android_world"},
                timeout=timeout,
            )
            resp.raise_for_status()
            print(f"[data] reinitialize_suite(seed={seed}) ok (attempt {attempt})")
            reinit_ok = True
            break
        except Exception as e:
            print(f"[data] reinitialize_suite failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(3)
    if not reinit_ok:
        return rows

    time.sleep(2)

    # 2. get_suite_task_list
    task_list_url = f"{base_url}/suite/task_list"
    task_list: list[str] = []
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(task_list_url, params={"max_index": max_index}, timeout=timeout)
            resp.raise_for_status()
            task_list = resp.json().get("task_list", [])
            print(f"[data] get_suite_task_list: {len(task_list)} task types (attempt {attempt})")
            break
        except Exception as e:
            print(f"[data] get_suite_task_list failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                time.sleep(3)
    if not task_list:
        return rows

    # 3. 遍历每个 task_type，获取 task_length 并逐个取 goal
    for task_name in task_list:
        task_len_url = f"{base_url}/suite/task_length"
        try:
            resp = requests.get(task_len_url, params={"task_type": task_name}, timeout=30)
            resp.raise_for_status()
            num_tasks = resp.json().get("length", 1)
        except Exception as e:
            print(f"[data] get task_length for {task_name} failed: {e}")
            num_tasks = 1

        for task_idx in range(num_tasks):
            goal_url = f"{base_url}/task/goal"
            try:
                resp = requests.get(
                    goal_url,
                    params={"task_type": task_name, "task_idx": task_idx},
                    timeout=30,
                )
                resp.raise_for_status()
                goal = resp.json().get("goal", "")
            except Exception as e:
                print(f"[data] get_task_goal for {task_name}_{task_idx} failed: {e}")
                goal = ""

            if not goal:
                continue

            package_name = TASK_NAME_TO_APP.get(task_name, [""])[0]
            rows.append({
                "prompt": [{"role": "user", "content": goal}],
                "task_type": task_name,
                "task_id": task_idx,
                "package_name": package_name,
                "seed": seed,
                "complexity": COMPLEXITY_MAP.get(task_name),
            })

    print(f"[data] 生成 {len(rows)} 条评测数据 (seed={seed})")
    return rows
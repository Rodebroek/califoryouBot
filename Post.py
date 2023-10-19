import os
import json

import asyncio
import datetime
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from telethon import TelegramClient
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor

# --- Aiogram Config ---

API_TOKEN = '6984306442:AAFUxEhLUHs9EJ1u9uX_ZSjIa2HBKobX8Dk'
bot = Bot(token=API_TOKEN)

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())
# --- Telethon Config ---
api_id = '28287530'
api_hash = '3f0c822bc2d922b6e8a64fc275867d56'
client = TelegramClient('session_name', api_id, api_hash)


class ForwardingForm(StatesGroup):
    text = State()
    media_type = State()
    media = State()
    groups = State()
    delay = State()


@dp.message_handler(commands=['forward'])
async def start_forwarding(message: types.Message):
    await ForwardingForm.text.set()
    await message.answer("Enter message text:")


@dp.message_handler(state=ForwardingForm.text)
async def process_text(message: types.Message, state: FSMContext):
    await state.update_data(text=message.text)

    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("Add photo", callback_data="add_photo"),
        InlineKeyboardButton("Add a video", callback_data="add_video"),
        InlineKeyboardButton("Add file", callback_data="add_file"),
        InlineKeyboardButton("Only Text", callback_data="continue_without_media")
    )

    await message.answer("Select a media type or continue without it:", reply_markup=markup)


@dp.callback_query_handler(lambda c: c.data in ["add_photo", "add_video", "add_file"], state=ForwardingForm.text)
async def ask_for_media(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data == "add_photo":
        await ForwardingForm.media_type.set()
        await state.update_data(media_type="photo")
        await callback_query.message.answer("Please send a photo.")
    elif callback_query.data == "add_video":
        await ForwardingForm.media_type.set()
        await state.update_data(media_type="video")
        await callback_query.message.answer("Please send a video.")
    elif callback_query.data == "add_file":
        await ForwardingForm.media_type.set()
        await state.update_data(media_type="file")
        await callback_query.message.answer("Please send the file.")


@dp.message_handler(content_types=['photo'], state=ForwardingForm.media_type)
async def process_photo(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    media_type = user_data.get("media_type")
    if media_type == "photo":
        photo_path = f"media/photo_{message.photo[-1].file_id}.jpg"
        await bot.download_file_by_id(file_id=message.photo[-1].file_id, destination=photo_path)
        await state.update_data(photo=photo_path)

        await ForwardingForm.groups.set()
        await message.answer("Photo added. Specify the groups (separated by commas)"
                             " where you want to send the message:")


@dp.message_handler(content_types=['video'], state=ForwardingForm.media_type)
async def process_video(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    media_type = user_data.get("media_type")
    if media_type == "video":
        video_path = f"media/video_{message.video.file_id}.mp4"
        await bot.download_file_by_id(file_id=message.video.file_id, destination=video_path)
        await state.update_data(video=video_path)

        await ForwardingForm.groups.set()
        await message.answer("Video added. Specify the groups (separated by commas)"
                             " where you want to send the message:")


@dp.message_handler(content_types=['document'], state=ForwardingForm.media_type)
async def process_document(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    media_type = user_data.get("media_type")
    if media_type == "file":
        document_path = f"media/document_{message.document.file_id}.{message.document.file_name.split('.')[-1]}"
        await bot.download_file_by_id(file_id=message.document.file_id, destination=document_path)
        await state.update_data(document=document_path)

        await ForwardingForm.groups.set()
        await message.answer("The file has been added. Specify the groups (separated by commas)"
                             " where you want to send the message:")


#
@dp.callback_query_handler(lambda c: c.data == "continue", state=ForwardingForm.media_type)
async def continue_after_media(callback_query: types.CallbackQuery):
    await ForwardingForm.groups.set()
    await callback_query.message.answer("Specify the groups (separated by commas) where you want to send the message:")


@dp.message_handler(state=ForwardingForm.groups)
async def process_groups(message: types.Message, state: FSMContext):
    groups = message.text.split(',')
    await state.update_data(groups=groups)

    await ForwardingForm.delay.set()
    await message.answer("Specify the delay (in seconds) between publications:")


@dp.message_handler(state=ForwardingForm.delay)
async def process_delay(message: types.Message, state: FSMContext):
    try:
        delay = int(message.text)
        await state.update_data(delay=delay)

        new_task = await state.get_data()

        with open("tasks.json", "r") as f:
            tasks = json.load(f) if os.path.getsize("tasks.json") > 0 else []

        tasks.append(new_task)

        with open("tasks.json", "w") as f:
            json.dump(tasks, f)

        await message.reply("The task for sending has been created!")
        await state.finish()

    except ValueError:
        await message.answer("Please enter a valid value for the delay.")


@dp.message_handler(commands=['deactivate_task'])
async def deactivate_task_menu(message: types.Message):
    with open("tasks.json", "r") as f:
        tasks = json.load(f)

    if not tasks:
        await message.reply("There are no active tasks.")
        return

    markup = InlineKeyboardMarkup()
    for idx, task in enumerate(tasks, 1):
        task_text = task['text'][:25]
        btn_text = f"{task_text}..."
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"deactivate_{idx}"))

    await message.reply("Select the task to deactivate:", reply_markup=markup)


@dp.callback_query_handler(lambda c: c.data.startswith('deactivate_'))
async def process_deactivate(callback_query: types.CallbackQuery):
    idx_to_delete = int(callback_query.data.split('_')[-1]) - 1

    with open("tasks.json", "r") as f:
        tasks = json.load(f)

    if 0 <= idx_to_delete < len(tasks):
        deleted_task = tasks.pop(idx_to_delete)
        with open("tasks.json", "w") as f:
            json.dump(tasks, f)
        await callback_query.message.edit_text(f"Task {idx_to_delete + 1} deactivated.")
    else:
        await callback_query.message.edit_text("Error when deactivating a task.")



async def send_messages():
    await asyncio.sleep(10)
    try:
        print('attempt')
        while True:
            with open("tasks.json", "r") as f:
                tasks = json.load(f)

            for task in tasks:
                text = task['text']
                photo_path = task.get('photo')
                video_path = task.get('video')
                document_path = task.get('document')
                delay = task['delay']
                groups = task['groups']

                if 'next_publication_time' not in task:
                    task['next_publication_time'] = (datetime.datetime.now() + datetime.timedelta(seconds=delay)).strftime(
                        '%Y-%m-%d %H:%M:%S')

                next_publication_time = datetime.datetime.strptime(task['next_publication_time'], '%Y-%m-%d %H:%M:%S')

                if datetime.datetime.now() >= next_publication_time:
                    for group in groups:
                        entity = await client.get_input_entity(group)

                        if text and photo_path is None and video_path is None and document_path is None:
                            await client.send_message(entity, text)
                        if photo_path:
                            await client.send_file(entity, photo_path, caption=text)
                        if video_path:
                            await client.send_file(entity, video_path, caption=text)
                        if document_path:
                            await client.send_file(entity, document_path, caption=text)

                    next_publication_time += datetime.timedelta(seconds=delay)
                    task['next_publication_time'] = next_publication_time.strftime('%Y-%m-%d %H:%M:%S')

            with open("tasks.json", "w") as f:
                json.dump(tasks, f)

            await asyncio.sleep(10)
    except Exception as e:
        print(e)
        await asyncio.sleep(30)


asyncio.get_event_loop().create_task(send_messages())

# --- Running both in separate threads ---
if __name__ == '__main__':
    with client:
        executor.start_polling(dp, skip_updates=True)
        client.run_until_disconnected()

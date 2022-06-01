import requests
from telegram.ext import CommandHandler
from telegram import InlineKeyboardMarkup
from .vimeo import vimdown

from bot import Interval, INDEX_URL, BUTTON_FOUR_NAME, BUTTON_FOUR_URL, BUTTON_FIVE_NAME, BUTTON_FIVE_URL, BUTTON_SIX_NAME, BUTTON_SIX_URL, BLOCK_MEGA_FOLDER, BLOCK_MEGA_LINKS, VIEW_LINK, aria2, get_client,CREDIT
from bot import dispatcher, DOWNLOAD_DIR, download_dict, download_dict_lock, SHORTENER, SHORTENER_API, TAR_UNZIP_LIMIT
from bot.helper.ext_utils import fs_utils, bot_utils
from bot.helper.ext_utils.bot_utils import get_mega_link_type
from bot.helper.ext_utils.exceptions import DirectDownloadLinkException, NotSupportedExtractionArchive
from bot.helper.mirror_utils.download_utils.aria2_download import AriaDownloadHelper
from bot.helper.mirror_utils.download_utils.mega_downloader import MegaDownloadHelper
from bot.helper.mirror_utils.download_utils.qbit_downloader import qbittorrent
from bot.helper.mirror_utils.download_utils.direct_link_generator import direct_link_generator
from bot.helper.mirror_utils.download_utils.telegram_downloader import TelegramDownloadHelper
from bot.helper.mirror_utils.status_utils import listeners
from bot.helper.mirror_utils.status_utils.extract_status import ExtractStatus
from bot.helper.mirror_utils.status_utils.tar_status import TarStatus
from bot.helper.mirror_utils.status_utils.upload_status import UploadStatus
from bot.helper.mirror_utils.status_utils.gdownload_status import DownloadStatus
from bot.helper.mirror_utils.upload_utils import gdriveTools
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.message_utils import *
from bot.helper.telegram_helper import button_build
import urllib
import pathlib
import os
import subprocess
import threading
import re
import random
import string
import json
ariaDlManager = AriaDownloadHelper()
ariaDlManager.start_listener()
ckey = '550c6e86fde0d46fdbf440e940a7179fae6dd'
class MirrorListener(listeners.MirrorListeners):
    def __init__(self, bot, update, pswd, isTar=False, extract=False, qbit=False):
        super().__init__(bot, update)
        self.isTar = isTar
        self.extract = extract
        self.qbit = qbit
        self.pswd = pswd

    def onDownloadStarted(self):
        pass

    def onDownloadProgress(self):
        # We are handling this on our own!
        pass

    def clean(self):
        try:
            aria2.purge()
            get_client().torrents_delete(torrent_hashes="all", delete_files=True)
            Interval[0].cancel()
            del Interval[0]
            delete_all_messages()
        except IndexError:
            pass

    def onDownloadComplete(self):
        with download_dict_lock:
            LOGGER.info(f"Download completed: {download_dict[self.uid].name()}")
            download = download_dict[self.uid]
            name = download.name()
            gid = download.gid()
            size = download.size_raw()
            if name is None or self.qbit: # when pyrogram's media.file_name is of NoneType
                name = os.listdir(f'{DOWNLOAD_DIR}{self.uid}')[0]
            m_path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        if self.isTar:
            try:
                with download_dict_lock:
                    download_dict[self.uid] = TarStatus(name, m_path, size)
                path = fs_utils.tar(m_path)
            except FileNotFoundError:
                LOGGER.info('File to archive not found!')
                self.onUploadError('Internal error occurred!!')
                return
        elif self.extract:
            try:
                path = fs_utils.get_base_name(m_path)
                LOGGER.info(f"Extracting: {name}")
                with download_dict_lock:
                    download_dict[self.uid] = ExtractStatus(name, m_path, size)
                pswd = self.pswd
                if pswd is not None:
                    archive_result = subprocess.run(["pextract", m_path, pswd])
                else:
                    archive_result = subprocess.run(["extract", m_path])
                if archive_result.returncode == 0:
                    threading.Thread(target=os.remove, args=(m_path,)).start()
                    LOGGER.info(f"Deleting archive: {m_path}")
                else:
                    LOGGER.warning('Unable to extract archive! Uploading anyway')
                    path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
                LOGGER.info(f'got path: {path}')

            except NotSupportedExtractionArchive:
                LOGGER.info("Not any valid archive, uploading file as it is.")
                path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        else:
            path = f'{DOWNLOAD_DIR}{self.uid}/{name}'
        up_name = pathlib.PurePath(path).name
        up_path = f'{DOWNLOAD_DIR}{self.uid}/{up_name}'
        LOGGER.info(f"Upload Name: {up_name}")
        drive = gdriveTools.GoogleDriveHelper(up_name, self)
        size = fs_utils.get_path_size(up_path)
        upload_status = UploadStatus(drive, size, gid, self)
        with download_dict_lock:
            download_dict[self.uid] = upload_status
        update_all_messages()
        drive.upload(up_name)

    def onDownloadError(self, error):
        error = error.replace('<', ' ')
        error = error.replace('>', ' ')
        with download_dict_lock:
            try:
                download = download_dict[self.uid]
                del download_dict[self.uid]
                fs_utils.clean_download(download.path())
            except Exception as e:
                LOGGER.error(str(e))
                pass
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        msg = f"{uname} your download has been stopped due to: {error}"
        sendMessage(msg, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onUploadStarted(self):
        pass

    def onUploadProgress(self):
        pass

    def onUploadComplete(self, link: str, size, files, folders, typ):
        with download_dict_lock:
            msg = f'<b>📝 Filename :</b> <code>{download_dict[self.uid].name()}</code>\n<b>💽 Size : {size}</b>'
            if os.path.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{download_dict[self.uid].name()}'):
                msg += '\n<b>📦 Type : Folder</b>'
                msg += f'\n<b>📮 SubFolders : {folders}</b>'
                msg += f'\n<b>📂 Files : {files}</b>'
            else:
                msg += f'\n<b>📦 Type : {typ}</b>'
            buttons = button_build.ButtonMaker()
            if SHORTENER is not None and SHORTENER_API is not None:
                link=json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, link)).text)['url']
                link=link['shortLink']
                print(link)
                surl = requests.get(f'https://{SHORTENER}/api/{SHORTENER_API}?s={link}').text
                buttons.buildbutton("⛈️ Drive Link", surl)
            else:
                buttons.buildbutton("⛈️ Drive Link", link)
            LOGGER.info(f'Done Uploading {download_dict[self.uid].name()}')
            if INDEX_URL is not None:
                url_path = requests.utils.quote(f'{download_dict[self.uid].name()}')
                share_url = f'{INDEX_URL}/{url_path}'
                if os.path.isdir(f'{DOWNLOAD_DIR}/{self.uid}/{download_dict[self.uid].name()}'):
                    share_url += '/'
                    if SHORTENER is not None and SHORTENER_API is not None:
                        share_url=json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, urllib.parse.quote(share_url))).text)['url']
                        
                        share_url=share_url['shortLink']
                        print(share_url)
                        siurl = requests.get(f'https://{SHORTENER}/api/{SHORTENER_API}?s={share_url}').text#['shortLink']
                        buttons.buildbutton("🚀 Index Link", siurl)
                    else:
                        buttons.buildbutton("🚀 Index Link", share_url)
                else:
                    share_urls = f'{INDEX_URL}/{url_path}?a=view'
                    if SHORTENER is not None and SHORTENER_API is not None:
                        
                        share_url=json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, urllib.parse.quote(share_url))).text)['url']
                        
                        share_urls=json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, urllib.parse.quote(share_urls))).text)['url']
                        print(share_url,share_urls)
                        share_url=share_url['shortLink']
                        share_urls=share_urls['shortLink']
                        print(share_url,share_urls)
                        
                        siurl = requests.get(f'https://{SHORTENER}/api/{SHORTENER_API}?s={share_url}').text
                        #print(json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, share_urls)).text)['url'],json.loads(requests.get('http://cutt.ly/api/api.php?key={}&short={}'.format(ckey, share_url)).text)['url'])
                        siurls = requests.get(f'https://{SHORTENER}/api/{SHORTENER_API}?s={share_urls}').text
                        buttons.buildbutton("🚀 Index Link", siurl)
                        if VIEW_LINK:
                            buttons.buildbutton("🔎 VIEW YOUR RESULTS 🔍", siurls)
                    else:
                        buttons.buildbutton("🚀 Index Link", share_url)
                        if VIEW_LINK:
                            buttons.buildbutton("🔎 VIEW YOUR RESULTS 🔍", share_urls)
            if BUTTON_FOUR_NAME is not None and BUTTON_FOUR_URL is not None:
                buttons.buildbutton(f"{BUTTON_FOUR_NAME}", f"{BUTTON_FOUR_URL}")
            if BUTTON_FIVE_NAME is not None and BUTTON_FIVE_URL is not None:
                buttons.buildbutton(f"{BUTTON_FIVE_NAME}", f"{BUTTON_FIVE_URL}")
            if BUTTON_SIX_NAME is not None and BUTTON_SIX_URL is not None:
                buttons.buildbutton(f"{BUTTON_SIX_NAME}", f"{BUTTON_SIX_URL}")
            if CREDIT:
                uname=CREDIT
            else:    
             if self.message.from_user.username:
                uname = f"@{self.message.from_user.username}"
             else:
                uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
            if uname is not None:
                msg += f'\n\n<b>📬 Mirrored By : {uname}</b>'
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.uid]
            count = len(download_dict)
        sendMarkup(msg, self.bot, self.update, InlineKeyboardMarkup(buttons.build_menu(2)))
        if count == 0:
            self.clean()
        else:
            update_all_messages()

    def onUploadError(self, error):
        e_str = error.replace('<', '').replace('>', '')
        with download_dict_lock:
            try:
                fs_utils.clean_download(download_dict[self.uid].path())
            except FileNotFoundError:
                pass
            del download_dict[self.message.message_id]
            count = len(download_dict)
        if self.message.from_user.username:
            uname = f"@{self.message.from_user.username}"
        else:
            uname = f'<a href="tg://user?id={self.message.from_user.id}">{self.message.from_user.first_name}</a>'
        if uname is not None:
            men = f'{uname} '
        sendMessage(men + e_str, self.bot, self.update)
        if count == 0:
            self.clean()
        else:
            update_all_messages()

def _mirror(bot, update, isTar=False, extract=False):
    mesg = update.message.text.split('\n')
    message_args = mesg[0].split(' ')
    name_args = mesg[0].split('|')
    qbit = False
    qbitsel = False
    try:
        link = message_args[1]
        if link == "qb" or link == "qbs":
            qbit = True
            if link == "qbs":
                qbitsel = True
            link = message_args[2]
        print(link)
        if link.startswith("|") or link.startswith("pswd: "):
            link = ''
    except IndexError:
        link = ''
    try:
        name = name_args[1]
        name = name.strip()
        if name.startswith("pswd: "):
            name = ''
    except IndexError:
        name = ''
    try:
        ussr = urllib.parse.quote(mesg[1], safe='')
        pssw = urllib.parse.quote(mesg[2], safe='')
    except:
        ussr = ''
        pssw = ''
    if ussr != '' and pssw != '':
        link = link.split("://", maxsplit=1)
        link = f'{link[0]}://{ussr}:{pssw}@{link[1]}'
    pswd = re.search('(?<=pswd: )(.*)', update.message.text)
    if pswd is not None:
      pswd = pswd.groups()
      pswd = " ".join(pswd)
    LOGGER.info(link)
    link = link.strip()
    reply_to = update.message.reply_to_message
    if reply_to is not None:
        file = None
        print(update)
        media_array = [reply_to.document, reply_to.video, reply_to.audio]
        for i in media_array:
            if i is not None:
                file = i
                break

        if not bot_utils.is_url(link) and not bot_utils.is_magnet(link) or len(link) == 0:
            if file is not None:
                if file.mime_type != "application/x-bittorrent":
                    listener = MirrorListener(bot, update, pswd, isTar, extract)
                    tg_downloader = TelegramDownloadHelper(listener)
                    ms = update.message
                    tg_downloader.add_download(ms, f'{DOWNLOAD_DIR}{listener.uid}/', name)
                    return
                else:
                    if qbit:
                        file.get_file().download(custom_path=f"/usr/src/app/{file.file_name}")
                        link = f"/usr/src/app/{file.file_name}"
                    else:
                        link = file.get_file().file_path

    if not bot_utils.is_url(link) and not bot_utils.is_magnet(link):
        sendMessage('No download source provided', bot, update)
        return

    try:
        link = direct_link_generator(link)
    except DirectDownloadLinkException as e:
        LOGGER.info(e)
        if "ERROR:" in str(e):
            sendMessage(f"{e}", bot, update)
            return
        if "Youtube" in str(e):
            sendMessage(f"{e}", bot, update)
            return

    listener = MirrorListener(bot, update, pswd, isTar, extract, qbit)

    if bot_utils.is_gdrive_link(link):
        if not isTar and not extract:
            sendMessage(f"Use /{BotCommands.CloneCommand} to clone Google Drive file/folder\nUse /{BotCommands.TarMirrorCommand} to make tar of Google Drive folder\nUse /{BotCommands.UnzipMirrorCommand} to extracts archive Google Drive file", bot, update)
            return
        res, size, name, files = gdriveTools.GoogleDriveHelper().clonehelper(link)
        if res != "":
            sendMessage(res, bot, update)
            return
        if TAR_UNZIP_LIMIT is not None:
            LOGGER.info(f'Checking File/Folder Size')
            limit = TAR_UNZIP_LIMIT
            limit = limit.split(' ', maxsplit=1)
            limitint = int(limit[0])
            msg = f'Failed, Tar/Unzip limit is {TAR_UNZIP_LIMIT}.\nYour File/Folder size is {get_readable_file_size(size)}.'
            if 'G' in limit[1] or 'g' in limit[1]:
                if size > limitint * 1024**3:
                    sendMessage(msg, listener.bot, listener.update)
                    return
            elif 'T' in limit[1] or 't' in limit[1]:
                if size > limitint * 1024**4:
                    sendMessage(msg, listener.bot, listener.update)
                    return
        LOGGER.info(f"Download Name : {name}")
        drive = gdriveTools.GoogleDriveHelper(name, listener)
        gid = ''.join(random.SystemRandom().choices(string.ascii_letters + string.digits, k=12))
        download_status = DownloadStatus(drive, size, listener, gid)
        with download_dict_lock:
            download_dict[listener.uid] = download_status
        sendStatusMessage(update, bot)
        drive.download(link)

    elif bot_utils.is_mega_link(link):
        link_type = get_mega_link_type(link)
        if link_type == "folder" and BLOCK_MEGA_FOLDER:
            sendMessage("Mega folder are blocked!", bot, update)
        elif BLOCK_MEGA_LINKS:
            sendMessage("Mega links are blocked!", bot, update)
        else:
            mega_dl = MegaDownloadHelper()
            mega_dl.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener)

    elif qbit and (bot_utils.is_magnet(link) or os.path.exists(link)):
        qbit = qbittorrent()
        qbit.add_torrent(link, f'{DOWNLOAD_DIR}{listener.uid}/', listener, qbitsel)

    else:
        ariaDlManager.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener, name)
        sendStatusMessage(update, bot)
def vmirror(update, context):
    mesg = update.message.text.split(' ', maxsplit=1)
    try:
     message_args=mesg[1].split('|')
    except IndexError:
        sendMessage('No download source provided', bot, update)
        return
    vlink=message_args[0]
    try:
     name=message_args[1]
    except IndexError:
        name = ''
    try:
     site=message_args[2]
    except IndexError:
        site = False
    try:
     qul=message_args[3]
    except IndexError:
        qul = 360
    link=vimdown(vlink,site,qul,bot,update)
    listener = MirrorListener(bot, update, pswd='', isTar=False, extract=False, qbit=False)
    ariaDlManager.add_download(link, f'{DOWNLOAD_DIR}/{listener.uid}/', listener, name)
    sendStatusMessage(update, bot)
def mirror(update, context):
    _mirror(context.bot, update)


def tar_mirror(update, context):
    _mirror(context.bot, update, True)


def unzip_mirror(update, context):
    _mirror(context.bot, update, extract=True)


mirror_handler = CommandHandler(BotCommands.MirrorCommand, mirror,
                                filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
tar_mirror_handler = CommandHandler(BotCommands.TarMirrorCommand, tar_mirror,
                                    filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
unzip_mirror_handler = CommandHandler(BotCommands.UnzipMirrorCommand, unzip_mirror,
                                      filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
vmirror_handler = CommandHandler(BotCommands.VmirrorCommand, vmirror,
                                      filters=CustomFilters.authorized_chat | CustomFilters.authorized_user, run_async=True)
dispatcher.add_handler(mirror_handler)
dispatcher.add_handler(tar_mirror_handler)
dispatcher.add_handler(unzip_mirror_handler)
dispatcher.add_handler(vmirror_handler)

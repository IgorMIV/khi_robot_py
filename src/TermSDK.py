# -*- coding: utf-8 -*-
"""
TermSDK.py
由 C# KhiSDK.TermSDK 转换而来。
依赖同目录下的 TermSocket.py 和 TagInfo.py。
"""

import enum
import os
import threading
import time
from pathlib import Path

try:
    from .TermSocket import TermSocket, TermErrorEventHandlerArgs
    from .TagInfo import TagInfo, InfoSys
except ImportError:
    from TermSocket import TermSocket, TermErrorEventHandlerArgs
    from TagInfo import TagInfo, InfoSys


class FileOperatorState(enum.IntEnum):
    Step0None = 0
    Step1StartRead = 1
    Step2StartWrite = 2
    Step3Reading = 3
    Step4Writing = 4
    Step5Over = 5


class FileReadType(enum.IntEnum):
    From0Memory = 0
    From1File = 1


class FileWriteType(enum.IntEnum):
    To0Memory = 0
    To1File = 1


class StepCtrl(enum.IntEnum):
    IsCtrlInit = 0
    IsEnquired = 1
    IsStartOfText = 2
    IsDataStart = 3


class BackInfoEventHandlerArgs:
    def __init__(self, backInfoText):
        self.backInfo = backInfoText


class TermSDK:
    """机器人控制器 SDK。回显事件通过 add_back_view_handler 注册。"""

    def __init__(self):
        self.BackViewText = []
        self.mOperState = FileOperatorState.Step0None
        self.mFileRead = FileReadType.From1File
        self.mFileWrite = FileWriteType.To1File

        self.recvDataArray = []
        self.rbInfoSys = None
        self.workDir = os.getcwd()
        self.enCode = "gb2312"

        self.backInfoBtyeArray = bytearray()
        self.recvWaitting = False
        self.escSeqMode = False
        self.loadFileDataArray = []
        self.saveFileDataArray = []
        self.AllowUpdateBackInfo = False
        self.mSaveFileName = bytearray()

        self.TimerInterval = 100
        self.rTerm = None
        self.rtTermMark = "KrTerm"
        self.rtIpAddress = "localhost"
        self.rtPortNum = 9105

        self._poll_thread = None
        self._poll_stop = threading.Event()
        self._poll_lock = threading.RLock()
        self._save_load_step = StepCtrl.IsCtrlInit
        self._save_load_ctrl = 0
        self._save_load_data = bytearray()

    # ------------------------- 事件 -------------------------
    def add_back_view_handler(self, handler):
        if callable(handler) and handler not in self.BackViewText:
            self.BackViewText.append(handler)

    def remove_back_view_handler(self, handler):
        if handler in self.BackViewText:
            self.BackViewText.remove(handler)

    def _raise_back_view(self, text):
        args = BackInfoEventHandlerArgs(text)
        for handler in list(self.BackViewText):
            try:
                handler(self, args)
            except Exception:
                pass

    def PrintTagMessage(self, tagText=None):
        if tagText is None:
            text = bytes(self.backInfoBtyeArray).decode(self.enCode, errors="replace")
            if self.AllowUpdateBackInfo:
                self._raise_back_view(text)
            self.backInfoBtyeArray.clear()
        else:
            self._raise_back_view(tagText)

    def RecviceSocketError(self, sender, eventArgs):
        self.PrintTagMessage(eventArgs.msgText + "\r\n")

    # ------------------------- 连接及命令 -------------------------
    def AsConnect(self):
        if self.rTerm is None:
            self.rTerm = TermSocket()
            self.rTerm.add_error_handler(self.RecviceSocketError)
            self.rTerm.IPAddress = self.rtIpAddress
            self.rTerm.PortNo = self.rtPortNum
            self.rTerm.Encode = self.enCode

        if not self.rTerm.Connected:
            if not self.rTerm.Connect(False):
                return False

        self.AllowUpdateBackInfo = False
        if not self.GetRobotTag():
            return False

        self._start_polling()
        return True

    def AsDisConnect(self):
        self._stop_polling()
        if self.rTerm is None:
            return True
        self.rTerm.remove_error_handler(self.RecviceSocketError)
        result = self.rTerm.Disconnect(True)
        self.rTerm = None
        return result

    def CmdSendEx(self, command):
        if self.rTerm is None or not self.Connected:
            return
        self.AllowUpdateBackInfo = True
        cmd = command.strip()
        check_str = cmd.upper()

        if check_str.startswith("IO"):
            send_cmd = None
            if len(check_str) == 2:
                send_cmd = cmd + "\n\n"
            io_str = check_str.replace(" ", "").replace("IO", "")
            if len(io_str) > 0 and io_str.isdigit():
                send_cmd = cmd + "\n\n"
            if send_cmd is not None:
                self.rTerm.TermPut(send_cmd)
                self.PrintTagMessage(command)
                return
        elif (check_str.startswith("SA") or check_str.startswith("SAV")
              or check_str.startswith("SAVE")):
            # 原 C# 代码此分支未实现
            return
        elif (check_str.startswith("LO") or check_str.startswith("LOA")
              or check_str.startswith("LOAD")):
            # 原 C# 代码此分支未实现
            return

    # ------------------------- 文件读写 -------------------------
    def FileRead(self, readPath):
        result = []
        with open(readPath, "r", encoding=self.enCode, errors="strict", newline="") as stream:
            current = ""
            length = 0
            max_length = 504
            for line in stream:
                # 对应 StreamReader.ReadLine()，统一按 CRLF 重新拼接
                line = line.rstrip("\r\n")
                if current == "":
                    current = line + "\r\n"
                    length = len(current)
                    continue
                length += len(line)
                if length <= max_length:
                    current += line + "\r\n"
                    length = len(current)
                else:
                    result.append(current)
                    current = line + "\r\n"
                    length = len(current)
            if current != "":
                result.append(current)
        return result

    def FileSave(self, dataArray, savePath):
        try:
            with open(savePath, "w", encoding=self.enCode, newline="") as stream:
                for data in dataArray:
                    stream.write(bytes(data).decode(self.enCode))
            return True
        except Exception:
            return False

    def SetSaveLoadDataStrem(self, fileName, modeByte):
        name = bytes(fileName).decode(self.enCode)
        path = os.path.join(self.workDir, name)

        if modeByte == 65:
            if self.mFileRead == FileReadType.From1File:
                if os.path.isfile(path):
                    self.loadFileDataArray = self.FileRead(path)
                else:
                    if self.AllowUpdateBackInfo:
                        self.PrintTagMessage("[File Read Error !]\r\n")
                        self.PrintTagMessage(path + "\r\n")
                    return False

        elif modeByte == 66:
            save_result = self.FileSave(self.saveFileDataArray, path)
            if not save_result and self.AllowUpdateBackInfo:
                self.PrintTagMessage("[File Write Error !]\r\n")
                self.PrintTagMessage(path + "\r\n")
            return save_result
        return True

    def GetRobotTag(self, timeout=15.0):
        if self.rTerm is None or not self.rTerm.Connected:
            return False

        self.rTerm.TermPut("SAVE/ROB rob.gettag\n")
        self.mOperState = FileOperatorState.Step0None
        self.saveFileDataArray.clear()
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            self.SocketSaveLoad(0)
            if (self.mOperState == FileOperatorState.Step5Over
                    and 62 in self.backInfoBtyeArray):
                self.rTerm.Clear()
                break
            time.sleep(0.005)
        else:
            return False

        data_lines = []
        for item in self.saveFileDataArray:
            data_lines.append(bytes(item).decode(self.enCode, errors="replace").replace("\r\n", ""))

        try:
            self.rbInfoSys = TagInfo().GetSysData(data_lines)
            self.enCode = self._encoding_for_locale(self.rbInfoSys.language)
            self.rTerm.Encode = self.enCode
        except Exception as ex:
            self.PrintTagMessage("解析机器人信息失败：" + str(ex) + "\r\n")
            return False

        self.mOperState = FileOperatorState.Step0None
        self.saveFileDataArray.clear()
        return True

    @staticmethod
    def _encoding_for_locale(locale_name):
        # 对应 C# CultureInfo.TextInfo.ANSICodePage 的常用语言映射
        mapping = {
            "ja-JP": "cp932",
            "en-US": "cp1252",
            "it-IT": "cp1252",
            "fr-FR": "cp1252",
            "de-DE": "cp1252",
            "zh-CN": "gb2312",
            "ko-KR": "cp949",
            "pl-PL": "cp1250",
            "es-ES": "cp1252",
            "nl-NL": "cp1252",
        }
        return mapping.get(locale_name, "gb2312")

    # ------------------------- 接收轮询 -------------------------
    def _start_polling(self):
        if self._poll_thread and self._poll_thread.is_alive():
            return
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="TermSDK-Poll", daemon=True
        )
        self._poll_thread.start()

    def _stop_polling(self):
        self._poll_stop.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None

    def _poll_loop(self):
        interval = max(1, self.TimerInterval) / 1000.0
        while not self._poll_stop.is_set():
            try:
                self.RefreshTimerTick()
            except Exception as ex:
                self.PrintTagMessage("接收处理异常：" + str(ex) + "\r\n")
            self._poll_stop.wait(interval)

    def RefreshTimerTick(self, sender=None, event=None):
        if not self.Connected:
            return
        recv_byte = self.rTerm.TermGetByte()
        if recv_byte <= 0:
            self.recvWaitting = True
            return

        self.recvWaitting = False
        if recv_byte in (2, 5, 23):
            self.SocketSaveLoad(recv_byte)
            return
        if recv_byte == 27:
            self.escSeqMode = True
            self.backInfoBtyeArray.clear()
            return

        if self.escSeqMode:
            if recv_byte == 91:
                pass
            elif 48 <= recv_byte <= 57:
                pass
            elif 65 <= recv_byte <= 90:
                self.escSeqMode = False
            return

        self.backInfoBtyeArray.append(recv_byte)
        if recv_byte in (10, 62):
            self.PrintTagMessage()

    # ------------------------- 控制器文件传输协议 -------------------------
    def SocketSaveLoad(self, lastByte=0):
        while True:
            if lastByte:
                recv_byte = lastByte
                lastByte = 0
            else:
                recv_byte = self.rTerm.TermGetByte() if self.rTerm else 0

            if recv_byte == 0:
                return

            if self._save_load_step == StepCtrl.IsCtrlInit:
                if recv_byte == 5:
                    self._save_load_step = StepCtrl.IsEnquired
                else:
                    self.backInfoBtyeArray.append(recv_byte)
                    if recv_byte == 10:
                        self.PrintTagMessage()

            elif self._save_load_step == StepCtrl.IsEnquired:
                if recv_byte == 2:
                    self._save_load_step = StepCtrl.IsStartOfText

            elif self._save_load_step == StepCtrl.IsStartOfText:
                self._save_load_ctrl = recv_byte
                self._save_load_data.clear()
                self._save_load_step = StepCtrl.IsDataStart

            elif self._save_load_step == StepCtrl.IsDataStart:
                if recv_byte != 23:
                    self._save_load_data.append(recv_byte)
                    continue

                data = bytes(self._save_load_data)
                ctrl = self._save_load_ctrl
                self._save_load_data.clear()
                self._save_load_step = StepCtrl.IsCtrlInit

                if ctrl == 65:  # OPEN_READ
                    check_file = self.SetSaveLoadDataStrem(data, 65)
                    if check_file:
                        self.mOperState = FileOperatorState.Step1StartRead
                        self.rTerm.TermPut(bytes((2, 65, 32, 32, 32, 32, 48, 23)))
                    else:
                        self.rTerm.TermPut(bytes((2, 65, 32, 32, 32, 32, 50, 23)))

                elif ctrl == 66:  # OPEN_WRITE
                    self.mSaveFileName = bytearray(data)
                    self.saveFileDataArray = []
                    self.mOperState = FileOperatorState.Step2StartWrite
                    self.rTerm.TermPut(bytes((2, 66, 32, 32, 32, 32, 48, 23)))

                elif ctrl == 67:  # READING
                    self.mOperState = FileOperatorState.Step3Reading
                    send_data = bytearray((2, 67, 32, 32, 32, 32, 48))
                    if not self.loadFileDataArray:
                        send_data.extend((26, 23))
                    else:
                        send_data.extend(self.loadFileDataArray.pop(0).encode(self.enCode))
                        send_data.append(23)
                    self.rTerm.TermPut(send_data)

                elif ctrl == 68:  # WRITING
                    self.mOperState = FileOperatorState.Step4Writing
                    self.saveFileDataArray.append(bytearray(data))

                elif ctrl == 69:  # CLOSE
                    self.rTerm.TermPut(bytes((2, 69, 32, 32, 32, 32, 48, 23)))
                    if (self.mOperState == FileOperatorState.Step4Writing
                            and self.mFileWrite == FileWriteType.To1File):
                        self.SetSaveLoadDataStrem(self.mSaveFileName, 66)
                    self.mOperState = FileOperatorState.Step5Over

                elif ctrl == 70:
                    pass

    # ------------------------- 属性 -------------------------
    @property
    def Connected(self):
        return self.rTerm is not None and self.rTerm.Connected

    @property
    def RecvFinish(self):
        return self.recvWaitting

    @property
    def AutoIPAddress(self):
        return self.rtIpAddress

    @AutoIPAddress.setter
    def AutoIPAddress(self, value):
        self.rtIpAddress = value

    @property
    def AutoPortNo(self):
        return self.rtPortNum

    @AutoPortNo.setter
    def AutoPortNo(self, value):
        self.rtPortNum = int(value)

    @property
    def AutoTermMark(self):
        return self.rtTermMark

    @AutoTermMark.setter
    def AutoTermMark(self, value):
        self.rtTermMark = value

    @property
    def AutoWorkDir(self):
        return self.workDir

    @AutoWorkDir.setter
    def AutoWorkDir(self, value):
        self.workDir = str(value)

    def Close(self):
        return self.AsDisConnect()

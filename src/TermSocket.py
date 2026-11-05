# -*- coding: utf-8 -*-
"""
TermSocket.py
由 C# KhiSDK.TermSocket 转换而来。

依赖：仅 Python 标准库。
默认编码：GB2312
默认地址：localhost:23
"""

import codecs
import datetime
import enum
import queue
import socket
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class TermErrorEventHandlerArgs:
    msgText: str
    dateTime: datetime.datetime


class SequenceKind(enum.IntEnum):
    DisConnected = 0
    Connecting = 1
    ReqTOption = 2
    RecvTOption_IAC = 3
    RecvTOption_SB = 4
    RecvTOption_TERMTYPE = 5
    RecvTOption_SE = 6
    SendTerminalType = 7
    RecvLoginRequest = 8
    SendLoginName = 9
    LoginComplete = 10


class TermSocket:
    # Telnet 命令/选项
    NULL = 0
    LF = 10
    CR = 13
    PROMPT = 62
    SE = 240
    SB = 250
    WILL = 251
    WONT = 252
    DO = 253
    DONT = 254
    IAC = 255
    TERMTYPE = 24

    def __init__(self):
        self.TermError = []       # 错误事件处理器列表；使用 add_error_handler 注册
        self.clientSocket = None
        self.tcpEndpoint = None
        self.IPAddress = "localhost"
        self.PortNo = 23

        self.ConnectTimeout = 5000
        self.RecvTimeout = 3000
        self.SendTimeout = 3000
        self.Encode = "gb2312"

        self.sequenceNo = SequenceKind.DisConnected
        self.firstByte = 0

        self.recvQueue = queue.Queue()
        self.recvLoginReq = bytearray()
        self.lostSockets = []

        self._send_lock = threading.Lock()
        self._connect_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._send_done = threading.Event()
        self._receive_done = threading.Event()
        self._login_done = threading.Event()
        self._recv_prompt_done = threading.Event()
        self._stop_event = threading.Event()
        self._recv_thread = None

    # ------------------------------------------------------------------
    # 事件及内部辅助方法
    # ------------------------------------------------------------------
    def add_error_handler(self, handler):
        """注册错误回调：handler(sender, TermErrorEventHandlerArgs)。"""
        if callable(handler) and handler not in self.TermError:
            self.TermError.append(handler)

    def remove_error_handler(self, handler):
        if handler in self.TermError:
            self.TermError.remove(handler)

    def _send_error_event(self, error):
        message = str(error)
        args = TermErrorEventHandlerArgs(message, datetime.datetime.now())
        for handler in list(self.TermError):
            try:
                handler(self, args)
            except Exception:
                # 与原 C# 一样，不让事件处理器异常影响主流程
                pass

    def _socket_connected(self):
        sock = self.clientSocket
        if sock is None:
            return False
        try:
            return sock.fileno() >= 0
        except OSError:
            return False

    def _reset_events(self):
        self._send_done.clear()
        self._receive_done.clear()
        self._login_done.clear()
        self._recv_prompt_done.clear()

    def _clear_recv_queue(self):
        while True:
            try:
                self.recvQueue.get_nowait()
            except queue.Empty:
                break

    def _send_all(self, data):
        sock = self.clientSocket
        if sock is None:
            raise OSError("Socket 尚未连接")
        with self._send_lock:
            sock.settimeout(self.SendTimeout / 1000.0 if self.SendTimeout > 0 else None)
            sock.sendall(bytes(data))

    # ------------------------------------------------------------------
    # 编码边界检查
    # ------------------------------------------------------------------
    def CheckLastByte(self, data, length=None):
        """检查指定字节范围末尾是否为未完成的双字节字符。"""
        data = bytes(data)
        if length is None:
            length = len(data)
        length = min(max(0, int(length)), len(data))
        if length == 0:
            return False

        encoding = self.Encode
        if not isinstance(encoding, str):
            encoding = getattr(encoding, "name", "gb2312")
        name = encoding.replace("-", "_").upper()

        count = 0
        for value in reversed(data[:length]):
            if name in ("SHIFT_JIS", "SHIFT_JISX0213", "CP932"):
                is_lead = 0x81 <= value <= 0x9F or 0xE0 <= value <= 0xFC
            elif name in ("GB2312", "GB_2312", "GBK", "CP936",
                          "KS_C_5601_1987", "EUC_KR"):
                is_lead = value >= 0x81
            else:
                # 其他编码不进行 C# 原实现中的双字节判断
                return False
            if not is_lead:
                break
            count += 1
        return count % 2 == 1

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------
    def Connect(self, sendError=True):
        self.Disconnect(False)
        self.sequenceNo = SequenceKind.Connecting
        self._stop_event.clear()
        self._reset_events()
        self.recvLoginReq.clear()
        self.firstByte = 0

        try:
            host = str(self.IPAddress).replace("\u3000", "").replace(" ", "")
            infos = socket.getaddrinfo(host, int(self.PortNo), socket.AF_INET,
                                       socket.SOCK_STREAM)
            if not infos:
                raise OSError("无法解析目标主机的 IPv4 地址")
            address = infos[0][4][0]
            self.tcpEndpoint = (address, int(self.PortNo))

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.clientSocket = sock
            sock.settimeout(self.ConnectTimeout / 1000.0 if self.ConnectTimeout > 0 else None)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.connect(self.tcpEndpoint)
            sock.settimeout(self.RecvTimeout / 1000.0 if self.RecvTimeout > 0 else None)

            self.sequenceNo = SequenceKind.ReqTOption
            self._send_all(bytes((self.IAC, self.WILL, self.TERMTYPE)))

            self._recv_thread = threading.Thread(
                target=self._receive_loop, name="TermSocketReceive", daemon=True
            )
            self._recv_thread.start()

            # 与 C# 一样，等待登录完成；ConnectTimeout 单位为毫秒
            completed = self._login_done.wait(
                self.ConnectTimeout / 1000.0 if self.ConnectTimeout > 0 else None
            )
            if completed and self.Connected:
                return True

            self.sequenceNo = SequenceKind.DisConnected
            if sendError:
                self._send_error_event("等待 Telnet 登录提示符超时")
            self.Disconnect(False)
            return False

        except Exception as ex:
            self.sequenceNo = SequenceKind.DisConnected
            if sendError:
                self._send_error_event(ex)
            self.Disconnect(False)
            return False

    def Disconnect(self, sendError=True, lost=False):
        result = True
        self._stop_event.set()
        sock = self.clientSocket
        self.clientSocket = None

        if sock is not None:
            try:
                if lost:
                    if sock not in self.lostSockets:
                        self.lostSockets.append(sock)
                else:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    sock.close()
            except Exception as ex:
                result = False
                if sendError:
                    self._send_error_event(ex)

        self.sequenceNo = SequenceKind.DisConnected
        self._clear_recv_queue()
        self.firstByte = 0
        self._reset_events()
        return result

    def FindConnection(self):
        """先执行系统 ping，再尝试 TCP/Telnet 连接。"""
        host = str(self.IPAddress).replace("\u3000", "").replace(" ", "")
        try:
            # Windows 与 Unix 的 ping 参数不同
            args = (["ping", "-n", "1", "-w", "1000", host]
                    if __import__("os").name == "nt"
                    else ["ping", "-c", "1", "-W", "1", host])
            ping_ok = subprocess.run(
                args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=3
            ).returncode == 0
            if ping_ok and self.Connect(False):
                self.Disconnect()
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # Telnet 接收及登录状态机
    # ------------------------------------------------------------------
    def _receive_loop(self):
        sock = self.clientSocket
        try:
            while not self._stop_event.is_set() and sock is self.clientSocket:
                try:
                    data = sock.recv(1024)
                except socket.timeout:
                    continue
                if not data:
                    break
                for value in data:
                    if self._stop_event.is_set():
                        break
                    self._process_received_byte(value)
                self._receive_done.set()
        except Exception as ex:
            if not self._stop_event.is_set():
                self._send_error_event(ex)
                self._receive_done.set()
                self._recv_prompt_done.set()
        finally:
            self._receive_done.set()
            if sock is self.clientSocket and not self._stop_event.is_set():
                # 远端关闭连接
                self.sequenceNo = SequenceKind.DisConnected

    def _process_received_byte(self, value):
        if self.sequenceNo < SequenceKind.LoginComplete:
            self.recvLoginReq.append(value)
            try:
                text = bytes(self.recvLoginReq).decode(
                    self._encoding_name(), errors="replace"
                )
            except Exception:
                text = ""

            if text.endswith("login: "):
                self.sequenceNo = SequenceKind.SendLoginName
                self._send_request("LoginName")
                return

            if self.sequenceNo == SequenceKind.SendLoginName:
                if value == self.PROMPT:
                    self.sequenceNo = SequenceKind.LoginComplete
                    self.recvQueue.put(value)
                    self._login_done.set()
                return

            # Telnet 选项协商
            if (self.sequenceNo != SequenceKind.LoginComplete and
                    (self.sequenceNo != SequenceKind.RecvTOption_TERMTYPE
                     or value == self.SE)):
                if value <= self.SE:
                    if value == self.SE:
                        if self.sequenceNo == SequenceKind.RecvTOption_TERMTYPE:
                            self.sequenceNo = SequenceKind.SendTerminalType
                            self._send_request("TerminalType")
                            self.sequenceNo = SequenceKind.RecvLoginRequest
                            self.recvLoginReq.clear()
                    elif value == self.TERMTYPE:
                        if self.sequenceNo == SequenceKind.RecvTOption_SB:
                            self.sequenceNo = SequenceKind.RecvTOption_TERMTYPE
                elif value != self.SB:
                    if value == self.DO:
                        self.sequenceNo = SequenceKind.ReqTOption
                    elif value == self.IAC:
                        self.sequenceNo = SequenceKind.RecvTOption_IAC
                elif self.sequenceNo == SequenceKind.RecvTOption_IAC:
                    self.sequenceNo = SequenceKind.RecvTOption_SB
        else:
            self.recvQueue.put(value)
            if value == self.PROMPT:
                self._recv_prompt_done.set()

    def _encoding_name(self):
        if isinstance(self.Encode, str):
            return self.Encode
        return getattr(self.Encode, "name", "gb2312")

    def _send_request(self, request, command=None):
        if request == "ReqTOption":
            data = bytes((self.IAC, self.WILL, self.TERMTYPE))
        elif request == "TerminalType":
            data = bytes((self.IAC, self.SB, self.TERMTYPE, 0)) + b"VT100" + bytes((self.IAC, self.SE))
        elif request == "LoginName":
            data = b"as" + bytes((self.CR, self.LF))
        elif request == "Command":
            data = command
        else:
            return False

        if data is None:
            return False
        try:
            self._send_done.clear()
            self._send_all(data)
            self._send_done.set()
            return True
        except Exception as ex:
            self._send_done.set()
            self._send_error_event(ex)
            return False

    # ------------------------------------------------------------------
    # 接收数据接口
    # ------------------------------------------------------------------
    def Clear(self):
        self._clear_recv_queue()

    def TermGetByte(self):
        if not self._socket_connected():
            return 0
        try:
            return self.recvQueue.get_nowait()
        except queue.Empty:
            return 0

    def TermGetByteArray(self, fullBytes=None):
        if fullBytes is None:
            fullBytes = bytearray()
        if not self._socket_connected():
            return False if not isinstance(fullBytes, bytearray) else (False, fullBytes)

        while True:
            try:
                value = self.recvQueue.get_nowait()
            except queue.Empty:
                break
            if value == 0:
                break
            if hasattr(fullBytes, "append"):
                fullBytes.append(value)
            else:
                fullBytes.append(value)
        if isinstance(fullBytes, bytearray):
            return (len(fullBytes) > 0, fullBytes)
        return len(fullBytes) > 0

    def TermGetChar(self, buf=None):
        value = self.TermGetByte() if self.Connected else 0
        if isinstance(buf, list):
            if buf:
                buf[0] = value
            else:
                buf.append(value)
        return value > 0 if buf is None else (value > 0, value)

    def TermGetString(self):
        if not self._socket_connected():
            return ""
        data = bytearray()
        while True:
            try:
                value = self.recvQueue.get_nowait()
            except queue.Empty:
                break
            if value == 0:
                break
            data.append(value)

        if self.firstByte:
            data.insert(0, self.firstByte)
            self.firstByte = 0

        if data and self.CheckLastByte(data):
            self.firstByte = data[-1]
            del data[-1]

        return bytes(data).decode(self._encoding_name(), errors="replace")

    # ------------------------------------------------------------------
    # 发送数据接口
    # ------------------------------------------------------------------
    def TermPut(self, senddata):
        if not self.Connected:
            return False
        try:
            if isinstance(senddata, str):
                data = senddata.encode(self._encoding_name())
            elif isinstance(senddata, int):
                data = bytes((senddata & 0xFF,))
            elif isinstance(senddata, (bytes, bytearray, memoryview)):
                data = bytes(senddata)
            else:
                # 兼容 byte/char 列表
                if senddata and isinstance(senddata[0], str):
                    data = "".join(senddata).encode(self._encoding_name())
                else:
                    data = bytes(senddata)
            return self._send_request("Command", data)
        except Exception as ex:
            self._send_error_event(ex)
            return False

    # ------------------------------------------------------------------
    # 提示符等待
    # ------------------------------------------------------------------
    def PromptReset(self):
        self._recv_prompt_done.clear()

    def PromptWait(self, millisecondsTimeout, exitContext=False):
        if not self.Connected:
            return False
        result = self._recv_prompt_done.wait(
            millisecondsTimeout / 1000.0 if millisecondsTimeout >= 0 else None
        )
        self._recv_prompt_done.clear()
        return result

    # ------------------------------------------------------------------
    # 属性兼容接口
    # ------------------------------------------------------------------
    @property
    def Connected(self):
        return self._socket_connected() and self.sequenceNo == SequenceKind.LoginComplete

    @property
    def Socket(self):
        return self.clientSocket

    @property
    def TCPEndPoint(self):
        return self.tcpEndpoint

    def __del__(self):
        try:
            self.Disconnect(False)
            for sock in self.lostSockets:
                try:
                    sock.close()
                except Exception:
                    pass
            self.lostSockets.clear()
        except Exception:
            pass


if __name__ == "__main__":
    # 简单连接示例：按实际终端地址和端口修改
    term = TermSocket()
    term.IPAddress = "127.0.0.1"
    term.PortNo = 23

    def on_error(sender, args):
        print("[TermSocket]", args.dateTime, args.msgText)

    term.add_error_handler(on_error)

    if term.Connect():
        print("连接成功")
        term.TermPut("help\r\n")
        time.sleep(0.5)
        print(term.TermGetString())
        term.Disconnect()
    else:
        print("连接失败")

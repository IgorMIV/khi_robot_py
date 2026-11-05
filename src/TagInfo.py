# -*- coding: utf-8 -*-
"""TagInfo.py：解析机器人控制器返回的系统标签信息。"""

from dataclasses import dataclass


@dataclass
class InfoSys:
    mainNum: str = ""
    subNum: str = ""
    axesNum: str = ""
    serialNo: str = ""
    Name: str = ""
    language: str = "zh-CN"


class TagInfo:
    def GetSysData(self, sysData):
        infoSys = InfoSys()
        select_num = -1
        option_array = None

        for line in sysData:
            upper = line.upper()
            parts = upper.split()

            if upper.startswith("ZROBOT.TYPE"):
                # 保留 C# 源代码字段位置定义
                if len(parts) > 6:
                    infoSys.mainNum = parts[1]
                    infoSys.subNum = parts[2]
                    infoSys.axesNum = parts[3]
                    infoSys.serialNo = parts[4]
                    infoSys.Name = parts[6]

            if upper.startswith("ZLANGUAGE"):
                if "OFF" in upper:
                    select_num = 1
                if "ON" in upper:
                    select_num = 2

            if upper.startswith("LANG_NO"):
                option_array = parts

            if upper.startswith("ZNOW_LANGUAGE"):
                if len(parts) > 1:
                    select_num = int(parts[1])

            if upper.startswith("ZLANG_NO"):
                option_array = parts

            if upper.startswith("LANGUAGE"):
                if len(parts) > 1:
                    select_num = int(parts[1])

        if option_array is None:
            language_num = select_num + 1
            infoSys.language = self.GetLocaleFromLangID(language_num, True)
        else:
            if select_num < 0 or select_num >= len(option_array):
                raise ValueError("语言选项索引超出范围：%s" % select_num)
            language_num = int(option_array[select_num])
            infoSys.language = self.GetLocaleFromLangID(language_num, False)

        return infoSys

    def GetLocaleFromLangID(self, langID, isNewType):
        if isNewType:
            mapping = {
                1: "ja-JP", 2: "en-US", 3: "it-IT", 4: "fr-FR",
                5: "de-DE", 6: "zh-CN", 7: "ko-KR", 9: "pl-PL",
                10: "es-ES", 11: "nl-NL",
            }
        else:
            mapping = {
                0: "ja-JP", 1: "en-US", 2: "de-DE", 3: "it-IT",
                4: "nl-NL", 6: "fr-FR", 7: "ko-KR", 8: "zh-CN",
                10: "pl-PL", 11: "es-ES",
            }
        return mapping.get(int(langID), "zh-CN")

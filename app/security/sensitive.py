import re

SENSITIVE_KEYWORDS = {
    "身份证",
    "手机号",
    "手机号码",
    "银行卡",
    "密码",
    "薪资",
    "工资",
    "住址",
    "家庭地址",
    "客户名单",
    "合同原件",
    "财务明细",
    "机密",
    "保密",
}

_FULL_WIDTH_TO_HALF = str.maketrans(
    "０１２３４５６７８９" "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ" "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789" "ABCDEFGHIJKLMNOPQRSTUVWXYZ" "abcdefghijklmnopqrstuvwxyz",
)
_WHITESPACE_RE = re.compile(r"[\s\u3000]+")


def _normalize(text: str) -> str:
    result = text.translate(_FULL_WIDTH_TO_HALF)
    result = _WHITESPACE_RE.sub("", result)
    return result.lower()


def is_sensitive_question(text: str) -> bool:
    content = _normalize(text.strip())
    return any(keyword in content for keyword in SENSITIVE_KEYWORDS)

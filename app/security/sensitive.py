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


def is_sensitive_question(text: str) -> bool:
    content = text.strip().lower()
    return any(keyword in content for keyword in SENSITIVE_KEYWORDS)

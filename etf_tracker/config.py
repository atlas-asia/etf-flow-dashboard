# -*- coding: utf-8 -*-
"""ETF分类配置"""

# 分类体系定义
# 每个子分类包含: (关键词列表, 排除关键词列表)
# 匹配时按顺序检查，优先匹配更具体的关键词

ETF_CLASSIFICATION = {
    "宽基ETF": {
        "上证50": {
            "keywords": ["上证50", "50ETF"],
            "exclude": ["500", "50A", "央企50", "科创50", "科创", "创业板50", "深证50", "中证A50", "A50ETF", "国证50"]
        },
        "科创板": {
            "keywords": ["科创"],
            "exclude": []
        },
        "中证A500": {
            "keywords": ["A500"],
            "exclude": []
        },
        "中证2000": {
            "keywords": ["2000"],
            "exclude": []
        },
        "中证500": {
            "keywords": ["500"],
            "exclude": ["A500", "5000"]
        },
        "沪深300": {
            "keywords": ["300"],
            "exclude": ["3000"]
        },
        "中证1000": {
            "keywords": ["1000"],
            "exclude": ["2000"]
        }
    },
    "行业ETF": {
        "半导体": {
            "keywords": ["半导体", "芯片"],
            "exclude": []
        },
        "券商": {
            "keywords": ["券商", "证券"],
            "exclude": []
        },
        "计算机": {
            "keywords": ["计算机", "信息技术"],
            "exclude": []
        },
        "互联网": {
            "keywords": ["互联网"],
            "exclude": []
        },
        "农业": {
            "keywords": ["农业", "养殖", "种业"],
            "exclude": []
        },
        "能源": {
            "keywords": ["能源", "煤炭", "石油"],
            "exclude": ["新能源"]
        },
        "基建": {
            "keywords": ["基建", "建筑材料"],
            "exclude": []
        },
        "电子": {
            "keywords": ["电子"],
            "exclude": []
        },
        "金融地产": {
            "keywords": ["金融地产"],
            "exclude": []
        },
        "家电": {
            "keywords": ["家电"],
            "exclude": []
        },
        "金融": {
            "keywords": ["金融"],
            "exclude": ["金融地产"]
        },
        "TMT": {
            "keywords": ["TMT"],
            "exclude": []
        },
        "钢铁": {
            "keywords": ["钢铁"],
            "exclude": []
        },
        "光伏": {
            "keywords": ["光伏"],
            "exclude": []
        },
        "有色金属": {
            "keywords": ["有色", "有色金属"],
            "exclude": []
        },
        "新能源": {
            "keywords": ["新能源", "碳中和"],
            "exclude": []
        },
        "航空航天": {
            "keywords": ["航空航天", "航天"],
            "exclude": []
        },
        "制造业": {
            "keywords": ["制造", "高端制造"],
            "exclude": ["智能制造"]
        },
        "电力": {
            "keywords": ["电力"],
            "exclude": []
        },
        "机器人": {
            "keywords": ["机器人"],
            "exclude": []
        },
        "消费": {
            "keywords": ["消费"],
            "exclude": []
        },
        "人工智能": {
            "keywords": ["人工智能", "AI智能"],
            "exclude": []
        },
        "锂电": {
            "keywords": ["锂电池", "锂电", "电池"],
            "exclude": []
        },
        "银行": {
            "keywords": ["银行"],
            "exclude": []
        },
        "军工": {
            "keywords": ["军工", "国防"],
            "exclude": []
        },
        "化工": {
            "keywords": ["化工", "化学"],
            "exclude": []
        },
        "通信": {
            "keywords": ["通信"],
            "exclude": []
        },
        "医药": {
            "keywords": ["医药", "医疗", "创新药", "生物", "疫苗", "健康"],
            "exclude": []
        }
    },
    "风格ETF": {
        "价值": {
            "keywords": ["价值"],
            "exclude": []
        },
        "科技": {
            "keywords": ["科技"],
            "exclude": ["科技创新", "恒生科技"]
        },
        "地域": {
            "keywords": ["地域"],
            "exclude": []
        },
        "成长": {
            "keywords": ["成长"],
            "exclude": []
        },
        "国企": {
            "keywords": ["国企", "央企"],
            "exclude": []
        },
        "红利": {
            "keywords": ["红利", "高股息", "股息"],
            "exclude": []
        }
    },
    "港股ETF": {
        "电力": {
            "keywords": ["电力"],
            "exclude": []
        },
        "服务": {
            "keywords": ["服务"],
            "exclude": []
        },
        "消费": {
            "keywords": ["消费"],
            "exclude": []
        },
        "汽车": {
            "keywords": ["汽车"],
            "exclude": []
        },
        "央企": {
            "keywords": ["央企"],
            "exclude": []
        },
        "高股息": {
            "keywords": ["高股息", "股息"],
            "exclude": []
        },
        "互联网": {
            "keywords": ["互联网", "互联"],
            "exclude": []
        },
        "科技": {
            "keywords": ["科技"],
            "exclude": []
        },
        "金融": {
            "keywords": ["金融"],
            "exclude": []
        },
        "医药": {
            "keywords": ["医药", "医疗", "创新药", "生物", "健康"],
            "exclude": []
        },
        "宽基": {
            "keywords": ["恒生", "恒指", "港股通50", "恒生指数"],
            "exclude": ["恒生科技", "恒生医疗", "恒生医药", "恒生互联网", "恒生互联"]
        }
    }
}

# 港股ETF识别关键词（用于判断ETF是否跟踪港股）
HK_KEYWORDS = ["港股", "恒生", "恒指", "恒科", "中概", "H股", "港股通"]

# 港股ETF子分类的匹配顺序（越具体越优先，科技和互联网在宽基之前检查）
HK_SUBCATEGORY_ORDER = [
    "电力", "服务", "消费", "汽车", "央企", "高股息",
    "互联网", "科技", "金融", "医药", "宽基"
]

# 行业ETF子分类的匹配顺序（越具体越优先）
INDUSTRY_SUBCATEGORY_ORDER = [
    "半导体", "券商", "计算机", "互联网", "农业", "能源", "基建",
    "电子", "金融地产", "家电", "TMT", "钢铁", "光伏", "有色金属",
    "新能源", "航空航天", "制造业", "电力", "机器人", "消费",
    "人工智能", "锂电", "银行", "军工", "化工", "通信", "医药", "金融"
]

# 风格ETF子分类的匹配顺序
STYLE_SUBCATEGORY_ORDER = [
    "价值", "科技", "地域", "成长", "国企", "红利"
]

# 宽基ETF子分类的匹配顺序（注意优先级）
BROAD_SUBCATEGORY_ORDER = [
    "中证A500",   # A500 优先于 500
    "中证2000",   # 2000 优先于 1000
    "中证1000",   # 1000
    "中证500",    # 500
    "沪深300",    # 300
    "科创板",     # 科创 (在50之前检查,避免科创50匹配上证50)
    "上证50"      # 50
]


def classify_etf(name):
    """
    根据ETF名称分类
    返回: (主分类, 子分类) 如 ("宽基ETF", "沪深300") 或 ("其他ETF", "其他")
    """
    if not name:
        return ("其他ETF", "其他")

    # 1. 先检查是否为港股ETF
    is_hk = any(kw in name for kw in HK_KEYWORDS)
    if is_hk:
        for sub_cat in HK_SUBCATEGORY_ORDER:
            sub_config = ETF_CLASSIFICATION["港股ETF"].get(sub_cat, {})
            keywords = sub_config.get("keywords", [])
            exclude = sub_config.get("exclude", [])
            matched = any(kw in name for kw in keywords)
            excluded = any(kw in name for kw in exclude)
            if matched and not excluded:
                return ("港股ETF", sub_cat)
        # 是港股ETF但未匹配到子分类
        return ("港股ETF", "其他港股")

    # 2. 检查宽基ETF
    for sub_cat in BROAD_SUBCATEGORY_ORDER:
        sub_config = ETF_CLASSIFICATION["宽基ETF"].get(sub_cat, {})
        keywords = sub_config.get("keywords", [])
        exclude = sub_config.get("exclude", [])
        matched = any(kw in name for kw in keywords)
        excluded = any(kw in name for kw in exclude)
        if matched and not excluded:
            return ("宽基ETF", sub_cat)

    # 3. 检查行业ETF
    for sub_cat in INDUSTRY_SUBCATEGORY_ORDER:
        sub_config = ETF_CLASSIFICATION["行业ETF"].get(sub_cat, {})
        keywords = sub_config.get("keywords", [])
        exclude = sub_config.get("exclude", [])
        matched = any(kw in name for kw in keywords)
        excluded = any(kw in name for kw in exclude)
        if matched and not excluded:
            return ("行业ETF", sub_cat)

    # 4. 检查风格ETF
    for sub_cat in STYLE_SUBCATEGORY_ORDER:
        sub_config = ETF_CLASSIFICATION["风格ETF"].get(sub_cat, {})
        keywords = sub_config.get("keywords", [])
        exclude = sub_config.get("exclude", [])
        matched = any(kw in name for kw in keywords)
        excluded = any(kw in name for kw in exclude)
        if matched and not excluded:
            return ("风格ETF", sub_cat)

    # 5. 其他ETF
    return ("其他ETF", "其他")

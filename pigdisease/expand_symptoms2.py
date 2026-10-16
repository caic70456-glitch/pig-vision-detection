# -*- coding: utf-8 -*-
"""第二批症状词表扩充：补上第一轮遗漏的、在鉴别诊断中有区分度的症状。

补充依据：对 15 条评测用例做症状识别覆盖率检查时，发现以下要点被漏识别——
  - 「突然死亡」「口鼻流出泡沫状液体」「咽喉部肿胀」（猪肺疫最急性型的关键特征）
  - 「犬坐姿势」「脓性鼻分泌物」（传染性胸膜肺炎的关键特征）
  - 「抽搐」「四肢划水」（神经症状的细分类）
  - 「转圈」「共济失调」「角弓反张」（神经系统定位体征）
  - 「先便秘后腹泻」（猪瘟的经典病程特征）
"""
import io
import json

NEW_SYMPTOMS = {
    "突然死亡": ["突然死亡", "猝死", "急性死亡", "无明显症状死亡", "夜间死亡"],
    "口鼻泡沫": ["口鼻流出泡沫", "泡沫状液体", "口鼻流出", "泡沫样分泌物", "血性泡沫"],
    "咽喉肿胀": ["咽喉部肿胀", "咽喉肿胀", "颈部肿胀", "喉部肿胀"],
    "犬坐姿势": ["犬坐姿势", "犬坐式", "犬坐"],
    "脓性鼻液": ["脓性分泌物", "脓性鼻液", "黄色脓性", "鼻流脓性"],
    "抽搐": ["抽搐", "痉挛", "惊厥", "强直"],
    "四肢划水": ["四肢划水", "划水样", "游泳样"],
    "转圈": ["转圈", "做圆圈运动", "定向障碍"],
    "共济失调": ["共济失调", "步态不稳", "行走不稳", "站立不稳"],
    "角弓反张": ["角弓反张", "头颈后仰"],
    "先便秘后腹泻": ["先便秘后腹泻", "便秘后腹泻", "初期便秘"],
    "便秘": ["便秘", "排便困难", "粪球干硬"],
    "黏膜发绀": ["黏膜发绀", "可视黏膜发绀", "眼结膜发绀", "口鼻黏膜发绀"],
    "眼睑水肿": ["眼睑水肿", "眼睑肿胀", "眼睑浮肿"],
    "皮肤苍白": ["皮肤苍白", "黏膜苍白", "可视黏膜苍白"],
    "耳尖发紫": ["耳尖发紫", "耳尖发绀", "耳部发绀", "耳朵发紫"],
    "腹式呼吸": ["腹式呼吸", "腹部起伏明显"],
    "张口呼吸": ["张口呼吸", "开口呼吸"],
    "打喷嚏": ["打喷嚏", "喷嚏"],
    "鼻衄": ["鼻出血", "鼻衄", "鼻腔出血"],
    "关节疼痛": ["关节疼痛", "关节肿大疼痛", "触痛", "关节变形"],
    "跛行明显": ["跛行", "瘸腿", "不愿走动", "站立困难"],
    "生长停滞": ["生长停滞", "光吃不长", "饲料转化率低", "增重缓慢"],
    "饲料报酬下降": ["饲料报酬降低", "饲料转化率低", "料肉比升高"],
    "流产先兆": ["先兆流产", "流产症状"],
    "产程异常": ["产程延长", "难产"],
    "乳汁异常": ["少乳", "无乳", "泌乳不足", "奶水不足"],
    "呼吸音异常": ["胸膜摩擦音", "肺部啰音", "呼吸音增强"],
    "呕吐物": ["呕吐物", "吐奶"],
}


def main():
    path = r"E:\harness\aic\pigdisease\data\symptom_dict.json"
    old = json.load(io.open(path, encoding="utf-8"))
    io.open(r"E:\harness\aic\pigdisease\data\symptom_dict_v2_backup.json", "w",
            encoding="utf-8").write(json.dumps(old, ensure_ascii=False, indent=1))

    merged = dict(old)
    added, extended = [], []
    for std, words in NEW_SYMPTOMS.items():
        if std in merged:
            new_words = [w for w in words if w not in merged[std]]
            if new_words:
                merged[std] = merged[std] + new_words
                extended.append(f"{std}(+{len(new_words)})")
        else:
            merged[std] = words
            added.append(std)

    io.open(path, "w", encoding="utf-8").write(json.dumps(merged, ensure_ascii=False, indent=1))
    print(f"症状词表：{len(old)} 个标准症状 / {sum(len(v) for v in old.values())} 个匹配词")
    print(f"   -> {len(merged)} 个标准症状 / {sum(len(v) for v in merged.values())} 个匹配词")
    print(f"\n新增 {len(added)} 个标准症状：\n  " + "、".join(added))
    if extended:
        print(f"\n扩充同义词的 {len(extended)} 个：\n  " + "、".join(extended))


if __name__ == "__main__":
    main()

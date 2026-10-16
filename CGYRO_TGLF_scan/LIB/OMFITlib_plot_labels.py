"""English figure text; GUI captions and stored scientific data stay separate."""
from builtins import getattr, len, setattr, sorted, str
from functools import partial
import re


# Extend this table for new built-in labels; do not translate solver keys/data.
ENGLISH_TERMS = {
    '当前 / 导入的 TGLF 文件': 'Imported TGLF input',
    '局部互转的 TGLF 文件': 'Converted TGLF input',
    '本轮生成剖面': 'Generated profile', '当前输入剖面': 'Input profile',
    '频率 / 增长率谱': 'Frequency / growth-rate spectrum',
    '原值': 'Original', '样本': 'Sample', '旧记录': 'legacy',
    '未命名': 'Unnamed', '未知案例': 'Unknown case', '案例': 'Case',
    '输入': 'Input', '剖面': 'Profile', '扫描': 'Scan', '结果': 'Result',
    '物种': 'Species', '主离子': 'Main ion', '杂质': 'Impurity',
    '电子': 'Electron', '离子': 'Ion', '半径': 'Radius',
    '温度': 'Temperature', '密度': 'Density', '梯度': 'Gradient',
    '增长率': 'Growth rate', '频率': 'Frequency', '通量': 'Flux',
    '时间': 'Time', '参考': 'Reference', '基准': 'Baseline',
    '开启': 'On', '关闭': 'Off', '无数据': 'No data',
}
_TERMS = re.compile('|'.join(re.escape(value) for value in sorted(ENGLISH_TERMS, key=len, reverse=True)))
_CJK = re.compile(r'[\u2e80-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff01-\uffef\U00020000-\U0003134f]+')
_PUNCTUATION = str.maketrans({
    '（': '(', '）': ')', '【': '[', '】': ']', '，': ',', '；': ';',
    '：': ':', '。': '.', '、': ', ', '“': '"', '”': '"',
    '‘': "'", '’': "'", '　': ' ',
})


def english_label(value, aliases):
    """Translate known captions; give opaque user text a distinct English ID."""
    text = str(value).translate(_PUNCTUATION)
    text = _TERMS.sub(lambda match: ENGLISH_TERMS[match.group()], text)

    def identifier(match):
        original = match.group()
        if original not in aliases:
            aliases[original] = 'Label {}'.format(len(aliases) + 1)
        return aliases[original]

    return _CJK.sub(identifier, text)


def _english_text(function, text, aliases, *args, **kwargs):
    current = text.get_text()
    translated = english_label(current, aliases)
    if translated != current:
        text.set_text(translated)
    return function(*args, **kwargs)


def apply_english_labels(figure):
    """Also handle tick formatters and labels changed after the initial draw."""
    from matplotlib.text import Text
    aliases = getattr(figure, '_project_label_aliases', None)
    if aliases is None:
        aliases = {}
        figure._project_label_aliases = aliases
    figure.set_label(english_label(figure.get_label(), aliases))
    for text in figure.findobj(match=Text):
        translated = english_label(text.get_text(), aliases)
        if translated != text.get_text():
            text.set_text(translated)
        for name in ('draw', 'get_window_extent'):
            saved = '_project_english_' + name
            original = getattr(text, saved, None)
            if original is None:
                original = getattr(text, name)
                setattr(text, saved, original)
                setattr(text, name, partial(_english_text, original, text, aliases))

"""Skill 加载器测试：解析 / 选择 / 注入。"""

import yroll.server.chat as chat_mod
from yroll.harness.skills import inject_prompt, load_skills, select_skills


def test_load_real_skills():
    skills = load_skills()  # 仓库根目录 skills/
    names = {s.name for s in skills}
    assert "silence-cleanup" in names
    assert "loudness-balance" in names
    s = next(s for s in skills if s.name == "silence-cleanup")
    assert s.tools == ["silence_remove"]
    assert "什么时候做" in s.body


def test_parse_without_frontmatter(tmp_path):
    (tmp_path / "plain").mkdir()
    (tmp_path / "plain" / "SKILL.md").write_text("纯正文，没有 frontmatter", encoding="utf-8")
    skills = load_skills(tmp_path)
    assert len(skills) == 1
    assert skills[0].name == "plain"
    assert skills[0].body == "纯正文，没有 frontmatter"


def test_load_missing_dir(tmp_path):
    assert load_skills(tmp_path / "nope") == []


def test_select_by_keyword():
    skills = load_skills()
    picked = select_skills("这段停顿太多了，帮我剪掉空白", skills)
    assert any(s.name == "silence-cleanup" for s in picked)
    picked2 = select_skills("BGM 声音太大盖过人声", skills)
    assert any(s.name == "loudness-balance" for s in picked2)
    # 无关消息不加载任何 Skill
    assert select_skills("帮我把时间轴移到 3 秒", skills) == []


def test_inject_prompt():
    skills = load_skills()
    picked = select_skills("停顿太多", skills)
    out = inject_prompt("BASE", picked)
    assert out.startswith("BASE")
    assert "已加载的领域经验" in out
    assert "去停顿" in out
    assert inject_prompt("BASE", []) == "BASE"


def test_build_system_cached(monkeypatch):
    chat_mod._skills_cache = None
    s1 = chat_mod.build_system("停顿太多")
    s2 = chat_mod.build_system("音量太小")
    assert "去停顿" in s1
    assert "音量平衡" in s2
    assert chat_mod._skills_cache is not None


def test_select_new_skills():
    skills = load_skills()
    assert any(s.name == "watermark-removal"
               for s in select_skills("右上角有个台标，帮我去掉水印", skills))
    assert any(s.name == "noise-reduction"
               for s in select_skills("这段底噪很大，有电流声", skills))


class _FakeResp:
    def __init__(self, text):
        self.choices = [type("C", (), {"message": type("M", (), {"content": text})()})()]


class _FakeClient:
    """模拟 OpenAI 兼容 client，返回固定路由结果。"""
    def __init__(self, text):
        self._text = text
        self.chat = type("Chat", (), {
            "completions": type("Comp", (), {"create": lambda s, **kw: _FakeResp(text)})()})()


def test_select_skills_llm():
    from yroll.harness.skills import select_skills_llm

    skills = load_skills()
    # LLM 语义路由：消息里没有 bigram 能匹配的关键词也能选对
    client = _FakeClient('{"skills":["noise-reduction"]}')
    picked = select_skills_llm("声音听起来毛毛的", skills, client=client)
    assert [s.name for s in picked] == ["noise-reduction"]

    # LLM 说无关 → 降级 bigram（bigram 也没有就空）
    client = _FakeClient('{"skills":[]}')
    assert select_skills_llm("今天天气不错", skills, client=client) == []

    # LLM 输出坏 JSON → 降级 bigram
    client = _FakeClient("这不是JSON")
    picked = select_skills_llm("停顿太多帮我剪掉", skills, client=client)
    assert any(s.name == "silence-cleanup" for s in picked)

    # client 抛异常 → 降级 bigram，绝不拖死主流程
    class Boom:
        @property
        def chat(self):
            raise RuntimeError("网络断了")
    picked = select_skills_llm("音量太小", skills, client=Boom())
    assert any(s.name == "loudness-balance" for s in picked)

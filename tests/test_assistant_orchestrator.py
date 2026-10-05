import pytest

from app.assistant import orchestrator


def test_system_help_does_not_require_snapshot():
    intent = orchestrator.classify("Как начать работу после загрузки Excel?",
                                   has_snapshot=False, focus=None, metric_codes=set(),
                                   has_scenario=False)
    assert intent.name == "system_help" and intent.clarification is None


def test_specific_plan_question_asks_for_context():
    intent = orchestrator.classify("Почему моя команда не укладывается?",
                                   has_snapshot=False, focus=None, metric_codes=set(),
                                   has_scenario=False)
    assert intent.name == "overview" and intent.clarification


def test_saved_scenario_enables_comparison():
    intent = orchestrator.classify("Сравни найм и перевод", has_snapshot=True,
                                   focus=None, metric_codes=set(), has_scenario=True)
    assert intent.name == "compare_measures" and intent.clarification is None


def test_metric_and_focus_route():
    metric = orchestrator.classify("Почему pi_predictability низкий?", has_snapshot=True,
                                   focus=None, metric_codes={"pi_predictability"}, has_scenario=False)
    team = orchestrator.classify("А эта команда?", has_snapshot=True,
                                 focus=("team", "ALPHA"), metric_codes=set(), has_scenario=False)
    assert metric.name == "metric_explanation"
    assert team.name == "team_analysis"


def test_changes_use_previous_bound_run():
    selected = orchestrator.classify("Что изменилось?", has_snapshot=True, focus=None,
                                     metric_codes=set(), has_scenario=False, has_previous_run=True)
    missing = orchestrator.classify("Что изменилось?", has_snapshot=True, focus=None,
                                    metric_codes=set(), has_scenario=False, has_previous_run=False)
    assert selected.name == "changes" and selected.clarification is None
    assert missing.clarification


def test_measure_followup_preserves_pending_intent():
    first = orchestrator.classify("Можно перевести инженера?", has_snapshot=True,
                                  focus=None, metric_codes=set(), has_scenario=False)
    followup = orchestrator.classify("Половину ставки с третьего спринта", has_snapshot=True,
                                     focus=None, metric_codes=set(), has_scenario=False,
                                     pending_intent=first.name)
    assert first.name == followup.name == "compare_measures"
    assert followup.clarification


@pytest.mark.parametrize("question", [
    "Как строится план квартала? Распиши по шагам.",
    "Как строится план квартала и почему часть задач переносится?",
    "Откуда берутся роли, ёмкость команд и Bus Factor?",
    "Как загрузить факт спринта и что произойдёт после пересчёта?",
    "что умеешь?",
])
def test_general_questions_in_knowledge_chat_go_to_help(question):
    intent = orchestrator.classify(question, has_snapshot=False, focus=None, metric_codes=set(), has_scenario=False)
    assert intent == orchestrator.Intent("system_help")


def test_own_plan_without_run_still_asks_for_run():
    intent = orchestrator.classify("Где у нас дефицит в плане?", has_snapshot=False, focus=None,
                                   metric_codes=set(), has_scenario=False)
    assert intent.name == "overview" and intent.clarification


@pytest.mark.parametrize("question", ["что произошло", "ну и как дела?", "объясни ситуацию"])
def test_vague_question_in_run_chat_goes_to_overview(question):
    intent = orchestrator.classify(question, has_snapshot=True, focus=None, metric_codes=set(), has_scenario=False)
    assert intent == orchestrator.Intent("overview")


def test_general_question_in_run_chat_still_gets_help():
    intent = orchestrator.classify("Что такое Bus Factor?", has_snapshot=True, focus=None,
                                   metric_codes=set(), has_scenario=False)
    assert intent == orchestrator.Intent("system_help")

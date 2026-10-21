"""Offline regressions for data boundaries and minimal historical requests."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import rdhs_query as r

COMPONENTS = ["链路闭环得分(25')", "交付闭环得分(15')", "时效节奏合理性(20')", "颗粒度对齐度(20')", "质量敏锐度(20')"]
TITLES = ["RDHS(100')", *COMPONENTS, '有效参与人数', '人均需求吞吐量', '人均缺陷关闭量', '积压需求占比', '严重缺陷占比']
MASTER = {'产品A': {'id': 1, 'business_path': '一级A/二级A', 'is_in_progress': True, 'is_custom': False, 'prod_rep': '产品甲', 'pm_rep': '项目甲'}}

def row(values=None, business='一级A', zero=False):
    numbers = values if values is not None else [80, 25, 15, 10, 15, 15, 10, 1, 5, 0, 0.1]
    return {'dim': {'0': business, '1': '产品A'}, 'value': {str(i): str(n) for i, n in enumerate(numbers)}, 'is_zero_spec': zero}

class SafetyTest(unittest.TestCase):
    def setUp(self):
        class FixedDate(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 9, 12, tzinfo=tz)
        clock = patch.object(r, 'datetime', FixedDate)
        clock.start()
        self.addCleanup(clock.stop)

    def test_placeholder_is_missing_but_real_zero_is_measured(self):
        self.assertEqual(r.parse_chart_rows(TITLES, [row(zero=True)], MASTER), {})
        actual = r.parse_chart_rows(TITLES, [row([0] * len(TITLES))], MASTER)
        self.assertEqual(actual['产品A']['rdhs'], 0)
        summary = r.summarize_scope([('产品A', actual['产品A'], None, MASTER['产品A'])])
        self.assertEqual(summary['tiers']['P0'], 1)

    def test_invalid_score_schema_rejected(self):
        cases = [(TITLES[1:], row()), (TITLES, row([float('nan'), *([0] * (len(TITLES)-1))])), (TITLES, row([101, *([0] * (len(TITLES)-1))])), (TITLES, row([70, 25, 15, 10, 15, 15, 10, 1, 5, 0, 0.1]))]
        for titles, value in cases:
            with self.subTest(value=value), self.assertRaises(ValueError):
                r.parse_chart_rows(titles, [value], MASTER)
        value = row(); value['value']['0'] = True
        with self.assertRaises(ValueError):
            r.parse_chart_rows(TITLES, [value], MASTER)
        value = row(); value['is_zero_spec'] = 'false'
        with self.assertRaises(ValueError):
            r.parse_chart_rows(TITLES, [value], MASTER)

    def test_rounding_tolerance_does_not_rewrite_score(self):
        actual = r.parse_chart_rows(TITLES, [row([79.99, 25, 15, 10, 15, 15, 10, 1, 5, 0, 0.1])], MASTER)
        self.assertEqual(actual['产品A']['rdhs'], 79.99)

    def test_business_mismatch_is_not_silent_fallback(self):
        with self.assertRaises(ValueError):
            r.parse_chart_rows(TITLES, [row(business='一级B')], MASTER)

    def test_unknown_multiblock_rejected(self):
        with patch.object(r, 'get_cached_or_fetch', return_value={'quota_titles': TITLES, 'chart_data_list': [[row()], [row()]]}):
            with self.assertRaises(ValueError):
                r.get_chart_data(r.CURRENT_CHART_ID)

    def test_low_positive_throughput_not_claimed_zero(self):
        result = r.evaluate_attribution({'有效参与人数': '10', '人均需求吞吐量': '0.2', '人均缺陷关闭量': '0.5', "链路闭环得分(25')": '13'})
        self.assertNotIn('吞吐量为 0', result[1])
        self.assertIn('0.2', result[1])

    def test_one_month_without_completions_not_called_faster(self):
        rows = [{'month': '2026-08', 'metrics': {'需求吞吐量': '10', '需求交付周期': '20', '严重缺陷占比': '0.1'}}, {'month': '2026-09', 'metrics': {'需求吞吐量': '0', '需求交付周期': '0', '严重缺陷占比': '0'}}]
        text = '\n'.join(r.format_trend_judgement(rows))
        self.assertNotIn('缩短', text)
        self.assertNotIn('改善', text)
        self.assertIn('样本', text)

    def test_quality_risk_has_quality_action(self):
        metrics = {title: str(value) for title, value in zip(TITLES, [67, 25, 15, 12, 10, 5, 10, 1, 5, 0, 0.3])}
        report = r.format_product_report('产品A', {'rdhs': 67, 'business_line_chart': '一级A', 'metrics': metrics}, None, MASTER['产品A'])
        self.assertNotIn('保持当前研发节拍', report)
        self.assertIn('严重缺陷', report.split('### 🎯 当前优先治理动作')[1])

    def test_relative_chart_cache_key_has_effective_month(self):
        with tempfile.TemporaryDirectory() as td, patch.object(r, 'CACHE_DIR', Path(td)), patch.object(r, 'run_meegle_cmd', return_value={'quota_titles': TITLES, 'chart_data_list': [[row()]]}) as fetch:
            for anchor in [datetime(2026, 9, 30), datetime(2026, 10, 1), datetime(2026, 10, 1)]:
                with patch.object(r, 'chart_period', return_value=r.previous_period(anchor)):
                    r.get_chart_data(r.LAST_CHART_ID, ttl=1800, now=anchor)
            self.assertEqual(fetch.call_count, 2)

    def test_auth_not_retried_and_request_has_timeout(self):
        response = SimpleNamespace(returncode=1, stdout='AUTH_REQUIRED', stderr='')
        with patch.object(r.subprocess, 'run', return_value=response) as run, patch.object(r.time, 'sleep') as sleep:
            with self.assertRaises(RuntimeError):
                r.run_meegle_cmd(['chart', 'get'])
            self.assertEqual(run.call_count, 1)
            self.assertGreater(run.call_args.kwargs['timeout'], 0)
            sleep.assert_not_called()

    def test_frequency_error_retried(self):
        responses = [SimpleNamespace(returncode=1, stdout='10429', stderr=''), SimpleNamespace(returncode=0, stdout='{"data": []}', stderr='')]
        with patch.object(r.subprocess, 'run', side_effect=responses) as run, patch.object(r.time, 'sleep'):
            self.assertEqual(r.run_meegle_cmd(['chart', 'get']), [])
            self.assertEqual(run.call_count, 2)

    def test_target_month_before_display_window(self):
        rows = [{'dim': {'0': f'2026-{month:02d}'}, 'value': {'0': str(month)}} for month in range(1, 10)]
        parsed = r.parse_trend_rows(['需求吞吐量'], rows, month='2026-02', now=datetime(2026, 10, 9))
        self.assertEqual([p['month'] for p in parsed], ['2026-02'])

    def test_bg_history_never_fetches_master_users_or_current_chart(self):
        rows = [{'dim': {'0': '2026-09'}, 'value': {'0': '631'}}]
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--month', '2026-09', '--format', 'json']), patch.object(r, 'get_product_master') as master, patch.object(r, 'resolve_user_names') as users, patch.object(r, 'get_chart_data', return_value=(['需求吞吐量'], rows)) as chart, contextlib.redirect_stdout(out):
            r.main()
        master.assert_not_called(); users.assert_not_called()
        self.assertEqual(chart.call_count, 1)
        self.assertEqual(chart.call_args.args[0], r.BG_TREND_CHART_ID)
        result = json.loads(out.getvalue())
        self.assertEqual(result['period'], '2026-09')
        self.assertEqual(result['status'], 'ok')

    def test_missing_comparison_is_not_nearest_month(self):
        rows = [{'dim': {'0': '2026-07'}, 'value': {'0': '1'}}, {'dim': {'0': '2026-09'}, 'value': {'0': '3'}}]
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--month', '2026-09', '--compare', '--format', 'json']), patch.object(r, 'get_chart_data', return_value=(['需求吞吐量'], rows)), contextlib.redirect_stdout(out):
            r.main()
        result = json.loads(out.getvalue())
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['trends'][0]['judgement'], [])
        self.assertIn('2026-08', ' '.join(result['warnings']))

    def test_current_month_and_product_history_rejected(self):
        for args in [['--all', '--month', r.current_period()], ['--product', '产品A', '--month', '2026-09']]:
            with patch.object(sys, 'argv', ['rdhs_query', *args]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                r.main()

    def test_empty_current_result_is_json(self):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--format', 'json']), patch.object(r, 'get_product_master', return_value={}), patch.object(r, 'get_chart_data', return_value=([], [])), contextlib.redirect_stdout(out):
            r.main()
        self.assertEqual(json.loads(out.getvalue())['status'], 'no_data')

    def test_unknown_custom_attribute_fails_closed(self):
        item = {'id': 1, 'name': '定制产品', 'work_item_status': {'state_key': 'In Progress'}, 'fields': [{'field_key': 'business', 'field_value': 'biz'}, {'field_key': 'field_22acd7', 'field_value': {'value': 'hmeckpgbh'}}]}
        with patch.object(r, 'get_cached_or_fetch', return_value=[item]), patch.object(r, 'get_business_lines', return_value={'biz': '一级A/二级A'}), patch.object(r, 'resolve_user_names', return_value={}):
            result = r.get_product_master()['定制产品']
        self.assertTrue(result['is_custom'])
        self.assertFalse(r.is_eligible_product(result))

    def test_missing_trend_columns_not_rendered_as_zero(self):
        report = r.format_trend_report('BG', [{'month': '2026-09', 'metrics': {'需求吞吐量': '1'}}])
        self.assertIn('未获取', report)
        self.assertNotIn('0.0%', report)

    def test_cross_month_fetch_does_not_write_cache(self):
        with tempfile.TemporaryDirectory() as td, patch.object(r, 'CACHE_DIR', Path(td)), patch.object(r, 'chart_period', side_effect=['2026-09', '2026-09', '2026-10']), patch.object(r, 'run_meegle_cmd', return_value={'quota_titles': TITLES, 'chart_data_list': [[row()]]}):
            with self.assertRaises(RuntimeError):
                r.get_chart_data(r.LAST_CHART_ID)
            self.assertEqual(list(Path(td).glob('*.json')), [])

    def test_timeout_and_invalid_json_have_bounded_retries(self):
        import subprocess
        with patch.object(r.subprocess, 'run', side_effect=subprocess.TimeoutExpired('meegle', 30)) as run, patch.object(r.time, 'sleep'):
            with self.assertRaises(RuntimeError):
                r.run_meegle_cmd(['chart', 'get'])
            self.assertEqual(run.call_count, 3)
        with patch.object(r.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='not-json', stderr='')) as run:
            with self.assertRaises(RuntimeError):
                r.run_meegle_cmd(['chart', 'get'])
            self.assertEqual(run.call_count, 1)

    def test_empty_historical_result_and_invalid_month(self):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--month', '2026-09', '--format', 'json']), patch.object(r, 'get_chart_data', return_value=(['需求吞吐量'], [])), contextlib.redirect_stdout(out):
            r.main()
        self.assertEqual(json.loads(out.getvalue())['status'], 'no_data')
        for month in ['2026-9', '2026-13', 'invalid', '2027-01']:
            with patch.object(sys, 'argv', ['rdhs_query', '--all', '--month', month]), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                r.main()

    def test_secondary_history_uses_tree_and_one_correct_chart(self):
        rows = [{'dim': {'0': '2026-09', '1': '一级A', '2': '二级A'}, 'value': {'0': '4'}}]
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--business-line', '二级A', '--month', '2026-09', '--format', 'json']), patch.object(r, 'get_business_lines', return_value={'a': '一级A', 'b': '一级A/二级A'}), patch.object(r, 'get_product_master') as master, patch.object(r, 'get_chart_data', return_value=(['需求吞吐量'], rows)) as chart, contextlib.redirect_stdout(out):
            r.main()
        master.assert_not_called()
        self.assertEqual(chart.call_args.args[0], r.SECONDARY_LINE_TREND_CHART_ID)
        self.assertEqual(json.loads(out.getvalue())['trends'][0]['rows'][0]['metrics']['需求吞吐量'], '4')

    def test_ambiguous_business_line_rejected_before_chart_fetch(self):
        with patch.object(sys, 'argv', ['rdhs_query', '--business-line', '二级A', '--month', '2026-09']), patch.object(r, 'get_business_lines', return_value={'a': '一级A/二级A', 'b': '一级B/二级A'}), patch.object(r, 'get_chart_data') as chart, contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            r.main()
        chart.assert_not_called()

    def test_baseline_failure_is_partial_and_only_selected_roles_resolved(self):
        info = {**MASTER['产品A'], 'roles': {'产品代表': ['user1'], '项目管理代表': ['user2']}}
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--compare', '--format', 'json']), patch.object(r, 'get_product_master', return_value={'产品A': info}), patch.object(r, 'get_chart_data', side_effect=[(TITLES, [row()]), RuntimeError('baseline missing')]), patch.object(r, 'resolve_user_names', return_value={'user1': '甲', 'user2': '乙'}) as names, contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            r.main()
        self.assertEqual(set(names.call_args.args[0]), {'user1', 'user2'})
        result = json.loads(out.getvalue())
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['products'][0]['master']['prod_rep'], '甲')
        self.assertIn('基线', ' '.join(result['warnings']))

    def test_unknown_enum_does_not_use_standard_label(self):
        for attr, expected in [({'value': 'unknown', 'label': '标准产品'}, '未知'), ({'label': '标准产品'}, '标准产品')]:
            item = {'id': 1, 'name': '产品A', 'fields': [{'field_key': 'field_22acd7', 'field_value': attr}]}
            with patch.object(r, 'get_cached_or_fetch', return_value=[item]), patch.object(r, 'get_business_lines', return_value={}), patch.object(r, 'resolve_user_names', return_value={}):
                self.assertEqual(r.get_product_master()['产品A']['product_attr'], expected)

    def test_missing_completion_count_is_distinct_from_zero(self):
        report = r.format_trend_report('BG', [{'month': '2026-09', 'metrics': {'需求交付周期': '5'}}])
        self.assertIn('完成量未获取', report)
        self.assertNotIn('无有效样本', report)
        with self.assertRaises(ValueError):
            r.parse_trend_rows(['需求吞吐量'], [{'dim': {'0': '2026-09'}, 'value': {'0': None}}])

    def test_two_chart_calls_across_month_do_not_emit_result(self):
        class ChangingDate(datetime):
            calls = 0
            @classmethod
            def now(cls, tz=None):
                cls.calls += 1
                return cls(2026, 9, 30, 23, 59, tzinfo=tz) if cls.calls == 1 else cls(2026, 10, 1, tzinfo=tz)
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--compare', '--format', 'json']), patch.object(r, 'datetime', ChangingDate), patch.object(r, 'get_product_master', return_value=MASTER), patch.object(r, 'resolve_user_names', return_value={}), patch.object(r, 'get_chart_data', return_value=(TITLES, [row()])), contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError):
            r.main()

    def test_json_error_entrypoint_is_parseable_without_network(self):
        import subprocess
        import os
        with tempfile.TemporaryDirectory() as td:
            script = Path(td) / 'probe.py'
            script.write_text("import runpy, subprocess\nsubprocess.run = lambda *a, **k: type('Response', (), {'returncode': 1, 'stdout': 'AUTH_REQUIRED', 'stderr': ''})()\nrunpy.run_path(" + repr(str(Path(r.__file__).resolve())) + ", run_name='__main__')\n")
            result = subprocess.run([sys.executable, str(script), '--all', '--refresh', '--format=json'], capture_output=True, text=True, env={**os.environ, 'HOME': td, 'PYTHONDONTWRITEBYTECODE': '1'})
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['status'], 'error')

    def test_release_registration_ratio_and_gap(self):
        report = r.format_trend_report('BG', [{'month': '2026-09', 'metrics': {'需求吞吐量': '631', '应发布需求数': '598', '有效发布需求数': '509'}}])
        self.assertIn('85.12%', report)
        self.assertIn('| 89 |', report)
        with self.assertRaises(ValueError):
            r.parse_trend_rows(['应发布需求数', '有效发布需求数'], [{'dim': {'0': '2026-09'}, 'value': {'0': '1', '1': '2'}}])

    def test_json_argument_error_is_structured(self):
        out = io.StringIO()
        with patch.object(sys, 'argv', ['rdhs_query', '--all', '--month', 'invalid', '--format', 'json']), contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as caught:
            r.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertEqual(json.loads(out.getvalue())['status'], 'error')

    def test_release_counts_invalid_or_no_sample(self):
        for required, valid in [('NaN', '0'), ('1', '-1'), ('1', 'Infinity')]:
            with self.assertRaises(ValueError):
                r.parse_trend_rows(['应发布需求数', '有效发布需求数'], [{'dim': {'0': '2026-09'}, 'value': {'0': required, '1': valid}}])
        report = r.format_trend_report('BG', [{'month': '2026-09', 'metrics': {'应发布需求数': '0', '有效发布需求数': '0'}}])
        self.assertIn('无应发布样本', report)
        self.assertNotIn('100.00%', report)

    def test_uncertain_scope_not_given_overall_tier(self):
        report = r.format_scope_summary('BG', [('产品A', {'rdhs': 80}, None, MASTER['产品A'])], scope_uncertain=True)
        self.assertIn('不作整体分档', report)
        self.assertNotIn('（常规跟踪）', report)

    def test_duplicate_master_name_rejected(self):
        base = {'name': '同名产品', 'work_item_status': {'state_key': 'In Progress'}, 'fields': []}
        with patch.object(r, 'get_cached_or_fetch', return_value=[{'id': 1, **base}, {'id': 2, **base}]), patch.object(r, 'get_business_lines', return_value={}), patch.object(r, 'resolve_user_names', return_value={}):
            with self.assertRaises(ValueError):
                r.get_product_master()

if __name__ == '__main__':
    unittest.main()

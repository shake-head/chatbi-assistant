"""Deterministic local provider for development, tests, and degraded mode."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.services.ai.base import AIProviderError, ProviderResult


class LocalRuleProvider:
    """Generate safe structured plans and conclusions without a remote model.

    This is intentionally limited. It keeps local development and tests usable
    when no hosted model credentials are configured, while all outputs still
    pass through the same schema validation and sandbox execution path.
    """

    name = "local"
    model = "deterministic-rules-v1"

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        json_mode: bool = False,
    ) -> ProviderResult:
        prompt = "\n".join(message["content"] for message in messages)
        try:
            request = json.loads(messages[-1]["content"])
            task = request["task"]
            if task == "intent":
                output = self._build_plan(request)
            elif task == "conclusion":
                output = self._build_conclusion(request)
            else:
                raise AIProviderError("LOCAL_UNSUPPORTED_TASK", retriable=False)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AIProviderError("LOCAL_INVALID_REQUEST", retriable=False) from exc

        content = json.dumps(output, ensure_ascii=False)
        return ProviderResult(
            content=content,
            provider=self.name,
            model=self.model,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(content) // 4),
        )

    def _build_plan(self, request: dict[str, Any]) -> dict[str, Any]:
        question = str(request.get("question", "")).strip()
        schema = request.get("schema") or {}
        columns = schema.get("columns") or []
        if not question or not columns:
            raise AIProviderError("LOCAL_PLAN_CONTEXT_MISSING", retriable=False)

        lower_question = question.lower()
        numeric_columns = [column for column in columns if column["dtype"] in {"number", "integer"}]
        datetime_columns = [column for column in columns if column["dtype"] == "datetime"]
        dimension_columns = [
            column for column in columns if column["dtype"] in {"string", "boolean"}
        ]

        metric_column = self._named_column(numeric_columns, lower_question)
        aggregation = self._aggregation(lower_question, metric_column)

        if aggregation == "count" and metric_column is None:
            metric: dict[str, Any] = {"aggregation": "count", "alias": "记录数"}
        else:
            if metric_column is None:
                if numeric_columns:
                    metric_column = numeric_columns[0]
                else:
                    metric = {"aggregation": "count", "alias": "记录数"}
                    metric_column = None
            if metric_column is not None:
                metric = {
                    "aggregation": aggregation,
                    "column": metric_column["name"],
                    "alias": self._metric_alias(aggregation, metric_column["name"]),
                }

        time_column = self._named_column(datetime_columns, lower_question)
        trend_words = ("趋势", "走势", "变化", "每月", "逐月", "按月", "时间")
        wants_time = any(word in question for word in trend_words) or "近" in question
        if time_column is None and wants_time and datetime_columns:
            time_column = datetime_columns[0]

        group_by: list[str] = []
        named_dimension = self._named_column(dimension_columns, lower_question)
        grouping_words = ("各", "按", "每", "分区域", "分渠道", "分组")
        if named_dimension is not None and (
            any(word in question for word in grouping_words) or time_column is not None
        ):
            group_by.append(named_dimension["name"])
        elif any(word in question for word in grouping_words) and dimension_columns:
            group_by.append(dimension_columns[0]["name"])

        filters: list[dict[str, Any]] = []
        if time_column is not None:
            date_filter = self._relative_date_filter(question, time_column["name"])
            if date_filter is not None:
                filters.append(date_filter)

        plan: dict[str, Any] = {
            "title": question[:200],
            "metrics": [metric],
            "group_by": group_by,
            "filters": filters,
            "limit": 100,
        }
        if time_column is not None and wants_time:
            plan["time_bucket"] = {
                "column": time_column["name"],
                "granularity": self._granularity(lower_question),
            }
            plan["chart_type"] = "line"
        elif any(word in question for word in ("占比", "比例", "构成")):
            plan["chart_type"] = "pie"
        else:
            plan["chart_type"] = "auto"

        return plan

    @staticmethod
    def _named_column(
        columns: list[dict[str, Any]],
        lower_question: str,
    ) -> dict[str, Any] | None:
        matches = [column for column in columns if str(column["name"]).lower() in lower_question]
        return max(matches, key=lambda column: len(column["name"])) if matches else None

    @staticmethod
    def _aggregation(lower_question: str, metric_column: dict[str, Any] | None) -> str:
        if any(word in lower_question for word in ("平均", "均值")):
            return "mean"
        if any(word in lower_question for word in ("最大", "最高")):
            return "max"
        if any(word in lower_question for word in ("最小", "最低")):
            return "min"
        if any(word in lower_question for word in ("去重", "不同")):
            return "count_distinct"
        if any(word in lower_question for word in ("合计", "总计", "总额", "总和", "求和")):
            return "sum"
        if metric_column is None and any(
            word in lower_question for word in ("数量", "多少", "几条", "笔数", "计数")
        ):
            return "count"
        return "sum"

    @staticmethod
    def _metric_alias(aggregation: str, column: str) -> str:
        labels = {
            "sum": "合计",
            "mean": "平均值",
            "min": "最小值",
            "max": "最大值",
            "count": "数量",
            "count_distinct": "去重数量",
        }
        return f"{column}{labels.get(aggregation, aggregation)}"

    @staticmethod
    def _granularity(lower_question: str) -> str:
        if any(word in lower_question for word in ("每天", "按日", "逐日")):
            return "day"
        if any(word in lower_question for word in ("每周", "按周", "逐周")):
            return "week"
        if "季度" in lower_question:
            return "quarter"
        if any(word in lower_question for word in ("每年", "按年", "逐年")):
            return "year"
        return "month"

    @staticmethod
    def _relative_date_filter(question: str, column: str) -> dict[str, Any] | None:
        match = re.search(r"近\s*(\d+)\s*(天|日|周|个月|月|年)", question)
        if match is None:
            return None
        amount = int(match.group(1))
        unit = match.group(2)
        days = {"天": 1, "日": 1, "周": 7, "个月": 30, "月": 30, "年": 365}[unit] * amount
        start = datetime.now(UTC).date() - timedelta(days=days)
        return {
            "column": column,
            "operator": "gte",
            "value": start.isoformat(),
        }

    def _build_conclusion(self, request: dict[str, Any]) -> dict[str, str]:
        plan = request.get("plan") or {}
        result = request.get("result") or {}
        columns = result.get("columns") or []
        rows = result.get("rows") or []
        row_count = int(result.get("row_count", len(rows)))
        title = str(plan.get("title", "本次分析"))

        if row_count == 0:
            return {"conclusion": f"根据计算结果，“{title}”在当前筛选条件下没有符合条件的数据。"}

        metric_names = [
            column["name"] for column in columns if column.get("dtype") in {"number", "integer"}
        ]
        group_names = [column["name"] for column in columns if column["name"] not in metric_names]
        conclusion = f"根据计算结果，“{title}”共得到 {row_count} 行结果。"

        if metric_names:
            metric_name = metric_names[0]
            values = [
                (row.get(group_names[0]) if group_names else None, row.get(metric_name))
                for row in rows
                if isinstance(row.get(metric_name), (int, float))
            ]
            if values:
                highest = max(values, key=lambda item: item[1])
                lowest = min(values, key=lambda item: item[1])
                if group_names and highest[0] is not None:
                    conclusion += (
                        f" 在结果中，{highest[0]} 的“{metric_name}”最高，"
                        f"为 {_format_number(highest[1])}；"
                        f"{lowest[0]} 最低，为 {_format_number(lowest[1])}。"
                    )
                else:
                    conclusion += f" “{metric_name}”的值为 {_format_number(highest[1])}。"
        return {"conclusion": conclusion}


def _format_number(value: object) -> str:
    if isinstance(value, (int, float)):
        if isinstance(value, float):
            return f"{value:,.2f}"
        return f"{value:,}"
    return str(value)

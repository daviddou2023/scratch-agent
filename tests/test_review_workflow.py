import unittest

from app.core.review_workflow import ReviewWorkflow
from app.core.schemas import ToolResponse
from app.observability.tracer import Tracer


class FakeTool:
    def __init__(self, name, data, calls, status="success"):
        self.name = name
        self.data = data
        self.calls = calls
        self.status = status

    async def run(self, **kwargs):
        self.calls.append((self.name, kwargs))
        return ToolResponse(status=self.status, data=self.data)


class ReviewWorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_fixed_order_and_passes_structured_results(self):
        calls = []
        workflow = ReviewWorkflow(
            metrics_tool=FakeTool("fetch_video_metrics", {"title": "title"}, calls),
            comments_tool=FakeTool("fetch_comments", {"comments": [{"text": "x"}], "total": 4}, calls),
            clean_tool=FakeTool("clean_comments", {"comments": [{"text": "x"}], "stats": {"cleaned": 1}}, calls),
            analyze_tool=FakeTool("analyze_comments", {"hot_topics": ["topic"]}, calls),
            report_tool=FakeTool("generate_report", {"summary": "summary"}, calls),
            suggestions_tool=FakeTool("generate_suggestions", {"suggestions": ["do this"]}, calls),
            tracer=Tracer(log_dir="test-traces"),
        )

        result = await workflow.run("video_001")

        self.assertEqual(
            [name for name, _ in calls],
            ["fetch_video_metrics", "fetch_comments", "clean_comments", "analyze_comments", "generate_report", "generate_suggestions"],
        )
        self.assertEqual(result["fetched_comment_count"], 4)
        self.assertEqual(result["cleaned_comment_count"], 1)
        self.assertEqual(calls[3][1]["comments"], [{"text": "x"}])
        self.assertIn("采集 4 条", workflow.render_markdown(result))

    async def test_stops_after_tool_error(self):
        calls = []
        workflow = ReviewWorkflow(
            metrics_tool=FakeTool("fetch_video_metrics", {}, calls, status="error"),
            comments_tool=FakeTool("fetch_comments", {}, calls),
            clean_tool=FakeTool("clean_comments", {}, calls),
            analyze_tool=FakeTool("analyze_comments", {}, calls),
            report_tool=FakeTool("generate_report", {}, calls),
            suggestions_tool=FakeTool("generate_suggestions", {}, calls),
            tracer=Tracer(log_dir="test-traces"),
        )

        with self.assertRaisesRegex(RuntimeError, "fetch_video_metrics failed"):
            await workflow.run("video_001")
        self.assertEqual([name for name, _ in calls], ["fetch_video_metrics"])


if __name__ == "__main__":
    unittest.main()

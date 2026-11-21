"""Regression tests for source-grounded ClassPilot assistant."""
import unittest

from course_ai import grading_answer, category_grading_answer, rank_syllabus_pages, rank_materials, _concise_answer

GRADING_PAGE = """iClicker profile
Grading Policy
A total of 1000 points can be earned in this course.
Course Components and Point Distribution
Course Component Points Percentage of Overall Grade
Polling Exercises/Class
Participation 100 10%
Homework 100 10%
Quizzes 150 15%
Exam 1 200 20%
Exam 2 200 20%
Final Exam 250 25%
Total 1000 100%
Course letter grades will be assigned according to the scale below.
Grading Scale
A 900-1000 90%-100%
Page 6 of 18"""
PAGES = [
    "CHEM 107 syllabus. Meeting times: Monday, Wednesday, Friday.",
    "Learning outcomes and chemistry concepts.",
    "Textbooks and course materials.",
    "Homework and course policies.",
    "Exam 1 dates; Example: Exam 1 score 80%, Exam 2 score 60%, final score 80%.",
    GRADING_PAGE,
    "More details about the exam replacement policy.",
]


class GradingTests(unittest.TestCase):
    def test_final_weight(self):
        a = grading_answer(PAGES, "How much is my final worth?")
        self.assertIsNotNone(a)
        self.assertIn("25%", a["answer"])
        self.assertIn("250 points", a["answer"])
        self.assertEqual(a["sources"], ["Official Syllabus · page 6 · Grading Policy"])

    def test_exam_one_weight(self):
        a = grading_answer(PAGES, "How much is Exam 1 worth?")
        self.assertIn("20%", a["answer"])
        self.assertIn("200 points", a["answer"])

    def test_exam_two_weight(self):
        a = grading_answer(PAGES, "What percentage is Exam 2?")
        self.assertIn("20%", a["answer"])

    def test_missing_table_never_guesses(self):
        self.assertIsNone(grading_answer(PAGES[:5], "How much is my final worth?"))

    def test_misleading_examples_ignored(self):
        pages = ["Grading Policy\nCourse Components and Point Distribution\nExam 1 200 20%\nFinal Exam 250 25%"]
        a = grading_answer(pages, "How much is my final worth?")
        self.assertIn("25%", a["answer"])
        self.assertNotIn("20%", a["answer"])

    def test_search_ranks_grading_section_first(self):
        matches = rank_syllabus_pages(PAGES, "How much is my final worth?")
        self.assertEqual(matches[0][1]["title"], "Official Syllabus · page 6")

    def test_unrelated_question_does_not_trigger_grade_parser(self):
        self.assertIsNone(grading_answer(PAGES, "When does the final start?"))


class ConciseAndDocumentTests(unittest.TestCase):
    def test_category_exams_weight_is_collective(self):
        pages = ["Intro", "Grading breakdown\nModule Quizzes: 30%\nAssignments: 30%\nExams: 30%\nReflection Video: 10%"]
        result = category_grading_answer(pages, "How much is each exam worth?")
        self.assertEqual(result["answer"], "Together, exams account for 30% of your overall grade.")
        self.assertEqual(result["sources"], ["Official Syllabus · page 2"])

    def test_category_does_not_override_individual_exam(self):
        self.assertIsNone(category_grading_answer(["Exams: 30%"], "How much is Exam 1 worth?"))

    def test_thinking_tags_are_not_displayed(self):
        raw = "<think>Let me reason through the user's request.</think>{\"answer\":\"Exams are worth 30%.\"}"
        self.assertEqual(_concise_answer(raw), "Exams are worth 30%.")

    def test_untagged_model_reasoning_never_reaches_chat(self):
        raw = "Okay, the user is asking about exams. Let me check the evidence."
        self.assertEqual(_concise_answer(raw), "")

    def test_documents_are_searched_beyond_first_2200_characters(self):
        rows = [{"title":"Lab handbook", "kind":"document", "body":"Unrelated material. " * 200 + "Lab reports are due each Friday at 5pm."}]
        results = rank_materials(rows, "When are lab reports due?")
        self.assertEqual(len(results), 1)
        self.assertIn("Friday at 5pm", results[0]["answer"])

    def test_document_search_scans_multiple_uploaded_documents(self):
        rows = [
            {"title":"Week 1 notes", "kind":"document", "body":"Foundations of financial planning."},
            {"title":"Project policies", "kind":"document", "body":"Projects are due Sunday at 11:59pm."}
        ]
        results = rank_materials(rows, "When are projects due?")
        self.assertTrue(any(item["title"] == "Project policies" for item in results))


if __name__ == "__main__":
    unittest.main()

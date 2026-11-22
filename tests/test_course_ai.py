"""Regression tests for source-grounded ClassPilot assistant."""
import unittest
from unittest.mock import patch
import io
import json
from pathlib import Path

from course_ai import grading_answer, category_grading_answer, grading_table_answer, unspecified_individual_exam_weight, rank_syllabus_pages, _clean_model_answer, _schedule_excerpt_answer, rank_materials, keyword_answer, syllabus_fact_answer, local_answer

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

    def test_keyword_answer_uses_retrieved_syllabus_line(self):
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.\\nExtra course information.",
                    "kind": "official_syllabus"}]
        result = keyword_answer("When are office hours?", matches)
        self.assertIn("Tuesdays at 2 PM", result["answer"])
        self.assertEqual(result["sources"], ["Official Syllabus · page 1"])

    def test_keyword_answer_does_not_invent_absent_answer(self):
        matches = [{"title": "Unrelated notes", "answer": "Safety glasses required in labs.", "kind": "document"}]
        self.assertIsNone(keyword_answer("What is the exam weight?", matches))

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


class OllamaRecoveryTests(unittest.TestCase):
    def test_original_working_plain_text_is_returned(self):
        requests = []
        def fake_urlopen(request, timeout):
            requests.append(json.loads(request.data.decode("utf-8")))
            return io.BytesIO(b'{"message":{"content":"Office hours are Tuesdays at 2 PM."}}')
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.",
                    "kind": "official_syllabus"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=fake_urlopen):
            result = local_answer("When are office hours?", matches)
        self.assertEqual(result["answer"], "Office hours are Tuesdays at 2 PM.")
        self.assertEqual(result["mode"], "ollama")
        self.assertEqual(len(requests), 1)
        self.assertNotIn("format", requests[0])

    def test_offline_keyword_fallback_still_answers(self):
        from urllib.error import URLError
        matches = [{"title": "Official Syllabus · page 1",
                    "answer": "Office Hours: Tuesdays at 2 PM.",
                    "kind": "official_syllabus"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=URLError("service down")):
            result = local_answer("When are office hours?", matches)
        self.assertIn("Tuesdays at 2 PM", result["answer"])
        self.assertEqual(result["mode"], "keyword")
        self.assertEqual(result["sources"], ["Official Syllabus · page 1"])

    def test_no_match_does_not_make_up_course_details(self):
        from urllib.error import URLError
        matches = [{"title": "Notes", "answer": "A clean glass beaker is required.", "kind": "document"}]
        with patch("course_ai.urllib.request.urlopen", side_effect=URLError("service down")):
            result = local_answer("When is the final exam?", matches)
        self.assertEqual(result["mode"], "no_match")
        self.assertNotIn("beaker", result["answer"])



class CommonStudentQuestionTests(unittest.TestCase):
    def test_professor_synonym_retrieves_instructor(self):
        pages = ["Course overview", "Instructor: Dr. Rivera\nEmail: rivera@example.edu"]
        matches = rank_syllabus_pages(pages, "Who is my professor?")
        self.assertEqual(matches[0][1]["title"], "Official Syllabus · page 2")
        answer = keyword_answer("Who is my professor?", [matches[0][1]])
        self.assertIn("Dr. Rivera", answer["answer"])

    def test_textbook_synonym_retrieves_book(self):
        pages = ["Required Book: Fundamentals of Chemistry, ISBN 1234567890"]
        matches = rank_syllabus_pages(pages, "What textbook do we need?")
        self.assertTrue(matches)
        answer = keyword_answer("What textbook do we need?", [matches[0][1]])
        self.assertIn("Fundamentals of Chemistry", answer["answer"])

    def test_office_hours_are_extractable(self):
        materials = [{"title": "Course details", "body": "Instructor: Dr. Rivera\nOffice Hours: Tuesdays at 2 PM in Room 130.", "kind": "document"}]
        result = rank_materials(materials, "When can I meet my professor?")
        self.assertTrue(result)
        answer = keyword_answer("When are office hours?", result)
        self.assertIn("Tuesdays at 2 PM", answer["answer"])

    def test_deadline_paraphrase_retrieves_due_date(self):
        rows = [{"title": "Course calendar", "body": "Assignments must be submitted by Sunday 11:59 PM.", "kind": "document"}]
        matches = rank_materials(rows, "When is homework due?")
        self.assertTrue(matches)
        self.assertIn("Sunday", matches[0]["answer"])

    def test_across_sources_choose_relevant_line(self):
        matches = [
            {"title": "Other notes", "kind": "document", "answer": "The final exam will occur in December."},
            {"title": "Official Syllabus · page 2", "kind": "official_syllabus",
             "answer": "Exams are worth 30% of the total grade."},
        ]
        answer = keyword_answer("How much are exams worth?", matches)
        self.assertIn("30%", answer["answer"])

    def test_missing_private_contact_does_not_invent(self):
        matches = [{"title": "Syllabus", "kind": "official_syllabus",
                    "answer": "Instructor: Dr. Rivera\nCourse title: Chemistry."}]
        answer = keyword_answer("What is the professor's personal phone number?", matches)
        self.assertIsNone(answer)

    def test_missing_date_does_not_return_unrelated_course_line(self):
        matches = [{"title": "Notes", "kind": "document",
                    "answer": "Final exams are important learning milestones."}]
        answer = keyword_answer("When is the final exam due?", matches)
        self.assertIsNone(answer)

    def test_many_questions_have_relevant_keyword_matches(self):
        sample = [
            ("When are office hours?", "Office Hours: Mondays at 3 PM."),
            ("Who is my professor?", "Instructor: Dr. Rivera"),
            ("What textbook is required?", "Required Book: Chemistry Fundamentals"),
            ("Are late assignments accepted?", "Late assignments are accepted with a 10% penalty."),
            ("How much are exams worth?", "Exams: 30% of final grade."),
            ("Is attendance mandatory?", "Attendance is required in every lab."),
        ]
        for question, line in sample:
            with self.subTest(question=question):
                item = {"title": "Official Syllabus · page 1", "kind": "official_syllabus",
                        "answer": line}
                self.assertIsNotNone(keyword_answer(question, [item]))


class FinancialPlanningSyllabusTests(unittest.TestCase):
    """Use the real FINP 235 Simple Syllabus sample checked into the repo."""
    @classmethod
    def setUpClass(cls):
        cls.pages = json.loads(
            (Path(__file__).resolve().parents[1] / "sample_finp235_pages.json").read_text(encoding="utf-8")
        )

    def test_professor_from_real_syllabus(self):
        result = syllabus_fact_answer(self.pages, "Who is my professor?")
        self.assertIn("Nick Kilmer", result["answer"])
        self.assertEqual(result["sources"], ["Official Syllabus · page 1"])

    def test_professor_email_from_real_syllabus(self):
        result = syllabus_fact_answer(self.pages, "What is the instructor's email?")
        self.assertIn("FINP235@ag.tamu.edu", result["answer"])

    def test_office_hours_from_real_syllabus(self):
        result = syllabus_fact_answer(self.pages, "When are office hours?")
        self.assertIn("appointment", result["answer"])

    def test_no_required_textbook(self):
        result = syllabus_fact_answer(self.pages, "What textbook do we need?")
        self.assertIn("not required", result["answer"])

    def test_category_grade_is_30_percent(self):
        result = category_grading_answer(self.pages, "How much are exams worth?")
        self.assertIn("30%", result["answer"])

    def test_uncertain_individual_exam_weight_is_not_inferred(self):
        self.assertIsNone(category_grading_answer(self.pages, "How much is Exam 1 worth?"))

    def test_late_policy_page_is_found(self):
        result = rank_syllabus_pages(self.pages, "What is the late work policy?")
        self.assertTrue(result)
        self.assertTrue(any("page 6" in entry["title"] or "page 5" in entry["title"] for _, entry in result))

    def test_unknown_personal_phone_is_not_guessed(self):
        self.assertIsNone(syllabus_fact_answer(self.pages, "What is my professor's personal cell phone number?"))


class GenericGradingTableTests(unittest.TestCase):
    """Test discovered grading categories against real and synthetic syllabi."""

    @classmethod
    def setUpClass(cls):
        cls.finp = json.loads(
            (Path(__file__).resolve().parents[1] / "sample_finp235_pages.json")
            .read_text(encoding="utf-8")
        )

    def test_reflection_video_from_real_syllabus(self):
        result = grading_table_answer(self.finp, "How much is the reflection video worth?")
        self.assertEqual(result["answer"], "Reflection Video is worth 10% of your overall grade.")
        self.assertEqual(result["sources"], ["Official Syllabus · page 5 · Grading table"])

    def test_other_categories_from_real_syllabus(self):
        cases = (
            ("How much are module quizzes worth?", "Module Quizzes", "30%"),
            ("What percentage are assignments worth?", "Assignments", "30%"),
            ("How much is extra credit worth?", "Extra Credit", "5%"),
            ("What percentage does the reflection video contribute?", "Reflection Video", "10%"),
        )
        for question, category, value in cases:
            with self.subTest(question=question):
                result = grading_table_answer(self.finp, question)
                self.assertIsNotNone(result)
                self.assertIn(category, result["answer"])
                self.assertIn(value, result["answer"])

    def test_new_course_and_unseen_labels(self):
        pages = ["Grading Policy",
                 "Research Portfolio: 42%\nSeminar Participation: 18%\nWeekly Exercises: 40%\nTotal: 100%"]
        result = grading_table_answer(pages, "What percentage is the research portfolio?")
        self.assertEqual(result["answer"], "Research Portfolio is worth 42% of your overall grade.")
        self.assertEqual(result["sources"], ["Official Syllabus · page 2 · Grading table"])

    def test_preserves_points_when_given(self):
        result = grading_table_answer(PAGES, "How much is homework worth?")
        self.assertIn("10%", result["answer"])
        self.assertIn("100 points", result["answer"])

    def test_individual_exam_not_derived_from_total(self):
        self.assertIsNone(grading_table_answer(self.finp, "What is Exam 1 worth?"))
        self.assertIsNone(grading_table_answer(self.finp, "What is the final exam worth?"))

    def test_grade_scale_and_schedule_not_mistaken_for_weights(self):
        pages = ["Final Exam scores: 85%\nExam 1 scores: 70%\nExam 2 scores: 75%",
                 "Grading Scale\nA: 90%\nB: 80%\nC: 70%\nTotal: 100%"]
        self.assertIsNone(grading_table_answer(pages, "How much is the final exam worth?"))

    def test_date_question_does_not_get_weight(self):
        self.assertIsNone(grading_table_answer(self.finp, "When is the reflection video due?"))

    def test_missing_component_does_not_invent_weight(self):
        self.assertIsNone(grading_table_answer(self.finp, "How much is the textbook worth?"))

    def test_ambiguous_category_does_not_guess(self):
        pages = ["Grading Policy\nFinal Project: 20%\nResearch Project: 30%\nParticipation: 50%\nTotal: 100%"]
        self.assertIsNone(grading_table_answer(pages, "How much is the project worth?"))


class EvidenceRetrievalAndOutputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = json.loads(
            (Path(__file__).resolve().parents[1] / "sample_finp235_pages.json").read_text(encoding="utf-8")
        )

    def test_week_10_returns_exact_schedule_passage(self):
        matches = rank_syllabus_pages(self.pages, "What's due in week 10?", limit=3)
        self.assertTrue(matches)
        self.assertEqual(matches[0][1]["title"], "Official Syllabus · page 8")
        self.assertIn("Exam 2 (due 11/1 @ 11:59pm)", matches[0][1]["answer"])
        self.assertIn("Assignment: None", matches[0][1]["answer"])
        self.assertNotIn("Week 11", matches[0][1]["answer"])

    def test_week_15_and_unknown_week(self):
        hits = rank_syllabus_pages(self.pages, "What is due in Week 15?")
        self.assertIn("Reflection Video (due 12/4 @ 11:59pm)", hits[0][1]["answer"])
        self.assertIn("Exam 3 (due 12/6 @ 11:59pm)", hits[0][1]["answer"])
        self.assertEqual(rank_syllabus_pages(self.pages, "What is due in Week 99?"), [])

    def test_offline_schedule_uses_real_source(self):
        matches = [x[1] for x in rank_syllabus_pages(self.pages, "What's due in week 10?")]
        result = _schedule_excerpt_answer("What's due in week 10?", matches)
        self.assertIn("Exam 2 (due 11/1 @ 11:59pm)", result["answer"])
        self.assertIn("Assignment: None", result["answer"])
        self.assertEqual(result["sources"], ["Official Syllabus · page 8"])

    def test_document_question_not_restricted_to_hardcoded_question(self):
        hits = rank_syllabus_pages(self.pages, "What is discussed in Week 12?")
        self.assertIn("Investments, Retirement Planning", hits[0][1]["answer"])

    def test_removes_untagged_reasoning_but_keeps_final_answer(self):
        original = (
            "Okay, the user is asking what's due in week 10. "
            "Let me check the evidence provided. "
            "Exam 2 is due November 1 at 11:59 PM."
        )
        self.assertEqual(_clean_model_answer(original), "Exam 2 is due November 1 at 11:59 PM.")

    def test_removes_tagged_thinking(self):
        self.assertEqual(
            _clean_model_answer("<think>Let me check the syllabus.</think>Week 10 has Exam 2."),
            "Week 10 has Exam 2.",
        )

    def test_rejects_only_thinking_with_no_answer(self):
        self.assertEqual(_clean_model_answer("Okay, the user is asking about the schedule. Let me check the evidence."), "")

    def test_real_ollama_response_is_sanitized(self):
        matches = [x[1] for x in rank_syllabus_pages(self.pages, "What's due in week 10?")]
        response_text = "Okay, the user is asking what's due in week 10. Let me check the evidence provided. Exam 2 is due 11/1 at 11:59pm."
        fake = io.BytesIO(json.dumps({"message": {"content": response_text}}).encode("utf-8"))
        with patch("course_ai.urllib.request.urlopen", return_value=fake):
            result = local_answer("What's due in week 10?", matches)
        self.assertEqual(result["answer"], "Exam 2 is due 11/1 at 11:59pm.")
        self.assertEqual(result["mode"], "ollama")




class ReasoningAndGradeEvidenceRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = json.loads((Path(__file__).resolve().parents[1] / "sample_finp235_pages.json").read_text(encoding="utf-8"))

    def test_no_separate_final_exam_weight(self):
        result = unspecified_individual_exam_weight(self.pages, "How much is my final exam worth?")
        self.assertIsNotNone(result)
        self.assertIn("30%", result["answer"])
        self.assertIn("does not specify a separate weight", result["answer"])
        self.assertEqual(result["sources"], ["Official Syllabus · page 5 · Grading table"])

    def test_grade_passages_rank_actual_grading_table(self):
        hits = rank_syllabus_pages(self.pages, "How much is my final exam worth?")
        self.assertEqual(hits[0][1]["title"], "Official Syllabus · page 5")
        self.assertIn("Exams: 30%", hits[0][1]["answer"])
        titles = [v["title"] for _, v in hits]
        self.assertEqual(len(titles), len(set(titles)))

    def test_explicit_exam_weight_remains_available(self):
        self.assertIn("25%", grading_answer(PAGES, "How much is my final exam worth?")["answer"])
        self.assertIsNone(unspecified_individual_exam_weight(PAGES, "How much is my final exam worth?"))

    def test_reasoning_screenshot_is_not_exposed(self):
        raw = "I need to check the evidence provided to find the answer. First, I'll look at the evidence. Wait, the question is about the final exam's weight. The user might be confused because the evidence provided is incomplete."
        self.assertEqual(_clean_model_answer(raw), "")

    def test_reasoning_only_is_rejected(self):
        self.assertEqual(_clean_model_answer("The user might be confused between the final grade"), "")

    def test_plain_answer_remains(self):
        self.assertEqual(_clean_model_answer("Reflection Video is worth 10% of the overall grade."), "Reflection Video is worth 10% of the overall grade.")

    def test_reasoning_returns_source_week_instead(self):
        matches = [e for _, e in rank_syllabus_pages(self.pages, "What's due in Week 10?")]
        fake = io.BytesIO(json.dumps({"message": {"content": "The user might be confused. I need to check the evidence."}}).encode())
        with patch("course_ai.urllib.request.urlopen", return_value=fake):
            answer = local_answer("What's due in Week 10?", matches)
        self.assertEqual(answer["mode"], "source_excerpt")
        self.assertIn("Exam 2", answer["answer"])



if __name__ == "__main__":
    unittest.main()

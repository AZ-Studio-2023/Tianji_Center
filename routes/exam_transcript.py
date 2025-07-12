from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models.exam import Exam, ExamPaper, ExamQuestion

transcript_bp = Blueprint('exam_transcript', __name__, template_folder='../templates/exam')

@transcript_bp.route('/transcript/<int:exam_id>')
@login_required
def transcript(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    paper = ExamPaper.query.filter_by(exam_id=exam.id, user_id=current_user.id).first()
    if not paper:
        return render_template('exam/transcript.html', exam=exam, paper=None)
    questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
    answers = eval(paper.answers)
    total_score = sum(q.score for q in questions)
    return render_template('exam/transcript.html', exam=exam, paper=paper, questions=questions, answers=answers, total_score=total_score)

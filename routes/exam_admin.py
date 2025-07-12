from flask import Blueprint, render_template
from flask_login import login_required, current_user
from models.exam import Exam, ExamPaper, ExamQuestion

admin_bp = Blueprint('exam_admin', __name__, template_folder='../templates/exam')

@admin_bp.route('/admin/exam/<int:exam_id>/answers')
@login_required
def answers(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        return render_template('exam/answers.html', exam=exam, papers=[])
    papers = ExamPaper.query.filter_by(exam_id=exam.id).all() if exam.instant_score or exam.must_exam else ExamPaper.query.filter_by(exam_id=exam.id, graded=True).all()
    questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
    return render_template('exam/answers.html', exam=exam, papers=papers, questions=questions)

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models.exam import Exam
from models.user import CoinRecord

exam_bp = Blueprint('exam', __name__, template_folder='../templates/exam')

@exam_bp.route('/')
@login_required
def index():
    # 管理员可见全部，普通用户只见未隐藏的
    if hasattr(current_user, 'is_admin') and current_user.is_admin:
        exams = Exam.query.order_by(Exam.pinned.desc(), Exam.created_at.desc()).all()
    else:
        exams = Exam.query.filter_by(hidden=False).order_by(Exam.pinned.desc(), Exam.created_at.desc()).all()
    # 传递 grader_ids 给模板，避免模板内用 for 表达式
    for exam in exams:
        exam.grader_ids = [g.user_id for g in getattr(exam, 'graders', [])]
    return render_template('exam/index.html', exams=exams)

@exam_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_exam():
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    if request.method == 'POST':
        exam = Exam(
            name=request.form['name'],
            description=request.form.get('description'),
            duration=int(request.form['duration']),
            auto_submit_limit=int(request.form.get('auto_submit_limit', 0)),
            must_exam='must_exam' in request.form,
            instant_score='instant_score' in request.form,
            start_time=request.form.get('start_time') or None,
            end_time=request.form.get('end_time') or None,
            hidden='hidden' in request.form,
            pinned='pinned' in request.form,
            creator_id=current_user.id
        )
        db.session.add(exam)
        db.session.commit()
        flash('考试已创建', 'success')
        return redirect(url_for('exam.index'))
    return render_template('exam/edit.html', exam=None)

@exam_bp.route('/edit/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def edit_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    from models.exam import ExamQuestion
    import json
    if request.method == 'POST':
        exam.name = request.form['name']
        exam.description = request.form.get('description')
        exam.duration = int(request.form['duration'])
        exam.auto_submit_limit = int(request.form.get('auto_submit_limit', 0))
        exam.must_exam = 'must_exam' in request.form
        exam.instant_score = 'instant_score' in request.form
        exam.start_time = request.form.get('start_time') or None
        exam.end_time = request.form.get('end_time') or None
        exam.hidden = 'hidden' in request.form
        exam.pinned = 'pinned' in request.form
        # 新增：是否打乱题目
        exam.shuffle_questions = 'shuffle_questions' in request.form
        db.session.commit()
        # 题目编辑
        ExamQuestion.query.filter_by(exam_id=exam.id).delete()
        db.session.commit()
        q_count = int(request.form.get('question_count', 0))
        for i in range(1, q_count+1):
            q_type = request.form.get(f'q{i}_type')
            q_content = request.form.get(f'q{i}_content')
            q_score = int(request.form.get(f'q{i}_score', 1))
            if q_type in ['single', 'multiple']:
                q_options = request.form.get(f'q{i}_options')
                q_answer = request.form.get(f'q{i}_answer')
                options_json = json.dumps([opt.strip() for opt in q_options.split('\n') if opt.strip()])
                answer_json = json.dumps([a.strip() for a in q_answer.split(',') if a.strip()]) if q_type == 'multiple' else q_answer.strip()
                question = ExamQuestion(
                    exam_id=exam.id,
                    type=q_type,
                    content=q_content,
                    options=options_json,
                    answer=answer_json,
                    score=q_score
                )
            elif q_type == 'blank':
                blank_length = int(request.form.get(f'q{i}_blank_length', 10))
                q_answer = request.form.get(f'q{i}_answer')
                question = ExamQuestion(
                    exam_id=exam.id,
                    type=q_type,
                    content=q_content,
                    blank_length=blank_length,
                    answer=q_answer.strip(),
                    score=q_score
                )
            db.session.add(question)
        db.session.commit()
        flash('考试及题目已更新', 'success')
        return redirect(url_for('exam.index'))
    # 获取题目列表
    questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
    return render_template('exam/edit.html', exam=exam, questions=questions)

@exam_bp.route('/take/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def take_exam(exam_id):
    from models.exam import ExamQuestion, ExamPaper
    from datetime import datetime
    exam = Exam.query.get_or_404(exam_id)
    # 检查时间范围、币余额、必考逻辑
    questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
    # 新增：同类型题目打乱
    if getattr(exam, 'shuffle_questions', False):
        import random
        single = [q for q in questions if q.type == 'single']
        multiple = [q for q in questions if q.type == 'multiple']
        blank = [q for q in questions if q.type == 'blank']
        random.shuffle(single)
        random.shuffle(multiple)
        random.shuffle(blank)
        questions = single + multiple + blank
    from models.user import User
    user = User.query.get(current_user.id)
    if request.method == 'POST':
        # 统一使用 coins 字段
        if hasattr(user, 'coins') and user.coins >= 10:
            user.coins -= 10
            record = CoinRecord(
                user_id=user.id,
                amount=-10,
                reason='参与考试'
            )
            db.session.add(record)
            db.session.commit()
        else:
            flash('天际币不足，无法参与考试', 'error')
            return redirect(url_for('exam.index'))
        answers = {}
        for q in questions:
            answers[str(q.id)] = request.form.getlist(f'q{q.id}') if q.type == 'multiple' else request.form.get(f'q{q.id}')
        paper = ExamPaper(
            exam_id=exam.id,
            user_id=current_user.id,
            answers=str(answers),
            submitted_at=datetime.utcnow()
        )
        db.session.add(paper)
        db.session.commit()
        flash('考试已提交，已扣除10天际币', 'success')
        return redirect(url_for('exam_transcript.transcript', exam_id=exam.id))
    return render_template('exam/take.html', exam=exam, questions=questions)

@exam_bp.route('/set_graders/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def set_graders(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    from models.user import User
    users = User.query.all()
    selected_graders = [g.user_id for g in exam.graders]
    if request.method == 'POST':
        grader_ids = request.form.getlist('graders')
        exam.graders = [User.query.get(int(uid)) for uid in grader_ids]
        db.session.commit()
        flash('批卷人已设置', 'success')
        return redirect(url_for('exam.index'))
    return render_template('exam/set_graders.html', exam=exam, users=users, selected_graders=selected_graders)

@exam_bp.route('/grade/<int:exam_id>')
@login_required
def grade(exam_id):
    from models.exam import ExamPaper, ExamQuestion
    exam = Exam.query.get_or_404(exam_id)
    # 仅管理员或批卷人可访问
    if not (getattr(current_user, 'is_admin', False) or current_user.id in [g.user_id for g in exam.graders]):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    import random
    # 随机分发一道未批改试卷
    papers = ExamPaper.query.filter_by(exam_id=exam.id, graded=False).all()
    paper = random.choice(papers) if papers else None
    if paper:
        paper.questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
        paper.answers = eval(paper.answers)
        paper.scores = {}
        # 不显示考生信息
        paper.user_id = None
        return render_template('exam/grade.html', exam=exam, papers=[paper])
    else:
        return render_template('exam/grade.html', exam=exam, papers=[])

@exam_bp.route('/grade_paper/<int:paper_id>', methods=['POST'])
@login_required
def grade_paper(paper_id):
    from models.exam import ExamPaper, ExamQuestion
    paper = ExamPaper.query.get_or_404(paper_id)
    exam = Exam.query.get_or_404(paper.exam_id)
    if not (getattr(current_user, 'is_admin', False) or current_user.id in [g.user_id for g in exam.graders]):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    questions = ExamQuestion.query.filter_by(exam_id=exam.id).all()
    answers = eval(paper.answers)
    total_score = 0
    for q in questions:
        if q.type == 'blank':
            score = int(request.form.get(f'score_{q.id}', 0))
        else:
            # 自动批改
            if q.type == 'single':
                score = q.score if answers.get(str(q.id)) == q.answer else 0
            elif q.type == 'multiple':
                score = q.score if set(answers.get(str(q.id), [])) == set(eval(q.answer)) else 0
            else:
                score = 0
        total_score += score
    paper.score = total_score
    paper.graded = True
    paper.grader_id = current_user.id
    db.session.commit()
    # 分数达到70分，写入用户可申请创造者权限标记（伪代码，需集成实际权限系统）
    # OP2权限：总分70%达标
    total_possible = sum(q.score for q in questions)
    if total_score >= total_possible * 0.7:
        from models.user import User
        user = User.query.get(paper.user_id)
        if hasattr(user, 'can_apply_op2'):
            user.can_apply_op2 = True
            db.session.commit()
    flash('批改完成', 'success')
    return redirect(url_for('exam.grade', exam_id=exam.id))

@exam_bp.route('/toggle_hidden/<int:exam_id>')
@login_required
def toggle_hidden(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    exam.hidden = not exam.hidden
    db.session.commit()
    return redirect(url_for('exam.index'))

@exam_bp.route('/toggle_pinned/<int:exam_id>')
@login_required
def toggle_pinned(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    exam.pinned = not exam.pinned
    db.session.commit()
    return redirect(url_for('exam.index'))

@exam_bp.route('/delete/<int:exam_id>')
@login_required
def delete_exam(exam_id):
    exam = Exam.query.get_or_404(exam_id)
    if not getattr(current_user, 'is_admin', False):
        flash('无权限', 'error')
        return redirect(url_for('exam.index'))
    db.session.delete(exam)
    db.session.commit()
    flash('考试已删除', 'success')
    return redirect(url_for('exam.index'))

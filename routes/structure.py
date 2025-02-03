from flask import Blueprint, render_template, request, jsonify, current_app, send_file, redirect, url_for, abort
from flask_login import login_required, current_user
from models.structure import StructureSlot, StructureShare, SlotCard, SlotCardUsage
from models.user import CoinRecord
from extensions import db, redis
import os
import shutil
import uuid
from werkzeug.utils import secure_filename

structure_bp = Blueprint('structure', __name__)

@structure_bp.app_template_global()
def get_structure_size(file_path):
    """获取结构文件大小(KB)"""
    try:
        return os.path.getsize(file_path) / 1024
    except:
        return 0

def get_available_slots(user_id, file_size):
    """获取用户可用的空槽位
    
    Args:
        user_id: 用户ID
        file_size: 文件大小(KB)
        
    Returns:
        list: 可用的槽位列表
    """
    return StructureSlot.query.filter(
        StructureSlot.user_id == user_id,
        StructureSlot.current_structure.is_(None),  # 槽位为空
        StructureSlot.size >= file_size  # 槽位大小足够
    ).all()

@structure_bp.route('/my-structures')
@login_required
def my_structures():
    slots = StructureSlot.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard/structures/my_structures.html', slots=slots)

@structure_bp.route('/structure-square')
def structure_square():
    shares = StructureShare.query.join(StructureSlot).filter(
        StructureSlot.current_structure.isnot(None)  # 确保槽位不为空
    ).order_by(StructureShare.created_at.desc()).all()
    return render_template('dashboard/structures/structure_square.html', 
        shares=shares,
        os=os,
        config=current_app.config
    )

@structure_bp.route('/buy-slot', methods=['POST'])
@login_required
def buy_slot():
    size = request.json.get('size')
    if not size or size < 5 or size > 500 or size % 5 != 0:
        return jsonify({'error': '无效的槽位大小'})
    
    cost = size // 5
    if current_user.coins < cost:
        return jsonify({'error': '天际币不足'})
    
    slot = StructureSlot(
        user_id=current_user.id,
        size=size
    )
    current_user.coins -= cost
    db.session.add(CoinRecord(
        user_id=current_user.id,
        amount=-cost,
        reason=f'购买{size}KB结构槽'
    ))
    db.session.add(slot)
    db.session.commit()
    
    return jsonify({'message': '购买成功'})

@structure_bp.route('/upgrade-slot/<int:slot_id>', methods=['POST'])
@login_required
def upgrade_slot(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此槽位'})
    
    new_size = request.json.get('size')
    if not new_size or new_size <= slot.size:
        return jsonify({'error': '新大小必须大于当前大小'})
    
    additional_size = new_size - slot.size
    cost = (additional_size // 5) * slot.remaining_clears
    
    if current_user.coins < cost:
        return jsonify({'error': '天际币不足'})
    
    current_user.coins -= cost
    slot.size = new_size
    db.session.add(CoinRecord(
        user_id=current_user.id,
        amount=-cost,
        reason=f'升级结构槽 #{slot.id} 到 {new_size}KB'
    ))
    db.session.commit()
    
    return jsonify({'message': '升级成功'})

@structure_bp.route('/upload-structure/<int:slot_id>', methods=['POST'])
@login_required
def upload_structure(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此槽位'})
    
    if slot.current_structure:
        return jsonify({'error': '槽位已有结构,请先清空'})
    
    upload_type = request.form.get('type')
    if upload_type not in ['local', 'game']:
        return jsonify({'error': '无效的上传类型'})
        
    structure_storage = current_app.config['STRUCTURE_STORAGE_PATH']
    slot_dir = os.path.join(structure_storage, str(slot_id))
    os.makedirs(slot_dir, exist_ok=True)
    
    if upload_type == 'local':
        # 本地文件上传
        if 'file' not in request.files:
            return jsonify({'error': '未选择文件'})
            
        file = request.files['file']
        if not file.filename.endswith('.schem'):
            return jsonify({'error': '仅支持.schem格式文件'})
            
        filename = secure_filename(file.filename)
        temp_path = os.path.join(slot_dir, 'temp_' + filename)
        file.save(temp_path)
        
        # 检查文件大小
        if get_structure_size(temp_path) > slot.size:
            os.remove(temp_path)
            return jsonify({'error': '文件大小超过槽位限制'})
            
        # 保存文件
        final_path = os.path.join(slot_dir, filename)
        os.rename(temp_path, final_path)
        slot.current_structure = filename
        db.session.commit()
        
    else:
        # 游戏内结构绑定
        structure_name = request.form.get('structure_name')
        if not structure_name:
            return jsonify({'error': '请输入结构名称'})
            
        game_structure_path = os.path.join(
            current_app.config['GAME_ROOT_PATH'],
            'config/worldedit/schematics',
            f'{structure_name}.schem'
        )
        
        if not os.path.exists(game_structure_path):
            return jsonify({'error': '找不到指定的结构文件'})
            
        # 检查文件大小
        if get_structure_size(game_structure_path) > slot.size:
            return jsonify({'error': '文件大小超过槽位限制'})
            
        # 复制文件
        filename = f'{structure_name}.schem'
        shutil.copy2(game_structure_path, os.path.join(slot_dir, filename))
        slot.current_structure = filename
        db.session.commit()
    
    return jsonify({'message': '上传成功'})

@structure_bp.route('/bind-structure/<int:slot_id>', methods=['POST'])
@login_required
def bind_structure(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此槽位'})
    
    if slot.current_structure:
        return jsonify({'error': '槽位已有结构'})
    
    structure_name = request.json.get('name')
    if not structure_name:
        return jsonify({'error': '未提供结构名'})
    
    # 检查游戏目录中是否存在该结构
    game_structure_path = os.path.join(
        current_app.config['GAME_ROOT_PATH'],
        'config/worldedit/schematics',
        f'{structure_name}.schem'
    )
    if not os.path.exists(game_structure_path):
        return jsonify({'error': '找不到该结构'})
    
    # 检查文件大小
    if get_structure_size(game_structure_path) > slot.size:
        return jsonify({'error': '结构超过槽位大小限制'})
    
    # 复制文件到槽位目录
    slot_dir = os.path.join(current_app.config['STRUCTURE_STORAGE_PATH'], str(slot.id))
    os.makedirs(slot_dir, exist_ok=True)
    shutil.copy2(game_structure_path, os.path.join(slot_dir, f'{structure_name}.schem'))
    
    slot.current_structure = f'{structure_name}.schem'
    db.session.commit()
    
    return jsonify({'message': '绑定成功'})

@structure_bp.route('/clear-slot/<int:slot_id>', methods=['POST'])
@login_required
def clear_slot(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此槽位'})
    
    if not slot.current_structure:
        return jsonify({'error': '槽位已是空的'})
    
    if slot.remaining_clears <= 0:
        # 销毁槽位
        slot_dir = os.path.join(current_app.config['STRUCTURE_STORAGE_PATH'], str(slot.id))
        if os.path.exists(slot_dir):
            shutil.rmtree(slot_dir)
        db.session.delete(slot)
    else:
        # 清空槽位
        slot_dir = os.path.join(current_app.config['STRUCTURE_STORAGE_PATH'], str(slot.id))
        if os.path.exists(slot_dir):
            shutil.rmtree(slot_dir)
            os.makedirs(slot_dir)  # 重新创建空目录
        slot.current_structure = None
        slot.remaining_clears -= 1
    
    db.session.commit()
    return jsonify({'message': '清空成功'})

@structure_bp.route('/sync-to-game/<int:slot_id>', methods=['POST'])
@login_required
def sync_to_game(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此结构'})
    
    if not slot.current_structure:
        return jsonify({'error': '槽位为空'})
    
    source_path = os.path.join(
        current_app.config['STRUCTURE_STORAGE_PATH'],
        str(slot.id),
        slot.current_structure
    )
    
    target_path = os.path.join(
        current_app.config['GAME_ROOT_PATH'],
        'config/worldedit/schematics',
        slot.current_structure
    )
    
    try:
        shutil.copy2(source_path, target_path)
        return jsonify({'message': '同步成功'})
    except Exception as e:
        return jsonify({'error': '同步失败'})

@structure_bp.route('/download-structure/<int:slot_id>', methods=['POST'])
@login_required
def download_structure(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权下载此结构'})
    
    # 如果是从广场下载，增加下载量
    share = StructureShare.query.filter_by(slot_id=slot_id).first()
    if share:
        share.downloads += 1
        db.session.commit()
    
    # 检查下载次数限制
    download_key = f'structure_download:{current_user.id}'
    download_count = redis.get(download_key)
    if download_count and int(download_count) >= 3:
        return jsonify({'error': '已达到每小时下载限制'})
    
    # 生成一次性下载链接
    token = str(uuid.uuid4())
    redis.setex(f'download_token:{token}', 300, str(slot.id))  # 5分钟有效期
    
    # 更新下载计数
    if download_count:
        redis.incr(download_key)
    else:
        redis.setex(download_key, 3600, '1') 
        
    return jsonify({
        'download_url': url_for('structure.download_file', token=token, _external=True).replace('http://', 'https://')
    })

@structure_bp.route('/download-file/<token>')
def download_file(token):
    slot_id = redis.get(f'download_token:{token}')
    if not slot_id:
        abort(404)
    
    slot = StructureSlot.query.get_or_404(int(slot_id))
    if not slot.current_structure:
        abort(404)
    
    file_path = os.path.join(
        current_app.config['STRUCTURE_STORAGE_PATH'],
        str(slot.id),
        slot.current_structure
    )
    
    if not os.path.exists(file_path):
        abort(404)
    
    return send_file(
        file_path,
        as_attachment=True,
        download_name=slot.current_structure,
        mimetype='application/octet-stream'  # 确保浏览器会下载文件
    )

@structure_bp.route('/share-structure/<int:slot_id>', methods=['POST'])
@login_required
def share_structure(slot_id):
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权分享此结构'})
    
    if not slot.current_structure:
        return jsonify({'error': '空槽位无法分享'})
    
    name = request.json.get('name')
    description = request.json.get('description')
    
    if not name or not description:
        return jsonify({'error': '请填写结构名称和介绍'})
    
    share = StructureShare(
        slot_id=slot.id,
        name=name,
        description=description,
        user_id=current_user.id
    )
    
    db.session.add(share)
    db.session.commit()
    
    return jsonify({'message': '分享成功'})

@structure_bp.route('/save-from-square/<int:share_id>', methods=['POST'])
@login_required
def save_from_square(share_id):
    share = StructureShare.query.get_or_404(share_id)
    slot_id = request.json.get('slot_id')
    if not slot_id:
        return jsonify({'error': '未指定目标槽位'})
    
    slot = StructureSlot.query.get_or_404(slot_id)
    if slot.user_id != current_user.id:
        return jsonify({'error': '无权操作此槽位'})
    
    if slot.current_structure:
        return jsonify({'error': '目标槽位不为空'})
    
    # 复制结构文件
    source_slot = StructureSlot.query.get(share.slot_id)
    source_path = os.path.join(
        current_app.config['STRUCTURE_STORAGE_PATH'],
        str(source_slot.id),
        source_slot.current_structure
    )
    
    if get_structure_size(source_path) > slot.size:
        return jsonify({'error': '结构超过槽位大小限制'})
    
    target_dir = os.path.join(current_app.config['STRUCTURE_STORAGE_PATH'], str(slot.id))
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy2(source_path, os.path.join(target_dir, source_slot.current_structure))
    
    slot.current_structure = source_slot.current_structure
    share.downloads += 1
    db.session.commit()
    
    return jsonify({'message': '保存成功'})

@structure_bp.route('/save-structure/<int:share_id>', methods=['POST'])
@login_required
def save_structure(share_id):
    share = StructureShare.query.get_or_404(share_id)
    source_slot = share.slot
    
    if not source_slot.current_structure:
        return jsonify({'error': '源结构不存在'})
    
    file_path = os.path.join(
        current_app.config['STRUCTURE_STORAGE_PATH'],
        str(source_slot.id),
        source_slot.current_structure
    )
    
    if not os.path.exists(file_path):
        return jsonify({'error': '找不到该结构'})
    
    file_size = get_structure_size(file_path)
    
    # 获取可用槽位
    available_slots = get_available_slots(current_user.id, file_size)
    if not available_slots:
        return jsonify({'error': '没有足够大的空槽位'})
    
    return jsonify({
        'slots': [{
            'id': slot.id,
            'size': slot.size
        } for slot in available_slots]
    })

# 管理员功能
@structure_bp.route('/admin/cards', methods=['GET', 'POST'])
@login_required
def generate_cards():
    if not current_user.is_admin:
        return redirect(url_for('dashboard.index'))
    
    if request.method == 'POST':
        size = request.json.get('size')
        count = request.json.get('count')
        uses = request.json.get('uses')
        
        if not all([size, count, uses]) or size < 5 or size > 500 or size % 5 != 0:
            return jsonify({'error': '参数无效'})
        
        code = str(uuid.uuid4()).replace('-', '')
        card = SlotCard(
            code=code,
            size=size,
            count=count,
            remaining_uses=uses
        )
        db.session.add(card)
        db.session.commit()
        
        return jsonify({
            'message': '生成成功',
            'code': code
        })
        
    return render_template('dashboard/structures/admin_cards.html')

@structure_bp.route('/redeem-card', methods=['POST'])
@login_required
def redeem_card():
    code = request.json.get('code')
    if not code:
        return jsonify({'error': '请输入兑换码'})
    
    card = SlotCard.query.filter_by(code=code).first()
    if not card:
        return jsonify({'error': '无效的兑换码'})
    
    if card.remaining_uses <= 0:
        return jsonify({'error': '兑换码已被使用完'})
    
    # 检查用户是否已经使用过这个兑换码
    usage = SlotCardUsage.query.filter_by(
        card_id=card.id,
        user_id=current_user.id
    ).first()
    
    if usage:
        return jsonify({'error': '您已经使用过这个兑换码了'})
    
    try:
        # 创建结构槽
        for _ in range(card.count):
            slot = StructureSlot(
                user_id=current_user.id,
                size=card.size
            )
            db.session.add(slot)
        
        # 记录使用记录
        usage = SlotCardUsage(
            card_id=card.id,
            user_id=current_user.id
        )
        db.session.add(usage)
        
        # 更新剩余使用次数
        card.remaining_uses -= 1
        db.session.commit()
        
        return jsonify({'message': '兑换成功'})
        
    except Exception as e:
        db.session.rollback()
        # 如果是唯一约束错误,说明用户重复使用
        if 'unique_card_usage' in str(e):
            return jsonify({'error': '您已经使用过这个兑换码了'})
        return jsonify({'error': '兑换失败,请重试'}) 
        return jsonify({'error': '兑换失败,请重试'}) 
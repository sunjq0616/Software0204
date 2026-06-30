from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from datetime import datetime
import random
import string

app = Flask(__name__)
app.config['SECRET_KEY'] = 'warehouse_secret_key_2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///warehouse.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, Warehouse, Product, Inventory, PurchaseOrder, Application, InOutOrder, OperationLog
db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'


def generate_order_no(prefix):
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_str = ''.join(random.choices(string.digits, k=4))
    return f'{prefix}{timestamp}{random_str}'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.route('/')
def index():
    if not current_user.is_authenticated:
        return render_template('login.html')
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return jsonify({'success': True, 'role': user.role, 'message': '登录成功'})
        return jsonify({'success': False, 'message': '用户名或密码错误'})
    
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'success': True, 'message': '退出成功'})


@app.route('/api/current_user')
@login_required
def current_user_info():
    warehouse_name = current_user.warehouse.name if current_user.warehouse else None
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'name': current_user.name,
        'role': current_user.role,
        'warehouse_id': current_user.warehouse_id,
        'warehouse_name': warehouse_name
    })


@app.route('/api/warehouses')
@login_required
def get_warehouses():
    warehouses = Warehouse.query.all()
    return jsonify([{'id': w.id, 'code': w.code, 'name': w.name, 'type': w.type, 'manager': w.manager} for w in warehouses])


@app.route('/api/products')
@login_required
def get_products():
    products = Product.query.all()
    return jsonify([{
        'id': p.id, 'code': p.code, 'name': p.name, 'unit': p.unit,
        'spec': p.spec, 'shelf_life': p.shelf_life
    } for p in products])


@app.route('/api/products', methods=['POST'])
@login_required
def add_product():
    if current_user.role not in ['大仓管理员', '审核人']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    data = request.json
    product = Product(
        code=data['code'], name=data['name'], unit=data['unit'],
        spec=data.get('spec', ''), shelf_life=data.get('shelf_life', 0)
    )
    db.session.add(product)
    
    for warehouse in Warehouse.query.all():
        inventory = Inventory(warehouse_id=warehouse.id, product_id=product.id, quantity=0)
        db.session.add(inventory)
    
    db.session.commit()
    return jsonify({'success': True, 'message': '商品添加成功'})


@app.route('/api/inventory')
@login_required
def get_inventory():
    if current_user.role == '小仓操作员':
        inventories = Inventory.query.filter_by(warehouse_id=current_user.warehouse_id).all()
    else:
        inventories = Inventory.query.all()
    
    result = []
    for inv in inventories:
        result.append({
            'id': inv.id,
            'warehouse_id': inv.warehouse_id,
            'warehouse_name': inv.warehouse.name,
            'product_id': inv.product_id,
            'product_code': inv.product.code,
            'product_name': inv.product.name,
            'product_unit': inv.product.unit,
            'product_spec': inv.product.spec,
            'quantity': inv.quantity
        })
    return jsonify(result)


@app.route('/api/purchase_orders', methods=['GET', 'POST'])
@login_required
def purchase_orders():
    if request.method == 'POST':
        if current_user.role != '大仓管理员':
            return jsonify({'success': False, 'message': '权限不足'})
        
        data = request.json
        order = PurchaseOrder(
            order_no=generate_order_no('PO'),
            supplier=data['supplier'],
            product_id=data['product_id'],
            quantity=data['quantity'],
            status='待审核',
            created_by=current_user.id
        )
        db.session.add(order)
        
        log = OperationLog(
            user_id=current_user.id,
            action='创建大仓采购入库单',
            detail=f'创建采购单 {order.order_no}，供应商：{data["supplier"]}',
            order_no=order.order_no
        )
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '采购单创建成功'})
    
    if current_user.role == '小仓操作员':
        return jsonify([])
    
    orders = PurchaseOrder.query.order_by(PurchaseOrder.created_at.desc()).all()
    return jsonify([{
        'id': o.id, 'order_no': o.order_no, 'supplier': o.supplier,
        'product_id': o.product_id, 'product_name': o.product.name,
        'quantity': o.quantity, 'status': o.status,
        'audit_quantity': o.audit_quantity, 'reject_reason': o.reject_reason,
        'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'creator_name': o.creator.name if o.creator else ''
    } for o in orders])


@app.route('/api/purchase_orders/<int:order_id>/audit', methods=['POST'])
@login_required
def audit_purchase_order(order_id):
    if current_user.role not in ['大仓管理员', '审核人']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    data = request.json
    order = PurchaseOrder.query.get_or_404(order_id)
    action = data['action']
    
    if action == 'approve':
        audit_quantity = data.get('audit_quantity', order.quantity)
        order.status = '已通过'
        order.audit_quantity = audit_quantity
        order.audited_by = current_user.id
        order.audited_at = datetime.now()
        
        inventory = Inventory.query.filter_by(warehouse_id=1, product_id=order.product_id).first()
        inventory.quantity += audit_quantity
        
        log = OperationLog(
            user_id=current_user.id,
            action='审核通过大仓采购单',
            detail=f'审核通过采购单 {order.order_no}，审核数量：{audit_quantity}',
            order_no=order.order_no
        )
        db.session.add(log)
        
    elif action == 'reject':
        order.status = '已驳回'
        order.reject_reason = data['reject_reason']
        order.audited_by = current_user.id
        order.audited_at = datetime.now()
        
        log = OperationLog(
            user_id=current_user.id,
            action='驳回大仓采购单',
            detail=f'驳回采购单 {order.order_no}，原因：{data["reject_reason"]}',
            order_no=order.order_no
        )
        db.session.add(log)
    
    db.session.commit()
    return jsonify({'success': True, 'message': '审核完成'})


@app.route('/api/applications', methods=['GET', 'POST'])
@login_required
def applications():
    if request.method == 'POST':
        if current_user.role != '小仓操作员':
            return jsonify({'success': False, 'message': '权限不足'})
        
        data = request.json
        app_type = data['type']
        app = Application(
            app_no=generate_order_no('AP'),
            type=app_type,
            warehouse_id=current_user.warehouse_id,
            product_id=data['product_id'],
            quantity=data['quantity'],
            expect_date=data.get('expect_date'),
            reason=data.get('reason', ''),
            source=data.get('source', ''),
            status='待审核',
            created_by=current_user.id
        )
        db.session.add(app)
        
        log = OperationLog(
            user_id=current_user.id,
            action=f'创建小仓{"要货" if app_type == "要货" else "退库" if app_type == "退库" else "入库"}申请',
            detail=f'创建申请单 {app.app_no}',
            order_no=app.app_no
        )
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '申请单创建成功'})
    
    if current_user.role == '小仓操作员':
        apps = Application.query.filter_by(warehouse_id=current_user.warehouse_id).order_by(Application.created_at.desc()).all()
    else:
        apps = Application.query.order_by(Application.created_at.desc()).all()
    
    return jsonify([{
        'id': a.id, 'app_no': a.app_no, 'type': a.type,
        'warehouse_id': a.warehouse_id, 'warehouse_name': a.warehouse.name,
        'product_id': a.product_id, 'product_name': a.product.name,
        'quantity': a.quantity, 'expect_date': a.expect_date,
        'reason': a.reason, 'source': a.source, 'status': a.status,
        'audit_quantity': a.audit_quantity, 'reject_reason': a.reject_reason,
        'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'creator_name': a.creator.name if a.creator else ''
    } for a in apps])


@app.route('/api/applications/<int:app_id>/audit', methods=['POST'])
@login_required
def audit_application(app_id):
    if current_user.role not in ['大仓管理员', '审核人']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    data = request.json
    app = Application.query.get_or_404(app_id)
    action = data['action']
    
    if action == 'approve':
        audit_quantity = data.get('audit_quantity', app.quantity)
        app.status = '已通过'
        app.audit_quantity = audit_quantity
        app.audited_by = current_user.id
        app.audited_at = datetime.now()
        
        if app.type == '要货':
            big_inventory = Inventory.query.filter_by(warehouse_id=1, product_id=app.product_id).first()
            if big_inventory.quantity < audit_quantity:
                return jsonify({'success': False, 'message': '大仓库存不足'})
            big_inventory.quantity -= audit_quantity
            
            out_order = InOutOrder(
                order_no=generate_order_no('OUT'),
                warehouse_id=1,
                product_id=app.product_id,
                quantity=audit_quantity,
                type='出库',
                source=f'小仓要货申请 {app.app_no}',
                status='已完成',
                related_app_id=app.id,
                created_by=current_user.id,
                created_at=datetime.now()
            )
            db.session.add(out_order)
            
        elif app.type == '退库':
            small_inventory = Inventory.query.filter_by(warehouse_id=app.warehouse_id, product_id=app.product_id).first()
            if small_inventory.quantity < audit_quantity:
                return jsonify({'success': False, 'message': '小仓库存不足'})
            small_inventory.quantity -= audit_quantity
            
            big_inventory = Inventory.query.filter_by(warehouse_id=1, product_id=app.product_id).first()
            big_inventory.quantity += audit_quantity
            
            in_order = InOutOrder(
                order_no=generate_order_no('IN'),
                warehouse_id=1,
                product_id=app.product_id,
                quantity=audit_quantity,
                type='入库',
                source=f'小仓退库申请 {app.app_no}',
                status='已完成',
                related_app_id=app.id,
                created_by=current_user.id,
                created_at=datetime.now()
            )
            db.session.add(in_order)
            
        elif app.type == '入库':
            small_inventory = Inventory.query.filter_by(warehouse_id=app.warehouse_id, product_id=app.product_id).first()
            small_inventory.quantity += audit_quantity
            
            in_order = InOutOrder(
                order_no=generate_order_no('IN'),
                warehouse_id=app.warehouse_id,
                product_id=app.product_id,
                quantity=audit_quantity,
                type='入库',
                source=app.source or f'小仓入库申请 {app.app_no}',
                status='已完成',
                related_app_id=app.id,
                created_by=current_user.id,
                created_at=datetime.now()
            )
            db.session.add(in_order)
        
        log = OperationLog(
            user_id=current_user.id,
            action='审核通过小仓申请',
            detail=f'审核通过申请单 {app.app_no}，审核数量：{audit_quantity}',
            order_no=app.app_no
        )
        db.session.add(log)
        
    elif action == 'reject':
        app.status = '已驳回'
        app.reject_reason = data['reject_reason']
        app.audited_by = current_user.id
        app.audited_at = datetime.now()
        
        log = OperationLog(
            user_id=current_user.id,
            action='驳回小仓申请',
            detail=f'驳回申请单 {app.app_no}，原因：{data["reject_reason"]}',
            order_no=app.app_no
        )
        db.session.add(log)
    
    db.session.commit()
    return jsonify({'success': True, 'message': '审核完成'})


@app.route('/api/out_orders', methods=['GET', 'POST'])
@login_required
def out_orders():
    if request.method == 'POST':
        if current_user.role != '小仓操作员':
            return jsonify({'success': False, 'message': '权限不足'})
        
        data = request.json
        product_id = data['product_id']
        quantity = data['quantity']
        
        inventory = Inventory.query.filter_by(
            warehouse_id=current_user.warehouse_id,
            product_id=product_id
        ).first()
        
        if not inventory or inventory.quantity < quantity:
            return jsonify({'success': False, 'message': '库存不足，无法提交'})
        
        order = InOutOrder(
            order_no=generate_order_no('OUT'),
            warehouse_id=current_user.warehouse_id,
            product_id=product_id,
            quantity=quantity,
            type='出库',
            source=data.get('source', ''),
            status='待审核',
            created_by=current_user.id
        )
        db.session.add(order)
        
        log = OperationLog(
            user_id=current_user.id,
            action='创建小仓出库单',
            detail=f'创建出库单 {order.order_no}',
            order_no=order.order_no
        )
        db.session.add(log)
        
        db.session.commit()
        return jsonify({'success': True, 'message': '出库单创建成功，待审核'})
    
    if current_user.role == '小仓操作员':
        orders = InOutOrder.query.filter_by(
            warehouse_id=current_user.warehouse_id,
            type='出库'
        ).order_by(InOutOrder.created_at.desc()).all()
    else:
        orders = InOutOrder.query.filter_by(type='出库').order_by(InOutOrder.created_at.desc()).all()
    
    return jsonify([{
        'id': o.id, 'order_no': o.order_no,
        'warehouse_id': o.warehouse_id, 'warehouse_name': o.warehouse.name,
        'product_id': o.product_id, 'product_name': o.product.name,
        'quantity': o.quantity, 'type': o.type, 'source': o.source,
        'status': o.status, 'reject_reason': o.reject_reason,
        'created_at': o.created_at.strftime('%Y-%m-%d %H:%M:%S'),
        'creator_name': o.creator.name if o.creator else ''
    } for o in orders])


@app.route('/api/out_orders/<int:order_id>/audit', methods=['POST'])
@login_required
def audit_out_order(order_id):
    if current_user.role not in ['大仓管理员', '审核人']:
        return jsonify({'success': False, 'message': '权限不足'})
    
    data = request.json
    order = InOutOrder.query.get_or_404(order_id)
    action = data['action']
    
    if action == 'approve':
        order.status = '已通过'
        order.audited_by = current_user.id
        order.audited_at = datetime.now()
        
        inventory = Inventory.query.filter_by(
            warehouse_id=order.warehouse_id,
            product_id=order.product_id
        ).first()
        inventory.quantity -= order.quantity
        
        log = OperationLog(
            user_id=current_user.id,
            action='审核通过小仓出库单',
            detail=f'审核通过出库单 {order.order_no}',
            order_no=order.order_no
        )
        db.session.add(log)
        
    elif action == 'reject':
        order.status = '已驳回'
        order.reject_reason = data['reject_reason']
        order.audited_by = current_user.id
        order.audited_at = datetime.now()
        
        log = OperationLog(
            user_id=current_user.id,
            action='驳回小仓出库单',
            detail=f'驳回出库单 {order.order_no}，原因：{data["reject_reason"]}',
            order_no=order.order_no
        )
        db.session.add(log)
    
    db.session.commit()
    return jsonify({'success': True, 'message': '审核完成'})


@app.route('/api/logs')
@login_required
def get_logs():
    if current_user.role == '小仓操作员':
        logs = OperationLog.query.filter_by(user_id=current_user.id).order_by(OperationLog.created_at.desc()).limit(100).all()
    else:
        logs = OperationLog.query.order_by(OperationLog.created_at.desc()).limit(200).all()
    
    return jsonify([{
        'id': l.id, 'user_name': l.user.name, 'action': l.action,
        'detail': l.detail, 'order_no': l.order_no,
        'created_at': l.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for l in logs])


def init_db():
    with app.app_context():
        db.create_all()
        
        if Warehouse.query.count() == 0:
            warehouse1 = Warehouse(code='BC001', name='主大仓', type='大仓', manager='张经理')
            warehouse2 = Warehouse(code='XC001', name='一号小仓', type='小仓', manager='李主管')
            warehouse3 = Warehouse(code='XC002', name='二号小仓', type='小仓', manager='王主管')
            db.session.add_all([warehouse1, warehouse2, warehouse3])
        
        if User.query.count() == 0:
            from werkzeug.security import generate_password_hash
            user1 = User(username='dacang', name='大仓管理员', role='大仓管理员', password_hash=generate_password_hash('123456'))
            user2 = User(username='xiaocang1', name='小仓1操作员', role='小仓操作员', warehouse_id=2, password_hash=generate_password_hash('123456'))
            user3 = User(username='xiaocang2', name='小仓2操作员', role='小仓操作员', warehouse_id=3, password_hash=generate_password_hash('123456'))
            user4 = User(username='shenhe', name='审核人', role='审核人', password_hash=generate_password_hash('123456'))
            db.session.add_all([user1, user2, user3, user4])
        
        if Product.query.count() == 0:
            products = [
                Product(code='CP001', name='笔记本电脑', unit='台', spec='15.6英寸', shelf_life=36),
                Product(code='CP002', name='无线鼠标', unit='个', spec='黑色', shelf_life=24),
                Product(code='CP003', name='键盘', unit='个', spec='机械键盘', shelf_life=24),
                Product(code='CP004', name='显示器', unit='台', spec='27英寸', shelf_life=36),
                Product(code='CP005', name='U盘', unit='个', spec='64GB', shelf_life=60)
            ]
            db.session.add_all(products)
            
            db.session.flush()
            
            for warehouse in Warehouse.query.all():
                for product in products:
                    inventory = Inventory(warehouse_id=warehouse.id, product_id=product.id, quantity=0)
                    db.session.add(inventory)
        
        db.session.commit()


if __name__ == '__main__':
    init_db()
    app.run(debug=True, port=5000)

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(UserMixin, db.Model):
    '''用户模型：存储系统用户信息，包括角色和关联的小仓'''
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'))
    
    warehouse = db.relationship('Warehouse', backref='users')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Warehouse(db.Model):
    '''仓库模型：存储大仓和小仓的基础信息'''
    __tablename__ = 'warehouses'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(10), nullable=False)
    manager = db.Column(db.String(50))


class Product(db.Model):
    '''商品模型：存储商品的基础信息'''
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(10), nullable=False)
    spec = db.Column(db.String(100))
    shelf_life = db.Column(db.Integer)


class Inventory(db.Model):
    '''库存模型：存储每个仓库每个商品的实时库存'''
    __tablename__ = 'inventory'
    
    id = db.Column(db.Integer, primary_key=True)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    
    warehouse = db.relationship('Warehouse', backref='inventories')
    product = db.relationship('Product', backref='inventories')
    
    __table_args__ = (db.UniqueConstraint('warehouse_id', 'product_id', name='_warehouse_product_uc'),)


class PurchaseOrder(db.Model):
    '''大仓采购入库单模型'''
    __tablename__ = 'purchase_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(30), unique=True, nullable=False)
    supplier = db.Column(db.String(100), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False)
    audit_quantity = db.Column(db.Integer)
    reject_reason = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    audited_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    audited_at = db.Column(db.DateTime)
    
    product = db.relationship('Product', backref='purchase_orders')
    creator = db.relationship('User', foreign_keys=[created_by])
    auditor = db.relationship('User', foreign_keys=[audited_by])


class Application(db.Model):
    '''小仓申请模型：要货申请、退库申请、入库申请'''
    __tablename__ = 'applications'
    
    id = db.Column(db.Integer, primary_key=True)
    app_no = db.Column(db.String(30), unique=True, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    expect_date = db.Column(db.String(20))
    reason = db.Column(db.String(200))
    source = db.Column(db.String(200))
    status = db.Column(db.String(20), nullable=False)
    audit_quantity = db.Column(db.Integer)
    reject_reason = db.Column(db.String(200))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    audited_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    audited_at = db.Column(db.DateTime)
    
    warehouse = db.relationship('Warehouse', backref='applications')
    product = db.relationship('Product', backref='applications')
    creator = db.relationship('User', foreign_keys=[created_by])
    auditor = db.relationship('User', foreign_keys=[audited_by])


class InOutOrder(db.Model):
    '''出入库单模型'''
    __tablename__ = 'inout_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(30), unique=True, nullable=False)
    warehouse_id = db.Column(db.Integer, db.ForeignKey('warehouses.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    type = db.Column(db.String(10), nullable=False)
    source = db.Column(db.String(200))
    status = db.Column(db.String(20), nullable=False)
    reject_reason = db.Column(db.String(200))
    related_app_id = db.Column(db.Integer, db.ForeignKey('applications.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.now)
    audited_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    audited_at = db.Column(db.DateTime)
    
    warehouse = db.relationship('Warehouse', backref='inout_orders')
    product = db.relationship('Product', backref='inout_orders')
    related_app = db.relationship('Application', backref='inout_orders')
    creator = db.relationship('User', foreign_keys=[created_by])
    auditor = db.relationship('User', foreign_keys=[audited_by])


class OperationLog(db.Model):
    '''操作日志模型：记录所有操作流水'''
    __tablename__ = 'operation_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    detail = db.Column(db.String(500))
    order_no = db.Column(db.String(30))
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref='logs')

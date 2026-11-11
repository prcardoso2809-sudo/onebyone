from db import db

class configserver(db.Model):
    __tablename__ = 'configserver'
    id = db.Column(db.Integer, primary_key=True)
    guild_id = db.Column(db.String(50), unique=True, nullable=False) 
    canal_jogo_id = db.Column(db.String(50), nullable=True)         
    prefixo = db.Column(db.String(10), default="@-")

class historia(db.Model):
    __tablename__ = 'hinstorias'
    __bind_key__ = 'historia_db'
    id = db.Column(db.Integer, primary_key=True)
    guild_id = db.Column(db.String(50), nullable=False)
    texto_completo = db.Column(db.Text, nullable=False)             
    vencedor_id = db.Column(db.String(50), nullable=False)          
    data_criacao = db.Column(db.DateTime, default=db.func.now())
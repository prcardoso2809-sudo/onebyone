import os
import requests
from flask import Flask, url_for, session, redirect, render_template, request
from dotenv import load_dotenv
from config import configserver, historia
from db import db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "chave_secreta_padrao")

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
BOT_TOKEN = os.getenv("BOT_TOKEN")
REDIRECT_URI = "http://localhost:5000/callback"

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///configserver.db'
app.config['SQLALCHEMY_BINDS'] = {
    'historia_db': 'sqlite:///hinstorias.db'
}
db.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    discord_login_url = (
        f"https://discord.com/api/oauth2/authorize?client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code&scope=identify%20guilds"
    )
    return redirect(discord_login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        return redirect(url_for('index'))
    
    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': REDIRECT_URI,
        'scope': 'identify guilds'
    }
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    resp = requests.post('https://discord.com/api/oauth2/token', data=data, headers=headers)
    
    if resp.status_code == 200:
        token_json = resp.json()
        session['discord_token'] = token_json.get('access_token')
        return redirect(url_for('dashboard'))
    
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'discord_token' not in session:
        return redirect(url_for('index'))

    headers = {'Authorization': f"Bearer {session['discord_token']}"}
    
    user_resp = requests.get('https://discord.com/api/users/@me', headers=headers)
    user_data = user_resp.json() if user_resp.status_code == 200 else None

    guilds_resp = requests.get('https://discord.com/api/users/@me/guilds', headers=headers)
    guilds_data = guilds_resp.json() if guilds_resp.status_code == 200 else []

    bot_guilds_resp = requests.get(
        'https://discord.com/api/v10/users/@me/guilds',
        headers={'Authorization': f"Bot {BOT_TOKEN}"}
    )
    
    bot_online = False
    bot_guild_ids = []
    if bot_guilds_resp.status_code == 200:
        bot_online = True
        bot_guild_ids = [str(g['id']) for g in bot_guilds_resp.json()]

    servidores_gerenciaveis = []
    for g in guilds_data:
        perms = int(g.get('permissions', 0))
        is_admin = (perms & 0x8) == 0x8 or g.get('owner', False)
        
        if is_admin:
            guild_id_str = str(g['id'])
            esta_no_servidor = guild_id_str in bot_guild_ids
            
            g_copy = dict(g)
            g_copy['is_admin'] = True
            g_copy['bot_presente'] = esta_no_servidor
            servidores_gerenciaveis.append(g_copy)

    return render_template(
        'dashboard.html', 
        user=user_data, 
        guilds=servidores_gerenciaveis, 
        view='servidores',
        bot_online=bot_online,
        client_id=CLIENT_ID
    )

@app.route('/historias/<guild_id>')
def ver_historias_servidor(guild_id):
    if 'discord_token' not in session:
        return redirect(url_for('index'))

    headers = {'Authorization': f"Bearer {session['discord_token']}"}
    user_resp = requests.get('https://discord.com/api/users/@me', headers=headers)
    user_data = user_resp.json() if user_resp.status_code == 200 else None

    # Busca apenas as histórias daquele guild_id específico
    historias_servidor = historia.query.filter_by(guild_id=str(guild_id)).all()
    
    return render_template(
        'dashboard.html', 
        user=user_data, 
        historias=historias_servidor, 
        view='historias',
        guild_id=guild_id
    )

@app.route('/deletar_historia/<int:historia_id>', methods=['POST'])
def deletar_historia(historia_id):
    if 'discord_token' not in session:
        return redirect(url_for('index'))

    h = historia.query.get(historia_id)
    if h:
        guild_id = h.guild_id
        db.session.delete(h)
        db.session.commit()
        return redirect(url_for('ver_historias_servidor', guild_id=guild_id))
    
    return redirect(url_for('dashboard'))

@app.route('/configurar/<guild_id>', methods=['GET', 'POST'])
def configurar(guild_id):
    if 'discord_token' not in session:
        return redirect(url_for('index'))

    headers = {'Authorization': f"Bearer {session['discord_token']}"}
    user_resp = requests.get('https://discord.com/api/users/@me', headers=headers)
    user_data = user_resp.json() if user_resp.status_code == 200 else None

    bot_guilds_resp = requests.get(
        'https://discord.com/api/v10/users/@me/guilds',
        headers={'Authorization': f"Bot {BOT_TOKEN}"}
    )
    bot_online = bot_guilds_resp.status_code == 200

    channels = []
    channels_resp = requests.get(
        f"https://discord.com/api/v10/guilds/{guild_id}/channels",
        headers={"Authorization": f"Bot {BOT_TOKEN}"}
    )
    if channels_resp.status_code == 200:
        all_channels = channels_resp.json()
        channels = [c for c in all_channels if c.get('type') == 0]

    config = configserver.query.filter_by(guild_id=str(guild_id)).first()

    if request.method == 'POST':
        novo_canal = request.form.get('canal_jogo_id')
        novo_prefixo = request.form.get('prefixo')

        if not config:
            config = configserver(
                guild_id=str(guild_id),
                canal_jogo_id=novo_canal if novo_canal else None,
                prefixo=novo_prefixo if novo_prefixo else '@-'
            )
            db.session.add(config)
        else:
            config.canal_jogo_id = novo_canal if novo_canal else None
            config.prefixo = novo_prefixo if novo_prefixo else '@-'

        db.session.commit()
        return redirect(url_for('dashboard'))

    return render_template(
        'configurar.html', 
        config=config, 
        guild_id=guild_id, 
        user=user_data, 
        channels=channels,
        bot_online=bot_online
    )

# Rota para listar os servidores em comum do usuário logado (sem precisar ser admin)
@app.route('/publico/servidores')
def publico_servidores():
    if 'discord_token' not in session:
        return redirect(url_for('login'))

    headers = {'Authorization': f"Bearer {session['discord_token']}"}
    
    # Puxa os dados do usuário e os servidores dele no Discord
    user_resp = requests.get('https://discord.com/api/users/@me', headers=headers)
    user_data = user_resp.json() if user_resp.status_code == 200 else None

    guilds_resp = requests.get('https://discord.com/api/users/@me/guilds', headers=headers)
    guilds_data = guilds_resp.json() if guilds_resp.status_code == 200 else []

    # Puxa a lista de servidores em que o BOT está conectado
    bot_guilds_resp = requests.get(
        'https://discord.com/api/v10/users/@me/guilds',
        headers={'Authorization': f"Bot {BOT_TOKEN}"}
    )
    
    bot_guild_ids = []
    if bot_guilds_resp.status_code == 200:
        bot_guild_ids = [str(g['id']) for g in bot_guilds_resp.json()]

    # Filtra apenas os servidores onde o usuário E o bot estão juntos (em comum)
    servidores_em_comum = []
    for g in guilds_data:
        guild_id_str = str(g['id'])
        if guild_id_str in bot_guild_ids:
            servidores_em_comum.append({
                'id': guild_id_str,
                'name': g.get('name')
            })

    return render_template(
        'servidores_publicos.html', 
        user=user_data, 
        servidores=servidores_em_comum
    )

# Rota para ver as histórias daquele servidor em comum
@app.route('/publico/historias/<guild_id>')
def publico_historias_servidor(guild_id):
    if 'discord_token' not in session:
        return redirect(url_for('login'))

    headers = {'Authorization': f"Bearer {session['discord_token']}"}
    user_resp = requests.get('https://discord.com/api/users/@me', headers=headers)
    user_data = user_resp.json() if user_resp.status_code == 200 else None

    historias_servidor = historia.query.filter_by(guild_id=str(guild_id)).all()
    
    return render_template(
        'dashboard.html', 
        user=user_data, 
        historias=historias_servidor, 
        view='historias',
        guild_id=guild_id
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
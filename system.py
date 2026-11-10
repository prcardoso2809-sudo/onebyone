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

@app.route('/historias')
def ver_historias():
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

    todas_historias = historia.query.all()
    return render_template(
        'dashboard.html', 
        user=user_data, 
        historias=todas_historias, 
        view='historias',
        bot_online=bot_online
    )

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

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
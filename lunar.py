# bot.py
# -*- coding: utf-8 -*-
# Bot Discord completo: Ticket, Moderazione, Minigiochi (Tris vs bot/utente), Economia, AI (stub disattivata)
# Requisiti: python 3.10+, discord.py 2.x
# Avvio:
#   - pip install -U discord.py
#   - Imposta DISCORD_TOKEN nell'ambiente
#   - python bot.py

import os
import re
import json
import random
import asyncio
import time
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands, ui, ButtonStyle, Interaction
from discord.ext import commands, tasks

DATA_FILE = "data.json"

def now_ts():
    return int(time.time())

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "staff_roles": [],  # list of role ids
            "logs_channel_id": None,
            "ticket_category_id": None,
            "ticket_counter": 1,
            "tickets": {},  # ticket_channel_id -> {"owner_id": int, "claimed_by": int|None}
            "economy": {},  # user_id -> {"balance": int, "last_work": int, "inventory": [str]}
            "warns": {},    # guild_id -> {user_id: [{"by": int, "reason": str, "ts": int}]}
            "mutes": {},    # guild_id -> {user_id: unmute_ts}
            "bans": {},     # guild_id -> {user_id: unban_ts}
            "store": [
                {"name": "VIP Pass", "price": 500},
                {"name": "Badge", "price": 200},
                {"name": "Lucky Charm", "price": 350}
            ]
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)

DATA = load_data()

INTENTS = discord.Intents.default()
INTENTS.guilds = True
INTENTS.members = True
# message_content non necessario per slash commands

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.synced = False

    async def setup_hook(self):
        self.background_tasks.start()

    async def on_ready(self):
        # Sync slash commands
        if not self.synced:
            await self.tree.sync()
            self.synced = True
        print(f"Online come {self.user} ({self.user.id})")

        # Autocreate ticket category / logs channel se mancano
        for guild in self.guilds:
            await ensure_infra(guild)

    @tasks.loop(seconds=30)
    async def background_tasks(self):
        # Unmute programmati
        now = now_ts()
        for guild in self.guilds:
            g_id = str(guild.id)
            # Unmute
            mutes = DATA.get("mutes", {}).get(g_id, {})
            to_unmute = [int(uid) for uid, ts in mutes.items() if ts and now >= ts]
            for uid in to_unmute:
                member = guild.get_member(uid)
                if member:
                    await ensure_muted_role(guild)  # ensure role exists
                    muted_role = discord.utils.get(guild.roles, name="Muted")
                    if muted_role in member.roles:
                        try:
                            await member.remove_roles(muted_role, reason="Auto unmute (timer scaduto)")
                        except Exception:
                            pass
                # remove from schedule
                DATA["mutes"][g_id].pop(str(uid), None)
                save_data()

            # Unban
            bans = DATA.get("bans", {}).get(g_id, {})
            to_unban = [int(uid) for uid, ts in bans.items() if ts and now >= ts]
            for uid in to_unban:
                try:
                    await guild.unban(discord.Object(id=uid), reason="Auto unban (durata scaduta)")
                except Exception:
                    pass
                DATA["bans"][g_id].pop(str(uid), None)
                save_data()

    @background_tasks.before_loop
    async def before_tasks(self):
        await self.wait_until_ready()

bot = Bot()

# ---------- Utility e infrastruttura ----------

async def ensure_infra(guild: discord.Guild):
    # Logs channel
    logs_channel_id = DATA.get("logs_channel_id")
    logs_channel = guild.get_channel(logs_channel_id) if logs_channel_id else None
    if logs_channel is None:
        # crea canale mod-logs se non esiste
        existing = discord.utils.get(guild.text_channels, name="mod-logs")
        if existing:
            logs_channel = existing
        else:
            try:
                logs_channel = await guild.create_text_channel("mod-logs", reason="Canale log moderazione")
            except Exception:
                logs_channel = None
        DATA["logs_channel_id"] = logs_channel.id if logs_channel else None
        save_data()

    # Ticket category
    ticket_cat_id = DATA.get("ticket_category_id")
    ticket_cat = guild.get_channel(ticket_cat_id) if ticket_cat_id else None
    if ticket_cat is None or not isinstance(ticket_cat, discord.CategoryChannel):
        # crea categoria tickets se non esiste
        existing_cat = discord.utils.get(guild.categories, name="tickets")
        if existing_cat:
            ticket_cat = existing_cat
        else:
            try:
                ticket_cat = await guild.create_category("tickets", reason="Categoria per i ticket")
            except Exception:
                ticket_cat = None
        DATA["ticket_category_id"] = ticket_cat.id if ticket_cat else None
        save_data()

async def ensure_muted_role(guild: discord.Guild):
    role = discord.utils.get(guild.roles, name="Muted")
    if role is None:
        try:
            role = await guild.create_role(name="Muted", reason="Ruolo mute")
            # aggiorna permessi nei canali
            for channel in guild.channels:
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                except Exception:
                    pass
        except Exception:
            role = None
    return role

async def log_action(guild: discord.Guild, embed: discord.Embed):
    logs_channel_id = DATA.get("logs_channel_id")
    ch = guild.get_channel(logs_channel_id) if logs_channel_id else None
    if ch is None:
        # tenta recupero o crea
        await ensure_infra(guild)
        ch = guild.get_channel(DATA.get("logs_channel_id"))
    if ch:
        try:
            await ch.send(embed=embed)
        except Exception:
            pass

def parse_duration(s: str | None) -> int | None:
    if not s:
        return None
    s = s.strip().lower()
    m = re.fullmatch(r"(\d+)([smhdw])", s)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2)
    mult = {"s":1, "m":60, "h":3600, "d":86400, "w":604800}[unit]
    return val * mult

def econ_user(user_id: int):
    uid = str(user_id)
    if uid not in DATA["economy"]:
        DATA["economy"][uid] = {"balance": 0, "last_work": 0, "inventory": []}
        save_data()
    return DATA["economy"][uid]

def add_money(user_id: int, amount: int):
    u = econ_user(user_id)
    u["balance"] += amount
    save_data()

def remove_money(user_id: int, amount: int) -> bool:
    u = econ_user(user_id)
    if u["balance"] >= amount:
        u["balance"] -= amount
        save_data()
        return True
    return False

def get_store():
    return DATA.get("store", [])

def ensure_warns(guild_id: int):
    g = str(guild_id)
    if "warns" not in DATA:
        DATA["warns"] = {}
    if g not in DATA["warns"]:
        DATA["warns"][g] = {}
    save_data()

def add_warn(guild_id: int, user_id: int, by_id: int, reason: str):
    ensure_warns(guild_id)
    g = str(guild_id)
    u = str(user_id)
    if u not in DATA["warns"][g]:
        DATA["warns"][g][u] = []
    DATA["warns"][g][u].append({"by": by_id, "reason": reason, "ts": now_ts()})
    save_data()

def list_warns(guild_id: int, user_id: int):
    ensure_warns(guild_id)
    return DATA["warns"].get(str(guild_id), {}).get(str(user_id), [])

def is_staff(member: discord.Member) -> bool:
    staff_roles = DATA.get("staff_roles", [])
    if not staff_roles:
        return member.guild_permissions.manage_guild or member.guild_permissions.manage_messages
    for rid in staff_roles:
        role = discord.utils.get(member.roles, id=rid)
        if role:
            return True
    return False

# ---------- Ticket System ----------

class TicketPanel(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Apri Ticket", style=ButtonStyle.primary, emoji="🎟️", custom_id="ticket_open")
    async def open_ticket(self, interaction: Interaction, button: ui.Button):
        await create_ticket(interaction)

async def create_ticket(interaction: Interaction):
    guild = interaction.guild
    user = interaction.user
    cat_id = DATA.get("ticket_category_id")
    category = guild.get_channel(cat_id) if cat_id else None
    if not category or not isinstance(category, discord.CategoryChannel):
        await ensure_infra(guild)
        category = guild.get_channel(DATA.get("ticket_category_id"))

    num = DATA.get("ticket_counter", 1)
    ch_name = f"ticket-{num:03d}"
    DATA["ticket_counter"] = num + 1
    save_data()

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
    }
    # Staff roles
    for rid in DATA.get("staff_roles", []):
        role = guild.get_role(rid)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel = await guild.create_text_channel(ch_name, category=category, overwrites=overwrites, reason="Nuovo ticket")
    DATA["tickets"][str(channel.id)] = {"owner_id": user.id, "claimed_by": None}
    save_data()

    view = TicketView(channel.id)
    embed = discord.Embed(title="Ticket aperto", description=f"Ciao {user.mention}, spiega pure il tuo problema.\nUno staffer ti risponderà al più presto.", color=0x2b2d31)
    await channel.send(content=f"{user.mention}", embed=embed, view=view)

    await interaction.response.send_message(f"Ticket creato: {channel.mention}", ephemeral=True)

class TicketView(ui.View):
    def __init__(self, ticket_channel_id: int):
        super().__init__(timeout=None)
        self.ticket_channel_id = ticket_channel_id

    @ui.button(label="Reclama", style=ButtonStyle.success, emoji="🛡️", custom_id="ticket_claim")
    async def claim(self, interaction: Interaction, button: ui.Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message("Solo lo staff può reclamare questo ticket.", ephemeral=True)

        info = DATA["tickets"].get(str(self.ticket_channel_id))
        if not info:
            return await interaction.response.send_message("Ticket non trovato.", ephemeral=True)
        if info.get("claimed_by"):
            return await interaction.response.send_message("Questo ticket è già stato reclamato.", ephemeral=True)

        info["claimed_by"] = interaction.user.id
        save_data()
        await interaction.response.send_message(f"Ticket reclamato da {interaction.user.mention}.")

    @ui.button(label="Chiudi", style=ButtonStyle.danger, emoji="🔒", custom_id="ticket_close")
    async def close(self, interaction: Interaction, button: ui.Button):
        channel = interaction.channel
        info = DATA["tickets"].get(str(channel.id))
        if not info:
            return await interaction.response.send_message("Ticket non trovato.", ephemeral=True)

        owner_id = info.get("owner_id")
        allowed = interaction.user.id == owner_id or is_staff(interaction.user)
        if not allowed:
            return await interaction.response.send_message("Solo il proprietario del ticket o lo staff può chiuderlo.", ephemeral=True)

        await interaction.response.send_message("Il ticket verrà chiuso tra 3 secondi...")
        await asyncio.sleep(3)
        try:
            await channel.delete(reason="Ticket chiuso")
        except Exception:
            pass
        DATA["tickets"].pop(str(channel.id), None)
        save_data()

# ---------- Minigiochi ----------

class TicTacToeButton(ui.Button):
    def __init__(self, row: int, col: int):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=row)
        self.row_idx = row
        self.col_idx = col

    async def callback(self, interaction: Interaction):
        view: "TicTacToeView" = self.view  # type: ignore
        await view.handle_move(interaction, self.row_idx, self.col_idx)

def check_winner(board, symbol):
    # righe, colonne, diagonali
    for i in range(3):
        if all(board[i][j] == symbol for j in range(3)): return True
        if all(board[j][i] == symbol for j in range(3)): return True
    if all(board[i][i] == symbol for i in range(3)): return True
    if all(board[i][2-i] == symbol for i in range(3)): return True
    return False

def board_full(board):
    return all(board[i][j] != "" for i in range(3) for j in range(3))

class TicTacToeView(ui.View):
    def __init__(self, player_x: int, player_o: int | None, vs_bot: bool):
        super().__init__(timeout=180)
        self.board = [["" for _ in range(3)] for _ in range(3)]
        self.player_x = player_x
        self.player_o = player_o  # None se bot
        self.turn = "X"
        self.vs_bot = vs_bot

        for r in range(3):
            for c in range(3):
                self.add_item(TicTacToeButton(r, c))

    async def handle_move(self, interaction: Interaction, r: int, c: int):
        user_id = interaction.user.id
        # Controllo turno
        if self.turn == "X" and user_id != self.player_x:
            return await interaction.response.send_message("Non è il tuo turno.", ephemeral=True)
        if self.turn == "O":
            if self.vs_bot:
                return await interaction.response.send_message("Attendi la mossa del bot.", ephemeral=True)
            if user_id != self.player_o:
                return await interaction.response.send_message("Non è il tuo turno.", ephemeral=True)
        # Casella già occupata
        if self.board[r][c] != "":
            return await interaction.response.send_message("Mossa non valida: casella già occupata.", ephemeral=True)

        # Effettua mossa utente
        self.board[r][c] = self.turn
        self.children[r*3 + c].label = self.turn
        self.children[r*3 + c].style = ButtonStyle.success if self.turn == "X" else ButtonStyle.danger
        self.children[r*3 + c].disabled = True

        # Controllo vittoria o pareggio
        if check_winner(self.board, self.turn):
            for b in self.children:
                b.disabled = True
            await interaction.response.edit_message(content=f"Vince {interaction.user.mention} ({self.turn})!", view=self)
            self.stop()
            return
        if board_full(self.board):
            for b in self.children:
                b.disabled = True
            await interaction.response.edit_message(content="Pareggio!", view=self)
            self.stop()
            return

        # Cambio turno
        self.turn = "O" if self.turn == "X" else "X"
        await interaction.response.edit_message(content=f"Turno: {self.turn}", view=self)

        # Mossa del bot (se vs bot e tocca a O)
        if self.vs_bot and self.turn == "O":
            await asyncio.sleep(0.6)
            r2, c2 = self.bot_move()
            self.board[r2][c2] = "O"
            idx = r2*3 + c2
            self.children[idx].label = "O"
            self.children[idx].style = ButtonStyle.danger
            self.children[idx].disabled = True

            if check_winner(self.board, "O"):
                for b in self.children:
                    b.disabled = True
                await interaction.message.edit(content="Il bot vince! (O)", view=self)
                self.stop()
                return
            if board_full(self.board):
                for b in self.children:
                    b.disabled = True
                await interaction.message.edit(content="Pareggio!", view=self)
                self.stop()
                return

            self.turn = "X"
            await interaction.message.edit(content="Turno: X", view=self)

    def bot_move(self):
        # AI semplice: vincere, bloccare, altrimenti random
        # Prova mosse vincenti
        for r in range(3):
            for c in range(3):
                if self.board[r][c] == "":
                    self.board[r][c] = "O"
                    if check_winner(self.board, "O"):
                        self.board[r][c] = ""
                        return r, c
                    self.board[r][c] = ""
        # Blocca X se sta per vincere
        for r in range(3):
            for c in range(3):
                if self.board[r][c] == "":
                    self.board[r][c] = "X"
                    if check_winner(self.board, "X"):
                        self.board[r][c] = ""
                        return r, c
                    self.board[r][c] = ""
        # Centro
        if self.board[1][1] == "":
            return 1, 1
        # Angoli o random
        cells = [(r, c) for r in range(3) for c in range(3) if self.board[r][c] == ""]
        random.shuffle(cells)
        return cells[0]

# ---------- Slash Commands ----------

@bot.tree.command(name="ticketpanel", description="Invia il pannello per aprire i ticket.")
@app_commands.checks.has_permissions(manage_guild=True)
async def ticketpanel(interaction: Interaction):
    view = TicketPanel()
    embed = discord.Embed(title="Supporto", description="Clicca il bottone per aprire un ticket.", color=0x5865F2)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="setstaff", description="Aggiungi o rimuovi un ruolo dallo staff.")
@app_commands.describe(ruolo="Seleziona il ruolo", azione="Azione da eseguire")
@app_commands.choices(azione=[
    app_commands.Choice(name="Aggiungi", value="add"),
    app_commands.Choice(name="Rimuovi", value="remove"),
    app_commands.Choice(name="Lista", value="list")
])
@app_commands.checks.has_permissions(manage_guild=True)
async def setstaff(interaction: Interaction, ruolo: discord.Role | None, azione: app_commands.Choice[str]):
    action = azione.value
    if action == "list":
        ids = DATA.get("staff_roles", [])
        if not ids:
            return await interaction.response.send_message("Nessun ruolo staff configurato.")
        names = []
        for rid in ids:
            r = interaction.guild.get_role(rid)
            if r:
                names.append(r.mention)
        return await interaction.response.send_message("Ruoli staff: " + (", ".join(names) if names else "nessuno"))
    if not ruolo:
        return await interaction.response.send_message("Seleziona un ruolo per questa azione.", ephemeral=True)
    if action == "add":
        if ruolo.id not in DATA["staff_roles"]:
            DATA["staff_roles"].append(ruolo.id)
            save_data()
        await interaction.response.send_message(f"Aggiunto {ruolo.mention} ai ruoli staff.")
    elif action == "remove":
        if ruolo.id in DATA["staff_roles"]:
            DATA["staff_roles"].remove(ruolo.id)
            save_data()
        await interaction.response.send_message(f"Rimosso {ruolo.mention} dai ruoli staff.")

# ---------- Minigiochi Commands ----------

@bot.tree.command(name="tris", description="Gioca a Tris (Tic-Tac-Toe).")
@app_commands.describe(modalita="Scegli avversario", avversario="Utente avversario (se modalita=utente)")
@app_commands.choices(modalita=[
    app_commands.Choice(name="Contro il bot", value="bot"),
    app_commands.Choice(name="Contro un utente", value="utente")
])
async def tris(interaction: Interaction, modalita: app_commands.Choice[str], avversario: discord.Member | None = None):
    if modalita.value == "bot":
        view = TicTacToeView(player_x=interaction.user.id, player_o=None, vs_bot=True)
        await interaction.response.send_message(content=f"Tris: {interaction.user.mention} (X) vs Bot (O)\nTurno: X", view=view)
    else:
        if avversario is None or avversario.bot or avversario.id == interaction.user.id:
            return await interaction.response.send_message("Seleziona un utente valido come avversario (non bot, non te stesso).", ephemeral=True)
        # Casualizza chi è X
        players = [interaction.user.id, avversario.id]
        random.shuffle(players)
        pX, pO = players
        view = TicTacToeView(player_x=pX, player_o=pO, vs_bot=False)
        await interaction.response.send_message(content=f"Tris: <@{pX}> (X) vs <@{pO}> (O)\nTurno: X", view=view)

@bot.tree.command(name="morra", description="Gioca a morra cinese (sasso, carta, forbici).")
@app_commands.describe(scelta="La tua scelta")
@app_commands.choices(scelta=[
    app_commands.Choice(name="Sasso", value="sasso"),
    app_commands.Choice(name="Carta", value="carta"),
    app_commands.Choice(name="Forbici", value="forbici"),
])
async def morra(interaction: Interaction, scelta: app_commands.Choice[str]):
    bot_choice = random.choice(["sasso", "carta", "forbici"])
    user_choice = scelta.value
    outcomes = {
        ("sasso","forbici"): "Vinci!",
        ("carta","sasso"): "Vinci!",
        ("forbici","carta"): "Vinci!",
    }
    if user_choice == bot_choice:
        result = "Pareggio."
    elif (user_choice, bot_choice) in outcomes:
        result = "Vinci!"
    else:
        result = "Perdi."
    await interaction.response.send_message(f"Hai scelto {user_choice}, io {bot_choice}. {result}")

@bot.tree.command(name="indovina", description="Indovina un numero tra 1 e 10.")
async def indovina(interaction: Interaction):
    target = random.randint(1, 10)
    await interaction.response.send_message("Ho pensato un numero tra 1 e 10. Prova a indovinarlo! Scrivi un numero in chat (hai 15 secondi).")

    def check(m: discord.Message):
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id and m.content.isdigit()

    try:
        msg = await bot.wait_for("message", timeout=15.0, check=check)
        guess = int(msg.content)
        if guess == target:
            await interaction.followup.send(f"Esatto! Era {target} 🎉")
        else:
            await interaction.followup.send(f"Nope! Era {target}.")
    except asyncio.TimeoutError:
        await interaction.followup.send("Tempo scaduto!")

# ---------- Economia Commands ----------

WORK_COOLDOWN = 60  # secondi
WORK_MIN, WORK_MAX = 50, 150

@bot.tree.command(name="saldo", description="Mostra il tuo saldo.")
async def saldo(interaction: Interaction, utente: discord.Member | None = None):
    user = utente or interaction.user
    eu = econ_user(user.id)
    await interaction.response.send_message(f"Saldo di {user.mention}: {eu['balance']}💰")

@bot.tree.command(name="lavora", description="Lavora per guadagnare monete (cooldown).")
async def lavora(interaction: Interaction):
    eu = econ_user(interaction.user.id)
    now = now_ts()
    if eu["last_work"] and now - eu["last_work"] < WORK_COOLDOWN:
        remaining = WORK_COOLDOWN - (now - eu["last_work"])
        return await interaction.response.send_message(f"Devi attendere ancora {remaining}s prima di lavorare di nuovo.", ephemeral=True)
    earn = random.randint(WORK_MIN, WORK_MAX)
    eu["last_work"] = now
    add_money(interaction.user.id, earn)
    save_data()
    await interaction.response.send_message(f"Hai guadagnato {earn}💰. Nuovo saldo: {eu['balance']}💰")

@bot.tree.command(name="trasferisci", description="Trasferisci monete a un utente.")
@app_commands.describe(utente="Utente destinatario", importo="Importo da trasferire")
async def trasferisci(interaction: Interaction, utente: discord.Member, importo: int):
    if importo <= 0:
        return await interaction.response.send_message("Importo non valido.", ephemeral=True)
    if utente.id == interaction.user.id:
        return await interaction.response.send_message("Non puoi trasferire a te stesso.", ephemeral=True)
    if remove_money(interaction.user.id, importo):
        add_money(utente.id, importo)
        await interaction.response.send_message(f"Trasferiti {importo}💰 a {utente.mention}.")
    else:
        await interaction.response.send_message("Fondi insufficienti.", ephemeral=True)

@bot.tree.command(name="negozio", description="Mostra gli oggetti acquistabili.")
async def negozio(interaction: Interaction):
    store = get_store()
    if not store:
        return await interaction.response.send_message("Il negozio è vuoto.")
    lines = [f"- {item['name']} — {item['price']}💰" for item in store]
    await interaction.response.send_message("Negozio:\n" + "\n".join(lines))

@bot.tree.command(name="compra", description="Acquista un oggetto dal negozio.")
@app_commands.describe(oggetto="Nome esatto dell'oggetto")
async def compra(interaction: Interaction, oggetto: str):
    store = get_store()
    item = next((i for i in store if i["name"].lower() == oggetto.lower()), None)
    if not item:
        return await interaction.response.send_message("Oggetto non trovato. Usa /negozio per vedere la lista.", ephemeral=True)
    price = item["price"]
    if not remove_money(interaction.user.id, price):
        return await interaction.response.send_message("Fondi insufficienti.", ephemeral=True)
    eu = econ_user(interaction.user.id)
    eu["inventory"].append(item["name"])
    save_data()
    await interaction.response.send_message(f"Hai acquistato {item['name']} per {price}💰.")

@bot.tree.command(name="inventario", description="Mostra il tuo inventario.")
async def inventario(interaction: Interaction, utente: discord.Member | None = None):
    user = utente or interaction.user
    eu = econ_user(user.id)
    inv = eu.get("inventory", [])
    if not inv:
        return await interaction.response.send_message(f"L'inventario di {user.mention} è vuoto.")
    await interaction.response.send_message(f"Inventario di {user.mention}:\n- " + "\n- ".join(inv))

# ---------- Moderazione Commands ----------

def guild_data_dict(d: dict, guild_id: int, key: str):
    if key not in d:
        d[key] = {}
    if str(guild_id) not in d[key]:
        d[key][str(guild_id)] = {}
    save_data()
    return d[key][str(guild_id)]

@bot.tree.command(name="ban", description="Banna un utente (opzionale: durata).")
@app_commands.describe(utente="Utente da bannare", motivo="Motivo del ban", durata="Durata (es. 30m, 2h, 1d). Vuoto = permanente")
@app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: Interaction, utente: discord.Member, motivo: str | None = None, durata: str | None = None):
    if utente == interaction.user:
        return await interaction.response.send_message("Non puoi bannare te stesso.", ephemeral=True)
    secs = parse_duration(durata)
    try:
        await utente.ban(reason=motivo or "Nessun motivo specificato")
    except discord.Forbidden:
        return await interaction.response.send_message("Permessi insufficienti per bannare questo utente.", ephemeral=True)
    await interaction.response.send_message(f"{utente} bannato. " + (f"Durata: {durata}" if secs else "Durata: permanente"))

    # schedule unban
    if secs:
        bans = guild_data_dict(DATA, interaction.guild.id, "bans")
        bans[str(utente.id)] = now_ts() + secs
        save_data()

    embed = discord.Embed(title="Ban", color=0xED4245, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente", value=str(utente), inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    embed.add_field(name="Motivo", value=motivo or "N/D", inline=False)
    if secs:
        embed.add_field(name="Durata", value=durata, inline=True)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="unban", description="Rimuove il ban a un utente (ID).")
@app_commands.describe(utente_id="ID dell'utente da sbannare")
@app_commands.checks.has_permissions(ban_members=True)
async def unban(interaction: Interaction, utente_id: str):
    try:
        await interaction.guild.unban(discord.Object(id=int(utente_id)), reason="Unban manuale")
    except Exception:
        return await interaction.response.send_message("Impossibile eseguire unban. Verifica l'ID.", ephemeral=True)
    # rimuovi da schedule
    DATA.get("bans", {}).get(str(interaction.guild.id), {}).pop(utente_id, None)
    save_data()
    await interaction.response.send_message(f"Utente {utente_id} sbannato.")
    embed = discord.Embed(title="Unban", color=0x57F287, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente ID", value=utente_id, inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="kick", description="Espelli un utente.")
@app_commands.describe(utente="Utente da espellere", motivo="Motivo")
@app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: Interaction, utente: discord.Member, motivo: str | None = None):
    if utente == interaction.user:
        return await interaction.response.send_message("Non puoi espellere te stesso.", ephemeral=True)
    try:
        await utente.kick(reason=motivo or "Nessun motivo specificato")
    except discord.Forbidden:
        return await interaction.response.send_message("Permessi insufficienti per espellere questo utente.", ephemeral=True)
    await interaction.response.send_message(f"{utente} espulso.")
    embed = discord.Embed(title="Kick", color=0xED4245, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente", value=str(utente), inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    embed.add_field(name="Motivo", value=motivo or "N/D", inline=False)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="mute", description="Silenzia un utente (opzionale: durata).")
@app_commands.describe(utente="Utente da mutare", durata="Durata (es. 30m, 2h, 1d). Vuoto = fino a unmute", motivo="Motivo")
@app_commands.checks.has_permissions(manage_roles=True)
async def mute(interaction: Interaction, utente: discord.Member, durata: str | None = None, motivo: str | None = None):
    role = await ensure_muted_role(interaction.guild)
    if role is None:
        return await interaction.response.send_message("Non riesco a creare/recuperare il ruolo Muted.", ephemeral=True)
    try:
        await utente.add_roles(role, reason=motivo or "Mute")
    except discord.Forbidden:
        return await interaction.response.send_message("Permessi insufficienti per assegnare il ruolo Muted.", ephemeral=True)
    secs = parse_duration(durata)
    if secs:
        mutes = guild_data_dict(DATA, interaction.guild.id, "mutes")
        mutes[str(utente.id)] = now_ts() + secs
        save_data()
    await interaction.response.send_message(f"{utente.mention} mutato." + (f" Durata: {durata}" if secs else ""))

    embed = discord.Embed(title="Mute", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente", value=str(utente), inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    embed.add_field(name="Motivo", value=motivo or "N/D", inline=False)
    if secs:
        embed.add_field(name="Durata", value=durata, inline=True)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="unmute", description="Rimuove il mute da un utente.")
@app_commands.describe(utente="Utente da smutare")
@app_commands.checks.has_permissions(manage_roles=True)
async def unmute(interaction: Interaction, utente: discord.Member):
    role = await ensure_muted_role(interaction.guild)
    if role and role in utente.roles:
        try:
            await utente.remove_roles(role, reason="Unmute manuale")
        except discord.Forbidden:
            return await interaction.response.send_message("Permessi insufficienti per rimuovere il ruolo Muted.", ephemeral=True)
    # rimuovi schedule
    DATA.get("mutes", {}).get(str(interaction.guild.id), {}).pop(str(utente.id), None)
    save_data()
    await interaction.response.send_message(f"{utente.mention} smutato.")
    embed = discord.Embed(title="Unmute", color=0x57F287, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente", value=str(utente), inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="warn", description="Avvisa un utente. Mantiene storico.")
@app_commands.describe(utente="Utente da avvisare", motivo="Motivo")
@app_commands.checks.has_permissions(moderate_members=True)
async def warn(interaction: Interaction, utente: discord.Member, motivo: str):
    add_warn(interaction.guild.id, utente.id, interaction.user.id, motivo)
    await interaction.response.send_message(f"{utente.mention} ha ricevuto un avviso. Motivo: {motivo}")
    embed = discord.Embed(title="Warn", color=0xFEE75C, timestamp=datetime.now(timezone.utc))
    embed.add_field(name="Utente", value=str(utente), inline=True)
    embed.add_field(name="Staff", value=str(interaction.user), inline=True)
    embed.add_field(name="Motivo", value=motivo, inline=False)
    await log_action(interaction.guild, embed)

@bot.tree.command(name="warns", description="Mostra gli avvisi di un utente.")
@app_commands.describe(utente="Utente")
@app_commands.checks.has_permissions(moderate_members=True)
async def warns(interaction: Interaction, utente: discord.Member):
    w = list_warns(interaction.guild.id, utente.id)
    if not w:
        return await interaction.response.send_message(f"Nessun avviso per {utente.mention}.")
    lines = []
    for i, entry in enumerate(w, start=1):
        dt = datetime.fromtimestamp(entry["ts"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"{i}. {dt} — by <@{entry['by']}> — {entry['reason']}")
    await interaction.response.send_message(f"Avvisi per {utente.mention}:\n" + "\n".join(lines))

# ---------- AI (stub disattivata di default) ----------

AI_ENABLED = False  # Imposta True se abiliti integrazione a un modello esterno

@bot.tree.command(name="ai", description="Parla con l'AI (attualmente disattivata).")
@app_commands.describe(prompt="La tua domanda o messaggio")
async def ai_cmd(interaction: Interaction, prompt: str):
    if not AI_ENABLED:
        return await interaction.response.send_message("L'AI è temporaneamente disattivata. Dimmi se vuoi che la attivi e con quale provider.", ephemeral=True)
    # Se abiliti, inserisci qui la chiamata al tuo provider e restituisci la risposta.
    # Esempio:
    # response = await call_your_ai_api(prompt)
    # await interaction.response.send_message(response)
    await interaction.response.send_message("AI attiva (placeholder).")

# ---------- Avvio ----------

def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        print("Errore: imposta la variabile d'ambiente DISCORD_TOKEN con il token del bot.")
        return
    bot.run(token)

if __name__ == "__main__":
    main()

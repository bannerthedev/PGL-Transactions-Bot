import asyncio
import json
import os
import re
from urllib.parse import urlparse, parse_qs
import random
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime, timedelta
from typing import Optional
import aiohttp
import xml.etree.ElementTree as ET
import dotenv

import discord
from discord.ext import commands
from discord import app_commands, Object
from pathlib import Path
from discord.ext import tasks
from aiohttp import web
from dotenv import load_dotenv

load_dotenv()


# ---------------- CONFIG ----------------
TEST_GUILD_ID = 1409038531329917044

# Channel IDs
TRANSACTIONS_CHANNEL_ID = 1416462357718241410
TRANSACTIONS_HELP_CHANNEL_ID = 1426624895722197193
MATCH_SCORE_CHANNEL_ID = 1409043896989777982
MATCH_TIMES_CHANNEL_ID = 1409044495743582268
ASSIGNMENTS_CHANNEL_ID = 1454349005202002012
SCRIM_CATEGORY_ID = 1410590393527046275
SEEDING_POINTS_CHANNEL_ID = 1517019335846006784  # <- replace 0 with your seeding-points channel ID


# Force-time review channel (staff-only announcement)
FORCE_TIME_REVIEW_CHANNEL_ID = 1521587566657404929


# Role IDs
HEAD_REF_ROLE_ID = 1521592074485629088
REF_ROLE_ID = 1409044267908993187
HEAD_CASTER_ROLE_ID = 1521592036795482393
CASTER_ROLE_ID = 1409044226418675814

CAPTAIN_ROLE_ID = 1409046071971151982
CO_CAPTAIN_ROLE_ID = 1409044157334290492
TEAM_PLAYER_ROLE_ID = 1409044068482158744
TEAM_EXEC_ROLE_ID = 1521591557747245277

BOARD_OF_DIRECTORS_ROLE_ID = 1513754689580040232  # @Board Of Directors
COMMUNITY_MANAGER_ROLE_ID = 1409038947413135370   # @Community Manager
SUPERVISOR_ROLE_ID        = 1476793870887948411   # @Supervisor
DEVELOPMENT_TEAM_ROLE_ID  = 1409057069566525471  # <-- replace 0 with your Dev Team role ID

# FAQ / misc roles
UNBORN_CAPTAIN_ROLE_ID = 1409043912487735387
EVENT_PING_ROLE_ID = 1483199997272002680
SCRIM_REFEREE_ROLE_ID = 1517719944916111501  # <-- replace 0 with your Scrim Referee role ID

BRACKET_CHANNEL_ID = 1409043839418896425
BRACKET_BASE_IMAGE_PATH = "MMM BRACKET.png"
BRACKET_OUTPUT_IMAGE_PATH = "MMM_BRACKET_FILLED.png"

ROSTER_LOCKED = False
SEEDING_OPEN = False
FORCE_WARN_DAYS = 4
FORCE_WARN_MARKER = "⚠️"

# Default config persisted to config.json (uses the IDs above as defaults)
DEFAULT_CONFIG = {
    "channels": {
        "transactions": TRANSACTIONS_CHANNEL_ID,
        "faq": None,
        "submit_time": MATCH_TIMES_CHANNEL_ID,
        "submit_score": MATCH_SCORE_CHANNEL_ID,
        "scheduling": None,
        "assignments": ASSIGNMENTS_CHANNEL_ID,
        "force_time_review": FORCE_TIME_REVIEW_CHANNEL_ID,
    },
    "roles": {
        "captain": CAPTAIN_ROLE_ID,
        "co_captain": CO_CAPTAIN_ROLE_ID,
        "executive": TEAM_EXEC_ROLE_ID,
        "team_member": TEAM_PLAYER_ROLE_ID,
        "caster": CASTER_ROLE_ID,
        "referee": REF_ROLE_ID,
    },
    "roster_rules": {
        "max_roster": 12,
        "max_co_captains": 2,
        "max_executive": 1,
    },
}

# ---------------- FILES ----------------
data_dir = Path(os.getenv("data_file", "/data"))
data_dir.mkdir(parents=True, exist_ok=True)

TEAMS_FILE = data_dir / "teams.json"
PLAYER_HISTORY_FILE = data_dir / "player_history.json"
INVITES_FILE = data_dir / "invites.json"
ROSTER_LOCK_FILE = data_dir / "roster_lock.json"
CONFIG_FILE = data_dir / "config.json"
CODES_STATE_FILE = data_dir / "codes_state.json"
HEADSETS_FILE = data_dir / "headsets.json"



# X/Y positions are the *centers* of the first‑round boxes.
# Adjust by a few pixels if they are still slightly off in your image.
BRACKET_SLOT_COORDS = {
    # LEFT SIDE (1–12) – ROUND 1 boxes
    1:  (228,  32),
    2:  (228, 122),
    3:  (228, 212),
    4:  (228, 302),
    5:  (228, 392),
    6:  (228, 482),   # offset from your (88, 482)
    7:  (228, 572),
    8:  (228, 662),
    9:  (228, 752),
    10: (228, 842),
    11: (228, 932),
    12: (228, 1022),

    # RIGHT SIDE (13–24) – ROUND 1 boxes
    13: (1396,  31),
    14: (1396, 121),
    15: (1396, 211),
    16: (1396, 301),
    17: (1396, 391),
    18: (1396, 481),  # offset from your (1536, 479)
    19: (1396, 571),
    20: (1396, 661),
    21: (1396, 751),
    22: (1396, 841),
    23: (1396, 931),
    24: (1396, 1021),
}




def format_list_arrow(items: list[str]) -> str:
    if not items:
        return "> • None"
    return "\n".join(f"> • {it}" for it in items)





DEFAULT_HEADSETS = [
    "Meta Quest 2",
    "Meta Quest 3",
    "Meta Quest 3s",
    "Meta Quest Pro",
    "Oculus Rift S",
    "Valve Index",
    "HTC Vive",
]

def load_headsets() -> list[str]:
    if not HEADSETS_FILE.is_file():
        return DEFAULT_HEADSETS.copy()
    try:
        with HEADSETS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # ensure all strings
                return [str(x) for x in data]
    except Exception:
        pass
    return DEFAULT_HEADSETS.copy()

def save_headsets(headsets: list[str]):
    try:
        with HEADSETS_FILE.open("w", encoding="utf-8") as f:
            json.dump(headsets, f, indent=2)
    except Exception:
        pass


def load_seeding_state() -> dict:
    if not SEEDING_STATE_FILE.is_file():
        return {}
    try:
        with SEEDING_STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_seeding_state(data: dict):
    try:
        with SEEDING_STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass



def load_codes_state() -> dict:
    if not CODES_STATE_FILE.is_file():
        return {}
    try:
        with CODES_STATE_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_codes_state(data: dict):
    try:
        with CODES_STATE_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass



def save_config(cfg):
    try:
        with CONFIG_FILE.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def load_config():
    if not CONFIG_FILE.is_file():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG.copy()

CONFIG = load_config()

# Standing / player-history paths

def load_teams() -> list[dict]:
    if not TEAMS_FILE.is_file():
        return []
    try:
        with TEAMS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []



# invites.json structure:
# {
#   "TEAM_ROLE_ID_STR": [USER_ID_INT, ...],
#   ...
# }

def load_invites() -> dict:
    if not INVITES_FILE.is_file():
        return {}
    try:
        with INVITES_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_invites(data: dict):
    try:
        with INVITES_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def add_pending_invite(team_role_id: int, user_id: int):
    data = load_invites()
    key = str(team_role_id)
    lst = data.get(key, [])
    if user_id not in lst:
        lst.append(user_id)
    data[key] = lst
    save_invites(data)


def remove_pending_invite(team_role_id: int, user_id: int):
    data = load_invites()
    key = str(team_role_id)
    lst = data.get(key)
    if not isinstance(lst, list):
        return
    if user_id in lst:
        lst.remove(user_id)
    if lst:
        data[key] = lst
    else:
        data.pop(key, None)
    save_invites(data)




def add_team_to_list(role_id: int, name: str):
    data = load_teams()
    for entry in data:
        if str(entry.get("role_id")) == str(role_id):
            entry["name"] = name
            break
    else:
        data.append({"role_id": role_id, "name": name})
    try:
        with TEAMS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception:
        return



def load_player_history() -> dict:
    if not PLAYER_HISTORY_FILE.is_file():
        return {}
    try:
        with PLAYER_HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}

# ---------------- INTENTS ----------------
INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.presences = True   # <-- add this
INTENTS.messages = True
INTENTS.dm_messages = True
INTENTS.guilds = True
INTENTS.message_content = True

# ---------------- HELPERS ----------------
def has_role_id(member: discord.Member, role_id: int | None) -> bool:
    return bool(role_id and any(r.id == role_id for r in member.roles))

def is_team_role(guild: discord.Guild, role: discord.Role) -> bool:
    protected = {
        CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
        HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
        UNBORN_CAPTAIN_ROLE_ID, EVENT_PING_ROLE_ID,
    }
    if role.is_default() or role.managed or role.id in protected:
        return False

    team_player = guild.get_role(TEAM_PLAYER_ROLE_ID)

    # Prefer roles where members also have TEAM_PLAYER_ROLE, if such members exist
    if team_player is not None:
        has_pair = False
        for m in guild.members:
            if m.bot:
                continue
            if role in m.roles and team_player in m.roles:
                has_pair = True
                break
        if has_pair:
            return True
        # if no members have both, fall through to generic check below

    # Generic fallback: any non‑protected role assigned to at least one non‑bot member
    for m in guild.members:
        if m.bot:
            continue
        if role in m.roles:
            return True

    return False

def get_user_team_role(member: discord.Member) -> discord.Role | None:
    """Return the team role for this member based ONLY on teams.json, or None."""
    guild = member.guild
    try:
        teams = load_teams()
    except Exception:
        teams = []

    team_roles: list[discord.Role] = []
    for entry in teams:
        rid = entry.get("role_id")
        if not rid:
            continue
        try:
            rid_int = int(rid)
        except (TypeError, ValueError):
            continue
        r = guild.get_role(rid_int)
        if r and r in member.roles:
            team_roles.append(r)

    # If exactly one team role matches, return it; otherwise None
    return team_roles[0] if len(team_roles) == 1 else None


def find_single_team_for_member(guild: discord.Guild, member: discord.Member) -> Optional[discord.Role]:
    # wrapper kept for compatibility
    return get_user_team_role(member)

async def get_team_data(team_role: discord.Role, guild: discord.Guild):
    members = [m for m in guild.members if team_role in m.roles and not m.bot]
    captain = None
    co_captains = []
    players = []
    for m in members:
        if has_role_id(m, CAPTAIN_ROLE_ID):
            if not captain:
                captain = m
                continue
        if has_role_id(m, CO_CAPTAIN_ROLE_ID):
            co_captains.append(m)
            continue
        if has_role_id(m, TEAM_EXEC_ROLE_ID):
            continue
        players.append(m)

    # -------- PENDING INVITES --------
    invites_raw = load_invites()
    team_invites_ids = invites_raw.get(str(team_role.id), []) or []
    pending_mentions: list[str] = []

    for uid in list(team_invites_ids):
        user = guild.get_member(uid) or guild.get_user(uid)
        # auto-clean: if user is already on any team, drop from pending
        if isinstance(user, discord.Member) and get_user_team_role(user) is not None:
            remove_pending_invite(team_role.id, uid)
            continue
        if user:
            pending_mentions.append(user.mention)
        else:
            # user not found -> clean it out
            remove_pending_invite(team_role.id, uid)

    return {
        "name": team_role.name,
        "executive": "None set",
        "captain": captain.mention if captain else "None",
        "co_captains": [m.mention for m in co_captains],
        "players": players,
        "pending_invites": pending_mentions,
    }

SELECTED_MEMBER_CACHE: dict[tuple[int, int], int] = {}

# ---------------- Settings summary view ----------------
class MainSettingsView(discord.ui.View):
    def __init__(self, timeout: Optional[float] = 600):
        super().__init__(timeout=timeout)
        options = [
            discord.SelectOption(label="Channels", description="Configure channel IDs via config.json.", value="channels"),
            discord.SelectOption(label="Roles", description="Configure role IDs via config.json.", value="roles"),
            discord.SelectOption(label="Roster Rules", description="View/update roster limits.", value="roster"),
        ]
        self.select = discord.ui.Select(placeholder="Choose settings section", min_values=1, max_values=1, options=options)
        self.select.callback = self._on_main_select
        self.add_item(self.select)

    async def _on_main_select(self, interaction: discord.Interaction):
        choice = interaction.data["values"][0]
        if choice == "channels":
            await self._show_channels(interaction)
        elif choice == "roles":
            await self._show_roles(interaction)
        elif choice == "roster":
            await self._show_roster(interaction)

    def _resolve_channel_id(self, key: str, fallback_name: Optional[str]) -> Optional[int]:
        # CONFIG -> DEFAULT_CONFIG -> module global
        val = None
        try:
            val = CONFIG.get("channels", {}).get(key)
        except Exception:
            val = None
        if val is None:
            val = DEFAULT_CONFIG.get("channels", {}).get(key)
        if val is None and fallback_name:
            val = globals().get(fallback_name)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    def _resolve_role_id(self, key: str, fallback_name: Optional[str]) -> Optional[int]:
        val = None
        try:
            val = CONFIG.get("roles", {}).get(key)
        except Exception:
            val = None
        if val is None:
            val = DEFAULT_CONFIG.get("roles", {}).get(key)
        if val is None and fallback_name:
            val = globals().get(fallback_name)
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    # ---------------- Channels ----------------
    async def _show_channels(self, interaction: discord.Interaction):
        guild = interaction.guild
        def chan_text(key, fallback):
            cid = self._resolve_channel_id(key, fallback)
            return f"<#{cid}>" if cid else "Not set"

        embed = discord.Embed(
            title="📺  Channel Settings",
            description=(
                "Pick a channel from the dropdown below.\n\n"
                "The bot will then ask you to go to that channel and send a message mentioning me (e.g. `@Bot`). "
                "I will read which channel the confirmation came from and save it.\n\n"
                "For Match Category, go to any channel inside the category you want."
            ),
            color=discord.Color.light_grey(),
        )

        embed.add_field(name="Transactions", value=chan_text("transactions", "TRANSACTIONS_CHANNEL_ID"), inline=True)
        embed.add_field(name="FAQ", value=chan_text("faq", None), inline=True)
        embed.add_field(name="Match Score", value=chan_text("submit_score", "MATCH_SCORE_CHANNEL_ID"), inline=True)
        embed.add_field(name="Match Time", value=chan_text("submit_time", "MATCH_TIMES_CHANNEL_ID"), inline=True)
        embed.add_field(name="Scheduling", value=chan_text("scheduling", None), inline=True)
        embed.add_field(name="Assignments", value=chan_text("assignments", "ASSIGNMENTS_CHANNEL_ID"), inline=True)
        embed.add_field(name="Force-time staff only announcement", value=chan_text("force_time_review", "FORCE_TIME_REVIEW_CHANNEL_ID"), inline=True)

        options = [
            discord.SelectOption(label="Transactions", value="transactions"),
            discord.SelectOption(label="FAQ", value="faq"),
            discord.SelectOption(label="Match Score", value="submit_score"),
            discord.SelectOption(label="Match Time", value="submit_time"),
            discord.SelectOption(label="Scheduling", value="scheduling"),
            discord.SelectOption(label="Assignments", value="assignments"),
            discord.SelectOption(label="Force-time staff only announcement", value="force_time_review"),
        ]
        sel = discord.ui.Select(placeholder="Select which channel setting to update", min_values=1, max_values=1, options=options)

        async def sel_cb(sel_int: discord.Interaction):
            key = sel_int.data["values"][0]
            await sel_int.response.send_message(
                f"Go to the channel you want to assign to **{key}** and send a message mentioning me (e.g. `@Bot`). I will read the channel where you post the mention and save it.",
                ephemeral=True,
            )

            def check(m: discord.Message):
                return (
                    m.author.id == sel_int.user.id
                    and m.guild is not None
                    and m.channel.type == discord.ChannelType.text
                    and any(u.id == sel_int.client.user.id for u in m.mentions)
                )

            try:
                msg = await sel_int.client.wait_for("message", timeout=120.0, check=check)
            except asyncio.TimeoutError:
                try:
                    await sel_int.followup.send("Timed out waiting for confirmation message. Try again.", ephemeral=True)
                except Exception:
                    pass
                return

            channel_obj = msg.channel
            CONFIG.setdefault("channels", {})[key] = channel_obj.id
            save_config(CONFIG)
            if key == "force_time_review":
                globals()["FORCE_TIME_REVIEW_CHANNEL_ID"] = channel_obj.id
            try:
                await sel_int.followup.send(f"Saved channel <#{channel_obj.id}> for `{key}`.", ephemeral=True)
            except Exception:
                pass

        sel.callback = sel_cb
        view = discord.ui.View(timeout=120)
        view.add_item(sel)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ---------------- Roles ----------------
    async def _show_roles(self, interaction: discord.Interaction):
        guild = interaction.guild
        def role_text(key, fallback):
            rid = self._resolve_role_id(key, fallback)
            return f"<@&{rid}>" if rid else "Not set"

        embed = discord.Embed(
            title="🎭  Role Settings",
            description=(
                "Pick a role from the dropdown below.\n\n"
                "The bot will then ask you to select/mention the role. Mentioning just the bot with no role will clear that setting."
            ),
            color=discord.Color.blue(),
        )

        embed.add_field(name="Captain", value=role_text("captain", "CAPTAIN_ROLE_ID"), inline=True)
        embed.add_field(name="Co-Captain", value=role_text("co_captain", "CO_CAPTAIN_ROLE_ID"), inline=True)
        embed.add_field(name="Executive", value=role_text("executive", "TEAM_EXEC_ROLE_ID"), inline=True)
        embed.add_field(name="Team Member", value=role_text("team_member", "TEAM_PLAYER_ROLE_ID"), inline=True)
        embed.add_field(name="Caster", value=role_text("caster", "CASTER_ROLE_ID"), inline=True)
        embed.add_field(name="Referee", value=role_text("referee", "REF_ROLE_ID"), inline=True)

        options = [
            discord.SelectOption(label="Captain", value="captain"),
            discord.SelectOption(label="Co-Captain", value="co_captain"),
            discord.SelectOption(label="Executive", value="executive"),
            discord.SelectOption(label="Team Member", value="team_member"),
            discord.SelectOption(label="Caster", value="caster"),
            discord.SelectOption(label="Referee", value="referee"),
        ]
        sel = discord.ui.Select(placeholder="Select which role setting to update", min_values=1, max_values=1, options=options)

        async def sel_cb(sel_int: discord.Interaction):
            key = sel_int.data["values"][0]

            class RoleChooseView(discord.ui.View):
                def __init__(self, parent_key: str):
                    super().__init__(timeout=120)
                    self.parent_key = parent_key
                    self.role_select = discord.ui.RoleSelect(placeholder="Pick a role (or cancel to keep current)", min_values=1, max_values=1)
                    self.role_select.callback = self.role_cb
                    self.add_item(self.role_select)

                async def role_cb(self, rs_int: discord.Interaction):
                    try:
                        rid = int(rs_int.data["values"][0])
                        role_obj = rs_int.guild.get_role(rid)
                    except Exception:
                        role_obj = None

                    if role_obj is None:
                        await rs_int.response.send_message("Could not resolve selected role.", ephemeral=True)
                        return

                    CONFIG.setdefault("roles", {})[self.parent_key] = role_obj.id
                    save_config(CONFIG)
                    await rs_int.response.send_message(f"Saved role {role_obj.mention} for `{self.parent_key}`.", ephemeral=True)
                    self.stop()

                @discord.ui.button(label="Clear", style=discord.ButtonStyle.danger)
                async def clear_btn(self, i: discord.Interaction, btn: discord.ui.Button):
                    CONFIG.setdefault("roles", {}).pop(self.parent_key, None)
                    save_config(CONFIG)
                    await i.response.send_message(f"Cleared `{self.parent_key}`.", ephemeral=True)
                    self.stop()

            view = RoleChooseView(parent_key=key)
            await sel_int.response.send_message(f"Select a role for `{key}` (or press Clear to remove it).", view=view, ephemeral=True)

        sel.callback = sel_cb
        v = discord.ui.View(timeout=120)
        v.add_item(sel)
        await interaction.response.send_message(embed=embed, view=v, ephemeral=True)

    # ---------------- Roster Rules ----------------
    async def _show_roster(self, interaction: discord.Interaction):
        rr = CONFIG.get("roster_rules", {}) or DEFAULT_CONFIG.get("roster_rules", {})
        embed = discord.Embed(title="👥  Roster Rules", description="Click a button to update the limit via a short modal.", color=discord.Color.red())
        embed.add_field(name="Max Roster Size", value=str(rr.get("max_roster", 12)), inline=True)
        embed.add_field(name="Max Co-Captains", value=str(rr.get("max_co_captains", 2)), inline=True)
        embed.add_field(name="Max Team Executives", value=str(rr.get("max_executive", 1)), inline=True)

        class NumModal(discord.ui.Modal):
            def __init__(self, title: str, prompt: str, key: str):
                super().__init__(title=title)
                self.prompt_field = discord.ui.TextInput(label=prompt, placeholder="Enter an integer", required=True, max_length=4)
                self.add_item(self.prompt_field)
                self.key = key

            async def on_submit(self, modal_inter: discord.Interaction):
                val_raw = self.prompt_field.value.strip()
                try:
                    val = int(val_raw)
                    if val < 0:
                        raise ValueError
                except Exception:
                    await modal_inter.response.send_message("Invalid integer. Please try again.", ephemeral=True)
                    return
                CONFIG.setdefault("roster_rules", {})[self.key] = val
                save_config(CONFIG)
                await modal_inter.response.send_message(f"Saved `{self.key}` = {val}.", ephemeral=True)

        view = discord.ui.View(timeout=120)

        @discord.ui.button(label="Max Roster Size", style=discord.ButtonStyle.primary)
        async def max_roster_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Roster Size", prompt="What is the new max for roster sizes:", key="max_roster"))

        @discord.ui.button(label="Max Co-Captains", style=discord.ButtonStyle.primary)
        async def max_co_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Co-Captains", prompt="What is the new Max for Co-captains:", key="max_co_captains"))

        @discord.ui.button(label="Max Team Executives", style=discord.ButtonStyle.primary)
        async def max_exec_btn(btn, i: discord.Interaction):
            await i.response.send_modal(NumModal(title="Set Max Team Executives", prompt="What it the new max for Team Executives:", key="max_executive"))

        view.add_item(max_roster_btn)
        view.add_item(max_co_btn)
        view.add_item(max_exec_btn)

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ---------------- Admin Panel Modals ----------------
class CreateTeamModal(discord.ui.Modal, title="Create Team"):
    team_name = discord.ui.TextInput(label="Team Name", required=True)
    captain = discord.ui.TextInput(label="Captain (mention or ID)", required=True)
    color = discord.ui.TextInput(label="Color code (hex, e.g. #ff0000)", required=True)
    pfp_url = discord.ui.TextInput(label="Team PFP URL (optional)", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        raw = self.captain.value.strip()
        if raw.startswith("<@") and raw.endswith(">"):
            raw = raw.strip("<@!>")
        member = None
        try:
            member = await guild.fetch_member(int(raw))
        except Exception:
            pass
        if member is None:
            await interaction.response.send_message("Could not find that captain.", ephemeral=True)
            return

        c = self.color.value.strip()
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            await interaction.response.send_message("Invalid color code.", ephemeral=True)
            return

        # create role
        try:
            role = await guild.create_role(
                name=self.team_name.value,
                colour=discord.Colour(color_int),
                reason=f"Team created by {interaction.user}",
            )
        except Exception as e:
            print(f"[CreateTeamModal] Failed to create role: {e}")
            await interaction.response.send_message("Failed to create role (missing perms?).", ephemeral=True)
            return

        # move team role under Team Player role in the role list
        try:
            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            if team_player_role:
                target_pos = max(team_player_role.position - 1, 1)
                await role.edit(position=target_pos)
        except Exception as e:
            print(f"[CreateTeamModal] Failed to move role {role} under Team Player: {e}")

        # register team
        add_team_to_list(role.id, role.name)

        # assign captain & team_player role
        roles_to_add = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles_to_add.append(cap_role)
        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        if team_player_role and team_player_role not in roles_to_add:
            roles_to_add.append(team_player_role)
        try:
            await member.add_roles(*roles_to_add, reason="New team created by admin")
        except Exception as e:
            print(f"[CreateTeamModal] Failed to assign roles to captain: {e}")
            await interaction.response.send_message("Team created but failed to assign roles.", ephemeral=True)
            return

        # optional: process PFP URL
        pfp = (self.pfp_url.value or "").strip()
        created_emoji = None
        if pfp:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(pfp, timeout=15) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            try:
                                await role.edit(reason=f"Set team icon by {interaction.user}", icon=data)
                            except Exception:
                                try:
                                    created_emoji = await guild.create_custom_emoji(
                                        name=re.sub(r"[^0-9A-Za-z_]", "_", role.name)[:32],
                                        image=data,
                                        reason="Team pfp uploaded"
                                    )
                                except Exception:
                                    created_emoji = None
            except Exception:
                created_emoji = None

        # log and notify
        if tx:
            try:
                await tx.send(f"# New Team Created!\n* Team Name: {role.mention}\n* Team Captain: {member.mention}")
            except Exception:
                pass

        msg_parts = [f"Team {role.mention} created and {member.mention} set as captain."]
        if created_emoji:
            msg_parts.append(f"Created emoji: {created_emoji}")
        await interaction.response.send_message("\n".join(msg_parts), ephemeral=True)


class AdminPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="roster lock all", style=discord.ButtonStyle.danger)
    async def roster_lock_all(self, interaction, button):
        global ROSTER_LOCKED
        guild = interaction.guild
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID) if guild else None
        ROSTER_LOCKED = True
        if tx:
            try:
                await tx.send("# ROSTER LOCK HAS BEEN ENABLED FOR ALL TEAM!")
            except Exception:
                pass
        await interaction.response.send_message("Rosters locked for all teams.", ephemeral=True)

    @discord.ui.button(label="disband all", style=discord.ButtonStyle.danger)
    async def disband_all(self, interaction, button):
        """
        Disband ONLY teams that are registered in teams.json (load_teams).
        Leaves all other server roles alone.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        # 1) Load known team roles from teams.json
        teams_data = load_teams()
        team_role_ids: set[int] = set()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                team_role_ids.add(int(rid))
            except (TypeError, ValueError):
                continue

        if not team_role_ids:
            await interaction.followup.send("No teams found in teams.json; nothing to disband.", ephemeral=True)
            return

        # 2) Resolve actual Role objects for those IDs
        team_roles: list[discord.Role] = []
        for rid in team_role_ids:
            r = guild.get_role(rid)
            if r and not r.is_default() and not r.managed:
                team_roles.append(r)

        if not team_roles:
            await interaction.followup.send("No valid team roles found on this server.", ephemeral=True)
            return

        # 3) Prepare global roles to strip only from members who had a team role
        global_role_ids = {
            CAPTAIN_ROLE_ID,
            CO_CAPTAIN_ROLE_ID,
            TEAM_PLAYER_ROLE_ID,
            TEAM_EXEC_ROLE_ID,
        }
        global_roles = {rid: guild.get_role(rid) for rid in global_role_ids if rid}

        # 4) For each member, if they have ANY team role -> remove team + global roles
        for member in guild.members:
            if member.bot:
                continue
            member_team_roles = [r for r in member.roles if r.id in team_role_ids]
            if not member_team_roles:
                continue

            roles_to_remove = list(member_team_roles)
            for r in global_roles.values():
                if r and r in member.roles:
                    roles_to_remove.append(r)

            if roles_to_remove:
                try:
                    await member.remove_roles(
                        *roles_to_remove,
                        reason=f"Disband-all teams by {interaction.user}",
                    )
                except Exception:
                    pass  # best-effort

        # 5) Delete ONLY the team roles, leave all other roles intact
        deleted_count = 0
        for r in team_roles:
            try:
                await r.delete(reason=f"Disband-all teams by {interaction.user}")
                deleted_count += 1
            except Exception:
                pass  # best-effort

        # 6) Optional: clean teams.json (remove teams whose roles no longer exist)
        cleaned: list[dict] = []
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except (TypeError, ValueError):
                continue
            # keep only teams whose role still exists
            if guild.get_role(rid_int) is not None:
                cleaned.append(entry)
        try:
            with TEAMS_FILE.open("w", encoding="utf-8") as f:
                json.dump(cleaned, f, indent=2)
        except Exception:
            pass

        # 7) Log to transactions and reply
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            try:
                await tx.send("# ALL REGISTERED TEAMS HAVE BEEN DISBANDED")
            except Exception:
                pass

        await interaction.followup.send(
            f"Disbanded {deleted_count} team roles and stripped their members' team/global roles.",
            ephemeral=True,
        )

    @discord.ui.button(label="add scrim", style=discord.ButtonStyle.primary)
    async def add_scrim(self, interaction, button):
        await interaction.response.send_modal(AddScrimModal())

    @discord.ui.button(label="submit score", style=discord.ButtonStyle.success)
    async def submit_score(self, interaction, button):
        global SEEDING_OPEN
        if SEEDING_OPEN:
            await interaction.response.send_modal(SubmitScoreModalSeeding())
        else:
            await interaction.response.send_modal(SubmitScoreModalNoSeeding())

    @discord.ui.button(label="submit time", style=discord.ButtonStyle.secondary)
    async def submit_time(self, interaction, button):
        await interaction.response.send_modal(SubmitTimeModal())

    @discord.ui.button(label="create team", style=discord.ButtonStyle.primary)
    async def create_team(self, interaction, button):
        await interaction.response.send_modal(CreateTeamModal())

    @discord.ui.button(label="Admin Add", style=discord.ButtonStyle.success)
    async def admin_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminAddModal())

    @discord.ui.button(label="Admin Kick", style=discord.ButtonStyle.danger)
    async def admin_kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(AdminKickModal())

    @discord.ui.button(label="unlock roster all", style=discord.ButtonStyle.success)
    async def unlock_roster_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        global ROSTER_LOCKED
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        ROSTER_LOCKED = False
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            try:
                await tx.send("# ALL ROSTERS HAVE BEEN UNLOCKED BY AN ADMIN")
            except Exception:
                pass

        await interaction.response.send_message("All rosters unlocked.", ephemeral=True)


class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-panel", description="Open the admin panel.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return
        await interaction.response.send_message("Admin Panel:", view=AdminPanelView(), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            return
        if message.channel.id != TRANSACTIONS_CHANNEL_ID:
            return
        content = message.content.strip()
        if not content.lower().startswith("/create-team"):
            return
        guild = message.guild
        if guild is None:
            return
        parts = content.split()
        if len(parts) < 4:
            return
        raw_color = parts[-1]
        raw_capt = parts[-2]
        name = " ".join(parts[1:-2])
        if raw_capt.startswith("<@") and raw_capt.endswith(">"):
            raw_capt = raw_capt.strip("<@!>")
        try:
            capt = await guild.fetch_member(int(raw_capt))
        except Exception:
            capt = None
        if capt is None:
            return
        c = raw_color
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            return
        try:
            role = await guild.create_role(
                name=name,
                colour=discord.Colour(color_int),
                reason="Team created by apply-bot command"
            )
        except Exception as e:
            print(f"[AdminPanel] Failed to create team role via /create-team: {e}")
            return

        # move team role under Team Player role in the role list
        try:
            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            if team_player_role:
                target_pos = max(team_player_role.position - 1, 1)
                await role.edit(position=target_pos)
        except Exception as e:
            print(f"[AdminPanel] Failed to move role {role} under Team Player: {e}")

        # register team in teams.json
        add_team_to_list(role.id, role.name)

        roles = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles.append(cap_role)
        try:
            await capt.add_roles(*roles, reason="New team created via /create-team")
        except Exception as e:
            print(f"[AdminPanel] Failed to assign roles to captain via /create-team: {e}")
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if tx:
            try:
                await tx.send(f"# New Team Created!\n* Team Name: {role.mention}\n* Team Captain: {capt.mention}")
            except Exception:
                pass



class SubmitScoreModalSeeding(discord.ui.Modal, title="Submit Score"):
    winner = discord.ui.TextInput(label="Winner (team name)", required=True)
    loser = discord.ui.TextInput(label="Loser (team name)", required=True)
    score = discord.ui.TextInput(label="Score (e.g. 3-1)", required=True)
    stage = discord.ui.TextInput(
        label="Stage (Regular / Semifinals / Finals)",
        required=False,
        placeholder="Regular",
        max_length=20,
    )
    timecap_winner = discord.ui.TextInput(
        label="Who got timecapped? (team name or 'None')",
        required=False,
        placeholder="None",
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID) if guild else None
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Match score channel not configured.", ephemeral=True)
            return

        winner = self.winner.value.strip()
        loser = self.loser.value.strip()
        score = self.score.value.strip()

        stage_raw = (self.stage.value or "Regular").strip().lower()
        if "final" in stage_raw:
            header = "# FINALS"
        elif "semi" in stage_raw:
            header = "# SEMIFINALS"
        else:
            header = None

        tc_raw = (self.timecap_winner.value or "").strip()
        if tc_raw and tc_raw.lower() != "none":
            timecap_line = f"> Timecap: {tc_raw}\n"
        else:
            timecap_line = "> Timecap: None\n"

        if header:
            base = f"{header}\n{winner} vs {loser}\n"
        else:
            base = f"{winner} vs {loser}\n"

        msg = (
            f"{base}"
            f"> Winner: {winner}\n"
            f"> Score: {score}\n"
            f"{timecap_line}"
            f"> Loser: {loser}"
        )

        await ch.send(msg)
        await interaction.response.send_message("Score submitted.", ephemeral=True)



class SubmitScoreModalNoSeeding(discord.ui.Modal, title="Submit Score"):
    winner = discord.ui.TextInput(label="Winner (team name)", required=True)
    loser = discord.ui.TextInput(label="Loser (team name)", required=True)
    score = discord.ui.TextInput(label="Score (e.g. 3-1)", required=True)
    stage = discord.ui.TextInput(
        label="Stage (Regular / Semifinals / Finals)",
        required=False,
        placeholder="Regular",
        max_length=20,
    )

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID) if guild else None
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message("Match score channel not configured.", ephemeral=True)
            return

        winner = self.winner.value.strip()
        loser = self.loser.value.strip()
        score = self.score.value.strip()

        stage_raw = (self.stage.value or "Regular").strip().lower()
        if "final" in stage_raw:
            header = "# FINALS"
        elif "semi" in stage_raw:
            header = "# SEMIFINALS"
        else:
            header = None

        if header:
            base = f"{header}\n{winner} vs {loser}\n"
        else:
            base = f"{winner} vs {loser}\n"

        msg = (
            f"{base}"
            f"> Winner: {winner}\n"
            f"> Score: {score}\n"
            f"> Loser: {loser}"
        )

        await ch.send(msg)
        await interaction.response.send_message("Score submitted.", ephemeral=True)



class AddScrimModal(discord.ui.Modal, title="Add Scrim"):
    team1 = discord.ui.TextInput(label="Team 1", required=True)
    team2 = discord.ui.TextInput(label="Team 2", required=True)
    lower_bracket = discord.ui.TextInput(label="Lower bracket? (true/false)", required=True)

    def _resolve_team(self, guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
        """
        Return (role_obj or None, mention_or_name, display_name)
        Based on mention, ID, or role name.
        """
        text = raw.strip()

        # Mention: <@&123>
        if text.startswith("<@&") and text.endswith(">"):
            try:
                rid = int(text.strip("<@&>"))
                r = guild.get_role(rid)
                if r:
                    return r, r.mention, r.name
            except Exception:
                pass

        # Raw ID
        try:
            rid = int(text)
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

        # Name
        r = discord.utils.get(guild.roles, name=text) or discord.utils.find(
            lambda rr: rr.name.lower() == text.lower(), guild.roles
        )
        if r:
            return r, r.mention, r.name

        # Fallback: no role found, just return text
        return None, text, text

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        cat = guild.get_channel(SCRIM_CATEGORY_ID)
        if not isinstance(cat, discord.CategoryChannel):
            await interaction.response.send_message("Scrim category is not configured.", ephemeral=True)
            return

        t1_role, t1m, t1n = self._resolve_team(guild, self.team1.value)
        t2_role, t2m, t2n = self._resolve_team(guild, self.team2.value)
        is_lb = self.lower_bracket.value.strip().lower() in ("true", "yes", "y", "1")

        raw_name = f"{t1n} vs {t2n}"
        chan_name = re.sub(r"[^a-zA-Z0-9 _-]", "", raw_name).strip().replace(" ", "-").lower()[:90]
        channel_topic = f"{t1n} Vs {t2n}"

        # Build permission overwrites:
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {}

        # Hide from everyone
        overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)

        # Allow only both team roles (if they exist)
        if t1_role:
            overwrites[t1_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if t2_role and t2_role != t1_role:
            overwrites[t2_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

        # NOTE: we intentionally do NOT add overwrites for refs/casters here.
        # Admins still see the channel via their Administrator permission.

        ch = await guild.create_text_channel(
            name=chan_name,
            category=cat,
            overwrites=overwrites,
            topic=channel_topic,
            reason=f"Scrim between {t1n} and {t2n}"
        )

        if is_lb:
            msg = (
                f"{t1m} vs {t2m}\n\n"
                f"> # Welcome to Losers Bracket.\n\n"
                f"> Your last chance to make it back to the regular bracket. If you lose you will be disbanded, however if you win you will be put back in the regular bracket!\n\n"
                f"> Reminder you have 3 days to schedule and 4 days to play."
            )
        else:
            msg = (
                f"{t1m} vs {t2m}\n\n"
                f"# Welcome to PGL Bracket\n"
                f"> 🗓️ You guys will have 3 day to schedule\n"
                f"> ⚔️ And 4 days to play\n"
                f"> Ping a staff member when you're ready to schedule or have any questions!"
                f"> Do `/forfeit` if you want to forfeit this scrim"
            )

        await ch.send(msg)
        await interaction.response.send_message(f"Scrim channel created: {ch.mention}", ephemeral=True)


class AdminAddModal(discord.ui.Modal, title="Admin Add Player"):
    username = discord.ui.TextInput(label="What username is it? (mention or ID)", required=True)
    team = discord.ui.TextInput(label="What team? (mention/name/id)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        raw_user = self.username.value.strip()
        if raw_user.startswith("<@") and raw_user.endswith(">"):
            raw_user = raw_user.strip("<@!>")
        member = None
        try:
            member = await guild.fetch_member(int(raw_user))
        except Exception:
            pass
        if member is None:
            await interaction.response.send_message("Could not find that user.", ephemeral=True)
            return

        raw_team = self.team.value.strip()
        team_role = None
        if raw_team.startswith("<@&") and raw_team.endswith(">"):
            try:
                rid = int(raw_team.strip("<@&>"))
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            try:
                rid = int(raw_team)
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            team_role = discord.utils.get(guild.roles, name=raw_team) or discord.utils.find(
                lambda r: r.name.lower() == raw_team.lower(), guild.roles
            )

        if team_role is None:
            await interaction.response.send_message("Could not find that team role.", ephemeral=True)
            return

        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        roles_to_add = [team_role]
        if team_player_role:
            roles_to_add.append(team_player_role)

        try:
            await member.add_roles(*roles_to_add, reason=f"Admin add by {interaction.user}")
        except Exception:
            await interaction.response.send_message("Failed to add roles (missing perms?).", ephemeral=True)
            return

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            await tx.send(f"{member.mention} Has Been added to **{team_role.name}** by an admin")

        await interaction.response.send_message(
            f"{member.mention} added to {team_role.mention}.",
            ephemeral=True,
        )




class AutoCodeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.state = load_codes_state()  # {str(message_id): {"code": PGL1234", "time": "..."}}
        self.check_matches.start()

    def cog_unload(self):
        self.check_matches.cancel()

    def _parse_match_message(self, msg: discord.Message):
        """
        Parse a MATCH_TIMES message.

        Regular:
            Team1 vs Team2
            > WEEK: X
            > Time: 6/25/26 at 8PM EST
            > Referee: <@id>
            > Caster: <@id>

        Finals/Semis:
            # FINALS / # SEMIFINALS
            > Teams: Team1 vs Team2
            > Time: 6/25/26 at 8PM EST
            > Referee: <@id>
            > Caster: <@id>
        """
        content = msg.content or ""
        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        if not lines:
            return None

        team1_name = None
        team2_name = None
        time_str = None
        caster_mention = None
        ref_mention = None

        header = lines[0].lower()
        special = header.startswith("# finals") or header.startswith("# semifinals")

        if special:
            # FINALS / SEMIFINALS format
            for ln in lines:
                ln_clean = ln.lstrip("> ").strip()
                lower = ln_clean.lower()
                if lower.startswith("teams:"):
                    vs_part = ln_clean.split(":", 1)[1].strip()
                    if " vs " in vs_part:
                        t1, t2 = vs_part.split(" vs ", 1)
                        team1_name = t1.strip()
                        team2_name = t2.strip()
                elif lower.startswith("time:"):
                    time_str = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("referee:"):
                    ref_mention = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("caster:"):
                    caster_mention = ln_clean.split(":", 1)[1].strip()
        else:
            # Regular format
            vs_line = lines[0]
            if " vs " in vs_line:
                t1, t2 = vs_line.split(" vs ", 1)
                team1_name = t1.strip()
                team2_name = t2.strip()
            for ln in lines[1:]:
                ln_clean = ln.lstrip("> ").strip()
                lower = ln_clean.lower()
                if lower.startswith("time:"):
                    time_str = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("referee:"):
                    ref_mention = ln_clean.split(":", 1)[1].strip()
                elif lower.startswith("caster:"):
                    caster_mention = ln_clean.split(":", 1)[1].strip()

        if not (team1_name and team2_name and time_str):
            return None

        return {
            "team1": team1_name,
            "team2": team2_name,
            "time_str": time_str,
            "caster_mention": caster_mention,
            "ref_mention": ref_mention,
        }

    def _parse_time_to_local(self, time_str: str) -> Optional[datetime]:
        """
        Parse strings like:
          '6/25/26 at 8PM EST'
          '6/25 at 8PM EST'
          '6/25/26 at 8:10PM EST'
          '6/25 at 8:10PM EST'
        into a naive datetime in *server local time* (CST),
        assuming the string is written in EST.
        """
        if not time_str:
            return None

        s = time_str.strip()
        if " at " not in s:
            return None

        date_part, time_part = s.split(" at ", 1)
        date_part = date_part.strip()
        time_part = time_part.strip()

        # Strip timezone words
        for tz_word in ("EST", "EDT", "est", "edt"):
            time_part = time_part.replace(tz_word, "")
        time_part = time_part.strip()

        # Handle missing year
        parts = date_part.split("/")
        if len(parts) == 2:
            # m/d -> add current year
            m, d = parts
            try:
                year_now = datetime.now().year
                date_part_full = f"{int(m)}/{int(d)}/{year_now}"
            except Exception:
                return None
        else:
            # assume m/d/yy or m/d/yyyy
            date_part_full = date_part

        # Try formats with and without minutes, and 2‑digit vs 4‑digit year
        fmts = [
            "%m/%d/%y %I%p",      # 6/25/26 8PM
            "%m/%d/%Y %I%p",      # 6/25/2026 8PM
            "%m/%d/%y %I:%M%p",   # 6/25/26 8:10PM
            "%m/%d/%Y %I:%M%p",   # 6/25/2026 8:10PM
        ]

        dt_est = None
        for fmt in fmts:
            try:
                dt_est = datetime.strptime(f"{date_part_full} {time_part}", fmt)
                break
            except Exception:
                continue

        if dt_est is None:
            return None

        # You type EST, but server is CST (UTC‑6). Convert EST->CST by subtracting 1 hour.
        dt_cst = dt_est - timedelta(hours=1)
        return dt_cst



    def _compute_ff_string_from_time_str(self, time_str: str) -> str:
        """
        Take the original 'Time: ...' value (e.g. '6/18/26 at 10:40PM EST')
        and return a display string like '10:55PM EST' (15 minutes later),
        WITHOUT using the server's timezone.

        This only looks at the clock time in the string.
        """
        if not time_str or " at " not in time_str:
            return "Unknown"

        _, time_part = time_str.split(" at ", 1)
        time_part = time_part.strip()

        # Strip timezone words but remember we will display EST
        for tz_word in ("EST", "EDT", "est", "edt"):
            time_part = time_part.replace(tz_word, "")
        time_part = time_part.strip()

        # Try to parse time only as 12‑hour clock, with and without minutes
        fmts = ["%I%p", "%I:%M%p"]
        dt = None
        for fmt in fmts:
            try:
                dt = datetime.strptime(time_part, fmt)
                break
            except Exception:
                continue

        if dt is None:
            return "Unknown"

        # Add 15 minutes for FF time (as per your example)
        dt_ff = dt + timedelta(minutes=15)
        ff_str = dt_ff.strftime("%I:%M%p").lstrip("0")
        return ff_str + " EST"



    def _resolve_member_from_mention(self, guild: discord.Guild, mention: str) -> Optional[discord.Member]:
        if not mention:
            return None
        mention = mention.strip()
        if mention.startswith("<@") and mention.endswith(">"):
            try:
                uid = int(mention.strip("<@!>"))
                return guild.get_member(uid)
            except Exception:
                return None
        return None

    def _find_scheduling_channel(self, guild: discord.Guild, team1_name: str, team2_name: str) -> Optional[discord.TextChannel]:
        """
        Try to find a scheduling channel for these two teams.
        Uses channel name and topic; assumes '-vs-' style channels like 'team1-vs-team2'.
        """
        t1 = (team1_name or "").lower()
        t2 = (team2_name or "").lower()

        def norm(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", (s or "").lower())

        n_t1 = norm(t1)
        n_t2 = norm(t2)

        for ch in guild.text_channels:
            name = ch.name or ""
            topic = ch.topic or ""
            if "-vs-" not in name.lower():
                continue
            combined = name + " " + topic
            n_combined = norm(combined)
            if n_t1 in n_combined and n_t2 in n_combined:
                return ch
        return None

    @tasks.loop(minutes=1)
    async def check_matches(self):
        await self.bot.wait_until_ready()
        now_local = datetime.now()

        for guild in self.bot.guilds:
            ch = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
            if not isinstance(ch, discord.TextChannel):
                continue

            try:
                async for msg in ch.history(limit=200):
                    mid = str(msg.id)

                    # already coded?
                    if mid in self.state:
                        continue

                    parsed = self._parse_match_message(msg)
                    if not parsed:
                        continue

                    sched_local = self._parse_time_to_local(parsed["time_str"])
                    if not sched_local:
                        continue

                    # send at macth time (within ~1 min around the time )
                    delta_min = (sched_local - now_local).total_seconds() / 60.0
                    if not (0 <= delta_min <= 5):
                        continue


                    # generate code
                    code = f"PGL{random.randint(1000, 9999)}"

                    # resolve teams to mentions
                    t1_role, t1_mention, _ = resolve_team_any(guild, parsed["team1"])
                    t2_role, t2_mention, _ = resolve_team_any(guild, parsed["team2"])

                    # compute FF display string purely from the original time string (EST-based)
                    ff_str = self._compute_ff_string_from_time_str(parsed["time_str"])

                    # post code in the scheduling channel for these teams, or fallback to MATCH_TIMES
                    body = (
                        f"{t1_mention} {t2_mention}\n"
                        f"# The Code Is:\n\n"
                        f"# {code}\n\n"
                        f"> time until FF is {ff_str}"
                    )

                    try:
                        sched_ch = self._find_scheduling_channel(guild, parsed["team1"], parsed["team2"])
                        target_ch = sched_ch if isinstance(sched_ch, discord.TextChannel) else ch
                        await target_ch.send(body)
                    except Exception:
                        pass

                    # DM caster/ref
                    caster = self._resolve_member_from_mention(guild, parsed["caster_mention"])
                    ref = self._resolve_member_from_mention(guild, parsed["ref_mention"])
                    dm_text = (
                        "# The Code Is:\n\n"
                        f"# {code}\n\n"
                        "***DO NOT SHARE THIS TO ANYONE. IF YOU DO, YOU WILL BE DEMOTED.***"
                    )
                    for target in (caster, ref):
                        if target and not target.bot:
                            try:
                                await target.send(dm_text)
                            except Exception:
                                pass

                    # remember we processed this message so we don't send again
                    self.state[mid] = {"code": code, "time": parsed["time_str"]}
                    save_codes_state(self.state)

            except Exception:
                continue

    @check_matches.before_loop
    async def before_check_matches(self):
        await self.bot.wait_until_ready()





class LeaveCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="leave", description="Leave your team (players, co-captains, executives).")
    async def leave(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # resolve member object
        try:
            member = guild.get_member(interaction.user.id) or await guild.fetch_member(interaction.user.id)
        except Exception:
            member = None

        if member is None:
            await interaction.response.send_message("Could not resolve your member object.", ephemeral=True)
            return

        team_role = get_user_team_role(member)
        if team_role is None:
            await interaction.response.send_message("You are not on a team.", ephemeral=True)
            return

        # check roles eligibility
        is_captain = has_role_id(member, CAPTAIN_ROLE_ID)
        is_co = has_role_id(member, CO_CAPTAIN_ROLE_ID)
        is_exec = has_role_id(member, TEAM_EXEC_ROLE_ID)
        is_player = has_role_id(member, TEAM_PLAYER_ROLE_ID)

        if not (is_player or is_co or is_exec or is_captain):
            await interaction.response.send_message("Only players, co-captains, executives, or captains may use this command.", ephemeral=True)
            return

        # If captain, require transfer or disallow if no candidates
        if is_captain:
            # build candidate list: co-captains or executives who share the team_role
            candidates = []
            for m in guild.members:
                if m.bot:
                    continue
                if team_role not in m.roles:
                    continue
                if has_role_id(m, CO_CAPTAIN_ROLE_ID) or has_role_id(m, TEAM_EXEC_ROLE_ID):
                    # exclude the leaving captain
                    if m.id == member.id:
                        continue
                    candidates.append(m)
                    if len(candidates) >= 25:
                        break

            if not candidates:
                await interaction.response.send_message(
                    "You are the captain and there are no co-captains/executives to transfer to. Please transfer captain to someone or disband the team before leaving.",
                    ephemeral=True,
                )
                return

            # present select to choose new captain
            options = [discord.SelectOption(label=c.display_name, description=f"{c.name}#{c.discriminator}", value=str(c.id)) for c in candidates]
            select = discord.ui.Select(placeholder="Select a new captain", options=options, min_values=1, max_values=1)

            async def sel_cb(sel_int: discord.Interaction):
                new_id = int(sel_int.data["values"][0])
                new_member = guild.get_member(new_id)
                if new_member is None:
                    await sel_int.response.send_message("Selected member not found.", ephemeral=True)
                    return

                cap_role = guild.get_role(CAPTAIN_ROLE_ID)
                if cap_role is None:
                    await sel_int.response.send_message("Captain role not configured on this server.", ephemeral=True)
                    return

                # perform transfer
                try:
                    # remove captain role from leaving member
                    if cap_role in member.roles:
                        await member.remove_roles(cap_role, reason=f"Transferred captain via /leave by {member}")
                    # add captain role to new member
                    await new_member.add_roles(cap_role, reason=f"Promoted to captain by {member} via /leave")
                except Exception:
                    await sel_int.response.send_message("Failed to transfer captain role (missing Manage Roles?).", ephemeral=True)
                    return

                # now remove leaver's team + relevant global roles
                roles_to_remove = []
                if team_role in member.roles:
                    roles_to_remove.append(team_role)
                for rid in (CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID, TEAM_PLAYER_ROLE_ID):
                    r = guild.get_role(rid)
                    if r and r in member.roles:
                        roles_to_remove.append(r)

                try:
                    if roles_to_remove:
                        await member.remove_roles(*roles_to_remove, reason=f"Left team via /leave by {member}")
                except Exception:
                    await sel_int.response.send_message("Transferred captain but failed to remove some roles from you (missing perms?).", ephemeral=True)
                    return

                # notify transactions
                try:
                    tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
                    if isinstance(tx, discord.TextChannel):
                        await tx.send(f"{member.mention} Has left **{team_role.name}**")
                except Exception:
                    pass

                await sel_int.response.send_message(f"Captain transferred to {new_member.mention} and you have left {team_role.name}.", ephemeral=True)

            select.callback = sel_cb
            view = discord.ui.View(timeout=60)
            view.add_item(select)
            await interaction.response.send_message("You are the captain. Select a new captain to transfer to before leaving:", view=view, ephemeral=True)
            return

        # Not a captain — proceed to remove roles
        roles_to_remove = []
        if team_role in member.roles:
            roles_to_remove.append(team_role)
        for rid in (CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID, TEAM_PLAYER_ROLE_ID):
            r = guild.get_role(rid)
            if r and r in member.roles:
                roles_to_remove.append(r)

        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Left team via /leave by {member}")
        except Exception:
            await interaction.response.send_message("Failed to remove roles (missing Manage Roles permission?). Contact staff.", ephemeral=True)
            return

        # notify transactions channel
        try:
            tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
            if isinstance(tx, discord.TextChannel):
                await tx.send(f"{member.mention} Has left **{team_role.name}**")
        except Exception:
            pass

        await interaction.response.send_message(f"You have left {team_role.name}.", ephemeral=True)




class AdminKickModal(discord.ui.Modal, title="Admin Kick Player"):
    username = discord.ui.TextInput(label="What username is it? (mention or ID)", required=True)
    team = discord.ui.TextInput(label="What team? (mention/name/id)", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        raw_user = self.username.value.strip()
        if raw_user.startswith("<@") and raw_user.endswith(">"):
            raw_user = raw_user.strip("<@!>")
        member = None
        try:
            member = await guild.fetch_member(int(raw_user))
        except Exception:
            pass
        if member is None:
            await interaction.response.send_message("Could not find that user.", ephemeral=True)
            return

        raw_team = self.team.value.strip()
        team_role = None
        if raw_team.startswith("<@&") and raw_team.endswith(">"):
            try:
                rid = int(raw_team.strip("<@&>"))
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            try:
                rid = int(raw_team)
                team_role = guild.get_role(rid)
            except Exception:
                pass
        if team_role is None:
            team_role = discord.utils.get(guild.roles, name=raw_team) or discord.utils.find(
                lambda r: r.name.lower() == raw_team.lower(), guild.roles
            )

        if team_role is None:
            await interaction.response.send_message("Could not find that team role.", ephemeral=True)
            return

        roles_to_remove = [r for r in member.roles if r.id in (team_role.id, TEAM_PLAYER_ROLE_ID)]
        if not roles_to_remove:
            await interaction.response.send_message(
                "That user does not appear to be on that team.",
                ephemeral=True,
            )
            return

        try:
            await member.remove_roles(*roles_to_remove, reason=f"Admin kick by {interaction.user}")
        except Exception:
            await interaction.response.send_message("Failed to remove roles (missing perms?).", ephemeral=True)
            return

        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if isinstance(tx, discord.TextChannel):
            await tx.send(f"{member.mention} Has Been kicked from **{team_role.name}** by an admin")

        await interaction.response.send_message(
            f"{member.mention} kicked from {team_role.mention}.",
            ephemeral=True,
        )

class SubmitCodeModal(discord.ui.Modal, title="Post Match Code"):
    team1 = discord.ui.TextInput(label="Team 1", required=True)
    team2 = discord.ui.TextInput(label="Team 2", required=True)
    code = discord.ui.TextInput(label="Code", required=True)

    def _resolve_role_and_display(self, guild, raw):
        t = raw.strip()
        if t.startswith("<@&") and t.endswith(">"):
            try:
                rid = int(t.strip("<@&>"))
                r = guild.get_role(rid)
            except Exception:
                r = None
            if r:
                return r, r.mention
        try:
            rid = int(t)
            r = guild.get_role(rid)
            if r:
                return r, r.mention
        except Exception:
            pass
        r = discord.utils.get(guild.roles, name=t) or discord.utils.find(lambda rr: rr.name.lower() == t.lower(), guild.roles)
        if r:
            return r, r.mention
        return None, raw

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        code = self.code.value.strip()
        t1_raw = self.team1.value.strip()
        t2_raw = self.team2.value.strip()

        # resolve roles/display names
        def _resolve(guild, raw):
            t = raw.strip()
            if t.startswith("<@&") and t.endswith(">"):
                try:
                    rid = int(t.strip("<@&>"))
                    r = guild.get_role(rid)
                except Exception:
                    r = None
                if r:
                    return r, r.mention
            try:
                rid = int(t)
                r = guild.get_role(rid)
                if r:
                    return r, r.mention
            except Exception:
                pass
            r = discord.utils.get(guild.roles, name=t) or discord.utils.find(lambda rr: rr.name.lower() == t.lower(), guild.roles)
            if r:
                return r, r.mention
            return None, raw

        t1_role, t1_disp = _resolve(guild, t1_raw)
        t2_role, t2_disp = _resolve(guild, t2_raw)

        msg = f"{t1_disp} vs {t2_disp}\n# The Code Is:\n\n# {code}"
        try:
            if interaction.channel:
                await interaction.channel.send(msg)
        except Exception:
            pass

        # search assignments channel for caster/ref; only DM if found
        assign = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)
        caster = None
        ref = None
        if isinstance(assign, discord.TextChannel):
            try:
                async for m in assign.history(limit=200):
                    c = m.content or ""
                    mt1 = (t1_role and t1_role.name in c) or (t1_raw in c)
                    mt2 = (t2_role and t2_role.name in c) or (t2_raw in c)
                    if mt1 and mt2:
                        for line in c.splitlines():
                            ln = line.strip()
                            if ln.lower().startswith("> referee:"):
                                v = ln.split(":", 1)[1].strip()
                                if v.startswith("<@") and v.endswith(">"):
                                    try:
                                        uid = int(v.strip("<@!>"))
                                        ref = guild.get_member(uid)
                                    except Exception:
                                        pass
                            if ln.lower().startswith("> caster:"):
                                v = ln.split(":", 1)[1].strip()
                                if v.startswith("<@") and v.endswith(">"):
                                    try:
                                        uid = int(v.strip("<@!>"))
                                        caster = guild.get_member(uid)
                                    except Exception:
                                        pass
                        if caster or ref:
                            break
            except Exception:
                pass

        # DM only to found caster/ref
        dm_text = "# The Code Is:\n\n# " + code + "\n\n***DO NOT SHARE THIS TO ANYONE. IF YOU DO, YOU WILL BE DEMOTED.***"
        dm_sent = 0
        for m in (caster, ref):
            if m and not m.bot:
                try:
                    await m.send(dm_text)
                    dm_sent += 1
                except Exception:
                    pass

        await interaction.response.send_message(f"Code posted. DMed caster/ref ({dm_sent}).", ephemeral=True)



class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-panel", description="Open the admin panel.")
    async def admin_panel(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return
        await interaction.response.send_message("Admin Panel:", view=AdminPanelView(), ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.author.bot:
            return
        if message.channel.id != TRANSACTIONS_CHANNEL_ID:
            return
        content = message.content.strip()
        if not content.lower().startswith("/create-team"):
            return
        guild = message.guild
        if guild is None:
            return
        parts = content.split()
        if len(parts) < 4:
            return
        raw_color = parts[-1]
        raw_capt = parts[-2]
        name = " ".join(parts[1:-2])
        if raw_capt.startswith("<@") and raw_capt.endswith(">"):
            raw_capt = raw_capt.strip("<@!>")
        try:
            capt = await guild.fetch_member(int(raw_capt))
        except Exception:
            capt = None
        if capt is None:
            return
        c = raw_color
        if not c.startswith("#"):
            c = "#" + c
        try:
            color_int = int(c[1:], 16)
        except Exception:
            return
        try:
            role = await guild.create_role(name=name, colour=discord.Colour(color_int),
                                           reason="Team created by apply-bot command")
        except Exception:
            return
        roles = [role]
        cap_role = guild.get_role(CAPTAIN_ROLE_ID)
        if cap_role:
            roles.append(cap_role)
        try:
            await capt.add_roles(*roles, reason="New team created via /create-team")
        except Exception:
            pass
        tx = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
        if tx:
            try:
                await tx.send(f"# New Team Created!\n* Team Name: {role.mention}\n* Team Captain: {capt.mention}")
            except Exception:
                pass



class InviteUserSelect(discord.ui.UserSelect):
    def __init__(self, parent_view: "ManageTeamView", invoker_id: int):
        super().__init__(
            placeholder="Select a player to invite",
            min_values=1,
            max_values=1,
        )
        self.parent_view = parent_view
        self.invoker_id = invoker_id

    async def callback(self, interaction: discord.Interaction):
        # Only the original opener (unless admin override) can use this
        if (
            self.parent_view.invoker_id
            and not self.parent_view.admin_override
            and interaction.user.id != self.invoker_id
        ):
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        target = self.values[0]  # Member/User from UserSelect
        if not isinstance(target, (discord.Member, discord.User)):
            await interaction.response.send_message("Invalid selection.", ephemeral=True)
            return

        if isinstance(target, discord.Member):
            if target.bot:
                await interaction.response.send_message("You cannot invite a bot.", ephemeral=True)
                return

            # Already on *this* team
            if self.parent_view.team_role in target.roles:
                await interaction.response.send_message(
                    f"{target.mention} is already on this team.",
                    ephemeral=True,
                )
                return

            # Already on *any* team
            existing_team = get_user_team_role(target)
            if existing_team is not None:
                await interaction.response.send_message(
                    f"{target.mention} is already on a team.",
                    ephemeral=True,
                )
                return

        team_role = self.parent_view.team_role
        team_name = team_role.name

        # find captain for display
        captain = None
        for m in guild.members:
            if has_role_id(m, CAPTAIN_ROLE_ID) and team_role in m.roles:
                captain = m
                break
        captain_disp = captain.mention if captain else interaction.user.mention

        class InviteAcceptView(discord.ui.View):
            def __init__(self, target_user: discord.abc.User):
                super().__init__(timeout=86400)
                self.target = target_user

            @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
            async def accept(self, intr: discord.Interaction, btn: discord.ui.Button):
                # We are in DMs, so intr.guild is None. Use the team role's guild.
                guild = team_role.guild

                # get member in that guild
                member_obj = guild.get_member(self.target.id)
                if member_obj is None:
                    try:
                        member_obj = await guild.fetch_member(self.target.id)
                    except Exception:
                        member_obj = None

                if member_obj is None:
                    try:
                        await intr.response.send_message(
                            "Could not find you in the server to add roles. Contact staff.",
                            ephemeral=True,
                        )
                    except Exception:
                        pass
                    return

                # add team role + TEAM_PLAYER_ROLE
                roles_to_add = [team_role]
                team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
                if team_player_role and team_player_role not in roles_to_add:
                    roles_to_add.append(team_player_role)

                try:
                    await member_obj.add_roles(
                        *roles_to_add,
                        reason=f"Accepted invite to {team_name}",
                    )
                except Exception:
                    # even if role add fails, still try to update the UI
                    pass

                # disable buttons on the original DM message
                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True
                try:
                    await intr.message.edit(view=self)
                except Exception:
                    pass

                # reply to that same DM message with confirmation
                try:
                    await intr.message.reply(f"You joined {team_name}!")
                except Exception:
                    # fallback if reply fails
                    try:
                        await intr.followup.send(f"You joined {team_name}!")
                    except Exception:
                        pass

                # transactions: "@user Has Joined **Team**"
                try:
                    tx_ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
                    if isinstance(tx_ch, discord.TextChannel):
                        await tx_ch.send(f"{member_obj.mention} Has Joined **{team_name}**")
                except Exception:
                    pass

                self.stop()

            @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
            async def decline(self, intr: discord.Interaction, btn: discord.ui.Button):
                # disable buttons when declined
                for child in self.children:
                    if isinstance(child, discord.ui.Button):
                        child.disabled = True
                try:
                    await intr.message.edit(view=self)
                except Exception:
                    pass
                try:
                    await intr.response.send_message("You declined the invite.", ephemeral=True)
                except Exception:
                    pass
                self.stop()

        invite_accept_view = InviteAcceptView(target)

        # Build DM embed
        # Color: use team role's color (from its hex); fallback to blurple
        embed_color = team_role.colour or discord.Color.blurple()
        embed = discord.Embed(
            title=f"You've been invited to {team_name}",
            description=f"{captain_disp} invited you to join {team_name}. Use the buttons below to respond.",
            color=embed_color,
        )

        # If the team has a role icon, show it as thumbnail
        if getattr(team_role, "icon", None):
            embed.set_thumbnail(url=team_role.icon.url)

        try:
            await target.send(embed=embed, view=invite_accept_view)
            await interaction.response.send_message(
                f"Tell {target.mention} to check their DMs with the bot",
                ephemeral=True,
            )
        except Exception:
            await interaction.response.send_message(
                "Failed to DM that user (they may have DMs off or blocked the bot).",
                ephemeral=True,
            )




class ManageTeamView(discord.ui.View):
    def __init__(
        self,
        team_role: discord.Role,
        can_captain: bool,
        can_co_captain: bool,
        players: list[discord.Member],
        invoker_id: Optional[int],
        roster_locked: bool,
        admin_override: bool = False,
    ):
        super().__init__(timeout=300)
        self.team_role = team_role
        self.invoker_id = invoker_id
        self.admin_override = admin_override
        self.players = players

        # member select for kick/promote/assign/transfer
        if players:
            member_select = discord.ui.Select(
                placeholder="Select member",
                min_values=1,
                max_values=1,
                options=[discord.SelectOption(label=p.display_name, value=str(p.id)) for p in players][:25],
                custom_id=f"mt:{team_role.id}:member"
            )

            async def member_cb(sel_inter: discord.Interaction, *, _select=member_select):
                if self.invoker_id and not self.admin_override and sel_inter.user.id != self.invoker_id:
                    await sel_inter.response.send_message("This panel is not for you.", ephemeral=True)
                    return
                target_id = int(sel_inter.data["values"][0])
                SELECTED_MEMBER_CACHE[(sel_inter.user.id, self.team_role.id)] = target_id
                await sel_inter.response.send_message("Member selected. You can now use Kick / Promote / Assign Exec / Transfer Captain.", ephemeral=True)

            member_select.callback = member_cb
            self.add_item(member_select)


        # If roster is locked, disable buttons for normal users.
        # Admin override (from /admin-manage) still keeps full control.
        if roster_locked and not self.admin_override:
            for child in list(self.children):
                if isinstance(child, discord.ui.Button):
                    if child.label == "Edit Team Info":
                        continue
                    child.disabled = True

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.invoker_id and not self.admin_override:
            return interaction.user.id == self.invoker_id
        return True

    def _get_selected_member(self, user_id: int) -> Optional[int]:
        return SELECTED_MEMBER_CACHE.get((user_id, self.team_role.id))

    async def _tx(self, guild: discord.Guild, content: str):
        try:
            ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)
            if isinstance(ch, discord.TextChannel):
                await ch.send(content)
        except Exception:
            pass

    @discord.ui.button(label="Invite", style=discord.ButtonStyle.success, custom_id="mt_invite_button")
    async def invite_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # Use a UserSelect dropdown (like your /invite example)
        view = discord.ui.View(timeout=60)
        view.add_item(InviteUserSelect(parent_view=self, invoker_id=interaction.user.id))

        await interaction.response.send_message(
            "Select a player to invite:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Kick member", style=discord.ButtonStyle.danger, custom_id="mt_kick_button")
    async def kick_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message("No member selected. Use the dropdown to select a member first.", ephemeral=True)
            return
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use in server.", ephemeral=True)
            return
        member = guild.get_member(sel_id)
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return
        roles_to_remove = []
        if self.team_role in member.roles:
            roles_to_remove.append(self.team_role)
        team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
        if team_player_role and team_player_role in member.roles:
            roles_to_remove.append(team_player_role)
        try:
            if roles_to_remove:
                await member.remove_roles(*roles_to_remove, reason=f"Kicked from {self.team_role.name} by {interaction.user}")
        except Exception:
            await interaction.response.send_message("Failed to remove roles (missing perms?).", ephemeral=True)
            return
        await interaction.response.send_message(f"{member.mention} kicked from {self.team_role.mention}.", ephemeral=True)
        await self._tx(guild, f"{member.mention} Has Been kicked from **{self.team_role.name}**")

    @discord.ui.button(label="Promote to co-captain", style=discord.ButtonStyle.primary, custom_id="mt_promote_co_button")
    async def promote_co(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message("No member selected. Use the dropdown to select a member first.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(sel_id) if guild else None
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return
        co_role = guild.get_role(CO_CAPTAIN_ROLE_ID)
        if co_role is None:
            await interaction.response.send_message("Co-captain role not configured.", ephemeral=True)
            return
        try:
            await member.add_roles(co_role, reason=f"Promoted to co-captain by {interaction.user}")
            await interaction.response.send_message(f"{member.mention} promoted to co-captain.", ephemeral=True)
            await self._tx(guild, f"{member.mention} Has Been Promoted to Co-captain")
        except Exception:
            await interaction.response.send_message("Failed to add co-captain role (missing perms?).", ephemeral=True)

    @discord.ui.button(label="Assign executive", style=discord.ButtonStyle.primary, custom_id="mt_assign_exec_button")
    async def assign_exec(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return
        sel_id = self._get_selected_member(interaction.user.id)
        if not sel_id:
            await interaction.response.send_message("No member selected. Use the dropdown to select a member first.", ephemeral=True)
            return
        guild = interaction.guild
        member = guild.get_member(sel_id) if guild else None
        if member is None:
            await interaction.response.send_message("Member not found.", ephemeral=True)
            return
        exec_role = guild.get_role(TEAM_EXEC_ROLE_ID)
        if exec_role is None:
            await interaction.response.send_message("Team executive role not configured.", ephemeral=True)
            return
        try:
            await member.add_roles(exec_role, reason=f"Assigned executive by {interaction.user}")
            await interaction.response.send_message(f"{member.mention} assigned as team executive.", ephemeral=True)
            await self._tx(guild, f"{member.mention} Has Been Promoted to Team executive")
        except Exception:
            await interaction.response.send_message("Failed to add executive role (missing perms?).", ephemeral=True)

    @discord.ui.button(label="Transfer captain", style=discord.ButtonStyle.danger, custom_id="mt_transfer_captain_button")
    async def transfer_captain(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use in server.", ephemeral=True)
            return

        # Build candidates: co-captains and executives on this team
        candidates = []
        for m in guild.members:
            if m.bot:
                continue
            if self.team_role not in m.roles:
                continue
            if has_role_id(m, CO_CAPTAIN_ROLE_ID) or has_role_id(m, TEAM_EXEC_ROLE_ID):
                candidates.append(discord.SelectOption(label=m.display_name, value=str(m.id)))
                if len(candidates) >= 25:
                    break

        if not candidates:
            await interaction.response.send_message("No co-captain/executive candidates available to transfer to.", ephemeral=True)
            return

        sel = discord.ui.Select(placeholder="Select new captain", options=candidates, min_values=1, max_values=1)

        async def sel_cb(sel_int: discord.Interaction):
            new_id = int(sel_int.data["values"][0])
            new_member = guild.get_member(new_id)
            if new_member is None:
                await sel_int.response.send_message("Member not found.", ephemeral=True)
                return

            # find current captain (first one)
            old_capt = None
            for m in guild.members:
                if self.team_role in m.roles and has_role_id(m, CAPTAIN_ROLE_ID):
                    old_capt = m
                    break

            cap_role = guild.get_role(CAPTAIN_ROLE_ID)
            if cap_role is None:
                await sel_int.response.send_message("Captain role not configured.", ephemeral=True)
                return

            try:
                if old_capt and cap_role in old_capt.roles:
                    await old_capt.remove_roles(cap_role, reason=f"Transferred captain to {new_member}")
                await new_member.add_roles(cap_role, reason=f"Promoted to captain for {self.team_role.name} by {sel_int.user}")
            except Exception:
                await sel_int.response.send_message("Failed to transfer captain role (missing perms?).", ephemeral=True)
                return

            await sel_int.response.send_message("Captain transferred.", ephemeral=True)
            old_disp = old_capt.mention if old_capt else "None"
            await self._tx(guild, f"# {self.team_role.name} HAS CHANGED THERE CAPTAIN\n***• Old Captain: {old_disp} New Captain: {new_member.mention} ***")

        sel.callback = sel_cb
        v = discord.ui.View(timeout=60)
        v.add_item(sel)
        await interaction.response.send_message("Select new captain:", view=v, ephemeral=True)

    @discord.ui.button(label="Disband", style=discord.ButtonStyle.danger, custom_id="mt_disband_button")
    async def disband_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        confirm_view = discord.ui.View(timeout=60)

        async def yes_cb(i: discord.Interaction):
            guild = i.guild
            if guild is None:
                await i.response.send_message("Guild not found.", ephemeral=True)
                return
            # delete team role
            try:
                await self.team_role.delete(reason=f"Disbanded by {i.user}")
            except Exception:
                pass
            # remove team role and team player from members
            team_player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)
            for m in list(guild.members):
                if self.team_role in m.roles:
                    try:
                        to_remove = [self.team_role]
                        if team_player_role and team_player_role in m.roles:
                            to_remove.append(team_player_role)
                        await m.remove_roles(*to_remove, reason="Team disbanded")
                    except Exception:
                        pass
            await i.response.send_message("Team disbanded.", ephemeral=True)
            await self._tx(guild, f"# {self.team_role.name} HAS BEEN DISBANDED\n\n")
            confirm_view.stop()

        async def no_cb(i: discord.Interaction):
            await i.response.send_message("Canceled disband.", ephemeral=True)
            confirm_view.stop()

        yes = discord.ui.Button(label="Yes", style=discord.ButtonStyle.danger)
        no = discord.ui.Button(label="No", style=discord.ButtonStyle.secondary)
        yes.callback = yes_cb
        no.callback = no_cb
        confirm_view.add_item(yes)
        confirm_view.add_item(no)
        await interaction.response.send_message("Are you sure you want to disband your team?", view=confirm_view, ephemeral=True)

    @discord.ui.button(label="Edit Team Info", style=discord.ButtonStyle.secondary, custom_id="mt_edit_button")
    async def edit_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.invoker_id and not self.admin_override and interaction.user.id != self.invoker_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return

        options = []
        options.append(discord.SelectOption(label="Team Profile Picture", description="Set a profile picture (URL).", value="pfp"))
        if self.admin_override:
            options.append(discord.SelectOption(label="Change Team Color", description="Update the team's color code in hex.", value="color"))
            options.append(discord.SelectOption(label="Change Team Name", description="Rename the team and log the rebrand.", value="name"))

        sel = discord.ui.Select(placeholder="Edit option", options=options, min_values=1, max_values=1)

        async def sel_cb(sel_int: discord.Interaction):
            choice = sel_int.data["values"][0]
            self_view = self

            if choice == "name":
                class NameModal(discord.ui.Modal, title="Change Team Name"):
                    new_name = discord.ui.TextInput(label="What is your new team's name?", required=True, max_length=100)
                    async def on_submit(self, modal_inter: discord.Interaction):
                        old = self_view.team_role.name
                        try:
                            await self_view.team_role.edit(name=self.new_name.value, reason=f"Team rename by {modal_inter.user}")
                            await modal_inter.response.send_message(f"Team renamed to {self.new_name.value}.", ephemeral=True)
                            await self_view._tx(modal_inter.guild, f"# TEAM HAS REBANED\n*** Old Name: {old} New Name: {self.new_name.value} ***")
                        except Exception:
                            await modal_inter.response.send_message("Failed to rename team (missing perms?).", ephemeral=True)
                await sel_int.response.send_modal(NameModal())

            elif choice == "color":
                class ColorModal(discord.ui.Modal, title="Change Team Color"):
                    color = discord.ui.TextInput(label="What is your new Teams Color code (in hex):", required=True, max_length=7)
                    async def on_submit(self, modal_inter: discord.Interaction):
                        new_code = self.color.value.strip()
                        if not new_code.startswith("#"):
                            new_code = "#" + new_code
                        try:
                            color_int = int(new_code[1:], 16)
                        except Exception:
                            await modal_inter.response.send_message("Invalid color code.", ephemeral=True)
                            return
                        old_col = self_view.team_role.colour
                        try:
                            await self_view.team_role.edit(colour=discord.Colour(color_int), reason=f"Team color change by {modal_inter.user}")
                            await modal_inter.response.send_message("Team color updated.", ephemeral=True)
                            await self_view._tx(modal_inter.guild, f"# TEAM HAS CHANGE THERE COLOR CODE\n***• Old Color Code: {old_col} New Color Code: {new_code} ***")
                        except Exception:
                            await modal_inter.response.send_message("Failed to change color (missing perms?).", ephemeral=True)
                await sel_int.response.send_modal(ColorModal())

            elif choice == "pfp":
                class PFPModal(discord.ui.Modal, title="Set Team Profile Picture"):
                    url = discord.ui.TextInput(label="What is your new team's pfp? (URL)", required=True)
                    async def on_submit(self, modal_inter: discord.Interaction):
                        url_val = self.url.value.strip()
                        try:
                            import aiohttp
                            async with aiohttp.ClientSession() as sess:
                                async with sess.get(url_val, timeout=15) as resp:
                                    if resp.status != 200:
                                        await modal_inter.response.send_message("Failed to download image from URL.", ephemeral=True)
                                        return
                                    data = await resp.read()
                        except Exception:
                            await modal_inter.response.send_message("Failed to download image from URL.", ephemeral=True)
                            return

                        created_emoji = None
                        try:
                            await self_view.team_role.edit(reason=f"Team pfp set by {modal_inter.user}", icon=data)
                            await modal_inter.response.send_message("Team PFP set as role icon (if supported).", ephemeral=True)
                        except Exception:
                            try:
                                import re
                                name_safe = re.sub(r"[^0-9A-Za-z_]", "_", self_view.team_role.name)[:32] or "teamimg"
                                created_emoji = await modal_inter.guild.create_custom_emoji(name=name_safe, image=data, reason="Team pfp uploaded")
                            except Exception:
                                created_emoji = None

                            if created_emoji:
                                await modal_inter.response.send_message(f"Team PFP uploaded as emoji: {created_emoji}", ephemeral=True)
                            else:
                                await modal_inter.response.send_message("Team PFP updated (or attempt made). If nothing changed, check bot permissions.", ephemeral=True)

                await sel_int.response.send_modal(PFPModal())

        sel.callback = sel_cb
        v = discord.ui.View(timeout=60)
        v.add_item(sel)
        await interaction.response.send_message("Choose edit action:", view=v, ephemeral=True)



# ---------------- Standing Cog ----------------
class StandingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- internal helpers ----------

    def _compute_stats(
        self,
        guild: discord.Guild,
        win_points: int,
        loss_points: int,
    ) -> dict[str, dict[str, int]]:
        """
        Returns:
          {
            "TeamName": {"W": int, "L": int, "PT": int},
            ...
          }
        """
        teams_data = load_teams()
        stats: dict[str, dict[str, int]] = {}

        # Initialize teams
        for entry in teams_data:
            rid = entry.get("role_id")
            name = entry.get("name", "Unknown Team")
            if not rid:
                continue
            try:
                role = guild.get_role(int(rid))
            except Exception:
                role = None
            if role is None:
                continue
            stats[name] = {"W": 0, "L": 0, "PT": 0}

        if not stats:
            return {}

        score_ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID)
        if not isinstance(score_ch, discord.TextChannel):
            return stats  # no scores, everyone stays 0

        # Parse messages like:
        # > Winner: Team1
        # > Loser: Team2
        async def _scan():
            async for msg in score_ch.history(limit=500):
                content = msg.content or ""
                lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
                if not lines:
                    continue

                winner_name = None
                loser_name = None

                for ln in lines:
                    ln_clean = ln.lstrip("> ").strip()
                    lower = ln_clean.lower()
                    if lower.startswith("winner:"):
                        winner_name = ln_clean.split(":", 1)[1].strip()
                    elif lower.startswith("loser:"):
                        loser_name = ln_clean.split(":", 1)[1].strip()

                if not winner_name or not loser_name:
                    continue
                if winner_name not in stats or loser_name not in stats:
                    continue

                stats[winner_name]["W"] += 1
                stats[loser_name]["L"] += 1

        # run async history scan in sync function via loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_scan())

        # Compute points with provided config
        for name, s in stats.items():
            s["PT"] = s["W"] * win_points + s["L"] * loss_points

        return stats

    def _format_seeding_message(self, stats: dict[str, dict[str, int]]) -> str:
        if not stats:
            return "PGL Seeding\n\nNo teams found."

        ordered = sorted(
            stats.items(),
            key=lambda kv: (-kv[1]["PT"], kv[0].lower()),
        )

        lines = ["PGL Seeding", ""]
        for name, s in ordered:
            lines.append(f"{name} | {s['W']}W | {s['L']}L | {s['PT']}P")

        return "\n".join(lines)

    async def _get_seeding_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        ch_cfg = CONFIG.get("channels", {}) or {}
        ch_id = ch_cfg.get("seeding_points") or SEEDING_POINTS_CHANNEL_ID
        ch = guild.get_channel(ch_id) if ch_id else None
        return ch if isinstance(ch, discord.TextChannel) else None

    # ---------- /start-seeding ----------

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="start-seeding",
        description="Enable seeding and post/update the seeding table.",
    )
    @app_commands.describe(
        win_points="Points given for a win (e.g. 3)",
        loss_points="Points given for a loss (e.g. -1, 0, 1)",
    )
    async def start_seeding(
        self,
        interaction: discord.Interaction,
        win_points: int,
        loss_points: int,
    ):
        global SEEDING_OPEN
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use this in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        SEEDING_OPEN = True

        seeding_ch = await self._get_seeding_channel(guild)
        if seeding_ch is None:
            await interaction.followup.send(
                "Seeding channel not configured.",
                ephemeral=True,
            )
            return

        # Compute stats
        stats = self._compute_stats(guild, win_points, loss_points)
        content = self._format_seeding_message(stats)

        state = load_seeding_state()
        msg_id = state.get("message_id")

        seeding_msg: Optional[discord.Message] = None
        if msg_id:
            try:
                seeding_msg = await seeding_ch.fetch_message(int(msg_id))
            except Exception:
                seeding_msg = None

        # Edit existing or send new
        if seeding_msg:
            try:
                await seeding_msg.edit(content=content)
            except Exception:
                seeding_msg = None

        if seeding_msg is None:
            seeding_msg = await seeding_ch.send(content)

        # Save state
        state = {
            "guild_id": guild.id,
            "channel_id": seeding_ch.id,
            "message_id": seeding_msg.id,
            "win_points": win_points,
            "loss_points": loss_points,
            "open": True,
        }
        save_seeding_state(state)

        await interaction.followup.send(
            f"Seeding started with win={win_points}, loss={loss_points}.",
            ephemeral=True,
        )

    # ---------- /end-seeding ----------

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="end-seeding",
        description="Disable seeding and delete the seeding message.",
    )
    async def end_seeding(self, interaction: discord.Interaction):
        global SEEDING_OPEN
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use this in a server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        SEEDING_OPEN = False

        state = load_seeding_state()
        ch_id = state.get("channel_id")
        msg_id = state.get("message_id")

        if ch_id and msg_id:
            ch = guild.get_channel(int(ch_id))
            if isinstance(ch, discord.TextChannel):
                try:
                    msg = await ch.fetch_message(int(msg_id))
                    await msg.delete()
                except Exception:
                    pass

        # clear state
        state["open"] = False
        state["message_id"] = None
        save_seeding_state(state)

        await interaction.followup.send(
            "Seeding ended and seeding message deleted (if found).",
            ephemeral=True,
        )

    # ---------- /standing (ephemeral view of same table) ----------

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="standing",
        description="View league standings for all teams.",
    )
    async def standing(self, interaction: discord.Interaction):
        global SEEDING_OPEN

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Must be used in a server.",
                ephemeral=True,
            )
            return

        if not SEEDING_OPEN:
            await interaction.response.send_message(
                "Seeding is not currently active.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        state = load_seeding_state()
        win_points = state.get("win_points")
        loss_points = state.get("loss_points")

        if win_points is None or loss_points is None:
            await interaction.followup.send(
                "Seeding point values are not set. Use /start-seeding again.",
                ephemeral=True,
            )
            return

        stats = self._compute_stats(guild, int(win_points), int(loss_points))
        content = self._format_seeding_message(stats)

        await interaction.followup.send(content, ephemeral=True)





class AssignmentClaimView(discord.ui.View):
    def __init__(self, week: str, time: str, team1_name: str, team2_name: str):
        super().__init__(timeout=None)
        self.week = week
        self.time = time
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.caster: Optional[discord.Member] = None
        self.referee: Optional[discord.Member] = None

    async def _find_message_to_edit(self, channel: discord.TextChannel) -> Optional[discord.Message]:
        if channel is None:
            return None

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = ""
            special = False

        teams_line_regular = f"{self.team1_name} vs {self.team2_name}"
        teams_line_special = f"> Teams: {self.team1_name} vs {self.team2_name}"
        q_week = f"> WEEK: {self.week}"
        q_time = f"> Time: {self.time}"

        try:
            async for msg in channel.history(limit=200):
                c = msg.content or ""
                if special:
                    if header in c and teams_line_special in c:
                        return msg
                else:
                    if teams_line_regular in c and q_week in c and q_time in c:
                        return msg
        except Exception:
            return None
        return None

    async def _update_messages(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return

        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)

        caster_text = self.caster.mention if self.caster else ""
        ref_text = self.referee.mention if self.referee else ""

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        if special:
            mt_content = (
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )
        else:
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )

        if isinstance(match_times, discord.TextChannel):
            mt_msg = await self._find_message_to_edit(match_times)
            try:
                if mt_msg:
                    await mt_msg.edit(content=mt_content)
            except Exception:
                pass

        staff_mentions = []
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions)

        if special:
            as_content = (
                f"{staff_header}\n"
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )
        else:
            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}\n"
                f"> Referee: {ref_text}\n"
                f"> Caster: {caster_text}"
            )

        if isinstance(assignments, discord.TextChannel):
            as_msg = await self._find_message_to_edit(assignments)
            try:
                if as_msg:
                    await as_msg.edit(content=as_content, view=self)
            except Exception:
                pass

        staff_mentions = []
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions)

        as_content = (
            f"{staff_header}\n"
            f"{self.team1_name} vs {self.team2_name}\n"
            f"> WEEK: {self.week}\n"
            f"> Time: {self.time}\n"
            f"> referee: {ref_text}\n"
            f"> Caster: {caster_text}"
        )
        if isinstance(assignments, discord.TextChannel):
            as_msg = await self._find_message_to_edit(assignments)
            try:
                if as_msg:
                    await as_msg.edit(content=as_content, view=self)
            except Exception:
                pass

    @discord.ui.button(label="Claim Caster", style=discord.ButtonStyle.primary)
    async def claim_caster(self, interaction: discord.Interaction, button: discord.ui.Button):
        # allow only for FINALS and only head casters / head refs / senior refs
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # finals-only
        if "final" not in (self.week or "").lower():
            await interaction.response.send_message("Caster claiming is only allowed for Finals.", ephemeral=True)
            return

        allowed = any(has_role_id(user, rid) for rid in (HEAD_CASTER_ROLE_ID, HEAD_REF_ROLE_ID, REF_ROLE_ID))
        if not allowed:
            await interaction.response.send_message("Only head casters, head refs, or senior refs may claim Caster for Finals.", ephemeral=True)
            return

        prev = self.caster
        self.caster = user

        button.disabled = True
        await interaction.response.send_message("You claimed Caster.", ephemeral=True)
        if prev and prev != user:
            try:
                await prev.send(f"You were unclaimed as Caster for {self.team1_name} vs {self.team2_name}.")
            except Exception:
                pass

        await self._update_messages(interaction)


    @discord.ui.button(label="Claim Referee", style=discord.ButtonStyle.primary)
    async def claim_ref(self, interaction: discord.Interaction, button: discord.ui.Button):
        # allow only for FINALS and only head casters / head refs / senior refs
        user = interaction.user
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        # finals-only
        if "final" not in (self.week or "").lower():
            await interaction.response.send_message("Referee claiming is only allowed for Finals.", ephemeral=True)
            return

        allowed = any(has_role_id(user, rid) for rid in (HEAD_CASTER_ROLE_ID, HEAD_REF_ROLE_ID, REF_ROLE_ID))
        if not allowed:
            await interaction.response.send_message("Only head casters, head refs, or senior refs may claim Referee for Finals.", ephemeral=True)
            return

        prev = self.referee
        self.referee = user

        button.disabled = True
        await interaction.response.send_message("You claimed Referee.", ephemeral=True)
        if prev and prev != user:
            try:
                await prev.send(f"You were unclaimed as Referee for {self.team1_name} vs {self.team2_name}.")
            except Exception:
                pass

        await self._update_messages(interaction)

    @discord.ui.button(label="Unclaim", style=discord.ButtonStyle.danger)
    async def unclaim(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Clear both claims; Unclaim button stays enabled
        self.caster = None
        self.referee = None
        # Re-enable claim buttons on this view instance (they will be re-rendered enabled)
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label in ("Claim Caster", "Claim Referee"):
                child.disabled = False
        await interaction.response.send_message("Claims cleared.", ephemeral=True)
        await self._update_messages(interaction)


class TimeAcceptView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        team1_role: Optional[discord.Role],
        team2_role: Optional[discord.Role],
        team1_name: str,
        team2_name: str,
        week: str,
        time: str,
    ):
        super().__init__(timeout=None)
        self.guild = guild
        self.team1_role = team1_role
        self.team2_role = team2_role
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.week = week
        self.time = time

        # runtime state
        self.team1_accepted: bool = False
        self.team2_accepted: bool = False
        self.origin_message: Optional[discord.Message] = None

        # for origin message display
        self.team1_mention = team1_role.mention if isinstance(team1_role, discord.Role) else team1_name
        self.team2_mention = team2_role.mention if isinstance(team2_role, discord.Role) else team2_name

    def _is_team_lead(self, member: discord.Member, team_role: Optional[discord.Role]) -> bool:
        if team_role is None:
            return False
        if team_role not in member.roles:
            return False
        return any(has_role_id(member, rid) for rid in (CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID))

    async def _finalize_if_ready(self, interaction: discord.Interaction):
        if not (self.team1_accepted and self.team2_accepted):
            return

        guild = self.guild
        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)

        stage_l = (self.week or "").lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        if special:
            mt_content = (
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}\n"
                f"> Referee: \n"
                f"> Caster: "
            )

        if isinstance(match_times, discord.TextChannel):
            try:
                await match_times.send(mt_content)
            except Exception:
                pass

        staff_mentions = []
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions)

        if special:
            as_content = (
                f"{staff_header}\n"
                f"{header}\n"
                f"> Teams: {self.team1_name} vs {self.team2_name}\n"
                f"> Time: {self.time}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {self.week}\n"
                f"> Time: {self.time}\n"
                f"> Referee: \n"
                f"> Caster: "
            )

        if isinstance(assignments, discord.TextChannel):
            try:
                view = AssignmentClaimView(self.week, self.time, self.team1_name, self.team2_name)
                await assignments.send(as_content, view=view)
            except Exception:
                pass

    async def _edit_origin(self):
        if not self.origin_message:
            return
        t1_line = f"{self.team1_mention}"
        t2_line = f"{self.team2_mention}"
        if self.team1_accepted:
            t1_line += " ✅"
        if self.team2_accepted:
            t2_line += " ✅"
        content = (
            f"{t1_line} vs {t2_line}\n"
            f"Team staff must accept this match.\n"
            f"> WEEK: {self.week}\n"
            f"> Time: {self.time}\n"
            f"> Team 1: {'Accepted ✅' if self.team1_accepted else ''}\n"
            f"> Team 2: {'Accepted ✅' if self.team2_accepted else ''}\n"
        )
        try:
            await self.origin_message.edit(content=content, view=self)
        except Exception:
            pass

    @discord.ui.button(label="Accept for Team 1", style=discord.ButtonStyle.success)
    async def accept_team1(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not self._is_team_lead(member, self.team1_role):
            await interaction.response.send_message("Only staff from Team 1 (captain/co-cap/exec) can accept.", ephemeral=True)
            return
        if self.team1_accepted:
            await interaction.response.send_message("Team 1 already accepted.", ephemeral=True)
            return

        self.team1_accepted = True
        # disable only Team 1 button
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Accept for Team 1":
                child.disabled = True

        await self._edit_origin()
        await interaction.response.send_message("Team 1 accepted.", ephemeral=True)
        await self._finalize_if_ready(interaction)

    @discord.ui.button(label="Accept for Team 2", style=discord.ButtonStyle.success)
    async def accept_team2(self, interaction: discord.Interaction, button: discord.ui.Button):
        member = interaction.user
        if not self._is_team_lead(member, self.team2_role):
            await interaction.response.send_message("Only staff from Team 2 (captain/co-cap/exec) can accept.", ephemeral=True)
            return
        if self.team2_accepted:
            await interaction.response.send_message("Team 2 already accepted.", ephemeral=True)
            return

        self.team2_accepted = True
        # disable only Team 2 button
        for child in self.children:
            if isinstance(child, discord.ui.Button) and child.label == "Accept for Team 2":
                child.disabled = True

        await self._edit_origin()
        await interaction.response.send_message("Team 2 accepted.", ephemeral=True)
        await self._finalize_if_ready(interaction)




class ForceTimeView(discord.ui.View):
    def __init__(
        self,
        team1_role: Optional[discord.Role],
        team2_role: Optional[discord.Role],
        team1_mention: str,
        team2_mention: str,
        team1_name: str,
        team2_name: str,
        time_str: str,
    ):
        super().__init__(timeout=None)
        self.team1_role = team1_role
        self.team2_role = team2_role
        self.team1_mention = team1_mention
        self.team2_mention = team2_mention
        self.team1_name = team1_name
        self.team2_name = team2_name
        self.time_str = time_str

    def _build_forced_message(self) -> str:
        # Only the "real time" line, for after /force-time is accepted
        return f"{self.team1_mention} {self.team2_mention} Your day to play is: {self.time_str}"


    def _build_staff_message(self, guild: discord.Guild) -> str:
        staff_mentions = []
        for rid in (
            BOARD_OF_DIRECTORS_ROLE_ID,
            COMMUNITY_MANAGER_ROLE_ID,
            SUPERVISOR_ROLE_ID,
            DEVELOPMENT_TEAM_ROLE_ID,  # <- added
        ):

            r = guild.get_role(rid)
            if r:
                staff_mentions.append(r.mention)
        staff_header = " ".join(staff_mentions) or ""

        return (
            f"{staff_header}\n"
            f"I have picked this time for {self.team1_mention} and {self.team2_mention}: **{self.time_str}**\n\n"
            f"If you want me to post the message click on the **Accept** button,\n"
            f"but if you want me to find a new time click the **Deny** button."
        )

    def _find_scheduling_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        """
        Try to find a scheduling channel for these two teams.
        Uses channel name and topic; assumes '-vs-' style channels like 'team1-vs-team2'.
        """
        t1 = self.team1_name.lower()
        t2 = self.team2_name.lower()

        def norm(s: str) -> str:
            import re
            return re.sub(r"[^a-z0-9]", "", s.lower())

        n_t1 = norm(t1)
        n_t2 = norm(t2)

        for ch in guild.text_channels:
            name = ch.name or ""
            topic = ch.topic or ""
            if "-vs-" not in name.lower():
                continue
            combined = name + " " + topic
            n_combined = norm(combined)
            if n_t1 in n_combined and n_t2 in n_combined:
                return ch
        return None

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only admins can accept.", ephemeral=True)
            return

        # 1) Find the scheduling channel based on team names and post forced-time message
        sched_ch = self._find_scheduling_channel(guild)
        if not isinstance(sched_ch, discord.TextChannel):
            await interaction.response.send_message(
                "Could not find a scheduling channel for these teams.",
                ephemeral=True,
            )
            return

        forced_msg = self._build_forced_message()
        try:
            await sched_ch.send(forced_msg)
        except Exception:
            await interaction.response.send_message("Failed to send forced time message.", ephemeral=True)
            return

        # 2) Auto "submit time" into MATCH_TIMES and ASSIGNMENTS

        # Treat this as WEEK: Forced
        week = "Forced"
        time_str = self.time_str

        # MATCH_TIMES entry (like a finalized time)
        match_times = guild.get_channel(MATCH_TIMES_CHANNEL_ID)
        if isinstance(match_times, discord.TextChannel):
            mt_content = (
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {week}\n"
                f"> Time: {time_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
            try:
                await match_times.send(mt_content)
            except Exception:
                pass

        # ASSIGNMENTS entry with AssignmentClaimView so staff can claim
        assignments = guild.get_channel(ASSIGNMENTS_CHANNEL_ID)
        if isinstance(assignments, discord.TextChannel):
            staff_mentions = []
            for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
                r = guild.get_role(rid)
                if r:
                    staff_mentions.append(r.mention)
            staff_header = " ".join(staff_mentions)

            as_content = (
                f"{staff_header}\n"
                f"{self.team1_name} vs {self.team2_name}\n"
                f"> WEEK: {week}\n"
                f"> Time: {time_str}\n"
                f"> Referee: \n"
                f"> Caster: "
            )

            try:
                view = AssignmentClaimView(week=week, time=time_str,
                                           team1_name=self.team1_name,
                                           team2_name=self.team2_name)
                await assignments.send(as_content, view=view)
            except Exception:
                pass

        # 3) Finish up the interaction
        await interaction.response.send_message(
            f"Forced time posted in {sched_ch.mention} and scheduling records updated.",
            ephemeral=True,
        )
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass
        self.stop()

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Only admins can deny.", ephemeral=True)
            return

        # pick a new time
        self.time_str = generate_forced_time_string()

        # update staff message with new time
        new_content = self._build_staff_message(guild)
        try:
            await interaction.message.edit(content=new_content, view=self)
        except Exception:
            pass

        await interaction.response.send_message("Picked a new time.", ephemeral=True)


class SubmitTimeModal(discord.ui.Modal, title="Submit Match Time"):
    week = discord.ui.TextInput(label="WEEK", required=True)
    time = discord.ui.TextInput(label="Time", required=True)
    team1 = discord.ui.TextInput(label="Team 1 (mention/name/id)", required=True)
    team2 = discord.ui.TextInput(label="Team 2 (mention/name/id)", required=True)

    def _resolve_team(self, guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
        text = raw.strip()

        # 1) Mention: <@&123>
        if text.startswith("<@&") and text.endswith(">"):
            try:
                rid = int(text.strip("<@&>"))
                r = guild.get_role(rid)
                if r:
                    return r, r.mention, r.name
            except Exception:
                pass

        # 2) Raw ID: 1234567890
        try:
            rid = int(text)
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

        # 3) Direct role name match (case-insensitive)
        r = (
            discord.utils.get(guild.roles, name=text)
            or discord.utils.find(lambda rr: rr.name.lower() == text.lower(), guild.roles)
        )
        if r:
            return r, r.mention, r.name

        # 4) Fallback: look in teams.json by team "name" field
        try:
            teams = load_teams()  # uses your existing helper
        except Exception:
            teams = []

        text_lower = text.lower()
        matched_role = None

        for entry in teams:
            t_name = str(entry.get("name", "")).strip()
            rid = entry.get("role_id")
            if not t_name or not rid:
                continue
            if t_name.lower() != text_lower:   # exact case-insensitive match on team name
                continue
            try:
                rid_int = int(rid)
            except Exception:
                continue
            r = guild.get_role(rid_int)
            if r:
                matched_role = r
                break

        if matched_role:
            return matched_role, matched_role.mention, matched_role.name

        # 5) Nothing matched: return the raw text as display + name, no ping
        return None, text, text

    async def on_submit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("This modal must be used in a text channel.", ephemeral=True)
            return

        team1_role, team1_mention, team1_name = self._resolve_team(guild, self.team1.value)
        team2_role, team2_mention, team2_name = self._resolve_team(guild, self.team2.value)

        stage_raw = self.week.value.strip()
        stage_l = stage_raw.lower()
        if "final" in stage_l:
            header = "# FINALS"
            special = True
        elif "semi" in stage_l:
            header = "# SEMIFINALS"
            special = True
        else:
            header = None
            special = False

        if special:
            content = (
                f"{header}\n"
                f"> Teams: {team1_mention} vs {team2_mention}\n"
                f"> Time: {self.time.value}\n"
                f"> Referee: \n"
                f"> Caster: "
            )
        else:
            content = (
                f"{team1_mention} vs {team2_mention}\n"
                f"Team staff must accept this match.\n"
                f"> WEEK: {self.week.value}\n"
                f"> Time: {self.time.value}\n"
                f"> Team 1: \n"
                f"> Team 2: "
            )

        view = TimeAcceptView(
            guild=guild,
            team1_role=team1_role,
            team2_role=team2_role,
            team1_name=team1_name,
            team2_name=team2_name,
            week=self.week.value,
            time=self.time.value,
        )

        try:
            sent = await channel.send(content, view=view)
            view.origin_message = sent
            await interaction.response.send_message("Match time request posted.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Failed to post match time (missing perms?).", ephemeral=True)


def resolve_team_any(guild: discord.Guild, raw: str) -> tuple[Optional[discord.Role], str, str]:
    text = raw.strip()

    if text.startswith("<@&") and text.endswith(">"):
        try:
            rid = int(text.strip("<@&>"))
            r = guild.get_role(rid)
            if r:
                return r, r.mention, r.name
        except Exception:
            pass

    try:
        rid = int(text)
        r = guild.get_role(rid)
        if r:
            return r, r.mention, r.name
    except Exception:
        pass

    r = (
        discord.utils.get(guild.roles, name=text)
        or discord.utils.find(lambda rr: rr.name.lower() == text.lower(), guild.roles)
    )
    if r:
        return r, r.mention, r.name

    try:
        teams = load_teams()
    except Exception:
        teams = []

    text_lower = text.lower()
    for entry in teams:
        t_name = str(entry.get("name", "")).strip()
        rid = entry.get("role_id")
        if not t_name or not rid:
            continue
        if t_name.lower() != text_lower:
            continue
        try:
            rid_int = int(rid)
        except Exception:
            continue
        r = guild.get_role(rid_int)
        if r:
            return r, r.mention, r.name

    return None, text, text


def generate_forced_time_string() -> str:
    """
    Generate a time string like '6/25/26 at 8PM EST'.
    """
    base = datetime.utcnow()
    delta_days = random.randint(1, 5)
    target = base + timedelta(days=delta_days)

    # format mm/dd/yy, strip leading zeros from month/day
    date_part = target.strftime("%m/%d/%y").lstrip("0").replace("/0", "/")
    return f"{date_part} at 8PM EST"





#---------------- say something command ----------------
class SaySomethingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # ignore bots and DMs
        if message.author.bot or not message.guild:
            return

        content = message.content
        # support both prefixes
        prefixes = [".!saysmth", "!saysmth"]
        used = None
        for p in prefixes:
            if content.startswith(p):
                used = p
                break

        if used is None:
            return

        # glued form (e.g. .!saysmthhi / !saysmthhi) -> delete + DM error
        if len(content) > len(used) and content[len(used)] not in (" ", "\n"):
            if not message.author.guild_permissions.administrator:
                return
            try:
                await message.delete()
            except Exception:
                pass
            try:
                await message.author.send("Could not send the message.")
            except Exception:
                pass
            return

        # admin check
        if not message.author.guild_permissions.administrator:
            return

        # strip off the used command
        body = content[len(used):].lstrip()
        if not body:
            try:
                await message.author.send("You must provide a message after the command.")
            except Exception:
                pass
            return

        guild = message.guild

        # Optional (channel_id) at the end: .!saysmth hi (123456789012345678) or !saysmth hi (...)
        chan = message.channel
        import re as _re
        m = _re.search(r"\((\d{5,})\)\s*$", body)
        if m:
            chan_id = int(m.group(1))
            target = guild.get_channel(chan_id)
            if isinstance(target, (discord.TextChannel, discord.Thread)):
                chan = target
            body = body[:m.start()].rstrip()

        if not body:
            try:
                await message.author.send("You must provide a message to send.")
            except Exception:
                pass
            return

        # normalize @ everyone / @ here -> @everyone / @here
        body = _re.sub(r"@ ?everyone", "@everyone", body, flags=_re.IGNORECASE)
        body = _re.sub(r"@ ?here", "@here", body, flags=_re.IGNORECASE)

        # map textual role pings to real role mentions
        def replace_role_pings(text: str) -> str:
            # (pattern, role_id)
            patterns = [
                (r"@ ?head ?caster", HEAD_CASTER_ROLE_ID),
                (r"@ ?head ?ref(?:eree)?", HEAD_REF_ROLE_ID),
                (r"@ ?ref(?:eree)?", REF_ROLE_ID),
                (r"@ ?caster", CASTER_ROLE_ID),
            ]

            def _make_replacer(role_id: int):
                role = guild.get_role(role_id)
                # capture mention or keep original if role missing
                mention = role.mention if role else None

                def _repl(mo: _re.Match) -> str:
                    return mention or mo.group(0)
                return _repl

            for pat, rid in patterns:
                body_local = _re.sub(pat, _make_replacer(rid), text, flags=_re.IGNORECASE)
                text = body_local
            return text

        body = replace_role_pings(body)

        # send the message (pings work as normal)
        try:
            await chan.send(body, allowed_mentions=discord.AllowedMentions.all())
        except Exception:
            try:
                await message.author.send("Failed to send message (check bot permissions / channel ID).")
            except Exception:
                pass
            return

        # delete the original command message
        try:
            await message.delete()
        except Exception:
            pass

        # DM confirmation
        try:
            if chan.id != message.channel.id:
                await message.author.send(f"✅Message sent to {chan.mention}")
            else:
                await message.author.send("✅Message sent!")
        except Exception:
            pass



# ---------------- ForceTimeAutoWarnCog ----------------
class ForceTimeAutoWarnCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.check_channels.start()

    def cog_unload(self):
        self.check_channels.cancel()

    @tasks.loop(hours=1)
    async def check_channels(self):
        """
        Every hour:
        - Look for scheduling channels (name contains '-vs-').
        - If channel is older than FORCE_WARN_DAYS and not yet warned:
          * Send a warning message.
          * Mark topic with FORCE_WARN_MARKER (⚠️ by default).
          * Prefix the channel name with ⚠️ so it’s visually clear the bot is forcing/scheduling.
        """
        now = datetime.utcnow()

        for guild in self.bot.guilds:
            for ch in guild.text_channels:
                name = ch.name or ""
                topic = ch.topic or ""

                # Only consider scheduling-style channels: name contains "-vs-"
                if "-vs-" not in name.lower():
                    continue

                # Skip if already warned (marker in topic)
                if FORCE_WARN_MARKER in (topic or ""):
                    continue

                # Check age (UTC)
                created_utc = ch.created_at.replace(tzinfo=None)
                age_days = (now - created_utc).days
                if age_days < FORCE_WARN_DAYS:
                    continue

                # Try to get team names from topic: "Team1 Vs Team2"
                t1_name = None
                t2_name = None

                if topic and " Vs " in topic:
                    parts = topic.split(" Vs ", 1)
                    if len(parts) == 2:
                        t1_name = parts[0].strip()
                        t2_name = parts[1].strip()

                # If topic failed, fallback: parse from channel name "team1-vs-team2"
                if not t1_name or not t2_name:
                    lower_name = name.lower()
                    if "-vs-" in lower_name:
                        p1, p2 = lower_name.split("-vs-", 1)
                        t1_name = p1.replace("-", " ").strip()
                        t2_name = p2.replace("-", " ").strip()

                if not t1_name or not t2_name:
                    # Can't parse team names; skip this channel
                    continue

                # Resolve to roles or keep plain text
                t1_role, t1_mention, _ = resolve_team_any(guild, t1_name)
                t2_role, t2_mention, _ = resolve_team_any(guild, t2_name)

                # Build and send the warning message
                warn_msg = (
                    f"{t1_mention} {t2_mention} "
                    "You Have Ran Out Of Time To Schedule. A Time Has Been Forced, "
                    "Meaning If One Player From One Team Joins Before The 15 Minute Late Time, That Team Will Win."
                )
                try:
                    await ch.send(warn_msg)
                except Exception:
                    # If we can't send a message, don't try to edit name/topic either
                    continue

                # Mark as warned by updating topic
                new_topic = (topic or "").strip()
                if FORCE_WARN_MARKER not in new_topic:
                    new_topic = (new_topic + " " + FORCE_WARN_MARKER).strip()

                try:
                    await ch.edit(topic=new_topic, reason="Force-time auto warning sent")
                except Exception:
                    # Topic edit failed; continue with name attempt anyway
                    pass

                # Also prefix the channel name with the warning emoji so users know
                # that the bot had to step in and schedule/force this match.
                try:
                    old_name = ch.name or ""
                    if not old_name.startswith(FORCE_WARN_MARKER):
                        new_name = f"{FORCE_WARN_MARKER}{old_name}"
                        # Discord hard limit is 100 chars; trim if needed
                        if len(new_name) > 100:
                            new_name = new_name[:100]
                        await ch.edit(name=new_name, reason="Mark channel as force-time scheduled")
                except Exception:
                    # Best-effort; do not crash the loop
                    pass

    @check_channels.before_loop
    async def before_check_channels(self):
        await self.bot.wait_until_ready()




class ScrimCheckCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="check-scrims",
        description="Check currently scheduled scrims.",
    )
    async def check_scrims(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Use this in a server.",
                ephemeral=True,
            )
            return

        cat = guild.get_channel(SCRIM_CATEGORY_ID)
        if not isinstance(cat, discord.CategoryChannel):
            await interaction.response.send_message(
                "Scrim category is not configured.",
                ephemeral=True,
            )
            return

        # All text channels inside the scrim category
        scrim_channels = [
            ch for ch in cat.channels
            if isinstance(ch, discord.TextChannel)
        ]

        if not scrim_channels:
            await interaction.response.send_message(
                "No scrims scheduled.",
                ephemeral=True,
            )
            return

        # Sort by creation time (oldest first)
        scrim_channels.sort(key=lambda c: c.created_at)

        lines = ["Current scrims:\n"]
        for ch in scrim_channels:
            # created_at is in UTC; you can adjust if you want
            created = ch.created_at.strftime("%m/%d/%y %I:%M%p UTC")
            # Try to show a nice label: topic or channel name
            label = ch.topic or ch.name
            lines.append(f"> {ch.mention} — {label} — created {created}")

        await interaction.response.send_message(
            "\n".join(lines),
            ephemeral=True,
        )





# ---------------- ForceTimeCog ----------------
class ForceTimeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="force-time",
        description="Force a match time between two teams (admins only).",
    )
    @app_commands.describe(
        team1="Team 1 (mention / name / id)",
        team2="Team 2 (mention / name / id)",
    )
    async def force_time(self, interaction: discord.Interaction, team1: str, team2: str):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        # resolve teams
        t1_role, t1_mention, t1_name = resolve_team_any(guild, team1)
        t2_role, t2_mention, t2_name = resolve_team_any(guild, team2)

        if not t1_mention or not t2_mention:
            await interaction.response.send_message("Could not resolve one or both teams.", ephemeral=True)
            return

        # pick an initial forced time
        time_str = generate_forced_time_string()

        # staff review channel (fixed)
        review_ch = guild.get_channel(FORCE_TIME_REVIEW_CHANNEL_ID)
        if not isinstance(review_ch, discord.TextChannel):
            await interaction.response.send_message("Review channel is not configured correctly.", ephemeral=True)
            return

        view = ForceTimeView(
            team1_role=t1_role,
            team2_role=t2_role,
            team1_mention=t1_mention,
            team2_mention=t2_mention,
            team1_name=t1_name,
            team2_name=t2_name,
            time_str=time_str,
        )

        staff_message = view._build_staff_message(guild)

        try:
            await review_ch.send(staff_message, view=view)
        except Exception:
            await interaction.response.send_message("Failed to post review message.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Proposed forced time created for {t1_mention} vs {t2_mention} and sent to {review_ch.mention}.",
            ephemeral=True,
        )





# ---------------- Allowed Headsets Cog ---------------------
class HeadsetInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- shared embed builder ----------
    def _build_headset_embed(self) -> discord.Embed:
        headsets = load_headsets()
        lines = ["Allowed Headsets:"]
        for h in headsets:
            lines.append(f"• {h}")

        desc = (
            "Note: No other VR headsets are allowed in competition beyond the list below.\n\n"
            + "\n".join(lines)
        )

        embed = discord.Embed(
            title="Allowed VR Headsets",
            description=desc,
            color=discord.Color.blue(),
        )
        return embed

    # ---------- Slash command: /headsets (ephemeral) ----------
    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="headsets",
        description="View the list of allowed VR headsets (competition).",
    )
    async def headsets_slash(self, interaction: discord.Interaction):
        embed = self._build_headset_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ---------- /edit-headsets (admin only) ----------
    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="edit-headsets",
        description="Add or remove allowed headsets (admins only).",
    )
    async def edit_headsets(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        view = self.EditHeadsetsView()
        await interaction.response.send_message("Choose an action:", view=view, ephemeral=True)

    # ---------- inner UI classes ----------
    class EditHeadsetsView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            options = [
                discord.SelectOption(label="Add", description="Add a headset to the allowed list.", value="add"),
                discord.SelectOption(label="Remove", description="Remove a headset from the allowed list.", value="remove"),
            ]
            self.select = discord.ui.Select(placeholder="Select an action", min_values=1, max_values=1, options=options)
            self.select.callback = self._on_select
            self.add_item(self.select)

        async def _on_select(self, interaction: discord.Interaction):
            choice = interaction.data["values"][0]
            if choice == "add":
                modal = HeadsetInfoCog.AddHeadsetModal()
                await interaction.response.send_modal(modal)
            elif choice == "remove":
                modal = HeadsetInfoCog.RemoveHeadsetModal()
                await interaction.response.send_modal(modal)

    class AddHeadsetModal(discord.ui.Modal, title="Add Allowed Headset"):
        name = discord.ui.TextInput(
            label="What are you adding?",
            placeholder="e.g. Valve Index",
            required=True,
            max_length=100,
        )

        async def on_submit(self, interaction: discord.Interaction):
            raw = self.name.value.strip()
            if not raw:
                await interaction.response.send_message("You must provide a name.", ephemeral=True)
                return

            headsets = load_headsets()
            # case-insensitive duplicate check
            existing_lower = {h.lower() for h in headsets}
            if raw.lower() in existing_lower:
                await interaction.response.send_message(f"`{raw}` is already in the allowed list.", ephemeral=True)
                return

            headsets.append(raw)
            save_headsets(headsets)
            await interaction.response.send_message(f"Added `{raw}` to the allowed headsets.", ephemeral=True)

    class RemoveHeadsetModal(discord.ui.Modal, title="Remove Allowed Headset"):
        name = discord.ui.TextInput(
            label="What are you removing?",
            placeholder="Exact name, e.g. Valve Index",
            required=True,
            max_length=100,
        )

        async def on_submit(self, interaction: discord.Interaction):
            raw = self.name.value.strip()
            if not raw:
                await interaction.response.send_message("You must provide a name.", ephemeral=True)
                return

            headsets = load_headsets()
            # remove any that match case-insensitively
            to_remove_lower = raw.lower()
            new_list = [h for h in headsets if h.lower() != to_remove_lower]

            if len(new_list) == len(headsets):
                await interaction.response.send_message(f"`{raw}` was not found in the allowed list.", ephemeral=True)
                return

            save_headsets(new_list)
            await interaction.response.send_message(f"Removed `{raw}` from the allowed headsets.", ephemeral=True)




# ---------------- Settings / Manage / Done / Roster / Info / AdminManage / FAQ+Bracket ----------------
class SettingsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="settings", description="Open server settings panel (admins only)")
    async def settings(self, interaction: discord.Interaction):
        ch = CONFIG.get("channels", {})
        rl = CONFIG.get("roles", {})
        rr = CONFIG.get("roster_rules", {})

        def ch_display(key):
            v = ch.get(key)
            return f"<#{v}>" if v else "Not set"

        def role_display(key):
            v = rl.get(key)
            return f"<@&{v}>" if v else "Not set"

        embed = discord.Embed(title="League Settings", color=discord.Color.green())
        embed.description = "Use the buttons to open the settings sections."
        channels_value = (
            f"Transactions: {ch_display('transactions')}\n"
            f"FAQ: {ch_display('faq')}\n"
            f"Match Score: {ch_display('submit_score')}\n"
            f"Match Time: {ch_display('submit_time')}\n"
            f"Scheduling: {ch_display('scheduling')}\n"
            f"Assignments: {ch_display('assignments')}"
        )
        roles_value = (
            f"Captain: {role_display('captain')}\n"
            f"Co-Captain: {role_display('co_captain')}\n"
            f"Executive: {role_display('executive')}\n"
            f"Team Member: {role_display('team_member')}\n"
            f"Caster: {role_display('caster')}\n"
            f"Referee: {role_display('referee')}"
        )
        roster_value = (
            f"Max Roster Size: {rr.get('max_roster', 12)}\n"
            f"Max Co-Captains: {rr.get('max_co_captains', 2)}\n"
            f"Max Executive: {rr.get('max_executive', 1)}"
        )
        embed.add_field(name="📡 Channels", value=channels_value, inline=False)
        embed.add_field(name="🎭 Roles", value=roles_value, inline=False)
        embed.add_field(name="👩🏻‍👦🏽 Roster Rules", value=roster_value, inline=False)
        view = MainSettingsView()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class ManageTeam(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="manage-team", description="View and manage your team roster.")
    async def manage_team(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        member = interaction.user
        team_role = get_user_team_role(member)
        if team_role is None:
            await interaction.response.send_message("You are not on a team.", ephemeral=True)
            return

        data = await get_team_data(team_role, guild)

        embed_color = team_role.colour if getattr(team_role, "colour", None) else discord.Color.blurple()
        embed = discord.Embed(title=f"Roster for {data['name']}", description="Team roster", color=embed_color)

        embed.add_field(name="Team Executive", value=format_list_arrow([data["executive"]]), inline=False)
        embed.add_field(name="Captain", value=format_list_arrow([data["captain"]]), inline=False)
        embed.add_field(name="Co-Captains", value=format_list_arrow(data.get("co_captains", [])), inline=False)

        players = data.get("players", [])
        player_mentions = [p.mention for p in players[:12]]
        embed.add_field(name="Players", value=format_list_arrow(player_mentions), inline=False)

        embed.add_field(name="\u200b", value=f"{len(players)}/12", inline=False)
        pending = data.get("pending_invites", [])
        pending_text = ", ".join(str(x) for x in pending) if pending else "None"
        embed.add_field(name="Pending invites", value=pending_text, inline=False)
        embed.set_footer(text=team_role.name)

        can_captain = has_role_id(member, CAPTAIN_ROLE_ID)
        can_co_captain = has_role_id(member, CO_CAPTAIN_ROLE_ID)

        view = None
        if can_captain or can_co_captain:
            view = ManageTeamView(
                team_role=team_role,
                can_captain=can_captain,
                can_co_captain=can_co_captain,
                players=players,
                invoker_id=member.id,
                roster_locked=ROSTER_LOCKED,
                admin_override=False,
            )

        if view is not None:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class DoneCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _extract_teams_from_channel(self, ch: discord.TextChannel) -> tuple[Optional[str], Optional[str]]:
        """
        Try to get 'Team1' and 'Team2' from channel name/topic like 'team1-vs-team2'
        or topic 'Team1 Vs Team2'.
        """
        name = ch.name or ""
        topic = ch.topic or ""

        # Try topic "Team1 Vs Team2"
        if topic and " Vs " in topic:
            parts = topic.split(" Vs ", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()

        # Fallback: channel name "team1-vs-team2"
        lower_name = name.lower()
        if "-vs-" in lower_name:
            p1, p2 = lower_name.split("-vs-", 1)
            t1 = p1.replace("-", " ").strip()
            t2 = p2.replace("-", " ").strip()
            return t1 or None, t2 or None

        return None, None

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="done", description="Mark match done and lock channel")
    @app_commands.describe(winner="Winner (team name or any text)")
    async def done(self, interaction: discord.Interaction, winner: str):
        ch = interaction.channel
        guild = interaction.guild
        if not isinstance(ch, discord.TextChannel) or guild is None:
            await interaction.response.send_message("Use this in a server text channel.", ephemeral=True)
            return

        # 1) Post the winner message
        try:
            await ch.send(f"# {winner} Won")
        except Exception:
            pass

        # 2) Figure out team roles from channel
        t1_name, t2_name = self._extract_teams_from_channel(ch)
        t1_role = t2_role = None
        if t1_name or t2_name:
            try:
                if t1_name:
                    t1_role, _, _ = resolve_team_any(guild, t1_name)
                if t2_name:
                    t2_role, _, _ = resolve_team_any(guild, t2_name)
            except Exception:
                t1_role = t2_role = None

        # 3) Build / enforce private permissions
        # @everyone: no view, no send
        try:
            await ch.set_permissions(
                guild.default_role,
                view_channel=False,
                send_messages=False,
                reason="Match finished (/done) - keep channel private",
            )
        except Exception:
            pass

        # allow staff roles to view (read-only)
        for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
            r = guild.get_role(rid)
            if r:
                try:
                    await ch.set_permissions(r, view_channel=True, send_messages=None)
                except Exception:
                    pass

        # ensure both team roles can still see, but cannot send
        for team_role in (t1_role, t2_role):
            if isinstance(team_role, discord.Role):
                try:
                    await ch.set_permissions(team_role, view_channel=True, send_messages=False, reason="Match finished (/done)")
                except Exception:
                    pass

        # 4) Rename the channel to add ✅ in front (e.g. '✅team1-vs-team2')
        try:
            old_name = ch.name or ""
            base_name = old_name

            # If it already starts with ✅, don't duplicate
            if base_name.startswith("✅"):
                base_name = base_name.lstrip("✅").lstrip("-")

            new_name = f"✅{base_name}"
            await ch.edit(name=new_name, reason=f"Match finished via /done by {interaction.user}")
        except Exception:
            pass

        await interaction.response.send_message("Result posted, channel locked, and kept private.", ephemeral=True)


class RosterCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _is_team_role(self, guild: discord.Guild, role: discord.Role) -> bool:
        return is_team_role(guild, role)

    def _build_roster_embed(self, role: discord.Role, data: dict) -> discord.Embed:
        max_roster = CONFIG.get("roster_rules", {}).get("max_roster", 12)
        embed_color = role.colour if getattr(role, "colour", None) else discord.Color.dark_green()

        embed = discord.Embed(
            title=f"Roster for {data['name']}",
            description="Team roster",
            color=embed_color,
        )

        embed.add_field(name="Team Executive", value=format_list_arrow([data["executive"]]), inline=False)
        embed.add_field(name="Captain",        value=format_list_arrow([data["captain"]]),   inline=False)
        embed.add_field(name="Co-Captains",    value=format_list_arrow(data.get("co_captains", [])), inline=False)

        players = data.get("players", [])
        player_mentions = [p.mention for p in players[:max_roster]]
        embed.add_field(name="Players", value=format_list_arrow(player_mentions), inline=False)
        embed.add_field(name="\u200b", value=f"{len(players)}/{max_roster}", inline=False)

        pending = data.get("pending_invites", [])
        pending_text = ", ".join(str(x) for x in pending) if pending else "None"
        embed.add_field(name="Pending invites", value=pending_text, inline=False)

        embed.set_footer(text=role.name)
        return embed

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="roster", description="Show a team's roster")
    async def roster(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        # Build list of team roles from teams.json that still exist and look like team roles
        roles: list[discord.Role] = []
        teams_data = load_teams()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except Exception:
                continue
            r = guild.get_role(rid_int)
            if r and not r.is_default() and not r.managed and is_team_role(guild, r):
                roles.append(r)

        if not roles:
            await interaction.followup.send("No teams found.", ephemeral=True)
            return

        # helper to build embed for a role
        def build_embed_for_role(role: discord.Role, data: dict) -> discord.Embed:
            max_roster = CONFIG.get("roster_rules", {}).get("max_roster", 12)
            embed_color = role.colour if getattr(role, "colour", None) else discord.Color.dark_green()

            embed = discord.Embed(
                title=f"Roster for {data['name']}",
                description="Team roster",
                color=embed_color,
            )

            embed.add_field(name="Team Executive", value=format_list_arrow([data["executive"]]), inline=False)
            embed.add_field(name="Captain",        value=format_list_arrow([data["captain"]]),   inline=False)
            embed.add_field(name="Co-Captains",    value=format_list_arrow(data.get("co_captains", [])), inline=False)

            players = data.get("players", [])
            player_mentions = [p.mention for p in players[:max_roster]]
            embed.add_field(name="Players", value=format_list_arrow(player_mentions), inline=False)
            embed.add_field(name="\u200b", value=f"{len(players)}/{max_roster}", inline=False)

            pending = data.get("pending_invites", [])
            pending_text = ", ".join(str(x) for x in pending) if pending else "None"
            embed.add_field(name="Pending invites", value=pending_text, inline=False)

            embed.set_footer(text=role.name)
            return embed

        options = [discord.SelectOption(label=r.name, value=str(r.id)) for r in roles][:25]
        select = discord.ui.Select(
            placeholder="Select a team to view its roster",
            options=options,
            min_values=1,
            max_values=1,
        )
        view = discord.ui.View(timeout=120)
        view.add_item(select)

        async def sel_cb(sel_int: discord.Interaction):
            try:
                sel_role_id = int(sel_int.data["values"][0])
            except Exception:
                await sel_int.response.send_message("Invalid selection.", ephemeral=True)
                return

            sel_role = guild.get_role(sel_role_id)
            if not sel_role:
                await sel_int.response.send_message("Role not found.", ephemeral=True)
                return

            data = await get_team_data(sel_role, guild)
            embed = build_embed_for_role(sel_role, data)

            # Edit the original ephemeral message so the dropdown stays under the updated embed
            try:
                await sel_int.response.edit_message(embed=embed, view=view)
            except Exception:
                await sel_int.response.send_message(embed=embed, ephemeral=True)

        select.callback = sel_cb

        # If the requester is on a team, we can pre-select it (optional)
        requester = guild.get_member(interaction.user.id)
        requester_team = find_single_team_for_member(guild, requester) if requester else None
        if requester_team:
            # put their team first in the dropdown by reordering options
            options_sorted = sorted(options, key=lambda o: (0 if o.value == str(requester_team.id) else 1, o.label.lower()))
            select.options = options_sorted

        # initial embed: prompt user to pick a team
        prompt_embed = discord.Embed(title="Pick a team", description="Select a team from the dropdown to view its roster.", color=discord.Color.dark_green())

        await interaction.followup.send(embed=prompt_embed, view=view, ephemeral=True)



from discord import app_commands

class AdminManage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _list_team_roles(self, guild: discord.Guild) -> list[discord.Role]:
        """Return only team roles that are in teams.json and still exist."""
        roles: list[discord.Role] = []
        teams_data = load_teams()
        for entry in teams_data:
            rid = entry.get("role_id")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except ValueError:
                continue
            r = guild.get_role(rid_int)
            if r and not r.is_default() and not r.managed:
                roles.append(r)
        roles.sort(key=lambda r: (-r.position, r.name.lower()))
        return roles

    async def _autocomplete_team(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        guild = interaction.guild
        if guild is None:
            return []

        roles = self._list_team_roles(guild)
        current_l = (current or "").lower()
        choices: list[app_commands.Choice[str]] = []

        for r in roles:
            name = r.name
            if not current_l or current_l in name.lower():
                choices.append(app_commands.Choice(name=name, value=name))
                if len(choices) >= 25:
                    break

        return choices

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-manage", description="Admin: view/manage a team by name")
    @app_commands.describe(team_name="Team name")
    @app_commands.autocomplete(team_name=_autocomplete_team)
    async def admin_manage(self, interaction: discord.Interaction, team_name: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return

        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        role = discord.utils.get(guild.roles, name=team_name) or discord.utils.find(lambda r: r.name.lower() == team_name.lower(), guild.roles)
        if role is None:
            teams = load_teams()
            for entry in teams:
                if entry.get("name", "").lower() == team_name.lower():
                    rid = entry.get("role_id")
                    try:
                        role = guild.get_role(int(rid)) if rid else None
                    except Exception:
                        role = None
                    if role:
                        break
        if role is None:
            await interaction.response.send_message("Team not found. Try selecting from the autocomplete options.", ephemeral=True)
            return

        data = await get_team_data(role, guild)

        embed_color = role.colour if getattr(role, "colour", None) else discord.Color.blurple()
        embed = discord.Embed(title=f"Roster for {data['name']}", description="Team roster (admin view)", color=embed_color)

        embed.add_field(name="Team Executive", value=format_list_arrow([data["executive"]]), inline=False)
        embed.add_field(name="Captain", value=format_list_arrow([data["captain"]]), inline=False)
        embed.add_field(name="Co-Captains", value=format_list_arrow(data.get("co_captains", [])), inline=False)

        players = data.get("players", [])
        player_mentions = [p.mention for p in players[:12]]
        embed.add_field(name="Players", value=format_list_arrow(player_mentions), inline=False)

        pending = data.get("pending_invites", [])
        pending_text = ", ".join(str(x) for x in pending) if pending else "None"
        embed.add_field(name="Pending invites", value=pending_text, inline=False)
        embed.add_field(name="\u200b", value=f"{len(players)}/12", inline=False)

        view = ManageTeamView(
            team_role=role,
            can_captain=True,
            can_co_captain=True,
            players=players,
            invoker_id=None,
            roster_locked=ROSTER_LOCKED,
            admin_override=True,
        )

        if view is not None:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)


class InfoCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="info", description="General commands available to users")
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Public Commands", color=discord.Color.blurple())
        embed.add_field(name="/manage-team", value="View/manage your team (players, co-captains, captains, executives)", inline=False)
        embed.add_field(name="/standing", value="View standings (everyone) (only when seeding is enabled)", inline=False)
        embed.add_field(name="/roster", value="Show a team's roster (everyone)", inline=False)
        embed.add_field(name="/list-teams", value="List all teams (everyone)", inline=False)
        embed.add_field(name="/player-info", value="View current and past teams (everyone)", inline=False)
        embed.add_field(name="/info", value="Shows this info (everyone)", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="admin-info", description="Admin-only command list")
    async def admin_info(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission to use this.", ephemeral=True)
            return
        embed = discord.Embed(title="Admin Commands", color=discord.Color.green())
        embed.add_field(name="/admin-panel", value="Open the admin panel with buttons for team/scrim tools.", inline=False)
        embed.add_field(name="/settings", value="Open server settings (channels, roles, roster rules).(Comming soon)", inline=False)
        embed.add_field(name="/done", value="Mark a match done, lock the channel, and rename it.", inline=False)
        embed.add_field(name="/admin-manage", value="Admin manage teams", inline=False)
        embed.add_field(name="/start-seeding", value="Enable /standing", inline=False)
        embed.add_field(name="/end-seeding", value="Disable /standing", inline=False)
        embed.add_field(name="/delete-scheduling", value="Delete all scheduling channels (name contains -vs-)", inline=False)
        embed.add_field(name="/faq", value="Post the FAQ + role buttons.", inline=False)
        embed.add_field(name="/force-time", value="Propose a forced match time between two teams.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(name="list-teams", description="List all teams (everyone).")
    async def list_teams(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        data = load_teams()
        if not data:
            await interaction.followup.send("No teams found.", ephemeral=True)
            return

        seen_roles: set[int] = set()
        lines = ["Below is a list of teams:\n"]

        for entry in data:
            rid = entry.get("role_id")
            name = entry.get("name", "Unknown Team")
            if not rid:
                continue
            try:
                rid_int = int(rid)
            except ValueError:
                continue
            if rid_int in seen_roles:
                continue
            seen_roles.add(rid_int)

            role = guild.get_role(rid_int)
            if role:
                if not is_team_role(guild, role):
                    continue
                lines.append(f"> {role.mention} ({role.name})")
            else:
                lines.append(f"> {name} (role not found)")

        if len(lines) == 1:
            await interaction.followup.send("No valid teams found.", ephemeral=True)
            return

        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="player-info",
        description="View a player's league information (current and past teams).",
    )
    @app_commands.describe(member="The player to look up (leave empty to view yourself)")
    async def player_info(self, interaction: discord.Interaction, member: discord.Member | None = None):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if member is None:
            member = guild.get_member(interaction.user.id)

        current_team_role = find_single_team_for_member(guild, member)
        current_team_mention = current_team_role.mention if current_team_role else "None"

        history = load_player_history()
        entry = history.get(str(member.id), {})
        past = entry.get("past_teams", [])

        if current_team_role is None and not past:
            await interaction.followup.send(
                f"{member.mention} does not have any league information!",
                ephemeral=True,
            )
            return

        lines = [
            f"# League Information for {member.mention}:\n",
            f"Current Team: {current_team_mention}",
            "Past Teams:",
        ]
        if past:
            for name in past:
                lines.append(f"> {name}")
        else:
            lines.append("> None")

        await interaction.followup.send("\n".join(lines), ephemeral=True)


class FAQBracketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    class FAQRoleView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)

        async def _toggle_role_id(self, interaction: discord.Interaction, role_id: int, label: str):
            guild = interaction.guild
            if guild is None or not role_id:
                await interaction.response.send_message("That role is not configured.", ephemeral=True)
                return

            role = guild.get_role(role_id)
            if not role:
                await interaction.response.send_message("Configured role not found on this server.", ephemeral=True)
                return

            member = guild.get_member(interaction.user.id)
            if member is None:
                await interaction.response.send_message("Could not resolve your member object.", ephemeral=True)
                return

            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="FAQ role toggle")
                    await interaction.response.send_message(f"Removed {label}.", ephemeral=True)
                except Exception:
                    await interaction.response.send_message("Could not remove role (missing perms).", ephemeral=True)
            else:
                try:
                    await member.add_roles(role, reason="FAQ role toggle")
                    await interaction.response.send_message(f"Added {label}.", ephemeral=True)
                except Exception:
                    await interaction.response.send_message("Could not add role (missing perms).", ephemeral=True)


        @discord.ui.button(label="🚀 Unborn Captain", style=discord.ButtonStyle.secondary, custom_id="faq_unborn")
        async def faq_unborn(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle_role_id(interaction, UNBORN_CAPTAIN_ROLE_ID, "Unborn Captain")

        @discord.ui.button(label="🎉 Event Ping", style=discord.ButtonStyle.secondary, custom_id="faq_event")
        async def faq_event(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle_role_id(interaction, EVENT_PING_ROLE_ID, "Event Ping")

        @discord.ui.button(label="🦓 Scrim Referee", style=discord.ButtonStyle.secondary, custom_id="faq_scrim_ref")
        async def faq_scrim_ref(self, interaction: discord.Interaction, button: discord.ui.Button):
            await self._toggle_role_id(interaction, SCRIM_REFEREE_ROLE_ID, "Scrim Referee")

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="faq", description="Post the FAQ message to the FAQ channel (or here)")
    async def faq(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        faq_ch_id = CONFIG.get("channels", {}).get("faq")
        channel = guild.get_channel(faq_ch_id) if faq_ch_id else interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Could not resolve FAQ channel.", ephemeral=True)
            return

        content = (
            "# Pro Gorilla League Frequently Asked Questions\n\n"
            "## • How can I make a team/How do I get it official?\n\n"
            "> **Making a team is quite easy,**\n"
            "> - Simply make a discord for your team, and use recruitment-center,\n"
            "> - Getting your team official is another challenge however,\n"
            "> **The first step to getting your team official is getting unborn captain role!,**\n"
            "> - We will use <#1409042326042578984> to update you on our team situation! We pick the best teams we can from out forms, so make sure you are active and competitive!\n"
            "> - Teams normally get selected at the start of a new season or replacing an older team during seeding season,\n"
            "> **If you are interested, use our auto roles to join!**\n\n"
            "## • Moderation Support\n\n"
            "> - If you have any reports of players, please open a ticket so the moderation team can tend to it,\n"
            "> - Tickets are not a place for discussion or questions, if you have something to ask, please head over to questions!,\n\n"
            "## • Application Forms\n\n"
            "> - PGL has a various list of positions and applications to better help the league!,\n"
            "> - These applications are looked at when needed, you will be messaged if it is accepted\n"
            "> <#1409042394787090583>\n\n"
            "## • Referee Rules\n\n"
            "> - You can only ping @Scrim Referee for scrims, @Referee are only used for official matches.\n"
            "> - Pinging @Referee for a scrim will result in a 1 day mute.\n"
            "> - Only ping scrim refs in scrims.\n"
            "> - Post the DATE and TIME of the scrim, along with the two teams that are playing.\n"
            "> - DO NOT SPAM IT EVERY FEW MINUTES.\n\n"
            "# ー Role Assign\n"
            "> 🚀 **Unborn Captain** ー Allows you to apply your team to participate in the league!\n"
            "> 🎉 **Event Ping** ー Participate in events! (Will receive pings)\n"
            "> 🦓 **Scrim Referee** - Participate in scrims by being a referee! (Will receive pings)\n"
        )

        view = FAQBracketCog.FAQRoleView()

        try:
            await channel.send(content, view=view)
            await interaction.response.send_message(f"FAQ posted in {channel.mention}.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("Failed to post FAQ (check bot permissions).", ephemeral=True)


class BracketAdmin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="upload-bracket",
        description="Upload the base bracket image to be used by /bracket (admin only)."
    )
    @app_commands.describe(image="PNG/JPG base bracket image")
    async def upload_bracket(self, interaction: discord.Interaction, image: discord.Attachment):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("You do not have permission.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)

        if image is None:
            await interaction.followup.send("No attachment provided.", ephemeral=True)
            return

        fname = image.filename or "bracket.png"
        if not any(fname.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg")):
            await interaction.followup.send("Please upload a PNG or JPG image.", ephemeral=True)
            return

        try:
            data = await image.read()
            with open(BRACKET_BASE_IMAGE_PATH, "wb") as f:
                f.write(data)
        except Exception as e:
            await interaction.followup.send(f"Failed to save image: {e}", ephemeral=True)
            return

        # Resolve bracket channel
        bracket_ch = None
        if BRACKET_CHANNEL_ID and interaction.guild:
            bracket_ch = interaction.guild.get_channel(BRACKET_CHANNEL_ID)

        if not isinstance(bracket_ch, discord.TextChannel):
            await interaction.followup.send(f"Saved `{BRACKET_BASE_IMAGE_PATH}` but bracket channel not found or invalid.", ephemeral=True)
            return

        basename = os.path.basename(BRACKET_BASE_IMAGE_PATH)
        basename_lower = basename.lower()

        # normalization helper: remove spaces/underscores/dashes and lowercase
        def _norm(s: str) -> str:
            return re.sub(r"[\s_-]+", "", (s or "").lower())

        norm_basename = _norm(basename)

        # get bot member and perms
        try:
            bot_member = interaction.guild.me or await interaction.guild.fetch_member(self.bot.user.id)
        except Exception:
            bot_member = interaction.guild.me
        perms = bracket_ch.permissions_for(bot_member) if bot_member else discord.Permissions.none()
        can_read = bool(perms.read_message_history)
        can_manage = bool(perms.manage_messages)

        found_filenames = []
        deleted_count = 0
        failed_deletes = []

        if can_read:
            try:
                async for msg in bracket_ch.history(limit=1000):
                    if not msg or not msg.attachments:
                        continue
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    for att in msg.attachments:
                        fn = (att.filename or "").strip()
                        if not fn:
                            continue
                        found_filenames.append(fn)
                        norm_fn = _norm(fn)
                        # match if normalized names overlap (handles spaces/underscores/dashes and suffixes)
                        if norm_basename in norm_fn or norm_fn in norm_basename:
                            if can_manage:
                                try:
                                    await msg.delete()
                                    deleted_count += 1
                                except Exception as ex:
                                    failed_deletes.append((msg.id, str(ex)))
                            else:
                                failed_deletes.append((msg.id, "missing manage_messages"))
                            break
            except Exception as ex:
                failed_deletes.append(("history_scan", str(ex)))

        # post new file
        posted = False
        post_error = None
        try:
            with open(BRACKET_BASE_IMAGE_PATH, "rb") as f:
                file = discord.File(f, filename=basename)
                await bracket_ch.send(file=file)
            posted = True
        except Exception as ex:
            post_error = str(ex)

        # send detailed debug (including filenames found)
        summary = [
            f"Saved `{BRACKET_BASE_IMAGE_PATH}`.",
            f"Bracket channel: #{bracket_ch.name} (id: {bracket_ch.id})",
            f"Permissions: read_history={can_read} manage_messages={can_manage}",
            f"Found bot attachments checked: {len(found_filenames)}",
            f"Deleted messages: {deleted_count}",
            f"Failed deletes: {len(failed_deletes)}",
        ]
        if found_filenames:
            sample = found_filenames[:50]
            summary.append(f"Filenames found (sample up to 50): {sample}")
        if failed_deletes:
            sample_f = failed_deletes[:10]
            summary.append(f"Delete failures (sample up to 10): {sample_f}")
        if not posted:
            summary.append(f"Failed to post new file: {post_error}")

        await interaction.followup.send("\n".join(summary), ephemeral=True)

# ------------------------------ Auto-disband losing teams in single elimination -----------------------
SINGLE_ELIM = True  # set True for this season

class AutoDisbandScrim(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.channel.id != MATCH_SCORE_CHANNEL_ID:
            return
        if not globals().get("SINGLE_ELIM", False):
            return

        content = (message.content or "").strip()
        if not content:
            return

        lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
        winner_name = None
        loser_name = None
        for ln in lines:
            ln_clean = ln.lstrip("> ").strip()
            lower = ln_clean.lower()
            if lower.startswith("winner:"):
                winner_name = ln_clean.split(":", 1)[1].strip()
            elif lower.startswith("loser:"):
                loser_name = ln_clean.split(":", 1)[1].strip()

        if not loser_name:
            return

        guild = message.guild
        if guild is None:
            return

        # Resolve loser to a role
        loser_role = None
        raw = loser_name
        if raw.startswith("<@&") and raw.endswith(">"):
            try:
                rid = int(raw.strip("<@&>"))
                loser_role = guild.get_role(rid)
            except Exception:
                loser_role = None

        if loser_role is None:
            try:
                rid = int(raw)
                loser_role = guild.get_role(rid)
            except Exception:
                loser_role = None

        if loser_role is None:
            r = discord.utils.get(guild.roles, name=raw) or discord.utils.find(lambda rr: rr.name.lower() == raw.lower(), guild.roles)
            if r:
                loser_role = r

        if loser_role is None:
            teams = load_teams()
            for entry in teams:
                if entry.get("name", "").lower() == raw.lower():
                    rid = entry.get("role_id")
                    try:
                        rid_int = int(rid)
                        r = guild.get_role(rid_int)
                        if r:
                            loser_role = r
                            break
                    except Exception:
                        continue

        if loser_role is None:
            return

        # Safety: don't disband protected roles
        protected = {
            CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_PLAYER_ROLE_ID, TEAM_EXEC_ROLE_ID,
            HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID,
            UNBORN_CAPTAIN_ROLE_ID, EVENT_PING_ROLE_ID,
        }
        if loser_role.id in protected or loser_role.is_default() or loser_role.managed:
            return

        tx_ch = guild.get_channel(TRANSACTIONS_CHANNEL_ID)

        try:
            removed_members = 0
            # Prepare global role objects once
            cap_role = guild.get_role(CAPTAIN_ROLE_ID)
            co_role = guild.get_role(CO_CAPTAIN_ROLE_ID)
            exec_role = guild.get_role(TEAM_EXEC_ROLE_ID)
            player_role = guild.get_role(TEAM_PLAYER_ROLE_ID)

            for m in list(guild.members):
                if m.bot:
                    continue
                if loser_role in m.roles:
                    roles_to_remove = [loser_role]
                    # remove global roles if present on this member
                    for r in (cap_role, co_role, exec_role, player_role):
                        if r and r in m.roles:
                            roles_to_remove.append(r)
                    try:
                        await m.remove_roles(*roles_to_remove, reason="Auto-disband (single elimination)")
                        removed_members += 1
                    except Exception:
                        pass

            # delete the role itself
            try:
                await loser_role.delete(reason="Auto-disband (single elimination)")
            except Exception:
                pass

            # send transaction message
            if isinstance(tx_ch, discord.TextChannel):
                try:
                    await tx_ch.send(f"# {loser_role.name} HAS BEEN DISBANDED\n\n")
                except Exception:
                    pass

        except Exception:
            return



# --------------------  CommandGuideCog ----------------------
class CommandGuideCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._posted_once = False  # avoid running twice per process

    @commands.Cog.listener()
    async def on_ready(self):
        # run only once per bot process
        if self._posted_once:
            return
        self._posted_once = True

        for guild in self.bot.guilds:
            ch = guild.get_channel(TRANSACTIONS_HELP_CHANNEL_ID)
            if not isinstance(ch, discord.TextChannel):
                continue

            # Check if the guide is already there
            already = False
            try:
                async for msg in ch.history(limit=200):
                    if msg.author.id != self.bot.user.id:
                        continue
                    if not msg.embeds:
                        continue
                    emb = msg.embeds[0]
                    if (emb.title or "").strip().lower() == "PGL command guide":
                        already = True
                        break
            except Exception:
                continue

            if already:
                continue

            # Build the guide embed (blue)
            embed = discord.Embed(
                title="PGL Command Guide",
                description="What every command does and who can use it:",
                color=discord.Color.blue(),
            )

            # 👤 Everyone
            everyone_value = (
                "/info - Shows this list and basic info.\n"
                "/roster - Shows your team’s roster (or a default team).\n"
                "/manage-team - View your team roster; captains/co-caps can manage it.\n"
                "/standing - View league standings (only when seeding is enabled).\n"
                "/list-teams - Lists all registered teams.\n"
                "/player-info - Shows a player's current team and past teams.\n"
                "/headsets - View the list of allowed VR headsets (only you can see it)"
            )
            embed.add_field(name="👤 Everyone", value=everyone_value, inline=False)

            # 👑 Captains & Co-Captains
            cc_value = (
                "/manage-team - Use the buttons to:\n"
                "• Invite players to your team.\n"
                "• Kick players from your team.\n"
                "• Promote players to Co-Captain.\n"
                "• Assign a Team Executive.\n"
                "• Transfer Captain to another staff member.\n"
                "• Disband your team.\n"
            )
            embed.add_field(name="👑 Captains & Co-Captains", value=cc_value, inline=False)

            # 🔧 Administrators
            admin_value = (
                "/admin-panel - Open the admin panel with buttons for team/scrim tools.\n"
                "/settings - View league settings (channels, roles, roster rules).(Comming soon)\n"
                "/admin-manage - Admin view/manage any team roster.\n"
                "/done - Mark a match done, lock the channel, and rename it.\n"
                "/start-seeding - Enable standings and seeding logic.\n"
                "/end-seeding - Disable standings and end seeding.\n"
                "/delete-scheduling - Delete all scheduling channels (-vs-).\n"
                "/faq - Post the FAQ + role buttons.\n"
                "/force-time - Propose a forced match time between two teams.\n"
            )
            embed.add_field(name="🔧 Administrators", value=admin_value, inline=False)

            # 🧰 Staff / Utility (message-based)
            staff_value = (
                ".!saysmth / !saysmth - Admin-only utility to send a message (with pings) "
                "to any channel by ID.\n"
            )
            embed.add_field(name="🧰 Staff Utility", value=staff_value, inline=False)

            embed.set_footer(text="PGL Season Management System")

            try:
                await ch.send(embed=embed)
            except Exception:
                continue





class ForfeitCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # Small helper to extract team names from a match channel
    def _extract_teams_from_channel(self, ch: discord.TextChannel) -> tuple[Optional[str], Optional[str]]:
        """
        Try to get 'Team1' and 'Team2' from channel name/topic like 'team1-vs-team2'
        or topic 'Team1 Vs Team2'.
        """
        name = ch.name or ""
        topic = ch.topic or ""

        # Try topic "Team1 Vs Team2"
        if topic and " Vs " in topic:
            parts = topic.split(" Vs ", 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()

        # Fallback: channel name "team1-vs-team2"
        lower_name = name.lower()
        if "-vs-" in lower_name:
            p1, p2 = lower_name.split("-vs-", 1)
            t1 = p1.replace("-", " ").strip()
            t2 = p2.replace("-", " ").strip()
            return t1 or None, t2 or None

        return None, None

    def _is_team_staff(self, member: discord.Member) -> bool:
        return any(
            has_role_id(member, rid)
            for rid in (CAPTAIN_ROLE_ID, CO_CAPTAIN_ROLE_ID, TEAM_EXEC_ROLE_ID)
        )

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.command(
        name="forfeit",
        description="Forfeit the current match (captains/co-captains/executives only).",
    )
    async def forfeit(self, interaction: discord.Interaction):
        guild = interaction.guild
        ch = interaction.channel

        if guild is None or not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(
                "Use this in a server text channel.",
                ephemeral=True,
            )
            return

        member = guild.get_member(interaction.user.id)
        if member is None:
            await interaction.response.send_message(
                "Could not resolve your member object.",
                ephemeral=True,
            )
            return

        # Check permissions: captain / co-captain / executive
        if not self._is_team_staff(member):
            await interaction.response.send_message(
                "Only captains, co-captains, or executives can forfeit.",
                ephemeral=True,
            )
            return

        # Find the member's team
        team_role = get_user_team_role(member)
        if team_role is None:
            await interaction.response.send_message(
                "You are not on a team.",
                ephemeral=True,
            )
            return

        my_team_name = team_role.name

        # Extract channel teams
        t1_name, t2_name = self._extract_teams_from_channel(ch)
        if not t1_name or not t2_name:
            await interaction.response.send_message(
                "Could not determine both teams from this channel. Make sure you use /forfeit in the match/scheduling channel.",
                ephemeral=True,
            )
            return

        # Normalize for comparison
        t1_l = t1_name.lower()
        t2_l = t2_name.lower()
        my_l = my_team_name.lower()

        if my_l == t1_l:
            forfeiting_team = t1_name
            other_team = t2_name
        elif my_l == t2_l:
            forfeiting_team = t2_name
            other_team = t1_name
        else:
            # Try resolving via roles if names don't match exactly
            t1_role, _, _ = resolve_team_any(guild, t1_name)
            t2_role, _, _ = resolve_team_any(guild, t2_name)

            if t1_role and t1_role.id == team_role.id:
                forfeiting_team = t1_name
                other_team = t2_name
            elif t2_role and t2_role.id == team_role.id:
                forfeiting_team = t2_name
                other_team = t1_name
            else:
                await interaction.response.send_message(
                    "Your team does not appear to be one of the teams in this channel.",
                    ephemeral=True,
                )
                return

        # Order them for the header line
        team1_display = t1_name
        team2_display = t2_name

        winner_name = other_team
        loser_name = forfeiting_team

        score_ch = guild.get_channel(MATCH_SCORE_CHANNEL_ID)
        if not isinstance(score_ch, discord.TextChannel):
            await interaction.response.send_message(
                "Match score channel is not configured.",
                ephemeral=True,
            )
            return

        # Score message formatted to match your other tools
        score_msg = (
            f"{team1_display} vs {team2_display}\n"
            f"> Winner: {winner_name}\n"
            f"> Score: 0-0\n"
            f"> Timecap: no\n"
            f"> Loser: {loser_name}"
        )

        try:
            await score_ch.send(score_msg)
            await score_ch.send(f"{loser_name} forfeited.")
        except Exception:
            await interaction.response.send_message(
                "Failed to submit forfeit score (check bot permissions).",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"You forfeited the match. Winner: **{winner_name}**.",
            ephemeral=True,
        )




class RescrimCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(
        name="rescrim",
        description="Create a rematch announcement between two teams (admins only).",
    )
    @app_commands.describe(
        team1="Team 1 (mention / role / id / name)",
        team2="Team 2 (mention / role / id / name)",
    )
    async def rescrim(
        self,
        interaction: discord.Interaction,
        team1: str,
        team2: str,
    ):
        guild = interaction.guild
        channel = interaction.channel

        if guild is None or not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Use this in a server text channel.",
                ephemeral=True,
            )
            return

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "You do not have permission to use this.",
                ephemeral=True,
            )
            return

        # resolve teams
        t1_role, _t1_mention_raw, t1_name = resolve_team_any(guild, team1)
        t2_role, _t2_mention_raw, t2_name = resolve_team_any(guild, team2)

        if not t1_name or not t2_name:
            await interaction.response.send_message(
                "Could not resolve one or both teams.",
                ephemeral=True,
            )
            return

        # Only @ if role exists; otherwise just use the name
        t1_display = t1_role.mention if isinstance(t1_role, discord.Role) else t1_name
        t2_display = t2_role.mention if isinstance(t2_role, discord.Role) else t2_name

        msg = (
            f"{t1_display} and {t2_display}\n"
            "# This Will Be A Rematch\n"
            "Our staff have decided to do a rematch and here are the stuff you’ll need:\n\n"
            "- Team Abbreviations (**Referee can give warnings**)\n"
            "- Discord Display Name (**Referee can give warnings**)\n"
            "- A Clean Mind\n"
            "- Sound Soul\n"
            "- And Stout Heart In Defeat."
        )

        # Post the rematch message (channel remains private)
        await channel.send(msg)

        # Remove leading ✅ from channel name if present
        try:
            old_name = channel.name or ""
            if old_name.startswith("✅"):
                new_name = old_name.lstrip("✅").lstrip("-").lstrip()
                if not new_name:
                    new_name = old_name
                await channel.edit(name=new_name, reason=f"Rescrim via /rescrim by {interaction.user}")
        except Exception:
            pass

        # Explicitly remove access for ref/caster roles for the whole time
        try:
            overwrites = channel.overwrites

            for rid in (HEAD_REF_ROLE_ID, REF_ROLE_ID, HEAD_CASTER_ROLE_ID, CASTER_ROLE_ID):
                role = guild.get_role(rid)
                if not role:
                    continue
                ow = overwrites.get(role, discord.PermissionOverwrite())
                ow.view_channel = False
                ow.send_messages = False
                overwrites[role] = ow

            await channel.edit(overwrites=overwrites, reason=f"/rescrim (lock refs/casters) by {interaction.user}")
        except Exception:
            # best-effort; don't fail the command on perms error
            pass

        await interaction.response.send_message(
            "Rematch message posted, channel kept private, ✅ removed, and refs/casters locked out.",
            ephemeral=True,
        )




# ---------------- Admin command: delete scheduling channels ----------------
class SchedulingAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.guilds(Object(id=TEST_GUILD_ID))
    @app_commands.default_permissions(administrator=True)
    @app_commands.command(name="delete-scheduling", description="Delete all scheduling channels (name contains -vs-).")
    async def delete_scheduling(self, interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Use this in a server.", ephemeral=True)
            return

        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

        deleted = 0
        for ch in list(guild.text_channels):
            try:
                if "-vs-" in (ch.name or "").lower():
                    await ch.delete(reason=f"/delete-scheduling by {interaction.user}")
                    deleted += 1
            except Exception:
                pass

        msg = f"Deleted {deleted} scheduling channels."
        try:
            await interaction.followup.send(msg, ephemeral=True)
            return
        except Exception:
            pass

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(msg, ephemeral=True)
                return
        except Exception:
            pass

        try:
            if interaction.channel and isinstance(interaction.channel, discord.abc.Messageable):
                await interaction.channel.send(msg)
        except Exception:
            pass


# ---------------- BOT SETUP ----------------
class MainBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self._web_runner: web.AppRunner | None = None

    async def setup_hook(self):
        guild_obj = Object(id=TEST_GUILD_ID)
        cog_names = [
            "SettingsCog",
            "AdminPanel",
            "ManageTeam",
            "DoneCommand",
            "RosterCog",          # <-- this must match the class name above
            "InfoCommands",
            "AdminManage",
            "FAQBracketCog",
            "StandingCog",
            "SchedulingAdmin",
            "BracketAdmin",
            "LeaveCog",
            "AutoDisbandScrim",
            "SaySomethingCog",
            "ForceTimeCog",
            "CommandGuideCog",
            "AutoCodeCog",
            "HeadsetInfoCog",
            "RescrimCog",
            "ScrimCheckCog",
            "ForfeitCog",
        ]

        for name in cog_names:
            cls = globals().get(name)
            if cls is None:
                print(f"Skipping cog {name}: not defined")
                continue
            try:
                await self.add_cog(cls(self))
                print(f"Added cog: {name}")
            except Exception:
                import traceback
                traceback.print_exc()
                print(f"Failed to add cog: {name}")

        try:
            await self.tree.sync(guild=guild_obj)
            print("Commands synced.")
        except Exception:
            import traceback
            traceback.print_exc()
            print("Failed to sync commands.")



bot = MainBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

if __name__ == "__main__":
    bot.run(os.getenv("BOT_TOKEN"))

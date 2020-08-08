import discord
import asyncio
from typing import List, Dict, Tuple, Optional, Iterable
from enum import Enum

from constant.emoji import NB, LETTER
from util.function import get_member_in_channel
from util.exception import InvalidArgs
from .Leaders import leaders
from .Draft import BlindDraft, get_draft, draw_draft
from .constant import TURKEY

DRAFT_MODE_TITLE = "Mode de draft"
class DraftMode(Enum):
    WITH_TRADE = "Trade autorisé"
    NO_TRADE = "Trade interdit"
    BLIND = "Aveugle"
    RANDOM = "All Random"

EMOJI = str
VOTED_SETTINGS : Dict[str, List[Tuple[EMOJI, str]]] = {
    "Map": [(LETTER.P, "Pangée"), (LETTER.C, "Contient & Iles"), (NB[7], "7 mers"), (LETTER.L, "Lacs"), (LETTER.A, "Archipelle"), (LETTER.F, "Fractale"),
            ("🏝️", "Plateau d'ile"), ("🌋", "Primordial"), (LETTER.T, "Tilted Axis"), (LETTER.M, "Mer Intérieure"), ("🌍", "Terre"), ("❓", "Aléatoire")],
    "Diplo": [("🦄", "Normal Diplo"), ("➕", "Diplo +"), ("🦅", "Always War"), ("🐨", "Always Peace")],
    "Timer": [("🕑", "Dynamique"), ("⏩", "Compétitif"), ("🔥", "90s"), ("🦘", "Sephi n+30"), ("🇿", "ZLAN")],
    "Age du monde": [("🗻", "Normal"), ("🌋", "Nouveau")],
    "Nukes": [("☢️", "Autorisées"), ("⛔", "Interdites")],
    "Ressources": [(LETTER.C, "Classique"), (LETTER.A, "Abondante")],
    "Stratégiques": [(LETTER.C, "Classique"), (LETTER.A, "Abondante"), (LETTER.E, "Epique"), (LETTER.G, "Garentie")],
    "Ridges definition": [(LETTER.S, "Standard"), (LETTER.V, "Vanilla"), (LETTER.L, "Large opening"), (LETTER.I, "Impénétrable")],
    "Catastrophe": [(NB[0], "0"), (NB[1], "1"), (NB[2], "2"), (NB[3], "3"), (NB[4], "4")],
    DRAFT_MODE_TITLE: [("✅", DraftMode.WITH_TRADE.value), ("🚫", DraftMode.NO_TRADE.value), ("🙈", DraftMode.BLIND.value), ("❓", DraftMode.RANDOM.value)]
}

class Voting:
    def __init__(self, members):
        self.members = members
        self.members_id = [i.id for i in members]
        self.waiting_members = self.members_id[:]
        self.result = {i: None for i in VOTED_SETTINGS}
        self.majority = len(self.members) // 2 + 1
        self.banned_leaders = []
        self.draft_mode = None

    async def run(self, channel : discord.TextChannel, client : discord.Client):
        await channel.send("Liste des joueurs: " + ' '.join(i.mention for i in self.members))
        sended = await asyncio.gather(*[self.send_line(k, v, channel) for k, v in VOTED_SETTINGS.items()])
        ban_msg = await self.send_ban_msg(channel)
        confirm_msg = await self.send_confirm_msg(channel)
        votes_msg_ids = [i.id for i in sended]
        msg_ids = [*votes_msg_ids, ban_msg.id, confirm_msg.id]
        msg_to_vote : Dict[int, Tuple[str, List[Tuple[EMOJI, str]]]] = {sended[i].id: (name, v) for i, (name, (v)) in enumerate(VOTED_SETTINGS.items())}

        def check(reac_ : discord.Reaction, user_ : discord.User):
            return reac_.message.id in msg_ids

        while True:
            reaction, user = await client.wait_for('reaction_add', check=check, timeout=600)  # type: (discord.Reaction, discord.User)
            if user.id not in self.members_id and user.id != client.user.id:
                try:
                    await reaction.remove(user)
                except discord.HTTPException:
                    pass
                continue

            if reaction.message.id == confirm_msg.id and user.id in self.waiting_members:
                self.waiting_members.remove(user.id)
                await self.edit_confirm_msg(confirm_msg)
                if not self.waiting_members:
                    break
            if reaction.message.id == ban_msg.id:
                emoji : discord.Emoji = reaction.emoji
                if not isinstance(emoji, discord.Emoji):
                    continue
                leader = leaders.get_leader_by_emoji_id(reaction.emoji.id)
                if not leader:
                    continue
                if (await self.is_vote_winner(reaction)) and leader not in self.banned_leaders:
                    self.banned_leaders.append(leader)
                    await self.edit_ban_msg(ban_msg, client)
            elif reaction.message.id in votes_msg_ids and (await self.is_vote_winner(reaction)):
                winner = self.get_winner_by_emoji_str(str(reaction.emoji), msg_to_vote[reaction.message.id])
                if not winner:
                    continue
                msg : discord.Message = reaction.message
                await asyncio.gather(msg.clear_reactions(), msg.edit(content="__**{0[0]}**__: {0[1]} {0[2]}".format(winner)))
                if winner[0] == DRAFT_MODE_TITLE:
                    self.draft_mode = DraftMode(winner[2])

        # Run draft
        if not self.draft_mode:
            await channel.send("WARNING : Aucun mode de draft n'a été voté, une draft FFA classique va donc être lancé.")
            self.draft_mode = DraftMode.NO_TRADE
        if self.draft_mode in (DraftMode.NO_TRADE, DraftMode.WITH_TRADE):
            drafts = get_draft(len(self.members), '.'.join(str(i) for i in self.banned_leaders), client=client)
            await draw_draft(drafts, (m.mention for m in self.members), channel)
            return
        if self.draft_mode == DraftMode.RANDOM:
            await channel.send("Le mode de draft sélectionné étant All Random, la draft est terminé !")
            return
        if self.draft_mode == DraftMode.BLIND:
            draft = BlindDraft(self.members, '.'.join(str(i) for i in self.banned_leaders))
            await draft.run(channel, client)
            return




    @staticmethod
    async def send_ban_msg(channel) -> discord.Message:
        msg = await channel.send("__**Bans**__: Sélectionnez les civs à bannir depuis la liste des emojis.")
        await msg.add_reaction("🚫")
        return msg

    async def edit_ban_msg(self, msg, client):
        await msg.edit(content="__**Bans**__: Sélectionnez les civs à bannir depuis la liste des emojis.\n" +
                       '\n'.join(f"{client.get_emoji(i.emoji_id)} {i.civ}" for i in self.banned_leaders))

    async def send_confirm_msg(self, channel) -> discord.Message:
        msg = await channel.send("En attente de : " + ', '.join(f"<@{i}>" for i in self.waiting_members))
        await msg.add_reaction(TURKEY)
        return msg

    async def edit_confirm_msg(self, msg):
        await msg.edit(content="En attente de : " + ', '.join(f"<@{i}>" for i in self.waiting_members))

    async def is_vote_winner(self, reaction : discord.Reaction) -> bool:
        users = await reaction.users().flatten()
        ls = list(filter(lambda user: user.id in self.members_id, users))
        if len(ls) >= self.majority:
            return True
        return False

    @staticmethod
    async def send_line(name, line, channel):
        msg = await channel.send(f"__**{name}**__:  " + '  |  '.join(f"{i} {j}" for i, j in line))
        for reaction, _ in line:
            await msg.add_reaction(reaction)
        return msg

    def get_winner_by_emoji_str(self, reaction_str : EMOJI, vote : Tuple[str, Iterable[Tuple[EMOJI, str]]]) -> Optional[Tuple[str, EMOJI, str]]:
        for line in vote[1]:
            if line[0] == reaction_str:
                return (vote[0], *line)
        return None


class CmdCivFRVoting:
    async def cmd_vote(self, *args, member, message : discord.Message, channel, client, **_):
        if not args:
            members = get_member_in_channel(member.voice)
        else:
            members = message.mentions
            if not members:
                raise InvalidArgs("Vous devez sois laisser la commande vide, ou bien notifier chacune des personnes participant au vote")
        voting = Voting(members)
        await voting.run(channel, client)

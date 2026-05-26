import os
import time
from flask import Flask, render_template, request, redirect, url_for, session
import random

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nasilemak_multiplayer_secret_key_2026")

BOT_PREFIX = "🤖Bot_"  # 机器人名字前缀，用于识别

CORE_5 = ["Rice", "Egg", "Peanuts", "Sambal", "Cucumber"]

def create_gold_deck():
    # 3 Nasi Lemak cards (1 pack each) + original 8x1 + 7x2
    deck = [1] * 11 + [2] * 7
    random.shuffle(deck)
    return deck

def create_main_deck():
    deck = []
    for ing in CORE_5:
        deck.extend([ing] * 10)
    deck.extend(["Rendang"] * 6)
    deck.extend(["Crow"] * 2)
    deck.extend(["Si Oyen"] * 3)
    deck.extend(["Wholesaler"] * 4)
    deck.extend(["Thief"] * 4)
    deck.extend(["Supplier"] * 4)
    deck.extend(["Mak Cik"] * 4)
    deck.extend(["Officer"] * 4)
    deck.extend(["Fly"] * 6)
    deck.extend(["Fly Swatter"] * 2)
    deck.extend(["Fan"] * 3)
    for _ in range(3): random.shuffle(deck)
    return deck

class OnlineGameState:
    def __init__(self, player_names):
        self.main_deck = create_main_deck()
        self.gold_deck = create_gold_deck()
        self.discard = []
        self.players = []
        for name in player_names:
            self.players.append({
                "name": name,
                "hand": [],
                "scored_cards": [],
                "flies": [],
                # placed_crow: None or {"ingredients": [...]}
                "placed_crow": None,
            })
        self.turn_idx = random.randint(0, len(self.players) - 1)
        self.moves_left = 3
        self.has_drawn = False
        self.game_over = False
        self.winner = ""
        self.log = [f"🎲 游戏正式开始！系统随机抽签，由 【{self.players[self.turn_idx]['name']}】 率先行动！"]
        self.active_inspection = None
        self.pending_trade = None
        self.wholesaler_reveal = None
        self.thief_pending = False
        self._bot_turn_pending = False

        for p in self.players:
            for _ in range(7):
                if self.main_deck: p["hand"].append(self.main_deck.pop())
            p["hand"].sort()

    def current_player(self):
        return self.players[self.turn_idx]

    def draw_from_deck(self, p_idx, count=1):
        p = self.players[p_idx]
        drawn = []
        for _ in range(count):
            if not self.main_deck:
                if self.discard:
                    self.main_deck = self.discard[:]
                    self.discard.clear()
                    for _ in range(3): random.shuffle(self.main_deck)
                    self.log.append("🔄 摸牌堆空了！弃牌堆已进行【深度混乱洗牌】重用。")
                else: break
            card = self.main_deck.pop()
            p["hand"].append(card)
            drawn.append(card)
        p["hand"].sort()
        return drawn

    def check_win(self):
        for p in self.players:
            net_packs = sum(val for idx, val in enumerate(p["scored_cards"]) if not p["flies"][idx])
            if net_packs >= 5:
                self.game_over = True
                self.winner = p["name"]
                self.log.append(f"👑 【{p['name']}】 成功卖出 {net_packs} 包净椰浆饭，赢得了胜利！")
                return True
        return False

    def spend_move(self, action_description):
        self.moves_left -= 1
        self.log.append(f"🎬 消耗动作：{action_description}（剩 {self.moves_left} 次动作）")
        if self.check_win():
            return
        if self.moves_left <= 0 and not self.pending_trade and not self.thief_pending and not getattr(self, 'wholesaler_reveal', None):
            self.end_turn()

    def end_turn(self):
        self.pending_trade = None
        self.wholesaler_reveal = None
        self.thief_pending = False
        if self.check_win():
            return
        if not self.gold_deck:
            self.game_over = True
            highest_packs = -1
            winner_p = None
            for p in self.players:
                packs = sum(val for idx, val in enumerate(p["scored_cards"]) if not p["flies"][idx])
                if packs > highest_packs:
                    highest_packs = packs
                    winner_p = p
                elif packs == highest_packs and winner_p:
                    if len(p["scored_cards"]) > len(winner_p["scored_cards"]): winner_p = p
            self.winner = winner_p["name"]
            self.log.append(f"📦 金卡堆耗尽！平局清算获胜者：{self.winner}")
            return
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self.moves_left = 3
        self.has_drawn = False
        self.active_inspection = None
        self.log.append(f"🟢 轮到 【{self.players[self.turn_idx]['name']}】 的回合。")
        # 如果下一个是机器人，自动行动
        self._bot_turn_pending = True

class GlobalRoom:
    def __init__(self):
        self.status = "EMPTY"
        self.joined_players = []
        self.game = None
        self.chat_messages = []

room = GlobalRoom()

# ============================================================
# 机器人 AI 逻辑
# ============================================================

def is_bot(name):
    return str(name).startswith(BOT_PREFIX)

def bot_generate_name():
    """生成一个唯一的机器人名字"""
    emojis = ["🐼","🦊","🐸","🐧","🦁","🐯","🐻","🦉"]
    adjectives = ["懒","快","猛","萌","乖","皮","强","酷"]
    used = set(room.joined_players)
    for _ in range(30):
        e = random.choice(emojis)
        a = random.choice(adjectives)
        n = f"{BOT_PREFIX}{e}{a}"
        if n not in used:
            return n
    return f"{BOT_PREFIX}玩家{random.randint(100,999)}"

def bot_take_turn(g, bot_idx):
    """机器人行动：每次调用执行完整的一个回合（摸牌 + 尽量行动 + 结束）"""
    p = g.players[bot_idx]

    # ── 1. 摸牌 ──────────────────────────────────────────────
    if not g.has_drawn:
        g.draw_from_deck(bot_idx, 2)
        g.has_drawn = True
        g.log.append(f"📥 【{p['name']}】 抽取了 2 张手牌。")

    # ── 2. 如果有待处理的交易（机器人是被请求方），随机接受 ──
    if g.pending_trade and g.pending_trade["to"] == p["name"]:
        t = g.pending_trade
        want_card = t["want"]
        if want_card in p["hand"] and random.random() < 0.6:
            # 接受交易
            p_from = next(x for x in g.players if x["name"] == t["from"])
            if t["offer"] in p_from["hand"]:
                p_from["hand"].remove(t["offer"]); p["hand"].append(t["offer"])
                p["hand"].remove(want_card); p_from["hand"].append(want_card)
                p_from["hand"].sort(); p["hand"].sort()
                g.log.append(f"🤝 【{p['name']}】(机器人) 接受了交易！")
            else:
                g.log.append(f"❌ 交易破裂（机器人接受时发牌方已无牌）")
        else:
            g.log.append(f"🚫 【{p['name']}】(机器人) 拒绝了交易。")
        g.pending_trade = None
        if g.moves_left <= 0:
            g.end_turn()
        return

    if g.game_over:
        return

    # ── 3. 执行动作（最多3次） ────────────────────────────────
    actions_taken = 0
    max_actions = g.moves_left

    for _ in range(max_actions):
        if g.game_over or g.moves_left <= 0:
            break
        if g.pending_trade or g.thief_pending:
            break
        did_action = _bot_do_one_action(g, bot_idx)
        if did_action:
            actions_taken += 1
        else:
            break  # 无事可做，提前结束

    # ── 4. 如果还没结束回合，手动结束 ──────────────────────────
    if not g.game_over and g.moves_left > 0:
        g.end_turn()


def _bot_do_one_action(g, bot_idx):
    """机器人执行单个动作，返回 True 表示成功执行了一个动作"""
    p = g.players[bot_idx]
    hand = p["hand"]

    # ── 优先：赶走自己面前的乌鸦 ─────────────────────────────
    if p.get("placed_crow"):
        # 找一个没乌鸦的对手
        chase_ingredients = [c for c in hand if c in CORE_5 + ["Rendang"]]
        targets_no_crow = [i for i, x in enumerate(g.players)
                           if x["name"] != p["name"] and x.get("placed_crow") is None]
        if chase_ingredients and targets_no_crow:
            ing = chase_ingredients[0]
            tgt_idx = random.choice(targets_no_crow)
            tgt = g.players[tgt_idx]
            hand.remove(ing)
            old_ings = p["placed_crow"]["ingredients"] + [ing]
            p["placed_crow"] = None
            tgt["placed_crow"] = {"ingredients": old_ings}
            g.spend_move(f"🐦‍⬛ 【{p['name']}】(机器人) 用[{ing}]把乌鸦赶到了【{tgt['name']}】！")
            return True
        # 没有食材赶乌鸦，什么都做不了
        return False

    # ── 尝试打包 ──────────────────────────────────────────────
    if g.gold_deck:
        rendang_count = hand.count("Rendang")
        missing_core = [i for i in CORE_5 if i not in hand]

        # 标准打包
        if len(missing_core) <= rendang_count:
            for i in CORE_5:
                if i in hand: hand.remove(i)
                else: hand.remove("Rendang")
            p["scored_cards"].append(g.gold_deck.pop())
            p["flies"].append(False)
            g.spend_move(f"【{p['name']}】(机器人) 打包了一份椰浆饭")
            return True

        # 大妈代工（≥3种食材）
        if "Mak Cik" in hand:
            unique_ings = list(set([i for i in CORE_5 if i in hand]))
            rendang_count = hand.count("Rendang")
            
            if len(unique_ings) + rendang_count >= 3:
                hand.remove("Mak Cik")
                # 扣除现有的普通食材
                cards_to_remove = unique_ings[:3]
                for card in cards_to_remove: 
                    hand.remove(card)
                # 不够的用 Rendang 补
                needed_rendang = 3 - len(cards_to_remove)
                for _ in range(needed_rendang): 
                    hand.remove("Rendang")
                    
                p["scored_cards"].append(g.gold_deck.pop())
                p["flies"].append(False)
                g.spend_move(f"【{p['name']}】(机器人) 狡猾地利用大妈和 {needed_rendang} 张Rendang代工打包了椰浆饭！")
                return True

    # ── 使用苍蝇拍 ────────────────────────────────────────────
    if "Fly Swatter" in hand:
        fly_idxs = [i for i, f in enumerate(p["flies"]) if f]
        if fly_idxs:
            idx = fly_idxs[0]
            hand.remove("Fly Swatter")
            g.discard.append("Fly Swatter"); g.discard.append("Fly")
            p["flies"][idx] = False
            g.spend_move(f"💥 【{p['name']}】(机器人) 打死了自己饭上的苍蝇")
            return True

    # ── 放苍蝇到对手饭上 ──────────────────────────────────────
    if "Fly" in hand:
        targets_with_food = [(i, x) for i, x in enumerate(g.players)
                             if x["name"] != p["name"] and x["scored_cards"]
                             and False in x["flies"]]
        if targets_with_food:
            tgt_idx, tgt = random.choice(targets_with_food)
            slot = tgt["flies"].index(False)
            hand.remove("Fly")
            tgt["flies"][slot] = True
            g.spend_move(f"🪰 【{p['name']}】(机器人) 把苍蝇放到了【{tgt['name']}】的饭上！")
            return True

    # ── 使用乌鸦骚扰对手 ──────────────────────────────────────
    if "Crow" in hand:
        targets_no_crow = [(i, x) for i, x in enumerate(g.players)
                           if x["name"] != p["name"] and x.get("placed_crow") is None]
        if targets_no_crow:
            tgt_idx, tgt = random.choice(targets_no_crow)
            hand.remove("Crow")
            tgt["placed_crow"] = {"ingredients": []}
            g.spend_move(f"🐦‍⬛ 【{p['name']}】(机器人) 把乌鸦放到了【{tgt['name']}】面前！")
            return True

    # ── Si Oyen 消灭乌鸦 ──────────────────────────────────────
    if "Si Oyen" in hand and p.get("placed_crow"):
        hand.remove("Si Oyen"); g.discard.append("Si Oyen")
        crow_ings = p["placed_crow"]["ingredients"]
        p["placed_crow"] = None
        for ing in crow_ings: hand.append(ing)
        hand.sort()
        g.spend_move(f"🐱 【{p['name']}】(机器人) 用Si Oyen消灭了乌鸦！")
        return True

    # ── 批发商摸牌 ─────────────────────────────────────────────
    if "Wholesaler" in hand and len(hand) < 8:
        hand.remove("Wholesaler"); g.discard.append("Wholesaler")
        g.draw_from_deck(bot_idx, 3)
        g.wholesaler_reveal = None  # 机器人直接跳过展示
        g.spend_move(f"【{p['name']}】(机器人) 用批发商摸了3张牌")
        return True

    # ── 供应商征收 ─────────────────────────────────────────────
    if "Supplier" in hand:
        # 征收自己最需要的食材
        have = set(c for c in hand if c in CORE_5)
        need = [i for i in CORE_5 if i not in have]
        if need:
            target_ing = need[0]
            hand.remove("Supplier"); g.discard.append("Supplier")
            total = 0
            for opp in g.players:
                if opp["name"] != p["name"]:
                    matches = [c for c in opp["hand"] if c == target_ing]
                    for m in matches:
                        opp["hand"].remove(m); hand.append(m); total += 1
            hand.sort()
            g.spend_move(f"【{p['name']}】(机器人) 供应商征收了全场[{target_ing}] 共{total}张")
            return True

    # ── 小偷 ──────────────────────────────────────────────────
    if "Thief" in hand:
        opponents = [opp for opp in g.players if opp["name"] != p["name"] and opp["hand"]]
        if opponents:
            hand.remove("Thief"); g.discard.append("Thief")
            stolen = 0
            sample = random.sample(opponents, min(3 if len(g.players) > 4 else len(opponents), len(opponents)))
            for opp in sample:
                if opp["hand"]:
                    card = random.choice(opp["hand"])
                    opp["hand"].remove(card); hand.append(card); stolen += 1
            hand.sort()
            names = "、".join(o["name"] for o in sample)
            g.spend_move(f"🥷 【{p['name']}】(机器人) 从【{names}】偷走了{stolen}张牌")
            return True

    # ── 没有好的动作可执行 ────────────────────────────────────
    return False

@app.route('/')
def index():
    my_name = session.get('my_name', None)
    error_msg = request.args.get('error', None)
    my_player_obj = None
    my_p_idx = -1
    trade_time_left = 0

    if my_name:
        if room.status == "EMPTY":
            session.pop('my_name', None); my_name = None
        elif room.status == "WAITING" and my_name not in room.joined_players:
            session.pop('my_name', None); my_name = None
        elif room.status == "PLAYING" and room.game:
            if my_name not in [p["name"] for p in room.game.players]:
                session.pop('my_name', None); my_name = None

    if room.status == "PLAYING" and room.game:
        # 如果轮到机器人，自动执行
        if getattr(room.game, '_bot_turn_pending', False):
            room.game._bot_turn_pending = False
            _trigger_bot_if_needed()
        if room.game.pending_trade:
            trade_time_left = int(room.game.pending_trade["expires_at"] - time.time())
            if trade_time_left <= 0:
                room.game.log.append(f"⏱️ 交易超时！")
                room.game.pending_trade = None
                trade_time_left = 0
                if room.game.moves_left <= 0: room.game.end_turn()
        if my_name:
            for idx, p in enumerate(room.game.players):
                if p["name"] == my_name:
                    my_player_obj = p; my_p_idx = idx; break

    return render_template('index.html', room=room, g=room.game, my_name=my_name,
                           my_player=my_player_obj, my_p_idx=my_p_idx, error=error_msg,
                           trade_time_left=trade_time_left, chat_messages=room.chat_messages[-10:])

@app.route('/create_room', methods=['POST'])
def create_room():
    room.status = "WAITING"; room.joined_players = []; room.game = None
    return redirect(url_for('index'))

@app.route('/join_room', methods=['POST'])
def join_room():
    if room.status != "WAITING": return redirect(url_for('index', error="房间当前不在等人状态，无法加入！"))
    player_name = request.form.get('player_name', '').strip()
    if not player_name: return redirect(url_for('index', error="名字不能为空！"))
    if player_name in room.joined_players: return redirect(url_for('index', error="该名字已经被别人使用了！"))
    if len(room.joined_players) >= 7: return redirect(url_for('index', error="房间已满！"))
    room.joined_players.append(player_name)
    session['my_name'] = player_name
    return redirect(url_for('index'))

@app.route('/add_bot', methods=['POST'])
def add_bot():
    """在等待室添加一个机器人"""
    if room.status != "WAITING":
        return redirect(url_for('index', error="房间不在等待状态！"))
    if len(room.joined_players) >= 7:
        return redirect(url_for('index', error="房间已满，无法添加机器人！"))
    bot_name = bot_generate_name()
    room.joined_players.append(bot_name)
    return redirect(url_for('index'))

@app.route('/remove_bot', methods=['POST'])
def remove_bot():
    """移除最后一个机器人"""
    if room.status != "WAITING":
        return redirect(url_for('index'))
    bots = [p for p in room.joined_players if is_bot(p)]
    if bots:
        room.joined_players.remove(bots[-1])
    return redirect(url_for('index'))

@app.route('/start_game', methods=['POST'])
def start_game():
    if room.status == "WAITING" and len(room.joined_players) >= 3:
        room.game = OnlineGameState(room.joined_players)
        room.status = "PLAYING"
        # 如果第一个行动的是机器人，立即让它行动
        _trigger_bot_if_needed()
    else:
        return redirect(url_for('index', error="至少需要 3 名玩家才能开始游戏！"))
    return redirect(url_for('index'))

def _trigger_bot_if_needed():
    """如果当前轮到机器人，自动执行机器人回合"""
    g = room.game
    if not g or g.game_over:
        return
    current_name = g.players[g.turn_idx]["name"]
    if is_bot(current_name):
        bot_take_turn(g, g.turn_idx)
        # 可能连续多个机器人，递归处理
        if not g.game_over:
            _trigger_bot_if_needed()

@app.route('/draw')
def draw():
    g = room.game
    if g and not g.has_drawn and not g.game_over:
        if session.get('my_name') == g.current_player()['name']:
            g.draw_from_deck(g.turn_idx, 2)
            g.has_drawn = True
            g.log.append(f"📥 【{g.current_player()['name']}】 抽取了 2 张手牌。")
    return redirect(url_for('index'))

@app.route('/propose_trade', methods=['POST'])
def propose_trade():
    g = room.game
    if not g or not g.has_drawn or g.game_over or g.pending_trade: return redirect(url_for('index'))
    my_name = session.get('my_name')
    if my_name != g.current_player()['name']: return redirect(url_for('index'))
    offer_card = request.form.get('offer')
    want_card = request.form.get('want')
    target_name = request.form.get('target')
    if offer_card not in CORE_5 or want_card not in CORE_5:
        g.log.append("❌ 交易发起失败：只能交换核心食材卡！Rendang不可交易。")
        return redirect(url_for('index'))
    p = g.current_player()
    target_p = next((x for x in g.players if x["name"] == target_name), None)
    if not target_p or offer_card not in p["hand"]:
        g.log.append("❌ 交易发起失败：你手里没有这张食材，或目标对象错误。")
        return redirect(url_for('index'))
    g.pending_trade = {"from": p["name"], "to": target_name, "offer": offer_card, "want": want_card, "expires_at": time.time() + 30}
    g.spend_move(f"向 【{target_name}】 发起 30 秒限时食材交易：用 [{offer_card}] 换取 [{want_card}]")
    # 如果交易对象是机器人，立即自动响应
    if is_bot(target_name):
        target_p2 = next((x for x in g.players if x["name"] == target_name), None)
        if target_p2 and want_card in target_p2["hand"] and random.random() < 0.6:
            target_p2["hand"].remove(want_card); p["hand"].append(want_card)
            p["hand"].remove(offer_card); target_p2["hand"].append(offer_card)
            p["hand"].sort(); target_p2["hand"].sort()
            g.log.append(f"🤝 【{target_name}】(机器人) 自动接受了交易！")
        else:
            g.log.append(f"🚫 【{target_name}】(机器人) 自动拒绝了交易。")
        g.pending_trade = None
        if g.moves_left <= 0: g.end_turn()
    return redirect(url_for('index'))

@app.route('/resolve_trade/<decision>')
def resolve_trade(decision):
    g = room.game
    my_name = session.get('my_name')
    if not g or not g.pending_trade: return redirect(url_for('index'))
    t_data = g.pending_trade
    if time.time() > t_data["expires_at"]:
        g.log.append(f"⏱️ 交易超时作废。")
        g.pending_trade = None
        if g.moves_left <= 0: g.end_turn()
        return redirect(url_for('index'))
    if my_name != t_data["to"]: return redirect(url_for('index'))
    if decision == 'accept':
        p_from = next(p for p in g.players if p["name"] == t_data["from"])
        p_to = next(p for p in g.players if p["name"] == t_data["to"])
        if t_data["offer"] in p_from["hand"] and t_data["want"] in p_to["hand"]:
            p_from["hand"].remove(t_data["offer"]); p_to["hand"].append(t_data["offer"])
            p_to["hand"].remove(t_data["want"]); p_from["hand"].append(t_data["want"])
            p_from["hand"].sort(); p_to["hand"].sort()
            g.log.append(f"🤝 交易成功！【{t_data['to']}】 接受了请求，双方完成了食材互换。")
        else:
            g.log.append(f"❌ 交易破裂！【{t_data['to']}】 根本没有 [{t_data['want']}] 食材卡。")
    else:
        g.log.append(f"🚫 【{t_data['to']}】 拒绝了交易请求。")
    g.pending_trade = None
    if g.moves_left <= 0: g.end_turn()
    _trigger_bot_if_needed()
    return redirect(url_for('index'))

@app.route('/action/<action_type>')
def play_action(action_type):
    g = room.game
    if not g or not g.has_drawn or g.game_over or g.pending_trade: return redirect(url_for('index'))
    if session.get('my_name') != g.current_player()['name']: return redirect(url_for('index'))

    p = g.current_player()
    try:
        target_idx = int(request.args.get('target', 0))
        card_idx = int(request.args.get('card_idx', 0))
    except ValueError: return redirect(url_for('index'))

    target_p = g.players[target_idx] if target_idx < len(g.players) else None

    # ── 打包标配 ────────────────────────────────────────────────────
    if action_type == 'pack_standard':
        if p.get("placed_crow"):
            g.log.append("❌ 你被乌鸦骚扰，无法包Nasi Lemak！先赶走乌鸦。")
            return redirect(url_for('index'))
        rendang_in_hand = p["hand"].count("Rendang")
        missing = [i for i in CORE_5 if i not in p["hand"]]
        if rendang_in_hand >= 5 and len([c for c in p["hand"] if c in CORE_5]) == 0:
            # pure rendang pack
            for _ in range(5): p["hand"].remove("Rendang")
            if g.gold_deck:
                p["scored_cards"].append(g.gold_deck.pop()); p["flies"].append(False)
                g.spend_move(f"【{p['name']}】 用5块Rendang奇迹包了一份椰浆饭！")
        elif len(missing) <= rendang_in_hand:
            for i in CORE_5:
                if i in p["hand"]: p["hand"].remove(i)
                else: p["hand"].remove("Rendang")
            if g.gold_deck:
                p["scored_cards"].append(g.gold_deck.pop()); p["flies"].append(False)
                g.spend_move(f"【{p['name']}】 打包了一份标准椰浆饭")
        else:
            g.log.append("❌ 你凑不够5种核心食材！")

    # ── 大妈代工 ────────────────────────────────────────────────────
    elif action_type == 'pack_makcik':
        if p.get("placed_crow"):
            g.log.append("❌ 你被乌鸦骚扰，无法包Nasi Lemak！先赶走乌鸦。")
            return redirect(url_for('index'))
        if "Mak Cik" not in p["hand"]: 
            return redirect(url_for('index'))
            
        # 统计手里的基础核心食材种类
        unique_ingredients = list(set([i for i in CORE_5 if i in p["hand"]]))
        rendang_count = p["hand"].count("Rendang")
        
        # 只要【基础食材种类 + Rendang数量】≥ 3，就说明可以凑出3种不同的食材！
        if len(unique_ingredients) + rendang_count >= 3:
            p["hand"].remove("Mak Cik")
            
            # 优先扣除手里的普通核心食材（最多扣3种）
            cards_to_remove = unique_ingredients[:3]
            for card in cards_to_remove:
                p["hand"].remove(card)
                
            # 如果扣完普通食材还不够3张，用 Rendang 来补齐缺口
            needed_rendang = 3 - len(cards_to_remove)
            for _ in range(needed_rendang):
                p["hand"].remove("Rendang")
                
            if g.gold_deck:
                p["scored_cards"].append(g.gold_deck.pop())
                p["flies"].append(False)
                g.spend_move(f"🧑‍🍳 【{p['name']}】 触发大妈神技！用 Mak Cik 加食材（含{needed_rendang}张Rendang）强行速成了椰浆饭！")
        else: 
            g.log.append("❌ 食材严重不足！就算是加上手里的 Rendang 也不够3种不同食材。")

    # ── 官员 ─────────────────────────────────────────────────────────
    elif action_type == 'officer':
        if "Officer" not in p["hand"] or not target_p or p["name"] == target_p["name"]: return redirect(url_for('index'))
        p["hand"].remove("Officer"); g.discard.append("Officer")
        g.active_inspection = {"target_idx": target_idx, "target_name": target_p["name"],
                               "hand_to_view": target_p["hand"][:], "taken_cards": []}
        g.log.append(f"👮 【{p['name']}】 派官员搜查了 【{target_p['name']}】 的手牌...")

    elif action_type == 'officer_take':
        if not g.active_inspection: return redirect(url_for('index'))
        card_to_take = request.args.get('card')
        t_p = g.players[g.active_inspection["target_idx"]]
        if card_to_take in t_p["hand"]:
            t_p["hand"].remove(card_to_take); p["hand"].append(card_to_take); p["hand"].sort()
            g.active_inspection["taken_cards"].append(card_to_take)
            if len(g.active_inspection["taken_cards"]) == 2 or not t_p["hand"]:
                taken_str = ", ".join(g.active_inspection["taken_cards"])
                g.active_inspection = None
                g.spend_move(f"【{p['name']}】 官员强占了卡牌：[{taken_str}]")

    # ── 小偷 ─────────────────────────────────────────────────────────
    elif action_type == 'thief':
        if "Thief" not in p["hand"]: return redirect(url_for('index'))
        opponents = [opp for opp in g.players if opp["name"] != p["name"] and opp["hand"]]
        if len(g.players) > 4:
            g.thief_pending = True
            g.log.append(f"🥷 【{p['name']}】 正在选择偷窃目标（需选3人）...")
            return redirect(url_for('index'))
        else:
            p["hand"].remove("Thief"); g.discard.append("Thief")
            stolen_count = 0
            for opp in opponents:
                card = random.choice(opp["hand"]); opp["hand"].remove(card); p["hand"].append(card); stolen_count += 1
            p["hand"].sort()
            g.spend_move(f"🥷 【{p['name']}】 派小偷从全场共摸走了 {stolen_count} 张手牌！")

    elif action_type == 'thief_targets':
        if not g.thief_pending or "Thief" not in p["hand"]: return redirect(url_for('index'))
        raw = request.args.get('targets', '')
        try: chosen_idxs = [int(x) for x in raw.split(',') if x.strip()]
        except ValueError: return redirect(url_for('index'))
        valid_targets = []
        for idx in chosen_idxs:
            if idx < len(g.players) and g.players[idx]["name"] != p["name"] and g.players[idx]["hand"]:
                valid_targets.append(idx)
        valid_targets = list(dict.fromkeys(valid_targets))[:3]
        if len(valid_targets) == 0:
            g.log.append("❌ 没有选择有效的偷窃目标！"); g.thief_pending = False; return redirect(url_for('index'))
        p["hand"].remove("Thief"); g.discard.append("Thief")
        stolen_count = 0; target_names = []
        for idx in valid_targets:
            opp = g.players[idx]
            if opp["hand"]:
                card = random.choice(opp["hand"]); opp["hand"].remove(card); p["hand"].append(card)
                stolen_count += 1; target_names.append(opp["name"])
        p["hand"].sort(); g.thief_pending = False
        g.spend_move(f"🥷 【{p['name']}】 从 【{'、'.join(target_names)}】 各偷走了1张手牌！")

    # ── 批发商 ────────────────────────────────────────────────────────
    elif action_type == 'wholesaler':
        if "Wholesaler" not in p["hand"]: return redirect(url_for('index'))
        p["hand"].remove("Wholesaler"); g.discard.append("Wholesaler")
        peeked = g.draw_from_deck(g.turn_idx, 3)
        g.wholesaler_reveal = {"player": p["name"], "cards": peeked, "kept": peeked, "discarded": []}
        g.spend_move(f"【{p['name']}】 批发商摸了牌堆顶 3 张牌，全部留下！")

    # ── 供应商 ────────────────────────────────────────────────────────
    elif action_type == 'supplier':
        if "Supplier" not in p["hand"]: return redirect(url_for('index'))
        requested_ing = request.args.get('ingredient')
        p["hand"].remove("Supplier"); g.discard.append("Supplier")
        total_collected = 0
        for opp in g.players:
            if opp["name"] != p["name"]:
                matches = [c for c in opp["hand"] if c == requested_ing]
                for m in matches:
                    opp["hand"].remove(m); p["hand"].append(m); total_collected += 1
        p["hand"].sort()
        g.spend_move(f"【{p['name']}】 供应商征收了全场所有的 [{requested_ing}] 共 {total_collected} 张")

    # ── 苍蝇系列 ──────────────────────────────────────────────────────
    elif action_type == 'play_fly':
        if "Fly" not in p["hand"] or not target_p or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        if target_p["flies"][card_idx]: g.log.append("❌ 这包椰浆饭已经有苍蝇了！")
        else:
            p["hand"].remove("Fly"); target_p["flies"][card_idx] = True
            g.spend_move(f"🪰 【{p['name']}】 把一只苍蝇拍到了 【{target_p['name']}】 的饭上！")

    elif action_type == 'swat_fly':
        if "Fly Swatter" not in p["hand"] or not p["flies"][card_idx]: return redirect(url_for('index'))
        p["hand"].remove("Fly Swatter"); g.discard.append("Fly Swatter"); g.discard.append("Fly")
        p["flies"][card_idx] = False
        g.spend_move(f"💥 【{p['name']}】 用苍蝇拍打死自己饭上的苍蝇")

    elif action_type == 'fan_fly':
        if "Fan" not in p["hand"] or not target_p or not p["flies"][card_idx] or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        assigned_idx = target_p["flies"].index(False) if False in target_p["flies"] else -1
        if assigned_idx == -1: g.log.append(f"❌ 对方全部长满苍蝇了，扇不过去！")
        else:
            p["hand"].remove("Fan"); g.discard.append("Fan")
            p["flies"][card_idx] = False; target_p["flies"][assigned_idx] = True
            g.spend_move(f"🪭 【{p['name']}】 用扇子把苍蝇吹到了 【{target_p['name']}】 的饭上")

    # ── 乌鸦：打出到目标玩家面前 ──────────────────────────────────────
    elif action_type == 'play_crow':
        if "Crow" not in p["hand"]: return redirect(url_for('index'))
        if not target_p or target_p["name"] == p["name"]: return redirect(url_for('index'))
        if target_p.get("placed_crow") is not None:
            g.log.append("❌ 目标玩家面前已经有乌鸦了！每人最多一只。")
            return redirect(url_for('index'))
        p["hand"].remove("Crow")
        target_p["placed_crow"] = {"ingredients": []}
        g.spend_move(f"🐦‍⬛ 【{p['name']}】 把乌鸦放到了 【{target_p['name']}】 面前！【{target_p['name']}】 暂时无法包Nasi Lemak！")

    # ── 乌鸦：用食材赶走 ──────────────────────────────────────────────
    elif action_type == 'chase_crow':
        if not p.get("placed_crow"):
            g.log.append("❌ 你面前没有乌鸦！")
            return redirect(url_for('index'))
        if not target_p or target_p["name"] == p["name"]: return redirect(url_for('index'))
        if target_p.get("placed_crow") is not None:
            g.log.append("❌ 目标玩家面前已经有乌鸦了！")
            return redirect(url_for('index'))
        ingredient = request.args.get('ingredient')
        valid_ings = CORE_5 + ["Rendang"]
        if ingredient not in valid_ings or ingredient not in p["hand"]:
            g.log.append("❌ 请选择一张有效的食材牌来喂乌鸦！")
            return redirect(url_for('index'))
        p["hand"].remove(ingredient)
        old_ings = p["placed_crow"]["ingredients"] + [ingredient]
        p["placed_crow"] = None
        target_p["placed_crow"] = {"ingredients": old_ings}
        g.spend_move(f"🐦‍⬛ 【{p['name']}】 用 [{ingredient}] 喂乌鸦，把乌鸦（携带{len(old_ings)}张食材）赶到了 【{target_p['name']}】！")

    # ── Si Oyen：捕获乌鸦 ──────────────────────────────────────────────
    elif action_type == 'si_oyen':
        if "Si Oyen" not in p["hand"]:
            return redirect(url_for('index'))
        if not p.get("placed_crow"):
            g.log.append(f"❌ 【{p['name']}】空放了一只 Si Oyen！但你面前根本没有乌鸦骚扰。")
            return redirect(url_for('index'))
        p["hand"].remove("Si Oyen")
        g.discard.append("Si Oyen")
        crow_ings = p["placed_crow"]["ingredients"]
        p["placed_crow"] = None
        for ing in crow_ings:
            p["hand"].append(ing)
        p["hand"].sort()
        reward_str = f"[{', '.join(crow_ings)}]" if crow_ings else "（无食材）"
        g.spend_move(f"🐱 【{p['name']}】使用 [Si Oyen]，直接扑杀了自己面前的乌鸦！获得食材反馈：{reward_str}")

    elif action_type == 'end_turn_manual':
        g.end_turn()
    
    _trigger_bot_if_needed()
    return redirect(url_for('index'))

@app.route('/action/wholesaler_dismiss')
def wholesaler_dismiss():
    g = room.game
    if g and session.get('my_name') == g.current_player()['name']:
        g.wholesaler_reveal = None
        if g.moves_left <= 0: g.end_turn()
    return redirect(url_for('index'))

@app.route('/quick_chat', methods=['POST'])
def quick_chat():
    my_name = session.get('my_name')
    if not my_name: return ('', 204)
    msg = request.form.get('msg', '').strip()
    mode = request.form.get('mode', 'have').strip()
    
    INGREDIENT_LABELS = {
        '🥚': '鸡蛋', '🥚': '鸡蛋',
        '🥒': '黄瓜', '🥒': '黄瓜',
        '🍚': '白饭', '🍚': '白饭',
        '🌶️': 'Sambal', '🌶': 'Sambal',
        '🥜': '花生', '🥜': '花生'
    }
    
    ALLOWED_SPECIAL = ['🙋', '⏩', '🖕']
    
    # 清洗可能夹杂的不可见字符或前后空格
    matched_label = None
    for k, v in INGREDIENT_LABELS.items():
        if k in msg or msg in k:
            matched_label = v
            break
            
    is_special = any(s in msg for s in ALLOWED_SPECIAL)
    
    if not matched_label and not is_special:
        # 如果白名单未精准命中，则启动宽松兼容机制，确保任何快捷短语都能成功发送
        if "蛋" in msg or "🥚" in msg: matched_label = "鸡蛋"
        elif "瓜" in msg or "🥒" in msg: matched_label = "黄瓜"
        elif "饭" in msg or "🍚" in msg: matched_label = "白饭"
        elif "🌶" in msg or "辣" in msg or "Sambal" in msg: matched_label = "Sambal"
        elif "豆" in msg or "花生" in msg or "🥜" in msg: matched_label = "花生"
        elif "🙋" in msg or "举手" in msg: msg = '🙋'
        elif "⏩" in msg or "快" in msg: msg = '⏩'
        elif "🖕" in msg or "中指" in msg: msg = '🖕'
        else:
            # 彻底宽容处理，避免拒绝
            matched_label = msg

    if matched_label:
        log_line = f"💬 【{my_name}】：{'我要' if mode=='want' else '我有'} {msg} {matched_label}！"
    elif msg == '🙋':
        log_line = f"💬 【{my_name}】：🙋 举手！"
    elif msg == '⏩':
        log_line = f"💬 【{my_name}】：⏩ 快一点啦！"
    elif msg == '🖕':
        log_line = f"💬 【{my_name}】：🖕 送全场一个温暖的中指！"
    else:
        log_line = f"💬 【{my_name}】发出了：{msg}"

    global room
    if 'room' in globals() and room.status == "PLAYING" and room.game:
        room.game.log.append(log_line)
        
    return ('', 204)

@app.route('/reset')
def reset():
    global room
    room.status = "EMPTY"
    room.joined_players = []
    room.game = None
    room.chat_messages = []
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

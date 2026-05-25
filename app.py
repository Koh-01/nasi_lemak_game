import os
import time
from flask import Flask, render_template, request, redirect, url_for, session
import random

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nasilemak_multiplayer_secret_key_2026")

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

class GlobalRoom:
    def __init__(self):
        self.status = "EMPTY"
        self.joined_players = []
        self.game = None
        self.chat_messages = []

room = GlobalRoom()

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

@app.route('/start_game', methods=['POST'])
def start_game():
    if room.status == "WAITING" and len(room.joined_players) >= 3:
        room.game = OnlineGameState(room.joined_players)
        room.status = "PLAYING"
    else: return redirect(url_for('index', error="至少需要 3 名玩家才能开始游戏！"))
    return redirect(url_for('index'))

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
        if "Mak Cik" not in p["hand"]: return redirect(url_for('index'))
        unique_ingredients = list(set([i for i in CORE_5 if i in p["hand"]]))
        if len(unique_ingredients) >= 3:
            p["hand"].remove("Mak Cik")
            for i in unique_ingredients[:3]: p["hand"].remove(i)
            if g.gold_deck:
                p["scored_cards"].append(g.gold_deck.pop()); p["flies"].append(False)
                g.spend_move(f"【{p['name']}】 使用大妈代工速成了椰浆饭")
        else: g.log.append("❌ 基础食材不足3种不同的！")

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
        g.spend_move(f"💥 【{p['name']}】 用苍蝇拍打死了自己饭上的苍蝇")

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
        # Play Crow card from hand onto a target player
        if "Crow" not in p["hand"]: return redirect(url_for('index'))
        if not target_p or target_p["name"] == p["name"]: return redirect(url_for('index'))
        if target_p.get("placed_crow") is not None:
            g.log.append("❌ 目标玩家面前已经有乌鸦了！每人最多一只。")
            return redirect(url_for('index'))
        p["hand"].remove("Crow")
        target_p["placed_crow"] = {"ingredients": []}
        g.spend_move(f"🐦‍⬛ 【{p['name']}】 把乌鸦放到了 【{target_p['name']}】 面前！【{target_p['name']}】 暂时无法包Nasi Lemak！")

    # ── 乌鸦：用食材赶走（由被骚扰的玩家操作，把乌鸦赶给别人）──────────
    elif action_type == 'chase_crow':
        # Current player must have a placed_crow in front of them
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
        # Move crow + accumulated ingredients + new ingredient to target
        p["hand"].remove(ingredient)
        old_ings = p["placed_crow"]["ingredients"] + [ingredient]
        p["placed_crow"] = None
        target_p["placed_crow"] = {"ingredients": old_ings}
        g.spend_move(f"🐦‍⬛ 【{p['name']}】 用 [{ingredient}] 喂乌鸦，把乌鸦（携带{len(old_ings)}张食材）赶到了 【{target_p['name']}】！")

    # ── Si Oyen：捕获乌鸦，领取其携带的食材 ──────────────────────────
    elif action_type == 'si_oyen':
        if "Si Oyen" not in p["hand"]:
            return redirect(url_for('index'))
    
        # 只能抓自己面前的乌鸦
        if not p.get("placed_crow"):
            g.log.append("❌ 你面前没有乌鸦！")
            return redirect(url_for('index'))
    
        p["hand"].remove("Si Oyen")
        g.discard.append("Si Oyen")
    
        crow_ings = p["placed_crow"]["ingredients"]
        p["placed_crow"] = None
    
        for ing in crow_ings:
            p["hand"].append(ing)
    
        p["hand"].sort()
    
        reward_str = f"[{', '.join(crow_ings)}]" if crow_ings else "（无食材）"
    
        g.spend_move(
            f"🐱 【{p['name']}】 的Si Oyen赶跑了自己面前的乌鸦！获得食材：{reward_str}"
        )

    elif action_type == 'end_turn_manual':
        g.end_turn()

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
    INGREDIENT_LABELS = {'🥚':'鸡蛋','🥒':'黄瓜','🍚':'白饭','🌶️':'Sambal','🥜':'花生'}
    ALLOWED_INGREDIENTS = list(INGREDIENT_LABELS.keys())
    ALLOWED_SPECIAL = ['🙋','⏩']
    if msg not in ALLOWED_INGREDIENTS and msg not in ALLOWED_SPECIAL:
        return ('', 204)
    if msg in INGREDIENT_LABELS:
        label = INGREDIENT_LABELS[msg]
        log_line = f"💬 【{my_name}】：{'我要' if mode=='want' else '我有'} {msg} {label}！"
    elif msg == '🙋':
        log_line = f"💬 【{my_name}】：🙋 举手！"
    elif msg == '⏩':
        log_line = f"💬 【{my_name}】：⏩ 快一点啦！"
    else:
        log_line = f"💬 【{my_name}】：{msg}"
    if room.status == "PLAYING" and room.game:
        room.game.log.append(log_line)
    room.chat_messages.append({"player": my_name, "msg": msg, "mode": mode, "log_line": log_line, "ts": time.time()})
    room.chat_messages = room.chat_messages[-30:]
    return ('', 204)

@app.route('/reset')
def reset():
    room.status = "EMPTY"; room.joined_players = []; room.game = None; session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

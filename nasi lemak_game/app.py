import os
from flask import Flask, render_template, request, redirect, url_for, session
import random

app = Flask(__name__)
# 必须设置 secret_key 才能使用 session 记住玩家身份
app.secret_key = "nasilemak_multiplayer_secret_key_2026"

CORE_5 = ["Rice", "Egg", "Peanuts", "Sambal", "Cucumber"]

def create_gold_deck():
    deck = [1] * 8 + [2] * 7
    random.shuffle(deck)
    return deck

def create_main_deck():
    deck = []
    # 50 张基础食材卡（每种 10 张）
    for ing in CORE_5:
        deck.extend([ing] * 10)
        
    # 功能行动卡（修复：每次只 extend 一个列表）
    deck.extend(["Wholesaler"] * 3)
    deck.extend(["Thief"] * 3)
    deck.extend(["Supplier"] * 3)
    deck.extend(["Mak Cik"] * 3)
    deck.extend(["Officer"] * 3)
    
    # 骚扰与防守卡
    deck.extend(["Fly"] * 5)
    deck.extend(["Fly Swatter"] * 2)
    deck.extend(["Fan"] * 3)
    
    random.shuffle(deck)
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
                "flies": []
            })
        self.turn_idx = 0
        self.moves_left = 3
        self.has_drawn = False
        self.game_over = False
        self.winner = ""
        self.log = ["游戏房间已创建！每位老板分发 7 张起始手牌。"]
        self.active_inspection = None

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
                    random.shuffle(self.main_deck)
                    self.log.append("🔄 摸牌堆空了！已将弃牌堆洗牌重用。")
                else: break
            card = self.main_deck.pop()
            p["hand"].append(card)
            drawn.append(card)
        p["hand"].sort()
        return drawn

    def spend_move(self, action_description):
        self.moves_left -= 1
        self.log.append(f"🎬 消耗动作：{action_description}（剩 {self.moves_left} 次动作）")
        if self.moves_left <= 0:
            self.end_turn()

    def end_turn(self):
        for p in self.players:
            net_packs = sum(val for idx, val in enumerate(p["scored_cards"]) if not p["flies"][idx])
            if net_packs >= 5:
                self.game_over = True
                self.winner = p["name"]
                self.log.append(f"👑 【{p['name']}】 成功售出 {net_packs} 包净椰浆饭，赢得了胜利！")
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
        self.log.append(f"🟢 轮到 【{self.players[self.turn_idx]['name']}】 的回合。请先摸牌。")

game = None

@app.route('/', methods=['GET', 'POST'])
def index():
    global game
    # 如果游戏还没创建，房东可以通过表单创建游戏
    if request.method == 'POST' and not game:
        names_raw = request.form.get('player_names', '老板A, 老板B, 老板C')
        names = [n.strip() for n in names_raw.split(',') if n.strip()]
        if 3 <= len(names) <= 7:
            game = OnlineGameState(names)
        return redirect(url_for('index'))
    
    # 联机核心：检查当前浏览网页的人，是否已经认领了游戏里的某个角色
    my_name = session.get('my_name', None)
    my_player_obj = None
    my_p_idx = -1
    
    if game:
        if my_name:
            for idx, p in enumerate(game.players):
                if p["name"] == my_name:
                    my_player_obj = p
                    my_p_idx = idx
                    break
        
        # 如果玩家通过其他设备进来，但还没认领名字，且游戏里有空位，让他认领
        if not my_player_obj and 'join_name' in request.args:
            join_name = request.args.get('join_name')
            for idx, p in enumerate(game.players):
                if p["name"] == join_name:
                    session['my_name'] = join_name
                    return redirect(url_for('index'))

    return render_template('index.html', g=game, my_name=my_name, my_player=my_player_obj, my_p_idx=my_p_idx)

@app.route('/draw')
def draw():
    global game
    if game and not game.has_drawn and not game.game_over:
        # 严格校验：只有当前轮到的玩家在自己的设备上点才有效
        if session.get('my_name') == game.current_player()['name']:
            game.draw_from_deck(game.turn_idx, 2)
            game.has_drawn = True
            game.log.append(f"📥 【{game.current_player()['name']}】 抽取了 2 张手牌。")
    return redirect(url_for('index'))

@app.route('/action/<action_type>')
def play_action(action_type):
    global game
    if not game or not game.has_drawn or game.game_over: 
        return redirect(url_for('index'))
    
    # 安全校验：只有轮到你的回合，你发送的动作请求才会被服务器执行
    if session.get('my_name') != game.current_player()['name']:
        return redirect(url_for('index'))
        
    p = game.current_player()
    target_idx = int(request.args.get('target', 0))
    target_p = game.players[target_idx]
    card_idx = int(request.args.get('card_idx', 0))
    
    if action_type == 'pack_standard':
        if all(i in p["hand"] for i in CORE_5):
            for i in CORE_5: p["hand"].remove(i)
            if game.gold_deck:
                gold_card = game.gold_deck.pop()
                p["scored_cards"].append(gold_card)
                p["flies"].append(False)
                game.spend_move(f"【{p['name']}】 打包了一份标准椰浆饭")
        else: game.log.append("❌ 你凑不够5种核心食材！")

    elif action_type == 'pack_makcik':
        if "Mak Cik" not in p["hand"]: return redirect(url_for('index'))
        unique_ingredients = list(set([i for i in CORE_5 if i in p["hand"]]))
        if len(unique_ingredients) >= 3:
            p["hand"].remove("Mak Cik")
            for i in unique_ingredients[:3]: p["hand"].remove(i)
            if game.gold_deck:
                gold_card = game.gold_deck.pop()
                p["scored_cards"].append(gold_card)
                p["flies"].append(False)
                game.spend_move(f"【{p['name']}】 使用大妈代工速成了椰浆饭")
        else: game.log.append("❌ 基础食材不足3种不同的！")

    elif action_type == 'officer':
        if "Officer" not in p["hand"] or p["name"] == target_p["name"]: return redirect(url_for('index'))
        p["hand"].remove("Officer")
        game.discard.append("Officer")
        game.active_inspection = {
            "target_idx": target_idx,
            "target_name": target_p["name"],
            "hand_to_view": target_p["hand"][:],
            "taken_cards": []
        }
        game.log.append(f"👮 【{p['name']}】 使用高级官员搜查了 【{target_p['name']}】 的手牌...")

    elif action_type == 'officer_take':
        if not game.active_inspection: return redirect(url_for('index'))
        card_to_take = request.args.get('card')
        t_p = game.players[game.active_inspection["target_idx"]]
        if card_to_take in t_p["hand"]:
            t_p["hand"].remove(card_to_take)
            p["hand"].append(card_to_take)
            p["hand"].sort()
            game.active_inspection["taken_cards"].append(card_to_take)
            if len(game.active_inspection["taken_cards"]) == 2 or not t_p["hand"]:
                taken_str = ", ".join(game.active_inspection["taken_cards"])
                game.active_inspection = None
                game.spend_move(f"【{p['name']}】 官员搜查并强占了卡牌：[{taken_str}]")

    elif action_type == 'thief':
        if "Thief" not in p["hand"]: return redirect(url_for('index'))
        p["hand"].remove("Thief")
        game.discard.append("Thief")
        stolen_count = 0
        for opp in game.players:
            if opp["name"] != p["name"] and opp["hand"]:
                card = random.choice(opp["hand"])
                opp["hand"].remove(card)
                p["hand"].append(card)
                stolen_count += 1
        p["hand"].sort()
        game.spend_move(f"【{p['name']}】 派小偷摸走了所有人各 1 张手牌")

    elif action_type == 'wholesaler':
        if "Wholesaler" not in p["hand"]: return redirect(url_for('index'))
        p["hand"].remove("Wholesaler")
        game.discard.append("Wholesaler")
        peeked = game.draw_from_deck(game.turn_idx, 3)
        kept = [c for c in peeked if c in CORE_5]
        discarded = [c for c in peeked if c not in CORE_5]
        for c in discarded:
            p["hand"].remove(c)
            game.discard.append(c)
        game.spend_move(f"【{p['name']}】 批发商过滤了牌堆顶 3 张牌")

    elif action_type == 'supplier':
        if "Supplier" not in p["hand"]: return redirect(url_for('index'))
        requested_ing = request.args.get('ingredient')
        p["hand"].remove("Supplier")
        game.discard.append("Supplier")
        total_collected = 0
        for opp in game.players:
            if opp["name"] != p["name"]:
                matches = [c for c in opp["hand"] if c == requested_ing]
                for m in matches:
                    opp["hand"].remove(m)
                    p["hand"].append(m)
                    total_collected += 1
        p["hand"].sort()
        game.spend_move(f"【{p['name']}】 供应商征收了全场所有的指定食材共 {total_collected} 张")

    elif action_type == 'play_fly':
        if "Fly" not in p["hand"] or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        if target_p["flies"][card_idx]: game.log.append("❌ 这包椰浆饭已经有苍蝇了！")
        else:
            p["hand"].remove("Fly")
            target_p["flies"][card_idx] = True
            game.spend_move(f"【{p['name']}】 把一只苍蝇放到了 【{target_p['name']}】 的第 {card_idx + 1} 包椰浆饭上")

    elif action_type == 'swat_fly':
        if "Fly Swatter" not in p["hand"] or not p["flies"][card_idx]: return redirect(url_for('index'))
        p["hand"].remove("Fly Swatter")
        game.discard.append("Fly Swatter")
        game.discard.append("Fly")
        p["flies"][card_idx] = False
        game.spend_move(f"【{p['name']}】 用苍蝇拍打死了自己第 {card_idx + 1} 包饭上的苍蝇")

    elif action_type == 'fan_fly':
        if "Fan" not in p["hand"] or not p["flies"][card_idx] or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        assigned_idx = -1
        for idx, has_fly in enumerate(target_p["flies"]):
            if not has_fly:
                assigned_idx = idx
                break
        if assigned_idx == -1: game.log.append(f"❌ 对方全部长满苍蝇了，扇不过去！")
        else:
            p["hand"].remove("Fan")
            game.discard.append("Fan")
            p["flies"][card_idx] = False 
            target_p["flies"][assigned_idx] = True 
            game.spend_move(f"【{p['name']}】 用扇子把苍蝇吹到了 【{target_p['name']}】 的第 {assigned_idx + 1} 包饭上")

    elif action_type == 'end_turn_manual':
        game.end_turn()

    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    global game
    game = None
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 必须开启 host='0.0.0.0' 允许局域网内其他手机设备访问
    app.run(debug=True, host='0.0.0.0', port=5000)
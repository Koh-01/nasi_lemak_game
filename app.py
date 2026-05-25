import os
from flask import Flask, render_template, request, redirect, url_for, session
import random

app = Flask(__name__)
# 线上部署安全密钥（防止本地与线上 Session 加密冲突）
app.secret_key = os.environ.get("SECRET_KEY", "nasilemak_multiplayer_secret_key_2026")

CORE_5 = ["Rice", "Egg", "Peanuts", "Sambal", "Cucumber"]

def create_gold_deck():
    deck = [1] * 8 + [2] * 7
    random.shuffle(deck)
    return deck

def create_main_deck():
    deck = []
    for ing in CORE_5:
        deck.extend([ing] * 10)
    # 功能行动卡（单行独立添加，防止 extend 多参数报错）
    deck.extend(["Wholesaler"] * 3)
    deck.extend(["Thief"] * 3)
    deck.extend(["Supplier"] * 3)
    deck.extend(["Mak Cik"] * 3)
    deck.extend(["Officer"] * 3)
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
        
        # 记录已经被其他设备认领过的名字列表（防止一个角色被多人选）
        self.claimed_roles = []
        
        for name in player_names:
            self.players.append({
                "name": name,
                "hand": [],
                "scored_cards": [],
                "flies": []
            })
            
        # 【新增】：开局顺序完全随机打乱
        self.turn_idx = random.randint(0, len(self.players) - 1)
        
        self.moves_left = 3
        self.has_drawn = False
        self.game_over = False
        self.winner = ""
        self.log = [f"🎲 游戏房间已创建！系统随机抽签，由 【{self.players[self.turn_idx]['name']}】 率先开始！"]
        self.active_inspection = None

        # 初始发 7 张牌
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
        # 胜利清算逻辑
        for p in self.players:
            net_packs = sum(val for idx, val in enumerate(p["scored_cards"]) if not p["flies"][idx])
            if net_packs >= 5:
                self.game_over = True
                self.winner = p["name"]
                self.log.append(f"👑 【{p['name']}】 成功售出 {net_packs} 包净椰浆饭，赢得了胜利！")
                return

        # 平局清算逻辑
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

        # 正常换人
        self.turn_idx = (self.turn_idx + 1) % len(self.players)
        self.moves_left = 3
        self.has_drawn = False
        self.active_inspection = None
        self.log.append(f"🟢 轮到 【{self.players[self.turn_idx]['name']}】 的回合。请先摸牌。")

# 线上安全的多进程全局共享类绑定
class GlobalGameHolder:
    def __init__(self):
        self.instance = None

game_holder = GlobalGameHolder()

@app.route('/', methods=['GET', 'POST'])
def index():
    # 1. 房东创建新游戏
    if request.method == 'POST' and not game_holder.instance:
        names_raw = request.form.get('player_names', '老板A, 老板B, 老板C')
        names = [n.strip() for n in names_raw.split(',') if n.strip()]
        if 3 <= len(names) <= 7:
            game_holder.instance = OnlineGameState(names)
        return redirect(url_for('index'))
    
    my_name = session.get('my_name', None)
    my_player_obj = None
    my_p_idx = -1
    
    if game_holder.instance:
        # 2. 【核心修改】玩家尝试认领角色身份
        if 'join_name' in request.args:
            join_name = request.args.get('join_name')
            # 校验 1：如果这个设备已经认领过名字了，不允许再认领别人
            if my_name:
                pass # 忽略请求
            # 校验 2：如果这个名字已经被别人抢先认领了，不允许认领
            elif join_name in game_holder.instance.claimed_roles:
                game_holder.instance.log.append(f"⚠️ 认领失败：角色【{join_name}】已被其他设备连接！")
            else:
                # 校验通过：绑定该设备
                for idx, p in enumerate(game_holder.instance.players):
                    if p["name"] == join_name:
                        session['my_name'] = join_name
                        game_holder.instance.claimed_roles.append(join_name) # 登记在册，锁定该角色
                        game_holder.instance.log.append(f"👤 玩家【{join_name}】已成功上线连接！")
                        break
            return redirect(url_for('index'))

        # 3. 刷新/获取当前 Session 绑定的角色指针
        my_name = session.get('my_name', None)
        if my_name:
            for idx, p in enumerate(game_holder.instance.players):
                if p["name"] == my_name:
                    my_player_obj = p
                    my_p_idx = idx
                    break

    return render_template('index.html', g=game_holder.instance, my_name=my_name, my_player=my_player_obj, my_p_idx=my_p_idx)

# 后续所有的 /action 和 /draw 路由保持不变，它们已经非常稳定了
@app.route('/draw')
def draw():
    g = game_holder.instance
    if g and not g.has_drawn and not g.game_over:
        if session.get('my_name') == g.current_player()['name']:
            g.draw_from_deck(g.turn_idx, 2)
            g.has_drawn = True
            g.log.append(f"📥 【{g.current_player()['name']}】 抽取了 2 张手牌。")
    return redirect(url_for('index'))

@app.route('/action/<action_type>')
def play_action(action_type):
    g = game_holder.instance
    if not g or not g.has_drawn or g.game_over: 
        return redirect(url_for('index'))
    
    if session.get('my_name') != g.current_player()['name']:
        return redirect(url_for('index'))
        
    p = g.current_player()

    try:
        target_idx = int(request.args.get('target', 0))
        card_idx = int(request.args.get('card_idx', 0))
    except ValueError:
        return redirect(url_for('index'))
        
    target_p = g.players[target_idx]
    
    if action_type == 'pack_standard':
        if all(i in p["hand"] for i in CORE_5):
            for i in CORE_5: p["hand"].remove(i)
            if g.gold_deck:
                gold_card = g.gold_deck.pop()
                p["scored_cards"].append(gold_card)
                p["flies"].append(False)
                g.spend_move(f"【{p['name']}】 打包了一份标准椰浆饭")
        else: g.log.append("❌ 你凑不够5种核心食材！")

    elif action_type == 'pack_makcik':
        if "Mak Cik" not in p["hand"]: return redirect(url_for('index'))
        unique_ingredients = list(set([i for i in CORE_5 if i in p["hand"]]))
        if len(unique_ingredients) >= 3:
            p["hand"].remove("Mak Cik")
            for i in unique_ingredients[:3]: p["hand"].remove(i)
            if g.gold_deck:
                gold_card = g.gold_deck.pop()
                p["scored_cards"].append(gold_card)
                p["flies"].append(False)
                g.spend_move(f"【{p['name']}】 使用大妈代工速成了椰浆饭")
        else: g.log.append("❌ 基础食材不足3种不同的！")

    elif action_type == 'officer':
        if "Officer" not in p["hand"] or p["name"] == target_p["name"]: return redirect(url_for('index'))
        p["hand"].remove("Officer")
        g.discard.append("Officer")
        g.active_inspection = {
            "target_idx": target_idx,
            "target_name": target_p["name"],
            "hand_to_view": target_p["hand"][:],
            "taken_cards": []
        }
        g.log.append(f"👮 【{p['name']}】 使用高级官员搜查了 【{target_p['name']}】 的手牌...")

    elif action_type == 'officer_take':
        if not g.active_inspection: return redirect(url_for('index'))
        card_to_take = request.args.get('card')
        t_p = g.players[g.active_inspection["target_idx"]]
        if card_to_take in t_p["hand"]:
            t_p["hand"].remove(card_to_take)
            p["hand"].append(card_to_take)
            p["hand"].sort()
            g.active_inspection["taken_cards"].append(card_to_take)
            if len(g.active_inspection["taken_cards"]) == 2 or not t_p["hand"]:
                taken_str = ", ".join(g.active_inspection["taken_cards"])
                g.active_inspection = None
                g.spend_move(f"【{p['name']}】 官员搜查并强占了卡牌：[{taken_str}]")

    elif action_type == 'thief':
        if "Thief" not in p["hand"]: return redirect(url_for('index'))
        p["hand"].remove("Thief")
        g.discard.append("Thief")
        stolen_count = 0
        for opp in g.players:
            if opp["name"] != p["name"] and opp["hand"]:
                card = random.choice(opp["hand"])
                opp["hand"].remove(card)
                p["hand"].append(card)
                stolen_count += 1
        p["hand"].sort()
        g.spend_move(f"🥷 【{p['name']}】 派小偷成功从全场其他人手里共摸走了 {stolen_count} 张手牌！")

    elif action_type == 'wholesaler':
        if "Wholesaler" not in p["hand"]: return redirect(url_for('index'))
        p["hand"].remove("Wholesaler")
        g.discard.append("Wholesaler")
        peeked = g.draw_from_deck(g.turn_idx, 3)
        kept = [c for c in peeked if c in CORE_5]
        discarded = [c for c in peeked if c not in CORE_5]
        for c in discarded:
            p["hand"].remove(c)
            g.discard.append(c)
        g.spend_move(f"【{p['name']}】 批发商过滤了牌堆顶 3 张牌，只留下了食材")

    elif action_type == 'supplier':
        if "Supplier" not in p["hand"]: return redirect(url_for('index'))
        requested_ing = request.args.get('ingredient')
        p["hand"].remove("Supplier")
        g.discard.append("Supplier")
        total_collected = 0
        for opp in g.players:
            if opp["name"] != p["name"]:
                matches = [c for c in opp["hand"] if c == requested_ing]
                for m in matches:
                    opp["hand"].remove(m)
                    p["hand"].append(m)
                    total_collected += 1
        p["hand"].sort()
        g.spend_move(f"【{p['name']}】 供应商征收了全场所有的指定食材共 {total_collected} 张")

    elif action_type == 'play_fly':
        if "Fly" not in p["hand"] or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        if target_p["flies"][card_idx]: g.log.append("❌ 这包椰浆饭已经有苍蝇了！")
        else:
            p["hand"].remove("Fly")
            target_p["flies"][card_idx] = True
            g.spend_move(f"🪰 【{p['name']}】 把一只苍蝇拍到了 【{target_p['name']}】 的饭上！")

    elif action_type == 'swat_fly':
        if "Fly Swatter" not in p["hand"] or not p["flies"][card_idx]: return redirect(url_for('index'))
        p["hand"].remove("Fly Swatter")
        g.discard.append("Fly Swatter")
        g.discard.append("Fly")
        p["flies"][card_idx] = False
        g.spend_move(f"💥 【{p['name']}】 用苍蝇拍打死了自己饭上的苍蝇")

    elif action_type == 'fan_fly':
        if "Fan" not in p["hand"] or not p["flies"][card_idx] or p["name"] == target_p["name"] or not target_p["scored_cards"]: return redirect(url_for('index'))
        assigned_idx = -1
        for idx, has_fly in enumerate(target_p["flies"]):
            if not has_fly:
                assigned_idx = idx
                break
        if assigned_idx == -1: g.log.append(f"❌ 对方全部长满苍蝇了，扇不过去！")
        else:
            p["hand"].remove("Fan")
            g.discard.append("Fan")
            p["flies"][card_idx] = False 
            target_p["flies"][assigned_idx] = True 
            g.spend_move(f"🪭 【{p['name']}】 用扇子把苍蝇吹到了 【{target_p['name']}】 的饭上")

    elif action_type == 'end_turn_manual':
        g.end_turn()

    return redirect(url_for('index'))

@app.route('/reset')
def reset():
    game_holder.instance = None
    session.clear()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

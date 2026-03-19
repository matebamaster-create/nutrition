import streamlit as st
import pandas as pd
import re
import os
import json
import google.generativeai as genai

# ==========================================
# ページ全体のデザイン設定
# ==========================================
st.set_page_config(
    page_title="献立自動チェックシステム",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 食事別のカスタムカラーボックスを定義
st.markdown("""
    <style>
    .main { background-color: #FAFAFA; }
    h1, h2, h3 { color: #2C3E50; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; border-radius: 5px 5px 0 0; }
    .day-container { padding: 10px 0px; }
    
    /* 食事別カラーボックスのベーススタイル */
    .meal-box {
        padding: 8px 12px;
        margin-bottom: 8px;
        border-radius: 4px;
        border-left: 5px solid;
        font-size: 0.9em;
        line-height: 1.4;
        height: 100%; /* 高さを揃えるための工夫 */
    }
    /* 朝食：オレンジ系 */
    .meal-bf { background-color: #FFF3E0; border-left-color: #FF9800; color: #E65100; }
    /* 昼食：グリーン系 */
    .meal-ld { background-color: #E8F5E9; border-left-color: #4CAF50; color: #2E7D32; }
    /* 夕食：ブルー系 */
    .meal-dn { background-color: #E3F2FD; border-left-color: #2196F3; color: #1565C0; }
    /* 全体・1日ルール：レッド系 */
    .meal-all { background-color: #FFEBEE; border-left-color: #F44336; color: #C62828; }
    </style>
    """, unsafe_allow_html=True)

RULE_FILE = "ai_rules.txt"
MODEL_FILE = "ai_model.txt" 

DEFAULT_RULES = """【朝食について】
・漬物やジャムなど味が偏っていないか（納豆の日は漬物を提供するなど）
・パンの時のおかずはパンに合うか。食パンの時のスープは牛乳か豆乳が入った味になっているか。
【昼・夕食について】
・日曜日の冷小鉢は「サラダ類」と「生の果物またはデザート」の組み合わせになっているか。
・メインと付け合わせの味付けが合っているか（和風メインに中華の付け合わせはNG）。
・魚や肉に偏りはないか、週全体でマヨネーズ味ばかりなど味付けが偏っていないか。
【外来食（月・水・金の夕食）への配慮】
・ボリュームのある主菜か（おでん、豆腐メインはNG。サイコロステーキやハンバーグ等はOK）。
・片手で食べにくい汁あり麺や温泉たまごはNG。
・おかずにならないパン料理やプリン等のデザート、果物入りサラダはNG。
【全体（食材・調理の重複）】
・いも類が同じ時間に2つ、または毎食提供されていないか。
・にんじんや青物などが同じ時間に全品に入っていないか（主菜ほうれん草、副菜小松菜はNG）。
・夕食の副菜と、翌日朝食の副菜が（食材含め）一緒ではないか。
・夕食の主菜と、翌日昼食の主菜の食材が一緒ではないか。
・箸だけで食べにくい食材（豆、豆腐、ひじき等）が含まれる場合はスプーンをつける配慮がメニュー名から読み取れるか。"""

DEFAULT_MODEL = "gemini-3.1-pro-preview" 

# ==========================================
# 便利関数の定義
# ==========================================
def extract_number(text):
    if pd.isna(text) or not str(text).strip(): return 0.0
    match = re.search(r'([0-9]+\.?[0-9]*)', str(text))
    return float(match.group(1)) if match else 0.0

def get_cell(df, r, c):
    if r < len(df) and c < len(df.columns):
        val = df.iloc[r, c]
        return "" if pd.isna(val) else str(val).strip()
    return ""

def load_ai_rules():
    if os.path.exists(RULE_FILE):
        with open(RULE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    return DEFAULT_RULES

def save_ai_rules(rules_text):
    with open(RULE_FILE, "w", encoding="utf-8") as f:
        f.write(rules_text)

def load_ai_model():
    if os.path.exists(MODEL_FILE):
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    return DEFAULT_MODEL

def save_ai_model(model_name):
    with open(MODEL_FILE, "w", encoding="utf-8") as f:
        f.write(model_name.strip())

# ==========================================
# サイドバー（設定画面）
# ==========================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3448/3448066.png", width=80)
    st.title("⚙️ システム設定")
    
    st.markdown("### 🔑 AI連携設定")
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🟢 AIシステム接続済み")
    except Exception:
        api_key = None
        st.error("⚠️ APIキーが設定されていません")
    
    st.markdown("---")
    st.markdown("### 📏 基準値の微調整")
    max_salt_daily = st.number_input("1日の塩分上限 (g)", value=6.3, step=0.1)
    max_potassium = st.number_input("昼・夕食のカリウム上限 (mg)", value=850, step=10)
    kawari_target = st.number_input("変わり御飯の週目標 (回)", value=3, step=1)
    st.success("設定は即座に反映されます👍")

# ==========================================
# メイン画面
# ==========================================
st.title("🍽️ 透析食A 献立自動チェックシステム")
st.markdown("「透析食Aの決まりごと」に基づき、カロリー・塩分の主食別変動チェック、NG曜日のキーワード判定、AI定性チェックを全自動で行います。")

tab_main, tab_rules = st.tabs(["🔍 献立チェック実行", "📝 マスター管理 (ルール・AIモデル)"])

with tab_rules:
    st.subheader("🤖 AIモデルの管理")
    st.info("使用するAIモデルのID（例：gemini-3.1-pro-preview）を指定します。新しいモデルが出た際はこちらを書き換えて保存してください。")
    current_model = load_ai_model()
    edited_model = st.text_input("▼ 現在のAIモデル", value=current_model)
    if st.button("💾 AIモデル名を保存する", type="primary", key="btn_save_model"):
        save_ai_model(edited_model)
        st.success(f"使用するAIモデルを「{edited_model}」に更新しました！")
    
    st.markdown("---")
    
    st.subheader("💡 AIにチェックさせる「定性的ルール」の管理")
    current_rules = load_ai_rules()
    edited_rules = st.text_area("▼ 現在の登録ルール", value=current_rules, height=400)
    if st.button("💾 このルールをマスターに保存する", type="primary", key="btn_save_rules"):
        save_ai_rules(edited_rules)
        st.success("新しい定性ルールを保存しました！")

with tab_main:
    uploaded_file = st.file_uploader("📂 献立ファイルのアップロード（.xls または .xlsx）", type=['xls', 'xlsx'])

    if uploaded_file is not None:
        if not api_key:
            st.warning("👈 左のサイドバーでAIシステムが接続されているか確認してください。")
        else:
            if st.button("✨ AI自動チェックを開始する", type="primary", use_container_width=True):
                genai.configure(api_key=api_key)
                
                with st.spinner('高度なルール解析とAIレビューを実行中です...（約1分かかります）'):
                    try:
                        target_model = load_ai_model()
                        model = genai.GenerativeModel(target_model)

                        df = pd.read_excel(uploaded_file, header=None)
                        daily_data = []
                        
                        for i in range(len(df)):
                            date_col_base = -1
                            for c in range(3, 8):
                                val = get_cell(df, i, c)
                                if "月" in val and "日" in val and "(" in val:
                                    date_col_base = c
                                    break
                            
                            if date_col_base != -1:
                                date_row_idx = i
                                for day_idx in range(7):
                                    col_idx = date_col_base + (day_idx * 16)
                                    date_str = get_cell(df, date_row_idx, col_idx)
                                    if not date_str: continue
                                        
                                    day_data = {
                                        "date": date_str,
                                        "meals": {"breakfast": {"menu": [], "nutrients": {}}, "lunch": {"menu": [], "nutrients": {}}, "dinner": {"menu": [], "nutrients": {}}},
                                        "daily_total_nutrients": {}
                                    }
                                    
                                    states = ['breakfast', 'lunch', 'dinner', 'daily_total']
                                    state_idx = 0
                                    r = date_row_idx + 1
                                    
                                    while r < min(len(df), date_row_idx + 60) and state_idx < len(states):
                                        current_state = states[state_idx]
                                        cell = get_cell(df, r, col_idx)
                                        
                                        if "ｴﾈﾙｷﾞｰ" in cell or "kcal" in cell.lower():
                                            n_data = {
                                                "energy_kcal": extract_number(get_cell(df, r, col_idx)),
                                                "protein_g": extract_number(get_cell(df, r, col_idx + 8)),
                                                "potassium_mg": extract_number(get_cell(df, r+2, col_idx + 8)),
                                                "salt_equivalent_g": extract_number(get_cell(df, r+3, col_idx + 8))
                                            }
                                            if current_state == 'daily_total': day_data["daily_total_nutrients"] = n_data
                                            else: day_data["meals"][current_state]["nutrients"] = n_data
                                            state_idx += 1
                                            r += 4 
                                            continue
                                            
                                        if cell and current_state != 'daily_total':
                                            day_data["meals"][current_state]["menu"].append(cell)
                                        r += 1
                                    daily_data.append(day_data)

                        weeks = []
                        current_week = []
                        for day in daily_data:
                            current_week.append(day)
                            if "(日)" in day.get("date", ""):
                                weeks.append(current_week)
                                current_week = []
                        if current_week: weeks.append(current_week)

                        week_results = []
                        active_rules = load_ai_rules()
                        
                        # --- 全体サマリー用の集計カウンター ---
                        count_salt_daily = 0
                        count_cal_daily = 0
                        count_nut_meal = 0
                        count_ng = 0

                        for week_idx, week in enumerate(weeks):
                            week_alerts = []
                            kawari_count = 0
                            curry_count = 0
                            day_details = []
                            
                            prompt = f"あなたは病院のプロの管理栄養士です。以下の献立を読み込み、修正が必要なポイントをリストアップしてください。\n\n"
                            prompt += f"【チェックしてほしい定性的ルール】\n{active_rules}\n\n"
                            prompt += "【出力フォーマット】\n出力は必ず以下のJSON配列形式のみで返してください。Markdown記号(```json)は不要です。問題がない日は配列に含めないでください。\n"
                            prompt += '[\n  {"date": "〇月〇日(曜)", "meal": "〇食", "comment": "〇〇のため変更を検討"}\n]\n\n'
                            
                            for day in week:
                                date = day.get('date')
                                total_nut = day.get("daily_total_nutrients", {})
                                day_alerts = []
                                formatted_menus = []
                                
                                is_monday = "(月)" in date
                                is_sunday = "(日)" in date
                                
                                # 1日ルールチェック（全体）
                                salt = total_nut.get("salt_equivalent_g", 0)
                                if salt >= max_salt_daily:
                                    day_alerts.append({"type": "all", "text": f"🚨 <b>1日塩分</b> 超過 ({salt}g / {max_salt_daily}g未満)"})
                                    count_salt_daily += 1 # 集計加算
                                    
                                cal_total = total_nut.get("energy_kcal", 0)
                                if cal_total > 0 and (cal_total < 1700 or cal_total > 1800):
                                    day_alerts.append({"type": "all", "text": f"⚠️ <b>1日カロリー</b> 基準外 ({cal_total}kcal / 1700-1800)"})
                                    count_cal_daily += 1 # 集計加算

                                prompt += f"■ {date}\n"
                                
                                for meal_type, meal_name in [("breakfast", "朝食"), ("lunch", "昼食"), ("dinner", "夕食")]:
                                    meal_data = day.get("meals", {}).get(meal_type, {})
                                    menu = meal_data.get("menu", [])
                                    nut = meal_data.get("nutrients", {})
                                    
                                    pro = nut.get("protein_g", 0)
                                    pot = nut.get("potassium_mg", 0)
                                    cal = nut.get("energy_kcal", 0)
                                    meal_salt = nut.get("salt_equivalent_g", 0)
                                    
                                    if menu:
                                        menu_str = "".join(menu)
                                        is_bread = any(k in menu_str for k in ['パン', 'サンドイッチ', 'ホットドッグ', 'バーガー'])
                                        is_noodle = any(k in menu_str for k in ['うどん', 'そば', 'ラーメン', 'パスタ', 'スパゲティ', 'そうめん', 'ちゃんぽん', '麺'])
                                        is_curry = 'カレー' in menu_str
                                        is_aji_gohan = any(k in menu_str for k in ['ピラフ', '炒飯', 'チャーハン', 'かしわ飯', '炊き込み', '丼', '寿司', 'オムライス', 'ビーフシチュー'])
                                        is_natto = '納豆' in menu_str
                                        
                                        # NG判定
                                        if is_natto and (is_sunday or is_monday):
                                            day_alerts.append({"type": meal_type, "text": f"❌ <b>[{meal_name}]</b> 日・月の納豆提供はNG"})
                                            count_ng += 1
                                        if is_bread and meal_type == "dinner":
                                            day_alerts.append({"type": meal_type, "text": f"❌ <b>[{meal_name}]</b> 夕食のパン提供はNG"})
                                            count_ng += 1
                                        if is_bread and is_monday:
                                            day_alerts.append({"type": meal_type, "text": f"❌ <b>[{meal_name}]</b> 月曜のパン提供はNG"})
                                            count_ng += 1
                                        if is_noodle and meal_type == "dinner":
                                            day_alerts.append({"type": meal_type, "text": f"❌ <b>[{meal_name}]</b> 夕食の麺類(汁あり)はNG"})
                                            count_ng += 1
                                            
                                        if is_curry: curry_count += 1
                                        if meal_type in ["lunch", "dinner"] and (is_bread or is_noodle or is_aji_gohan or (menu and menu[0] != "御飯" and menu[0] != "全粥")):
                                            kawari_count += 1
                                            
                                        # 塩分・カロリー判定
                                        if meal_type == "breakfast":
                                            cal_limit = 550 if is_bread else 500
                                            if cal > 0 and (cal < 400 or cal > cal_limit):
                                                day_alerts.append({"type": meal_type, "text": f"⚠️ <b>[{meal_name}] カロリー</b> ({cal}kcal)"})
                                                count_nut_meal += 1
                                            if pro > 0 and (pro < 10 or pro > 15):
                                                day_alerts.append({"type": meal_type, "text": f"⚠️ <b>[{meal_name}] たんぱく</b> ({pro}g)"})
                                                count_nut_meal += 1
                                            salt_limit = 2.3 if is_bread else 2.0
                                            if meal_salt > salt_limit:
                                                day_alerts.append({"type": meal_type, "text": f"🚨 <b>[{meal_name}] 塩分</b> ({meal_salt}g)"})
                                                count_nut_meal += 1
                                        else:
                                            if cal > 0 and (cal < 550 or cal > 750):
                                                day_alerts.append({"type": meal_type, "text": f"⚠️ <b>[{meal_name}] カロリー</b> ({cal}kcal)"})
                                                count_nut_meal += 1
                                            if pro > 0 and (pro < 23 or pro > 27):
                                                day_alerts.append({"type": meal_type, "text": f"⚠️ <b>[{meal_name}] たんぱく</b> ({pro}g)"})
                                                count_nut_meal += 1
                                            if pot > max_potassium:
                                                day_alerts.append({"type": meal_type, "text": f"⚠️ <b>[{meal_name}] カリウム</b> ({pot}mg)"})
                                                count_nut_meal += 1
                                                
                                            if is_bread or is_noodle or is_curry or '炒飯' in menu_str or '高菜ピラフ' in menu_str: salt_limit = 2.8
                                            elif is_aji_gohan: salt_limit = 2.5
                                            else: salt_limit = 2.0
                                                
                                            if meal_salt > salt_limit:
                                                day_alerts.append({"type": meal_type, "text": f"🚨 <b>[{meal_name}] 塩分</b> ({meal_salt}g)"})
                                                count_nut_meal += 1
                                                
                                        clean_menu = [m for m in menu if ":" not in m and "kcal" not in m]
                                        formatted_menus.append({"type": meal_type, "text": f"<b>[{meal_name}]</b> {', '.join(clean_menu)}"})
                                        prompt += f"[{meal_name}] {', '.join(clean_menu)}\n"
                                        
                                day_details.append({
                                    "date": date,
                                    "menus": formatted_menus,
                                    "alerts": day_alerts,
                                    "ai_comments": [] 
                                })
                                
                            if kawari_count > kawari_target + 1 or kawari_count < kawari_target - 1:
                                week_alerts.append(f"📌 **変わり御飯**：今週{kawari_count}回 (目標{kawari_target}回前後)")
                                count_ng += 1
                            if curry_count == 0:
                                week_alerts.append(f"❌ **カレーライス**：今週の提供がありません (週1回必須)")
                                count_ng += 1

                            # AIへ送信し、JSONとしてパース
                            response = model.generate_content(prompt)
                            ai_raw_text = response.text
                            
                            try:
                                clean_text = re.sub(r'```json\n?', '', ai_raw_text)
                                clean_text = re.sub(r'```\n?', '', clean_text)
                                parsed_json = json.loads(clean_text.strip())
                                parse_success = True
                                
                                for item in parsed_json:
                                    d = item.get("date", "")
                                    ai_meal = item.get("meal", "")
                                    if "朝" in ai_meal: m_type = "breakfast"
                                    elif "昼" in ai_meal: m_type = "lunch"
                                    elif "夕" in ai_meal or "夜" in ai_meal: m_type = "dinner"
                                    else: m_type = "all"
                                    
                                    for day_d in day_details:
                                        if day_d["date"] == d:
                                            day_d["ai_comments"].append({"type": m_type, "text": f"<b>[{ai_meal}]</b> {item.get('comment', '')}"})
                            except:
                                parse_success = False

                            week_results.append({
                                "week_alerts": week_alerts,
                                "days": day_details,
                                "parse_success": parse_success,
                                "raw_text": ai_raw_text
                            })

                        # --- 3. 画面への結果表示 ---
                        st.success(f"✅ 全ての解析が完了しました！（使用AIモデル: {target_model}）")
                        
                        tab_names = ["📊 全体サマリー"] + [f"📅 第{i+1}週" for i in range(len(weeks))]
                        result_tabs = st.tabs(tab_names)
                        
                        # --- 全体サマリー画面の描画（追加箇所） ---
                        with result_tabs[0]:
                            st.subheader("📊 献立チェック総括")
                            
                            col1, col2, col3, col4 = st.columns(4)
                            col1.metric("1日塩分 超過", f"{count_salt_daily} 日")
                            col2.metric("1日カロリー 基準外", f"{count_cal_daily} 日")
                            col3.metric("1食あたりの数値エラー", f"{count_nut_meal} 件")
                            col4.metric("提供ルール・週間アラート", f"{count_ng} 件")
                            
                            total_sys_errors = count_salt_daily + count_cal_daily + count_nut_meal + count_ng
                            if total_sys_errors == 0:
                                st.success("✨ 素晴らしいです！システムが検知した定量エラーはありませんでした。")
                            else:
                                st.warning(f"⚠️ 合計 {total_sys_errors} 件のシステムアラートが発生しています。各週のタブから詳細を確認してください。")
                                
                            st.info("💡 各週のタブをクリックして、日別の詳細なエラーとメニューを一覧で確認できます。")
                        
                        for i, tab in enumerate(result_tabs[1:]):
                            with tab:
                                if week_results[i]["week_alerts"]:
                                    for wa in week_results[i]["week_alerts"]:
                                        if "❌" in wa: st.error(wa)
                                        else: st.info(wa)
                                        
                                if not week_results[i]["parse_success"]:
                                    st.warning("⚠️ AIの回答形式が一部崩れました。念のため生の指摘データも表示します。")
                                    with st.expander("AIからの生データを見る"):
                                        st.write(week_results[i]["raw_text"])

                                # 日ごとにレンダリング
                                for day_data in week_results[i]["days"]:
                                    st.markdown(f"<div class='day-container'>", unsafe_allow_html=True)
                                    st.markdown(f"#### 🗓️ {day_data['date']}")
                                    
                                    # 1日全体の指摘（赤色）を一番上に配置
                                    all_alerts = [a for a in day_data["alerts"] if a["type"] == "all"]
                                    all_ai = [c for c in day_data["ai_comments"] if c["type"] == "all"]
                                    if all_alerts or all_ai:
                                        st.markdown("<b style='color:#C62828;'>【1日全体・その他の指摘】</b>", unsafe_allow_html=True)
                                        for a in all_alerts:
                                            st.markdown(f"<div class='meal-box meal-all'>{a['text']}</div>", unsafe_allow_html=True)
                                        for c in all_ai:
                                            st.markdown(f"<div class='meal-box meal-all'>{c['text']}</div>", unsafe_allow_html=True)

                                    # ヘッダー
                                    col_m, col_q, col_ai = st.columns([2, 1.5, 2])
                                    col_m.caption("🍽️ 提供予定メニュー")
                                    col_q.caption("📊 システム判定 (ルール・数値)")
                                    col_ai.caption("🤖 AI定性チェック (文脈・バランス)")

                                    # 食事ごと（朝・昼・夕）に行を作ってレンダリング
                                    meal_types = [("breakfast", "meal-bf"), ("lunch", "meal-ld"), ("dinner", "meal-dn")]
                                    for m_type, css_class in meal_types:
                                        col1, col2, col3 = st.columns([2, 1.5, 2])
                                        
                                        # メニュー
                                        menus = [m for m in day_data["menus"] if m["type"] == m_type]
                                        with col1:
                                            for m in menus:
                                                st.markdown(f"<div class='meal-box {css_class}'>{m['text']}</div>", unsafe_allow_html=True)
                                                
                                        # システムエラー
                                        alerts = [a for a in day_data["alerts"] if a["type"] == m_type]
                                        with col2:
                                            if alerts:
                                                for a in alerts:
                                                    st.markdown(f"<div class='meal-box {css_class}'>{a['text']}</div>", unsafe_allow_html=True)
                                            elif menus: # メニューが存在する時だけ「問題なし」を表示
                                                st.markdown(f"<div class='meal-box {css_class}' style='opacity: 0.6;'>✅ 問題なし</div>", unsafe_allow_html=True)
                                                
                                        # AI指摘
                                        ai_comments = [c for c in day_data["ai_comments"] if c["type"] == m_type]
                                        with col3:
                                            if ai_comments:
                                                for c in ai_comments:
                                                    st.markdown(f"<div class='meal-box {css_class}'>{c['text']}</div>", unsafe_allow_html=True)
                                            elif menus:
                                                st.markdown(f"<div class='meal-box {css_class}' style='opacity: 0.6;'>✨ 指摘なし</div>", unsafe_allow_html=True)
                                                
                                    st.divider()
                                    st.markdown(f"</div>", unsafe_allow_html=True)

                    except Exception as e:
                        st.error(f"❌ 処理中にエラーが発生しました: {e}")

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

st.markdown("""
    <style>
    .main { background-color: #FAFAFA; }
    h1, h2, h3 { color: #2C3E50; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; border-radius: 5px 5px 0 0; }
    .day-container { padding: 10px 0px; }
    .menu-text { font-size: 0.9em; color: #555; }
    </style>
    """, unsafe_allow_html=True)

RULE_FILE = "ai_rules.txt"

# 透析食Aの決まりごとを網羅した定性ルール（初期値）
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
    st.caption("※透析食Aの基本ルールは内部プログラムに組み込み済みです。ここではイレギュラーな変更のみ行えます。")
    max_salt_daily = st.number_input("1日の塩分上限 (g)", value=6.3, step=0.1)
    max_potassium = st.number_input("昼・夕食のカリウム上限 (mg)", value=850, step=10)
    kawari_target = st.number_input("変わり御飯の週目標 (回)", value=3, step=1)
    
    st.success("設定は即座に反映されます👍")

# ==========================================
# メイン画面
# ==========================================
st.title("🍽️ 透析食A 献立自動チェックシステム (完全版)")
st.markdown("「透析食Aの決まりごと」に基づき、カロリー・塩分の主食別変動チェック、NG曜日のキーワード判定、AI定性チェックを全自動で行います。")

tab_main, tab_rules = st.tabs(["🔍 献立チェック実行", "📝 定性ルールマスター管理"])

with tab_rules:
    st.subheader("💡 AIにチェックさせる「定性的ルール」の管理")
    st.info("外来食の配慮や食材の被りなど、文脈の理解が必要なルールはここに記載します。システムが自動で行う数値計算（カロリーや塩分）は書かなくて大丈夫です。")
    current_rules = load_ai_rules()
    edited_rules = st.text_area("▼ 現在の登録ルール", value=current_rules, height=400)
    if st.button("💾 このルールをマスターに保存する", type="primary"):
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
                        # AIモデルの自動選択
                        available_models = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
                        preferred_models = ['models/gemini-1.5-flash', 'models/gemini-1.5-pro', 'models/gemini-1.0-pro', 'models/gemini-pro']
                        selected_model = available_models[0] if available_models else 'models/gemini-pro'
                        for pref in preferred_models:
                            if pref in available_models:
                                selected_model = pref
                                break
                        model = genai.GenerativeModel(selected_model.replace('models/', ''))

                        # Excel読み込み処理
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

                        # 週ごとに分割
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

                        # 各週の処理
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
                                
                                # 曜日判定用
                                is_monday = "(月)" in date
                                is_sunday = "(日)" in date
                                
                                # 1日ルールチェック
                                salt = total_nut.get("salt_equivalent_g", 0)
                                if salt >= max_salt_daily:
                                    day_alerts.append(f"🚨 **1日塩分** 超過 ({salt}g / {max_salt_daily}g未満)")
                                    
                                cal_total = total_nut.get("energy_kcal", 0)
                                if cal_total > 0 and (cal_total < 1700 or cal_total > 1800):
                                    day_alerts.append(f"⚠️ **1日カロリー** 基準外 ({cal_total}kcal / 1700-1800)")

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
                                        
                                        # カテゴリ判定
                                        is_bread = any(k in menu_str for k in ['パン', 'サンドイッチ', 'ホットドッグ', 'バーガー'])
                                        is_noodle = any(k in menu_str for k in ['うどん', 'そば', 'ラーメン', 'パスタ', 'スパゲティ', 'そうめん', 'ちゃんぽん', '麺'])
                                        is_curry = 'カレー' in menu_str
                                        is_aji_gohan = any(k in menu_str for k in ['ピラフ', '炒飯', 'チャーハン', 'かしわ飯', '炊き込み', '丼', '寿司', 'オムライス', 'ビーフシチュー'])
                                        is_natto = '納豆' in menu_str
                                        
                                        # NG曜日・時間の判定
                                        if is_natto and (is_sunday or is_monday):
                                            day_alerts.append(f"❌ **{meal_name}** 日・月の納豆提供はNG")
                                        if is_bread and meal_type == "dinner":
                                            day_alerts.append(f"❌ **{meal_name}** 夕食のパン提供はNG")
                                        if is_bread and is_monday:
                                            day_alerts.append(f"❌ **{meal_name}** 月曜のパン提供はNG")
                                        if is_noodle and meal_type == "dinner":
                                            day_alerts.append(f"❌ **{meal_name}** 夕食の麺類(汁あり)はNG")
                                            
                                        # カウント系
                                        if is_curry: curry_count += 1
                                        if meal_type in ["lunch", "dinner"] and (is_bread or is_noodle or is_aji_gohan or (menu and menu[0] != "御飯" and menu[0] != "全粥")):
                                            kawari_count += 1
                                            
                                        # 塩分・カロリーの条件付き判定
                                        if meal_type == "breakfast":
                                            cal_limit = 550 if is_bread else 500
                                            if cal > 0 and (cal < 400 or cal > cal_limit):
                                                day_alerts.append(f"⚠️ **{meal_name} カロリー** ({cal}kcal / 400-{cal_limit})")
                                            if pro > 0 and (pro < 10 or pro > 15):
                                                day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g / 10-15g)")
                                            
                                            salt_limit = 2.3 if is_bread else 2.0
                                            if meal_salt > salt_limit:
                                                day_alerts.append(f"🚨 **{meal_name} 塩分** ({meal_salt}g / {salt_limit}g以下)")
                                                
                                        else:
                                            if cal > 0 and (cal < 550 or cal > 750):
                                                day_alerts.append(f"⚠️ **{meal_name} カロリー** ({cal}kcal / 550-750)")
                                            if pro > 0 and (pro < 23 or pro > 27):
                                                day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g / 23-27g)")
                                            if pot > max_potassium:
                                                day_alerts.append(f"⚠️ **{meal_name} カリウム** ({pot}mg / {max_potassium}mg以下)")
                                                
                                            if is_bread or is_noodle or is_curry or '炒飯' in menu_str or '高菜ピラフ' in menu_str:
                                                salt_limit = 2.8
                                            elif is_aji_gohan:
                                                salt_limit = 2.5
                                            else:
                                                salt_limit = 2.0
                                                
                                            if meal_salt > salt_limit:
                                                day_alerts.append(f"🚨 **{meal_name} 塩分** ({meal_salt}g / {salt_limit}g以下)")
                                                
                                        clean_menu = [m for m in menu if ":" not in m and "kcal" not in m]
                                        formatted_menus.append(f"**[{meal_name}]** {', '.join(clean_menu)}")
                                        prompt += f"[{meal_name}] {', '.join(clean_menu)}\n"
                                        
                                day_details.append({
                                    "date": date,
                                    "menus": formatted_menus,
                                    "alerts": day_alerts,
                                    "ai_comments": [] # あとでJSONパースして入れる
                                })
                                
                            # 週ルールのチェック
                            if kawari_count > kawari_target + 1 or kawari_count < kawari_target - 1:
                                week_alerts.append(f"📌 **変わり御飯**：今週{kawari_count}回 (目標{kawari_target}回前後)")
                            if curry_count == 0:
                                week_alerts.append(f"❌ **カレーライス**：今週の提供がありません (週1回必須)")

                            # AIへ送信し、JSONとしてパース
                            response = model.generate_content(prompt)
                            ai_raw_text = response.text
                            
                            try:
                                clean_text = re.sub(r'```json\n?', '', ai_raw_text)
                                clean_text = re.sub(r'```\n?', '', clean_text)
                                parsed_json = json.loads(clean_text.strip())
                                parse_success = True
                                
                                # day_detailsにAIコメントを紐づけ
                                for item in parsed_json:
                                    d = item.get("date", "")
                                    for day_d in day_details:
                                        if day_d["date"] == d:
                                            day_d["ai_comments"].append(f"**[{item.get('meal', '全体')}]** {item.get('comment', '')}")
                            except:
                                parse_success = False

                            week_results.append({
                                "week_alerts": week_alerts,
                                "days": day_details,
                                "parse_success": parse_success,
                                "raw_text": ai_raw_text
                            })

                        # --- 3. 画面への結果表示 ---
                        st.success(f"✅ 全ての解析が完了しました！")
                        
                        tab_names = ["📊 全体サマリー"] + [f"📅 第{i+1}週" for i in range(len(weeks))]
                        result_tabs = st.tabs(tab_names)
                        
                        with result_tabs[0]:
                            st.subheader("システムの解析完了")
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

                                for day_data in week_results[i]["days"]:
                                    st.markdown(f"<div class='day-container'>", unsafe_allow_html=True)
                                    st.markdown(f"#### 🗓️ {day_data['date']}")
                                    
                                    col_m, col_q, col_ai = st.columns([2, 1.5, 2])
                                    
                                    with col_m:
                                        st.caption("🍽️ 提供予定メニュー")
                                        for m in day_data["menus"]:
                                            st.markdown(f"<div class='menu-text'>{m}</div>", unsafe_allow_html=True)
                                            
                                    with col_q:
                                        st.caption("📊 システム判定 (ルール・数値)")
                                        if day_data["alerts"]:
                                            for a in day_data["alerts"]:
                                                if "❌" in a or "🚨" in a: st.error(a)
                                                else: st.warning(a)
                                        else:
                                            st.write("✅ 問題なし")
                                            
                                    with col_ai:
                                        st.caption("🤖 AI定性チェック (文脈・バランス)")
                                        if day_data["ai_comments"]:
                                            for c in day_data["ai_comments"]:
                                                st.error(c) 
                                        else:
                                            st.write("✨ 指摘なし")
                                            
                                    st.divider()
                                    st.markdown(f"</div>", unsafe_allow_html=True)

                    except Exception as e:
                        st.error(f"❌ 処理中にエラーが発生しました: {e}")

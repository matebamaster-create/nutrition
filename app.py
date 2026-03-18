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

# カスタムCSS（日別カードを見やすくするための線や余白の調整）
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

DEFAULT_RULES = """1. 味付けのバランス（メインと付け合わせの相性、1食の味の偏り）
2. 彩りと形状（全体が茶色っぽくないか、似た形状ばかりでないか）
3. パンの日の組み合わせ（洋風のおかずか、牛乳・豆乳・コンソメ系スープか）
4. 日曜日の特別ルール（日曜の冷小鉢が「サラダ類」と「果物orデザート」か）
5. 外来食への配慮（片手で食べにくいもの、おかずにならないもの、おでん等ボリューム不足の回避）"""

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
    st.markdown("### 📏 定量チェック基準")
    max_salt = st.number_input("1日の塩分上限 (g)", value=6.3, step=0.1)
    
    st.markdown("**朝食のたんぱく質 (g)**")
    col1, col2 = st.columns(2)
    min_pro_bf = col1.number_input("下限", value=10.0, step=0.5, key="min_pro_bf")
    max_pro_bf = col2.number_input("上限", value=15.0, step=0.5, key="max_pro_bf")
    
    st.markdown("**昼・夕食のたんぱく質 (g)**")
    col3, col4 = st.columns(2)
    min_pro_ld = col3.number_input("下限", value=23.0, step=0.5, key="min_pro_ld")
    max_pro_ld = col4.number_input("上限", value=27.0, step=0.5, key="max_pro_ld")
    
    max_potassium = st.number_input("昼・夕食のカリウム上限 (mg)", value=850, step=10)
    kawari_target = st.number_input("変わり御飯の週目標 (回)", value=3, step=1)
    
    st.success("変更は即座に反映されます👍")

# ==========================================
# メイン画面
# ==========================================
st.title("🍽️ 透析食A 献立自動チェックシステム")
st.markdown("毎月の献立ファイルをアップロードすると、栄養素の定量チェックとAI定性レビューを自動実行します。")

tab_main, tab_rules = st.tabs(["🔍 献立チェック実行", "📝 定性ルールマスター管理"])

with tab_rules:
    st.subheader("💡 AIにチェックさせる「定性的ルール」の管理")
    st.info("ここで設定した文章が、そのままAIへの指示になります。季節ごとの注意点などを自由に追加・編集してください。")
    current_rules = load_ai_rules()
    edited_rules = st.text_area("▼ 現在の登録ルール", value=current_rules, height=250)
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
                
                with st.spinner('データを解析し、AIが献立をレビューしています...（約1分かかります）'):
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
                        total_salt_errors = 0
                        total_pro_errors = 0
                        active_rules = load_ai_rules()

                        # 各週の処理
                        for week_idx, week in enumerate(weeks):
                            week_alerts = []
                            kawari_count = 0
                            day_details = []
                            
                            # プロンプト作成（JSON形式で返すようAIに強めに指示）
                            prompt = f"あなたは病院のプロの管理栄養士です。以下の献立を読み込み、修正が必要なポイントをリストアップしてください。\n\n"
                            prompt += f"【チェックしてほしい定性的ルール】\n{active_rules}\n\n"
                            prompt += "【出力フォーマット】\n出力は必ず以下のJSON配列形式のみで返してください。Markdown記号(```json)は不要です。問題がない日は配列に含めないでください。\n"
                            prompt += '[\n  {"date": "〇月〇日(曜)", "meal": "〇食", "comment": "〇〇のため変更を検討"}\n]\n\n'
                            
                            for day in week:
                                date = day.get('date')
                                total_nut = day.get("daily_total_nutrients", {})
                                day_alerts = []
                                formatted_menus = []
                                
                                # 1日塩分チェック
                                salt = total_nut.get("salt_equivalent_g", 0)
                                if salt >= max_salt:
                                    day_alerts.append(f"🚨 **1日塩分超過** ({salt}g / 基準{max_salt}g未満)")
                                    total_salt_errors += 1
                                
                                prompt += f"■ {date}\n"
                                
                                for meal_type, meal_name in [("breakfast", "朝食"), ("lunch", "昼食"), ("dinner", "夕食")]:
                                    meal_data = day.get("meals", {}).get(meal_type, {})
                                    menu = meal_data.get("menu", [])
                                    nut = meal_data.get("nutrients", {})
                                    pro = nut.get("protein_g", 0)
                                    pot = nut.get("potassium_mg", 0)
                                    
                                    if menu:
                                        if meal_type in ["lunch", "dinner"] and menu[0] != "御飯":
                                            kawari_count += 1
                                            
                                        if meal_type == "breakfast":
                                            if pro > 0 and (pro < min_pro_bf or pro > max_pro_bf):
                                                day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g / 基準{min_pro_bf}-{max_pro_bf}g)")
                                                total_pro_errors += 1
                                        else:
                                            if pro > 0 and (pro < min_pro_ld or pro > max_pro_ld):
                                                day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g / 基準{min_pro_ld}-{max_pro_ld}g)")
                                                total_pro_errors += 1
                                            if pot > max_potassium:
                                                day_alerts.append(f"⚠️ **{meal_name} カリウム** ({pot}mg / 上限{max_potassium}mg)")
                                                
                                        clean_menu = [m for m in menu if ":" not in m and "kcal" not in m]
                                        formatted_menus.append(f"**[{meal_name}]** {', '.join(clean_menu)}")
                                        prompt += f"[{meal_name}] {', '.join(clean_menu)}\n"
                                        
                            if kawari_count > kawari_target + 1 or kawari_count < kawari_target - 1:
                                week_alerts.append(f"📌 **今週の変わり御飯**：{kawari_count}回 (目標{kawari_target}回前後です)")

                            # AIへ送信し、JSONとしてパース（変換）
                            response = model.generate_content(prompt)
                            ai_raw_text = response.text
                            ai_feedback_dict = {}
                            
                            try:
                                # JSON部分だけを抽出して変換
                                clean_text = re.sub(r'```json\n?', '', ai_raw_text)
                                clean_text = re.sub(r'```\n?', '', clean_text)
                                parsed_json = json.loads(clean_text.strip())
                                for item in parsed_json:
                                    d = item.get("date", "")
                                    if d not in ai_feedback_dict:
                                        ai_feedback_dict[d] = []
                                    ai_feedback_dict[d].append(f"**[{item.get('meal', '全体')}]** {item.get('comment', '')}")
                                parse_success = True
                            except:
                                parse_success = False
                                
                            # UI描画用に日別データを再構築
                            for day in week:
                                date_str = day.get('date')
                                # 上で集計した day_alerts を取得
                                day_alerts = [a for a in day_alerts] # すでにローカル変数にあるが再生成が必要な場合はループ外で保持するよう修正しました。
                                
                                # ※簡略化のため再集計
                                current_day_alerts = []
                                total_nut = day.get("daily_total_nutrients", {})
                                if total_nut.get("salt_equivalent_g", 0) >= max_salt:
                                    current_day_alerts.append(f"🚨 **1日塩分超過** ({total_nut.get('salt_equivalent_g')}g)")
                                
                                current_menus = []
                                for meal_type, meal_name in [("breakfast", "朝食"), ("lunch", "昼食"), ("dinner", "夕食")]:
                                    menu = day.get("meals", {}).get(meal_type, {}).get("menu", [])
                                    pro = day.get("meals", {}).get(meal_type, {}).get("nutrients", {}).get("protein_g", 0)
                                    pot = day.get("meals", {}).get(meal_type, {}).get("nutrients", {}).get("potassium_mg", 0)
                                    
                                    if menu:
                                        if meal_type == "breakfast" and pro > 0 and (pro < min_pro_bf or pro > max_pro_bf):
                                            current_day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g)")
                                        elif meal_type != "breakfast" and pro > 0 and (pro < min_pro_ld or pro > max_pro_ld):
                                            current_day_alerts.append(f"⚠️ **{meal_name} たんぱく** ({pro}g)")
                                        if meal_type != "breakfast" and pot > max_potassium:
                                            current_day_alerts.append(f"⚠️ **{meal_name} カリウム** ({pot}mg)")
                                            
                                        clean_menu = [m for m in menu if ":" not in m and "kcal" not in m]
                                        current_menus.append(f"**[{meal_name}]** {', '.join(clean_menu)}")
                                
                                day_details.append({
                                    "date": date_str,
                                    "menus": current_menus,
                                    "alerts": current_day_alerts,
                                    "ai_comments": ai_feedback_dict.get(date_str, [])
                                })

                            week_results.append({
                                "week_alerts": week_alerts,
                                "days": day_details,
                                "parse_success": parse_success,
                                "raw_text": ai_raw_text
                            })

                        # --- 3. 画面への結果表示（タブUI・日別カード表示） ---
                        st.success(f"✅ 全てのチェックが完了しました！")
                        
                        tab_names = ["📊 全体サマリー"] + [f"📅 第{i+1}週" for i in range(len(weeks))]
                        result_tabs = st.tabs(tab_names)
                        
                        with result_tabs[0]:
                            st.subheader("今月のチェック総括")
                            colA, colB, colC = st.columns(3)
                            colA.metric("1日塩分超過日数", f"{total_salt_errors} 日", delta="要確認" if total_salt_errors>0 else "完璧!", delta_color="inverse")
                            colB.metric("たんぱく質基準外", f"{total_pro_errors} 食", delta="要確認" if total_pro_errors>0 else "完璧!", delta_color="inverse")
                            colC.metric("解析した週", f"{len(weeks)} 週")
                            st.info("💡 各週のタブをクリックして、日別の詳細なエラーとメニューを一覧で確認できます。")
                        
                        for i, tab in enumerate(result_tabs[1:]):
                            with tab:
                                if week_results[i]["week_alerts"]:
                                    for wa in week_results[i]["week_alerts"]:
                                        st.info(wa)
                                        
                                if not week_results[i]["parse_success"]:
                                    st.warning("⚠️ AIの回答形式が一部崩れました。念のため生の指摘データも表示します。")
                                    with st.expander("AIからの生データを見る"):
                                        st.write(week_results[i]["raw_text"])

                                # 日別の横並びカード描画
                                for day_data in week_results[i]["days"]:
                                    st.markdown(f"<div class='day-container'>", unsafe_allow_html=True)
                                    st.markdown(f"#### 🗓️ {day_data['date']}")
                                    
                                    col_m, col_q, col_ai = st.columns([2, 1, 2])
                                    
                                    with col_m:
                                        st.caption("🍽️ 提供予定メニュー")
                                        for m in day_data["menus"]:
                                            st.markdown(f"<div class='menu-text'>{m}</div>", unsafe_allow_html=True)
                                            
                                    with col_q:
                                        st.caption("📊 定量ルール (数値エラー)")
                                        if day_data["alerts"]:
                                            for a in day_data["alerts"]:
                                                st.write(a)
                                        else:
                                            st.write("✅ 問題なし")
                                            
                                    with col_ai:
                                        st.caption("🤖 AI定性チェック (ルール違反)")
                                        if day_data["ai_comments"]:
                                            for c in day_data["ai_comments"]:
                                                st.error(c) # エラーを目立たせるために赤い枠(error)で表示
                                        else:
                                            st.write("✨ 問題なし")
                                            
                                    st.divider() # 日ごとの区切り線
                                    st.markdown(f"</div>", unsafe_allow_html=True)

                    except Exception as e:
                        st.error(f"❌ 処理中にエラーが発生しました: {e}")

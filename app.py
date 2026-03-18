import streamlit as st
import pandas as pd
import re
import os
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

# カスタムCSS
st.markdown("""
    <style>
    .main { background-color: #FAFAFA; }
    h1, h2, h3 { color: #2C3E50; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; border-radius: 5px 5px 0 0; }
    </style>
    """, unsafe_allow_html=True)

# 定性ルール保存用のファイルパス
RULE_FILE = "ai_rules.txt"

# デフォルトの定性ルール
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
# メイン画面（タブ構成）
# ==========================================
st.title("🍽️ 透析食A 献立自動チェックシステム")
st.markdown("毎月の献立ファイル（Excel）をアップロードすると、栄養素の定量チェックとAIによる定性レビューを自動実行します。")

# 大きなタブで機能を分ける
tab_main, tab_rules = st.tabs(["🔍 献立チェック実行", "📝 定性ルールマスター管理"])

# ------------------------------------------
# タブ2：定性ルールマスター管理
# ------------------------------------------
with tab_rules:
    st.subheader("💡 AIにチェックさせる「定性的ルール」の管理")
    st.info("ここで設定した文章が、そのままAIへの指示（プロンプト）になります。季節ごとの注意点などを自由に追加・編集してください。")
    
    current_rules = load_ai_rules()
    edited_rules = st.text_area("▼ 現在の登録ルール（自由に書き換えてください）", value=current_rules, height=250)
    
    if st.button("💾 このルールをマスターに保存する", type="primary"):
        save_ai_rules(edited_rules)
        st.success("新しい定性ルールを保存しました！次回のチェックからAIがこの基準でレビューします。")

# ------------------------------------------
# タブ1：献立チェック実行
# ------------------------------------------
with tab_main:
    uploaded_file = st.file_uploader("📂 献立ファイルのアップロード（.xls または .xlsx）", type=['xls', 'xlsx'])

    if uploaded_file is not None:
        if not api_key:
            st.warning("👈 左のサイドバーでAIシステムが接続されているか確認してください（Secretsの設定が必要です）。")
        else:
            if st.button("✨ AI自動チェックを開始する", type="primary", use_container_width=True):
                # AI設定
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-pro')
                
                with st.spinner('データを解析し、AIが献立をレビューしています...（約30秒〜1分）'):
                    try:
                        # --- 1. Excelの読み込みとデータ抽出 ---
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
                                        "meals": {
                                            "breakfast": {"menu": [], "nutrients": {}},
                                            "lunch": {"menu": [], "nutrients": {}},
                                            "dinner": {"menu": [], "nutrients": {}}
                                        },
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
                                            if current_state == 'daily_total':
                                                day_data["daily_total_nutrients"] = n_data
                                                break
                                            else:
                                                day_data["meals"][current_state]["nutrients"] = n_data
                                            state_idx += 1
                                            r += 4 
                                            continue
                                            
                                        if cell and current_state != 'daily_total':
                                            day_data["meals"][current_state]["menu"].append(cell)
                                        r += 1
                                    daily_data.append(day_data)

                        # --- 2. データの週分割とチェック実行 ---
                        weeks = []
                        current_week = []
                        for day in daily_data:
                            current_week.append(day)
                            if "(日)" in day.get("date", ""):
                                weeks.append(current_week)
                                current_week = []
                        if current_week: weeks.append(current_week)

                        # 結果格納用
                        week_results = []
                        total_salt_errors = 0
                        total_pro_errors = 0
                        
                        # AIプロンプトのベース（マスターから読み込み）
                        active_rules = load_ai_rules()

                        for week_idx, week in enumerate(weeks):
                            week_alerts = []
                            kawari_count = 0
                            
                            prompt = f"あなたは病院のプロの管理栄養士です。以下の献立を読み込み、修正が必要なポイントをリストアップしてください。\n\n"
                            prompt += f"【チェックしてほしい定性的ルール】\n{active_rules}\n\n"
                            prompt += "【出力フォーマット】\n問題がない日は出力せず、修正が必要な日のみ「■ 〇月〇日 〇食：〇〇のため〇〇に変更を検討」と簡潔に出力してください。\n\n"
                            
                            for day in week:
                                date = day.get('date')
                                total_nut = day.get("daily_total_nutrients", {})
                                
                                # 1日塩分チェック
                                salt = total_nut.get("salt_equivalent_g", 0)
                                if salt >= max_salt:
                                    week_alerts.append(f"🚨 **{date}**：[1日塩分] 超過 ({salt}g / 基準{max_salt}g未満)")
                                    total_salt_errors += 1
                                
                                prompt += f"■ {date}\n"
                                
                                for meal_type, meal_name in [("breakfast", "朝食"), ("lunch", "昼食"), ("dinner", "夕食")]:
                                    meal_data = day.get("meals", {}).get(meal_type, {})
                                    menu = meal_data.get("menu", [])
                                    nut = meal_data.get("nutrients", {})
                                    pro = nut.get("protein_g", 0)
                                    pot = nut.get("potassium_mg", 0)
                                    
                                    if menu:
                                        # 変わり御飯カウント
                                        if meal_type in ["lunch", "dinner"] and menu[0] != "御飯":
                                            kawari_count += 1
                                            
                                        # たんぱく質・カリウムチェック
                                        if meal_type == "breakfast":
                                            if pro > 0 and (pro < min_pro_bf or pro > max_pro_bf):
                                                week_alerts.append(f"⚠️ **{date} {meal_name}**：たんぱく質基準外 ({pro}g / 基準{min_pro_bf}-{max_pro_bf}g)")
                                                total_pro_errors += 1
                                        else:
                                            if pro > 0 and (pro < min_pro_ld or pro > max_pro_ld):
                                                week_alerts.append(f"⚠️ **{date} {meal_name}**：たんぱく質基準外 ({pro}g / 基準{min_pro_ld}-{max_pro_ld}g)")
                                                total_pro_errors += 1
                                            if pot > max_potassium:
                                                week_alerts.append(f"⚠️ **{date} {meal_name}**：カリウム超過 ({pot}mg / 上限{max_potassium}mg)")
                                                
                                        clean_menu = [m for m in menu if ":" not in m and "kcal" not in m]
                                        prompt += f"[{meal_name}] {', '.join(clean_menu)}\n"
                                        
                            # 週ルールのチェック
                            if kawari_count > kawari_target + 1 or kawari_count < kawari_target - 1:
                                week_alerts.append(f"📌 **今週の変わり御飯**：{kawari_count}回 (目標{kawari_target}回前後です)")

                            # AIへ送信
                            response = model.generate_content(prompt)
                            
                            week_results.append({
                                "alerts": week_alerts,
                                "ai_review": response.text
                            })

                        # --- 3. 画面への結果表示（タブUI） ---
                        st.success("✅ 全てのチェックが完了しました！以下のタブから結果を確認してください。")
                        
                        # タブの生成
                        tab_names = ["📊 全体サマリー"] + [f"📅 第{i+1}週" for i in range(len(weeks))]
                        result_tabs = st.tabs(tab_names)
                        
                        # 全体サマリータブ
                        with result_tabs[0]:
                            st.subheader("今月のチェック総括")
                            colA, colB, colC = st.columns(3)
                            colA.metric("1日塩分超過日数", f"{total_salt_errors} 日", delta="要確認" if total_salt_errors>0 else "完璧!", delta_color="inverse")
                            colB.metric("たんぱく質基準外", f"{total_pro_errors} 食", delta="要確認" if total_pro_errors>0 else "完璧!", delta_color="inverse")
                            colC.metric("解析した週", f"{len(weeks)} 週")
                            st.info("💡 各週のタブをクリックすると、日別の詳細なエラーとAIからのアドバイスが確認できます。")
                        
                        # 各週のタブ
                        for i, tab in enumerate(result_tabs[1:]):
                            with tab:
                                st.markdown(f"### 第{i+1}週のチェック結果")
                                
                                col_left, col_right = st.columns(2)
                                
                                with col_left:
                                    st.markdown("#### 🚨 定量チェック（数値・ルール）")
                                    if week_results[i]["alerts"]:
                                        for alert in week_results[i]["alerts"]:
                                            st.write(alert)
                                    else:
                                        st.success("数値やルールのエラーはありません！🎉")
                                        
                                with col_right:
                                    st.markdown("#### 🤖 AI定性チェック（彩り・味付けなど）")
                                    if week_results[i]["ai_review"]:
                                        st.info(week_results[i]["ai_review"])
                                    else:
                                        st.success("AIが指摘する問題点はありませんでした！✨")

                    except Exception as e:
                        st.error(f"❌ 処理中にエラーが発生しました: {e}")

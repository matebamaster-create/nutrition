import streamlit as st
import pandas as pd
import re
import os
import json
import io
import google.generativeai as genai
import plotly.express as px
import plotly.graph_objects as go

# ==========================================
# ページ全体のデザイン設定
# ==========================================
st.set_page_config(
    page_title="献立自動チェックシステム",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 食事別のカスタムカラーボックス・チェックボックス用余白調整
st.markdown("""
    <style>
    .main { background-color: #FAFAFA; }
    h1, h2, h3 { color: #2C3E50; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { padding-top: 10px; padding-bottom: 10px; border-radius: 5px 5px 0 0; }
    .day-container { padding: 10px 0px; }
    
    .meal-box {
        padding: 8px 12px;
        margin-bottom: 2px; /* チェックボックスとの隙間を詰める */
        border-radius: 4px;
        border-left: 5px solid;
        font-size: 0.9em;
        line-height: 1.4;
        width: 100%;
    }
    .meal-bf { background-color: #FFF3E0; border-left-color: #FF9800; color: #E65100; }
    .meal-ld { background-color: #E8F5E9; border-left-color: #4CAF50; color: #2E7D32; }
    .meal-dn { background-color: #E3F2FD; border-left-color: #2196F3; color: #1565C0; }
    .meal-all { background-color: #FFEBEE; border-left-color: #F44336; color: #C62828; }
    
    /* Streamlitの標準チェックボックスの余白を少し詰める */
    div[data-testid="stCheckbox"] {
        margin-bottom: 15px;
    }
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
・いも類が同じ時間に2つ、または毎食提供されていないか.
・にんじんや青物などが同じ時間に全品提供していないか
・（ 主菜にほうれん草、副菜に小松菜はNG ）
・箸だけでは食べにくい食材（ 豆や豆腐、ひじきなど ）には小スプーンをつける配慮がメニュー名から読み取れるか。
・同じ名前の魚（サバ、サケ、カレイ等）が、同じ週の中や連続した日で提供されていないか厳しくチェックすること。"""

DEFAULT_MODEL = "gemini-3.1-pro-preview" 

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

def strip_html(text):
    return re.sub(r'<[^>]+>', '', text)

# ==========================================
# サイドバー（設定画面）
# ==========================================
with st.sidebar:
    logo_path = "logo.png"
    if os.path.exists(logo_path):
        st.image(logo_path, use_column_width=True)
    else:
        st.image("https://cdn-icons-png.flaticon.com/512/3448/3448066.png", width=80)
    
    st.title("⚙️ システム設定")
    
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        st.success("🟢 AIシステム接続済み")
    except Exception:
        api_key = None
        st.error("⚠️ APIキーが設定されていません")
    
    st.markdown("---")
    st.markdown("### 📏 基準値の微調整")
    
    with st.expander("⚡ カロリー (kcal)", expanded=False):
        min_cal_daily = st.number_input("1日の下限", value=1700, step=10)
        max_cal_daily = st.number_input("1日の上限", value=1800, step=10)
        min_cal_bf = st.number_input("朝食の下限", value=400, step=10)
        max_cal_bf = st.number_input("朝食の上限(基本)", value=500, step=10)
        max_cal_bf_bread = st.number_input("朝食の上限(パン)", value=550, step=10)
        min_cal_ld = st.number_input("昼・夕食の下限", value=550, step=10)
        max_cal_ld = st.number_input("昼・夕食の上限", value=750, step=10)

    with st.expander("🥩 たんぱく質 (g)", expanded=False):
        min_pro_bf = st.number_input("朝食の下限", value=10.0, step=0.5)
        max_pro_bf = st.number_input("朝食の上限", value=15.0, step=0.5)
        min_pro_ld = st.number_input("昼・夕食の下限", value=23.0, step=0.5)
        max_pro_ld = st.number_input("昼・夕食の上限", value=27.0, step=0.5)

    with st.expander("🧂 塩分 (g)", expanded=False):
        max_salt_daily = st.number_input("1日の上限", value=6.3, step=0.1)
        max_salt_bf = st.number_input("朝食の上限(基本)", value=2.0, step=0.1)
        max_salt_bf_bread = st.number_input("朝食の上限(パン)", value=2.3, step=0.1)
        max_salt_ld = st.number_input("昼・夕食の上限(基本)", value=2.0, step=0.1)
        max_salt_ld_aji = st.number_input("昼・夕食の上限(味ご飯)", value=2.5, step=0.1)
        max_salt_ld_noodle = st.number_input("昼・夕食の上限(パン/麺/等)", value=2.8, step=0.1)

    with st.expander("🥦 その他", expanded=False):
        max_potassium = st.number_input("昼・夕食のカリウム上限 (mg)", value=850, step=10)
        kawari_target = st.number_input("変わり御飯の週目標 (回)", value=3, step=1)

# ==========================================
# メイン画面
# ==========================================
st.title("🍽️ 透析食A 献立自動チェックシステム")

tab_main, tab_rules = st.tabs(["🔍 献立チェック実行", "📝 マスター管理 (ルール・AIモデル)"])

with tab_rules:
    st.subheader("🤖 AIモデルの管理")
    current_model = load_ai_model()
    edited_model = st.text_input("▼ 現在のAIモデル", value=current_model)
    if st.button("💾 AIモデル名を保存する", type="primary"):
        save_ai_model(edited_model)
        st.success(f"更新しました！")
    
    st.markdown("---")
    st.subheader("💡 AIにチェックさせる「定性的ルール」の管理")
    current_rules = load_ai_rules()
    edited_rules = st.text_area("▼ 現在の登録ルール", value=current_rules, height=400)
    if st.button("💾 このルールをマスターに保存する", type="primary"):
        save_ai_rules(edited_rules)
        st.success("保存しました！")

with tab_main:
    uploaded_file = st.file_uploader("📂 献立ファイルのアップロード（.xls または .xlsx）", type=['xls', 'xlsx'])

    if uploaded_file is not None:
        if "last_uploaded" not in st.session_state or st.session_state.last_uploaded != uploaded_file.name:
            st.session_state.processed = False
            st.session_state.last_uploaded = uploaded_file.name
            if "analysis_results" in st.session_state: del st.session_state.analysis_results

        if not api_key:
            st.warning("👈 左のサイドバーでAIシステムが接続されているか確認してください。")
        else:
            if not st.session_state.get("processed", False):
                if st.button("✨ AI自動チェックを開始する", type="primary", use_container_width=True):
                    genai.configure(api_key=api_key)
                    
                    with st.spinner('高度なAI解析（ルール判定・食材カテゴリ分類）を実行中です...（約1〜2分かかります）'):
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
                            
                            day_idx_counter = 0
                            for week in weeks:
                                for day in week:
                                    day['day_index'] = day_idx_counter
                                    day_idx_counter += 1

                            week_results = []
                            active_rules = load_ai_rules()
                            
                            count_salt_daily, count_cal_daily, count_nut_meal, count_ng = 0, 0, 0, 0
                            
                            categories = ['白身魚', '青魚', 'その他(赤魚)', '豚肉', '鶏肉', '牛肉', 'ミンチ']
                            time_slots = ['月水金(昼)', '月水金(夕)', '火木土(昼)', '火木土(夕)']
                            detailed_cross_data = {cat: {slot: [] for slot in time_slots} for cat in categories}
                            fish_details = {'白身魚': {}, '青魚': {}, 'その他(赤魚)': {}}
                            fish_history = []
                            fish_alerts = []
                            kawari_weekly_counts = []
                            
                            # 出力リスト（IDベースで管理）
                            export_registry = []

                            ai_instruction = f"""あなたは病院のプロの管理栄養士です。以下の献立データを読み込み、2つのタスクを実行してください。

【タスク1：定性的ルールのチェック】
以下のルールに基づき、修正が必要なポイントをリストアップしてください。
{active_rules}

【タスク2：昼食・夕食のメイン食材のカテゴリ分類】
各日の「昼食」と「夕食」のメニューを文脈から判断し、メインとなる食材を以下の7カテゴリのいずれかに分類してください。
カテゴリ：[白身魚, 青魚, その他(赤魚), 牛肉, 豚肉, 鶏肉, ミンチ]
※果物（マスカット等）や乳製品（牛乳等）、野菜（牛蒡等）を肉・魚と誤認しないよう、料理の文脈から正確に判断してください。
※メイン食材が上記7カテゴリに該当しない場合はカテゴリ分類に含めないでください。
※魚（白身魚、青魚、その他(赤魚)）に分類した場合は、必ず具体的な魚種名（例：サバ、サケ、タラ、アジなど）も特定してください。

【出力フォーマット】
必ず以下のJSON形式のみで返してください。Markdown記号は不要です。
{{
  "alerts": [ {{"date": "〇月〇日(曜)", "meal": "〇食", "comment": "〇〇のため変更を検討"}} ],
  "ingredients": [ {{"date": "〇月〇日(曜)", "meal": "〇食", "menu_name": "料理名", "category": "カテゴリ", "fish_name": "魚種名"}} ]
}}"""

                            for week_idx, week in enumerate(weeks):
                                week_alerts = []
                                kawari_count, curry_count = 0, 0
                                day_details = []
                                prompt = ai_instruction + "\n\n【対象の献立データ】\n"
                                
                                for day in week:
                                    date = day.get('date')
                                    day_index = day.get('day_index', 0)
                                    total_nut = day.get("daily_total_nutrients", {})
                                    day_alerts = []
                                    formatted_menus = []
                                    
                                    is_monday = "(月)" in date
                                    is_sunday = "(日)" in date
                                    
                                    # 1日ルールチェック
                                    salt = total_nut.get("salt_equivalent_g", 0)
                                    if salt >= max_salt_daily:
                                        msg = f"🚨 <b>1日塩分</b> 超過 ({salt}g / {max_salt_daily}g未満)"
                                        a_id = f"sys_all_salt_{date}"
                                        day_alerts.append({"type": "all", "text": msg, "id": a_id})
                                        export_registry.append({"id": a_id, "date": date, "meal": "1日全体", "source": "定量/ルール", "text": strip_html(msg)})
                                        count_salt_daily += 1
                                        
                                    cal_total = total_nut.get("energy_kcal", 0)
                                    if cal_total > 0 and (cal_total < min_cal_daily or cal_total > max_cal_daily):
                                        msg = f"⚠️ <b>1日カロリー</b> 基準外 ({cal_total}kcal / {min_cal_daily}-{max_cal_daily})"
                                        a_id = f"sys_all_cal_{date}"
                                        day_alerts.append({"type": "all", "text": msg, "id": a_id})
                                        export_registry.append({"id": a_id, "date": date, "meal": "1日全体", "source": "定量/ルール", "text": strip_html(msg)})
                                        count_cal_daily += 1

                                    prompt += f"■ {date}\n"
                                    
                                    for meal_type, meal_name in [("breakfast", "朝食"), ("lunch", "昼食"), ("dinner", "夕食")]:
                                        meal_data = day.get("meals", {}).get(meal_type, {})
                                        menu = meal_data.get("menu", [])
                                        nut = meal_data.get("nutrients", {})
                                        
                                        pro, pot, cal, meal_salt = nut.get("protein_g", 0), nut.get("potassium_mg", 0), nut.get("energy_kcal", 0), nut.get("salt_equivalent_g", 0)
                                        
                                        if menu:
                                            clean_menu = [m for m in menu if ":" not in m and "kcal" not in m and not re.match(r'^\d', m)]
                                            menu_str = "".join(clean_menu)
                                            is_bread = any(k in menu_str for k in ['パン', 'サンドイッチ', 'ホットドッグ', 'バーガー'])
                                            is_noodle = any(k in menu_str for k in ['うどん', 'そば', 'ラーメン', 'パスタ', 'スパゲティ', 'そうめん', 'ちゃんぽん', '麺'])
                                            is_aji_gohan = any(k in menu_str for k in ['ピラフ', '炒飯', 'チャーハン', 'かしわ飯', '炊き込み', '丼', '寿司', 'オムライス', 'ビーフシチュー'])
                                            is_curry = 'カレー' in menu_str
                                            is_natto = '納豆' in menu_str
                                            
                                            # NG判定
                                            if is_natto and (is_sunday or is_monday):
                                                msg = f"❌ <b>[{meal_name}]</b> 日・月の納豆提供はNG"
                                                a_id = f"sys_ng_natto_{date}_{meal_type}"
                                                day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                count_ng += 1
                                            if is_bread and meal_type == "dinner":
                                                msg = f"❌ <b>[{meal_name}]</b> 夕食のパン提供はNG"
                                                a_id = f"sys_ng_bread_dn_{date}_{meal_type}"
                                                day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                count_ng += 1
                                            if is_bread and is_monday:
                                                msg = f"❌ <b>[{meal_name}]</b> 月曜のパン提供はNG"
                                                a_id = f"sys_ng_bread_mon_{date}_{meal_type}"
                                                day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                count_ng += 1
                                            if is_noodle and meal_type == "dinner":
                                                msg = f"❌ <b>[{meal_name}]</b> 夕食の麺類(汁あり)はNG"
                                                a_id = f"sys_ng_noodle_{date}_{meal_type}"
                                                day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                count_ng += 1
                                                
                                            if is_curry: curry_count += 1
                                            if meal_type in ["lunch", "dinner"] and (is_bread or is_noodle or is_aji_gohan or (menu and menu[0] != "御飯" and menu[0] != "全粥")):
                                                kawari_count += 1
                                                
                                            # 塩分・カロリー判定
                                            if meal_type == "breakfast":
                                                cal_limit = max_cal_bf_bread if is_bread else max_cal_bf
                                                if cal > 0 and (cal < min_cal_bf or cal > cal_limit):
                                                    msg = f"⚠️ <b>[{meal_name}] カロリー</b> ({cal}kcal)"
                                                    a_id = f"sys_cal_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                if pro > 0 and (pro < min_pro_bf or pro > max_pro_bf):
                                                    msg = f"⚠️ <b>[{meal_name}] たんぱく</b> ({pro}g)"
                                                    a_id = f"sys_pro_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                salt_limit = max_salt_bf_bread if is_bread else max_salt_bf
                                                if meal_salt > salt_limit:
                                                    msg = f"🚨 <b>[{meal_name}] 塩分</b> ({meal_salt}g)"
                                                    a_id = f"sys_salt_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                            else:
                                                if cal > 0 and (cal < min_cal_ld or cal > max_cal_ld):
                                                    msg = f"⚠️ <b>[{meal_name}] カロリー</b> ({cal}kcal)"
                                                    a_id = f"sys_cal_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                if pro > 0 and (pro < min_pro_ld or pro > max_pro_ld):
                                                    msg = f"⚠️ <b>[{meal_name}] たんぱく</b> ({pro}g)"
                                                    a_id = f"sys_pro_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                if pot > max_potassium:
                                                    msg = f"⚠️ <b>[{meal_name}] カリウム</b> ({pot}mg)"
                                                    a_id = f"sys_pot_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                    
                                                if is_bread or is_noodle or is_curry or '炒飯' in menu_str or '高菜ピラフ' in menu_str: salt_limit = max_salt_ld_noodle
                                                elif is_aji_gohan: salt_limit = max_salt_ld_aji
                                                else: salt_limit = max_salt_ld
                                                    
                                                if meal_salt > salt_limit:
                                                    msg = f"🚨 <b>[{meal_name}] 塩分</b> ({meal_salt}g)"
                                                    a_id = f"sys_salt_{date}_{meal_type}"
                                                    day_alerts.append({"type": meal_type, "text": msg, "id": a_id})
                                                    export_registry.append({"id": a_id, "date": date, "meal": meal_name, "source": "定量/ルール", "text": strip_html(msg)})
                                                    count_nut_meal += 1
                                                    
                                            formatted_menus.append({"type": meal_type, "text": f"<b>[{meal_name}]</b> {', '.join(clean_menu)}"})
                                            prompt += f"[{meal_name}] {', '.join(clean_menu)}\n"
                                            
                                    day_details.append({
                                        "date": date, "day_index": day_index,
                                        "menus": formatted_menus, "alerts": day_alerts, "ai_comments": [] 
                                    })
                                
                                kawari_weekly_counts.append(kawari_count)
                                
                                if kawari_count > kawari_target + 1 or kawari_count < kawari_target - 1:
                                    msg = f"📌 **変わり御飯**：今週{kawari_count}回 (目標{kawari_target}回前後)"
                                    a_id = f"week_kawari_{week_idx}"
                                    week_alerts.append({"text": msg, "id": a_id})
                                    export_registry.append({"id": a_id, "date": f"第{week_idx+1}週", "meal": "週間", "source": "定量/ルール", "text": strip_html(msg)})
                                    count_ng += 1
                                if curry_count == 0:
                                    msg = f"❌ **カレーライス**：今週の提供がありません (週1回必須)"
                                    a_id = f"week_curry_{week_idx}"
                                    week_alerts.append({"text": msg, "id": a_id})
                                    export_registry.append({"id": a_id, "date": f"第{week_idx+1}週", "meal": "週間", "source": "定量/ルール", "text": strip_html(msg)})
                                    count_ng += 1

                                # AIへ送信
                                response = model.generate_content(prompt)
                                ai_raw_text = response.text
                                
                                try:
                                    clean_text = re.sub(r'```json\n?', '', ai_raw_text)
                                    clean_text = re.sub(r'```\n?', '', clean_text)
                                    parsed_json = json.loads(clean_text.strip())
                                    parse_success = True
                                    
                                    # AIのアラート
                                    ai_alerts = parsed_json.get("alerts", [])
                                    for idx, item in enumerate(ai_alerts):
                                        d = item.get("date", "")
                                        ai_meal = item.get("meal", "")
                                        if "朝" in ai_meal: m_type = "breakfast"
                                        elif "昼" in ai_meal: m_type = "lunch"
                                        elif "夕" in ai_meal or "夜" in ai_meal: m_type = "dinner"
                                        else: m_type = "all"
                                        
                                        msg = f"<b>[{ai_meal}]</b> {item.get('comment', '')}"
                                        a_id = f"ai_alert_{week_idx}_{idx}"
                                        export_registry.append({"id": a_id, "date": d, "meal": ai_meal, "source": "AI定性", "text": strip_html(msg)})

                                        for day_d in day_details:
                                            if day_d["date"] == d:
                                                day_d["ai_comments"].append({"type": m_type, "text": msg, "id": a_id})
                                                
                                    # AIの食材判定
                                    ai_ingredients = parsed_json.get("ingredients", [])
                                    for item in ai_ingredients:
                                        d = item.get("date", "")
                                        meal_type_str = item.get("meal", "")
                                        ai_cat = item.get("category", "")
                                        menu_name = item.get("menu_name", "")
                                        fish_name = item.get("fish_name", "")
                                        
                                        if ai_cat in categories:
                                            day_type = ""
                                            if any(x in d for x in ["(月)", "(水)", "(金)"]): day_type = "月水金"
                                            elif any(x in d for x in ["(火)", "(木)", "(土)"]): day_type = "火木土"
                                            
                                            meal_time = ""
                                            if "昼" in meal_type_str: meal_time = "昼"
                                            elif "夕" in meal_type_str or "夜" in meal_type_str: meal_time = "夕"
                                                
                                            if day_type and meal_time:
                                                slot = f"{day_type}({meal_time})"
                                                detailed_cross_data[ai_cat][slot].append(f"{d}: {menu_name}")
                                                
                                                if ai_cat in ['白身魚', '青魚', 'その他(赤魚)'] and fish_name:
                                                    fish_details[ai_cat][fish_name] = fish_details[ai_cat].get(fish_name, 0) + 1
                                                    current_day_idx = next((dd["day_index"] for dd in day_details if dd["date"] == d), 0)
                                                    
                                                    for hist in fish_history:
                                                        diff = current_day_idx - hist['day_index']
                                                        if hist['fish'] == fish_name and diff <= 3 and diff > 0:
                                                            msg = f"🚨 【{fish_name}】 {hist['date']} と {d} で提供間隔が近すぎます（中2日以内）"
                                                            a_id = f"fish_alert_{len(fish_alerts)}"
                                                            fish_alerts.append({"text": msg, "id": a_id})
                                                            export_registry.append({"id": a_id, "date": d, "meal": "全体", "source": "定量/ルール", "text": strip_html(msg)})
                                                    fish_history.append({'date': d, 'fish': fish_name, 'day_index': current_day_idx})
                                                    
                                except Exception as e:
                                    parse_success = False

                                week_results.append({
                                    "week_alerts": week_alerts,
                                    "days": day_details,
                                    "parse_success": parse_success,
                                    "raw_text": ai_raw_text
                                })

                            st.session_state.analysis_results = {
                                "weeks": weeks,
                                "week_results": week_results,
                                "summary": (count_salt_daily, count_cal_daily, count_nut_meal, count_ng),
                                "dash": (detailed_cross_data, fish_details, kawari_weekly_counts, fish_alerts),
                                "export_registry": export_registry,
                                "model_used": target_model
                            }
                            st.session_state.processed = True
                            st.rerun()

                        except Exception as e:
                            st.error(f"❌ 処理中にエラーが発生しました: {e}")

            # ==========================================
            # 画面レンダリング（セッションデータを使用）
            # ==========================================
            if st.session_state.get("processed", False) and "analysis_results" in st.session_state:
                res = st.session_state.analysis_results
                weeks = res["weeks"]
                week_results = res["week_results"]
                c_salt, c_cal, c_nut, c_ng = res["summary"]
                d_cross, d_fish, d_kawari, d_alerts = res["dash"]
                export_registry = res["export_registry"]
                
                st.success(f"✅ 全ての解析が完了しました！（使用AIモデル: {res['model_used']}）")
                
                tab_names = ["📊 全体サマリー"] + [f"📅 第{i+1}週" for i in range(len(weeks))] + ["🖨️ レポート出力"]
                result_tabs = st.tabs(tab_names)
                
                # --- タブ0：全体サマリー ---
                with result_tabs[0]:
                    st.subheader("📊 献立チェック総括")
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("1日塩分 超過", f"{c_salt} 日")
                    col2.metric("1日カロリー 基準外", f"{c_cal} 日")
                    col3.metric("1食あたりの数値エラー", f"{c_nut} 件")
                    col4.metric("提供ルール・週間アラート", f"{c_ng} 件")
                    
                    st.divider()
                    st.markdown("### 💡 月間バランス・ダッシュボード")
                    colA, colB = st.columns([1.5, 1])
                    
                    with colA:
                        st.markdown("##### 🥩 食材の提供頻度（4枠ヒートマップ）")
                        st.caption("👉 マス目にカーソルを合わせると、具体的な日付とメニューが表示されます。")
                        categories = ['白身魚', '青魚', 'その他(赤魚)', '豚肉', '鶏肉', '牛肉', 'ミンチ']
                        time_slots = ['月水金(昼)', '月水金(夕)', '火木土(昼)', '火木土(夕)']
                        heat_data, hover_data = [], []
                        for cat in categories:
                            row_counts, row_hovers = [], []
                            for slot in time_slots:
                                count = len(d_cross[cat][slot])
                                row_counts.append(count)
                                hover_text = f"<b>{cat} - {slot}</b> (合計: {count}回)<br>" + "<br>".join(d_cross[cat][slot]) if count > 0 else f"<b>{cat} - {slot}</b><br>提供なし"
                                row_hovers.append(hover_text)
                            heat_data.append(row_counts)
                            hover_data.append(row_hovers)
                        
                        df_heat = pd.DataFrame(heat_data, index=categories, columns=time_slots)
                        fig = px.imshow(df_heat, x=time_slots, y=categories, color_continuous_scale="OrRd", aspect="auto", text_auto=True)
                        fig.update_traces(hovertemplate="%{customdata}<extra></extra>", customdata=hover_data)
                        fig.update_layout(xaxis_title="", yaxis_title="", coloraxis_showscale=False, margin=dict(l=10, r=10, t=10, b=10), height=360, yaxis=dict(autorange='reversed'))
                        fig.update_xaxes(tickangle=0, side="top")
                        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                        
                        st.markdown("##### 🐟 今月の魚種バリエーション内訳")
                        for cat in ['白身魚', '青魚', 'その他(赤魚)']:
                            details = ", ".join([f"{f}({c}回)" for f, c in d_fish[cat].items()])
                            st.markdown(f"<span style='font-size:0.9em;'><b>[{cat}]</b> {details if details else 'なし'}</span>", unsafe_allow_html=True)

                    with colB:
                        st.markdown("##### 🍚 変わり御飯の提供ペース（カレンダー順）")
                        week_names_ordered = [f"第{i+1}週" for i in range(len(weeks))]
                        df_kawari = pd.DataFrame({'週': week_names_ordered, '変わり御飯(回)': d_kawari})
                        fig_kawari = px.bar(df_kawari, x='変わり御飯(回)', y='週', orientation='h', text='変わり御飯(回)', color='変わり御飯(回)', color_continuous_scale="Oranges")
                        fig_kawari.update_traces(textposition='outside')
                        fig_kawari.update_layout(xaxis_title="", yaxis_title="", height=250, margin=dict(l=10, r=10, t=10, b=10), coloraxis_showscale=False, yaxis=dict(autorange='reversed'))
                        fig_kawari.update_xaxes(showticklabels=False, showgrid=False)
                        st.plotly_chart(fig_kawari, use_container_width=True, config={'displayModeBar': False})
                        
                        if d_alerts:
                            st.markdown("##### 🚨 食材の連続・近接提供アラート")
                            unique_fish_alerts = []
                            seen = set()
                            for alert in d_alerts:
                                if alert["text"] not in seen:
                                    seen.add(alert["text"])
                                    unique_fish_alerts.append(alert)
                                    
                            for alert in unique_fish_alerts:
                                st.error(alert["text"])
                                # ダッシュボードのアラートにもチェックボックスを追加
                                st.checkbox("📝 レポートに出力する", value=True, key=alert["id"])
                
                # --- タブ1〜N：日別メニュー（インラインチェックボックス付き） ---
                for i, tab in enumerate(result_tabs[1:-1]):
                    with tab:
                        if week_results[i]["week_alerts"]:
                            for wa in week_results[i]["week_alerts"]:
                                if "❌" in wa["text"]: st.error(wa["text"])
                                else: st.info(wa["text"])
                                st.checkbox("📝 レポートに出力する", value=True, key=wa["id"])
                                
                        if not week_results[i]["parse_success"]:
                            st.warning("⚠️ AIの回答形式が一部崩れました。念のため生の指摘データも表示します。")
                            with st.expander("AIからの生データを見る"): st.write(week_results[i]["raw_text"])

                        for day_data in week_results[i]["days"]:
                            st.markdown(f"<div class='day-container'>", unsafe_allow_html=True)
                            st.markdown(f"#### 🗓️ {day_data['date']}")
                            
                            all_alerts = [a for a in day_data["alerts"] if a["type"] == "all"]
                            all_ai = [c for c in day_data["ai_comments"] if c["type"] == "all"]
                            if all_alerts or all_ai:
                                st.markdown("<b style='color:#C62828;'>【1日全体・その他の指摘】</b>", unsafe_allow_html=True)
                                for a in all_alerts:
                                    st.markdown(f"<div class='meal-box meal-all'>{a['text']}</div>", unsafe_allow_html=True)
                                    st.checkbox("📝 レポートに出力", value=True, key=a["id"])
                                for c in all_ai:
                                    st.markdown(f"<div class='meal-box meal-all'>{c['text']}</div>", unsafe_allow_html=True)
                                    st.checkbox("📝 レポートに出力", value=True, key=c["id"])

                            col_m, col_q, col_ai = st.columns([2, 1.5, 2])
                            col_m.caption("🍽️ 提供予定メニュー")
                            col_q.caption("📊 システム判定 (ルール・数値)")
                            col_ai.caption("🤖 AI定性チェック (文脈・バランス)")

                            meal_types = [("breakfast", "meal-bf"), ("lunch", "meal-ld"), ("dinner", "meal-dn")]
                            for m_type, css_class in meal_types:
                                col1, col2, col3 = st.columns([2, 1.5, 2])
                                
                                menus = [m for m in day_data["menus"] if m["type"] == m_type]
                                with col1:
                                    for m in menus: st.markdown(f"<div class='meal-box {css_class}'>{m['text']}</div>", unsafe_allow_html=True)
                                        
                                alerts = [a for a in day_data["alerts"] if a["type"] == m_type]
                                with col2:
                                    if alerts:
                                        for a in alerts:
                                            st.markdown(f"<div class='meal-box {css_class}'>{a['text']}</div>", unsafe_allow_html=True)
                                            st.checkbox("📝 レポートに出力", value=True, key=a["id"])
                                    elif menus:
                                        st.markdown(f"<div class='meal-box {css_class}' style='opacity: 0.6;'>✅ 問題なし</div>", unsafe_allow_html=True)
                                        
                                ai_comments = [c for c in day_data["ai_comments"] if c["type"] == m_type]
                                with col3:
                                    if ai_comments:
                                        for c in ai_comments:
                                            st.markdown(f"<div class='meal-box {css_class}'>{c['text']}</div>", unsafe_allow_html=True)
                                            st.checkbox("📝 レポートに出力", value=True, key=c["id"])
                                    elif menus:
                                        st.markdown(f"<div class='meal-box {css_class}' style='opacity: 0.6;'>✨ 指摘なし</div>", unsafe_allow_html=True)
                                        
                            st.divider()
                            st.markdown(f"</div>", unsafe_allow_html=True)

                # --- タブ最後：レポート出力（スッキリ版） ---
                with result_tabs[-1]:
                    st.subheader("🖨️ 献立修正タスクシートの出力")
                    st.info("💡 各週のタブで「📝 レポートに出力」にチェックが入っている項目だけが、このExcelシートにまとめられます。\n不要なエラーは、各画面でチェックを外してください。")
                    
                    # セッションステートのチェックボックス状態を見て最終データを作成
                    final_export_data = []
                    for item in export_registry:
                        # チェックボックスのデフォルトはTrue。外されたらFalseになる
                        if st.session_state.get(item["id"], True):
                            final_export_data.append({
                                "確認": "",
                                "日付": item["date"],
                                "食事": item["meal"],
                                "判定元": item["source"],
                                "指摘内容": item["text"],
                                "対応メモ": ""
                            })
                            
                    if final_export_data:
                        df_export = pd.DataFrame(final_export_data)
                        
                        # Excel生成
                        output = io.BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df_export.to_excel(writer, index=False, sheet_name="献立修正シート")
                            worksheet = writer.sheets['献立修正シート']
                            worksheet.column_dimensions['A'].width = 6   # 確認
                            worksheet.column_dimensions['B'].width = 15  # 日付
                            worksheet.column_dimensions['C'].width = 10  # 食事
                            worksheet.column_dimensions['D'].width = 15  # 判定元
                            worksheet.column_dimensions['E'].width = 60  # 指摘内容
                            worksheet.column_dimensions['F'].width = 30  # 対応メモ
                            
                        excel_data = output.getvalue()
                        
                        st.success(f"✅ 現在、**{len(final_export_data)}件** のアラートが出力対象として選択されています。")
                        st.download_button(
                            label="📥 献立修正タスクシート (Excel) をダウンロードする",
                            data=excel_data,
                            file_name="献立修正タスクシート.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            type="primary",
                            use_container_width=True
                        )
                    else:
                        st.success("🎉 出力対象のアラートはありません！（すべてチェックが外されているか、エラーが0件です）")

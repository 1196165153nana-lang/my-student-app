# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time

# -------------------------- 1. 核心安全配置 --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_ONLY_CONTENTS = ["单词", "大学单词", "雅思单词", "旧数据补录", "导入"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

if 'menu_choice' not in st.session_state:
    st.session_state['menu_choice'] = "首页"
if 'undo_cache' not in st.session_state:
    st.session_state['undo_cache'] = None

# -------------------------- 2. 核心工具函数 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    try:
        r = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=10)
        return r.json().get("tenant_access_token")
    except: return None

def fetch_feishu_data(table_id):
    token = get_tenant_access_token()
    if not token: return pd.DataFrame()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records?page_size=500"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        items = r.json().get("data", {}).get("items", [])
        if not items: return pd.DataFrame()
        data = [item["fields"] for item in items]
        for i in range(len(items)):
            data[i]["record_id"] = items[i]["record_id"]
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    forbidden = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt", "dt_obj", "统计课型", "序号", "总课时(h)", "上课日期"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden}
    try:
        r = requests.post(url, headers=headers, json={"fields": clean_f})
        return r.json()
    except: return {"code": -1}

def update_feishu_record(table_id, record_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.put(url, headers=headers, json={"fields": fields})
        return r.json()
    except: return {"code": -1}

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(url, headers=headers)
        return r.json()
    except: return {"code": -1}

def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]: return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]: return 50
    return 40 

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦"

# -------------------------- 3. 终极自适应 CSS (匹配你的截图) --------------------------
st.set_page_config(page_title="FishTeacher", layout="wide", page_icon="🐟")

st.markdown("""
    <style>
    /* 1. 全屏宽度控制 */
    .block-container {
        max-width: 100% !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
        padding-top: 1rem !important;
    }
    
    /* 2. 标题文字居中 */
    .brand-title { text-align: center; color: #4A90E2; font-size: 45px; font-weight: bold; margin-bottom: 0px; }
    .brand-subtitle { text-align: center; color: #888; font-size: 16px; margin-bottom: 40px; }

    /* 3. 核心：长方形全宽按钮样式 */
    div.stButton > button {
        width: 100% !important;
        height: 100px !important;  /* 增加高度更像长方形 */
        font-size: 22px !important;
        font-weight: bold !important;
        color: #FFFFFF !important;
        background-color: #21242c !important; /* 深灰色背景 */
        border: 2px solid #5289f7 !important;   /* 亮蓝色边框 */
        border-radius: 20px !important;         /* 圆角 */
        margin-bottom: 15px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important; /* 文字靠左对齐 */
        padding-left: 30px !important;          /* 增加左侧边距 */
        transition: 0.3s !important;
        box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.3) !important;
    }
    
    /* 按钮点击效果 */
    div.stButton > button:active {
        transform: scale(0.98);
        background-color: #5289f7 !important;
    }

    /* 针对子页面的返回按钮样式 */
    .back-btn-box div.stButton > button {
        height: 55px !important;
        font-size: 16px !important;
        background-color: transparent !important;
        border: 1px solid #555 !important;
        justify-content: center !important;
        padding-left: 0px !important;
    }

    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# -------------------------- 4. 逻辑控制 --------------------------

def back_home():
    st.session_state['menu_choice'] = "首页"
    st.rerun()

# --- 首页：纵向排列全宽按钮 ---
if st.session_state['menu_choice'] == "首页":
    st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
    st.markdown('<p class="brand-subtitle">高效学员管理 & 21天抗遗忘系统</p>', unsafe_allow_html=True)
    
    # 一个按钮一行，自动填满宽度
    if st.button("🔍 复习提醒"): st.session_state['menu_choice'] = "提醒"; st.rerun()
    if st.button("💰 财务核算"): st.session_state['menu_choice'] = "财务"; st.rerun()
    if st.button("👥 学生档案"): st.session_state['menu_choice'] = "名册"; st.rerun()
    if st.button("📝 快速录课"): st.session_state['menu_choice'] = "录入"; st.rerun()
    if st.button("📜 流水明细"): st.session_state['menu_choice'] = "明细"; st.rerun()
    if st.button("📄 导出21天"): st.session_state['menu_choice'] = "导出"; st.rerun()
    
    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
    if st.button("📥 批量数据导入"): st.session_state['menu_choice'] = "导入"; st.rerun()

# --- 各子功能模块逻辑 (保持最新且全宽) ---

elif st.session_state['menu_choice'] == "提醒":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("🔍 单词复习清单")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("选择日期", datetime.date.today())
        target_s = st.selectbox("筛选学员", ["全部学生"] + sorted(r_df['姓名'].unique().tolist()))
        reminders = {}
        for _, row in r_df.iterrows():
            if row['学习内容'] in WORD_ONLY_CONTENTS:
                diff = (q_date - row['dt']).days + 1
                if diff in REVIEW_DAYS:
                    n = row['姓名']
                    if target_s != "全部学生" and n != target_s: continue
                    if n not in reminders: reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("无复习任务")

elif st.session_state['menu_choice'] == "财务":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("💰 财务核算 (点选看明细)")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        r_df['日期文字'] = r_df['dt_obj'].dt.strftime('%Y-%m-%d')
        target_m = st.selectbox("选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        
        c1, c2 = st.columns(2)
        c1.metric("总薪资", f"¥{m_df['小计'].sum():,.0f}")
        c2.metric("总课时", f"{m_df['课时'].sum():.1f}h")
        
        sum_df = m_df.groupby('姓名').agg({'课时': 'sum', '小计': 'sum'}).reset_index()
        sum_df = sum_df.sort_values(by='小计', ascending=False)
        sum_df.insert(0, '序号', range(1, len(sum_df) + 1))
        sum_df.columns = ["序号", "学生姓名", "总课时(h)", "总金额(元)"]
        
        event = st.dataframe(sum_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single_row")

        if event and len(event.selection.rows) > 0:
            selected_name = sum_df.iloc[event.selection.rows[0]]["学生姓名"]
            st.markdown(f"#### 🔍 {selected_name} 的明细")
            detail = m_df[m_df['姓名'] == selected_name].sort_values(by='日期文字', ascending=False)
            st.dataframe(detail[['日期文字', '学习内容', '课时', '小计']], use_container_width=True, hide_index=True)

elif st.session_state['menu_choice'] == "录入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("📝 快速录课")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("input"):
            name = st.selectbox("学生", active_s); date = st.date_input("日期"); content = st.selectbox("内容", LEARN_CONTENTS); hour = st.selectbox("课时", HOURS_OPTIONS, index=1)
            if st.form_submit_button("保存至飞书"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success("同步成功")

elif st.session_state['menu_choice'] == "名册":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("👥 学生档案管理")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    with st.expander("➕ 添加新学员"):
        with st.form("add"):
            n = st.text_input("姓名"); s = st.selectbox("状态", STATUS_OPTIONS); info = st.text_area("基础信息"); 
            if st.form_submit_button("确认入库"):
                if n: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s, "基础信息": info}); st.rerun()
    if not s_df.empty:
        target_s = st.selectbox("档案查看", ["请选择"] + sorted(s_df['姓名'].tolist()))
        if target_s != "请选择":
            data = s_df[s_df['姓名'] == target_s].iloc[0]
            current_status = st.selectbox("修改状态", STATUS_OPTIONS, index=STATUS_OPTIONS.index(data['状态']) if data['status'] in STATUS_OPTIONS else 0)
            new_info = st.text_area("基础信息文本", value=data.get('基础信息', ""), height=200)
            if st.button("💾 保存档案"):
                update_feishu_record(TABLE_ID_STUDENTS, data['record_id'], {"状态": current_status, "基础信息": new_info})
                st.success("同步完成")

elif st.session_state['menu_choice'] == "明细":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","日期","学习内容","课时"]], use_container_width=True, hide_index=True)

elif st.session_state['menu_choice'] == "导出":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt_obj'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("学员", sorted(r_all['姓名'].unique().tolist()))
        if st.button("生成 21 天表"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt_obj")
            output = [["21天表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt_obj']; rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO(); pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button("📥 下载", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

elif st.session_state['menu_choice'] == "导入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回主菜单"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f); bar = st.progress(0)
        if st.button("启动搬家"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS); names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                if name not in names_in: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"}); names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date(); ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            st.success("完成")

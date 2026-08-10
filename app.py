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

# 业务规则
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

# -------------------------- 3. 经典界面样式 --------------------------
st.set_page_config(page_title="FishTeacher", layout="centered", page_icon="🐟")

st.markdown("""
    <style>
    .brand-title { text-align: center; color: #4A90E2; font-size: 45px; font-weight: bold; margin-top: -10px; margin-bottom: 5px; }
    .brand-subtitle { text-align: center; color: #888; font-size: 14px; margin-bottom: 30px; }
    
    /* 经典大方块按钮 */
    div.stButton > button {
        width: 100%;
        height: 100px;
        font-size: 20px !important;
        font-weight: bold;
        color: #FFFFFF;
        background-color: #262730;
        border: 2px solid #4A90E2;
        border-radius: 15px;
        margin-bottom: 10px;
    }
    
    .back-btn-box div.stButton > button {
        height: 45px !important;
        font-size: 16px !important;
        border: 1px solid #444;
        background-color: transparent;
    }
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

# -------------------------- 4. 逻辑处理 --------------------------

if st.session_state['undo_cache']:
    if st.sidebar.button("🔙 撤销上次删除", type="primary"):
        add_feishu_record(st.session_state['undo_cache']['table'], st.session_state['undo_cache']['data'])
        st.session_state['undo_cache'] = None
        st.sidebar.success("已恢复！"); time.sleep(1); st.rerun()

def back_home():
    st.session_state['menu_choice'] = "首页"
    st.rerun()

# --- 首页：两列经典布局 ---
if st.session_state['menu_choice'] == "首页":
    st.markdown('<p class="brand-title">🐟 FishTeacher</p>', unsafe_allow_html=True)
    st.markdown('<p class="brand-subtitle">高效学员管理 & 21天抗遗忘系统</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔍 单词复习提醒"): st.session_state['menu_choice'] = "提醒"; st.rerun()
        if st.button("📊 财务账单核算"): st.session_state['menu_choice'] = "财务"; st.rerun()
        if st.button("👤 学生名册管理"): st.session_state['menu_choice'] = "名册"; st.rerun()
    with col2:
        if st.button("📝 课时快速录入"): st.session_state['menu_choice'] = "录入"; st.rerun()
        if st.button("📜 历史流水明细"): st.session_state['menu_choice'] = "明细"; st.rerun()
        if st.button("📄 导出21天表格"): st.session_state['menu_choice'] = "导出"; st.rerun()
    
    st.write("---")
    if st.button("📥 批量数据导入"): st.session_state['menu_choice'] = "导入"; st.rerun()

# --- 各模块逻辑 (保持功能最新) ---

elif st.session_state['menu_choice'] == "提醒":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("🔍 单词复习清单")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("提醒日期", datetime.date.today())
        target_s = st.selectbox("指定学员", ["全部学生"] + sorted(r_df['姓名'].unique().tolist()))
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
        else: st.info("该学生今日无复习任务")

elif st.session_state['menu_choice'] == "财务":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("💰 财务核算与对账")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        r_df['上课日期'] = r_df['dt_obj'].dt.strftime('%Y-%m-%d')
        target_m = st.selectbox("选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价值'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时值'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计值'] = m_df['课时值'] * m_df['单价值']
        
        c1, c2 = st.columns(2)
        c1.metric("当月总课酬", f"¥{m_df['小计值'].sum():,.0f}")
        c2.metric("当月总课时", f"{m_df['课时值'].sum():.1f} h")
        
        def merge_c(c):
            if c in ["单词", "旧数据补录", "导入", "大学单词", "雅思单词"]: return "单词课(合并)"
            return c
        m_df['统计课型'] = m_df['学习内容'].apply(merge_c)
        s_sum = m_df.groupby(['姓名', '统计课型']).agg({'课时值': 'sum', '小计值': 'sum'}).reset_index()
        s_order = s_sum.groupby('姓名')['课时值'].sum().reset_index().sort_values('课时值', ascending=False)
        final = pd.merge(s_order[['姓名']], s_sum, on='姓名', how='left')
        final.insert(0, '序号', final['姓名'].map({n: i+1 for i, n in enumerate(s_order['姓名'].unique())}))
        st.dataframe(final, use_container_width=True, hide_index=True)
        
        st.write("---")
        st.markdown("#### 🔍 学生明细穿透")
        search_n = st.selectbox("选择学生看明细", final['姓名'].unique().tolist())
        if search_n:
            detail = m_df[m_df['姓名'] == search_n].sort_values(by='上课日期', ascending=False)
            st.dataframe(detail[['上课日期', '学习内容', '课时值', '小计值']], use_container_width=True, hide_index=True)

elif st.session_state['menu_choice'] == "录入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("input"):
            name = st.selectbox("学员姓名", active_s)
            date = st.date_input("日期", datetime.date.today())
            content = st.selectbox("课程内容", LEARN_CONTENTS)
            hour = st.selectbox("时长(h)", options=HOURS_OPTIONS, index=1)
            if st.form_submit_button("🚀 存入云端"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success("✅ 同步成功！")

elif st.session_state['menu_choice'] == "名册":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("👥 学员信息库")
    with st.expander("➕ 添加学员"):
        with st.form("add"):
            n = st.text_input("姓名"); s = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("确认"):
                if n: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s}); st.rerun()
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.dataframe(s_df[["姓名","状态"]], use_container_width=True, hide_index=True)
        t = st.selectbox("🗑️ 删除学员", ["请选择"] + s_df['姓名'].tolist())
        if t != "请选择" and st.checkbox("确认永久删除"):
            if st.button("立即彻底删除"):
                rid = s_df[s_df['姓名'] == t]['record_id'].values[0]
                delete_feishu_record(TABLE_ID_STUDENTS, rid); st.rerun()

elif st.session_state['menu_choice'] == "明细":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    st.subheader("📜 历史流水")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","日期","学习内容","课时"]], use_container_width=True, hide_index=True)
        t = st.selectbox("🗑️ 删除记录", ["请选择"] + (all_r['姓名']+" | "+all_r['日期']).tolist())
        if t != "请选择" and st.checkbox("确认删除"):
            if st.button("执行删除"):
                idx = (all_r['姓名']+" | "+all_r['日期']).tolist().index(t)
                rid = all_r.iloc[idx]['record_id']
                delete_feishu_record(TABLE_ID_RECORDS, rid); st.rerun()

elif st.session_state['menu_choice'] == "导出":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt_obj'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("选择学生", sorted(r_all['姓名'].unique().tolist()))
        if st.button("生成 21 天表"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt_obj")
            output = [["21天周期表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt_obj']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO(); pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载表格", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

elif st.session_state['menu_choice'] == "导入":
    st.markdown('<div class="back-btn-box">', unsafe_allow_html=True)
    if st.button("🏠 返回 FishTeacher"): back_home()
    st.markdown('</div>', unsafe_allow_html=True)
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f)
        if st.button("🚀 启动同步"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS); bar = st.progress(0)
            names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                if name not in names_in: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"}); names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date(); ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            st.success("🎊 完成")

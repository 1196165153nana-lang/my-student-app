# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json
import time

# -------------------------- 1. 核心安全配置 --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

# 业务配置
REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]
WORD_RELATED_CONTENTS = ["单词", "大学单词", "雅思单词"]
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] 
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# 课时费逻辑
def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]: return 45
    if content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]: return 50
    return 40

if 'last_deleted' not in st.session_state:
    st.session_state['last_deleted'] = None

# -------------------------- 2. 飞书 API 核心工具 --------------------------

def get_tenant_access_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    payload = {"app_id": APP_ID, "app_secret": APP_SECRET}
    try:
        r = requests.post(url, json=payload)
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
        data = []
        for item in items:
            fields = item["fields"]
            fields["record_id"] = item["record_id"]
            data.append(fields)
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def add_feishu_record(table_id, fields):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # 过滤掉不需要上传到飞书的本地计算字段
    clean_f = {k: v for k, v in fields.items() if k not in ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt"]}
    r = requests.post(url, headers=headers, json={"fields": clean_f})
    return r.json()

def delete_feishu_record(table_id, record_id):
    token = get_tenant_access_token()
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records/{record_id}"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.delete(url, headers=headers)
    return r.json()

def generate_wechat_msg(name, review_date, learn_dates):
    rv_date_str = review_date.strftime("%m月%d日")
    sorted_ln = sorted(list(set(learn_dates)))
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日单词学习内容") for d in sorted_ln])
    return f"【21天抗遗忘单词复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦"

# -------------------------- 3. 界面布局 --------------------------
st.set_page_config(page_title="学生管理专业版", layout="centered", page_icon="🎯")

# 手机适配样式
st.markdown("<style>.stButton>button {width: 100%; height: 3.5em; font-size: 18px !important;}</style>", unsafe_allow_html=True)

# 侧边栏恢复功能
if st.session_state['last_deleted']:
    if st.sidebar.button("🔙 恢复上一条删除"):
        add_feishu_record(st.session_state['last_deleted']['table'], st.session_state['last_deleted']['data'])
        st.session_state['last_deleted'] = None
        st.sidebar.success("已恢复！")
        time.sleep(1)
        st.rerun()

menu = st.selectbox("📌 选择功能", ["📝 课时录入", "🔍 单词复习提醒", "📊 当月工资统计", "👤 学生库管理", "📜 历史记录明细", "📄 导出21天表", "📥 批量导入旧数据"])

# --- 模块 1：课时录入 ---
if menu == "📝 课时录入":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("input_f"):
            name = st.selectbox("👤 学生", active_s)
            date = st.date_input("📅 学习日期")
            content = st.selectbox("📚 内容", LEARN_CONTENTS)
            hour = st.selectbox("⏰ 课时 (h)", options=HOURS_OPTIONS, index=1)
            if st.form_submit_button("💾 保存同步"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success("✅ 已同步")

# --- 模块 2：复习提醒 ---
elif menu == "🔍 单词复习提醒":
    st.subheader("🔍 单词复习清单")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("查询日期", datetime.date.today())
        reminders = {}
        for _, row in r_df.iterrows():
            if row['学习内容'] in WORD_RELATED_CONTENTS:
                diff = (q_date - row['dt']).days + 1
                if diff in REVIEW_DAYS:
                    n = row['姓名']
                    if n not in reminders: reminders[n] = []
                    reminders[n].append(row['dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("今日无任务")

# --- 模块 3：工资统计 ---
elif menu == "📊 当月工资统计":
    st.subheader("💰 课时费用统计")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt'].dt.strftime('%Y-%m')
        m = st.selectbox("选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        m_df = r_df[r_df['月份'] == m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        st.metric("总计金额", f"¥{m_df['小计'].sum()}")
        st.dataframe(m_df[["姓名","学习内容","课时","小计"]], use_container_width=True)

# --- 模块 4：名册管理 ---
elif menu == "👤 学生库管理":
    st.subheader("👥 名册管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_s"):
            n = st.text_input("姓名")
            s = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("入库"):
                add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s})
                st.rerun()
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.dataframe(s_df[["姓名","状态"]], use_container_width=True)
        del_n = st.selectbox("删除学员", ["请选择"] + s_df['姓名'].tolist())
        if del_n != "请选择" and st.checkbox("确认删除"):
            if st.button("🔥 执行"):
                row = s_df[s_df['姓名'] == del_n].iloc[0]
                st.session_state['last_deleted'] = {"table": TABLE_ID_STUDENTS, "data": row.to_dict()}
                delete_feishu_record(TABLE_ID_STUDENTS, row['record_id'])
                st.rerun()

# --- 模块 5：明细查询 ---
elif menu == "📜 历史记录明细":
    st.subheader("📊 历史记录")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['显示日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","显示日期","学习内容","课时"]], use_container_width=True)
        target = st.selectbox("删除单条记录", ["请选择"] + (all_r['姓名']+" | "+all_r['显示日期']).tolist())
        if target != "请选择" and st.checkbox("确认"):
            if st.button("🔥 删除记录"):
                idx = (all_r['姓名']+" | "+all_r['显示日期']).tolist().index(target)
                row = all_r.iloc[idx].to_dict()
                st.session_state['last_deleted'] = {"table": TABLE_ID_RECORDS, "data": row}
                delete_feishu_record(TABLE_ID_RECORDS, row['record_id'])
                st.rerun()

# --- 模块 6：导出表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("选择学生", r_all['姓名'].unique())
        if st.button("生成"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天抗遗忘表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button("📥 下载表格", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块 7：批量导入 ---
elif menu == "📥 批量导入旧数据":
    st.subheader("📥 批量同步")
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f)
        if st.button("🚀 启动同步"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS)
            names_in = s_now['姓名'].tolist() if not s_now.empty else []
            bar = st.progress(0)
            for i, row in df.iterrows():
                name = str(row['姓名'])
                if name not in names_in:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                    names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": "导入", "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            st.success("🎊 同步成功")

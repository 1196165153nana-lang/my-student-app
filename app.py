# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import json
import time

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句"]
HOURS_OPTIONS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

# --- 课时费定价逻辑 ---
def get_unit_price(content):
    if content in ["初中阅读", "初中语法"]:
        return 45
    elif content in ["高中阅读", "高中完型", "长难句", "雅思单词", "大学单词", "雅思", "托福", "四六级"]:
        return 50
    elif content in ["单词", "小学阅读", "旧数据补录", "导入"]:
        return 40
    return 40 # 默认价格

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
        if not items: return pd.DataFrame()
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
    clean_fields = {k: v for k, v in fields.items() if k not in ["record_id", "显示日期", "标签"]}
    r = requests.post(url, headers=headers, json={"fields": clean_fields})
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
    ln_dates_str = "\n".join([datetime.datetime.strptime(d, "%Y-%m-%d").strftime("%m月%d日学习内容") for d in sorted_ln])
    return f"【21天抗遗忘复习提醒】\n\n{rv_date_str}复习内容为：\n\n{ln_dates_str}\n\n请{name}同学抽出时间复习 巩固单词印象 加油哦💪期待下次的课堂哦[加油][加油][加油]\n\n也请家长把复习视频发到群里🌹"

# -------------------------- 3. 界面布局 --------------------------
st.set_page_config(page_title="21天抗遗忘专业财务版", layout="centered", page_icon="🎯")

# --- 恢复功能 ---
if st.session_state['last_deleted']:
    if st.sidebar.button("🔙 恢复上一条删除"):
        add_feishu_record(st.session_state['last_deleted']['table'], st.session_state['last_deleted']['data'])
        st.session_state['last_deleted'] = None
        st.sidebar.success("已恢复！")
        time.sleep(1)
        st.rerun()

menu = st.selectbox("📌 切换功能模块", ["📊 当月工资统计", "🔍 复习提醒查询", "📝 录入课时记录", "👤 学生名单管理", "📜 历史记录明细", "📄 导出21天表", "📥 批量导入旧数据"])

# --- 模块 0：工资统计 (新功能) ---
if menu == "📊 当月工资统计":
    st.subheader("💰 课时费用统计")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt'].dt.strftime('%Y-%m')
        
        # 月份选择
        month_list = sorted(r_df['月份'].unique().tolist(), reverse=True)
        target_month = st.selectbox("选择统计月份", month_list)
        
        # 筛选当月数据
        m_df = r_df[r_df['月份'] == target_month].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时'], errors='coerce').fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        
        # 汇总展示
        total_salary = m_df['小计'].sum()
        total_hours = m_df['课时'].sum()
        
        col1, col2 = st.columns(2)
        col1.metric("当月应发工资", f"¥{total_salary:,.2f}")
        col2.metric("总授课时长", f"{total_hours} 小时")
        
        st.write("---")
        st.write(f"### 📑 {target_month} 工资核算表")
        
        # 分档统计逻辑
        def group_price(row):
            p = row['单价']
            if p == 45: return "初中阅读/语法 (45元档)"
            if p == 50: return "高中/长难句/雅思托福 (50元档)"
            if p == 40: return "单词/小学阅读 (40元档)"
            return "其他"

        m_df['分类'] = m_df.apply(group_price, axis=1)
        summary = m_df.groupby(['分类', '单价']).agg({'课时': 'sum', '小计': 'sum'}).reset_index()
        summary.columns = ["课程分类", "单价", "总数量(h)", "应发金额(元)"]
        st.table(summary)
        
        with st.expander("🔍 查看当月每一笔课时酬劳明细"):
            st.dataframe(m_df[["姓名", "学习内容", "学习日期", "课时", "单价", "小计"]], use_container_width=True)
    else:
        st.info("尚无云端记录，无法统计。")

# --- 模块 1：复习提醒查询 ---
elif menu == "🔍 复习提醒查询":
    st.subheader("🔍 复习提醒查询")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['学习日期_dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        col1, col2 = st.columns(2)
        with col1: q_date = st.date_input("选择查询日期", datetime.date.today())
        with col2:
            all_names = ["全部学生"] + sorted(r_df['姓名'].unique().tolist())
            target_student = st.selectbox("筛选学生", all_names)
        
        reminders = {}
        for _, row in r_df.iterrows():
            diff = (q_date - row['学习日期_dt']).days + 1
            if diff in REVIEW_DAYS:
                name = row['姓名']
                if target_student != "全部学生" and name != target_student: continue
                if name not in reminders: reminders[name] = []
                reminders[name].append(row['学习日期_dt'].strftime("%Y-%m-%d"))
        if reminders:
            for name, dates in reminders.items():
                with st.container(border=True):
                    st.markdown(f"👤 **学生：{name}**")
                    st.code(generate_wechat_msg(name, q_date, dates), language=None)
        else: st.info("💡 该日期暂无复习任务")

# --- 模块 2：录入课时记录 ---
elif menu == "📝 录入课时记录":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_students = s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist()
        with st.form("l_form"):
            name = st.selectbox("👤 选择学生", active_students)
            date = st.date_input("📅 学习日期")
            content = st.selectbox("📚 内容", LEARN_CONTENTS)
            hour = st.select_slider("⏰ 课时", options=HOURS_OPTIONS, value=1.0)
            if st.form_submit_button("💾 保存同步"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success(f"✅ 已同步。单价: {get_unit_price(content)}元")

# --- 模块 3：学生名单管理 ---
elif menu == "👤 学生名单管理":
    st.subheader("👥 学员库管理")
    with st.expander("➕ 添加新学员"):
        with st.form("add_s"):
            n = st.text_input("姓名")
            s = st.selectbox("状态", STATUS_OPTIONS)
            if st.form_submit_button("入库"):
                add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s})
                st.success("✅ 已入库")
                st.rerun()
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.dataframe(s_df[["姓名", "状态"]], use_container_width=True)
        del_name = st.selectbox("选择删除学生", ["请选择"] + s_df['姓名'].tolist())
        if del_name != "请选择" and st.checkbox("确认删除"):
            if st.button("🔥 执行删除"):
                row = s_df[s_df['姓名'] == del_name].iloc[0]
                st.session_state['last_deleted'] = {"table": TABLE_ID_STUDENTS, "data": row.to_dict()}
                delete_feishu_record(TABLE_ID_STUDENTS, row['record_id'])
                st.rerun()

# --- 模块 4：历史数据总表 (更名为 📜 历史记录明细) ---
elif menu == "📜 历史记录明细":
    st.subheader("📊 历史记录明细")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['课时'] = pd.to_numeric(all_r['课时'], errors='coerce').fillna(0)
        all_r['显示日期'] = pd.to_datetime(all_r['学习日期'], unit='ms', errors='coerce').dt.strftime('%Y-%m-%d')
        
        st.markdown("### 📋 详细流水账单")
        st.dataframe(all_r[["姓名", "显示日期", "学习内容", "课时"]], use_container_width=True)
        
        st.write("🗑️ **单条记录删除**")
        all_r['标签'] = all_r['姓名'] + " | " + all_r['显示日期'] + " | " + all_r['课时'].astype(str) + "h"
        target = st.selectbox("选择要删除的记录", ["请选择"] + all_r['标签'].tolist())
        if target != "请选择" and st.checkbox("确认删除该笔"):
            if st.button("🔥 执行删除"):
                idx = all_r[all_r['标签'] == target].index[0]
                row_data = all_r.iloc[idx].to_dict()
                st.session_state['last_deleted'] = {"table": TABLE_ID_RECORDS, "data": row_data}
                delete_feishu_record(TABLE_ID_RECORDS, row_data['record_id'])
                st.rerun()

# --- 模块 5/6：导出与导入 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 单人21天表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt'] = pd.to_datetime(r_all['学习日期'], unit='ms', errors='coerce').dt.date
        target = st.selectbox("选择学生", r_all['姓名'].unique())
        if st.button("生成"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt")
            output = [["21天抗遗忘表", "", ""], [f"学生姓名：{target}", "", ""], ["日期", "复习", "新学", "第1天", "第2天", "第3天", "第5天", "第7天", "第9天", "第12天", "第14天", "第17天", "第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"), "", ""] + rvs)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target}_21天表.csv", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

elif menu == "📥 批量导入旧数据":
    st.subheader("📥 批量搬家")
    file = st.file_uploader("上传 CSV", type="csv")
    if file:
        df = pd.read_csv(file)
        if st.button("🚀 确认同步"):
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
            st.success("🎊 导入完成")

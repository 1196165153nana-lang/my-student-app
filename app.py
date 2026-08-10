# -*- coding: utf-8 -*-
import streamlit as st
import requests
import pandas as pd
import datetime
import io
import time

# -------------------------- 1. 核心安全配置 (从 Secrets 读取) --------------------------
APP_ID = st.secrets["FEISHU_APP_ID"]
APP_SECRET = st.secrets["FEISHU_APP_SECRET"]
APP_TOKEN = st.secrets["FEISHU_APP_TOKEN"]
TABLE_ID_STUDENTS = st.secrets["TABLE_ID_STUDENTS"]
TABLE_ID_RECORDS = st.secrets["TABLE_ID_RECORDS"]

REVIEW_DAYS = [1, 2, 3, 5, 7, 9, 12, 14, 17, 21]
LEARN_CONTENTS = ["单词", "大学单词", "雅思单词", "小学阅读", "初中阅读", "初中语法", "高中阅读", "高中完型", "长难句", "雅思", "托福", "四六级"]
WORD_ONLY_CONTENTS = ["单词", "大学单词", "雅思单词"] 
HOURS_OPTIONS = [float(x)/2 for x in range(1, 21)] 
STATUS_OPTIONS = ["在读/上课", "停课/休假", "结课/毕业"]

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
    forbidden_keys = ["record_id", "显示日期", "标签", "小计", "单价", "分类", "dt", "月份", "学习日期_dt", "dt_obj", "统计课型", "序号"]
    clean_f = {k: v for k, v in fields.items() if k not in forbidden_keys}
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

# -------------------------- 3. 界面布局 --------------------------
st.set_page_config(page_title="21天抗遗忘专业版", layout="centered", page_icon="🎯")

# 手机适配样式
st.markdown("""
    <style>
    .stButton > button { width: 100%; height: 3em; font-weight: bold; }
    .metric-card { background-color: #1e2129; padding: 15px; border-radius: 10px; border: 1px solid #3d424d; }
    </style>
    """, unsafe_allow_html=True)

if st.session_state['undo_cache']:
    if st.sidebar.button("🔙 撤销上次删除", type="primary"):
        add_feishu_record(st.session_state['undo_cache']['table'], st.session_state['undo_cache']['data'])
        st.session_state['undo_cache'] = None
        st.sidebar.success("已恢复！")
        time.sleep(1)
        st.rerun()

menu = st.selectbox("📌 切换功能模块", ["📊 工资财务统计", "📝 课时快速录入", "🔍 单词复习提醒", "👤 学生库管理", "📜 历史记录明细", "📄 导出21天表", "📥 导入旧数据"])

# --- 模块：工资财务统计 (界面大优化) ---
if menu == "📊 工资财务统计":
    st.subheader("💰 当月工资与课时核算")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        # 数据预处理
        r_df['dt_obj'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce')
        r_df['月份'] = r_df['dt_obj'].dt.strftime('%Y-%m')
        
        target_m = st.selectbox("📅 选择月份", sorted(r_df['月份'].unique().tolist(), reverse=True))
        
        m_df = r_df[r_df['月份'] == target_m].copy()
        m_df['单价'] = m_df['学习内容'].apply(get_unit_price)
        m_df['课时'] = pd.to_numeric(m_df['课时']).fillna(0)
        m_df['小计'] = m_df['课时'] * m_df['单价']
        
        # 1. 顶部汇总信息
        total_students = m_df['姓名'].nunique()
        total_pay = m_df['小计'].sum()
        total_time = m_df['课时'].sum()
        
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("应发总工资", f"¥{total_pay:,.0f}")
        with c2: st.metric("总授课时长", f"{total_time:.1f} h")
        with c3: st.metric("上课学员数", f"{total_students} 人")
        
        st.write("---")
        
        # 2. 学生明细汇总 (核心需求：排序、序号、合并单词)
        st.markdown("#### 👤 学生个人课时排行榜")
        
        def merge_content_logic(content):
            if content in ["单词", "旧数据补录", "导入", "大学单词", "雅思单词"]:
                return "单词课(含补录/导入)"
            return content

        m_df['统计课型'] = m_df['学习内容'].apply(merge_content_logic)
        
        # 分组计算
        student_sum = m_df.groupby(['姓名', '统计课型']).agg({
            '课时': 'sum',
            '小计': 'sum'
        }).reset_index()
        
        # 【排序逻辑】先算出每个人的总课时用于整体排序
        student_order = student_sum.groupby('姓名')['课时'].sum().reset_index().sort_values('课时', ascending=False)
        
        # 按照总课时顺序合并数据
        final_display = pd.merge(student_order[['姓名']], student_sum, on='姓名', how='left')
        
        # 【序号逻辑】
        # 这里为了标记有几个学生，我们需要对姓名进行去重计数
        unique_names = student_order['姓名'].unique().tolist()
        name_to_no = {name: i+1 for i, name in enumerate(unique_names)}
        final_display.insert(0, '序号', final_display['姓名'].map(name_to_no))
        
        final_display.columns = ["序号", "学生姓名", "课程内容", "课时(h)", "小计(元)"]
        
        # 显示表格
        st.dataframe(final_display, use_container_width=True, hide_index=True)
        st.caption(f"💡 当前表格已按学生总课时由高到低排列，本月共有 {total_students} 名学生上课。")
        
        # 3. 价格档位
        with st.expander("📊 查看价格档位分布统计"):
            summary_p = m_df.groupby('单价').agg({'课时': 'sum', '小计': 'sum'}).reset_index()
            summary_p.columns = ["单价(元)", "合计时长(h)", "金额小计(元)"]
            st.table(summary_p)
            
    else: st.info("云端暂无数据")

# --- 模块：课时录入 ---
elif menu == "📝 课时快速录入":
    st.subheader("📝 课时录入")
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        active_s = sorted(s_df[s_df['状态'] == "在读/上课"]['姓名'].tolist())
        with st.form("input_f"):
            name = st.selectbox("👤 选择学员", active_s)
            date = st.date_input("📅 选择日期", datetime.date.today())
            content = st.selectbox("📚 课程内容", LEARN_CONTENTS)
            hour = st.selectbox("⏰ 课时时长", options=HOURS_OPTIONS, index=1)
            if st.form_submit_button("🚀 确认并同步云端"):
                ts = int(datetime.datetime.combine(date, datetime.time()).timestamp() * 1000)
                add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": content, "课时": hour})
                st.success(f"✅ 保存成功！{name} {hour}h")
                st.balloons()
    else: st.warning("名册为空，请先添加学生。")

# --- 模块：单词提醒 ---
elif menu == "🔍 单词复习提醒":
    st.subheader("🔍 单词复习提醒")
    r_df = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_df.empty:
        r_df['dt'] = pd.to_datetime(r_df['学习日期'], unit='ms', errors='coerce').dt.date
        q_date = st.date_input("🗓️ 提醒日期", datetime.date.today())
        target_s = st.selectbox("🎯 指定学生", ["全部学生"] + sorted(r_df['姓名'].unique().tolist()))
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
        else: st.info("该日期暂无复习任务")

# --- 模块：学生管理 ---
elif menu == "👤 学生库管理":
    st.subheader("👥 学员信息库")
    with st.expander("➕ 添加新成员"):
        with st.form("add"):
            n = st.text_input("学生姓名")
            s = st.selectbox("当前状态", STATUS_OPTIONS)
            if st.form_submit_button("保存入库"):
                if n: add_feishu_record(TABLE_ID_STUDENTS, {"姓名": n, "状态": s})
                st.rerun()
    s_df = fetch_feishu_data(TABLE_ID_STUDENTS)
    if not s_df.empty:
        st.dataframe(s_df[["姓名","状态"]], use_container_width=True, hide_index=True)
        t = st.selectbox("🗑️ 选择要注销的学生", ["请选择"] + s_df['姓名'].tolist())
        if t != "请选择" and st.checkbox("我确定要彻底删除该学生及其记录"):
            if st.button("🔥 彻底删除"):
                row = s_df[s_df['姓名'] == t].iloc[0]
                st.session_state['undo_cache'] = {"table": TABLE_ID_STUDENTS, "data": row.to_dict()}
                delete_feishu_record(TABLE_ID_STUDENTS, row['record_id'])
                st.rerun()

# --- 模块：明细明细 ---
elif menu == "📜 历史记录明细":
    st.subheader("📊 历史明细与删除")
    all_r = fetch_feishu_data(TABLE_ID_RECORDS)
    if not all_r.empty:
        all_r['日期'] = pd.to_datetime(all_r['学习日期'], unit='ms').dt.strftime('%Y-%m-%d')
        st.dataframe(all_r[["姓名","日期","学习内容","课时"]], use_container_width=True, hide_index=True)
        t = st.selectbox("🗑️ 选择要删除的单笔记录", ["请选择"] + (all_r['姓名']+" | "+all_r['日期']+" | "+all_r['学习内容']).tolist())
        if t != "请选择" and st.checkbox("确认删除此条"):
            if st.button("执行删除"):
                idx = (all_r['姓名']+" | "+all_r['日期']+" | "+all_r['学习内容']).tolist().index(t)
                row = all_r.iloc[idx].to_dict()
                st.session_state['undo_cache'] = {"table": TABLE_ID_RECORDS, "data": row}
                delete_feishu_record(TABLE_ID_RECORDS, row['record_id'])
                st.rerun()

# --- 模块：导出表 ---
elif menu == "📄 导出21天表":
    st.subheader("📄 21天抗遗忘表导出")
    r_all = fetch_feishu_data(TABLE_ID_RECORDS)
    if not r_all.empty:
        r_all['dt_obj'] = pd.to_datetime(r_all['学习日期'], unit='ms').dt.date
        target = st.selectbox("选择学员", sorted(r_all['姓名'].unique().tolist()))
        if st.button("生成表格"):
            sub = r_all[r_all['姓名'] == target].sort_values("dt_obj")
            output = [["21天抗遗忘周期表","",""], [f"姓名：{target}","",""], ["日期","复习","新学","第1天","第2天","第3天","第5天","第7天","第9天","第12天","第14天","第17天","第21天"]]
            for _, row in sub.iterrows():
                ld = row['dt_obj']
                rvs = [(ld + datetime.timedelta(days=d-1)).strftime("%Y/%m/%d") for d in REVIEW_DAYS]
                output.append([ld.strftime("%Y/%m/%d"),"",""] + rvs)
            buf = io.StringIO()
            pd.DataFrame(output).to_csv(buf, index=False, header=False, encoding="utf-8-sig")
            st.download_button(f"📥 下载 {target} 的表", buf.getvalue().encode("utf-8-sig"), f"{target}_21天表.csv", "text/csv")

# --- 模块：导入 ---
elif menu == "📥 导入旧数据":
    st.subheader("📥 批量数据同步")
    f = st.file_uploader("上传 CSV", type="csv")
    if f:
        df = pd.read_csv(f)
        if st.button("🚀 启动搬家"):
            s_now = fetch_feishu_data(TABLE_ID_STUDENTS); bar = st.progress(0)
            names_in = s_now['姓名'].tolist() if not s_now.empty else []
            for i, row in df.iterrows():
                name = str(row['姓名'])
                if name not in names_in:
                    add_feishu_record(TABLE_ID_STUDENTS, {"姓名": name, "状态": "在读/上课"})
                    names_in.append(name)
                try:
                    ld = pd.to_datetime(row['学习日期']).date()
                    ts = int(datetime.datetime.combine(ld, datetime.time()).timestamp() * 1000)
                    add_feishu_record(TABLE_ID_RECORDS, {"姓名": name, "学习日期": ts, "学习内容": str(row.get('学习内容','导入')), "课时": float(row.get('课时', 1))})
                except: pass
                bar.progress((i+1)/len(df))
            st.success("🎊 成功！")
